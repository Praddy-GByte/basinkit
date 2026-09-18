"""Draw the verification figures from the shipped benchmark tables.

Four figures, each the picture of a claim the verification page makes in prose:

1. Area error against catchment size -- the finding the whole page rests on.
2. The twelve-metre backend by size band -- the mechanism, not only the gain.
3. The suitability grade against an independent elevation model, beside the
   same comparison under the measure that inverts it.
4. Four D8 implementations on one set of rasters.

Every figure is written twice, once for a light page and once for a dark one,
because a figure with a baked light background is unreadable under a dark theme
and the site has a theme toggle. Material picks between them by the ``#only-light``
and ``#only-dark`` suffixes on the image link.

    python verify/make_figures.py

Reads only from ``verify/benchmarks/`` and writes to ``docs/assets/figures/``,
so the charts on the page can be rebuilt from what the repository ships.

Figure 1 is drawn from ``accuracy_by_size.csv``, which holds the blind
validation result exactly as the page reports it, rather than from the raw
per-gauge run. The raw run is 2,740 delineations and is not shipped: it is
built on GSIM station records, and redistributing the identified set would be
redistributing that dataset. Drawing the figure from the same numbers the table
prints is also the only way to guarantee the chart and the table agree.
"""

from __future__ import annotations

import csv
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
DATA = HERE / "benchmarks"
OUT = HERE.parent / "docs" / "assets" / "figures"

#: The two modes are selected, not flipped: each is its own set of steps,
#: checked against the surface it actually renders on.
THEMES = {
    "light": {
        "surface": "#fcfcfb", "ink": "#0b0b0b", "ink2": "#52514e",
        "muted": "#898781", "grid": "#e1e0d9", "axis": "#c3c2b7",
        "series1": "#2a78d6", "series2": "#eb6834",
        "good": "#0ca30c", "warning": "#fab219", "critical": "#d03b3b",
    },
    "dark": {
        "surface": "#1a1a19", "ink": "#ffffff", "ink2": "#c3c2b7",
        "muted": "#898781", "grid": "#2c2c2a", "axis": "#383835",
        "series1": "#3987e5", "series2": "#d95926",
        "good": "#0ca30c", "warning": "#fab219", "critical": "#d03b3b",
    },
}


def _rows(name):
    with open(DATA / name, newline="", encoding="utf-8") as handle:
        lines = [line for line in handle if not line.startswith("#")]
    return list(csv.DictReader(lines))


def _header(figure, theme, title, subtitle, *, top=0.88):
    """Title and subtitle as figure furniture, with the axes told to keep clear.

    Drawn on the figure rather than the axes because an axes title and a line
    of text above it collide as soon as either wraps.
    """
    figure.suptitle(title, color=theme["ink"], fontsize=12.5, fontweight="bold",
                    x=0.012, ha="left", y=0.985)
    figure.text(0.012, 0.92, subtitle, color=theme["ink2"], fontsize=8.6,
                ha="left", va="top")
    return top


def _frame(axes, theme, *, grid_axis="y"):
    """Recessive chrome: the data carries the figure, not the furniture."""
    axes.set_facecolor(theme["surface"])
    for side in ("top", "right"):
        axes.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axes.spines[side].set_color(theme["axis"])
        axes.spines[side].set_linewidth(0.8)
    axes.tick_params(colors=theme["muted"], labelsize=8, length=3, width=0.8)
    for label in axes.get_xticklabels() + axes.get_yticklabels():
        label.set_color(theme["ink2"])
    if grid_axis:
        axes.grid(axis=grid_axis, color=theme["grid"], linewidth=0.7, zorder=0)
        axes.set_axisbelow(True)


def _boxes(axes, groups, theme, colours, *, width=0.55):
    """A box per group with every point behind it, so n is shown, not claimed."""
    import numpy as np

    rng = np.random.default_rng(11)
    positions = list(range(1, len(groups) + 1))
    drawn = axes.boxplot(
        groups, positions=positions, widths=width, patch_artist=True,
        showfliers=False, medianprops={"color": theme["surface"], "linewidth": 2.0},
        whiskerprops={"color": theme["axis"], "linewidth": 1.0},
        capprops={"color": theme["axis"], "linewidth": 1.0},
    )
    for patch, colour in zip(drawn["boxes"], colours, strict=True):
        patch.set_facecolor(colour)
        patch.set_alpha(0.85)
        patch.set_edgecolor(theme["surface"])   # the 2px surface ring
        patch.set_linewidth(2.0)
    for position, values, colour in zip(positions, groups, colours, strict=True):
        if not values:
            continue
        jitter = rng.uniform(-width / 3.2, width / 3.2, size=len(values))
        axes.scatter([position + j for j in jitter], values, s=7, color=colour,
                     alpha=0.35, linewidths=0, zorder=1)
    return drawn


