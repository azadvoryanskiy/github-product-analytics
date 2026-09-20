"""The four figures of the data-quality case study.

They live here rather than inside the notebook so the same code produces the
light versions the notebook and markdown use and the dark versions the
published page uses. One definition, two themes.

    python src/figures.py          # renders both themes into docs/img
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))

import charts  # noqa: E402
from bots import ACCOUNT_DAYS, KIND, PROCESSED  # noqa: E402
from data import WINDOW_END, WINDOW_START, connect, events  # noqa: E402

CAP_DAY = pd.Timestamp("2025-05-24")

KINDS = ["person", "declared bot", "round the clock", "one target, one action"]
KIND_LABELS = ["People", "Declared bots\n(login ends in [bot])",
               "Round the clock\n(20+ hours a day)",
               "One target, one action\n(one type, 1-2 repos)"]


def daily_events(daily: pd.DataFrame, t: charts.Theme):
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(daily.day, daily.events / 1e6, color=t.blue)
    ax.axvline(CAP_DAY, color=t.critical, lw=1.5, ls="--")
    ax.annotate("24 May 2025", xy=(CAP_DAY, 5.9), xytext=(6, 0),
                textcoords="offset points", color=t.critical, fontsize=10, va="top")
    ax.set_ylabel("events per day, millions")
    ax.set_ylim(0, 6.5)
    charts.finish(ax, t, "Published activity fell 34% overnight and stayed down",
                  "Events per day. The fall lands between Friday 23 and "
                  "Saturday 24 May 2025.")
    return fig


def hourly_ceiling(hourly: pd.DataFrame, t: charts.Theme):
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(hourly.hour, hourly.before / 1000, color=t.blue, label="12–23 May")
    ax.plot(hourly.hour, hourly.after / 1000, color=t.orange, label="26 May – 6 June")
    ax.set_xlabel("hour of day, UTC")
    ax.set_ylabel("events per hour, thousands")
    ax.set_ylim(0, 300)
    ax.set_xticks(range(0, 24, 3))
    ax.legend(loc="lower right")
    charts.finish(ax, t, "Every hour was clipped, the busiest hours hardest",
                  "Average events per hour, two weekday-matched fortnights "
                  "either side of 24 May.")
    return fig


def composition(mix: pd.DataFrame, t: charts.Theme):
    vals = [float(mix.loc[mix.kind == k, "pct"].iloc[0]) for k in KINDS]
    fig, ax = plt.subplots(figsize=(9, 3.8))
    ax.barh(range(len(KINDS)), vals, height=0.62, color=t.series)
    for i, value in enumerate(vals):
        # Aqua and yellow fall below 3:1 on the light surface, so the value is
        # written out rather than left to colour and bar length alone.
        ax.text(value + 1.2, i, f"{value}%", va="center", ha="left",
                color=t.ink, fontsize=11, fontweight="semibold")
    ax.set_yticks(range(len(KINDS)))
    ax.set_yticklabels(KIND_LABELS, fontsize=9.5, color=t.ink_soft)
    ax.invert_yaxis()
    ax.set_xlim(0, 72)
    ax.set_xlabel("share of all events, %")
    charts.finish(ax, t, "37.5% of events are automation, not people",
                  "Filtering on logins that end in [bot] catches 25.3 of "
                  "those 37.5 points.")
    return fig


def deletion_rates(summary: pd.DataFrame, t: charts.Theme):
    s = summary.loc[KINDS]
    fig, ax = plt.subplots(figsize=(9, 3.6))
    y = range(len(KINDS))
    ax.errorbar(s.gone_pct, y, xerr=[s.gone_pct - s.lo, s.hi - s.gone_pct],
                fmt="o", color=t.blue, ecolor=t.axis, elinewidth=2, capsize=0)
    for i, (rate, hi) in enumerate(zip(s.gone_pct, s.hi)):
        ax.text(hi + 1.0, i, f"{rate}%", va="center", ha="left",
                color=t.ink, fontsize=10.5)
    ax.set_yticks(list(y))
    ax.set_yticklabels([lbl.split("\n")[0] for lbl in KIND_LABELS], color=t.ink_soft)
    ax.invert_yaxis()
    ax.set_xlabel("accounts no longer on GitHub, % (95% confidence interval)")
    ax.set_xlim(0, 40)
    charts.finish(ax, t, "GitHub removes the flagged accounts far more often",
                  "Share of 150 sampled accounts per rule that no longer "
                  "exist, with 95% intervals.")
    return fig


# --- the numbers each figure needs -------------------------------------------

def load(con) -> dict[str, pd.DataFrame]:
    events(con, "events_2025-*.parquet", view="ev",
           window=(WINDOW_START, WINDOW_END))
    con.execute(f"""
        CREATE OR REPLACE VIEW accounts AS
        SELECT *, {KIND} AS kind FROM read_parquet('{ACCOUNT_DAYS}/*.parquet')
    """)

    daily = con.sql("""
        SELECT day, sum(events) AS events FROM accounts GROUP BY 1 ORDER BY 1
    """).df()
    daily["day"] = pd.to_datetime(daily["day"])

    hourly = con.sql("""
        WITH h AS (SELECT created_at::DATE AS d, hour(created_at) AS hour,
                          count(*) AS n FROM ev GROUP BY 1, 2)
        SELECT hour,
          avg(CASE WHEN d BETWEEN DATE '2025-05-12' AND DATE '2025-05-23' THEN n END) AS before,
          avg(CASE WHEN d BETWEEN DATE '2025-05-26' AND DATE '2025-06-06' THEN n END) AS after
        FROM h GROUP BY hour ORDER BY hour
    """).df()

    mix = con.sql("""
        SELECT kind, sum(events) AS events,
               round(100.0 * sum(events) / sum(sum(events)) OVER (), 1) AS pct
        FROM accounts GROUP BY 1 ORDER BY events DESC
    """).df()

    val = pd.read_parquet(PROCESSED / "validation.parquet")
    summary = val.groupby("kind").agg(
        sampled=("actor_id", "size"),
        gone=("exists", lambda s: int((s == False).sum())),  # noqa: E712
    )
    summary["gone_pct"] = (100 * summary.gone / summary.sampled).round(1)
    ci = summary.apply(
        lambda r: stats.binomtest(int(r.gone), int(r.sampled)).proportion_ci(
            method="wilson"), axis=1)
    summary["lo"] = [100 * c.low for c in ci]
    summary["hi"] = [100 * c.high for c in ci]

    return {"daily": daily, "hourly": hourly, "mix": mix, "summary": summary}


FIGURES = {
    "01_daily_events": (daily_events, "daily"),
    "02_hourly_ceiling": (hourly_ceiling, "hourly"),
    "03_composition": (composition, "mix"),
    "04_deletion_rates": (deletion_rates, "summary"),
}


def main() -> None:
    con = connect()
    frames = load(con)
    for theme_name in ("light", "dark"):
        t = charts.use(theme_name)
        for name, (builder, frame) in FIGURES.items():
            fig = builder(frames[frame], t)
            print(charts.save(fig, name, t))
            plt.close(fig)


if __name__ == "__main__":
    main()
