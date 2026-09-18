"""Terrain surfaces derived from the basin's own elevation model.

Every layer here is computed from the array ``Basin.dem()`` already returns, so
none of it costs another download. They are separate functions rather than
something the DEM fetcher does, because a caller who wants slope for three
different lighting angles should pay for the elevation once.

Spacing is the part that is easy to get wrong. A Copernicus tile is on a
geographic grid, so a cell is a constant number of degrees wide and a varying
number of metres wide: at 60 degrees north it is half as wide as at the
equator. Gradients here are taken against metres computed per row from the
latitude of that row, so a slope in a high-latitude basin is not overstated by
a factor of two.
"""

from __future__ import annotations

import math

from .exceptions import MissingDependency

#: Metres per degree of latitude, and of longitude at the equator. The WGS84
#: meridional and equatorial values, rounded to the metre.
_M_PER_DEG_LAT = 110_574.0
_M_PER_DEG_LON = 111_320.0


def _as_array(dem):
    import numpy as np

    values = np.asarray(getattr(dem, "values", dem), dtype="float64")
    if values.ndim == 3 and values.shape[0] == 1:
        values = values[0]
    if values.ndim != 2:
        raise ValueError(
            f"Expected a 2-D elevation array, got shape {values.shape}. "
            "Pass basin.dem(), or one band of it."
        )
    return values


def _spacing(dem, values):
    """Cell size in metres: one number north-south, one per row east-west."""
    import numpy as np

    rio = getattr(dem, "rio", None)
    if rio is None:
        raise ValueError(
            "The elevation array carries no georeferencing, so cell size is "
            "unknown. Pass the array basin.dem() returns rather than a bare "
            "numpy array."
        )
    xres, yres = (abs(float(v)) for v in rio.resolution())
    crs = rio.crs

    if crs is not None and crs.is_projected:
        return yres, np.full(values.shape[0], xres, dtype="float64")

    lats = np.asarray(dem["y"].values, dtype="float64")
    if lats.size != values.shape[0]:
        lats = np.full(values.shape[0], float(np.mean(lats)))
    dx = xres * _M_PER_DEG_LON * np.cos(np.radians(lats))
    return yres * _M_PER_DEG_LAT, dx


def _gradient(dem):
    """(dz/dy, dz/dx) in metres per metre, with y increasing northwards."""
    import numpy as np

    values = _as_array(dem)
    dy_m, dx_m = _spacing(dem, values)
    gy, gx = np.gradient(values, edge_order=1)
    # rows run north to south in a north-up raster, so a positive step down a
    # row is a step south; flip it so that gy points north.
    ascending = float(dem["y"].values[0]) < float(dem["y"].values[-1]) if "y" in getattr(dem, "coords", {}) else False
    gy = gy / dy_m
    if not ascending:
        gy = -gy
    gx = gx / dx_m[:, None]
    return gy, gx


def _wrap(dem, values, name: str, units: str, long_name: str):
    """Return the same kind of object the caller handed in."""
    try:
        out = dem.copy(data=values)
    except Exception:
        return values
    out.name = name
    out.attrs = {
        **{k: v for k, v in getattr(dem, "attrs", {}).items()
           if k in ("license", "citation", "basinkit_product", "basinkit_sources")},
        "units": units,
        "long_name": long_name,
        "basinkit_derived_from": getattr(dem, "name", None) or "elevation",
    }
    return out


def slope(dem, *, degrees: bool = True):
    """Steepest descent at every cell.

    Returns degrees by default; ``degrees=False`` returns the tangent, which is
    the rise over run that most hydrological formulae actually want.
    """
    import numpy as np

    gy, gx = _gradient(dem)
    tangent = np.hypot(gx, gy)
    values = np.degrees(np.arctan(tangent)) if degrees else tangent
    return _wrap(dem, values, "slope",
                 "degrees" if degrees else "m/m", "terrain slope")


def aspect(dem):
    """Compass direction each slope faces, in degrees clockwise from north.

    Flat cells have no aspect and come back as NaN rather than as zero, which
    would otherwise read as a north-facing slope and bias any circular mean.
    """
    import numpy as np

    gy, gx = _gradient(dem)
    values = (np.degrees(np.arctan2(-gx, gy)) + 360.0) % 360.0
    values = np.where(np.hypot(gx, gy) < 1e-9, np.nan, values)
    return _wrap(dem, values, "aspect", "degrees", "slope aspect, clockwise from north")


