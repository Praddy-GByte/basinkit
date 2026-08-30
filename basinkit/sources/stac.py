"""STAC-backed imagery: Sentinel-2, Landsat, Sentinel-1 RTC, HLS, land cover.

Two catalogues, chosen per collection rather than by preference:

* **Earth Search** (Element 84) for Sentinel-2, because its assets are plain
  COGs on a public bucket with no token layer at all -- the fewest moving parts
  of any optical route in existence.
* **Planetary Computer** for Landsat, Sentinel-1 RTC, HLS and land cover. Its
  SAS tokens are issued to anyone without identifying you, so it stays
  account-free, and it is the only anonymous route to globally terrain-corrected
  Sentinel-1.

Landsat is deliberately *not* taken from Earth Search: those assets live in the
requester-pays ``usgs-landsat`` bucket, so a user without AWS credentials gets
a 403, and a user with them gets a bill.
"""

from __future__ import annotations

import warnings

from ..exceptions import DataSourceError, MissingDependency

EARTH_SEARCH = "https://earth-search.aws.element84.com/v1"
PLANETARY = "https://planetarycomputer.microsoft.com/api/stac/v1"

def asset_scaling(items, bands: list[str] | None = None) -> dict[str, dict]:
    """Read per-band scale, offset and nodata out of the STAC metadata itself.

    Both catalogues publish this in each asset's ``raster:bands`` extension, so
    there is no need to hard-code conversion factors that differ per mission
    and change with processing baseline. Landsat Collection 2 Level-2 uses
    ``scale 2.75e-05, offset -0.2``; Sentinel-2 L2A uses ``scale 0.0001`` with
    an offset that is ``0`` before processing baseline 04.00 and ``-0.1``
    after. Guessing either one produces reflectances that look plausible and
    are wrong by a constant -- reading them is both simpler and safer.
    """
    out: dict[str, dict] = {}
    for item in items:
        props = getattr(item, "properties", {}) or {}
        # Earth Search compensates the Sentinel-2 baseline-04.00 BOA offset in
        # the stored values and says so with this flag, while still publishing
        # the nominal -0.1 in raster:bands. Applying it a second time is how
        # you get negative surface reflectance -- during testing, a red band
        # over a green German catchment came back with a mean of -0.05.
        offset_already_applied = bool(props.get("earthsearch:boa_offset_applied"))
        for name, asset in getattr(item, "assets", {}).items():
            if bands and name not in bands:
                continue
            if name in out:
                continue
            rb = (getattr(asset, "extra_fields", {}) or {}).get("raster:bands")
            if isinstance(rb, list) and rb:
                info = rb[0]
                if "scale" in info or "offset" in info or "nodata" in info:
                    out[name] = {
                        "scale": info.get("scale"),
                        "offset": 0.0 if offset_already_applied else info.get("offset"),
                        "nodata": info.get("nodata"),
                        "offset_already_applied": offset_already_applied,
                    }
        if bands and len(out) >= len(bands):
            break
    return out


#: Fallback nodata sentinel per collection, used only when the STAC metadata
#: does not declare one. Optical products encode "no observation" as
#: 0, which is a perfectly ordinary number -- so a median over time treats it
#: as a very dark pixel and drags the composite toward black wherever a scene
#: did not cover the basin. Since a basin usually straddles several MGRS or WRS
#: tiles, most items cover only a fraction of the extent, and the effect is
#: severe rather than marginal: an unmasked Sentinel-2 median over one basin
#: came back 87% zero. These values are converted to NaN on load.
NODATA = {
    "sentinel2": 0,
    "sentinel2_c1": 0,
    "landsat": 0,
    "hls_s30": -9999,
    "hls_l30": -9999,
    "sentinel1_rtc": None,   # already float32 with NaN
    "esri_lulc": None,       # categorical: 0 is a real class
}

#: Pixel budget per collection. The default suits optical COGs; Sentinel-1 RTC
#: gets a much lower one because its scenes are float32 at 10 m over
#: 20,000-by-30,000-pixel frames, so a byte of RTC costs far more network time
#: than a byte of Sentinel-2. Measured on a 1,555 km2 basin: 30 m took 12
#: seconds, 10 m did not finish in three minutes. Pass max_pixels or
#: resolution explicitly to override.
PIXEL_BUDGET = {
    "sentinel1_rtc": 8_000_000,
}
DEFAULT_PIXEL_BUDGET = 40_000_000

