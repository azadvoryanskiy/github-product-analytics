"""One chart style for the repo, in a light and a dark theme.

The two themes are separate selections from the same colour ramps, not one
flipped into the other: each was validated against the surface it actually
renders on. Light is for the notebook and the markdown write-ups, dark for the
published page, which sits on the portfolio's dark background.

Worst adjacent pair under colour-vision simulation is ΔE 9.1 light and 8.4 dark,
both clear of the separation floor. On the light surface, aqua and yellow fall
below 3:1 against the background, so anything drawn in them carries a written
value rather than relying on the colour alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt

IMG_DIR = Path(__file__).resolve().parent.parent / "docs" / "img"


@dataclass(frozen=True)
class Theme:
    name: str
    surface: str
    ink: str
    ink_soft: str
    muted: str
    grid: str
    axis: str
    blue: str
    orange: str
    aqua: str
    yellow: str
    critical: str   # reserved for marking the break, never for a series

    @property
    def series(self) -> list[str]:
        """Categorical slots, assigned in this order and never cycled."""
        return [self.blue, self.orange, self.aqua, self.yellow]


LIGHT = Theme(
    name="light", surface="#fcfcfb", ink="#0b0b0b", ink_soft="#52514e",
    muted="#898781", grid="#e1e0d9", axis="#c3c2b7",
    blue="#2a78d6", orange="#eb6834", aqua="#1baf7a", yellow="#eda100",
    critical="#d03b3b",
)

# Surface is the portfolio site's card colour, so the figures sit on the page
# rather than on a panel of their own.
DARK = Theme(
    name="dark", surface="#141417", ink="#ffffff", ink_soft="#c3c2b7",
    muted="#898781", grid="#2c2c2a", axis="#383835",
    blue="#3987e5", orange="#d95926", aqua="#199e70", yellow="#c98500",
    critical="#e66767",
)

THEMES = {"light": LIGHT, "dark": DARK}


def use(theme: str | Theme = "light") -> Theme:
    """Apply a theme's rcParams and hand it back for the colours."""
    t = THEMES[theme] if isinstance(theme, str) else theme
    mpl.rcParams.update({
        "figure.facecolor": t.surface,
        "axes.facecolor": t.surface,
        "savefig.facecolor": t.surface,
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 11,
        "axes.titlesize": 13,
        "axes.titleweight": "semibold",
        "axes.titlecolor": t.ink,
        "axes.titlelocation": "left",
        "axes.labelcolor": t.ink_soft,
        "axes.labelsize": 10,
        "axes.edgecolor": t.axis,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": t.grid,
        "grid.linewidth": 0.8,
        "text.color": t.ink,
        "xtick.color": t.muted,
        "ytick.color": t.muted,
        "xtick.labelsize": 9.5,
        "ytick.labelsize": 9.5,
        "legend.frameon": False,
        "legend.fontsize": 10,
        "legend.labelcolor": t.ink_soft,
        "lines.linewidth": 2,
        "lines.markersize": 8,
        "figure.dpi": 110,
        "savefig.dpi": 160,
        "savefig.bbox": "tight",
    })
    return t


def finish(ax, t: Theme, title: str, note: str | None = None) -> None:
    """Title, then one line saying what is actually plotted.

    Both are placed in points above the axes rather than in axes fractions, so
    the gap between them does not change with the figure's height.
    """
    ax.set_title(title, pad=32 if note else 14)
    if note:
        ax.annotate(note, xy=(0, 1), xycoords="axes fraction",
                    xytext=(0, 8), textcoords="offset points",
                    ha="left", va="bottom", color=t.ink_soft, fontsize=10)
    ax.grid(axis="x", visible=False)


def save(fig, name: str, t: Theme) -> Path:
    """Light goes in docs/img, dark alongside it in docs/img/dark."""
    out_dir = IMG_DIR if t.name == "light" else IMG_DIR / t.name
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.png"
    fig.savefig(path)
    return path
