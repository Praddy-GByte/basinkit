"""Hydrography vectors from HydroSHEDS: rivers and lakes inside the basin."""

from __future__ import annotations

import warnings as _warnings
import zipfile

from pandas import concat as pd_concat

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

    HydroSHEDS ships one file per region and the regional extents overlap, so
    a point can sit inside more than one. Taking the first candidate returned
    an empty network for basins on a seam: the Magdalena's centroid falls in
    the North American extent, and that file carries none of its reaches. So
    every candidate is consulted until the reaches are found, and a basin that
    crosses a seam is assembled from both sides.
    """
    import geopandas as gpd

    from ..delineate.hydrobasins import REGIONS, candidate_regions

    if region is not None:
        codes = [region.lower()]
    else:
        cx, cy = geometry.centroid.x, geometry.centroid.y
        codes = [r for r in candidate_regions(cy, cx) if r in RIVER_REGIONS]
        if not codes:
            raise DataSourceError(
                "HydroRIVERS publishes no regional file covering "
                f"({cy:.4f}, {cx:.4f})."
            )

    bounds = geometry.bounds

    def _read(code: str):
        shp = _unpack(
            f"{RIVERS}/HydroRIVERS_v10_{code}_shp.zip",
            f"HydroRIVERS_v10_{code}", "hydrorivers", progress=progress,
        )
        gdf = gpd.read_file(shp, bbox=bounds)
        if len(gdf):
            gdf = gdf[gdf.intersects(geometry)].copy()
        return gdf

    def _covers(code: str) -> bool:
        w, s_, e, n = REGIONS[code]
        return w <= bounds[0] and s_ <= bounds[1] and e >= bounds[2] and n >= bounds[3]

    used, frames = [], []
    for code in codes:
        part = _read(code)
        if len(part):
            frames.append(part)
            used.append(code)
        # one region is enough only when it holds the whole basin and has reaches
        if frames and _covers(code):
            break

    if frames:
        gdf = frames[0] if len(frames) == 1 else gpd.GeoDataFrame(
            pd_concat(frames), crs=frames[0].crs
        )
    else:
        gdf = _read(codes[0])
        if not len(gdf):
            _warnings.warn(
                "HydroRIVERS returned no reaches for this basin from "
                f"{', '.join(codes)}. Below about 10 km2 the network carries "
                "no reach at all, so a small headwater catchment is expected "
                "to come back empty.",
                stacklevel=2,
            )

    if min_order and "ORD_STRA" in gdf.columns:
        gdf = gdf[gdf["ORD_STRA"] >= min_order]
    gdf.attrs["license"] = "CC BY 4.0"
    gdf.attrs["basinkit_regions"] = used or codes[:1]
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
