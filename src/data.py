"""Shared access to the extracted GH Archive events."""

from __future__ import annotations

import glob
from pathlib import Path

import duckdb

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


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
    return con


def days(pattern: str = "events_*.parquet") -> list[str]:
    """Paths of extracted days matching a glob, sorted by date."""
    return sorted(str(p) for p in RAW_DIR.glob(pattern))


def events(con: duckdb.DuckDBPyConnection, pattern: str = "events_*.parquet",
           view: str = "ev") -> duckdb.DuckDBPyConnection:
    """Register the matching days as a view."""
    paths = days(pattern)
    if not paths:
        raise FileNotFoundError(f"no extracted days match {pattern} in {RAW_DIR}")
    con.execute(f"CREATE OR REPLACE VIEW {view} AS SELECT * FROM read_parquet({paths})")
    return con


# An account is a declared bot when GitHub itself marks it: every GitHub App
# acts through a login ending in "[bot]". It is the rule everyone reaches for,
# and the bots case study measures how much it misses.
DECLARED_BOT = "actor_login LIKE '%[bot]'"
