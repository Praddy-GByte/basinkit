"""Land cover: ESA WorldCover (10 m tiles) and ESRI annual LULC (via STAC)."""

from __future__ import annotations

import math

from ..cache import download
from ..exceptions import DataSourceError

WORLDCOVER_S3 = "https://esa-worldcover.s3.eu-central-1.amazonaws.com"

WORLDCOVER_CLASSES = {
    10: "Tree cover", 20: "Shrubland", 30: "Grassland", 40: "Cropland",
    50: "Built-up", 60: "Bare / sparse vegetation", 70: "Snow and ice",
    80: "Permanent water bodies", 90: "Herbaceous wetland",
    95: "Mangroves", 100: "Moss and lichen",
}

ESRI_CLASSES = {
    1: "Water", 2: "Trees", 4: "Flooded vegetation", 5: "Crops",
    7: "Built area", 8: "Bare ground", 9: "Snow/ice", 10: "Clouds",
    11: "Rangeland",
}


def _wc_tile(lat: int, lon: int, year: int) -> str:
    version = "v100" if year == 2020 else "v200"
    ns = f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}"
    ew = f"{'E' if lon >= 0 else 'W'}{abs(lon):03d}"
    stem = f"ESA_WorldCover_10m_{year}_{version}_{ns}{ew}_Map.tif"
    return f"{WORLDCOVER_S3}/{version}/{year}/map/{stem}"


def worldcover(geometry, year: int = 2021, *, clip: bool = True,
               max_pixels: int | None = None, progress: bool = True):
    """ESA WorldCover 10 m land cover, clipped to the basin.

    WorldCover v100 (2020) and v200 (2021) use different algorithms and ESA
    states they are not comparable for change detection. If you need land cover
    *change*, use :func:`esri_lulc`, which is a consistent annual series.
    """
    if year not in (2020, 2021):
        raise ValueError("ESA WorldCover has only 2020 (v100) and 2021 (v200) epochs.")

    w, s, e, n = geometry.bounds
    # 3x3 degree tiles, indexed by their south-west corner.
    paths = []
    for lat in range(math.floor(s / 3) * 3, math.ceil(n / 3) * 3 + 1, 3):
        for lon in range(math.floor(w / 3) * 3, math.ceil(e / 3) * 3 + 1, 3):
            try:
                paths.append(
                    download(
                        _wc_tile(lat, lon, year), namespace=f"worldcover/{year}",
                        progress=progress, timeout=300, expected_min_bytes=1024,
                    )
                )
            except DataSourceError:
                continue
    if not paths:
        raise DataSourceError(
            f"No WorldCover tiles cover this basin for {year}. Coverage is "
            "60S-82.75N; polar basins are outside it."
        )
    return _mosaic_and_clip(
        paths, geometry, clip,
        name="landcover",
        attrs={"classes": str(WORLDCOVER_CLASSES),
               "basinkit_product": f"ESA WorldCover {year}",
               "license": "CC BY 4.0"},
        categorical=True, max_pixels=max_pixels, src_nodata=0,
    )


def esri_lulc(geometry, year: int = 2024, *, clip: bool = True):
    """ESRI / Impact Observatory 10 m annual land cover (2017-2024) via STAC."""
    from .stac import stac_search, stac_stack

    items = stac_search(
        "esri_lulc", geometry=geometry,
        start=f"{year}-01-01", end=f"{year}-12-31",
    )
    if not items:
        raise DataSourceError(
            f"No ESRI LULC items for {year}. The series covers 2017-2024."
        )
    ds = stac_stack(items, geometry, bands=["data"], clip=clip,
                    collection="esri_lulc")
    ds.attrs.update({"classes": str(ESRI_CLASSES), "license": "CC BY 4.0"})
    return ds


def _mosaic_and_clip(paths, geometry, clip, *, name, attrs, categorical=True,
                     max_pixels=None, nodata_below=None, src_nodata=None):
    from ..mosaic import DEFAULT_MAX_PIXELS, merge_tiles

    da, meta = merge_tiles(
        paths, geometry.bounds,
        max_pixels=max_pixels or DEFAULT_MAX_PIXELS,
        categorical=categorical,
        nodata_below=nodata_below,
        src_nodata=src_nodata,
    )
    da.name = name
    da.attrs.update({**attrs, **meta})
    if clip:
        from ..clip import clip_raster

        da = clip_raster(da, geometry)
    return da.squeeze()


def class_fractions(da, classes: dict[int, str] | None = None) -> dict[str, float]:
    """Fraction of basin area in each land-cover class."""
    import numpy as np

    classes = classes or WORLDCOVER_CLASSES
    vals = np.asarray(da.values).ravel()
    vals = vals[np.isfinite(vals)]
    vals = vals[vals > 0]
    if vals.size == 0:
        return {}
    uniq, counts = np.unique(vals.astype(int), return_counts=True)
    total = counts.sum()
    return {
        classes.get(int(u), f"class {int(u)}"): round(float(c) / total, 4)
        for u, c in sorted(zip(uniq, counts, strict=False), key=lambda t: -t[1])
    }
