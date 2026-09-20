"""What separates the newcomers who come back from the ones who do not.

Reads the per-newcomer table `src/activation.py` builds: one row per account,
features from its first active day only, outcome from the days after it.

Every comparison is run twice — once raw, once inside bands of how much the
account did on day one. Newcomers who do more of anything come back more often,
so a raw gap mostly measures eagerness. What survives the banding is the part
that is about the thing itself.

    python src/drivers.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bots import PROCESSED  # noqa: E402
from data import connect  # noqa: E402

NEWCOMERS = PROCESSED / "newcomers.parquet"
BANDS = ["1", "2-3", "4-10", "11+"]

FEATURES = {
    "pushed": "pushed code",
    "opened_pr": "opened a pull request",
    "got_a_reply": "got a reply from someone",
    "commented": "commented",
    "opened_issue": "opened an issue",
    "forked": "forked a repository",
    "starred": "starred a repository",
    "touched_someone_elses": "touched someone else's repository",
}


def load(con):
    con.execute(f"""
        CREATE OR REPLACE VIEW newcomers AS
        SELECT *,
               (opened_pr OR opened_issue OR commented) AS posted_something,
               CASE WHEN events = 1 THEN '1'
                    WHEN events <= 3 THEN '2-3'
                    WHEN events <= 10 THEN '4-10'
                    ELSE '11+' END AS band
        FROM read_parquet('{NEWCOMERS}')
    """)


def raw_and_matched(con) -> pd.DataFrame:
    weights = con.sql(
        "SELECT band, count(*) AS n FROM newcomers GROUP BY 1"
    ).df().set_index("band").n.reindex(BANDS)
    weights = weights / weights.sum()

    rows = []
    for column, label in FEATURES.items():
        d = con.sql(f"""
            SELECT band, {column} AS did_it, count(*) AS n,
                   100.0 * avg(came_back::INT) AS pct
            FROM newcomers GROUP BY 1, 2
        """).df()
        pct = d.pivot(index="band", columns="did_it", values="pct").reindex(BANDS)
        n = d.pivot(index="band", columns="did_it", values="n").reindex(BANDS)
        share = n[True].sum() / (n[True].sum() + n[False].sum())
        raw_yes = (pct[True] * n[True]).sum() / n[True].sum()
        raw_no = (pct[False] * n[False]).sum() / n[False].sum()
        rows.append({
            "on day one they…": label,
            "share of newcomers": round(100 * share, 1),
            "raw gap": round(raw_yes - raw_no, 1),
            "same-volume gap": round(((pct[True] - pct[False]) * weights).sum(), 1),
        })
    return pd.DataFrame(rows).sort_values("same-volume gap", ascending=False)


def reply_effect(con) -> tuple[pd.DataFrame, float, float]:
    """The reply comparison, restricted to newcomers who posted something.

    Only an account that opened an issue or a pull request, or commented, can
    be replied to. Comparing it against everyone else would mostly compare
    people who posted with people who did not.
    """
    d = con.sql("""
        SELECT band, got_a_reply, count(*) AS accounts,
               round(100.0 * avg(came_back::INT), 1) AS came_back_pct
        FROM newcomers WHERE posted_something GROUP BY 1, 2
    """).df()
    pct = d.pivot(index="band", columns="got_a_reply", values="came_back_pct")
    n = d.pivot(index="band", columns="got_a_reply", values="accounts")
    table = pd.DataFrame({
        "no reply %": pct[False], "got a reply %": pct[True],
        "gap, pts": (pct[True] - pct[False]).round(1),
        "n no reply": n[False].astype(int), "n got a reply": n[True].astype(int),
    }).reindex(BANDS)

    totals = con.sql("""
        SELECT got_a_reply, sum(came_back::INT) AS back, count(*) AS n
        FROM newcomers WHERE posted_something GROUP BY 1
    """).df().set_index("got_a_reply")
    a, b = totals.loc[True], totals.loc[False]
    odds, p = stats.fisher_exact([[int(a.back), int(a.n - a.back)],
                                  [int(b.back), int(b.n - b.back)]])
    return table, odds, p


def main() -> None:
    con = connect()
    load(con)

    base = con.sql("""
        SELECT count(*) AS newcomers, round(100.0*avg(came_back::INT),1) AS came_back_pct
        FROM newcomers
    """).df().iloc[0]
    print(f"{int(base.newcomers):,} newcomers, {base.came_back_pct}% come back\n")

    print("=== what separates them, before and after matching on day-one volume ===")
    print(raw_and_matched(con).to_string(index=False))

    print("\n=== day-one volume on its own ===")
    print(con.sql("""
        SELECT band AS day_one_events, count(*) AS accounts,
               round(100.0*avg(came_back::INT),1) AS came_back_pct
        FROM newcomers GROUP BY 1 ORDER BY min(events)
    """).df().to_string(index=False))

    print("\n=== the reply effect, among newcomers who posted something ===")
    table, odds, p = reply_effect(con)
    print(table.to_string())
    print(f"\noverall odds ratio {odds:.2f}, Fisher exact p = {p:.1e}")

    print("\n=== how many newcomers even get the chance ===")
    print(con.sql("""
        SELECT posted_something, count(*) AS accounts,
               round(100.0*avg(got_a_reply::INT),1) AS got_a_reply_pct
        FROM newcomers GROUP BY 1 ORDER BY 1
    """).df().to_string(index=False))


if __name__ == "__main__":
    main()