# --- figure 1 ---------------------------------------------------------------


def figure_error_by_size(theme):
    rows = _rows("accuracy_by_size.csv")[::-1]        # smallest catchment first
    labels = [r["size_band"].replace(";", ",") for r in rows]
    medians = [float(r["median_error_pct"]) for r in rows]
    within = [int(r["within_20_pct"]) for r in rows]

    figure, axes = plt.subplots(figsize=(8.6, 4.4), facecolor=theme["surface"])
    top = _header(
        figure, theme,
        "Catchment area error is set by catchment size, not by implementation",
        "2,740 delineations at 2,550 gauges in 99 countries, against areas "
        "published by the agencies that operate them")

    bars = axes.bar(range(len(medians)), medians, width=0.6,
                    color=theme["series1"], zorder=3)
    axes.set_yscale("log")
    axes.axhline(20, color=theme["muted"], linewidth=1.0, linestyle=(0, (4, 3)),
                 zorder=2)
    axes.text(len(medians) - 0.42, 22, "20% of the published area",
              color=theme["muted"], fontsize=8, va="bottom", ha="right")

    for bar, median in zip(bars, medians, strict=True):
        axes.text(bar.get_x() + bar.get_width() / 2, median * 1.18,
                  f"{median:g}%", ha="center", fontsize=9.5,
                  color=theme["ink"], fontweight="bold")

    axes.set_xticks(range(len(labels)))
    axes.set_xticklabels([f"{label}\n{share}% within 20%"
                          for label, share in zip(labels, within, strict=True)],
                         fontsize=8.5)
    axes.set_ylim(0.2, 600)
    axes.set_xlabel("published catchment area, km2", color=theme["ink2"],
                    fontsize=9, labelpad=8)
    axes.set_ylabel("median area error, percent (log)", color=theme["ink2"],
                    fontsize=9)
    _frame(axes, theme)
    figure.tight_layout(rect=(0, 0, 1, top))
    return figure


# --- figure 2 ---------------------------------------------------------------

TDX_BANDS = [(100, 200, "100 to 200"), (200, 350, "200 to 350"),
             (350, 500, "350 to 500")]


def figure_tdx_by_size(theme):
    rows = _rows("tdx_wide.csv")
    hb_med, tdx_med, labels = [], [], []
    for low, high, label in TDX_BANDS:
        subset = [r for r in rows if r["hb_err_pct"] and r["tdx_err_pct"]
                  and low <= float(r["reported_area_km2"]) < high]
        hb = [abs(float(r["hb_err_pct"])) for r in subset]
        tdx = [abs(float(r["tdx_err_pct"])) for r in subset]
        hb_med.append(statistics.median(hb))
        tdx_med.append(statistics.median(tdx))
        better = sum(1 for r in subset
                     if abs(float(r["tdx_err_pct"])) < abs(float(r["hb_err_pct"])))
        labels.append(f"{label}\nn = {len(subset)}\n"
                      f"tdx better on {round(100 * better / len(subset))}%")

    figure, axes = plt.subplots(figsize=(8.0, 4.4), facecolor=theme["surface"])
    top = _header(
        figure, theme,
        "The twelve-metre backend pays where the units are too coarse",
        "360 gauges between 100 and 500 km2, eight GEOGLOWS regions on four "
        "continents, drawn by seed before any result was seen")

    positions = range(len(TDX_BANDS))
    width, gap = 0.30, 0.012                        # the 2px surface gap
    left = axes.bar([p - width / 2 - gap for p in positions], hb_med, width,
                    color=theme["series1"], label="hydrobasins (default)", zorder=3)
    right = axes.bar([p + width / 2 + gap for p in positions], tdx_med, width,
                     color=theme["series2"], label="tdx (12 m)", zorder=3)
    for bars in (left, right):
        for bar in bars:
            axes.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.1,
                      f"{bar.get_height():.1f}%", ha="center", fontsize=9,
                      color=theme["ink"], fontweight="bold")

    axes.set_xticks(list(positions))
    axes.set_xticklabels(labels, fontsize=8.5)
    axes.set_ylim(0, max(hb_med) * 1.24)
    axes.set_xlabel("published catchment area, km2", color=theme["ink2"],
                    fontsize=9, labelpad=8)
    axes.set_ylabel("median area error, percent", color=theme["ink2"], fontsize=9)
    legend = axes.legend(frameon=False, fontsize=9, loc="upper right")
    for text in legend.get_texts():
        text.set_color(theme["ink2"])
    _frame(axes, theme)
    figure.tight_layout(rect=(0, 0, 1, top))
    return figure


# --- figure 3 ---------------------------------------------------------------

GRADES = ["HIGH", "MODERATE", "LIMITED"]


