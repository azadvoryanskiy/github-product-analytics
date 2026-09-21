"""The four figures of the activation case study.

Same arrangement as the data-quality ones: the drawing lives here so a single
definition renders the light versions for the notebook and the dark versions
for the published page.

    python src/activation_figures.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import charts  # noqa: E402
import drivers as drv  # noqa: E402
from bots import PROCESSED  # noqa: E402
from data import connect  # noqa: E402

AGE_BANDS = [(-1, 0, "made that day"), (0, 7, "1–7 days old"),
             (7, 30, "8–30 days"), (30, 90, "1–3 months"),
             (90, 365, "3–12 months"), (365, 730, "1–2 years"),
             (730, 10 ** 6, "over 2 years")]


def account_ages(sample: pd.DataFrame, t: charts.Theme):
    labels = [b[2] for b in AGE_BANDS]
    counts = [((sample.age_days > lo) & (sample.age_days <= hi)).sum()
              for lo, hi, _ in AGE_BANDS]
    pct = [100 * c / len(sample) for c in counts]

    fig, ax = plt.subplots(figsize=(9, 3.8))
    # One measure across ordered bands: one hue, with the band that breaks the
    # naive definition picked out rather than given a colour of its own.
    colours = [t.blue] * len(labels)
    colours[-1] = t.orange
    ax.barh(range(len(labels)), pct, height=0.62, color=colours)
    for i, (value, n) in enumerate(zip(pct, counts)):
        ax.text(value + 1.2, i, f"{value:.1f}%  ({n})", va="center", ha="left",
                color=t.ink, fontsize=10.5)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, color=t.ink_soft)
    ax.invert_yaxis()
    ax.set_xlim(0, 78)
    ax.set_xlabel("share of the sample, %")
    charts.finish(ax, t, "\"First seen in the data\" is not a new account",
                  f"{len(sample)} accounts first seen in one week, asked the API "
                  "when they actually registered.")
    return fig


def funnel(weekly: pd.DataFrame, t: charts.Theme):
    stages = ["Account ids issued", "Did anything public\nwithin 28 days",
              "Came back on\na second day"]
    values = [weekly.ids_in_week.mean(), weekly.acted.mean(),
              weekly.came_back.mean()]

    fig, ax = plt.subplots(figsize=(9, 3.8))
    ax.barh(range(3), values, height=0.6, color=t.blue)
    for i, value in enumerate(values):
        ax.text(value * 1.08, i - 0.1, f"{value:,.0f}", va="bottom", ha="left",
                color=t.ink, fontsize=12, fontweight="semibold")
        if i:
            ax.text(value * 1.08, i + 0.06,
                    f"{100 * value / values[i - 1]:.0f}% of the step above",
                    va="top", ha="left", color=t.ink_soft, fontsize=9.5)
    ax.set_yticks(range(3))
    ax.set_yticklabels(stages, color=t.ink_soft, fontsize=9.5)
    ax.invert_yaxis()
    ax.set_xscale("log")
    ax.set_xlim(2 * 10 ** 4, 4 * 10 ** 6)
    ax.set_xlabel("accounts per signup week (log scale)")
    charts.finish(ax, t, "Two thirds of the people who start never come back",
                  "Average of nine weekly signup cohorts, June–July 2025.")
    return fig


def driver_gaps(gaps: pd.DataFrame, t: charts.Theme):
    d = gaps.sort_values("same-volume gap")
    y = range(len(d))
    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    ax.axvline(0, color=t.axis, lw=1)
    for i, row in enumerate(d.itertuples()):
        raw, matched = getattr(row, "_3"), getattr(row, "_4")
        ax.plot([raw, matched], [i, i], color=t.axis, lw=2, zorder=1)
    ax.scatter(d["raw gap"], y, color=t.orange, zorder=2, label="raw")
    ax.scatter(d["same-volume gap"], y, color=t.blue, zorder=3,
               label="compared at the same day-one volume")
    for i, row in enumerate(d.itertuples()):
        raw, matched = getattr(row, "_3"), getattr(row, "_4")
        if matched >= 0:
            ax.text(max(raw, matched) + 0.8, i, f"{matched:+.1f}", va="center",
                    ha="left", color=t.ink, fontsize=10)
        else:
            ax.text(min(raw, matched) - 0.8, i, f"{matched:+.1f}", va="center",
                    ha="right", color=t.ink, fontsize=10)
    ax.set_yticks(list(y))
    ax.set_yticklabels(d["on day one they…"], color=t.ink_soft, fontsize=10)
    ax.set_xlim(-16, 20)
    ax.set_xlabel("difference in the share who come back, percentage points")
    ax.legend(loc="lower right")
    charts.finish(ax, t, "Making something brings people back; looking around does not",
                  "Every gap shrinks once eagerness is held constant — a third of "
                  "it was never the action.")
    return fig


def reply_effect(table: pd.DataFrame, t: charts.Theme):
    bands = table.index.tolist()
    x = range(len(bands))
    width = 0.38
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.bar([i - width / 2 for i in x], table["no reply %"], width,
           color=t.orange, edgecolor=t.surface, linewidth=2, label="nobody replied")
    ax.bar([i + width / 2 for i in x], table["got a reply %"], width,
           color=t.blue, edgecolor=t.surface, linewidth=2, label="someone replied")
    for i, (lo, hi) in enumerate(zip(table["no reply %"], table["got a reply %"])):
        ax.text(i - width / 2, lo + 1.5, f"{lo:.0f}%", ha="center",
                color=t.ink, fontsize=10)
        ax.text(i + width / 2, hi + 1.5, f"{hi:.0f}%", ha="center",
                color=t.ink, fontsize=10)
    ax.set_xticks(list(x))
    ax.set_xticklabels([f"{b} event{'s' if b != '1' else ''}" for b in bands],
                       color=t.ink_soft)
    ax.set_xlabel("how much they did on their first day")
    ax.set_ylabel("came back on a second day, %")
    ax.set_ylim(0, 75)
    ax.legend(loc="upper left")
    charts.finish(ax, t, "A reply is worth about ten points, whoever you are",
                  "Only newcomers who posted something a person could reply to. "
                  "The gap holds in every band.")
    return fig


def load():
    con = connect()
    drv.load(con)
    sample = pd.read_parquet(PROCESSED / "cohort_calibration.parquet").dropna(
        subset=["created_at"]).copy()
    sample["created_at"] = pd.to_datetime(sample["created_at"])
    sample["first_seen"] = pd.to_datetime(sample["first_seen"]).dt.tz_localize(None)
    sample["age_days"] = (sample.first_seen - sample.created_at).dt.days
    table, _, _ = drv.reply_effect(con)
    return {
        "sample": sample,
        "weekly": pd.read_parquet(PROCESSED / "activation.parquet"),
        "gaps": drv.raw_and_matched(con),
        "reply": table,
    }


FIGURES = {
    "05_account_ages": (account_ages, "sample"),
    "06_funnel": (funnel, "weekly"),
    "07_driver_gaps": (driver_gaps, "gaps"),
    "08_reply_effect": (reply_effect, "reply"),
}


def main() -> None:
    frames = load()
    for theme_name in ("light", "dark"):
        t = charts.use(theme_name)
        for name, (builder, key) in FIGURES.items():
            fig = builder(frames[key], t)
            print(charts.save(fig, name, t))
            plt.close(fig)


if __name__ == "__main__":
    main()
