"""SoilGrids 250 m via the ISRIC Web Coverage Service.

The classic SoilGrids bug is the CRS. Its native grid is Interrupted Goode
Homolosine, not lon/lat, so a WCS request built from a raw lon/lat bbox
silently returns a coverage from somewhere else entirely. basinkit reprojects
the request extent into the Homolosine metres the service expects, then
reprojects the result back.
"""

from __future__ import annotations

from ..cache import download
from ..exceptions import DataSourceError

WCS = "https://maps.isric.org/mapserv"
REST = "https://rest.isric.org/soilgrids/v2.0/properties/query"

HOMOLOSINE = (
    "+proj=igh +lat_0=0 +lon_0=0 +datum=WGS84 +units=m +no_defs"
)

PROPERTIES = {
    "clay": "Clay content (g/kg)",
    "sand": "Sand content (g/kg)",
    "silt": "Silt content (g/kg)",
    "bdod": "Bulk density (cg/cm3)",
    "soc": "Soil organic carbon (dg/kg)",
    "nitrogen": "Nitrogen (cg/kg)",
    "cec": "Cation exchange capacity (mmol(c)/kg)",
    "phh2o": "pH in water (pH*10)",
    "cfvo": "Coarse fragments (cm3/dm3)",
    "ocd": "Organic carbon density (hg/m3)",
    "wv0010": "Water content at 10 kPa (0.1 v%)",
    "wv0033": "Water content at 33 kPa - field capacity (0.1 v%)",
    "wv1500": "Water content at 1500 kPa - wilting point (0.1 v%)",
}

DEPTHS = ("0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm", "100-200cm")

#: The two that matter most for rainfall-runoff modelling: the plant-available
#: water capacity of the soil column is wv0033 minus wv1500.
HYDRO_PROPERTIES = ("wv0033", "wv1500", "clay", "sand", "bdod")


def soilgrids(
    geometry,
    prop: str = "clay",
    depth: str = "0-5cm",
    stat: str = "mean",
    *,
    clip: bool = True,
):
    """Fetch one SoilGrids property/depth, clipped to the basin."""
    if prop not in PROPERTIES:
        raise ValueError(
            f"Unknown property {prop!r}. Available: {', '.join(PROPERTIES)}"
        )
    if depth not in DEPTHS:
        raise ValueError(f"Unknown depth {depth!r}. Available: {', '.join(DEPTHS)}")

    import geopandas as gpd

    gdf = gpd.GeoDataFrame(geometry=[geometry], crs="EPSG:4326").to_crs(HOMOLOSINE)
    xmin, ymin, xmax, ymax = gdf.total_bounds
    pad = 500.0

    coverage = f"{prop}_{depth}_{stat}"
    url = (
        f"{WCS}?map=/map/{prop}.map&SERVICE=WCS&VERSION=2.0.1"
        f"&REQUEST=GetCoverage&COVERAGEID={coverage}"
        f"&FORMAT=GEOTIFF_INT16"
        f"&SUBSET=X({xmin - pad},{xmax + pad})"
        f"&SUBSET=Y({ymin - pad},{ymax + pad})"
        f"&SUBSETTINGCRS=http://www.opengis.net/def/crs/EPSG/0/152160"
        f"&OUTPUTCRS=http://www.opengis.net/def/crs/EPSG/0/152160"
    )

    path = download(
        url, namespace="soilgrids", timeout=300, expected_min_bytes=512, progress=False
    )

    import rioxarray  # noqa: F401

    da = rioxarray.open_rasterio(path, masked=True)
    if da.rio.crs is None:
        da = da.rio.write_crs(HOMOLOSINE)
    da = da.rio.reproject("EPSG:4326")
    da = da.where(da > -32000)
    da.name = prop
    da.attrs.update(
        {
            "long_name": PROPERTIES[prop],
            "depth": depth,
            "statistic": stat,
            "basinkit_product": "SoilGrids 250m v2.0",
            "license": "CC BY 4.0",
        }
    )
    if clip:
        from ..clip import clip_raster

        da = clip_raster(da, geometry)
    return da.squeeze()


def soil_profile(lat: float, lon: float, properties: list[str] | None = None) -> dict:
    """Full soil profile at one point via the ISRIC REST endpoint.

    Much cheaper than a coverage request when you only need the value at a
    gauge or the basin centroid.
    """

    props = properties or list(HYDRO_PROPERTIES)
    params = [("lon", lon), ("lat", lat), ("value", "mean")]
    params += [("property", p) for p in props]
    params += [("depth", d) for d in DEPTHS]

    import requests

    try:
        r = requests.get(REST, params=params, timeout=90,
                         headers={"User-Agent": "basinkit/0.1.0"})
        r.raise_for_status()
        return r.json()
    except requests.RequestException as exc:
        raise DataSourceError(f"SoilGrids point query failed: {exc}") from exc


def available_water_capacity(geometry, depth: str = "0-5cm"):
    """Plant-available water capacity: field capacity minus wilting point.

    Returned in volumetric percent. This is the single most useful soil input
    to a conceptual rainfall-runoff model, and it is not distributed directly --
    it has to be differenced from the two water-retention layers.
    """
    fc = soilgrids(geometry, "wv0033", depth)
    wp = soilgrids(geometry, "wv1500", depth)
    awc = (fc - wp) / 10.0
    # Field capacity below wilting point is physically impossible; where it
    # happens it is prediction noise in one of the two layers, usually on a
    # tile edge or over rock. Clamp rather than propagate a negative capacity
    # into whatever model consumes this.
    awc = awc.where(awc >= 0, 0.0)
    awc.name = "awc"
    awc.attrs.update(
        {
            "long_name": "Plant-available water capacity",
            "units": "volumetric %",
            "definition": "wv0033 (field capacity) - wv1500 (wilting point)",
            "depth": depth,
        }
    )
    return awc