def figure_grade(theme):
    rows = [r for r in _rows("grade_validation.csv")
            if r.get("grade") and r.get("slope_pearson_r")]
    colours = [theme["good"], theme["warning"], theme["critical"]]
    corr = [[float(r["slope_pearson_r"]) for r in rows if r["grade"] == g]
            for g in GRADES]
    degrees = [[float(r["slope_median_abs_diff_deg"]) for r in rows
                if r["grade"] == g] for g in GRADES]

    figure, (left, right) = plt.subplots(
        1, 2, figsize=(9.2, 5.0), facecolor=theme["surface"])
    top = _header(
        figure, theme,
        "The grade holds against an elevation model it was not fitted to",
        "133 gauges: the grade from Copernicus GLO-30, the slope field compared\n"
        "against NASADEM. Flat ground has less gradient to disagree about, so\n"
        "degrees cannot tell \"the models agree\" from \"neither can see anything\".",
        top=0.855)

    for axes, groups, ylabel, title, note in (
        (left, corr, "agreement between the two models (Pearson r)",
         "What the grade predicts", "z = -4.84,  p = 1.3e-06"),
        (right, degrees, "slope disagreement, degrees",
         "The measure that would have inverted it",
         "the same basins, ordered the other way"),
    ):
        _boxes(axes, groups, theme, colours)
        axes.set_xticks(range(1, len(GRADES) + 1))
        axes.set_xticklabels([f"{g}\nn = {len(v)}"
                              for g, v in zip(GRADES, groups, strict=True)],
                             fontsize=8.5)
        axes.set_ylabel(ylabel, color=theme["ink2"], fontsize=9)
        axes.set_title(title, color=theme["ink"], fontsize=10.5,
                       fontweight="bold", loc="left", pad=8)
        for i, values in enumerate(groups, start=1):
            axes.text(i + 0.34, statistics.median(values),
                      f"{statistics.median(values):.2f}", fontsize=9,
                      color=theme["ink"], fontweight="bold", va="center")
        axes.text(0.5, -0.30, note, transform=axes.transAxes, fontsize=8.6,
                  color=theme["ink2"], ha="center")
        _frame(axes, theme)

    figure.tight_layout(rect=(0.01, 0.07, 1, top), w_pad=3.0)
    return figure


# --- figure 4 ---------------------------------------------------------------

METHODS = [
    ("basinkit40_err", "basinkit on the DEM"),
    ("whitebox40_err", "WhiteboxTools 2.4.0"),
    ("pysheds40_err", "pysheds"),
    ("hb_err", "HydroBASINS (the default)"),
]


def figure_implementations(theme):
    rows = _rows("implementations.csv")
    total = len(rows)
    medians, labels, answered = [], [], []
    for column, label in METHODS:
        values = [abs(float(r[column])) for r in rows
                  if r.get(column) not in (None, "", "None")]
        medians.append(statistics.median(values))
        answered.append(round(100 * len(values) / total))
        labels.append(label)

    figure, axes = plt.subplots(figsize=(8.0, 3.6), facecolor=theme["surface"])
    top = _header(
        figure, theme, "Four D8 implementations on one set of rasters",
        f"{total} catchments under 2,000 km2, identical Copernicus windows and "
        "identical snapping", top=0.84)

    order = list(range(len(medians)))[::-1]
    bars = axes.barh(order, medians, height=0.5, color=theme["series1"], zorder=3)
    for bar, median, share in zip(bars, medians, answered, strict=True):
        text = f"{median:.1f}%"
        if share != 100:
            text += f"   ({share}% of them answered at all)"
        axes.text(bar.get_width() + 0.8, bar.get_y() + bar.get_height() / 2,
                  text, va="center", fontsize=9, color=theme["ink"],
                  fontweight="bold")

    axes.set_yticks(order)
    axes.set_yticklabels(labels, fontsize=9)
    axes.set_xlim(0, max(medians) * 1.45)
    axes.set_xlabel("median area error, percent", color=theme["ink2"], fontsize=9)
    _frame(axes, theme, grid_axis="x")
    figure.tight_layout(rect=(0, 0, 1, top))
    return figure


FIGURES = {
    "error-by-catchment-size": figure_error_by_size,
    "tdx-by-catchment-size": figure_tdx_by_size,
    "grade-validation": figure_grade,
    "implementations": figure_implementations,
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, maker in FIGURES.items():
        for mode, theme in THEMES.items():
            figure = maker(theme)
            stem = OUT / f"{name}-{mode}"
            figure.savefig(f"{stem}.svg", facecolor=theme["surface"],
                           bbox_inches="tight")
            figure.savefig(f"{stem}.png", dpi=200, facecolor=theme["surface"],
                           bbox_inches="tight")
            plt.close(figure)
            print(f"wrote {stem.name}.svg and .png")


if __name__ == "__main__":
    main()
