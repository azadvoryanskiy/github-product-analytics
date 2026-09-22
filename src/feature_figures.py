"""Static figures for the feature-usage write-up.

The dashboard is the deliverable; these two exist because a markdown file and a
link preview cannot hold an interactive page.

    python src/feature_figures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import charts  # noqa: E402
from cube import OUT as CUBE  # noqa: E402


def load() -> dict:
    c = json.loads(Path(CUBE).read_text())
    ret = pd.DataFrame(c["retention"])
    rows = []
    for feature, g in ret[ret.horizon == 90].groupby("feature"):
        raw = g.users_kept.sum() / g.users.sum() - g.others_kept.sum() / g.others.sum()
        per = g.groupby("band").agg(u=("users", "sum"), uk=("users_kept", "sum"),
                                    o=("others", "sum"), ok=("others_kept", "sum"))
        per = per[(per.u > 0) & (per.o > 0)]
        w = per.u + per.o
        matched = ((w * (per.uk / per.u)).sum() - (w * (per.ok / per.o)).sum()) / w.sum()
        rows.append({"feature": feature, "raw": 100 * raw, "matched": 100 * matched,
                     "users": int(g.users.sum())})
    cur = pd.DataFrame(c["curves"])
    cur = (cur[cur.horizon == 90].groupby("n_features")
           .agg(n=("accounts", "sum"), kept=("kept", "sum")))
    cur["rate"] = 100 * cur.kept / cur.n
    return {"gaps": pd.DataFrame(rows).sort_values("matched"), "curve": cur}


def collapse(gaps: pd.DataFrame, t: charts.Theme):
    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    ax.axvline(0, color=t.axis, lw=1)
    y = range(len(gaps))
    for i, row in enumerate(gaps.itertuples()):
        ax.plot([row.raw, row.matched], [i, i], color=t.axis, lw=2, zorder=1)
    ax.scatter(gaps.raw, y, color=t.orange, zorder=2, label="raw comparison")
    ax.scatter(gaps.matched, y, color=t.blue, zorder=3,
               label="at equal activity")
    for i, row in enumerate(gaps.itertuples()):
        edge = max(row.raw, row.matched) if row.matched >= 0 else min(row.raw, row.matched)
        ax.text(edge + (1.2 if row.matched >= 0 else -1.2), i, f"{row.matched:+.1f}",
                va="center", ha="left" if row.matched >= 0 else "right",
                color=t.ink, fontsize=10)
    ax.set_yticks(list(y))
    ax.set_yticklabels(gaps.feature, color=t.ink_soft, fontsize=10)
    ax.set_xlim(-12, 46)
    ax.set_xlabel("difference in 90-day retention, percentage points")
    ax.legend(loc="lower right")
    charts.finish(ax, t, "Hold activity constant and most of it disappears",
                  "Pushing code — what 62% of accounts do — ends up worth less "
                  "than nothing.")
    return fig


def breadth(curve: pd.DataFrame, t: charts.Theme):
    labels = [f"{i} feature" + ("" if i == 1 else "s") for i in curve.index[:-1]] + \
             [f"{curve.index[-1]}+ features"]
    fig, ax = plt.subplots(figsize=(8.5, 3.8))
    ax.bar(range(len(curve)), curve.rate, width=0.6, color=t.blue)
    for i, v in enumerate(curve.rate):
        ax.text(i, v + 1.6, f"{v:.1f}%", ha="center", color=t.ink,
                fontsize=11, fontweight="semibold")
    ax.set_xticks(range(len(curve)))
    ax.set_xticklabels(labels, color=t.ink_soft)
    ax.set_ylabel("still active after 90 days, %")
    ax.set_ylim(0, 78)
    charts.finish(ax, t, "Breadth is the relationship that survives",
                  "Retention by how many different features the account used "
                  "in the baseline month.")
    return fig


def main() -> None:
    frames = load()
    for theme_name in ("light", "dark"):
        t = charts.use(theme_name)
        for name, builder, key in (("09_matched_collapse", collapse, "gaps"),
                                   ("10_breadth", breadth, "curve")):
            fig = builder(frames[key], t)
            print(charts.save(fig, name, t))
            plt.close(fig)


if __name__ == "__main__":
    main()
