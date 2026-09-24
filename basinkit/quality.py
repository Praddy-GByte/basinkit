"""A quality indicator for every layer, not only for the elevation model.

:func:`~basinkit.suitability.suitability` grades the elevation raster, because
every terrain product is derived from it. The other layers arrive with no such
statement: a land cover map, a soil raster and a rainfall series all come back
looking equally authoritative, and nothing in the output says which of them can
carry the weight a study puts on it.

This module measures each layer against something independent of it and reports
what it found:

``elevation``
    The suitability grade, and the same measurement split by terrain class, so
    that a basin which is part plain and part mountain is not reported as one
    number. The classes are cut on local relief, which is the quantity the
    model's vertical error competes with. Both the relief and the noise floor
    are per-cell quantities, so the split is reported together with the cell
    size it was measured at.

``landcover``
    Two independently produced maps of the same year -- ESA WorldCover and the
    ESRI annual series -- reduced to the classes they both define, and the
    share of the basin where they agree. Where two mapping teams disagree, the
    class under a given pixel is not settled.

``soil``
    SoilGrids publishes a 5th and a 95th percentile beside its mean. The width
    of that interval, in the units of the property, is the model's own
    statement about how well it knows this ground.

``precipitation``
    CHIRPS against TerraClimate over the same years: two products built from
    different inputs. Their correlation and the difference between their means
    bound how much of a rainfall figure is the choice of product.

``surface_water``
    How much of the water in the basin is permanent, how much seasonal, and
    how much of the basin the Landsat record never observed cleanly.

``delineation``
    The boundary is not measured here -- it comes from the backend -- so this
    reports the checks that do exist: the river-network consistency check and
    the accuracy regime for a basin of this size.

Every threshold below is a choice, stated in the output, not a measurement.
The measurements are the numbers beside them.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

#: Local relief, in metres between a cell and its eight neighbours, that
#: separates the terrain classes. Chosen so that "flat" is ground where a
#: 30 m model's vertical error is a large share of the relief present.
RELIEF_CLASSES = ((0.0, 20.0, "flat"), (20.0, 100.0, "hilly"), (100.0, np.inf, "mountain"))

#: Where each indicator stops being reported as HIGH, and where it becomes
#: LIMITED. Every pair is a judgement, and is printed with the result.
THRESHOLDS = {
    "landcover_agreement": (0.80, 0.65),      # share of cells where two maps agree
    "precipitation_r": (0.90, 0.75),          # correlation between two products
}

#: WorldCover and ESRI do not define the same legend. These are the classes
#: both of them do define, and the codes that carry them.
_COMMON = {
    "tree": ({10}, {2}),
    "grass_shrub": ({20, 30}, {11}),
    "crop": ({40}, {5}),
    "built": ({50}, {7}),
    "bare": ({60}, {8}),
    "snow_ice": ({70}, {9}),
    "water": ({80}, {1}),
    "wetland": ({90, 95}, {4}),
}


def _noise_floor_deg(error_m: float, cell_m: float) -> float:
    """The slope a model cannot resolve: its vertical error over one cell.

    The same expression :mod:`basinkit.suitability` grades against. It is
    repeated here because the terrain split may be measured on a decimated copy
    of the raster, where the cell is wider and the floor is therefore lower.
    """
    return math.degrees(math.atan(error_m / cell_m))


def _grade(value: float, good: float, bad: float, *, higher_is_better: bool) -> str:
    if higher_is_better:
        if value >= good:
            return "HIGH"
        return "MODERATE" if value >= bad else "LIMITED"
    if value <= good:
        return "HIGH"
    return "MODERATE" if value <= bad else "LIMITED"


def _worst(grades: list[str]) -> str:
    for g in ("LIMITED", "MODERATE", "HIGH"):
        if g in grades:
            return g
    return "HIGH"


#: Pixels to read for the quality pass when the caller hands over no elevation
#: model. The grade is a statement about the raster it was measured on, and the
#: cell size is reported with it, so the budget is bounded here to keep the pass
#: itself from being the heaviest thing a user runs.
QUALITY_DEM_PIXELS = 8_000_000

#: The terrain split is measured on the elevation raster itself. Both the relief
#: classes and the noise floor are quantities per cell, so decimating the raster
#: moves them: a 3x3 window over coarser cells spans more ground and reports more
#: relief, and a coarser slope is a gentler slope. The budget matches
#: :data:`QUALITY_DEM_PIXELS`, so the default path measures the split on the same
#: cells it graded. A raster handed in by the caller that is larger than this is
#: decimated to fit -- the noise floor is then recomputed for the coarser cell,
#: and the cell size the split was measured at is reported as
#: ``class_cell_size_m``.
CLASS_SAMPLE_PIXELS = 8_000_000


def elevation_quality(basin, dem=None, **kwargs) -> dict[str, Any]:
    """The suitability grade, plus the noise-floor test per terrain class."""
    from .suitability import _range_3x3, suitability
    from .terrain import _as_array
    from .terrain import slope as _slope

    if dem is None:
        kwargs.setdefault("max_pixels", QUALITY_DEM_PIXELS)
        dem = basin.dem(**kwargs)
    graded = suitability(basin, dem=dem)
    values = _as_array(dem)
    step = max(1, int(np.ceil(np.sqrt(values.size / CLASS_SAMPLE_PIXELS))))
    sampled = dem[::step, ::step] if step > 1 else dem
    relief = _range_3x3(_as_array(sampled))
    slopes = np.asarray(_slope(sampled).values, dtype="float64")
    floor = next((t for t in graded["tests"] if t["test"] == "slope"), {}).get("noise_floor_deg")
    cell_m = float(graded["cell_size_m"]) * step
    if step > 1 and graded.get("vertical_error_m"):
        # The floor is atan(vertical error / cell size): on a decimated copy the
        # cells are wider, so the angle the model cannot resolve is smaller.
        floor = round(_noise_floor_deg(float(graded["vertical_error_m"]), cell_m), 3)

    classes = []
    usable = np.isfinite(relief) & np.isfinite(slopes)
    total = int(usable.sum())
    for low, high, name in RELIEF_CLASSES:
        picked = usable & (relief >= low) & (relief < high)
        n = int(picked.sum())
        if n == 0:
            continue
        row = {"terrain": name, "share_of_basin": round(n / total, 4),
               "mean_slope_deg": round(float(np.mean(slopes[picked])), 2)}
        if floor is not None:
            row["below_noise_floor"] = round(float(np.mean(slopes[picked] < floor)), 4)
        classes.append(row)

    statement = graded["statement"]
    if floor is not None and classes:
        worst = max(classes, key=lambda c: c.get("below_noise_floor", 0.0))
        statement += (
            f" Split by terrain, {worst['share_of_basin']:.0%} of the basin is "
            f"{worst['terrain']} ground, where {worst['below_noise_floor']:.0%} of "
            f"slopes fall below the {floor:.1f} degree noise floor of a "
            f"{cell_m:.0f} m cell."
        )
    return {"layer": "elevation", "indicator": "suitability grade, by terrain class",
            "class_sample_step": step, "class_cell_size_m": round(cell_m, 2),
            "class_noise_floor_deg": floor,
            "grade": graded["grade"], "value": graded["support_fraction"],
            "terrain_classes": classes, "tests": graded["tests"],
            "statement": statement,
            "source": f"{graded['product']}, cell {graded['cell_size_m']:.0f} m"}


#: Pixels to read for the land cover comparison. Two 10 m maps of a large
#: basin will not both fit in memory, and the question here is what share of
#: the basin the maps agree on, which a coarser read answers as well.
LANDCOVER_PIXELS = 4_000_000


def landcover_quality(basin, year: int = 2021, max_pixels: int | None = None,
                      **kwargs) -> dict[str, Any]:
    """Agreement between ESA WorldCover and the ESRI annual map for one year."""
    budget = LANDCOVER_PIXELS if max_pixels is None else max_pixels
    first = basin.landcover(year=year, source="worldcover", max_pixels=budget, **kwargs)
    # The ESRI reader takes no progress flag, and reads through a different
    # path, so its budget is passed on its own terms.
    second = basin.landcover(year=year, source="esri", max_pixels=budget)
    if second.shape != first.shape:
        second = second.rio.reproject_match(first)
    a = np.asarray(first.values, dtype="float64").squeeze()
    b = np.asarray(second.values, dtype="float64").squeeze()

    common = np.zeros(a.shape, dtype="int16")
    other = np.zeros(a.shape, dtype="int16")
    for i, (wc_codes, esri_codes) in enumerate(_COMMON.values(), start=1):
        common[np.isin(a, list(wc_codes))] = i
        other[np.isin(b, list(esri_codes))] = i
    usable = (common > 0) & (other > 0)
    n = int(usable.sum())
    if n == 0:
        return {"layer": "landcover", "grade": "LIMITED", "value": None,
                "indicator": "agreement between two independent maps",
                "statement": "No cell fell in a class both maps define, so no comparison was possible.",
                "source": f"ESA WorldCover {year} against ESRI {year}"}
    agree = float(np.mean(common[usable] == other[usable]))
    per_class, counts = {}, {}
    for i, name in enumerate(_COMMON, start=1):
        picked = usable & (common == i)
        if picked.any():
            per_class[name] = round(float(np.mean(other[picked] == i)), 4)
            counts[name] = int(picked.sum())
    good, bad = THRESHOLDS["landcover_agreement"]
    # A class covering a handful of cells can disagree completely without
    # saying anything about the map, so the weakest class is only named when
    # it holds at least one per cent of the ground compared.
    substantial = {k: v for k, v in per_class.items() if counts[k] >= 0.01 * n}
    weakest = min(substantial, key=substantial.get) if substantial else None
    statement = (f"Two independently produced maps of {year} agree on "
                 f"{agree:.0%} of the basin, over the classes both of them define "
                 f"({n:,} cells).")
    if weakest is not None:
        statement += (f" Of the classes covering more than one per cent of that ground, they "
                      f"agree least on {weakest.replace('_', ' ')}, at {per_class[weakest]:.0%}.")
    return {"layer": "landcover", "indicator": "agreement between two independent maps",
            "grade": _grade(agree, good, bad, higher_is_better=True), "value": round(agree, 4),
            "per_class_agreement": per_class, "class_cells": counts, "compared_cells": n,
            "threshold": {"high_at_or_above": good, "limited_below": bad},
            "statement": statement,
            "source": f"ESA WorldCover {year} against ESRI Annual LULC {year}"}


def soil_quality(basin, prop: str = "clay", depth: str = "0-5cm", **kwargs) -> dict[str, Any]:
    """SoilGrids' own 90 per cent interval, as a share of its mean."""
    mean = basin.soil(prop, depth, stat="mean", **kwargs)
    low = basin.soil(prop, depth, stat="Q0.05", **kwargs)
    high = basin.soil(prop, depth, stat="Q0.95", **kwargs)
    m = np.asarray(mean.values, dtype="float64").squeeze()
    lo = np.asarray(low.values, dtype="float64").squeeze()
    hi = np.asarray(high.values, dtype="float64").squeeze()
    ok = np.isfinite(m) & np.isfinite(lo) & np.isfinite(hi) & (m > 0)
    if not ok.any():
        return {"layer": "soil", "grade": "LIMITED", "value": None,
                "indicator": "SoilGrids 90% interval width",
                "statement": "SoilGrids returned no usable values for this basin.",
                "source": f"SoilGrids {prop} {depth}"}
    width = float(np.median(hi[ok] - lo[ok]))
    relative = float(np.median((hi[ok] - lo[ok]) / m[ok])) * 100.0
    factor = 10.0 if prop in ("clay", "sand", "silt") else 1.0   # SoilGrids maps g/kg for these
    return {"layer": "soil", "indicator": "SoilGrids 90% interval width, relative to its mean",
            "grade": None, "not_graded_because":
                ("SoilGrids' published quantiles are wide in every basin tested, so any "
                 "pass/fail threshold here would be invented. The width is reported so that "
                 "basins, depths and properties can be compared with each other."),
            "value": round(relative, 1),
            "interval_width_percent_points": round(width / factor, 1),
            "median_mean_percent": round(float(np.median(m[ok])) / factor, 1),
            "statement": (f"At the median cell SoilGrids reports {np.median(m[ok])/factor:.0f}% {prop} "
                          f"with a 5th to 95th percentile range {width/factor:,.0f} points wide, "
                          f"{relative:.0f}% of that mean. Read the map for pattern, not for a field."),
            "source": f"SoilGrids {prop} {depth}, mean against its own Q0.05 and Q0.95"}


