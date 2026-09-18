"""Delineation on TDX-Hydro, the 12 m global hydrography.

HydroBASINS level-12 units average about 130 km2, which is why a catchment of
a few hundred comes back with a wide error band: the boundary can only be as
sharp as the unit the outlet falls in. TDX-Hydro is a different order of
detail. It is derived from TanDEM-X at 12 m and carries one catchment polygon
per stream reach, so a small headwater basin is described by its own ground
rather than by the cell that contains it.

The data is read from the GEOGLOWS v2 distribution on AWS Open Data, which is
anonymous over plain HTTPS and supports range requests, rather than from NGA's
own download endpoint, which serves whole multi-gigabyte files with no resume.
GEOGLOWS also gives every reach a globally unique id and a topology with no
dangling pointers, which the per-basin native files do not.

Two things to know before choosing this backend.

**The licence is ShareAlike.** TDX-Hydro is CC BY-SA 4.0. Every other default
in this package is CC BY 4.0 or more permissive, so this one is opt-in and
never selected by ``backend='auto'``: a derivative you redistribute inherits
the ShareAlike obligation, and that is a decision to make deliberately rather
than to discover later.

**Twelve of NGA's sixty-two regions are absent from GEOGLOWS**, among them
Greenland and much of Arctic North America. Those points fall back with a
message rather than a wrong answer.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque

from ..cache import download
from ..exceptions import DelineationError, MissingDependency, OutletSnapError

#: GEOGLOWS v2 on AWS Open Data. Anonymous, range-capable, us-west-2.
BASE = "https://geoglows-v2.s3.us-west-2.amazonaws.com"

#: One row per reach: id, its processing unit, and a point on it. 139 MB, and
#: the only global file needed before a region is known.
INDEX = f"{BASE}/tables/package-metadata-table.parquet"

LICENSE = "CC BY-SA 4.0"
CITATION = (
    "TDX-Hydro, National Geospatial-Intelligence Agency, 2023 (CC BY-SA 4.0); "
    "distributed in the GEOGLOWS v2 hydrography. Carlson et al. (2024), "
    "doi:10.22541/essoar.171629686.65893579/v1."
)

_EARTH_R_KM = 6371.0088


def _parquet_reader():
    """pandas reads Parquet only through pyarrow, which this route needs."""
    try:
        import pyarrow  # noqa: F401
    except ImportError as exc:
        raise MissingDependency("pyarrow", "tdx") from exc

    import pandas as pd

    return pd


def _index(progress: bool = True):
    """Every reach's id, unit and location, as four numpy arrays."""
    _parquet_reader()
    import pyarrow.parquet as pq

    path = download(INDEX, namespace="tdx", progress=progress, timeout=900,
                    expected_min_bytes=1 << 20)
    table = pq.read_table(path, columns=["LINKNO", "VPUCode", "lat", "lon"])
    return (table["LINKNO"].to_numpy(),
            table["VPUCode"].to_numpy(),
            table["lat"].to_numpy().astype("float64"),
            table["lon"].to_numpy().astype("float64"))


def _nearest_reach(lat: float, lon: float, snap_km: float, progress: bool):
    """The reach whose recorded point is closest, if one is close enough."""
    import numpy as np

    links, vpus, lats, lons = _index(progress=progress)

    # Narrow by a degree box first: the haversine over 6.8 million points is
    # fast but the box makes it trivial, and the box has to be generous in
    # longitude near the poles.
    pad_lat = snap_km / 111.0
    cos_lat = max(math.cos(math.radians(lat)), 1e-6)
    pad_lon = pad_lat / cos_lat
    near = ((np.abs(lats - lat) <= pad_lat) & (np.abs(lons - lon) <= pad_lon))
    if not near.any():
        raise OutletSnapError(
            f"No TDX-Hydro reach within {snap_km:g} km of ({lat}, {lon}).\n"
            "GEOGLOWS omits twelve of NGA's sixty-two regions, Greenland and "
            "much of Arctic North America among them. Use "
            "backend='hydrobasins' there."
        )

    phi1, phi2 = math.radians(lat), np.radians(lats[near])
    dphi = phi2 - phi1
    dlam = np.radians(lons[near] - lon)
    a = (np.sin(dphi / 2) ** 2
         + math.cos(phi1) * np.cos(phi2) * np.sin(dlam / 2) ** 2)
    distances = 2 * _EARTH_R_KM * np.arcsin(np.sqrt(a))

    pick = int(np.argmin(distances))
    if distances[pick] > snap_km:
        raise OutletSnapError(
            f"Nearest TDX-Hydro reach is {distances[pick]:.2f} km from "
            f"({lat}, {lon}), beyond snap_km={snap_km:g}."
        )
    return (int(links[near][pick]), int(vpus[near][pick]),
            float(distances[pick]))


