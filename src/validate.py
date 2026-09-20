"""Check the bot rules against GitHub itself.

The GitHub API cannot confirm the behavioural rules: an account running a
script on a timer is a user account, and the API says `"type": "User"`. What it
can do is say whether the account still exists. GitHub removes accounts that
abuse the platform, so if the rules are finding real automation, the accounts
they flag should disappear at a higher rate than the accounts they do not.

Also records each account's creation date, which is the calibration needed to
turn `actor_id` into an approximate signup date later.

    python src/validate.py [accounts_per_rule]
"""

from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bots import ACCOUNT_DAYS, KIND  # noqa: E402
from data import connect  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "data" / "processed" / "validation.parquet"


def look_up(actor_id: int) -> dict:
    """Ask the API about one account id. A 404 means it is gone."""
    proc = subprocess.run(
        ["gh", "api", f"user/{actor_id}"], capture_output=True, text=True, timeout=60
    )
    if proc.returncode != 0:
        # 404 is the answer we are after; anything else is a problem worth seeing.
        gone = "Not Found" in proc.stderr or '"status": "404"' in proc.stdout
        return {"actor_id": actor_id, "exists": False if gone else None,
                "error": None if gone else proc.stderr.strip()[:120]}
    body = json.loads(proc.stdout)
    return {
        "actor_id": actor_id,
        "exists": True,
        "api_type": body.get("type"),
        "created_at": (body.get("created_at") or "")[:10],
        "public_repos": body.get("public_repos"),
        "followers": body.get("followers"),
    }


def main(per_rule: int = 150) -> None:
    con = connect()
    con.execute(f"""
        CREATE VIEW c AS SELECT *, {KIND} AS kind
        FROM read_parquet('{ACCOUNT_DAYS}/*.parquet')
    """)
    sample = con.sql(f"""
        SELECT kind, actor_id, any_value(login) AS login, sum(events) AS events
        FROM c GROUP BY kind, actor_id
        QUALIFY row_number() OVER (PARTITION BY kind ORDER BY random()) <= {per_rule}
    """).df()
    print(f"looking up {len(sample)} accounts", flush=True)

    with ThreadPoolExecutor(max_workers=8) as pool:
        looked_up = list(pool.map(look_up, sample.actor_id.tolist()))

    df = sample.merge(pd.DataFrame(looked_up), on="actor_id", how="left")
    df.to_parquet(OUT)

    print("\n=== accounts that no longer exist on GitHub ===")
    summary = df.groupby("kind").agg(
        sampled=("actor_id", "size"),
        gone=("exists", lambda s: int((s == False).sum())),  # noqa: E712
        errors=("exists", lambda s: int(s.isna().sum())),
    )
    summary["gone_pct"] = (100 * summary.gone / summary.sampled).round(1)
    print(summary.to_string())

    print("\n=== what the API calls the ones that still exist ===")
    alive = df[df.exists == True]  # noqa: E712
    print(pd.crosstab(alive.kind, alive.api_type).to_string())

    print("\n=== public repositories per account (median) ===")
    print(alive.groupby("kind").public_repos.median().to_string())
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 150)