def precipitation_quality(basin, start: int = 2000, end: int | None = None, **kwargs) -> dict[str, Any]:
    """CHIRPS against TerraClimate: two products, the same basin and years."""
    import pandas as pd

    chirps = basin.precipitation(start=start, end=end, source="chirps", **kwargs)
    terra = basin.precipitation(start=start, end=end, source="terraclimate", **kwargs)
    def _annual(obj, column=None):
        s = obj.to_series() if hasattr(obj, "to_series") else obj
        if isinstance(s, pd.DataFrame):
            s = s[column] if column and column in s else s.iloc[:, 0]
        s = pd.Series(s)
        index = pd.to_datetime(pd.Index(s.index).get_level_values(-1))
        s = pd.Series(np.asarray(s, dtype="float64"), index=index)
        s = s[~s.index.duplicated()]
        return s.groupby(s.index.year).sum()
    a = _annual(chirps)
    b = _annual(terra.to_dataframe() if hasattr(terra, "to_dataframe") else terra, column="ppt")
    years = sorted(set(a.index) & set(b.index))
    years = [y for y in years if y != max(years)] or years   # drop a partial final year
    a, b = a.loc[years], b.loc[years]
    r = float(np.corrcoef(a.values, b.values)[0, 1])
    bias = float(a.mean() / b.mean() - 1.0) * 100.0
    good, bad = THRESHOLDS["precipitation_r"]
    return {"layer": "precipitation", "indicator": "two independent products, annual totals",
            "grade": _grade(r, good, bad, higher_is_better=True),
            "value": round(r, 3), "bias_pct": round(bias, 1), "years": len(years),
            "chirps_mm_per_year": round(float(a.mean()), 1),
            "terraclimate_mm_per_year": round(float(b.mean()), 1),
            "threshold": {"high_at_or_above_r": good, "limited_below_r": bad},
            "statement": (f"Over {len(years)} years CHIRPS and TerraClimate agree year to year at "
                          f"r = {r:.2f}, with CHIRPS {bias:+.0f}% against TerraClimate "
                          f"({a.mean():,.0f} against {b.mean():,.0f} mm a year). The gap between "
                          "them is the part of a rainfall figure that is the choice of product."),
            "source": "CHIRPS v3.0 against TerraClimate"}


