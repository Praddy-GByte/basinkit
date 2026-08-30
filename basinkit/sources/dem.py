"""Digital elevation models from anonymous cloud mirrors.

Every route here is account-free. That is a deliberate constraint: the
OpenTopography *API* is excellent but capped at 50 calls a day for
non-academic keys, which is unusable as a package default, so basinkit reads
from the same data on its anonymous S3 mirror and keeps the API as an
explicit opt-in.

Copernicus GLO-30 is not quite as global as its documentation implies -- a
handful of national tiles are withheld from the public AWS bucket. Rather than
returning a hole, ``dem()`` falls back per tile (GLO-30 to GLO-90 to
OpenTopography's mirror) and reports in provenance which source filled what.
"""

from __future__ import annotations

import math
from pathlib import Path

from ..cache import download
from ..exceptions import DataSourceError

COP30 = "https://copernicus-dem-30m.s3.amazonaws.com"
COP90 = "https://copernicus-dem-90m.s3.amazonaws.com"
OT = "https://opentopography.s3.sdsc.edu/raster"

PRODUCTS = ("cop30", "cop90", "nasadem", "srtm30")


def _ns(lat: int) -> str:
    return f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}"


def _ew(lon: int) -> str:
    return f"{'E' if lon >= 0 else 'W'}{abs(lon):03d}"


def tile_url(product: str, lat: int, lon: int) -> str:
    """URL of the 1x1 degree tile whose south-west corner is (lat, lon)."""
    if product == "cop30":
        stem = f"Copernicus_DSM_COG_10_{_ns(lat)}_00_{_ew(lon)}_00_DEM"
        return f"{COP30}/{stem}/{stem}.tif"
    if product == "cop90":
        stem = f"Copernicus_DSM_COG_30_{_ns(lat)}_00_{_ew(lon)}_00_DEM"
        return f"{COP90}/{stem}/{stem}.tif"
    if product == "nasadem":
        ns = f"{'n' if lat >= 0 else 's'}{abs(lat):02d}"
        ew = f"{'e' if lon >= 0 else 'w'}{abs(lon):03d}"
        return f"{OT}/NASADEM/NASADEM_be/NASADEM_HGT_{ns}{ew}.tif"
    if product == "srtm30":
        return f"{OT}/SRTM_GL1/SRTM_GL1_srtm/{_ns(lat)}{_ew(lon)}.tif"
    raise ValueError(f"Unknown DEM product {product!r}; choose from {PRODUCTS}")


def _tile_corners(bounds: tuple[float, float, float, float]):
    w, s, e, n = bounds
    for lat in range(math.floor(s), math.ceil(n)):
        for lon in range(math.floor(w), math.ceil(e)):
            yield lat, lon


def dem_tiles(
    bounds: tuple[float, float, float, float],
    product: str = "cop30",
    *,
    fallback: bool = True,
    progress: bool = True,
) -> tuple[list[Path], dict]:
    """Download the DEM tiles covering ``bounds`` (west, south, east, north)."""
    chain = [product]
    if fallback and product == "cop30":
        chain += ["cop90", "nasadem"]
    elif fallback and product in ("nasadem", "srtm30"):
        chain += ["cop30", "cop90"]

    paths: list[Path] = []
    used: dict[str, str] = {}
    missing: list[str] = []

    for lat, lon in _tile_corners(bounds):
        label = f"{_ns(lat)}{_ew(lon)}"
        for candidate in chain:
            try:
                paths.append(
                    download(
                        tile_url(candidate, lat, lon),
                        namespace=f"dem/{candidate}",
                        progress=progress,
                        timeout=180,
                        expected_min_bytes=1024,
                    )
                )
                used[label] = candidate
                break
            except DataSourceError:
                continue
        else:
            missing.append(label)

    if not paths:
        raise DataSourceError(
            f"No DEM tiles available for {bounds} from any of {chain}. "
            "If this is an ocean-only extent that is expected."
        )
    return paths, {"tiles_used": used, "tiles_missing": missing, "chain": chain}


def dem(
    geometry=None,
    bounds: tuple[float, float, float, float] | None = None,
    product: str = "cop30",
    *,
    fallback: bool = True,
    clip: bool = True,
    max_pixels: int | None = None,
    progress: bool = True,
):
    """Return a DEM mosaic clipped and masked to ``geometry``.

    Parameters
    ----------
    geometry
        Basin polygon. When given, the result is masked to it, not merely cut
        to its bounding box.
    product
        One of ``cop30``, ``cop90``, ``nasadem``, ``srtm30``.
    fallback
        Fill tiles absent from the primary product from the next source in the
        chain, and record it in ``.attrs['basinkit_tiles_used']``.
    """
    import rioxarray  # noqa: F401

    if bounds is None:
        if geometry is None:
            raise ValueError("Pass either geometry or bounds.")
        bounds = geometry.bounds

    pad = 0.01
    padded = (bounds[0] - pad, bounds[1] - pad, bounds[2] + pad, bounds[3] + pad)
    paths, meta = dem_tiles(padded, product, fallback=fallback, progress=progress)

    from ..mosaic import DEFAULT_MAX_PIXELS, merge_tiles

    da, mosaic_meta = merge_tiles(
        paths, padded, max_pixels=max_pixels or DEFAULT_MAX_PIXELS,
        categorical=False, nodata_below=-1e4,
    )
    meta.update(mosaic_meta)

    da.name = "elevation"
    da.attrs.update(
        {
            "units": "m",
            "vertical_datum": "EGM2008 (Copernicus) / EGM96 (SRTM lineage)",
            "basinkit_product": product,
            "basinkit_tiles_used": str(meta["tiles_used"]),
            "basinkit_tiles_missing": ", ".join(meta["tiles_missing"]) or "none",
            "basinkit_native_res_m": meta.get("basinkit_native_res_m", ""),
            "basinkit_output_res_m": meta.get("basinkit_output_res_m", ""),
            "basinkit_coarsen_factor": meta.get("basinkit_coarsen_factor", 1),
            "basinkit_resampling": meta.get("basinkit_resampling", ""),
        }
    )

    if clip and geometry is not None:
        from ..clip import clip_raster

        da = clip_raster(da, geometry)
    return da.squeeze()
