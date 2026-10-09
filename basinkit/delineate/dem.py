"""Delineation by D8 flow routing over a freshly downloaded DEM.

This is the precise backend: it resolves a divide down to one 30 m pixel, so it
is the right choice for headwater catchments that a HydroBASINS level-12 unit
cannot see inside of. The cost is that it has to download and route a window
big enough to contain the whole basin, which stops being sensible somewhere
around a few thousand square kilometres.

The window is grown adaptively: if the delineated basin touches the edge of the
DEM window, the true basin extends beyond it and the answer is wrong, so the
window is doubled and the routing re-run.
"""

from __future__ import annotations

import functools
import warnings

import numpy as np

from ..exceptions import DelineationError, MissingDependency, OutletSnapError

#: Peak resident memory per pixel of the routing window, in bytes. D8 routing
#: holds far more than the elevation array: the receiver index, the ordered
#: traversal, upstream area and the basin mask are all the size of the grid
#: again. Measured here on two windows of the same terrain, reading the peak
#: resident set of the whole process:
#:
#:     1 degree window   13.5 Mpx   1.12 GB
#:     2 degree window   52.9 Mpx   3.32 GB
#:
#: which is 56 bytes per pixel at the margin, over a baseline of about 0.4 GB
#: for the interpreter and its libraries. Rounded up, because being wrong in
#: this direction costs a refusal and being wrong in the other costs the
#: process.
BYTES_PER_PIXEL = 60

#: How much memory the routing step may be expected to need before this
#: backend declines the job. The failure it replaces is the one worth knowing
#: about: a 25,000 km2 catchment grows its window to four degrees, 207
#: megapixels, an estimated twelve gigabytes, and the process is killed by the
#: kernel with no traceback and nothing written. A refusal that names the
#: figure and the alternative is a better answer than a dead terminal. Raise
#: it on a machine with the memory to spare.
DEFAULT_MAX_MEMORY_GB = 4.0


def _estimated_gb(n_pixels: int) -> float:
    return n_pixels * BYTES_PER_PIXEL / 1e9


def _refuse(n_pixels: int, half: float, limit_gb: float) -> DelineationError:
    """The message that replaces being killed by the kernel."""
    return DelineationError(
        f"Routing a {2 * half:.1f} degree window at 30 m means "
        f"{n_pixels / 1e6:,.0f} megapixels, which needs about "
        f"{_estimated_gb(n_pixels):.1f} GB of memory -- above the "
        f"{limit_gb:g} GB this backend will attempt. D8 routing holds the "
        "receiver index, the traversal order, upstream area and the basin "
        "mask at the size of the grid, so the cost grows with the square of "
        "the window.\n\n"
        "Either delineate with backend='hydrobasins', which walks a graph "
        "instead of a raster and handles any size, or raise the limit with "
        "max_memory_gb= if this machine has the memory."
    )


def _require_pyflwdir():
    try:
        import pyflwdir

        return pyflwdir
    except ImportError as exc:
        raise MissingDependency("pyflwdir", "delineate") from exc


