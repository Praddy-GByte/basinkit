"""Machine-readable catalogue of the open datasets basinkit can fetch.

Every entry records not just *where* the data lives but the two facts that
decide whether a pipeline is reproducible: whether an account is needed, and
what the licence permits. ``basinkit.catalog.table()`` prints it; the CLI and
``Basin.license_report()`` read from the same dict, so the documentation can
never drift from the code.

Verified live 2026-08-25.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Auth = Literal["none", "account", "key", "gated"]


@dataclass(frozen=True)
class Dataset:
    """One fetchable open dataset."""

    key: str
    name: str
    category: str
    resolution: str
    temporal: str
    coverage: str
    license: str
    auth: Auth
    route: str
    commercial_ok: bool
    redistributable: bool
    notes: str = ""
    citation: str = ""
    extras: tuple[str, ...] = field(default_factory=tuple)
    #: Whether basinkit can actually fetch this, as opposed to merely knowing
    #: about it. A catalogue that lists datasets it cannot deliver is worse
    #: than a shorter one: it reads as a feature list. Entries with
    #: ``implemented=False`` are documented pointers, and asking for one raises
    #: an error that says exactly how to obtain the data by hand.
    implemented: bool = True

    @property
    def clean(self) -> bool:
        """True when the layer is safe to use commercially *and* redistribute."""
        return self.commercial_ok and self.redistributable and self.auth == "none"

    @property
    def how_to_get(self) -> str:
        """Human-readable instructions for a dataset basinkit cannot fetch."""
        lines = [f"{self.name} is catalogued but basinkit cannot fetch it yet.",
                 f"    Access : {self.route}",
                 f"    Licence: {self.license}"]
        if self.auth != "none":
            lines.append(f"    Auth   : {self.auth} required")
        if self.notes:
            lines.append(f"    Note   : {self.notes}")
        lines.append(
            "    Once you have it locally, pass the geometry to "
            "basinkit.clip.clip_raster() to cut it to the basin."
        )
        return "\n".join(lines)


#: Layers enabled by default: global, anonymous, commercially safe, and
#: actually implemented -- a test asserts all four for every key here.
DEFAULT_STACK = (
    "cop30", "cop90", "nasadem",
    "hydrobasins", "hydrorivers", "hydrolakes",
    "worldcover", "esri_lulc",
    "soilgrids",
    "chirps", "terraclimate", "persiann",
    "jrc_gsw",
    "sentinel2", "sentinel1_rtc", "landsat",
)

DATASETS: dict[str, Dataset] = {}


def _reg(ds: Dataset) -> None:
    DATASETS[ds.key] = ds


# --------------------------------------------------------------------------
# Terrain
# --------------------------------------------------------------------------
_reg(Dataset(
    key="cop30", name="Copernicus DEM GLO-30", category="terrain",
    resolution="1 arc-sec (~30 m)", temporal="2011-2015 acquisition, 2021 product",
    coverage="Global minus withheld tiles (e.g. Armenia/Azerbaijan)",
    license="Copernicus DEM free-and-open licence", auth="none",
    route="AWS Open Data s3://copernicus-dem-30m (anonymous COG)",
    commercial_ok=True, redistributable=True,
    notes="Not literally complete: a few national tiles are absent from the public "
          "bucket. basinkit falls back to GLO-90 and then the OpenTopography mirror "
          "for those, and records which source filled each tile.",
    citation="European Space Agency (2021). Copernicus DEM GLO-30.",
))
_reg(Dataset(
    key="cop90", name="Copernicus DEM GLO-90", category="terrain",
    resolution="3 arc-sec (~90 m)", temporal="2011-2015", coverage="Truly global",
    license="Copernicus DEM free-and-open licence", auth="none",
    route="AWS Open Data s3://copernicus-dem-90m (anonymous COG)",
    commercial_ok=True, redistributable=True,
    notes="Gap-filler for GLO-30 holes and the sane choice for basins >100,000 km2.",
))
_reg(Dataset(
    key="nasadem", name="NASADEM HGT v001", category="terrain",
    resolution="1 arc-sec (~30 m)", temporal="Feb 2000 (reprocessed)",
    coverage="60N-56S", license="NASA public domain", auth="none",
    route="OpenTopography S3 mirror (anonymous) or Planetary Computer STAC",
    commercial_ok=True, redistributable=True,
    notes="Best SRTM-lineage DEM: void-filled with ASTER and ICESat, better geolocation.",
))
_reg(Dataset(
    key="srtm30", name="SRTM GL1 v003", category="terrain",
    resolution="1 arc-sec (~30 m)", temporal="Feb 2000", coverage="60N-56S",
    license="NASA public domain", auth="none",
    route="OpenTopography S3 mirror (anonymous)",
    commercial_ok=True, redistributable=True,
    notes="Voids over water and steep terrain. Prefer NASADEM or COP30 unless you "
          "specifically need the original SRTM epoch.",
))
_reg(Dataset(
    key="fabdem", name="FABDEM V1-2", category="terrain",
    resolution="1 arc-sec, bare-earth", temporal="2023", coverage="80N-60S",
    license="CC BY-NC-SA 4.0", auth="gated",
    route="University of Bristol data repository (manual)",
    commercial_ok=False, redistributable=False,
    notes="LICENCE LANDMINE. Non-commercial AND ShareAlike: anything you derive from "
          "it inherits those terms. Opt-in only; basinkit prints the licence before "
          "the first byte is fetched.", extras=("licensed",),
    implemented=False,
))
_reg(Dataset(
    key="merit_hydro", name="MERIT Hydro v1.0.1", category="terrain",
    resolution="3 arc-sec (~90 m)", temporal="2019", coverage="90N-60S",
    license="CC BY-NC 4.0 or ODbL 1.0", auth="gated",
    route="Google Form -> emailed password -> Dropbox (no API exists)",
    commercial_ok=False, redistributable=False,
    notes="Hydrologically conditioned flow direction, HAND and upstream area, and the "
          "best product of its kind. But acquisition cannot be automated and both "
          "licence options poison a permissive package. Opt-in, bring your own copy.",
    extras=("licensed", "byo"),
    implemented=False,
))

# --------------------------------------------------------------------------
# Hydrography vectors
# --------------------------------------------------------------------------
_reg(Dataset(
    key="hydrobasins", name="HydroBASINS v1c (Pfafstetter levels 1-12)",
    category="hydrography", resolution="vector, level 12 median ~130 km2",
    temporal="static", coverage="Global ex-Antarctica", license="CC BY 4.0",
    auth="none", route="https://data.hydrosheds.org/file/hydrobasins/standard/",
    commercial_ok=True, redistributable=True,
    notes="basinkit's default delineation backend: the NEXT_DOWN field makes upstream "
          "aggregation a graph traversal instead of a raster fill.",
    citation="Lehner, B. & Grill, G. (2013). Hydrological Processes 27(15).",
))
_reg(Dataset(
    key="hydrorivers", name="HydroRIVERS v1.0", category="hydrography",
    resolution="vector, 8.5M reaches", temporal="static", coverage="Global",
    license="CC BY 4.0", auth="none",
    route="https://data.hydrosheds.org/file/hydrorivers/",
    commercial_ok=True, redistributable=True,
    notes="Carries discharge and stream order attributes per reach.",
))
_reg(Dataset(
    key="hydrolakes", name="HydroLAKES v1.0", category="hydrography",
    resolution="1.4M lakes >10 ha", temporal="static", coverage="Global",
    license="CC BY 4.0", auth="none",
    route="https://data.hydrosheds.org/file/hydrolakes/",
    commercial_ok=True, redistributable=True,
))
_reg(Dataset(
    key="hydroatlas", name="BasinATLAS / RiverATLAS v1.0", category="hydrography",
    resolution="vector, 281 attributes", temporal="static", coverage="Global",
    license="CC BY 4.0", auth="none",
    route="figshare article 9890531 (resolve file IDs via the anonymous API)",
    commercial_ok=True, redistributable=True,
    notes="281 pre-computed environmental attributes per basin. The fastest way to "
          "characterise a catchment without downloading a single raster.",
))

# --------------------------------------------------------------------------
# Imagery
# --------------------------------------------------------------------------
_reg(Dataset(
    key="sentinel2", name="Sentinel-2 L2A", category="imagery",
    resolution="10/20/60 m", temporal="2015-06-27 to present", coverage="Global",
    license="Copernicus open (attribution)", auth="none",
    route="Earth Search v1 STAC -> s3://sentinel-cogs (fully anonymous COG)",
    commercial_ok=True, redistributable=True,
    notes="The cleanest optical route that exists: no token layer at all.",
    extras=("stac",),
))
_reg(Dataset(
    key="landsat", name="Landsat Collection 2 Level-2 (4/5/7/8/9)", category="imagery",
    resolution="30 m", temporal="1982 to present", coverage="Global",
    license="US public domain", auth="none",
    route="Planetary Computer STAC (anonymous SAS signing)",
    commercial_ok=True, redistributable=True,
    notes="Use Planetary Computer, not Earth Search: the latter points at the "
          "requester-pays usgs-landsat bucket, which silently costs money.",
    extras=("stac",),
))
_reg(Dataset(
    key="sentinel1_rtc", name="Sentinel-1 RTC", category="imagery",
    resolution="10 m gamma-0", temporal="2014-10-10 to present",
    coverage="Global", license="CC BY 4.0", auth="none",
    route="Planetary Computer STAC (anonymous SAS signing)",
    commercial_ok=True, redistributable=True,
    notes="Radiometrically terrain-corrected, so unlike plain GRD it is usable for "
          "flood mapping in relief. Cloud-independent inundation mapping with no account.",
    extras=("stac",),
))
_reg(Dataset(
    key="hls", name="HLS v2.0 (HLSS30 / HLSL30)", category="imagery",
    resolution="30 m harmonised", temporal="2013 to present (2020+ anonymously)",
    coverage="Global land", license="NASA public domain", auth="none",
    route="Planetary Computer STAC for 2020+; NASA Earthdata login before that",
    commercial_ok=True, redistributable=True, extras=("stac",),
))

# --------------------------------------------------------------------------
# Land cover, soil
# --------------------------------------------------------------------------
_reg(Dataset(
    key="worldcover", name="ESA WorldCover v100/v200", category="landcover",
    resolution="10 m, 11 classes", temporal="2020 and 2021 epochs",
    coverage="60S-82.75N", license="CC BY 4.0", auth="none",
    route="s3://esa-worldcover (anonymous COG, 3x3 degree tiles)",
    commercial_ok=True, redistributable=True,
    notes="v100 and v200 use different algorithms. ESA says explicitly they are not "
          "comparable for change detection, so basinkit refuses to difference them.",
))
_reg(Dataset(
    key="esri_lulc", name="ESRI / Impact Observatory 10 m Annual LULC",
    category="landcover", resolution="10 m, 9 classes", temporal="2017-2024",
    coverage="Global", license="CC BY 4.0", auth="none",
    route="Planetary Computer STAC io-lulc-annual-v02",
    commercial_ok=True, redistributable=True,
    notes="The only anonymous annual land-cover time series. Use this, not WorldCover, "
          "when you need change over time.", extras=("stac",),
))
_reg(Dataset(
    key="soilgrids", name="SoilGrids 250 m v2.0", category="soil",
    resolution="250 m, 6 depths", temporal="static", coverage="Global",
    license="CC BY 4.0", auth="none",
    route="ISRIC WCS (maps.isric.org) and REST point query",
    commercial_ok=True, redistributable=True,
    notes="Native CRS is Interrupted Goode Homolosine. basinkit reprojects the request "
          "bbox for you; hand-rolled WCS calls that skip this land in the wrong "
          "hemisphere. wv0033 and wv1500 are field capacity and wilting point.",
))
_reg(Dataset(
    key="jrc_gsw", name="JRC Global Surface Water v1.4", category="water",
    resolution="30 m", temporal="1984-03 to 2021-12", coverage="78N-56S",
    license="CC BY 4.0", auth="none",
    route="storage.googleapis.com/global-surface-water (anonymous, 10x10 deg tiles)",
    commercial_ok=True, redistributable=True,
    notes="This is a pre-reduced 37-year Landsat water stack. It is what most people "
          "spend a week of Earth Engine compute recreating.",
))

# --------------------------------------------------------------------------
# Climate and hydrology forcing
# --------------------------------------------------------------------------
_reg(Dataset(
    key="chirps", name="CHIRPS v3.0", category="climate",
    resolution="0.05 degree", temporal="1981 to near-real-time", coverage="60N-60S",
    license="Public domain", auth="none",
    route="https://data.chc.ucsb.edu/products/CHIRPS/v3.0/ (anonymous)",
    commercial_ok=True, redistributable=True,
    notes="v3.0 is gauge-undercatch corrected and systematically wetter than v2.0. "
          "basinkit refuses to concatenate v2 and v3 into one series.",
))
_reg(Dataset(
    key="persiann", name="PERSIANN-CDR v1r1", category="climate",
    resolution="0.25 degree, daily", temporal="1983-01-01 to present",
    coverage="60N-60S", license="No constraints on access or use", auth="none",
    route="NOAA NCEI ERDDAP griddap (server-side spatial and temporal subsetting)",
    commercial_ok=True, redistributable=True,
    notes="Underused: ERDDAP subsets server-side, so a 40-year basin series is one "
          "small request rather than a terabyte of tiles.",
))
_reg(Dataset(
    key="terraclimate", name="TerraClimate", category="climate",
    resolution="1/24 degree (~4 km), monthly", temporal="1958 to present",
    coverage="Global land", license="CC0-1.0", auth="none",
    route="climate.northwestknowledge.net (anonymous NetCDF)",
    commercial_ok=True, redistributable=True,
    notes="Carries q (runoff), aet, pet, def and soil moisture, so a first-order water "
          "balance needs no other source. CC0: the most permissive licence in the catalogue.",
))
_reg(Dataset(
    key="era5_land", name="ERA5-Land", category="climate",
    resolution="0.1 degree (~9 km), hourly", temporal="1950 to present (~6 day lag)",
    coverage="Global", license="CC BY 4.0", auth="account",
    route="Copernicus CDS via cdsapi (ECMWF account + personal access token)",
    commercial_ok=True, redistributable=True,
    notes="Requires a free account and a one-time manual licence click per dataset, "
          "and requests are queued for minutes to hours. Never put it on a synchronous "
          "path. Use reanalysis-era5-land-timeseries for point extraction: far faster "
          "than gridded pulls.", extras=("account",),
    implemented=False,
))
_reg(Dataset(
    key="imerg", name="GPM IMERG V07", category="climate",
    resolution="0.1 degree, 30-min", temporal="1998-06 to present", coverage="Global",
    license="CC BY 4.0", auth="account",
    route="NASA earthaccess (Earthdata Login)",
    commercial_ok=True, redistributable=True,
    notes="The Planetary Computer mirror is abandoned and returns zero items. Go "
          "through NASA.", extras=("account",),
    implemented=False,
))
_reg(Dataset(
    key="glofas", name="GloFAS v4 (CEMS-Floods)", category="hydrology",
    resolution="0.05 degree river network, daily", temporal="1979 to present",
    coverage="70N-70S", license="CEMS-Floods licence", auth="account",
    route="CEMS Early Warning Data Store (ewds.climate.copernicus.eu/api)",
    commercial_ok=True, redistributable=False,
    notes="Moved off the main CDS. Needs its own ECMWF token, separate from ERA5. "
          "Pre-migration code fails with 'dataset not found'.", extras=("account",),
    implemented=False,
))
_reg(Dataset(
    key="grdc", name="GRDC river discharge", category="hydrology",
    resolution="~10,000 stations", temporal="1806 to present", coverage="Global",
    license="GRDC terms: no commercial use, no redistribution at all", auth="gated",
    route="Web portal order form only. No API exists.",
    commercial_ok=False, redistributable=False,
    notes="The strictest licence here: you may not cache it, ship it, or put it in a "
          "demo notebook. basinkit will locate the nearest stations and hand you the "
          "order link, and will not touch the values.", extras=("licensed", "byo"),
    implemented=False,
))
_reg(Dataset(
    key="grace", name="GRACE / GRACE-FO mascons RL06.3", category="hydrology",
    resolution="0.5 degree grid (~300 km effective)", temporal="2002-04 to present",
    coverage="Global", license="NASA public domain", auth="account",
    route="JPL PO.DAAC via earthaccess (Earthdata Login). The CSR anonymous "
          "mirror was unreachable when this was last checked.",
    commercial_ok=True, redistributable=True,
    notes="Effective resolution is ~300 km, so it is meaningless below roughly "
          "200,000 km2. Apply the provided scale factors and subtract the GIA "
          "correction or the storage anomalies will be wrong.",
    extras=("account",), implemented=False,
))


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def get(key: str) -> Dataset:
    try:
        return DATASETS[key]
    except KeyError:
        raise KeyError(
            f"Unknown dataset {key!r}. Available: {', '.join(sorted(DATASETS))}"
        ) from None


def by_category(category: str) -> list[Dataset]:
    return [d for d in DATASETS.values() if d.category == category]


def implemented() -> list[Dataset]:
    """Datasets basinkit can actually fetch today."""
    return [d for d in DATASETS.values() if d.implemented]


def unimplemented() -> list[Dataset]:
    """Datasets basinkit documents but cannot fetch."""
    return [d for d in DATASETS.values() if not d.implemented]


def require(key: str) -> Dataset:
    """Return a dataset, raising with instructions if it cannot be fetched."""
    from .exceptions import NotImplementedSource

    ds = get(key)
    if not ds.implemented:
        raise NotImplementedSource(ds.how_to_get)
    return ds


def anonymous() -> list[Dataset]:
    """Datasets needing no account of any kind."""
    return [d for d in DATASETS.values() if d.auth == "none"]


def needs_account() -> list[Dataset]:
    return [d for d in DATASETS.values() if d.auth in ("account", "key", "gated")]


def table(datasets: list[Dataset] | None = None) -> str:
    """Render the catalogue as a plain-text table."""
    rows = datasets if datasets is not None else list(DATASETS.values())
    rows = sorted(rows, key=lambda d: (d.category, d.key))
    head = f"{'key':<14} {'category':<12} {'auth':<8} {'comm':<5} {'fetch':<6} {'name'}"
    lines = [head, "-" * len(head)]
    for d in rows:
        lines.append(
            f"{d.key:<14} {d.category:<12} {d.auth:<8} "
            f"{'yes' if d.commercial_ok else 'NO':<5} "
            f"{'yes' if d.implemented else 'DOC':<6} {d.name}"
        )
    lines.append("")
    lines.append("fetch=DOC means basinkit documents the dataset but cannot download it;")
    lines.append("ask for it and you get instructions rather than a stack trace.")
    return "\n".join(lines)
