"""Feature usage and retention: the data model behind the dashboard.

**Population.** Every account with at least one event in a baseline month,
minus the automation caught by `src/bots.py`.

**Features.** GH Archive event types grouped into the things a person would
call a feature. Several event types make up one feature — a review and a review
comment are both "code review".

**Outcome.** Still active later, checked over a fortnight rather than on a
single day, because one day is mostly noise: an account is retained at 90 days
if it did anything in the fourteen days ending on day 90.

**Matching.** Everything is also cut by how many days the account was active in
the baseline month. People who use more of the product are more active and stay
longer, so an unmatched comparison mostly measures activity. The dashboard
shows both and lets you switch.

    python src/features.py
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bots import ACCOUNT_DAYS, KIND, PROCESSED  # noqa: E402
from data import connect, days as extracted_days  # noqa: E402

BASELINE_START = date(2025, 5, 26)      # first full day after the rate cap
BASELINE_DAYS = 30
BASELINE_END = BASELINE_START + timedelta(days=BASELINE_DAYS - 1)

# Retention is checked over the fortnight ending on each horizon.
HORIZONS = (30, 60, 90)
CHECK_WINDOW = 14

FEATURE_DIR = PROCESSED / "feature_days"
BASELINE = PROCESSED / "baseline.parquet"
OUTCOMES = PROCESSED / "outcomes.parquet"

# One SQL CASE, used everywhere, so the dashboard and the write-up cannot drift
# apart on what counts as which feature.
FEATURE = """
CASE event_type
    WHEN 'PushEvent'                     THEN 'Push code'
    WHEN 'PullRequestEvent'              THEN 'Pull requests'
    WHEN 'PullRequestReviewEvent'        THEN 'Code review'
    WHEN 'PullRequestReviewCommentEvent' THEN 'Code review'
    WHEN 'IssuesEvent'                   THEN 'Issues'
    WHEN 'IssueCommentEvent'             THEN 'Comments'
    WHEN 'CommitCommentEvent'            THEN 'Comments'
    WHEN 'WatchEvent'                    THEN 'Stars'
    WHEN 'ForkEvent'                     THEN 'Forks'
    WHEN 'CreateEvent'                   THEN 'Branches and repos'
    WHEN 'DeleteEvent'                   THEN 'Branches and repos'
    WHEN 'ReleaseEvent'                  THEN 'Releases'
    WHEN 'GollumEvent'                   THEN 'Wiki'
    WHEN 'MemberEvent'                   THEN 'Collaborators'
    ELSE NULL
END
"""

# Discussions is missing on purpose. GitHub only began publishing
# DiscussionEvent to the events feed in October 2025 — the baseline month has
# exactly zero of them, which would draw an empty bar and read as "nobody uses
# Discussions" rather than "this feed cannot see it".
FEATURES = ["Push code", "Pull requests", "Code review", "Issues", "Comments",
            "Stars", "Forks", "Branches and repos", "Releases", "Wiki",
            "Collaborators"]

# Bands of how many days the account was active in the baseline month. Active
# days rather than event count: a single burst of two hundred pushes is one
# day of using the product, not a heavy user.
ACTIVITY_BAND = """
CASE WHEN active_days = 1 THEN '1 day'
     WHEN active_days <= 3 THEN '2-3 days'
     WHEN active_days <= 7 THEN '4-7 days'
     WHEN active_days <= 15 THEN '8-15 days'
     ELSE '16+ days' END
"""
ACTIVITY_BANDS = ["1 day", "2-3 days", "4-7 days", "8-15 days", "16+ days"]


def day_files(first: date, last: date) -> list[str]:
    return [p for p in extracted_days("events_*.parquet")
            if first.isoformat() <= Path(p).stem.removeprefix("events_")
            <= last.isoformat()]


def build_feature_days(con) -> None:
    """Per account, per day, per feature: how many events. One file per day."""
    FEATURE_DIR.mkdir(parents=True, exist_ok=True)
    for path in day_files(BASELINE_START, BASELINE_END):
        day = Path(path).stem.removeprefix("events_")
        out = FEATURE_DIR / f"{day}.parquet"
        if out.exists():
            continue
        con.execute(f"""
            COPY (
                SELECT created_at::DATE AS day, actor_id,
                       {FEATURE} AS feature, count(*) AS events
                FROM read_parquet('{path}', union_by_name=true)
                WHERE {FEATURE} IS NOT NULL
                GROUP BY 1, 2, 3
            ) TO '{out}' (FORMAT parquet, COMPRESSION zstd)
        """)
        print(f"  {day}", flush=True)


def build_baseline(con) -> None:
    """One row per account: activity, and events per feature, in the month."""
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE automated AS
        SELECT DISTINCT actor_id
        FROM (SELECT *, {KIND} AS kind
              FROM read_parquet('{ACCOUNT_DAYS}/*.parquet'))
        WHERE kind <> 'person'
    """)
    pivot = ",\n".join(
        f"""sum(CASE WHEN feature = '{f}' THEN events ELSE 0 END) AS "{f}" """
        for f in FEATURES)
    con.execute(f"""
        COPY (
            SELECT actor_id,
                   count(DISTINCT day) AS active_days,
                   sum(events)         AS events,
                   {pivot}
            FROM read_parquet('{FEATURE_DIR}/*.parquet')
            WHERE actor_id NOT IN (SELECT actor_id FROM automated)
            GROUP BY actor_id
        ) TO '{BASELINE}' (FORMAT parquet, COMPRESSION zstd)
    """)


def build_outcomes(con) -> None:
    """Was the account active in the fortnight ending at each horizon?"""
    parts = []
    for h in HORIZONS:
        end = BASELINE_END + timedelta(days=h)
        start = end - timedelta(days=CHECK_WINDOW - 1)
        files = day_files(start, end)
        if not files:
            raise SystemExit(f"no extracted days for the {h}-day window "
                             f"({start} .. {end})")
        parts.append(f"""
            SELECT actor_id, {h} AS horizon
            FROM read_parquet({files}, union_by_name=true)
            GROUP BY actor_id
        """)
        print(f"  {h}-day window: {start} .. {end}, {len(files)} days", flush=True)
    con.execute(f"""
        COPY ({' UNION ALL '.join(parts)})
        TO '{OUTCOMES}' (FORMAT parquet, COMPRESSION zstd)
    """)


def main() -> None:
    con = connect()
    print(f"baseline month {BASELINE_START} .. {BASELINE_END}", flush=True)
    build_feature_days(con)
    print("aggregating the month", flush=True)
    build_baseline(con)
    print("outcome windows", flush=True)
    build_outcomes(con)

    summary = con.sql(f"""
        SELECT count(*) AS accounts,
               round(avg(active_days), 2) AS mean_active_days,
               round(median(events), 1) AS median_events
        FROM read_parquet('{BASELINE}')
    """).df()
    print(f"\n{summary.to_string(index=False)}")
    print(con.sql(f"""
        SELECT horizon, count(*) AS accounts_seen
        FROM read_parquet('{OUTCOMES}') GROUP BY 1 ORDER BY 1
    """).df().to_string(index=False))


if __name__ == "__main__":
    main()
