"""Account id thresholds for each year, so an id can be read as an age.

`src/cohort.py` proved ids are issued in registration order. That makes the id
axis a timeline: find the first id issued on 1 January of each year and any
account can be placed in a year without asking the API about it.

    python src/account_age.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bots import PROCESSED  # noqa: E402
from cohort import created_at, first_id_on  # noqa: E402

YEARS = range(2012, 2026)
OUT = PROCESSED / "year_boundaries.parquet"


def main() -> None:
    rows, lo, hi = [], 1, 231_000_000
    for year in YEARS:
        boundary = first_id_on(date(year, 1, 1), lo, hi)
        print(f"{year}: first id {boundary:>12,}  "
              f"(checked: {created_at(boundary)})", flush=True)
        rows.append({"year": year, "first_id": boundary})
        lo = boundary
    df = pd.DataFrame(rows)
    df["accounts_created"] = df.first_id.diff().shift(-1)
    df.to_parquet(OUT)
    print(f"\n{df.to_string(index=False)}\nwrote {OUT}")


if __name__ == "__main__":
    main()