def hillshade(dem, *, azimuth: float = 315.0, altitude: float = 45.0,
              z_factor: float = 1.0):
    """Shaded relief, 0 to 1, lit from ``azimuth`` at ``altitude`` degrees."""
    import numpy as np

    gy, gx = _gradient(dem)
    gy, gx = gy * z_factor, gx * z_factor
    slope_rad = np.arctan(np.hypot(gx, gy))
    aspect_rad = np.arctan2(-gx, gy)
    az, alt = math.radians(azimuth), math.radians(altitude)
    values = (np.sin(alt) * np.cos(slope_rad)
              + np.cos(alt) * np.sin(slope_rad) * np.cos(az - aspect_rad))
    return _wrap(dem, np.clip(values, 0.0, 1.0), "hillshade", "1",
                 f"shaded relief, lit from {azimuth:g} degrees at {altitude:g} degrees")


def curvature(dem):
    """Profile curvature: positive where the surface is convex.

    Convex ground sheds water and concave ground collects it, so the sign is
    the useful part.
    """
    import numpy as np

    values = _as_array(dem)
    dy_m, dx_m = _spacing(dem, values)
    gy, gx = np.gradient(values, edge_order=1)
    gyy = np.gradient(gy, edge_order=1)[0] / (dy_m ** 2)
    gxx = np.gradient(gx, edge_order=1)[1] / (dx_m[:, None] ** 2)
    return _wrap(dem, gyy + gxx, "curvature", "1/m", "profile curvature")


def cell_area_km2(dem):
    """Area of every cell, in square kilometres, as a 2-D array."""
    import numpy as np

    values = _as_array(dem)
    dy_m, dx_m = _spacing(dem, values)
    return np.broadcast_to((dy_m * dx_m[:, None]) / 1e6, values.shape).copy()


def _flwdir(dem):
    """Route the basin's own elevation, with everything outside it as nodata.

    Cells outside the polygon must be nodata rather than filled ground.
    Filling them with elevation turns every neighbouring catchment into a
    ridge that drains inwards, and the accumulation then counts cells that are
    not in this basin at all.
    """
    import numpy as np

    try:
        import pyflwdir
    except ImportError as exc:  # pragma: no cover - exercised by the extra
        raise MissingDependency("pyflwdir", "delineate") from exc

    values = _as_array(dem)
    nodata = -9999.0
    masked = np.where(np.isfinite(values), values, nodata).astype("float32")
    # Route on the depression-filled surface and keep it: height above
    # drainage measured against the raw elevation goes negative inside every
    # filled pit, because the cell sits below the channel it now drains into.
    filled, _ = pyflwdir.dem.fill_depressions(
        masked, nodata=nodata, outlets="min"
    )
    flw = pyflwdir.from_dem(
        data=filled, nodata=nodata,
        transform=dem.rio.transform(),
        latlon=not (dem.rio.crs is not None and dem.rio.crs.is_projected),
        outlets="min",
    )
    return flw, values, filled


def flow_accumulation(dem, *, method: str = "d8"):
    """Number of upstream cells draining through each cell.

    Runs pyflwdir over the basin's own elevation, which means the network is
    consistent with the terrain in front of you rather than with a global
    product at a different resolution.
    """
    import numpy as np

    if method != "d8":
        raise ValueError(f"Unknown method {method!r}. Only 'd8' is implemented.")
    flw, values, _ = _flwdir(dem)
    acc = np.where(np.isfinite(values), flw.upstream_area(unit="cell"), np.nan)
    return _wrap(dem, acc.astype("float64"), "flow_accumulation", "cells",
                 "cells draining through each cell")


def streams(dem, *, min_area_km2: float = 1.0):
    """Boolean mask of the channel network, thresholded on drained area.

    The threshold is the choice that decides how far the network reaches into
    the headwaters. A square kilometre is a common default for a 30 m grid;
    raise it on flat or arid ground where the routed network runs further than
    any channel actually does.
    """
    import numpy as np

    flw, values, _ = _flwdir(dem)
    drained = flw.upstream_area(unit="cell") * cell_area_km2(dem)
    mask = np.isfinite(values) & (drained >= float(min_area_km2))
    return _wrap(dem, mask.astype("float32"), "streams", "1",
                 f"channel network, drained area at least {min_area_km2:g} km2")


