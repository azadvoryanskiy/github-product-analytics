"""Download GH Archive hourly files and write one compact Parquet file per day.

GH Archive publishes every public GitHub event as one gzipped JSON file per
hour (https://data.gharchive.org/YYYY-MM-DD-H.json.gz). A full day is about
1 GB gzipped and 5 GB once unpacked, which is too much to keep around, so this
script works one hour at a time: download, keep the fields we need, append to
the day's Parquet file, delete the download. Peak disk use is one hourly file
(20-60 MB) plus the output.

The output keeps roughly 1.5% of the original bytes. Most of the raw file is
issue and comment text inside `payload`, which none of the analyses need.

Usage:
    python src/extract.py 2026-09-07:2026-09-13
    python src/extract.py 2015-09-15 2016-09-15 2017-09-15
"""

from __future__ import annotations

import gzip
import os
import sys
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

import orjson
import pyarrow as pa
import pyarrow.parquet as pq
import requests

BASE_URL = "https://data.gharchive.org"
# Hours downloaded ahead of the one being parsed. Downloading is the slow
# step, so a few in flight roughly halves the wall clock; the window is kept
# small because each unparsed hour sits in memory at ~100 MB.
PREFETCH = 4
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
TMP_DIR = OUT_DIR / "tmp"

# Kept deliberately wide: re-downloading 90 days to add one column is painful,
# and these columns cost almost nothing next to the payload text we drop.
SCHEMA = pa.schema(
    [
        ("event_id", pa.string()),
        ("event_type", pa.string()),
        ("created_at", pa.timestamp("s", tz="UTC")),
        ("actor_id", pa.int64()),
        ("actor_login", pa.string()),
        ("repo_id", pa.int64()),
        ("repo_name", pa.string()),
        ("org_id", pa.int64()),
        ("org_login", pa.string()),
        ("action", pa.string()),
        ("ref_type", pa.string()),
        ("pusher_type", pa.string()),
        # The issue or pull request the event is about, when there is one.
        ("target_number", pa.int64()),
        ("target_author", pa.string()),
        ("target_created_at", pa.timestamp("s", tz="UTC")),
        # Present only before 7 October 2025, when GitHub cut the Events API
        # payloads down. NULL afterwards. See docs/data_notes.md.
        ("author_association", pa.string()),
        ("pr_merged", pa.bool_()),
        ("pr_additions", pa.int64()),
        ("pr_deletions", pa.int64()),
        ("pr_changed_files", pa.int64()),
        ("pr_comments", pa.int64()),
    ]
)

# payload.action is absent on these; recording it as NULL rather than inventing
# a value keeps "no action" and "action we failed to parse" distinguishable.
_NO_ACTION = {"PushEvent", "CreateEvent", "DeleteEvent", "GollumEvent", "PublicEvent"}


