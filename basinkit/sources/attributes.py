"""BasinATLAS: 281 pre-computed environmental attributes per sub-basin.

This is the fastest way to characterise a catchment, and the most overlooked.
BasinATLAS ships climate, physiography, land cover, soil, geology and
anthropogenic variables already summarised per HydroBASINS unit -- and it
carries them in two forms: ``_c`` for the local sub-catchment and ``_u`` for
everything upstream. The upstream form means the row belonging to your outlet
unit is *already* a basin-wide characterisation. No rasters, no zonal
statistics, no reprojection.

The cost is a single 2.7 GB download, once. After that every basin on Earth is
a dictionary lookup.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from ..cache import download, memo_json, subdir
from ..exceptions import DataSourceError

FIGSHARE_ARTICLE = "https://api.figshare.com/v2/articles/9890531"

#: A readable name for each attribute-group prefix. The full definitions are in
#: the HydroATLAS technical documentation.
GROUPS = {
    "dis": "discharge", "run": "land surface runoff", "inu": "inundation extent",
    "lka": "lake area", "lkv": "lake volume", "rev": "reservoir volume",
    "dor": "degree of regulation", "ria": "river area", "riv": "river volume",
    "gwt": "groundwater table depth", "ele": "elevation", "slp": "slope",
    "sgr": "stream gradient", "clz": "climate zone", "cls": "climate strata",
    "tmp": "air temperature", "pre": "precipitation", "pet": "potential ET",
    "aet": "actual ET", "ari": "aridity index", "cmi": "climate moisture index",
    "snw": "snow cover", "glc": "land cover class", "pnv": "potential natural vegetation",
    "wet": "wetland class", "for": "forest cover", "crp": "cropland cover",
    "pst": "pasture cover", "ire": "irrigated area", "gla": "glacier extent",
    "prm": "permafrost extent", "pac": "protected area", "cly": "clay fraction",
    "slt": "silt fraction", "snd": "sand fraction", "soc": "soil organic carbon",
    "swc": "soil water content", "lit": "lithological class", "kar": "karst area",
    "ero": "soil erosion", "pop": "population count", "ppd": "population density",
    "urb": "urban extent", "nli": "night lights", "rdd": "road density",
    "hft": "human footprint", "gad": "country", "gdp": "gross domestic product",
    "hdi": "human development index",
}


def _resolve_file(name: str) -> tuple[str, int]:
    """Look the download URL up through figshare's anonymous API.

    Hard-coding the file id is tempting and wrong: figshare reissues ids when a
    dataset is re-versioned, so a pinned URL silently becomes a 404 or, worse,
    a different file.
    """
    meta = memo_json(FIGSHARE_ARTICLE, namespace="figshare", max_age_days=90)
    for entry in meta.get("files", []):
        if entry["name"] == name:
            return entry["download_url"], int(entry["size"])
    available = ", ".join(f["name"] for f in meta.get("files", []))
    raise DataSourceError(
        f"{name} is not in the HydroATLAS figshare record. Available: {available}"
    )


def fetch_basinatlas(*, progress: bool = True) -> Path:
    """Download and unpack BasinATLAS. About 2.7 GB, once, then cached."""
    target = subdir("hydroatlas") / "BasinATLAS_v10"
    existing = list(target.glob("*.gdb")) or list(target.rglob("*.gdb"))
    if existing:
        return existing[0]

    url, size = _resolve_file("BasinATLAS_Data_v10.gdb.zip")
    zpath = download(
        url, namespace="hydroatlas", progress=progress, timeout=3600,
        expected_min_bytes=size // 2,
    )
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zpath) as zf:
        zf.extractall(target)
    found = list(target.rglob("*.gdb"))
    if not found:
        raise DataSourceError(f"No file geodatabase inside {url}")
    return found[0]


def hydroatlas(
    hybas_id: int | None = None,
    geometry=None,
    *,
    level: int = 12,
    prefixes: tuple[str, ...] | None = None,
    progress: bool = True,
):
    """Return BasinATLAS attributes.

    Parameters
    ----------
    hybas_id
        The outlet unit's HydroBASINS id. Pass this to get one row whose ``_u``
        columns already describe the whole upstream basin.
    geometry
        Alternatively, every unit intersecting a polygon.
    prefixes
        Restrict to attribute groups, e.g. ``("pre", "tmp", "ari")``. See
        :data:`GROUPS`.
    """
    import geopandas as gpd

    gdb = fetch_basinatlas(progress=progress)
    layer = f"BasinATLAS_v10_lev{level:02d}"

    if hybas_id is not None:
        gdf = gpd.read_file(gdb, layer=layer, where=f"HYBAS_ID = {int(hybas_id)}")
        if len(gdf) == 0:
            raise DataSourceError(
                f"HYBAS_ID {hybas_id} is not in {layer}. Level {level} ids come "
                "from the same level's HydroBASINS file."
            )
    elif geometry is not None:
        gdf = gpd.read_file(gdb, layer=layer, bbox=geometry.bounds)
        if len(gdf):
            gdf = gdf[gdf.intersects(geometry)].copy()
    else:
        raise ValueError("Pass either hybas_id or geometry.")

    if prefixes:
        keep = ["HYBAS_ID", "geometry"] + [
            c for c in gdf.columns if c.split("_")[0] in prefixes
        ]
        gdf = gdf[[c for c in keep if c in gdf.columns]]

    gdf.attrs.update(
        {
            "basinkit_product": "BasinATLAS v1.0",
            "license": "CC BY 4.0",
            "citation": "Linke, S. et al. (2019). Scientific Data 6, 283.",
            "note": "_c columns describe the local sub-catchment; _u columns are "
                    "already aggregated over everything upstream.",
        }
    )
    return gdf


#: Spatial extent is encoded in the *first letter* of a BasinATLAS column's
#: third token, not as a trailing suffix: ``pre_mm_uyr`` is upstream,
#: ``run_mm_syr`` is the local sub-catchment, ``dis_m3_pyr`` is at the pour
#: point. Reading it as a suffix silently matches nothing.
EXTENT_CODES = {"u": "upstream", "s": "sub-catchment", "p": "pour point",
                "c": "catchment", "l": "local"}

#: BasinATLAS stores several variables as scaled integers to keep the tables
#: compact. Read raw, the Koshi looks like it has a mean air temperature of 50
#: degrees and a mean slope of 204 degrees. Divisor and unit per variable
#: prefix, from the HydroATLAS technical documentation.
SCALING = {
    "tmp": (10.0, "degC"),
    "slp": (10.0, "degrees"),
    "ari": (100.0, "index"),
    "cmi": (100.0, "index"),
    "hft": (10.0, "index"),
}

#: Class-code variables: integers that label a category, never to be scaled or
#: averaged.
CATEGORICAL = {"clz", "cls", "glc", "pnv", "wet", "lit", "gad", "tbi", "tec", "fmh"}


def describe(row, extent: str = "u") -> dict:
    """Turn one BasinATLAS row into a readable summary.

    Parameters
    ----------
    extent
        ``"u"`` (default) keeps only the upstream-aggregated variables, which
        together characterise the whole basin. ``"s"`` keeps the local
        sub-catchment, ``"p"`` the pour point, and ``None`` keeps everything.
    """
    out: dict[str, float] = {}
    for name, value in row.items():
        if not isinstance(name, str) or name in ("geometry",):
            continue
        parts = name.split("_")
        if len(parts) < 3:
            continue                       # HYBAS_ID, UP_AREA and friends
        if extent and not parts[2].startswith(extent):
            continue
        label = GROUPS.get(parts[0], parts[0])
        if parts[0] not in CATEGORICAL and parts[0] in SCALING:
            divisor, unit = SCALING[parts[0]]
            try:
                value = round(float(value) / divisor, 3)
                label = f"{label} ({unit})"
            except (TypeError, ValueError):
                pass
        out[f"{label} [{name}]"] = value
    return out
