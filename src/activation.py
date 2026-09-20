"""What new GitHub accounts do in their first four weeks, and who comes back.

A cohort is one week of signups, identified by the range of account ids that
week covers (`src/cohort.py` finds the boundaries and checks them against the
API). Everyone is then measured on one clock: days since the Monday their
account was created.

* **Signed up** — ids in the week's range. An upper bound: ids also go to
  organisations, and some are never used.
* **Acted** — did anything public inside 28 days. Accounts that sign up and
  never act are invisible in this data, so this is where the funnel really
  starts, and the step above it is an estimate.
* **Came back** — was active on a second distinct day inside the 28. A second
  day, not a second event: half of all newcomers fire several events within
  minutes, and that is one sitting, not a return.

Automation is removed first, using the rules from `src/bots.py`. New accounts
are exactly where the push farms live, and leaving them in would inflate both
the numerator and the denominator.

    python src/activation.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bots import ACCOUNT_DAYS, KIND, PROCESSED  # noqa: E402
from cohort import BOUNDARIES, OBSERVATION_DAYS  # noqa: E402
from data import connect, events  # noqa: E402

OUT = PROCESSED / "activation.parquet"


def build(con) -> pd.DataFrame:
    events(con, "events_2025-0[5-9]-*.parquet", view="ev",
           window=("2025-05-26", "2025-09-05"))
    weeks = pd.read_parquet(BOUNDARIES)

    # Any account whose behaviour trips an automation rule on any day is out.
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE automated AS
        SELECT DISTINCT actor_id
        FROM (SELECT *, {KIND} AS kind
              FROM read_parquet('{ACCOUNT_DAYS}/*.parquet'))
        WHERE kind <> 'person'
    """)

    rows = []
    for w in weeks.itertuples():
        week_start = pd.Timestamp(w.week).date()
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE cohort_events AS
            SELECT e.actor_id,
                   date_diff('day', DATE '{week_start}', e.created_at::DATE) AS day,
                   e.event_type, e.action, e.repo_name, e.author_association
            FROM ev e
            WHERE e.actor_id BETWEEN {w.first_id} AND {w.last_id}
              AND e.created_at::DATE
                  BETWEEN DATE '{week_start}'
                      AND DATE '{week_start}' + {OBSERVATION_DAYS - 1}
              AND e.actor_id NOT IN (SELECT actor_id FROM automated)
        """)
        stats = con.sql("""
            SELECT count(DISTINCT actor_id) AS acted,
                   count(DISTINCT CASE WHEN days >= 2 THEN actor_id END) AS came_back
            FROM (SELECT actor_id, count(DISTINCT day) AS days
                  FROM cohort_events GROUP BY actor_id)
        """).df().iloc[0]
        rows.append({
            "week": week_start,
            "ids_in_week": int(w.ids_in_week),
            "acted": int(stats.acted),
            "came_back": int(stats.came_back),
        })
        print(f"  {week_start}  acted {int(stats.acted):>7,}  "
              f"came back {int(stats.came_back):>7,}", flush=True)

    df = pd.DataFrame(rows)
    df["acted_pct"] = (100 * df.acted / df.ids_in_week).round(1)
    df["activation_pct"] = (100 * df.came_back / df.acted).round(1)
    return df


def main() -> None:
    con = connect()
    print(f"building {OBSERVATION_DAYS}-day cohorts", flush=True)
    df = build(con)
    df.to_parquet(OUT)
    print("\n=== signup cohorts, first 28 days ===")
    print(df.to_string(index=False))
    print(f"\nacross all weeks: {df.came_back.sum():,} of {df.acted.sum():,} "
          f"newcomers came back on a second day "
          f"({100 * df.came_back.sum() / df.acted.sum():.1f}%)")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()


# --- what separates the ones who come back ----------------------------------

FIRST_DAY_FEATURES = """
CREATE OR REPLACE TEMP TABLE newcomers AS
WITH mine AS (
    SELECT e.actor_id, any_value(e.actor_login) AS login,
           min(e.created_at::DATE) AS first_day
    FROM ev e
    WHERE e.actor_id BETWEEN {first_id} AND {last_id}
      AND e.created_at::DATE BETWEEN DATE '{start}'
                                 AND DATE '{start}' + {span}
      AND e.actor_id NOT IN (SELECT actor_id FROM automated)
    GROUP BY e.actor_id
),
day_one AS (
    -- Everything the account did on its very first active day. Features come
    -- only from here; the outcome comes only from later days, so nothing the
    -- outcome is made of can leak into a feature.
    SELECT m.actor_id,
           count(*)                                              AS events,
           count(DISTINCT e.repo_id)                             AS repos,
           max(e.event_type = 'PushEvent')                       AS pushed,
           max(e.event_type = 'PullRequestEvent'
               AND e.action = 'opened')                          AS opened_pr,
           max(e.event_type IN ('IssueCommentEvent',
                                'PullRequestReviewCommentEvent')) AS commented,
           max(e.event_type = 'IssuesEvent' AND e.action = 'opened') AS opened_issue,
           max(e.event_type = 'WatchEvent')                      AS starred,
           max(e.event_type = 'ForkEvent')                       AS forked,
           max(e.repo_name NOT LIKE m.login || '/%')             AS touched_someone_elses,
           max(coalesce(e.author_association, 'NONE') = 'NONE'
               AND e.repo_name NOT LIKE m.login || '/%')         AS outside_contribution
    FROM mine m JOIN ev e
      ON e.actor_id = m.actor_id AND e.created_at::DATE = m.first_day
    GROUP BY m.actor_id
),
replies AS (
    -- Someone other than the newcomer acting on the newcomer's issue or PR,
    -- on that same first day.
    SELECT m.actor_id, count(*) AS replies
    FROM mine m JOIN ev e
      ON e.target_author = m.login AND e.actor_id <> m.actor_id
     AND e.created_at::DATE BETWEEN m.first_day AND m.first_day + 1
    GROUP BY m.actor_id
),
outcome AS (
    SELECT m.actor_id,
           max(e.created_at::DATE > m.first_day) AS came_back
    FROM mine m JOIN ev e
      ON e.actor_id = m.actor_id
     AND e.created_at::DATE BETWEEN DATE '{start}' AND DATE '{start}' + {span}
    GROUP BY m.actor_id
)
SELECT d.*, coalesce(r.replies, 0) > 0 AS got_a_reply, o.came_back
FROM day_one d
JOIN outcome o USING (actor_id)
LEFT JOIN replies r USING (actor_id)
"""

DRIVERS = """
SELECT '{label}' AS feature, did_it,
       count(*) AS accounts,
       round(100.0 * avg(came_back::INT), 1) AS came_back_pct
FROM newcomers GROUP BY did_it
"""


def drivers(con) -> pd.DataFrame:
    weeks = pd.read_parquet(BOUNDARIES)
    frames = []
    for w in weeks.itertuples():
        con.execute(FIRST_DAY_FEATURES.format(
            first_id=w.first_id, last_id=w.last_id,
            start=pd.Timestamp(w.week).date(), span=OBSERVATION_DAYS - 1))
        con.execute(f"""
            CREATE OR REPLACE TABLE wk_{w.Index} AS SELECT * FROM newcomers
        """)
        frames.append(f"wk_{w.Index}")
        print(f"  features built for {pd.Timestamp(w.week).date()}", flush=True)
    con.execute("CREATE OR REPLACE TABLE all_newcomers AS "
                + " UNION ALL ".join(f"SELECT * FROM {f}" for f in frames))
    return con.sql("SELECT count(*) AS newcomers FROM all_newcomers").df()
