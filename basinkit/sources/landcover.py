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


def _item_year(item) -> int | None:
    """The year an ESRI annual item actually describes."""
    start = (item.properties or {}).get("start_datetime")
    if isinstance(start, str) and len(start) >= 4 and start[:4].isdigit():
        return int(start[:4])
    tail = str(item.id).rsplit("-", 1)[-1]
    return int(tail) if tail.isdigit() and len(tail) == 4 else None


def esri_years(geometry) -> list[int]:
    """Years of ESRI annual land cover actually available over ``geometry``."""
    from .stac import stac_search

    items = stac_search("esri_lulc", geometry=geometry,
                        start="2017-01-01", end="2100-01-01")
    return sorted({y for y in (_item_year(i) for i in items) if y})


def esri_lulc(geometry, year: int | None = None, *, clip: bool = True, **kwargs):
    """ESRI / Impact Observatory 10 m annual land cover, via STAC.

    ``year=None`` takes the most recent year published for this location.
    That is deliberately not a hard-coded number: coverage ends in different
    years in different places, and a constant would quietly rot.

    Extra keywords (``resolution``, ``max_pixels``, ...) pass through to the
    STAC reader, so this takes the same tuning knobs as ``worldcover()``.
    """

    from .stac import stac_search, stac_stack

    available = esri_years(geometry)
    if not available:
        raise DataSourceError(
            "No ESRI annual land cover covers this basin. ESA WorldCover is "
            "global: use landcover(source='worldcover')."
        )
    if year is None:
        year = available[-1]

    items = [i for i in stac_search("esri_lulc", geometry=geometry,
                                    start=f"{year}-01-01", end=f"{year}-12-31")
             if _item_year(i) == year]
    if not items:
        # The previous year's item ends at 00:00 on 1 January, so a naive
        # window for a year with no data matches it and returns the year
        # before -- silently, with an array that looks entirely correct.
        raise DataSourceError(
            f"ESRI annual land cover has no {year} map for this basin. "
            f"Available here: {', '.join(map(str, available))}."
        )

    ds = stac_stack(items, geometry, bands=["data"], clip=clip,
                    collection="esri_lulc", **kwargs)

    names = list(ds.data_vars)
    da = ds[names[0]] if len(names) == 1 else ds["data"]

    if "time" in da.dims and da.sizes["time"] > 1:
        # Adjacent ESRI tiles arrive as separate items and odc-stac stacks them
        # along time. They are spatially complementary, not repeat looks at the
        # same ground, so they are combined first-valid. Averaging class codes
        # would invent classes that do not exist -- the mean of water (1) and
        # trees (2) is not a land cover.
        valid = da.where(da > 0)
        merged = valid.isel(time=0)
        for t in range(1, da.sizes["time"]):
            merged = merged.fillna(valid.isel(time=t))
        da = merged.fillna(0)
    da = da.squeeze(drop=True)

    if da.dtype.kind == "f":
        da = da.astype("uint8")
    da.name = "landcover"
    da.attrs.update({
        **ds.attrs,
        "classes": str(ESRI_CLASSES),
        "basinkit_product": f"ESRI Land Cover {year}",
        "basinkit_year": year,
        "license": "CC BY 4.0",
    })
    return da


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


def _declared_classes(obj) -> dict[int, str] | None:
    """The legend the array is carrying, if it brought one."""
    import ast

    raw = getattr(obj, "attrs", {}).get("classes")
    if not raw:
        return None
    try:
        parsed = ast.literal_eval(raw) if isinstance(raw, str) else raw
    except (ValueError, SyntaxError):
        return None
    if isinstance(parsed, dict) and parsed:
        return {int(k): str(v) for k, v in parsed.items()}
    return None


def class_fractions(da, classes: dict[int, str] | None = None) -> dict[str, float]:
    """Fraction of basin area in each land-cover class.

    The legend is read from the array unless you pass one. That matters more
    than it looks: WorldCover and ESRI number their classes differently, and
    code 10 means "tree cover" in one and "clouds" in the other. Defaulting to
    WorldCover for everything reported ESRI cloud as forest, in a dictionary
    that looked perfectly reasonable.
    """
    import numpy as np

    # A Dataset has no ``.values`` array -- reaching for one picks up the
    # method and every downstream numpy call fails or, worse, does not.
    if hasattr(da, "data_vars"):
        names = list(da.data_vars)
        if len(names) != 1:
            raise ValueError(
                "class_fractions needs one land-cover band; this Dataset has "
                f"{len(names)}: {names}. Select one first."
            )
        da = da[names[0]]
    if hasattr(da, "squeeze"):
        da = da.squeeze(drop=True)

    if classes is None:
        classes = _declared_classes(da) or WORLDCOVER_CLASSES

    vals = np.asarray(da.values).ravel()
    if vals.dtype.kind == "f":                 # isfinite is float-only
        vals = vals[np.isfinite(vals)]
    elif vals.dtype.kind not in "iub":
        raise TypeError(
            f"expected a numeric land-cover raster, got dtype {vals.dtype}"
        )
    vals = vals[vals > 0]
    if vals.size == 0:
        return {}
    uniq, counts = np.unique(vals.astype(int), return_counts=True)
    total = counts.sum()
    return {
        classes.get(int(u), f"class {int(u)}"): round(float(c) / total, 4)
        for u, c in sorted(zip(uniq, counts, strict=False), key=lambda t: -t[1])
    }
