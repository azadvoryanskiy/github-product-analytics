"""How the public GitHub event feed changed over time.

Two series, both on sampled days rather than every day:

* one 15 September per year, 2015-2026 — the long view of how much of the
  activity is automated;
* one Wednesday per month from August 2025 — a close-up on the drop in volume
  that appears during 2026.

Sampled days are all the same weekday inside each series. Activity on GitHub
swings by more than a third between a Wednesday and a Sunday, so a series built
from whatever date happened to be picked measures the calendar as much as it
measures GitHub.

    python src/timeline.py
"""

from __future__ import annotations

import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

from data import DECLARED_BOT, connect, events  # noqa: E402

BY_DAY = f"""
SELECT created_at::DATE           AS day,
       dayname(created_at)        AS weekday,
       count(*)                   AS events,
       count(DISTINCT actor_id)   AS accounts,
       sum(CASE WHEN {DECLARED_BOT} THEN 1 ELSE 0 END) AS bot_events,
       round(100.0 * sum(CASE WHEN {DECLARED_BOT} THEN 1 ELSE 0 END)
             / count(*), 1)       AS bot_pct,
       sum(CASE WHEN event_type = 'PushEvent' THEN 1 ELSE 0 END) AS pushes,
       round(100.0 * sum(CASE WHEN event_type = 'PushEvent'
                              AND {DECLARED_BOT} THEN 1 ELSE 0 END)
             / nullif(sum(CASE WHEN event_type = 'PushEvent' THEN 1 ELSE 0 END), 0),
             1)                   AS push_bot_pct
FROM {{view}}
GROUP BY 1, 2
ORDER BY 1
"""


def main() -> None:
    con = connect()

    events(con, "events_20??-09-15.parquet", view="yearly")
    print("=== one 15 September per year ===")
    print(con.sql(BY_DAY.format(view="yearly")).df().to_string(index=False))

    events(con, "events_*.parquet", view="sampled")
    print("\n=== Wednesdays, August 2025 onwards ===")
    print(
        con.sql(
            BY_DAY.format(view="sampled WHERE dayname(created_at) = 'Wednesday'")
        ).df().to_string(index=False)
    )


if __name__ == "__main__":
    main()
