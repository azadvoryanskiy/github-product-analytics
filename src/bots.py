"""How much of the public GitHub activity is not a person typing.

Three rules, applied in order, each one catching what the previous rule misses:

1. **Declared.** The login ends in `[bot]`. GitHub Apps always act through such
   an account, so this is the rule everyone reaches for. It is also the only
   one that needs no judgement.
2. **Round the clock.** An account active in at least 20 of the 24 hours of a
   day, with enough events that the coverage is not chance. People sleep;
   nothing else in this data separates automation as cleanly.
3. **One target, one action.** An account that does hundreds of events in a
   day, all of the same type, into one or two repositories. This is the shape
   of a script pushing to its own repository on a timer.

The volume floor is set well above where people stop: on 11 June 2025 the
median account produced 2 events and the 99.9th percentile produced 166.

    python src/bots.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from data import connect, events  # noqa: E402

# Above the 99.9th percentile of accounts, by a wide margin.
VOLUME_FLOOR = 200
ROUND_THE_CLOCK_HOURS = 20

ACCOUNT_DAYS = f"""
CREATE OR REPLACE TABLE account_days AS
SELECT
    created_at::DATE                     AS day,
    actor_id,
    any_value(actor_login)               AS login,
    count(*)                             AS events,
    count(DISTINCT hour(created_at))     AS hours,
    count(DISTINCT repo_id)              AS repos,
    count(DISTINCT event_type)           AS event_types,
    max(actor_login LIKE '%[bot]')       AS declared
FROM {{view}}
GROUP BY 1, 2
"""

# Order matters: an account day is assigned to the first rule that matches, so
# the layers add up to the total instead of double counting.
CLASSIFY = f"""
CREATE OR REPLACE TABLE classified AS
SELECT *,
    CASE
        WHEN declared THEN 'declared bot'
        WHEN hours >= {ROUND_THE_CLOCK_HOURS} AND events >= {VOLUME_FLOOR}
            THEN 'round the clock'
        WHEN events >= {VOLUME_FLOOR} AND repos <= 2 AND event_types = 1
            THEN 'one target, one action'
        ELSE 'person'
    END AS kind
FROM account_days
"""


def main() -> None:
    con = connect()
    events(con, "events_2025-0[4-8]-*.parquet", view="ev")
    con.execute(ACCOUNT_DAYS.format(view="ev"))
    con.execute(CLASSIFY)

    print("=== what the activity is made of, 21 Apr - 14 Aug 2025 ===")
    print(con.sql("""
        SELECT kind,
               count(*)                                            AS account_days,
               sum(events)                                         AS events,
               round(100.0 * sum(events) / sum(sum(events)) OVER (), 1) AS pct_events
        FROM classified GROUP BY 1 ORDER BY events DESC
    """).df().to_string(index=False))

    print("\n=== what each rule adds, as a share of all events ===")
    print(con.sql("""
        SELECT
            round(100.0 * sum(CASE WHEN kind = 'declared bot' THEN events ELSE 0 END)
                  / sum(events), 1) AS declared_only,
            round(100.0 * sum(CASE WHEN kind <> 'person' THEN events ELSE 0 END)
                  / sum(events), 1) AS all_three_rules
        FROM classified
    """).df().to_string(index=False))

    print("\n=== biggest accounts each rule catches that [bot] misses ===")
    print(con.sql("""
        SELECT kind, login, sum(events) AS events, count(*) AS days,
               round(avg(repos)) AS avg_repos, round(avg(hours)) AS avg_hours
        FROM classified WHERE kind NOT IN ('declared bot', 'person')
        GROUP BY 1, 2 QUALIFY row_number() OVER (PARTITION BY kind ORDER BY sum(events) DESC) <= 8
        ORDER BY kind, events DESC
    """).df().to_string(index=False))

    con.execute("COPY classified TO 'data/processed/classified.parquet' (FORMAT parquet)")
    print("\nwrote data/processed/classified.parquet")


if __name__ == "__main__":
    main()
