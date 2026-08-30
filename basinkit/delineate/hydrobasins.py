"""Delineation by upstream graph traversal over HydroBASINS level-12 units.

HydroBASINS ships every sub-basin with a ``NEXT_DOWN`` pointer to the unit it
drains into. That turns "find everything upstream of here" from a raster fill
over hundreds of millions of cells into a breadth-first walk over a few hundred
thousand nodes -- milliseconds instead of minutes, and the cost barely grows
with basin size. It is why this is the default backend even though the DEM
router is more precise.

The trade-off is a resolution floor: a level-12 unit has a median area around
130 km2, so the delineated boundary is only as sharp as the unit the outlet
falls in. ``delineate(backend='auto')`` detects that case and re-runs on the DEM.
"""

from __future__ import annotations

import warnings
from collections import defaultdict, deque
from pathlib import Path

from ..cache import download, subdir
from ..exceptions import DelineationError, OutletSnapError

_BASE = "https://data.hydrosheds.org/file/hydrobasins/standard"

#: Approximate extents of the HydroSHEDS regional files, in probe order.
#: Overlaps are deliberate -- the point-in-polygon test resolves them.
REGIONS: dict[str, tuple[float, float, float, float]] = {
    # code: (min_lon, min_lat, max_lon, max_lat)
    "eu": (-25.0, 12.0, 70.0, 82.0),
    "as": (57.0, -12.0, 180.0, 61.0),
    "si": (58.0, 45.0, 180.0, 81.0),
    "af": (-19.0, -36.0, 55.0, 38.0),
    "na": (-140.0, 5.0, -52.0, 62.0),
    "sa": (-93.0, -56.0, -32.0, 15.0),
    "au": (95.0, -56.0, 180.0, 20.0),
    "ar": (-170.0, 51.0, -50.0, 84.0),
    "gr": (-75.0, 59.0, -10.0, 84.0),
}

REGION_NAMES = {
    "af": "Africa", "ar": "North American Arctic", "as": "Central and Southeast Asia",
    "au": "Australia and Oceania", "eu": "Europe and Middle East", "gr": "Greenland",
    "na": "North America", "sa": "South America", "si": "Siberia",
}


def candidate_regions(lat: float, lon: float) -> list[str]:
    """Regional files whose extent contains the point, most likely first."""
    hits = [
        code
        for code, (w, s, e, n) in REGIONS.items()
        if w <= lon <= e and s <= lat <= n
    ]
    if not hits:
        raise DelineationError(
            f"({lat}, {lon}) falls outside every HydroBASINS region. "
            "HydroSHEDS covers all land except Antarctica -- check that latitude "
            "and longitude are not swapped."
        )
    return hits


def fetch_region(region: str, level: int = 12, *, progress: bool = True) -> Path:
    """Download and unpack one regional HydroBASINS file, cached forever."""
    import zipfile

    region = region.lower()
    name = f"hybas_{region}_lev{level:02d}_v1c"
    target = subdir("hydrobasins") / name
    shp = target / f"{name}.shp"
    if shp.exists():
        return shp

    url = f"{_BASE}/{name}.zip"
    zpath = download(
        url, namespace="hydrobasins", progress=progress,
        timeout=300, expected_min_bytes=1 << 20,
    )
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zpath) as zf:
        zf.extractall(target)
    if not shp.exists():
        found = list(target.glob("*.shp"))
        if not found:
            raise DelineationError(f"No shapefile inside {url}")
        return found[0]
    return shp


# How far out to look when telling the user their point may be off-channel.
# Kept inside the shapefile read window (0.25 deg ~ 25 km of longitude at
# mid latitudes) so the check never sees a truncated view.
_ADVISORY_KM = 20.0


