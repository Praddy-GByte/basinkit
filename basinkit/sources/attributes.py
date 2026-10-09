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


#: Written beside the geodatabase once every member of the archive is out.
#: A file geodatabase is a directory, so an interrupted extraction leaves one
#: that exists, is named correctly, and is missing most of its contents -- and
#: the old check was that a ``*.gdb`` directory existed. Afterwards every
#: attributes() call failed with "Layer could not be opened" until somebody
#: deleted the folder by hand, and nothing in the message said that was the
#: remedy. The marker records what the directory listing cannot.
_COMPLETE = ".basinkit-extracted"

#: Free space the unpacked geodatabase needs. The archive itself is another
#: 2.7 GB on top, when it is not already cached. Checked before starting,
#: because running out part-way through is what produced the half-extracted
#: directory in the first place.
_NEEDED_BYTES = 7 * 1024 ** 3


def _has_layers(gdb: Path) -> bool:
    """Whether the geodatabase can be opened and holds its level-12 layer.

    This is what an extraction has to be good for, so it is a better question
    than whether the directory exists -- and it is the one that lets an
    extraction made before the marker existed go on working instead of being
    refused. Opening a file geodatabase to list its layers reads its catalogue
    table, not its 6 GB of features.
    """
    try:
        import pyogrio

        names = {str(n) for n in pyogrio.list_layers(gdb)[:, 0]}
    except Exception:                                       # noqa: BLE001
        try:
            import fiona

            names = set(fiona.listlayers(str(gdb)))
        except Exception:                                   # noqa: BLE001
            return False
    return any(n.startswith("BasinATLAS_v10_lev") for n in names)


def _usable_gdb(target: Path) -> Path | None:
    """An extraction that finished, or ``None``.

    A marker is trusted outright. Without one -- an extraction from before the
    marker existed, or one someone unpacked by hand -- the geodatabase is
    opened and asked for its layers, and a marker written if it answers, so
    the question is asked once rather than on every call.
    """
    for found in list(target.glob("*.gdb")) + list(target.rglob("*.gdb")):
        if (found.parent / _COMPLETE).exists() or (found / _COMPLETE).exists():
            return found
        if _has_layers(found):
            try:
                (found.parent / _COMPLETE).write_text(
                    "verified by reading its layers\n", encoding="utf-8")
            except OSError:
                pass
            return found
    return None


def _partial_gdb(target: Path) -> Path | None:
    for found in list(target.glob("*.gdb")) + list(target.rglob("*.gdb")):
        return found
    return None


def fetch_basinatlas(*, progress: bool = True, force: bool = False) -> Path:
    """Download and unpack BasinATLAS. About 2.7 GB, once, then cached.

    Parameters
    ----------
    force
        Extract again even if a finished extraction is already there. Use it
        to replace one that was interrupted; the message raised in that case
        says so.
    """
    import shutil

    target = subdir("hydroatlas") / "BasinATLAS_v10"
    if not force:
        done = _usable_gdb(target)
        if done is not None:
            return done
        stale = _partial_gdb(target)
        if stale is not None:
            raise DataSourceError(
                f"{stale} is there but the extraction that made it did not "
                "finish, so most of its layers are absent and every read of "
                "it fails with 'Layer could not be opened'. A file "
                "geodatabase is a directory, so this cannot be told apart "
                "from a complete one by looking.\n\n"
                f"Delete {stale.parent} and call this again, or pass "
                "force=True to extract over it. The archive itself is still "
                "cached, so this costs the unpacking and not the download. "
                "The layers were looked for and not found, so this is not "
                "merely a missing marker."
            )

    free = shutil.disk_usage(subdir("hydroatlas")).free
    if free < _NEEDED_BYTES:
        raise DataSourceError(
            f"BasinATLAS unpacks to about {_NEEDED_BYTES / 1024 ** 3:.0f} GB, "
            "plus 2.7 GB for the archive if it is not already cached, and "
            f"{free / 1024 ** 3:.1f} GB is free. Freeing the space first "
            "avoids an extraction that stops half way and leaves a "
            "geodatabase that looks complete and is not -- which is how this "
            "check came to exist."
        )

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
    # Last, and only once extractall has returned, so the marker means what it
    # says.
    (found[0].parent / _COMPLETE).write_text(
        f"{url}\n{size} bytes\n", encoding="utf-8")
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


def describe(row, extent: str = "u", *, progress: bool = True) -> dict:
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