#: collection key -> (catalogue url, collection id, default bands)
COLLECTIONS = {
    "sentinel2": (EARTH_SEARCH, "sentinel-2-l2a", ["blue", "green", "red", "nir"]),
    "sentinel2_c1": (EARTH_SEARCH, "sentinel-2-c1-l2a", ["blue", "green", "red", "nir"]),
    "landsat": (PLANETARY, "landsat-c2-l2", ["blue", "green", "red", "nir08"]),
    "sentinel1_rtc": (PLANETARY, "sentinel-1-rtc", ["vv", "vh"]),
    "hls_s30": (PLANETARY, "hls2-s30", ["B02", "B03", "B04", "B08"]),
    "hls_l30": (PLANETARY, "hls2-l30", ["B02", "B03", "B04", "B05"]),
    "esri_lulc": (PLANETARY, "io-lulc-annual-v02", ["data"]),
}


def _client(url: str):
    try:
        from pystac_client import Client
    except ImportError as exc:
        raise MissingDependency("pystac-client", "stac") from exc

    if url == PLANETARY:
        try:
            import planetary_computer as pc

            return Client.open(url, modifier=pc.sign_inplace)
        except ImportError as exc:
            raise MissingDependency("planetary-computer", "stac") from exc
    return Client.open(url)


def stac_search(
    collection: str,
    geometry=None,
    bbox: tuple[float, float, float, float] | None = None,
    start: str | None = None,
    end: str | None = None,
    *,
    cloud_cover: float | None = None,
    limit: int | None = None,
    query: dict | None = None,
):
    """Search a STAC collection over a basin geometry.

    Note that ``geometry`` is passed to the API as an *intersects* filter, so
    scenes are selected by real overlap with the basin rather than with its
    bounding box.
    """
    if collection not in COLLECTIONS:
        raise ValueError(
            f"Unknown collection {collection!r}. Available: {', '.join(COLLECTIONS)}"
        )
    url, cid, _ = COLLECTIONS[collection]
    client = _client(url)

    kwargs: dict = {"collections": [cid]}
    if geometry is not None:
        from shapely.geometry import mapping

        kwargs["intersects"] = mapping(geometry)
    elif bbox is not None:
        kwargs["bbox"] = list(bbox)
    else:
        raise ValueError("Pass either geometry or bbox.")

    if start or end:
        kwargs["datetime"] = f"{start or '..'}/{end or '..'}"

    filters = dict(query or {})
    if cloud_cover is not None:
        filters["eo:cloud_cover"] = {"lt": cloud_cover}
    if filters:
        kwargs["query"] = filters
    if limit:
        kwargs["max_items"] = limit

    try:
        return list(client.search(**kwargs).items())
    except Exception as exc:
        raise DataSourceError(f"STAC search failed for {cid}: {exc}") from exc


def native_resolution(items, bands: list[str] | None = None) -> float | None:
    """Ground sample distance in metres, read from the item or asset metadata."""
    for item in items:
        for name, asset in getattr(item, "assets", {}).items():
            if bands and name not in bands:
                continue
            rb = (getattr(asset, "extra_fields", {}) or {}).get("raster:bands")
            if isinstance(rb, list) and rb and rb[0].get("spatial_resolution"):
                return float(rb[0]["spatial_resolution"])
        gsd = (getattr(item, "properties", {}) or {}).get("gsd")
        if gsd:
            return float(gsd)
    return None


def _budget_resolution(geometry, items, bands, max_pixels: int):
    """Coarsen the request when a basin at native resolution would not fit.

    The mosaic path has had this since a 10 m land-cover request over the Koshi
    tried to allocate 1.3 billion pixels. The STAC path needs it just as much,
    and arguably more: Sentinel-2 is 10 m across four bands and a time
    dimension, so a perfectly reasonable-sounding request over a few thousand
    square kilometres is several gigabytes before anything has been reduced.
    """
    import math

    native = native_resolution(items, bands)
    if native is None or geometry is None:
        return None, {}

    w, s_, e, n = geometry.bounds
    lat = (s_ + n) / 2
    width_m = (e - w) * 111_320 * math.cos(math.radians(lat))
    height_m = (n - s_) * 110_540
    want = (width_m / native) * (height_m / native)

    if want <= max_pixels:
        return None, {"basinkit_native_res_m": native, "basinkit_output_res_m": native}

    factor = math.ceil(math.sqrt(want / max_pixels))
    res = native * factor
    warnings.warn(
        f"This basin at {native:.0f} m is about {want / 1e6:.0f} megapixels per band, "
        f"above the {max_pixels / 1e6:.0f} Mpx budget. Requesting {res:.0f} m instead. "
        "Pass max_pixels= to raise the ceiling, or resolution= to choose your own.",
        stacklevel=3,
    )
    return res, {
        "basinkit_native_res_m": native,
        "basinkit_output_res_m": res,
        "basinkit_coarsen_factor": factor,
    }


