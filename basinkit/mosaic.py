"""Tile mosaicking with a hard ceiling on how much comes into memory.

The naive version of this -- merge every tile at native resolution, then clip --
is fine for a 200 km2 catchment and fatal for a 50,000 km2 one. ESA WorldCover
over the Koshi basin is nine tiles and a five-degree extent; at 10 m that is
about 2.5 billion pixels, which no laptop will hold.

So the mosaic is budgeted. basinkit estimates the output size first and, if it
exceeds ``max_pixels``, coarsens by an integer factor and records that in the
array's attributes. Nearest-neighbour resampling is used for categorical layers
so class codes are never averaged into meaningless intermediates.
"""

from __future__ import annotations

import math
import warnings
from pathlib import Path

import numpy as np

#: Roughly 800 MB as float64, or 100 MB as uint8. Comfortable on a laptop.
DEFAULT_MAX_PIXELS = 100_000_000


def estimate_pixels(bounds, res: float) -> int:
    w, s, e, n = bounds
    return int(math.ceil((e - w) / res) * math.ceil((n - s) / res))


def merge_tiles(
    paths: list[Path],
    bounds: tuple[float, float, float, float],
    *,
    max_pixels: int = DEFAULT_MAX_PIXELS,
    categorical: bool = False,
    nodata_below: float | None = None,
    src_nodata: float | None = None,
):
    """Merge tiles into one DataArray, coarsening if the result would be huge.

    Returns
    -------
    (xarray.DataArray, dict)
        The mosaic, and a dict describing whether and by how much it was
        coarsened. The caller writes that into ``.attrs`` so the decision is
        visible in the output rather than silent.
    """
    import rasterio
    import rioxarray  # noqa: F401
    import xarray as xr
    from rasterio.enums import Resampling
    from rasterio.merge import merge

    srcs = [rasterio.open(p) for p in paths]
    try:
        native_res = abs(srcs[0].transform.a)
        want = estimate_pixels(bounds, native_res)

        factor = 1
        if want > max_pixels:
            factor = int(math.ceil(math.sqrt(want / max_pixels)))
        res = native_res * factor

        if factor > 1:
            warnings.warn(
                f"This extent is {want / 1e6:.0f} megapixels at native "
                f"{native_res * 111_320:.0f} m resolution, above the "
                f"{max_pixels / 1e6:.0f} Mpx budget. Coarsening {factor}x to "
                f"~{res * 111_320:.0f} m. Pass max_pixels= to change this, or "
                "work on a sub-basin to keep native resolution.",
                stacklevel=3,
            )

        # Several products use a sentinel value (255 in JRC surface water, 0 in
        # WorldCover) without declaring it as nodata in the file header.
        # rasterio only masks what a dataset calls nodata, so an averaging
        # resample happily blends the sentinel into real values -- a
        # water-occurrence grid that must top out at 100% comes back with
        # pixels at 101, and every basin mean is slightly wrong. Nearest-
        # neighbour never mixes two values, so it is used whenever the sentinel
        # is undeclared. Averaging is kept where nodata is declared properly
        # (the DEMs), because there it is the better downsampler.
        undeclared = src_nodata is not None and any(s_.nodata is None for s_ in srcs)
        resampling = (
            Resampling.nearest
            if (categorical or undeclared)
            else Resampling.average
        )

        merge_kwargs = {}
        if src_nodata is not None:
            merge_kwargs["nodata"] = src_nodata

        arr, transform = merge(
            srcs, bounds=bounds, res=(res, res), resampling=resampling,
            **merge_kwargs,
        )
        crs = srcs[0].crs
    finally:
        for handle in srcs:
            handle.close()

    ny, nx = arr.shape[-2], arr.shape[-1]
    xs = transform.c + transform.a * (np.arange(nx) + 0.5)
    ys = transform.f + transform.e * (np.arange(ny) + 0.5)

    da = xr.DataArray(
        arr if categorical else arr.astype("float32"),
        dims=("band", "y", "x"),
        coords={"band": np.arange(1, arr.shape[0] + 1), "y": ys, "x": xs},
    ).rio.write_crs(crs)

    if nodata_below is not None:
        da = da.where(da > nodata_below)
    if src_nodata is not None and not categorical:
        da = da.where(da != src_nodata)

    return da, {
        "basinkit_resampling": resampling.name,
        "basinkit_native_res_m": round(native_res * 111_320, 1),
        "basinkit_output_res_m": round(res * 111_320, 1),
        "basinkit_coarsen_factor": factor,
        "basinkit_tiles_merged": len(paths),
    }