def _find_outlet_unit(shp: Path, lat: float, lon: float, snap_km: float,
                      river_snap_km: float, river_snap_ratio: float):
    """Find the level-12 unit the outlet belongs to.

    Returns ``(unit, snap_info)``.

    The subtlety is that "the unit containing the point" is frequently not the
    unit the user meant. A gauge coordinate sits on a river *bank*, and on a
    large river the bank belongs to a small lateral sub-basin rather than to
    the main stem. Two real examples, both measured:

      Rhine at Lobith      containing unit 270 km2; the main-stem unit
                           (158,835 km2) is 200 m away
      Godavari at Polavaram  containing unit 354 km2; the main-stem unit
                           (307,666 km2) is 454 m away

    Taking the containing unit there returns a basin three orders of magnitude
    too small, and -- because HydroBASINS' own UP_AREA field agrees with the
    tiny answer -- every internal consistency check still passes. It is exactly
    the kind of wrong answer that never announces itself.

    So a nearby unit wins only when it is dramatically larger: within
    ``river_snap_km`` and at least ``river_snap_ratio`` times the containing
    unit's upstream area. Requiring a large jump rather than simply taking the
    biggest neighbour is what keeps a genuine small tributary near a big river
    from being silently swallowed. Whenever a snap happens it is warned about
    and recorded in provenance.
    """
    import geopandas as gpd
    from shapely.geometry import Point

    pt = Point(lon, lat)
    pad = max(0.25, river_snap_km / 111.0 * 3)
    gdf = gpd.read_file(
        shp,
        bbox=(lon - pad, lat - pad, lon + pad, lat + pad),
        columns=["HYBAS_ID", "NEXT_DOWN", "UP_AREA", "SUB_AREA", "ORDER"],
    )
    if len(gdf) == 0:
        return None, {}

    # Distances have to be real kilometres, not degrees scaled by 111. A degree
    # of longitude is 111 km only at the equator; at Lobith (51.8N) it is 68.7,
    # so a degree-based radius is 1.6x too generous east-west and the snap
    # tolerance stops meaning what it says. An azimuthal-equidistant projection
    # centred on the outlet makes it exact, and silences geopandas' warning
    # about measuring distance in a geographic CRS.
    aeqd = (
        f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m +no_defs"
    )
    gdf = gdf.copy()
    local = gdf.to_crs(aeqd)
    origin = gpd.GeoSeries([pt], crs="EPSG:4326").to_crs(aeqd).iloc[0]
    gdf["dist_km"] = local.distance(origin) / 1000.0

    inside = gdf[gdf.contains(pt)]
    if len(inside):
        unit = inside.iloc[0]
        snap: dict = {}
    else:
        # Not inside any unit: a coastal sliver, or a point in a lake.
        nearest = gdf.nsmallest(1, "dist_km").iloc[0]
        if nearest["dist_km"] > snap_km:
            return None, {}
        unit = nearest
        snap = {
            "snapped_to_nearest_unit": True,
            "snap_distance_km": round(float(nearest["dist_km"]), 3),
        }

    if river_snap_ratio and river_snap_km > 0:
        here = float(unit.get("UP_AREA", 0) or 0)
        near = gdf[gdf["dist_km"] <= river_snap_km]
        bigger = near[near["UP_AREA"] >= max(here, 1e-9) * river_snap_ratio]
        if len(bigger):
            best = bigger.nlargest(1, "UP_AREA").iloc[0]
            warnings.warn(
                f"Outlet ({lat}, {lon}) falls in a {here:,.0f} km2 unit, but a "
                f"{float(best['UP_AREA']):,.0f} km2 unit lies "
                f"{float(best['dist_km']) * 1000:,.0f} m away -- the point is on the "
                "bank of a much larger river. Snapping to the main stem. Pass "
                "river_snap_ratio=None to take the containing unit instead.",
                stacklevel=3,
            )
            snap = {
                **snap,
                "snapped_to_main_stem": True,
                "snap_distance_km": round(float(best["dist_km"]), 3),
                "containing_unit_up_area_km2": round(here, 1),
                "containing_unit_hybas_id": int(unit["HYBAS_ID"]),
                "snap_ratio": round(float(best["UP_AREA"]) / max(here, 1e-9), 1),
            }
            unit = best

    # Advisory. The point may simply be off-channel: far enough from the main
    # stem that snapping would be reckless, but close enough that the user
    # probably meant it. Say so loudly and change nothing -- a silently tiny
    # basin is the exact failure this package exists to prevent.
    if river_snap_ratio and not snap.get("snapped_to_main_stem"):
        here = float(unit.get("UP_AREA", 0) or 0)
        window = gdf[gdf["dist_km"] <= _ADVISORY_KM]
        larger = window[window["UP_AREA"] >= max(here, 1e-9) * river_snap_ratio]
        if len(larger):
            best = larger.nlargest(1, "UP_AREA").iloc[0]
            warnings.warn(
                f"Outlet ({lat}, {lon}) sits in a {here:,.0f} km2 unit, but a "
                f"{float(best['UP_AREA']):,.0f} km2 unit lies "
                f"{float(best['dist_km']):.1f} km away -- outside the "
                f"{river_snap_km:g} km snap radius, so the point was NOT moved. "
                f"If you meant the larger river, put the coordinate on its "
                f"channel or pass river_snap_km={float(best['dist_km']) + 1:.0f}. "
                f"Returning the {here:,.0f} km2 basin.",
                stacklevel=3,
            )
            snap["off_channel_candidate"] = {
                "hybas_id": int(best["HYBAS_ID"]),
                "up_area_km2": round(float(best["UP_AREA"]), 1),
                "distance_km": round(float(best["dist_km"]), 3),
            }

    # Record what else was in range, so a wrong pick is visible rather than
    # invisible.
    near = gdf[(gdf["dist_km"] <= max(river_snap_km, 2.0))]
    alts = near.nlargest(4, "UP_AREA")
    snap["alternatives_in_range"] = [
        {"hybas_id": int(r.HYBAS_ID), "up_area_km2": round(float(r.UP_AREA), 1),
         "distance_km": round(float(r.dist_km), 3)}
        for r in alts.itertuples()
        if int(r.HYBAS_ID) != int(unit["HYBAS_ID"])
    ]
    return unit, snap