def _snap_to_stream(flw, uparea, row, col, *, search_px: int = 12,
                    min_uparea_km2: float = 1.0):
    """Move the pour point onto the largest-drainage cell nearby.

    A coordinate taken from a map or a GPS is rarely exactly on the modelled
    channel. Routing from a hillslope cell one pixel off the stream returns a
    basin of a few hectares instead of a few hundred square kilometres -- the
    single most common way DEM delineation goes silently wrong. Snapping to the
    local maximum of upstream area fixes it.
    """
    nrow, ncol = uparea.shape
    # Cells on the DEM edge absorb everything leaving the window, so their
    # upstream area is an artefact of where the raster was cropped, not real
    # drainage. Snapping onto one silently returns a basin that is mostly
    # off-map, so they are excluded from the search.
    safe = uparea.astype("float64").copy()
    safe[0, :] = safe[-1, :] = safe[:, 0] = safe[:, -1] = np.nan

    r0, r1 = max(0, row - search_px), min(nrow, row + search_px + 1)
    c0, c1 = max(0, col - search_px), min(ncol, col + search_px + 1)
    window = safe[r0:r1, c0:c1]
    if window.size == 0 or not np.isfinite(window).any():
        raise OutletSnapError("DEM window contains no valid flow accumulation.")

    if not np.isfinite(window).any():
        raise OutletSnapError(
            "Every candidate cell near the outlet sits on the DEM window edge. "
            "Increase window_deg so the outlet is interior."
        )
    idx = int(np.nanargmax(window))
    dr, dc = np.unravel_index(idx, window.shape)
    best = float(window[dr, dc])
    if best < min_uparea_km2:
        raise OutletSnapError(
            f"No cell within {search_px} px of the outlet drains more than "
            f"{min_uparea_km2} km2 (best: {best:.3f} km2). The point is probably "
            "on a hillslope rather than a channel."
        )
    return r0 + int(dr), c0 + int(dc), best


def _quiet_matmul(fn):
    """Silence affine's matmul deprecation for the duration of one call.

    ``affine`` 3.0 deprecated ``*`` for matrix multiplication, and pyflwdir,
    rasterio and rioxarray all still use it, so a single delineation emitted
    twenty-six copies of "Use `@` matmul instead of `*` mul operator" --
    twenty-six lines in the QGIS log for every basin. It names a file the user
    did not write and cannot change, there is nothing to be done about it
    until those libraries are updated, and a log nobody reads is worse than no
    log. Filtered by its own message, inside this call only, so no other
    warning is lost and the process-wide filters are left as the caller set
    them.
    """
    @functools.wraps(fn)
    def inner(*args, **kwargs):
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=r".*matmul.*")
            return fn(*args, **kwargs)

    return inner


