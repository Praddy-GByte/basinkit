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

import numpy as np

from ..exceptions import DelineationError, MissingDependency, OutletSnapError


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


def delineate_dem(
    lat: float,
    lon: float,
    *,
    window_deg: float = 0.5,
    product: str = "cop30",
    snap_px: int = 12,
    min_uparea_km2: float = 1.0,
    max_window_deg: float = 4.0,
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
    max_window_deg
        Stop growing at this half-width and raise instead of silently
        downloading the continent.
    """
    pyflwdir = _require_pyflwdir()
    from shapely.geometry import shape
    from shapely.ops import unary_union

    from ..sources.dem import dem as fetch_dem

    half = window_deg
    while True:
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
        "snapped_outlet": (float(ys[row]), float(xs[col])),
        "snap_distance_px": snap_px_moved,
        "flow_accum_at_outlet_km2": round(float(snapped_area), 3),
        "window_deg": half * 2,
        "area_km2": round(basin_area_km2(geom), 3),
        "license": "Copernicus DEM free-and-open licence",
    }
