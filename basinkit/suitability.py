"""Whether the elevation model supports the terrain analysis asked of it.

Every terrain product in basinkit -- slope, aspect, curvature, the wetness
index, height above drainage, the hypsometric integral, every relief parameter
in :func:`~basinkit.morphometry.morphometry` -- is computed from one elevation
raster. Whether those numbers mean anything depends on whether the raster can
resolve the terrain in this particular basin, which is a different question in
a Himalayan gorge and on a coastal plain.

The accuracy tables published with basinkit answer the first half of that:
across thousands of gauges, at this catchment size, this is the error to
expect. That is a population figure. It cannot say whether *this* basin is one
of the good cases. This module answers the second half by measuring the basin
in front of it.

Five tests, each a measurement against a stated threshold:

``filling``
    How much of the surface depression filling had to invent. A basin where a
    fifth of the cells were raised is one where the drainage network is partly
    the conditioning algorithm's own work.

``slope``
    The noise floor of the model, ``arctan(vertical error / cell size)``, and
    how many of the basin's slopes fall below it. Below that angle a slope
    value is the model's error expressed as a gradient.

``relief``
    Total relief against the model's vertical error. A 40 m basin measured
    with a 4 m error carries a tenth of its own signal as uncertainty.

``water``
    The largest level surface inside the basin. Standing water has no
    gradient, so slope, aspect, curvature and the wetness index over it are
    not measurements of anything.

``coverage``
    Cells inside the basin with no elevation at all. Global models have
    withheld tiles and voids, and a missing fifth of a basin biases every
    statistic computed over it.

The grade is ``HIGH`` when every test passes, ``MODERATE`` when one is close
to its threshold, and ``LIMITED`` when one is past it. It is deliberately
about the terrain products and not about the basin boundary: the boundary
comes from the delineation backend, which is measured separately in the
verification page.
"""

from __future__ import annotations

import math
import warnings
from typing import Any

import numpy as np

from .terrain import _as_array, _spacing
from .terrain import slope as _slope

#: Approximate vertical RMSE in metres, from each product's own specification.
#: These are the numbers every threshold below is expressed against, so they
#: are stated here rather than buried in the tests.
VERTICAL_ERROR_M = {
    "cop30": 4.0,
    "cop90": 4.0,
    "nasadem": 5.3,
    "srtm30": 6.0,
}

#: Used when the product is unknown -- a caller's own raster, for instance.
#: The least favourable of the four, because assuming better than is known
#: would turn an unsupported answer into a passing grade.
DEFAULT_VERTICAL_ERROR_M = 6.0

# A radar model over standing water returns an almost perfectly smooth
# surface: the local 3x3 range collapses towards zero. Real terrain, even a
# floodplain, carries metres of variation at that scale, so the test separates
# water from level ground rather than merely from steep ground.
_SMOOTH_TOL_M = 0.6

# And a water surface is level end to end, not merely locally smooth. Measured
# between the 2nd and 98th percentiles, because a few shoreline cells inflate
# the raw range enough to reject a genuine reservoir.
_LEVEL_TOL_M = 2.5

# Below this a level surface cannot distort the basin statistics whatever
# fraction it occupies, so it is not worth naming.
_MIN_BODY_KM2 = 0.5

_GRADES = ("HIGH", "MODERATE", "LIMITED")


def _range_3x3(values):
    """Local maximum minus local minimum over a 3x3 window, ignoring nodata."""
    padded = np.pad(values, 1, mode="edge")
    stack = np.stack([
        padded[a:a + values.shape[0], b:b + values.shape[1]]
        for a in range(3) for b in range(3)
    ])
    # A window entirely outside the basin is all nodata, which numpy reports
    # rather than returning quietly. It is expected here, not a problem.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmax(stack, axis=0) - np.nanmin(stack, axis=0)


