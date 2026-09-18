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


def flow_accumulation(dem, *, method: str = "d8"):
    """Number of upstream cells draining through each cell.

    Runs pyflwdir over the basin's own elevation, which means the network is
    consistent with the terrain in front of you rather than with a global
    product at a different resolution.
    """
    import numpy as np

    try:
        import pyflwdir
    except ImportError as exc:  # pragma: no cover - exercised by the extra
        raise MissingDependency("pyflwdir", "delineate") from exc

    values = _as_array(dem)
    # Cells outside the polygon must be nodata, not filled ground. Filling
    # them with the maximum elevation turns every neighbouring catchment into
    # a ridge that drains inwards, and the accumulation then counts cells that
    # are not in this basin at all.
    nodata = -9999.0
    filled = np.where(np.isfinite(values), values, nodata)
    flw = pyflwdir.from_dem(
        data=filled.astype("float32"), nodata=nodata,
        transform=dem.rio.transform(),
        latlon=not (dem.rio.crs is not None and dem.rio.crs.is_projected),
        outlets="min",
    )
    if method != "d8":
        raise ValueError(f"Unknown method {method!r}. Only 'd8' is implemented.")
    acc = flw.upstream_area(unit="cell").astype("float64")
    acc = np.where(np.isfinite(values), acc, np.nan)
    return _wrap(dem, acc, "flow_accumulation", "cells",
                 "cells draining through each cell")


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