@_quiet_matmul
def delineate_dem(
    lat: float,
    lon: float,
    *,
    window_deg: float = 0.5,
    product: str = "cop30",
    snap_px: int = 12,
    min_uparea_km2: float = 1.0,
    max_window_deg: float = 4.0,
    max_memory_gb: float = DEFAULT_MAX_MEMORY_GB,
    streams=None,
    burn_depth_m: float = 20.0,
    progress: bool = True,
    **_,
):
    """Delineate the upstream basin by D8 routing on a Copernicus DEM window.

    Parameters
    ----------
    window_deg
        Half-width of the initial DEM window in degrees. Grown automatically if
        the basin reaches the edge.
    snap_px
        Radius, in pixels, of the search for the true channel cell.
    streams
        Lines to force the flow along, in EPSG:4326: a vector file path, a
        GeoDataFrame, or shapely geometries. Use it where the elevation model
        cannot see the channel -- a culverted urban stream, a canal across a
        divide, a valley the model dams with a road embankment. The flow path
        is then the one supplied rather than the one found, which is recorded
        in the provenance because it changes what the answer means.
    burn_depth_m
        How far the burned cells are lowered. Deeper than the relief it has to
        beat, shallower than a trench the flow cannot leave.
    max_window_deg
        Stop growing at this half-width and raise instead of silently
        downloading the continent.
    max_memory_gb
        Refuse, with the figure named, rather than attempt a routing window
        whose estimated peak memory exceeds this. Above roughly 10,000 km2 the
        window needed is large enough for that estimate to matter; below it,
        this never comes up.
    """
    pyflwdir = _require_pyflwdir()
    from shapely.geometry import shape
    from shapely.ops import unary_union

    from ..sources.dem import dem as fetch_dem

    half = window_deg
    while True:
        # Checked before the download, not after: a window too large to route
        # is also too large to be worth fetching, and the old order spent the
        # transfer first and was killed second.
        planned = int(round(2 * half * 3600)) ** 2
        if _estimated_gb(planned) > max_memory_gb:
            raise _refuse(planned, half, max_memory_gb)

        bounds = (lon - half, lat - half, lon + half, lat + half)
        elev = fetch_dem(bounds=bounds, product=product, clip=False, progress=progress)
        elev = elev.squeeze()

        arr = np.asarray(elev.values, dtype="float32")
        if not np.isfinite(arr).any():
            raise DelineationError(
                f"DEM window around ({lat}, {lon}) is entirely nodata -- an "
                "ocean-only extent, or outside the product's coverage."
            )
        arr = np.where(np.isfinite(arr), arr, -9999.0)

        transform = elev.rio.transform()

        burn_record = {"burned": False}
        if streams is not None:
            from ..condition import burn_streams

            arr, burn_record = burn_streams(
                arr, transform, streams, depth_m=burn_depth_m)
        # outlets='edge', not 'min'. With outlets='min' pyflwdir routes the
        # whole window toward its single lowest cell, which on a cropped DEM
        # drags the network away from the real channels -- a river with
        # thousands of km2 upstream can end up with a fraction of a km2 of
        # accumulation. 'edge' lets flow leave wherever it reaches the boundary,
        # which is what a window cut out of a larger landscape actually does.
        flw = pyflwdir.from_dem(
            data=arr, nodata=-9999.0, transform=transform, latlon=True,
            outlets="edge",
        )
        uparea = flw.upstream_area(unit="km2")

        xs = np.asarray(elev.x.values)
        ys = np.asarray(elev.y.values)
        col0 = int(np.abs(xs - lon).argmin())
        row0 = int(np.abs(ys - lat).argmin())

        row, col, snapped_area = _snap_to_stream(
            flw, uparea, row0, col0, search_px=snap_px, min_uparea_km2=min_uparea_km2
        )
        snap_px_moved = int(max(abs(row - row0), abs(col - col0)))

        mask = flw.basins(idxs=np.array([row * flw.shape[1] + col]))
        mask = (mask > 0).astype("uint8")

        if mask.sum() == 0:
            raise DelineationError("Flow routing produced an empty basin.")

        touches_edge = bool(
            mask[0, :].any() or mask[-1, :].any() or mask[:, 0].any() or mask[:, -1].any()
        )
        if touches_edge and half < max_window_deg:
            half *= 2
            nxt = int(round(2 * half * 3600)) ** 2
            warnings.warn(
                f"The basin reaches the edge of the window, so it is being "
                f"doubled to {2 * half:.1f} degrees -- "
                f"{nxt / 1e6:,.0f} megapixels, about "
                f"{_estimated_gb(nxt):.1f} GB. A basin that needs this much "
                "window is at the upper end of what the DEM backend is for; "
                "backend='hydrobasins' costs neither.",
                stacklevel=2)
            continue
        break

    if touches_edge:
        raise DelineationError(
            f"The basin still reaches the edge of a {2 * half:.1f} degree DEM window. "
            "It is too large for the DEM backend -- use backend='hydrobasins', "
            "which handles any size."
        )

    from rasterio.features import shapes as rio_shapes

    geoms = [
        shape(geom)
        for geom, val in rio_shapes(mask, mask=mask.astype(bool), transform=transform)
        if val == 1
    ]
    if not geoms:
        raise DelineationError("Could not vectorise the delineated basin mask.")

    geom = unary_union(geoms).buffer(0)

    from ..clip import basin_area_km2

    return geom, {
        "backend": "dem",
        "source_dataset": f"{product} via D8 routing (pyflwdir)",
        "outlet": (lat, lon),
        "conditioning": burn_record,
        "snapped_outlet": (float(ys[row]), float(xs[col])),
        "snap_distance_px": snap_px_moved,
        "flow_accum_at_outlet_km2": round(float(snapped_area), 3),
        "window_deg": half * 2,
        "window_megapixels": round(arr.size / 1e6, 1),
        "estimated_peak_gb": round(_estimated_gb(arr.size), 2),
        "area_km2": round(basin_area_km2(geom), 3),
        "license": "Copernicus DEM free-and-open licence",
    }
