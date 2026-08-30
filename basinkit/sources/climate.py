"""Precipitation and climate, basin-averaged.

All three sources here are anonymous, and each is chosen for a different job:

* **CHIRPS v3.0** -- 0.05 degree, gauge-blended, 1981 to near-real-time. The
  default for basin rainfall in the tropics and subtropics (60N-60S).
* **PERSIANN-CDR** -- served through NOAA's ERDDAP, which subsets *server-side*.
  A 40-year basin series is one small request instead of a terabyte of tiles.
  Underused because almost nobody notices the ERDDAP route exists.
* **TerraClimate** -- monthly water balance (precipitation, PET, AET, runoff,
  soil moisture, deficit) at 4 km, CC0. Read over OPeNDAP so only the basin
  window crosses the network. A first-order water balance needs nothing else.

ERA5-Land and IMERG are better for some purposes but both need an account, so
they live behind explicit opt-in rather than in the default stack.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from ..cache import download, subdir
from ..exceptions import DataSourceError, MissingDependency

CHIRPS = "https://data.chc.ucsb.edu/products/CHIRPS/v3.0"
TERRACLIM_DODS = (
    "https://thredds.northwestknowledge.net/thredds/dodsC/TERRACLIMATE_ALL/data"
)
ERDDAP = "https://www.ncei.noaa.gov/erddap/griddap/cdr_persiann_by_time_lon_lat.nc"

TERRACLIMATE_VARS = {
    "ppt": "Precipitation (mm)",
    "tmax": "Max temperature (degC)",
    "tmin": "Min temperature (degC)",
    "pet": "Reference evapotranspiration (mm)",
    "aet": "Actual evapotranspiration (mm)",
    "def": "Climate water deficit (mm)",
    "q": "Runoff (mm)",
    "soil": "Soil moisture (mm)",
    "swe": "Snow water equivalent (mm)",
    "PDSI": "Palmer Drought Severity Index",
    "vpd": "Vapour pressure deficit (kPa)",
    "srad": "Downward shortwave radiation (W/m2)",
    "ws": "Wind speed (m/s)",
}

#: The variables a monthly water balance actually needs.
WATER_BALANCE_VARS = ("ppt", "aet", "pet", "q", "soil", "def")


def _read_window(url: str, bounds, pad: float = 0.1):
    """Read just the basin window out of a remote COG, over HTTP range requests.

    CHIRPS publishes one global grid per month. Downloading all of them to use a
    basin-sized corner of each is the obvious implementation and roughly a
    hundred times more traffic than necessary: a 25-year monthly series is
    ~300 files of ~10 MB. Reading through GDAL's ``/vsicurl`` fetches only the
    tiles the window overlaps, which turns minutes into seconds and leaves
    nothing on disk.
    """
    import rasterio
    import rioxarray  # noqa: F401
    import xarray as xr
    from rasterio.windows import from_bounds

    w, s_, e, n = bounds
    env = rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".cog,.tif,.tiff",
        GDAL_HTTP_MAX_RETRY="3",
        GDAL_HTTP_RETRY_DELAY="1",
    )
    with env, rasterio.open(f"/vsicurl/{url}") as src:
        win = from_bounds(
            w - pad, s_ - pad, e + pad, n + pad, transform=src.transform
        ).round_offsets().round_lengths()
        arr = src.read(1, window=win, masked=True)
        transform = src.window_transform(win)
        crs = src.crs

    import numpy as np

    ny, nx = arr.shape
    if ny == 0 or nx == 0:
        raise DataSourceError(f"Window is empty for {url}")
    xs = transform.c + transform.a * (np.arange(nx) + 0.5)
    ys = transform.f + transform.e * (np.arange(ny) + 0.5)
    da = xr.DataArray(
        np.asarray(arr.filled(np.nan), dtype="float32"),
        dims=("y", "x"), coords={"y": ys, "x": xs},
    ).rio.write_crs(crs)
    return da.where(da > -9000)


def chirps(
    geometry,
    start: int | str = 2000,
    end: int | str | None = None,
    *,
    freq: str = "monthly",
    aggregate: bool = True,
    progress: bool = True,
):
    """CHIRPS v3.0 rainfall over the basin.

    Read directly from the remote COGs over HTTP range requests, so only the
    basin window travels -- a 25-year series is seconds, not minutes, and
    nothing is written to disk.

    Parameters
    ----------
    aggregate
        ``True`` returns a basin-mean time series (1-D, indexed by time);
        ``False`` returns the clipped grids.

    Notes
    -----
    v3.0 is gauge-undercatch corrected and systematically wetter than v2.0.
    basinkit will not silently splice the two together -- if you need a series
    that spans the change, decide explicitly which version to use throughout.
    """
    import numpy as np
    import xarray as xr

    if freq != "monthly":
        raise NotImplementedError(
            "basinkit 0.1 fetches CHIRPS at monthly resolution. Daily is a much "
            "larger transfer; open an issue if you need it."
        )

    from ..clip import clip_raster, zonal_mean

    start_year = int(str(start)[:4])
    end_year = int(str(end)[:4]) if end else date.today().year
    today = date.today()
    bounds = geometry.bounds

    months = [
        (y, m)
        for y in range(start_year, end_year + 1)
        for m in range(1, 13)
        if not (y == today.year and m > today.month - 1)
    ]

    iterator = months
    if progress and len(months) > 12:
        try:
            from tqdm import tqdm

            iterator = tqdm(months, desc="CHIRPS", unit="month", leave=False)
        except ImportError:
            pass

    grids, times = [], []
    for year, month in iterator:
        url = f"{CHIRPS}/monthly/global/cogs/chirps-v3.0.{year}.{month:02d}.cog"
        try:
            da = _read_window(url, bounds)
            clipped = clip_raster(da, geometry).squeeze()
        except Exception:
            continue
        grids.append(zonal_mean(clipped) if aggregate else clipped)
        times.append(np.datetime64(f"{year}-{month:02d}-01"))

    if not grids:
        raise DataSourceError(
            "No CHIRPS data retrieved. CHIRPS covers 60N-60S -- a basin outside "
            "that band has none. Try TerraClimate, which is global land."
        )

    out = xr.concat(
        grids, dim=xr.DataArray(times, dims="time", name="time")
    )
    out.name = "precipitation"
    out.attrs.update(
        {
            "units": "mm/month",
            "basinkit_product": "CHIRPS v3.0 monthly",
            "basinkit_n_months": len(times),
            "license": "Public domain",
            "citation": "Funk, C. et al. (2015). Scientific Data 2, 150066.",
            "note": "v3.0 is gauge-undercatch corrected and wetter than v2.0.",
        }
    )
    return out


def terraclimate(
    geometry,
    variables: tuple[str, ...] | list[str] = ("ppt", "aet", "pet", "q"),
    start: int = 2000,
    end: int | None = None,
    *,
    aggregate: bool = True,
):
    """TerraClimate monthly water balance over the basin, read via OPeNDAP.

    OPeNDAP means only the basin window travels over the network, not the
    global grid. Returns an ``xarray.Dataset`` with one variable per entry in
    ``variables``.
    """
    try:
        import xarray as xr
    except ImportError as exc:  # pragma: no cover
        raise MissingDependency("xarray", "climate") from exc

    unknown = set(variables) - set(TERRACLIMATE_VARS)
    if unknown:
        raise ValueError(
            f"Unknown TerraClimate variable(s): {', '.join(sorted(unknown))}. "
            f"Available: {', '.join(TERRACLIMATE_VARS)}"
        )

    end = end or date.today().year - 1
    w, s, e, n = geometry.bounds
    pad = 0.05

    from ..clip import clip_raster, zonal_mean

    def _one(var: str, year: int):
        url = f"{TERRACLIM_DODS}/TerraClimate_{var}_{year}.nc"
        try:
            ds = xr.open_dataset(url, decode_times=True)
            sub = ds[var].sel(
                lon=slice(w - pad, e + pad), lat=slice(n + pad, s - pad)
            ).load()
            ds.close()
        except Exception:
            return var, None
        return var, (sub if sub.size else None)

    # One NetCDF per variable per year means a 20-year, six-variable request is
    # 120 sequential OPeNDAP round trips -- minutes of latency and almost no
    # bandwidth. The reads are independent and I/O bound, so a small thread
    # pool collapses that to roughly the time of the slowest one. The pool is
    # deliberately small: this is a university server, not a CDN.
    jobs = [(var, year) for var in variables for year in range(start, end + 1)]
    collected: dict[str, list] = {var: [] for var in variables}
    with ThreadPoolExecutor(max_workers=min(6, len(jobs))) as pool:
        futures = [pool.submit(_one, var, year) for var, year in jobs]
        for fut in as_completed(futures):
            var, sub = fut.result()
            if sub is not None:
                collected[var].append(sub)

    out = {}
    for var in variables:
        yearly = collected[var]
        if not yearly:
            continue
        merged = xr.concat(yearly, dim="time").sortby("time")
        merged = merged.rename({"lon": "x", "lat": "y"}).rio.write_crs("EPSG:4326")
        try:
            merged = clip_raster(merged, geometry)
        except Exception:
            pass
        out[var] = zonal_mean(merged) if aggregate else merged

    if not out:
        raise DataSourceError(
            "TerraClimate returned nothing. The OPeNDAP server occasionally "
            "rejects concurrent requests; retry, or narrow the year range."
        )

    ds = xr.Dataset(out)
    for var in ds.data_vars:
        ds[var].attrs["long_name"] = TERRACLIMATE_VARS[var]
    ds.attrs.update(
        {
            "basinkit_product": "TerraClimate monthly",
            "license": "CC0-1.0",
            "citation": "Abatzoglou, J.T. et al. (2018). Scientific Data 5, 170191.",
        }
    )
    return ds


def _as_date(value, *, end_of_year: bool = False) -> str:
    """Accept 2020, "2020" or "2020-03-01" and return an ISO date."""
    text = str(value)
    if len(text) == 4 and text.isdigit():
        return f"{text}-12-31" if end_of_year else f"{text}-01-01"
    return text


def persiann(
    geometry, start: str | int = "2000-01-01", end: str | int | None = None,
    *, aggregate: bool = True
):
    """PERSIANN-CDR daily rainfall via NOAA ERDDAP (server-side subsetting)."""
    import xarray as xr

    start = _as_date(start)
    end = _as_date(end, end_of_year=True) if end else date.today().strftime("%Y-%m-%d")
    w, s, e, n = geometry.bounds
    pad = 0.25
    # ERDDAP wants 0-360 longitude for this dataset.
    lon0 = (w - pad) % 360
    lon1 = (e + pad) % 360

    query = (
        f"precipitation[({start}T00:00:00Z):({end}T00:00:00Z)]"
        f"[({lon0:.3f}):({lon1:.3f})][({s - pad:.3f}):({n + pad:.3f})]"
    )
    url = f"{ERDDAP}?{query}"
    path = download(
        url, dest=subdir("persiann") / f"persiann_{start}_{end}_{w:.2f}_{s:.2f}.nc",
        timeout=600, progress=True, expected_min_bytes=512,
    )

    ds = xr.open_dataset(path)
    da = ds["precipitation"]
    if "longitude" in da.dims:
        da = da.rename({"longitude": "x", "latitude": "y"})
    elif "lon" in da.dims:
        da = da.rename({"lon": "x", "lat": "y"})
    da = da.assign_coords(x=((da.x + 180) % 360) - 180).sortby("x")
    da = da.rio.write_crs("EPSG:4326")

    from ..clip import clip_raster, zonal_mean

    try:
        da = clip_raster(da, geometry)
    except Exception:
        pass
    if aggregate:
        da = zonal_mean(da)
    da.name = "precipitation"
    da.attrs.update(
        {
            "units": "mm/day",
            "basinkit_product": "PERSIANN-CDR v1r1",
            "license": "No constraints on access or use",
            "citation": "Ashouri, H. et al. (2015). BAMS 96(1), 69-83.",
        }
    )
    return da


def water_balance(geometry, start: int = 2000, end: int | None = None):
    """Monthly basin water balance from TerraClimate, with a closure check.

    Returns the standard terms plus ``residual = ppt - aet - q``. A residual
    that does not hover near zero is not a bug in the arithmetic: it is storage
    change plus the model's own error, and it is worth looking at before you
    trust any of the components.
    """
    ds = terraclimate(geometry, WATER_BALANCE_VARS, start, end, aggregate=True)
    if all(v in ds for v in ("ppt", "aet", "q")):
        ds["residual"] = ds["ppt"] - ds["aet"] - ds["q"]
        ds["residual"].attrs["long_name"] = (
            "P - AET - Q (storage change plus model error, mm)"
        )
    ds["runoff_coefficient"] = (
        ds["q"].sum() / ds["ppt"].sum() if "q" in ds and "ppt" in ds else None
    )
    return ds