def hand(dem, *, min_area_km2: float = 1.0):
    """Height above the nearest drainage, in metres.

    The drop from each cell to the channel it drains into, following the flow
    path rather than the straight line. Low HAND is the ground a river reaches
    first, so this is the terrain layer flood work actually wants; elevation
    on its own says nothing about how far above the water a place sits.

    After Nobre et al. (2016), Hydrological Processes 30, 320-333.
    """
    import numpy as np

    flw, values, filled = _flwdir(dem)
    drained = flw.upstream_area(unit="cell") * cell_area_km2(dem)
    drain = np.isfinite(values) & (drained >= float(min_area_km2))
    if not drain.any():
        raise ValueError(
            f"No cell drains {min_area_km2:g} km2 or more, so there is no "
            "channel to measure height above. Lower min_area_km2, or work on "
            "a larger basin."
        )
    heights = flw.hand(drain=drain, elevtn=filled)
    heights = np.where(np.isfinite(values), heights, np.nan)
    return _wrap(dem, heights.astype("float64"), "hand", "m",
                 "height above nearest drainage")


def twi(dem, *, accumulation=None):
    """Topographic wetness index, ln(a / tan beta).

    High where a lot of ground drains into a place that is flat: the ground
    that saturates first. Slopes below a hundredth of a degree are floored
    rather than allowed to divide by zero and produce an infinity that
    propagates through every statistic computed afterwards.
    """
    import numpy as np

    acc = flow_accumulation(dem) if accumulation is None else accumulation
    acc_values = _as_array(acc)
    elevation = _as_array(dem)
    dy_m, dx_m = _spacing(dem, elevation)
    cell_area = dy_m * dx_m[:, None]
    width = np.sqrt(cell_area)

    tan_beta = _as_array(slope(dem, degrees=False))
    tan_beta = np.maximum(tan_beta, math.tan(math.radians(0.01)))

    specific = (acc_values + 1.0) * cell_area / width
    values = np.log(specific / tan_beta)
    values = np.where(np.isfinite(elevation), values, np.nan)
    return _wrap(dem, values, "twi", "1", "topographic wetness index")


def _box_sum(values, size: int):
    """Sum over every ``size`` x ``size`` window, by summed-area table.

    One pass whatever the window, which is what makes an 11-cell window as
    cheap as a 3-cell one. Cells off the edge count as absent rather than as
    zero, so a border window averages the cells it actually has.
    """
    import numpy as np

    pad = size // 2
    padded = np.pad(values, pad, mode="constant", constant_values=0.0)
    integral = padded.cumsum(axis=0).cumsum(axis=1)
    integral = np.pad(integral, ((1, 0), (1, 0)), mode="constant", constant_values=0.0)
    rows, cols = values.shape
    return (integral[size:size + rows, size:size + cols]
            - integral[0:rows, size:size + cols]
            - integral[size:size + rows, 0:cols]
            + integral[0:rows, 0:cols])


def _window_mean(values, size: int):
    """Mean over a square window, with nodata left out of both sums."""
    import numpy as np

    finite = np.isfinite(values)
    total = _box_sum(np.where(finite, values, 0.0), size)
    count = _box_sum(finite.astype("float64"), size)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = total / count
    return np.where(count > 0, mean, np.nan)


def _neighbours(values):
    """The eight neighbours of every cell, stacked, edges replicated."""
    import numpy as np

    padded = np.pad(values, 1, mode="edge")
    rows, cols = values.shape
    return np.stack([
        padded[a:a + rows, b:b + cols]
        for a in range(3) for b in range(3)
        if not (a == 1 and b == 1)
    ])


def tpi(dem, *, window: int = 11):
    """Topographic position index: height above the surrounding ground.

    A cell's elevation minus the mean of the window around it. Positive on
    ridges and spurs, negative in valleys, near zero on a uniform slope and on
    a plain alike -- which is why the landform classes below need slope as
    well, to tell a flat valley floor from a flat hilltop.

    After Weiss (2001), ESRI User Conference.

    Parameters
    ----------
    window
        Width of the neighbourhood in cells. The scale of landform it
        responds to: 11 cells on a 30 m grid is roughly a 300 m hillslope.
    """
    import numpy as np

    if window < 3 or window % 2 == 0:
        raise ValueError(f"window must be an odd number of cells, 3 or more, not {window}")
    values = _as_array(dem)
    out = values - _window_mean(values, window)
    out = np.where(np.isfinite(values), out, np.nan)
    return _wrap(dem, out, "tpi", "m",
                 f"topographic position index over {window} cells")


