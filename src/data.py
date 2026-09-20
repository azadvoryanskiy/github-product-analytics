"""Shared access to the extracted GH Archive events."""

from __future__ import annotations

import glob
from pathlib import Path

import duckdb

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

# The analysis window, fixed here so every script and notebook counts the same
# days. It is one unbroken run. Sampled days outside it — one per year back to
# 2015, one Wednesday a month into 2026 — exist in data/raw for the long-range
# charts and must not leak into the main figures, which is what `window` is for.
WINDOW_START, WINDOW_END = "2025-04-21", "2025-09-05"

# Everything from 26 May 2025 is after the rate cap. The case studies that need
# a cohort and a follow-up start here; only the data-quality one crosses the cap,
# because the cap is its subject.
POST_CAP_START = "2025-05-26"


def connect() -> duckdb.DuckDBPyConnection:
    """A DuckDB connection that reports timestamps in UTC.

    `created_at` is stored as TIMESTAMP WITH TIME ZONE, so DuckDB renders it in
    the session's timezone. On a laptop in Calgary that silently shifts every
    event six hours back, which splits each UTC day across two local dates and
    makes complete days look like they are missing six hours. Every connection
    here is pinned to UTC so a "day" always means the UTC day GH Archive
    published.
    """
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    # This laptop has little free disk, and DuckDB spills to it. Capping memory
    # and dropping the ordering guarantee keeps a wide GROUP BY from filling the
    # drive; nothing here depends on row order.
    con.execute("SET memory_limit='4GB'")
    con.execute("SET preserve_insertion_order=false")
    return con


def days(pattern: str = "events_*.parquet") -> list[str]:
    """Paths of extracted days matching a glob, sorted by date."""
    return sorted(str(p) for p in RAW_DIR.glob(pattern))


def events(con: duckdb.DuckDBPyConnection, pattern: str = "events_*.parquet",
           view: str = "ev", window: tuple[str, str] | None = None
           ) -> duckdb.DuckDBPyConnection:
    """Register the matching days as a view.

    `window` clips to a date range. Pass it whenever the figure should cover the
    analysis window rather than every day that happens to be extracted — a glob
    alone would quietly pull in the sampled days and draw them as a broken line.
    """
    paths = days(pattern)
    if not paths:
        raise FileNotFoundError(f"no extracted days match {pattern} in {RAW_DIR}")
    where = ""
    if window:
        where = (f" WHERE created_at::DATE BETWEEN DATE '{window[0]}'"
                 f" AND DATE '{window[1]}'")
    # union_by_name keeps a day extracted under an older column set from
    # failing the whole glob: the columns it lacks come back NULL instead.
    # Sampled days outside the analysis window are deliberately left that way.
    con.execute(
        f"CREATE OR REPLACE VIEW {view} AS "
        f"SELECT * FROM read_parquet({paths}, union_by_name=true){where}"
    )
    return con


# An account is a declared bot when GitHub itself marks it: every GitHub App
# acts through a login ending in "[bot]". It is the rule everyone reaches for,
# and the bots case study measures how much it misses.
DECLARED_BOT = "actor_login LIKE '%[bot]'"