def stac_stack(
    items,
    geometry=None,
    bands: list[str] | None = None,
    *,
    resolution: float | None = None,
    crs: str = "EPSG:4326",
    chunks: dict | None = None,
    clip: bool = True,
    collection: str | None = None,
    nodata: float | None = None,
    mask_nodata: bool = True,
    scale: bool = True,
    groupby: str | None = "solar_day",
    max_pixels: int | None = None,
):
    """Lazily load STAC items into an xarray cube, clipped to the basin.

    Nothing is read until you compute. The clip happens on the polygon, so a
    dendritic basin does not drag in the two thirds of its bounding box that
    belongs to its neighbours.

    Parameters
    ----------
    groupby
        ``"solar_day"`` (default) merges the several tiles from one satellite
        pass into a single time slice. Without it a basin straddling four MGRS
        tiles produces four mostly-empty time steps per pass, and any
        reduction over time is computed against that padding.
    mask_nodata
        Convert the collection's nodata sentinel to NaN so reductions skip it.
        Leave this on unless you specifically want the raw integer values.
    scale
        Apply the scale and offset the STAC metadata declares, turning stored
        integers into physical units. Without it, Landsat surface reflectance
        comes back as numbers near 9,000 and Sentinel-2 as numbers near 1,000 --
        both perfectly usable if you remember the conversion, and a silent
        factor-of-10,000 error if you do not. What was applied is recorded in
        each variable's attributes.
    """
    try:
        import odc.stac
    except ImportError as exc:
        raise MissingDependency("odc-stac", "stac") from exc

    if not items:
        raise DataSourceError(
            "No STAC items to stack. Widen the date range or relax cloud_cover."
        )

    scaling = asset_scaling(items, bands)
    if nodata is None:
        declared = [v["nodata"] for v in scaling.values() if v.get("nodata") is not None]
        if declared:
            nodata = declared[0]
        elif collection is not None:
            nodata = NODATA.get(collection)

    if max_pixels is None:
        max_pixels = PIXEL_BUDGET.get(collection, DEFAULT_PIXEL_BUDGET)

    budget_meta: dict = {}
    if resolution is None and max_pixels:
        resolution, budget_meta = _budget_resolution(
            geometry, items, bands, max_pixels
        )

    kwargs: dict = {"chunks": chunks or {"x": 2048, "y": 2048}}
    if bands:
        kwargs["bands"] = bands
    if resolution:
        kwargs["resolution"] = resolution
    if geometry is not None:
        kwargs["geopolygon"] = geometry
    if groupby:
        kwargs["groupby"] = groupby
    if mask_nodata and nodata is not None:
        # Loading straight to float32 with a NaN fill is what makes the
        # sentinel disappear from every later reduction.
        kwargs["dtype"] = "float32"
        kwargs["nodata"] = float("nan")

    ds = odc.stac.load(items, **kwargs)

    if mask_nodata and nodata is not None:
        ds = ds.where(ds != nodata)

    if scale and scaling:
        for name in list(ds.data_vars):
            info = scaling.get(name)
            if not info:
                continue
            factor, offset = info.get("scale"), info.get("offset")
            if factor in (None, 1) and offset in (None, 0):
                continue
            ds[name] = ds[name] * (factor or 1.0) + (offset or 0.0)
            ds[name].attrs.update(
                {
                    "basinkit_scale_applied": factor,
                    "basinkit_offset_applied": offset,
                    "units": "surface reflectance (0-1)",
                }
            )

    ds.attrs.update(budget_meta)

    if clip and geometry is not None:
        from ..clip import clip_raster

        ds = clip_raster(ds, geometry, crs=crs)
    return ds


def composite(ds, method: str = "median", dim: str = "time"):
    """Reduce a time cube to a single cloud-suppressed scene.

    Median over time is the standard trick: an individual cloud is bright and
    transient, so it loses to the clear-sky majority at each pixel, without
    needing a cloud mask at all. It only works if nodata is genuinely absent
    rather than encoded as zero -- see ``mask_nodata`` in :func:`stac_stack`.
    """
    if dim not in ds.dims:
        return ds
    out = getattr(ds, method)(dim=dim, skipna=True)
    out.attrs.update({**ds.attrs, "basinkit_composite": f"{method} over {dim}"})
    return out