def _upstream_ids(shp: Path, seed_id: int) -> set[int]:
    """Breadth-first walk up the NEXT_DOWN graph from ``seed_id``."""
    from pyogrio import read_dataframe

    attrs = read_dataframe(
        shp, columns=["HYBAS_ID", "NEXT_DOWN"], read_geometry=False
    )
    parents: dict[int, list[int]] = defaultdict(list)
    for hid, nxt in zip(
        attrs["HYBAS_ID"].to_numpy(), attrs["NEXT_DOWN"].to_numpy(), strict=False
    ):
        if nxt:
            parents[int(nxt)].append(int(hid))

    seen = {int(seed_id)}
    queue = deque([int(seed_id)])
    while queue:
        node = queue.popleft()
        for up in parents.get(node, ()):
            if up not in seen:
                seen.add(up)
                queue.append(up)
    return seen


def delineate_hydrobasins(
    lat: float,
    lon: float,
    *,
    level: int = 12,
    snap_km: float = 5.0,
    river_snap_km: float = 1.0,
    river_snap_ratio: float | None = 10.0,
    progress: bool = True,
    **_,
):
    """Delineate the upstream basin from HydroBASINS level-12 units.

    Parameters
    ----------
    level
        Pfafstetter level of the source file. 12 is finest and the default.
    snap_km
        If the outlet is not inside any unit at all, snap to the nearest one
        within this distance. Coastal outlets often sit just offshore.
    river_snap_km, river_snap_ratio
        Guard against the bank-of-a-big-river problem: if a unit within
        ``river_snap_km`` drains at least ``river_snap_ratio`` times more than
        the unit containing the point, snap to it and warn. Set
        ``river_snap_ratio=None`` to always take the containing unit.
    """
    import geopandas as gpd

    errors = []
    for region in candidate_regions(lat, lon):
        shp = fetch_region(region, level, progress=progress)
        seed, snap_info = _find_outlet_unit(
            shp, lat, lon, snap_km, river_snap_km, river_snap_ratio or 0
        )
        if seed is None:
            errors.append(region)
            continue

        ids = _upstream_ids(shp, int(seed["HYBAS_ID"]))
        id_list = sorted(ids)

        # Read back only the geometries we need. For a large basin this is
        # still tens of thousands of polygons, so chunk the SQL IN clause --
        # OGR will refuse a single statement with 200k literals.
        frames = []
        for i in range(0, len(id_list), 2000):
            chunk = id_list[i : i + 2000]
            where = "HYBAS_ID IN (" + ",".join(str(x) for x in chunk) + ")"
            frames.append(
                gpd.read_file(
                    shp, where=where, columns=["HYBAS_ID", "SUB_AREA"], engine="pyogrio"
                )
            )
        units = gpd.GeoDataFrame(
            __import__("pandas").concat(frames, ignore_index=True), crs=frames[0].crs
        )

        geom = units.union_all()
        # Dissolving thousands of adjacent polygons leaves hairline slivers on
        # shared edges. A tiny buffer out-and-back welds them without moving
        # the outer boundary perceptibly (1e-5 deg is about a metre).
        geom = geom.buffer(1e-5).buffer(-1e-5)
        if geom.geom_type == "GeometryCollection":
            from shapely.geometry import MultiPolygon

            geom = MultiPolygon(
                [g for g in geom.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
            )

        from ..clip import basin_area_km2

        return geom, {
            "backend": "hydrobasins",
            "source_dataset": f"HydroBASINS v1c level {level} ({REGION_NAMES[region]})",
            "region": region,
            "level": level,
            "n_units": len(units),
            "outlet": (lat, lon),
            "outlet_hybas_id": int(seed["HYBAS_ID"]),
            "reported_up_area_km2": float(seed.get("UP_AREA", 0) or 0),
            **snap_info,
            "area_km2": round(basin_area_km2(geom), 2),
            "license": "CC BY 4.0",
            "citation": "Lehner, B. & Grill, G. (2013). Hydrological Processes 27(15), 2171-2186.",
        }

    raise OutletSnapError(
        f"No HydroBASINS level-{level} unit within {snap_km} km of ({lat}, {lon}); "
        f"searched region(s): {', '.join(errors) or 'none'}.\n"
        "Usually this means the coordinate is offshore or in a closed basin. "
        "Try a larger snap_km, move the point onto the river, or use backend='dem'."
    )
