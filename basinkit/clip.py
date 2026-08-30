"""Clip and mask rasters to a basin polygon.

This is the part every generic downloader skips. ``eodag``, ``earthaccess``,
``pystac-client`` and friends all take a *bounding box* and give you whole
scenes or tiles. For a river basin that is the wrong shape by a wide margin: a
long dendritic catchment can occupy under a third of its own bbox, so two
thirds of what you download, store and average over belongs to a neighbouring
basin. Everything here works on the polygon.
"""

from __future__ import annotations

import warnings
from typing import Any

import numpy as np


def _as_geoms(geometry: Any) -> list[dict]:
    """Normalise shapely / GeoDataFrame / GeoSeries / mapping into GeoJSON dicts."""
    from shapely.geometry import mapping
    from shapely.geometry.base import BaseGeometry

    if isinstance(geometry, BaseGeometry):
        return [mapping(geometry)]
    if isinstance(geometry, dict):
        return [geometry]
    if hasattr(geometry, "geometry"):  # GeoDataFrame
        return [mapping(g) for g in geometry.geometry]
    if hasattr(geometry, "__geo_interface__"):
        gi = geometry.__geo_interface__
        if gi.get("type") == "FeatureCollection":
            return [f["geometry"] for f in gi["features"]]
        return [gi]
    if isinstance(geometry, (list, tuple)):
        out: list[dict] = []
        for g in geometry:
            out.extend(_as_geoms(g))
        return out
    raise TypeError(f"Cannot interpret {type(geometry)!r} as a geometry")


def clip_raster(
    path_or_ds: Any,
    geometry: Any,
    *,
    crs: str = "EPSG:4326",
    all_touched: bool = False,
    nodata: float | None = None,
    drop_empty: bool = True,
):
    """Open a raster, clip it to ``geometry`` and mask everything outside.

    Parameters
    ----------
    path_or_ds
        File path, URL, or an already-open ``xarray`` object.
    geometry
        Basin polygon in ``crs``.
    all_touched
        Include pixels merely touched by the boundary. Set ``True`` for small
        basins on coarse grids, where strict centroid-in-polygon can return an
        empty array.
    drop_empty
        Raise a helpful error instead of returning an all-nodata array.

    Returns
    -------
    xarray.DataArray
        Clipped to the polygon envelope and masked outside the polygon itself.
    """
    import rioxarray  # noqa: F401  (registers the .rio accessor)
    import xarray as xr

    geoms = _as_geoms(geometry)

    if isinstance(path_or_ds, (xr.DataArray, xr.Dataset)):
        da = path_or_ds
    else:
        da = rioxarray.open_rasterio(str(path_or_ds), masked=True, chunks="auto")

    if da.rio.crs is None:
        da = da.rio.write_crs(crs)

    if str(da.rio.crs).upper() != str(crs).upper():
        import geopandas as gpd
        from shapely.geometry import shape

        gdf = gpd.GeoDataFrame(
            geometry=[shape(g) for g in geoms], crs=crs
        ).to_crs(da.rio.crs)
        from shapely.geometry import mapping

        geoms = [mapping(g) for g in gdf.geometry]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        clipped = da.rio.clip(
            geoms, crs=da.rio.crs, all_touched=all_touched, drop=True, from_disk=True
        )

    if nodata is not None:
        clipped = clipped.rio.write_nodata(nodata)

    if drop_empty and not all_touched and _is_worth_checking(clipped):
        if _all_nodata(clipped):
            # Retry once with all_touched before giving up: this is the classic
            # small-basin-on-a-coarse-grid failure, not a real absence of data.
            return clip_raster(
                path_or_ds, geometry, crs=crs, all_touched=True,
                nodata=nodata, drop_empty=False,
            )
    return clipped


#: Above this many cells the emptiness check costs more than it is worth.
_CHECK_LIMIT = 20_000_000


def _is_worth_checking(obj) -> bool:
    """Whether the empty-result check can run without forcing an expensive load.

    Two things make it a bad idea. A dask-backed cube -- which is what every
    STAC stack is -- would have to be computed in full just to answer the
    question, discarding the laziness that makes those stacks usable at all.
    And even eager arrays get large enough that scanning them for finiteness
    is slower than the clip itself.
    """
    chunks = getattr(obj, "chunks", None)
    if chunks:                      # dask-backed: never force it
        return False
    try:
        arrays = _as_arrays(obj)
        return bool(arrays) and sum(a.size for a in arrays) <= _CHECK_LIMIT
    except Exception:
        return False


def _as_arrays(obj) -> list:
    """DataArray or Dataset in, list of DataArrays out.

    ``Dataset`` has no ``.values`` array -- reaching for one silently picks up
    an unrelated method, which is how a clip that works fine on a single band
    fails on every multi-band STAC result.
    """
    if hasattr(obj, "data_vars"):
        return list(obj.data_vars.values())
    return [obj]


def _all_nodata(obj) -> bool:
    arrays = _as_arrays(obj)
    if not arrays:
        return True
    for a in arrays:
        values = np.asarray(a.values)
        if values.size and np.isfinite(values).any():
            return False
    return True


def clip_stack(da, geometry, *, crs: str = "EPSG:4326", all_touched: bool = False):
    """Clip an already-loaded (possibly multi-temporal) DataArray to a polygon."""
    return clip_raster(da, geometry, crs=crs, all_touched=all_touched)


def zonal_mean(da, geometry=None, *, dims: tuple[str, ...] = ("y", "x")):
    """Area-weighted-ish spatial mean over a clipped array.

    On a geographic grid, pixel area shrinks with ``cos(latitude)``. Ignoring
    that biases a basin mean toward its poleward end. For a small basin the
    error is negligible; for a Nile- or Ob-sized one it is not, so this
    weights by ``cos(lat)`` whenever a latitude coordinate is present.
    """
    if geometry is not None:
        da = clip_raster(da, geometry)

    lat_name = next((n for n in ("y", "lat", "latitude") if n in da.coords), None)
    if lat_name is not None:
        weights = np.cos(np.deg2rad(da[lat_name]))
        weights.name = "weights"
        present = [d for d in dims if d in da.dims]
        return da.weighted(weights.fillna(0)).mean(dim=present, skipna=True)
    return da.mean(dim=[d for d in dims if d in da.dims], skipna=True)


def basin_area_km2(geometry, crs: str = "EPSG:4326") -> float:
    """Area of a lon/lat polygon in km2, via an equal-area projection.

    Computing area in degrees is a common and badly wrong shortcut. This
    reprojects to a Lambert azimuthal equal-area centred on the basin itself,
    which is accurate to well under a percent at catchment scale.
    """
    import geopandas as gpd
    from shapely.geometry import shape

    geoms = [shape(g) for g in _as_geoms(geometry)]
    gdf = gpd.GeoDataFrame(geometry=geoms, crs=crs)
    cx, cy = gdf.union_all().centroid.x, gdf.union_all().centroid.y
    aea = f"+proj=laea +lat_0={cy} +lon_0={cx} +datum=WGS84 +units=m +no_defs"
    return float(gdf.to_crs(aea).area.sum() / 1e6)
