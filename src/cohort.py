"""Turn a registration week into a range of account ids.

GH Archive never says when an account was created. It does carry `actor_id`,
and GitHub issues those in registration order — checked on 370 accounts spread
across 2025, sorted by id, with zero dates going backwards.

So a week of signups is a contiguous range of ids, and the boundary between two
weeks can be found exactly by binary search against the API rather than guessed
from a sample. That matters because the cohorts are compared to each other: a
fuzzy boundary mixes one week's signups into the next.

Not every id resolves — accounts get deleted, and ids also go to organisations —
so the search steps past the gaps.

    python src/cohort.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from data import connect, events  # noqa: E402

PROCESSED = Path(__file__).resolve().parent.parent / "data" / "processed"
BOUNDARIES = PROCESSED / "week_boundaries.parquet"

# Registration weeks to build cohorts for: Monday-start, each one far enough
# from the end of the data to allow a full 28-day observation window.
FIRST_WEEK = date(2025, 6, 2)
N_WEEKS = 9
OBSERVATION_DAYS = 28


def created_at(actor_id: int) -> date | None:
    proc = subprocess.run(["gh", "api", f"user/{actor_id}"],
                          capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        return None
    raw = (json.loads(proc.stdout).get("created_at") or "")[:10]
    return date.fromisoformat(raw) if raw else None


def nearest_existing(actor_id: int, hi: int, step: int = 1) -> tuple[int, date] | None:
    """Walk forward from an id until one resolves. Gaps are only a few wide."""
    for candidate in range(actor_id, min(actor_id + 400 * step, hi), step):
        got = created_at(candidate)
        if got:
            return candidate, got
    return None


def first_id_on(target: date, lo: int, hi: int) -> int:
    """Smallest account id created on or after `target`, by binary search."""
    while lo < hi:
        mid = (lo + hi) // 2
        found = nearest_existing(mid, hi)
        if found is None:
            hi = mid          # nothing resolves up here; search lower
            continue
        actor_id, made = found
        if made < target:
            lo = actor_id + 1
        else:
            hi = actor_id
    return lo


def main() -> None:
    con = connect()
    events(con, "events_2025-0[5-9]-*.parquet", view="ev",
           window=("2025-05-26", "2025-09-05"))
    hi = int(con.sql("SELECT max(actor_id) FROM ev").fetchone()[0])

    weeks = [FIRST_WEEK + timedelta(weeks=i) for i in range(N_WEEKS + 1)]
    rows, lo = [], 200_000_000
    for week in weeks:
        boundary = first_id_on(week, lo, hi)
        check = created_at(boundary)
        print(f"{week}  first id {boundary:>12,}  (that account was made {check})",
              flush=True)
        rows.append({"week": week, "first_id": boundary})
        lo = boundary

    df = pd.DataFrame(rows)
    df["last_id"] = df.first_id.shift(-1) - 1
    df["ids_in_week"] = df.last_id - df.first_id + 1
    df = df.dropna(subset=["last_id"]).astype({"last_id": int, "ids_in_week": int})
    df.to_parquet(BOUNDARIES)
    print(f"\n{df.to_string(index=False)}\nwrote {BOUNDARIES}")


if __name__ == "__main__":
    main()