def _components(mask):
    """Label connected regions of ``mask``, eight-connected.

    Uses ``scipy.ndimage`` when it is installed and a breadth-first walk when
    it is not, so that the suitability check never depends on an extra.
    """
    mask = np.asarray(mask, dtype=bool)
    try:
        from scipy import ndimage

        structure = np.ones((3, 3), dtype=bool)
        labels, count = ndimage.label(mask, structure=structure)
        return labels, count
    except ImportError:
        pass

    from collections import deque

    labels = np.zeros(mask.shape, dtype="int32")
    nrow, ncol = mask.shape
    count = 0
    for seed in zip(*np.nonzero(mask), strict=True):
        if labels[seed]:
            continue
        count += 1
        labels[seed] = count
        queue = deque([seed])
        while queue:
            row, col = queue.popleft()
            for drow in (-1, 0, 1):
                for dcol in (-1, 0, 1):
                    r, c = row + drow, col + dcol
                    if 0 <= r < nrow and 0 <= c < ncol and mask[r, c] and not labels[r, c]:
                        labels[r, c] = count
                        queue.append((r, c))
    return labels, count


def _largest_level_surface(values, cell_km2: float):
    """Area and elevation of the biggest contiguous level surface, if any."""
    finite = np.isfinite(values)
    if not finite.any():
        return 0.0, None

    smooth = (_range_3x3(values) < _SMOOTH_TOL_M) & finite
    if not smooth.any():
        return 0.0, None

    labels, count = _components(smooth)
    if not count:
        return 0.0, None

    best_area, best_elev = 0.0, None
    for i in range(1, count + 1):
        body = labels == i
        size = int(body.sum())
        area = size * cell_km2
        if area <= best_area or area < _MIN_BODY_KM2:
            continue
        surface = values[body]
        spread = float(np.nanpercentile(surface, 98) - np.nanpercentile(surface, 2))
        if spread > _LEVEL_TOL_M:
            continue
        best_area, best_elev = area, float(np.nanmedian(surface))
    return best_area, best_elev


def _verdict(measured: float, advisory_at: float, unmet_at: float, *,
             lower_is_better: bool = True) -> str:
    if lower_is_better:
        if measured >= unmet_at:
            return "unmet"
        return "advisory" if measured >= advisory_at else "pass"
    if measured <= unmet_at:
        return "unmet"
    return "advisory" if measured <= advisory_at else "pass"


def _fill_depth(dem, values):
    """Metres added to each cell by depression filling, or ``None``.

    Returns ``None`` rather than raising when ``pyflwdir`` is absent: the other
    four tests are still worth having, and the report says which one is
    missing.
    """
    try:
        import pyflwdir
    except ImportError:
        return None

    nodata = -9999.0
    masked = np.where(np.isfinite(values), values, nodata).astype("float32")
    filled, _ = pyflwdir.dem.fill_depressions(masked, nodata=nodata, outlets="min")
    depth = np.where(np.isfinite(values), filled - masked, np.nan)
    return np.asarray(depth, dtype="float64")


def _inside_polygon(basin, dem, values):
    """Which cells the basin actually covers, or ``None`` for a bare raster.

    ``Basin.dem()`` returns the clip's bounding box with everything outside
    the polygon as nodata, and on a real catchment that is most of the array.
    Counting those cells as missing elevation would report a basin with
    complete coverage as more than half absent -- the bounding-box mistake
    this package exists to avoid, made against itself.
    """
    geometry = getattr(basin, "geometry", None)
    if geometry is None:
        return None
    try:
        from rasterio.features import geometry_mask

        return ~geometry_mask([geometry], out_shape=values.shape,
                              transform=dem.rio.transform(), invert=False)
    except Exception:
        return None