def surface_water_quality(basin, **kwargs) -> dict[str, Any]:
    """Permanent against seasonal water, and how much was never observed."""
    occurrence = basin.surface_water(**kwargs)
    v = np.asarray(occurrence.values, dtype="float64").squeeze()
    inside = np.isfinite(v)
    total = int(inside.sum())
    if total == 0:
        return {"layer": "surface_water", "grade": "LIMITED", "value": None,
                "indicator": "observed share of the basin",
                "statement": "The surface water record covers none of this basin.",
                "source": "JRC Global Surface Water occurrence"}
    permanent = float(np.mean(v[inside] >= 75))
    seasonal = float(np.mean((v[inside] > 5) & (v[inside] < 75)))
    return {"layer": "surface_water", "indicator": "permanent against seasonal water",
            "grade": None, "not_graded_because":
                ("The JRC record carries no per-pixel confidence, so there is nothing here to "
                 "grade against. The split between permanent and seasonal water is reported "
                 "instead, because a basin whose water is mostly seasonal is one where a single "
                 "date would have misled."),
            "value": round(permanent, 5), "seasonal": round(seasonal, 5),
            "statement": (f"{permanent:.2%} of the basin holds water more than three months in four "
                          f"and {seasonal:.2%} holds it seasonally, over 1984 to 2021. "
                          "Water hidden under cloud or canopy is not in the record, so the seasonal "
                          "figure is a floor."),
            "source": "JRC Global Surface Water occurrence, 1984 to 2021"}


