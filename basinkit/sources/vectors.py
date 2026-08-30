"""Hydrography vectors from HydroSHEDS: rivers and lakes inside the basin."""

from __future__ import annotations

import zipfile

from ..cache import download, subdir
from ..exceptions import DataSourceError

RIVERS = "https://data.hydrosheds.org/file/hydrorivers"
LAKES = "https://data.hydrosheds.org/file/hydrolakes"

RIVER_REGIONS = ("af", "ar", "as", "au", "eu", "gr", "na", "sa", "si")


def _unpack(url: str, name: str, namespace: str, *, progress: bool = True):
    target = subdir(namespace) / name
    existing = list(target.glob("*.shp"))
    if existing:
        return existing[0]
    zpath = download(
        url, namespace=namespace, progress=progress, timeout=900,
        expected_min_bytes=1 << 20,
    )
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zpath) as zf:
        zf.extractall(target)
    found = list(target.rglob("*.shp"))
    if not found:
        raise DataSourceError(f"No shapefile inside {url}")
    return found[0]


def hydrorivers(geometry, region: str | None = None, *, min_order: int = 0,
                progress: bool = True):
    """River reaches intersecting the basin, with discharge and stream order.

    ``ORD_STRA`` is Strahler order; ``DIS_AV_CMS`` is long-term average
    discharge. Filtering on ``min_order`` is the quick way to get a drawable
    main-stem network out of 8.5 million global reaches.
    """
    import geopandas as gpd

    if region is None:
        from ..delineate.hydrobasins import candidate_regions

        cx, cy = geometry.centroid.x, geometry.centroid.y
        region = candidate_regions(cy, cx)[0]

    shp = _unpack(
        f"{RIVERS}/HydroRIVERS_v10_{region}_shp.zip",
        f"HydroRIVERS_v10_{region}", "hydrorivers", progress=progress,
    )
    gdf = gpd.read_file(shp, bbox=geometry.bounds)
    if len(gdf):
        gdf = gdf[gdf.intersects(geometry)].copy()
    if min_order and "ORD_STRA" in gdf.columns:
        gdf = gdf[gdf["ORD_STRA"] >= min_order]
    gdf.attrs["license"] = "CC BY 4.0"
    return gdf


def hydrolakes(geometry, *, min_area_km2: float = 0.0, progress: bool = True):
    """Lakes and reservoirs inside the basin (HydroLAKES, >10 ha).

    The download is a single 820 MB global file, so the first call is slow and
    every later one is instant.
    """
    import geopandas as gpd

    shp = _unpack(
        f"{LAKES}/HydroLAKES_polys_v10_shp.zip", "HydroLAKES_v10",
        "hydrolakes", progress=progress,
    )
    gdf = gpd.read_file(shp, bbox=geometry.bounds)
    if len(gdf):
        gdf = gdf[gdf.intersects(geometry)].copy()
    if min_area_km2 and "Lake_area" in gdf.columns:
        gdf = gdf[gdf["Lake_area"] >= min_area_km2]
    gdf.attrs["license"] = "CC BY 4.0"
    return gdf