def suitability(basin, *, dem=None, product: str | None = None,
                support_map: bool = False) -> dict[str, Any]:
    """Grade how well the elevation model supports terrain analysis here.

    Parameters
    ----------
    basin
        A :class:`~basinkit.basin.Basin`, or any elevation array carrying its
        own georeferencing.
    dem
        An already-fetched elevation raster, to avoid downloading it twice.
    product
        The elevation product, used to pick the vertical error. Taken from the
        raster's own attributes when it is not given, and assumed to be the
        least accurate of the four when it cannot be determined.
    support_map
        Also return ``support``: 1 where a cell was neither raised by filling
        nor below the slope noise floor, 0 where it was, and nodata outside
        the basin.

    Returns
    -------
    dict
        ``grade``, the five ``tests`` with their measurements and thresholds,
        ``unmet`` and ``advisory`` lists, ``statement``, and the constants the
        thresholds were applied against.
    """
    elevation = dem
    if elevation is None:
        elevation = basin.dem() if hasattr(basin, "dem") else basin
    values = _as_array(elevation)

    if product is None:
        product = getattr(elevation, "attrs", {}).get("basinkit_product")
    key = str(product).lower() if product else ""
    error_m = VERTICAL_ERROR_M.get(key, DEFAULT_VERTICAL_ERROR_M)

    dy_m, dx_m = _spacing(elevation, values)
    cell_m = float(np.mean([dy_m, float(np.mean(dx_m))]))
    cell_km2 = float(np.mean(dx_m)) * dy_m / 1e6

    inside = np.isfinite(values)
    known = int(inside.sum())
    polygon = _inside_polygon(basin, elevation, values)
    covered = polygon if polygon is not None else np.ones(values.shape, dtype=bool)
    total_cells = int(covered.sum())

    tests: list[dict[str, Any]] = []
    unmet: list[str] = []
    advisory: list[str] = []

    def record(name, verdict, measured, unit, advisory_at, unmet_at, statement,
               evaluated=True, **extra):
        entry = {"test": name, "verdict": verdict, "measured": measured,
                 "unit": unit, "advisory_at": advisory_at, "unmet_at": unmet_at,
                 "evaluated": evaluated, "statement": statement, **extra}
        tests.append(entry)
        if verdict == "unmet":
            unmet.append(name)
        elif verdict == "advisory":
            advisory.append(name)

    # --- filling -----------------------------------------------------------
    depth = _fill_depth(elevation, values)
    raised_frac = None
    if depth is None:
        record("filling", "pass", None, "percent of cells", 5.0, 20.0,
               "Not evaluated: depression filling needs pyflwdir, which is in "
               'the delineate extra. Install it with pip install '
               '"basinkit[delineate]" to include this test.',
               evaluated=False)
    else:
        d = depth[np.isfinite(depth)]
        raised = (d > 0.01)
        raised_pct = float(raised.sum() / d.size * 100) if d.size else 0.0
        max_fill = float(d.max()) if d.size else 0.0
        raised_frac = raised_pct
        record("filling", _verdict(raised_pct, 5.0, 20.0), round(raised_pct, 2),
               "percent of cells", 5.0, 20.0,
               f"Depression filling raised {raised_pct:.1f}% of cells, the "
               f"deepest by {max_fill:.1f} m. Drainage across raised ground is "
               "the conditioning algorithm's construction, not mapped relief.",
               max_fill_m=round(max_fill, 2))

    # --- slope -------------------------------------------------------------
    noise_floor_deg = float(math.degrees(math.atan(error_m / cell_m)))
    slope_deg = np.asarray(getattr(_slope(elevation), "values", None), dtype="float64")
    s = slope_deg[np.isfinite(slope_deg)]
    below_pct = float((s < noise_floor_deg).sum() / s.size * 100) if s.size else 0.0
    record("slope", _verdict(below_pct, 25.0, 60.0), round(below_pct, 2),
           "percent of cells", 25.0, 60.0,
           f"At {error_m:.1f} m vertical error over a {cell_m:.0f} m cell the "
           f"noise floor is {noise_floor_deg:.1f} degrees, and {below_pct:.0f}% "
           "of this basin's slopes fall below it. Those values are the model's "
           "own error expressed as a gradient.",
           noise_floor_deg=round(noise_floor_deg, 3))

    # --- relief ------------------------------------------------------------
    z = values[inside]
    relief_m = float(z.max() - z.min()) if z.size else 0.0
    ratio = relief_m / error_m if error_m else float("inf")
    record("relief", _verdict(ratio, 100.0, 20.0, lower_is_better=False),
           round(ratio, 1), "relief divided by vertical error", 100.0, 20.0,
           f"Relief is {relief_m:.0f} m against a vertical error of "
           f"{error_m:.1f} m, a ratio of {ratio:.0f}. Every elevation-derived "
           "parameter carries that ratio as its relative uncertainty.",
           relief_m=round(relief_m, 1))

    # --- water -------------------------------------------------------------
    body_km2, body_elev = _largest_level_surface(values, cell_km2)
    basin_km2 = known * cell_km2
    body_pct = (body_km2 / basin_km2 * 100) if basin_km2 else 0.0
    # Judged as a share of the basin, not as an absolute area. A 24 km2 lake
    # is most of a small catchment and a rounding error in the Koshi, and an
    # absolute threshold grades the second one as though it were the first.
    if body_km2 >= _MIN_BODY_KM2:
        water_verdict = _verdict(body_pct, 1.0, 5.0)
        water_statement = (
            f"A level surface of {body_km2:.2f} km2 at {body_elev:.0f} m covers "
            f"{body_pct:.2f}% of the basin: standing water, or permanent snow "
            "and ice, which the sensor returns the same way. Slope, aspect, "
            "curvature and the wetness index over it describe a flat return "
            "rather than ground. The basin boundary is unaffected, since "
            "delineation here does not route on this raster."
        )
    else:
        water_verdict = "pass"
        water_statement = (
            "No level surface large enough to distort the terrain statistics."
        )
    record("water", water_verdict, round(body_pct, 3),
           "percent of basin", 1.0, 5.0, water_statement,
           surface_km2=round(body_km2, 3),
           surface_elev_m=None if body_elev is None else round(body_elev, 1))

    # --- coverage ----------------------------------------------------------
    absent = int((covered & ~inside).sum())
    missing_pct = float(absent / total_cells * 100) if total_cells else 0.0
    record("coverage", _verdict(missing_pct, 0.5, 2.0), round(missing_pct, 3),
           "percent of cells", 0.5, 2.0,
           f"{missing_pct:.2f}% of the cells inside this basin carry no "
           "elevation. Global models have withheld tiles and unfilled voids, "
           "and every statistic computed over the basin is biased by whatever "
           "is missing.",
           measured_inside="polygon" if polygon is not None else "whole raster")

    grade = "LIMITED" if unmet else ("MODERATE" if advisory else "HIGH")

    out: dict[str, Any] = {
        "grade": grade,
        "product": product or "unknown",
        "vertical_error_m": error_m,
        "cell_size_m": round(cell_m, 2),
        "basin_km2": round(basin_km2, 3),
        "tests": tests,
        "unmet": unmet,
        "advisory": advisory,
        "statement": _statement(grade, tests),
        "note": "A grade for the terrain products computed from this raster. "
                "The basin boundary is delineated separately and its accuracy "
                "is reported in the verification page, not here.",
    }

    if support_map:
        supported = np.ones(values.shape, dtype="float64")
        if depth is not None:
            supported[np.nan_to_num(depth, nan=0.0) > 0.01] = 0.0
        supported[np.nan_to_num(slope_deg, nan=noise_floor_deg) < noise_floor_deg] = 0.0
        supported[~inside] = np.nan
        out["support"] = _wrap_support(elevation, supported)
        out["support_fraction"] = (
            round(float(np.nansum(supported) / known), 4) if known else None
        )
    elif raised_frac is not None:
        out["support_fraction"] = None

    return out


def _wrap_support(dem, supported):
    from .terrain import _wrap

    return _wrap(dem, supported, "dem_support", "1 = supported",
                 "Cells neither raised by depression filling nor below the "
                 "slope noise floor")


def _statement(grade: str, tests: list[dict[str, Any]]) -> str:
    """The plain-language verdict, built from the tests that were not met."""
    if grade == "HIGH":
        return (
            "Every suitability test passed. The terrain signal in this basin "
            "sits well above the elevation model's stated accuracy, little of "
            "the surface was reconstructed by conditioning, and the basin is "
            "fully covered. The terrain products are as good as this model gets."
        )

    failing = [t for t in tests if t["verdict"] in ("unmet", "advisory")]
    reasons = " ".join(t["statement"] for t in failing)

    if grade == "MODERATE":
        head = (
            "The terrain products are usable with the qualification below. One "
            "measurement is close to the model's resolving limit, so read the "
            "affected values as approximate rather than exact. "
        )
    else:
        head = (
            "This basin sits at or past the resolving limit of the elevation "
            "model, so the terrain products below reflect the model and its "
            "conditioning as much as the ground. A finer elevation source, "
            "survey sheets or field data will settle it. The measurements say "
            "precisely which condition applies. "
        )
    return head + reasons
