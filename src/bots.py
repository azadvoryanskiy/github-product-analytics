"""How much of the public GitHub activity is not a person typing.

Three rules, applied in order, each catching what the previous one misses:

1. **Declared.** The login ends in `[bot]`. GitHub Apps always act through such
   an account, so this is the rule everyone reaches for, and the only one that
   needs no judgement.
2. **Round the clock.** Active in at least 20 of a day's 24 hours, with enough
   events that the coverage is not chance. People sleep.
3. **One target, one action.** Hundreds of events in a day, all of one type,
   into one or two repositories — the shape of a script pushing to its own
   repository on a timer.

The volume floor sits far above where people stop: the median account produces
2 events a day and the 99.9th percentile produces 166.

The per-account-per-day table is built one day at a time and cached, because
doing it in a single query means grouping ~97M rows at once, which spills more
temporary data than this machine has disk for.

    python src/bots.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from data import WINDOW_END, WINDOW_START, connect, days  # noqa: E402

PROCESSED = Path(__file__).resolve().parent.parent / "data" / "processed"
ACCOUNT_DAYS = PROCESSED / "account_days"

VOLUME_FLOOR = 200          # above the 99.9th percentile of accounts, by a lot
ROUND_THE_CLOCK_HOURS = 20

# Order matters: an account-day takes the first rule it matches, so the layers
# add up to the whole instead of double counting.
KIND = f"""
CASE
    WHEN declared THEN 'declared bot'
    WHEN hours >= {ROUND_THE_CLOCK_HOURS} AND events >= {VOLUME_FLOOR}
        THEN 'round the clock'
    WHEN events >= {VOLUME_FLOOR} AND repos <= 2 AND event_types = 1
        THEN 'one target, one action'
    ELSE 'person'
END
"""


def build_account_days(con) -> int:
    """One Parquet file of per-account totals per day. Skips days already done."""
    ACCOUNT_DAYS.mkdir(parents=True, exist_ok=True)
    built = 0
    for path in days("events_*.parquet"):
        day = Path(path).stem.removeprefix("events_")
        if not WINDOW_START <= day <= WINDOW_END:
            continue
        out = ACCOUNT_DAYS / f"{day}.parquet"
        if out.exists():
            continue
        con.execute(f"""
            COPY (
                SELECT created_at::DATE                 AS day,
                       actor_id,
                       any_value(actor_login)           AS login,
                       count(*)                         AS events,
                       count(DISTINCT hour(created_at)) AS hours,
                       count(DISTINCT repo_id)          AS repos,
                       count(DISTINCT event_type)       AS event_types,
                       max(actor_login LIKE '%[bot]')   AS declared
                FROM read_parquet('{path}')
                GROUP BY 1, 2
            ) TO '{out}' (FORMAT parquet, COMPRESSION zstd)
        """)
        built += 1
        print(f"  {day}", flush=True)
    return built


def main() -> None:
    con = connect()
    print(f"building account-days for {WINDOW_START} to {WINDOW_END}", flush=True)
    built = build_account_days(con)
    print(f"{built} day(s) built, rest already cached\n", flush=True)

    con.execute(f"""
        CREATE OR REPLACE VIEW classified AS
        SELECT *, {KIND} AS kind
        FROM read_parquet('{ACCOUNT_DAYS}/*.parquet')
    """)

    mix = con.sql("""
        SELECT kind,
               sum(events)                                             AS events,
               round(100.0 * sum(events) / sum(sum(events)) OVER (), 1) AS pct,
               count(*)                                                AS account_days
        FROM classified GROUP BY 1 ORDER BY events DESC
    """).df()
    print(f"=== what the activity is made of, {WINDOW_START} to {WINDOW_END} ===")
    print(mix.to_string(index=False))
    mix.to_parquet(PROCESSED / "mix.parquet")

    declared = float(mix.loc[mix.kind == "declared bot", "pct"].iloc[0])
    automated = float(100 - mix.loc[mix.kind == "person", "pct"].iloc[0])
    print(f"\nthe [bot] rule alone finds {declared}% of events; "
          f"all three rules find {automated:.1f}%")

    top = con.sql("""
        SELECT kind, any_value(login) AS login, actor_id,
               sum(events) AS events, count(*) AS days,
               round(avg(repos)) AS repos, round(avg(hours)) AS hours_per_day
        FROM classified
        WHERE kind NOT IN ('declared bot', 'person') AND events >= 200
        GROUP BY kind, actor_id
        QUALIFY row_number() OVER (PARTITION BY kind ORDER BY sum(events) DESC) <= 8
        ORDER BY kind, events DESC
    """).df()
    print("\n=== biggest accounts the [bot] rule misses ===")
    print(top.to_string(index=False))
    top.to_parquet(PROCESSED / "top_accounts.parquet")

    traps = con.sql("""
        SELECT 'logins used by more than one account' AS trap, count(*) AS n
        FROM (SELECT login FROM classified GROUP BY 1
              HAVING count(DISTINCT actor_id) > 1)
        UNION ALL
        SELECT 'accounts that changed their login', count(*)
        FROM (SELECT actor_id FROM classified GROUP BY 1
              HAVING count(DISTINCT login) > 1)
    """).df()
    print("\n=== identity traps ===")
    print(traps.to_string(index=False))
    traps.to_parquet(PROCESSED / "identity_traps.parquet")


if __name__ == "__main__":
    main()
