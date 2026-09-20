"""One chart style for the whole repo, so the notebooks stay about the analysis.

Colours come from a palette validated for colour-vision deficiency: the worst
adjacent pair is well clear of the separation floor. Two of the four sit below
3:1 against the surface, so anything drawn in aqua or yellow carries a visible
label rather than relying on the colour alone.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt

# Absolute, so a notebook saves to the same place wherever it is run from.
IMG_DIR = Path(__file__).resolve().parent.parent / "docs" / "img"

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SOFT = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

# Categorical slots, assigned in this order and never cycled.
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
SERIES = [BLUE, ORANGE, AQUA, YELLOW]
CRITICAL = "#d03b3b"  # reserved for marking the break, never for a series


def use_style() -> None:
    mpl.rcParams.update({
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 11,
        "axes.titlesize": 13,
        "axes.titleweight": "semibold",
        "axes.titlecolor": INK,
        "axes.titlelocation": "left",
        "axes.titlepad": 14,
        "axes.labelcolor": INK_SOFT,
        "axes.labelsize": 10,
        "axes.edgecolor": AXIS,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.labelsize": 9.5,
        "ytick.labelsize": 9.5,
        "legend.frameon": False,
        "legend.fontsize": 10,
        "lines.linewidth": 2,
        "lines.markersize": 8,
        "figure.dpi": 110,
        "savefig.dpi": 160,
        "savefig.bbox": "tight",
    })


def finish(ax, title: str, note: str | None = None) -> None:
    """Title, then one line of plain-language takeaway under it.

    Both are positioned in points above the axes rather than in axes fractions,
    so the gap between them does not change with the figure's height.
    """
    ax.set_title(title, pad=32 if note else 14)
    if note:
        ax.annotate(note, xy=(0, 1), xycoords="axes fraction",
                    xytext=(0, 8), textcoords="offset points",
                    ha="left", va="bottom", color=INK_SOFT, fontsize=10)
    ax.grid(axis="x", visible=False)


def save(fig, name: str) -> None:
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(IMG_DIR / f"{name}.png")
    plt.close(fig)