def _int(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _target(payload: dict) -> dict:
    """Facts about the issue or pull request an event is about.

    How much comes back depends on when the event happened. Until 7 October
    2025 the `pull_request` object carried 48 fields, including whether it was
    merged, how many lines it touched, and `author_association` — GitHub's own
    label for whether the author was a first-time contributor, a collaborator
    or a member. From that date it carries five: base, head, id, number, url.

    Everything the later payloads dropped comes back as NULL rather than as a
    default, so "we do not know" stays distinguishable from "no".
    """
    obj = payload.get("issue") or payload.get("pull_request")
    if not isinstance(obj, dict):
        return {"target_number": _int(payload.get("number"))}
    user = obj.get("user")
    merged = obj.get("merged")
    return {
        "target_number": _int(obj.get("number")),
        "target_author": user.get("login") if isinstance(user, dict) else None,
        "target_created_at": obj.get("created_at"),
        "author_association": obj.get("author_association")
        or (payload.get("comment") or {}).get("author_association"),
        "pr_merged": merged if isinstance(merged, bool) else None,
        "pr_additions": _int(obj.get("additions")),
        "pr_deletions": _int(obj.get("deletions")),
        "pr_changed_files": _int(obj.get("changed_files")),
        "pr_comments": _int(obj.get("comments")),
    }


def parse_hour(raw: bytes) -> dict[str, list]:
    """Turn one hour of newline-delimited JSON into column arrays."""
    cols: dict[str, list] = {name: [] for name in SCHEMA.names}
    for line in gzip.decompress(raw).splitlines():
        if not line:
            continue
        try:
            ev = orjson.loads(line)
        except orjson.JSONDecodeError:
            continue

        actor = ev.get("actor") or {}
        repo = ev.get("repo") or {}
        org = ev.get("org") or {}
        payload = ev.get("payload") or {}
        event_type = ev.get("type")
        target = _target(payload)

        cols["event_id"].append(ev.get("id"))
        cols["event_type"].append(event_type)
        cols["created_at"].append(ev.get("created_at"))
        cols["actor_id"].append(actor.get("id"))
        # display_login is the current name; login can be an old one after a
        # rename. actor_id is the only stable identity, so analyses key on it.
        cols["actor_login"].append(actor.get("login") or actor.get("display_login"))
        cols["repo_id"].append(repo.get("id"))
        cols["repo_name"].append(repo.get("name"))
        cols["org_id"].append(org.get("id"))
        cols["org_login"].append(org.get("login"))
        cols["action"].append(None if event_type in _NO_ACTION else payload.get("action"))
        cols["ref_type"].append(payload.get("ref_type"))
        cols["pusher_type"].append(payload.get("pusher_type"))
        for key in (
            "target_number",
            "target_author",
            "target_created_at",
            "author_association",
            "pr_merged",
            "pr_additions",
            "pr_deletions",
            "pr_changed_files",
            "pr_comments",
        ):
            cols[key].append(target.get(key))
    return cols


def _column(name: str, values: list) -> pa.Array:
    """Build one Arrow column, parsing the ISO-8601 timestamp strings.

    Arrow casts "2026-09-15T15:00:00Z" straight to a UTC timestamp, which is
    far faster than parsing 1.4M strings in Python. A single odd value would
    fail the whole cast, so that case falls back to parsing one at a time and
    dropping what will not parse, rather than losing the day.
    """
    field_type = SCHEMA.field(name).type
    if not pa.types.is_timestamp(field_type):
        return pa.array(values, type=field_type)
    strings = pa.array(values, type=pa.string())
    try:
        return strings.cast(field_type)
    except pa.ArrowInvalid:
        print(f"    {name}: some timestamps did not parse, falling back")
        parsed = []
        for value in values:
            try:
                parsed.append(datetime.fromisoformat(value) if value else None)
            except (TypeError, ValueError):
                parsed.append(None)
        return pa.array(parsed, type=field_type)


def to_batch(cols: dict[str, list]) -> pa.RecordBatch:
    return pa.record_batch(
        [_column(name, cols[name]) for name in SCHEMA.names], schema=SCHEMA
    )


def fetch(url: str, attempts: int = 4) -> bytes | None:
    """Download one hourly file. Returns None if GH Archive does not have it.

    Hours genuinely go missing — GH Archive has gaps from GitHub API outages —
    so a 404 is data, not a failure, and gets recorded rather than retried.
    """
    for attempt in range(attempts):
        try:
            resp = requests.get(url, timeout=120)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.content
        except requests.RequestException as exc:
            if attempt == attempts - 1:
                raise
            print(f"    retry {attempt + 1}/{attempts - 1} after {exc}")
            time.sleep(2 ** attempt)
    return None


def extract_day(day: date, overwrite: bool = False) -> None:
    out_path = OUT_DIR / f"events_{day:%Y-%m-%d}.parquet"
    if out_path.exists() and not overwrite:
        print(f"{day}  already done, skipping", flush=True)
        return

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    # The pid keeps two copies of this script from writing the same temp
    # file: without it they race, and one renames a file the other is still
    # writing, leaving a truncated Parquet behind.
    tmp_path = TMP_DIR / f"{day:%Y-%m-%d}.{os.getpid()}.parquet"
    started = time.time()
    rows = missing = 0

    def url(hour: int) -> str:
        return f"{BASE_URL}/{day:%Y-%m-%d}-{hour}.json.gz"

    writer = pq.ParquetWriter(tmp_path, SCHEMA, compression="zstd")
    try:
        with ThreadPoolExecutor(max_workers=PREFETCH) as pool:
            in_flight: deque = deque()
            next_hour = 0
            while next_hour < min(PREFETCH, 24):
                in_flight.append((next_hour, pool.submit(fetch, url(next_hour))))
                next_hour += 1

            while in_flight:
                hour, future = in_flight.popleft()
                raw = future.result()
                if next_hour < 24:
                    in_flight.append((next_hour, pool.submit(fetch, url(next_hour))))
                    next_hour += 1
                if raw is None:
                    missing += 1
                    print(f"    {day} hour {hour}: not published by GH Archive",
                          flush=True)
                    continue
                batch = to_batch(parse_hour(raw))
                writer.write_batch(batch)
                rows += batch.num_rows
    finally:
        writer.close()

    tmp_path.replace(out_path)
    size_mb = out_path.stat().st_size / 1e6
    note = f", {missing} hours missing" if missing else ""
    print(
        f"{day}  {rows:>9,} events  {size_mb:6.1f} MB  "
        f"{time.time() - started:5.1f}s{note}",
        flush=True,
    )


def parse_dates(args: list[str]) -> list[date]:
    """Accept single dates and START:END ranges (both ends included)."""
    days: list[date] = []
    for arg in args:
        if ":" in arg:
            start_s, end_s = arg.split(":", 1)
            start, end = date.fromisoformat(start_s), date.fromisoformat(end_s)
            if end < start:
                raise SystemExit(f"range {arg} ends before it starts")
            days.extend(start + timedelta(days=i) for i in range((end - start).days + 1))
        else:
            days.append(date.fromisoformat(arg))
    return days


def main(argv: list[str]) -> None:
    if not argv:
        raise SystemExit(__doc__)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    days = parse_dates(argv)
    print(f"{len(days)} day(s) -> {OUT_DIR}", flush=True)
    for day in days:
        extract_day(day)


if __name__ == "__main__":
    main(sys.argv[1:])