def tri(dem):
    """Terrain ruggedness index: how far a cell sits from its neighbours.

    The root of the summed squared elevation difference to all eight adjacent
    cells.

    Worth knowing before quoting it. On a smooth uniform slope this is largely
    a restatement of gradient, because a plane's neighbours differ from its
    centre in proportion to its steepness: a 30 percent plane with no
    variation in it at all scores about 82 m on a 110 m grid. It separates
    rough ground from smooth ground *at a given gradient*; it does not
    separate rough ground from steep ground. Where the two need telling apart,
    read it beside :func:`slope` rather than instead of it.

    After Riley et al. (1999), Intermountain Journal of Sciences 5, 23-27.
    """
    import numpy as np

    values = _as_array(dem)
    diff = _neighbours(values) - values[None, :, :]
    with np.errstate(invalid="ignore"):
        out = np.sqrt(np.nansum(diff ** 2, axis=0))
    out = np.where(np.isfinite(values), out, np.nan)
    return _wrap(dem, out, "tri", "m", "terrain ruggedness index")


def roughness(dem):
    """Local relief: the elevation range within a cell's 3x3 neighbourhood.

    The plainest of the three, and the one to reach for when the number has to
    mean something to a reader without a definition to hand.

    After Wilson et al. (2007), Marine Geodesy 30, 3-35.
    """
    import numpy as np

    values = _as_array(dem)
    stack = np.concatenate([_neighbours(values), values[None, :, :]])
    with np.errstate(invalid="ignore"):
        out = np.nanmax(stack, axis=0) - np.nanmin(stack, axis=0)
    out = np.where(np.isfinite(values), out, np.nan)
    return _wrap(dem, out, "roughness", "m", "local relief over 3x3 cells")


#: The six slope-position classes, in the order their codes run.
LANDFORM_CLASSES = ("valley", "lower slope", "flat", "mid slope",
                    "upper slope", "ridge")


def landform(dem, *, window: int = 11, flat_deg: float = 5.0):
    """Six slope-position classes, from the position index and the gradient.

    Codes 0 to 5: valley, lower slope, flat, mid slope, upper slope, ridge,
    as :data:`LANDFORM_CLASSES` names them. The cuts are at half and one
    standard deviation of the position index over this basin, so the classes
    are relative to the terrain in front of you and are not comparable between
    basins without saying so.

    After Weiss (2001). The flat and mid-slope classes share a band of the
    position index and are separated by gradient, which is the only way to
    tell a valley floor from a bench on a hillside.
    """
    import numpy as np

    position = _as_array(tpi(dem, window=window))
    gradient = _as_array(slope(dem))
    spread = float(np.nanstd(position))
    if not np.isfinite(spread) or spread == 0:
        raise ValueError(
            "The position index has no spread in this basin, so there are no "
            "slope positions to separate. That is a perfectly level surface, "
            "or a window larger than the basin."
        )

    out = np.full(position.shape, np.nan)
    middle = (position > -spread / 2) & (position < spread / 2)
    out = np.where(position <= -spread, 0.0, out)
    out = np.where((position > -spread) & (position <= -spread / 2), 1.0, out)
    out = np.where(middle & (gradient <= flat_deg), 2.0, out)
    out = np.where(middle & (gradient > flat_deg), 3.0, out)
    out = np.where((position >= spread / 2) & (position < spread), 4.0, out)
    out = np.where(position >= spread, 5.0, out)
    out = np.where(np.isfinite(position), out, np.nan)

    wrapped = _wrap(dem, out, "landform", "class",
                    "slope position: " + ", ".join(
                        f"{i}={name}" for i, name in enumerate(LANDFORM_CLASSES)))
    try:
        wrapped.attrs["basinkit_classes"] = list(LANDFORM_CLASSES)
        wrapped.attrs["basinkit_tpi_sd_m"] = round(spread, 4)
    except AttributeError:
        pass
    return wrapped