def _upstream(link: int, vpu: int, progress: bool) -> set[int]:
    """Every reach draining into ``link``, itself included.

    A processing unit is closed: no downstream pointer leaves it, so the walk
    never needs a second file.
    """
    pd = _parquet_reader()

    url = f"{BASE}/routing-configs/vpu={vpu}/connectivity.parquet"
    path = download(url, namespace="tdx", progress=progress, timeout=300)
    edges = pd.read_parquet(path)

    upstream: dict[int, list[int]] = defaultdict(list)
    for child, parent in zip(edges["river_id"].to_numpy(),
                             edges["ds_river_id"].to_numpy(), strict=True):
        if parent != -1:
            upstream[int(parent)].append(int(child))

    seen = {link}
    queue = deque([link])
    while queue:
        for child in upstream.get(queue.popleft(), ()):
            if child not in seen:
                seen.add(child)
                queue.append(child)
    return seen


def _catchments(vpu: int, wanted: set[int], progress: bool):
    """The unit catchments for ``wanted``, as a GeoDataFrame.

    Read in batches rather than whole. A processing unit holds tens of
    thousands of polygons drawn at 12 m, and decoding all of them to fetch the
    few hundred that make up one small basin is how this ends as an out-of-
    memory kill on a laptop. Each batch is filtered and dropped.
    """
    _parquet_reader()
    import geopandas as gpd
    import numpy as np
    import pyarrow as pa
    import pyarrow.parquet as pq

    url = f"{BASE}/hydrography/vpu={vpu}/catchments_{vpu}.parquet"
    path = download(url, namespace="tdx", progress=progress, timeout=1800,
                    expected_min_bytes=1 << 20)

    reader = pq.ParquetFile(path)
    # The id column is spelled five different ways across the 125 files.
    lookup = {name.lower(): name for name in reader.schema_arrow.names}
    key = lookup.get("linkno")
    if key is None:
        raise DelineationError(
            f"The catchment file for unit {vpu} carries no link id; its "
            f"columns are {reader.schema_arrow.names}."
        )

    keep = np.fromiter(wanted, dtype="int64", count=len(wanted))
    pieces = []
    for batch in reader.iter_batches(batch_size=4096):
        ids = batch.column(key).to_numpy(zero_copy_only=False)
        mask = np.isin(ids, keep)
        if mask.any():
            pieces.append(pa.Table.from_batches([batch]).filter(pa.array(mask)))

    if not pieces:
        return gpd.GeoDataFrame(columns=[key, "geometry"], crs="EPSG:4326")
    return gpd.GeoDataFrame.from_arrow(pa.concat_tables(pieces))


def delineate_tdx(lat: float, lon: float, *, snap_km: float = 2.0,
                  progress: bool = True, **_):
    """Delineate the upstream basin from TDX-Hydro unit catchments.

    Parameters
    ----------
    snap_km
        How far the outlet may sit from the nearest mapped reach. The network
        is dense at 12 m, so the default is tighter than the HydroBASINS one:
        a point two kilometres from any reach is more likely to be off the
        river than to be a reach that is missing.
    """
    from ..clip import basin_area_km2

    link, vpu, snapped_km = _nearest_reach(lat, lon, snap_km, progress)
    wanted = _upstream(link, vpu, progress)
    units = _catchments(vpu, wanted, progress)

    if units.empty:
        raise DelineationError(
            f"Reach {link} has {len(wanted)} upstream reaches but unit {vpu} "
            "holds no catchment polygon for any of them. One GEOGLOWS unit "
            "(302) is known to be missing most of its catchments; use "
            "backend='hydrobasins' there."
        )

    geom = units.union_all()
    # Dissolving adjacent polygons leaves hairline slivers on shared edges; a
    # buffer out and back welds them without moving the outer boundary
    # perceptibly. 1e-6 degrees is about a tenth of a metre, an order finer
    # than the HydroBASINS pass because these edges are ten times sharper.
    geom = geom.buffer(1e-6).buffer(-1e-6)
    if geom.geom_type == "GeometryCollection":
        from shapely.geometry import MultiPolygon

        geom = MultiPolygon(
            [g for g in geom.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
        )

    provenance = {
        "backend": "tdx",
        "source_dataset": "TDX-Hydro (TanDEM-X 12 m), GEOGLOWS v2 hydrography",
        "grid": "12 m TanDEM-X",
        "vpu": vpu,
        "outlet": (lat, lon),
        "outlet_link": link,
        "n_reaches": len(wanted),
        "n_units": len(units),
        "snapped_km": round(snapped_km, 4),
        "area_km2": round(basin_area_km2(geom), 2),
        "license": LICENSE,
        "citation": CITATION,
    }
    if len(units) < len(wanted):
        provenance["warning"] = (
            f"{len(wanted) - len(units)} of {len(wanted)} upstream reaches have "
            "no catchment polygon in this GEOGLOWS unit, so the basin is "
            "incomplete by that much."
        )
    return geom, provenance