def delineation_quality(basin) -> dict[str, Any]:
    """What is actually known about the boundary: the checks that ran."""
    prov = dict(basin.provenance or {})
    check = prov.get("outlet_check") or {}
    area = float(basin.area_km2)
    regimes = ((100_000, 0.3), (10_000, 1.3), (2_000, 1.7))
    expected = next((err for floor, err in regimes if area >= floor), None)
    if expected is None:
        grade = "MODERATE"
        band = ("Below about 2,000 km2 the default backend's median error grows and the DEM "
                "backend is the better instrument.")
    else:
        grade = "HIGH"
        band = (f"At {area:,.0f} km2 the blind validation across 2,550 gauges in 99 countries "
                f"puts the median area error at {expected}%.")
    if check and check.get("ok") is False:
        grade = "LIMITED"
    statement = band
    if check:
        statement += (" The river-network check "
                      + ("agrees with the result" if check.get("ok") else
                         f"disagrees: {check.get('reason', 'see provenance')}") + ".")
    return {"layer": "delineation", "indicator": "network check and size regime",
            "grade": grade, "value": area, "backend": prov.get("backend"),
            "network_check": check or None, "statement": statement,
            "source": "basinkit validation table; the boundary itself is not remeasured here"}


def data_quality(basin, *, layers: tuple[str, ...] = ("elevation", "landcover", "soil",
                                                      "precipitation", "surface_water",
                                                      "delineation"),
                 dem=None, year: int = 2021, progress: bool = True) -> dict[str, Any]:
    """A grade for every layer this basin can return, each against something independent.

    Every entry carries the measurement, the threshold it was judged against and
    a sentence saying what was compared with what. A layer that could not be
    fetched is reported as an error rather than dropped, so the absence is
    visible.
    """
    runners = {
        "elevation": lambda: elevation_quality(basin, dem=dem, progress=progress),
        "landcover": lambda: landcover_quality(basin, year=year, progress=progress),
        "soil": lambda: soil_quality(basin, progress=progress),
        "precipitation": lambda: precipitation_quality(basin, progress=progress),
        "surface_water": lambda: surface_water_quality(basin, progress=progress),
        "delineation": lambda: delineation_quality(basin),
    }
    unknown = [name for name in layers if name not in runners]
    if unknown:
        raise ValueError(f"Unknown layer(s) {unknown}: choose from {sorted(runners)}")

    rows = []
    for name in layers:
        try:
            rows.append(runners[name]())
        except Exception as exc:
            rows.append({"layer": name, "grade": None, "value": None,
                         "indicator": None, "error": f"{type(exc).__name__}: {exc}",
                         "statement": f"{name} could not be checked: {exc}"})
    graded = [r["grade"] for r in rows if r.get("grade")]
    return {"basin_km2": round(float(basin.area_km2), 2),
            "overall": _worst(graded) if graded else None,
            "layers": rows,
            "note": ("Each layer is judged against something produced independently of it. "
                     "The thresholds are choices and are printed with every result; the "
                     "measurements beside them are what was found in this basin.")}