def initiation_threshold_km2(dem, *, slope_deg=None) -> tuple[float, str]:
    """A channel-initiation threshold scaled to how steep the basin is.

    Critical source area falls as gradient rises, so steep ground starts
    channels at a much smaller contributing area than a plain does. Using one
    threshold everywhere makes drainage density incomparable between the two.

    After Montgomery and Dietrich (1988), Nature 336, 232-234.

    Returns
    -------
    tuple
        The threshold in square kilometres and the reason it was chosen, so
        that the reason can be printed beside the number.
    """
    import numpy as np

    values = _as_array(slope(dem) if slope_deg is None else slope_deg)
    median = float(np.nanmedian(values))
    if median >= 15.0:
        return 0.05, f"steep terrain, median slope {median:.1f} degrees"
    if median >= 5.0:
        return 0.25, f"moderate terrain, median slope {median:.1f} degrees"
    return 1.00, f"low-relief terrain, median slope {median:.1f} degrees"


def drainage_density(dem, *, thresholds=None, chosen_km2: float | None = None):
    """Drainage density across the range of defensible thresholds.

    Drainage density is the most quoted number in basin morphometry and the
    least comparable. It is not a property of a basin: it is a function of
    where you decide a channel begins, and it moves by a large factor across
    thresholds that are all defensible. Reporting the curve, and printing the
    threshold used, turns a quotable number into a comparable one.

    Parameters
    ----------
    thresholds
        Channel-initiation areas in square kilometres. The default runs an
        order of magnitude either side of the slope-scaled choice, which is
        about as far as a threshold can be defended in either direction.
        Widening it further inflates the range factor with choices nobody
        would make.
    chosen_km2
        The threshold to mark as chosen. Defaults to
        :func:`initiation_threshold_km2`.

    Returns
    -------
    dict
        ``curve`` is one row per threshold with the channel length and the
        density it implies; ``chosen`` is the marked row; ``range_factor`` is
        how far the density moves across the span, which is the figure that
        says whether a quoted density means anything on its own.
    """
    import numpy as np

    flw, values, _ = _flwdir(dem)
    inside = np.isfinite(values)
    basin_cells = int(inside.sum())
    if not basin_cells:
        raise ValueError("The elevation array is entirely nodata.")

    per_cell_km2 = _as_array(cell_area_km2(dem))
    basin_km2 = float(np.nansum(np.where(inside, per_cell_km2, 0.0)))
    drained_km2 = flw.upstream_area(unit="cell") * per_cell_km2

    # The distance from each cell to the one it drains into, which is the
    # segment that cell contributes to the network's length.
    dy_m, dx_m = _spacing(dem, values)
    rows, cols = values.shape
    index = np.arange(values.size).reshape(values.shape)
    downstream = np.asarray(flw.idxs_ds).reshape(values.shape)
    drow = downstream // cols - index // cols
    dcol = downstream % cols - index % cols
    step_m = np.hypot(drow * dy_m, dcol * dx_m[:, None])
    # A pit drains to itself, so it contributes no length.
    step_m = np.where(downstream == index, 0.0, step_m)

    if chosen_km2 is None:
        chosen_km2, reason = initiation_threshold_km2(dem)
    else:
        reason = "supplied by the caller"

    if thresholds is None:
        thresholds = [chosen_km2 * f for f in
                      (0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0)]
    thresholds = sorted(float(t) for t in thresholds if float(t) > 0)

    curve = []
    for threshold in thresholds:
        channel = inside & (drained_km2 >= threshold)
        length_km = float(np.nansum(np.where(channel, step_m, 0.0))) / 1000.0
        curve.append({
            "threshold_km2": round(threshold, 6),
            "channel_length_km": round(length_km, 3),
            "drainage_density_km_per_km2": round(length_km / basin_km2, 5),
            "channel_cells": int(channel.sum()),
        })

    densities = [row["drainage_density_km_per_km2"] for row in curve
                 if row["drainage_density_km_per_km2"] > 0]
    factor = (max(densities) / min(densities)) if len(densities) > 1 else 1.0
    marked = min(curve, key=lambda row: abs(row["threshold_km2"] - chosen_km2))

    return {
        "basin_km2": round(basin_km2, 4),
        "span": [round(thresholds[0], 6), round(thresholds[-1], 6)],
        "chosen_threshold_km2": round(float(chosen_km2), 6),
        "chosen_because": reason,
        "chosen": marked,
        "curve": curve,
        "range_factor": round(float(factor), 2),
        "note": "Drainage density is a function of the channel-initiation "
                "threshold, not a property of the basin. Quote the threshold "
                "with the number, or the number cannot be compared with "
                "anyone else's.",
    }
