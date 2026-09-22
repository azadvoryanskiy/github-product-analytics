"""Everything the dashboard needs, as one small JSON file.

The page has no server behind it, so every slice the filters can produce is
counted here in advance. That is cheap because the cube is counts, not rows:
twelve features by three horizons by five activity bands by four account-age
bands is a few hundred numbers.

Percentages are deliberately *not* precomputed. The page adds up the counts for
whatever is selected and divides, which is the only way a filtered view and the
matched view can both come out right from one file.

    python src/cube.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bots import PROCESSED  # noqa: E402
from data import connect  # noqa: E402
from features import (ACTIVITY_BAND, ACTIVITY_BANDS, BASELINE, BASELINE_END,
                      BASELINE_START, FEATURES, HORIZONS, OUTCOMES)  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "docs" / "data" / "features.json"

# Registration-year bands, from the id thresholds in src/account_age.py.
AGE_BANDS = [("Joined 2025", 193367641, 10 ** 12),
             ("Joined 2023-24", 121737400, 193367640),
             ("Joined 2020-22", 59402242, 121737399),
             ("Joined before 2020", 0, 59402241)]


def age_case() -> str:
    arms = " ".join(f"WHEN actor_id BETWEEN {lo} AND {hi} THEN '{name}'"
                    for name, lo, hi in AGE_BANDS)
    return f"CASE {arms} END"


def prepare(con) -> None:
    used = ",\n".join(f'("{f}" > 0) AS "u_{f}"' for f in FEATURES)
    counts = ",\n".join(f'"{f}"' for f in FEATURES)
    n_features = " + ".join(f'CASE WHEN "{f}" > 0 THEN 1 ELSE 0 END'
                            for f in FEATURES)
    horizons = ",\n".join(
        f"max(CASE WHEN o.horizon = {h} THEN 1 ELSE 0 END) = 1 AS r{h}"
        for h in HORIZONS)
    con.execute(f"""
        CREATE OR REPLACE TABLE people AS
        SELECT b.actor_id,
               b.active_days, b.events,
               {ACTIVITY_BAND.replace('active_days', 'b.active_days')} AS band,
               {age_case().replace('actor_id', 'b.actor_id')} AS age_band,
               {n_features} AS n_features,
               {used}, {counts},
               {horizons}
        FROM read_parquet('{BASELINE}') b
        LEFT JOIN read_parquet('{OUTCOMES}') o USING (actor_id)
        GROUP BY ALL
    """)


def adoption(con) -> list[dict]:
    parts = [f"""SELECT '{f}' AS feature, band, age_band,
                        count(*) FILTER ("u_{f}") AS users,
                        count(*) AS accounts
                 FROM people GROUP BY band, age_band""" for f in FEATURES]
    return con.sql(" UNION ALL ".join(parts)).df().to_dict("records")


def retention(con) -> list[dict]:
    parts = []
    for f in FEATURES:
        for h in HORIZONS:
            parts.append(f"""
                SELECT '{f}' AS feature, {h} AS horizon, band, age_band,
                       count(*) FILTER ("u_{f}")               AS users,
                       count(*) FILTER ("u_{f}" AND r{h})      AS users_kept,
                       count(*) FILTER (NOT "u_{f}")           AS others,
                       count(*) FILTER (NOT "u_{f}" AND r{h})  AS others_kept
                FROM people GROUP BY band, age_band""")
    return con.sql(" UNION ALL ".join(parts)).df().to_dict("records")


def frequency(con) -> list[dict]:
    """Events per active day, among the people who use the feature at all."""
    parts = [f"""SELECT '{f}' AS feature,
                        round(quantile_cont("{f}" / active_days, 0.25), 2) AS p25,
                        round(quantile_cont("{f}" / active_days, 0.50), 2) AS median,
                        round(quantile_cont("{f}" / active_days, 0.75), 2) AS p75,
                        round(avg(CASE WHEN "{f}" > 0 THEN 1.0 ELSE 0 END), 4) AS x
                 FROM people WHERE "u_{f}" """ for f in FEATURES]
    df = con.sql(" UNION ALL ".join(parts)).df().drop(columns=["x"])
    return df.to_dict("records")


def pairs(con) -> list[dict]:
    out = []
    for i, a in enumerate(FEATURES):
        for b in FEATURES[i + 1:]:
            out.append(f"""
                SELECT '{a}' AS a, '{b}' AS b,
                       count(*) FILTER ("u_{a}" AND "u_{b}")          AS both,
                       count(*) FILTER ("u_{a}" AND "u_{b}" AND r90)  AS both_kept,
                       count(*) FILTER ("u_{a}" AND NOT "u_{b}")      AS only_a,
                       count(*) FILTER ("u_{a}" AND NOT "u_{b}" AND r90) AS only_a_kept,
                       count(*) FILTER (NOT "u_{a}" AND "u_{b}")      AS only_b,
                       count(*) FILTER (NOT "u_{a}" AND "u_{b}" AND r90) AS only_b_kept
                FROM people""")
    return con.sql(" UNION ALL ".join(out)).df().to_dict("records")


def curves(con) -> list[dict]:
    parts = [f"""SELECT least(n_features, 5) AS n_features, {h} AS horizon,
                        band, age_band, count(*) AS accounts,
                        count(*) FILTER (r{h}) AS kept
                 FROM people GROUP BY 1, band, age_band""" for h in HORIZONS]
    return con.sql(" UNION ALL ".join(parts)).df().to_dict("records")


def main() -> None:
    con = connect()
    print("building the person table", flush=True)
    prepare(con)
    total = con.sql("SELECT count(*) FROM people").fetchone()[0]
    print(f"{total:,} accounts in the baseline month", flush=True)

    cube = {
        "meta": {
            "baseline_start": BASELINE_START.isoformat(),
            "baseline_end": BASELINE_END.isoformat(),
            "accounts": int(total),
            "features": FEATURES,
            "activity_bands": ACTIVITY_BANDS,
            "age_bands": [name for name, _, _ in AGE_BANDS],
            "horizons": list(HORIZONS),
        },
        "adoption": adoption(con),
        "retention": retention(con),
        "frequency": frequency(con),
        "pairs": pairs(con),
        "curves": curves(con),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(cube, separators=(",", ":")))
    size = OUT.stat().st_size / 1024
    print(f"wrote {OUT}  ({size:.0f} KB)")
    for key in ("adoption", "retention", "frequency", "pairs", "curves"):
        print(f"  {key}: {len(cube[key])} rows")


if __name__ == "__main__":
    main()
