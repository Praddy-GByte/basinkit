"""Forcing a known channel into the elevation model before it is routed.

    streams = "bh_drainage_network.gpkg"
    basin = bk.Basin.from_point(-19.92, -43.94, backend="dem", streams=streams)

A global elevation model knows what the ground surface looks like. It does not
know what is under it. Where a stream has been culverted beneath a city there
is nothing on the surface to see, so flow routing sends the water over the
buildings instead, and the catchment it returns is not the catchment that
drains there. The same happens at a road embankment that dams a valley in the
model, or a canal that crosses a divide.

Burning fixes that by lowering the elevation along a line the user supplies,
so the routing is obliged to follow it. It is the standard answer and it has a
sharp edge worth stating plainly: **burning does not make the channel true, it
makes the model obey you.** A line in the wrong place produces a confident
wrong basin, and nothing downstream will question it. The provenance records
that burning happened, how deep, and over how many cells, so an answer that
was forced can be told apart from one that was found.

What burning cannot fix: a channel whose real path you do not know. If you are
guessing where the culvert runs, the result is a guess with a sharper edge.
"""

from __future__ import annotations

import warnings

import numpy as np

#: Deep enough to dominate the local relief of most urban and lowland terrain
#: without creating a trench the router cannot climb out of at the ends.
DEFAULT_BURN_M = 20.0


def _as_geometries(streams):
    """Accept a path, a GeoDataFrame, a GeoSeries, or shapely geometries."""
    from shapely.geometry.base import BaseGeometry

    if isinstance(streams, (str, bytes)) or hasattr(streams, "__fspath__"):
        import geopandas as gpd

        frame = gpd.read_file(streams)
        if frame.crs is not None and frame.crs.to_epsg() != 4326:
            frame = frame.to_crs("EPSG:4326")
        return list(frame.geometry)

    if hasattr(streams, "geometry") and hasattr(streams, "crs"):
        frame = streams
        if frame.crs is not None and frame.crs.to_epsg() != 4326:
            frame = frame.to_crs("EPSG:4326")
        return list(frame.geometry)

    if isinstance(streams, BaseGeometry):
        return [streams]

    return list(streams)


def _cells_along(line, transform, shape):
    """The grid cells a line passes through, in order along the line.

    Sampled at half a pixel so no cell on the path is skipped, then
    de-duplicated. Order matters: carving walks the path from one end.
    """
    import numpy as np
    from rasterio.transform import rowcol

    px = abs(transform.a)
    n = max(int(line.length / (px / 2)) + 1, 2)
    pts = [line.interpolate(i / (n - 1), normalized=True) for i in range(n)]
    rows, cols = rowcol(transform, [p.x for p in pts], [p.y for p in pts])
    rows = np.asarray(rows)
    cols = np.asarray(cols)
    keep = np.ones(rows.size, bool)
    keep[1:] = (rows[1:] != rows[:-1]) | (cols[1:] != cols[:-1])
    rows = rows[keep]
    cols = cols[keep]
    inside = (rows >= 0) & (rows < shape[0]) & (cols >= 0) & (cols < shape[1])
    return rows[inside], cols[inside]


def burn_streams(elevation, transform, streams, *, depth_m=DEFAULT_BURN_M,
                 drop_m=0.05, all_touched=True):
    """Carve ``streams`` into ``elevation`` so flow is obliged to follow them.

    Lowering every cell on a line by a fixed depth is the obvious thing and it
    does not work: the trench keeps the terrain's own ups and downs, so a line
    crossing a divide still climbs over it, and the router treats the two
    halves as separate hollows and fills them. What forces flow is a path that
    descends the whole way.

    So each line is walked from its lower end, and every cell on it is pushed
    to at least ``drop_m`` below the one before. The result is a continuous
    channel with a gentle, monotonic fall, which the router has to follow.

    Parameters
    ----------
    depth_m
        How far the lower end of each line starts below the surface. The rest
        of the line follows from the descent, not from this.
    drop_m
        The fall enforced from one cell to the next. Small: the point is that
        the channel never climbs, not that it plunges.
    all_touched
        Also lower every cell the line touches, not only those on the carved
        path, so a diagonal channel is continuous on the grid.

    Returns
    -------
    (numpy.ndarray, dict)
        The modified elevation and a record of what was carved.
    """
    from rasterio.features import rasterize

    geoms = []
    for g in _as_geometries(streams):
        if g is None or g.is_empty:
            continue
        if g.geom_type == "MultiLineString":
            geoms.extend(list(g.geoms))
        else:
            geoms.append(g)
    if not geoms:
        raise ValueError(
            "No usable geometry in the streams given to burn. Lines are "
            "expected, in EPSG:4326 or a CRS that declares itself."
        )

    out = elevation.copy()
    valid = np.isfinite(out) & (out > -9000)

    touched = 0
    if all_touched:
        mask = rasterize(
            [(g, 1) for g in geoms], out_shape=elevation.shape,
            transform=transform, fill=0, all_touched=True, dtype="uint8",
        ).astype(bool) & valid
        touched = int(mask.sum())
        out[mask] = out[mask] - float(depth_m)

    carved = 0
    for line in geoms:
        if line.geom_type != "LineString" or line.length == 0:
            continue
        rows, cols = _cells_along(line, transform, elevation.shape)
        if rows.size < 2:
            continue
        ok = valid[rows, cols]
        rows, cols = rows[ok], cols[ok]
        if rows.size < 2:
            continue
        z = out[rows, cols].astype("float64")
        # Walk downhill: start from whichever end sits lower on the surface.
        if z[0] > z[-1]:
            rows, cols, z = rows[::-1], cols[::-1], z[::-1]
        z[0] -= float(depth_m) if not all_touched else 0.0
        for i in range(1, z.size):
            limit = z[i - 1] - float(drop_m)
            if z[i] > limit:
                z[i] = limit
        out[rows, cols] = z.astype(out.dtype)
        carved += int(rows.size)

    if touched == 0 and carved == 0:
        warnings.warn(
            "The streams given to burn fall entirely outside the elevation "
            "window, so nothing was carved and the delineation is the "
            "unmodified one. Check that the lines are in EPSG:4326 and cover "
            "the basin.",
            stacklevel=2,
        )
        return elevation, {"burned": False, "reason": "no overlap"}

    return out, {
        "burned": True,
        "method": "carved to a monotonic descent",
        "burn_depth_m": float(depth_m),
        "drop_per_cell_m": float(drop_m),
        "carved_cells": carved,
        "touched_cells": touched,
        "n_lines": len(geoms),
        "warning": (
            "The flow path was forced along the lines supplied, not found by "
            "the elevation model. This basin is only as right as those lines."
        ),
    }
