"""Confirm a delineated basin against the river network before returning it.

A coordinate names a place, not a river. HydroBASINS level-12 units average
about 130 km2, so a point on a small creek falls inside a unit whose outlet may
be on the trunk river a few kilometres away, and the polygon returned is then
the trunk's catchment. The geometry gives no sign of this on its own: the
traversal is exact, and the dataset's own ``UP_AREA`` agrees with the assembled
area to within one percent either way.

The river network settles it. HydroRIVERS records ``UPLAND_SKM`` for every
reach, so the largest river near the outlet bounds what the point can plausibly
drain, and a polygon far larger than that bound belongs to a different river.
Blind validation against 2,550 gauges with agency-published catchment areas
sets the scale of the question: it arises on a fifth of outlets overall and on
most outlets below 100 km2, and it is where the DEM backend earns its place.

Measured on the global sample, n=1,146, at ``ratio > 2``, and the search radius
matters more than the ratio does:

======================  ==========  ==========
                        1 km        2 km
======================  ==========  ==========
precision               77 %        85 %
false alarms            6.2 %       3.2 %
recall                  33 %        30 %
======================  ==========  ==========

Per continent at 2 km the precision runs from 75 percent (Europe) to 93 percent
(Africa), so it holds everywhere rather than in one region. Recall is modest by
design: a check that stays quiet on 97 percent of sound outlets is one people
keep reading. HydroRIVERS carries no reach draining under about 10 km2, so on
the smallest headwaters there is nothing to compare against, and the message
returned says which situation the outlet is in.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# Search radius for "the river this point is on". This has to be wider than the
# distance a gauge coordinate typically sits from its channel, or the search
# finds a roadside ditch and concludes the trunk river is not there. GSIM's own
# relocations have a median of 280 m and a 90th percentile near 1.4 km, so one
# kilometre was too tight by construction.
#
# Measured, on 25 stations where the corrective switch fired: at 1 km it
# rewrote two correct continental answers, including a Mekong gauge whose
# 373,000 km2 became 9.5 because the only reach within a kilometre drained
# 5.9 km2. At 2 km both of those find their real river and are left alone, at
# the cost of four small catchments that stop being corrected. Losing four
# improvements is the cheaper error.
SEARCH_KM = 2.0

# Above this multiple the polygon is not a version of what the nearest river
# drains, it is a different river. Chosen on one sample, confirmed on another.
RATIO_LIMIT = 2.0

# HydroRIVERS carries no reach below roughly this upstream area, so a point
# with no reach nearby is below the network's own floor rather than in error.
NETWORK_FLOOR_KM2 = 10.0

# A second, narrower signal. When no river is mapped within the search radius,
# the network itself is saying the point drains less than NETWORK_FLOOR_KM2. A
# polygon of a few hundred square kilometres then contradicts it by two orders
# of magnitude, and that is the shape of a single level-12 unit captured by
# outlet. Measured separately on both validation samples:
#
#     first sample   n=1,169   65 fire   86 % precision   1.2 % false alarms
#     global sample  n=1,238   72 fire   89 % precision   1.0 % false alarms
#
# The window matters: above 1,000 km2 a missing nearby reach usually means a
# gauge on a floodplain set back from the mapped centreline, where flagging
# earns its keep only 22 % of the time, so the condition stops there.
ORPHAN_RANGE_KM2 = (100.0, 1_000.0)


@dataclass
class OutletCheck:
    """What the river network says about a delineated basin."""

    ok: bool
    reason: str
    message: str = ""
    basin_area_km2: float | None = None
    largest_upland_km2: float | None = None
    largest_distance_km: float | None = None
    nearest_upland_km2: float | None = None
    nearest_distance_km: float | None = None
    ratio: float | None = None
    suggested_area_km2: float | None = None
    notes: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok


def _deg_box(lat: float, lon: float, km: float):
    dlat = km / 110.574
    dlon = km / max(111.320 * math.cos(math.radians(lat)), 1e-6)
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


def check_outlet(
    lat: float,
    lon: float,
    basin_area_km2: float,
    *,
    search_km: float = SEARCH_KM,
    ratio_limit: float = RATIO_LIMIT,
    progress: bool = False,
    allow_download: bool = True,
) -> OutletCheck:
    """Compare a delineated basin against the rivers around its outlet.

    Parameters
    ----------
    allow_download
        HydroRIVERS is a regional download of a few hundred megabytes. With
        ``False`` the check is skipped rather than started, and the result says
        ``reason='not-cached'`` so a caller can tell a clean check apart from
        one that was never run.
    """
    from .delineate.hydrobasins import candidate_regions
    from .sources.vectors import RIVER_REGIONS, RIVERS, _unpack

    try:
        regions = [r for r in candidate_regions(lat, lon) if r in RIVER_REGIONS]
    except Exception as exc:
        return OutletCheck(True, "no-coverage", str(exc),
                           basin_area_km2=basin_area_km2)
    if not regions:
        return OutletCheck(True, "no-coverage",
                           "No HydroRIVERS region covers this point.",
                           basin_area_km2=basin_area_km2)

    if not allow_download:
        from .cache import subdir
        cached = any((subdir("hydrorivers") / f"HydroRIVERS_v10_{r}").exists()
                     for r in regions)
        if not cached:
            return OutletCheck(
                True, "not-cached",
                "The river network for this region is not downloaded, so the "
                "answer was not checked against it.",
                basin_area_km2=basin_area_km2)

    import geopandas as gpd

    bbox = _deg_box(lat, lon, search_km)
    best = None
    for region in regions:
        try:
            shp = _unpack(f"{RIVERS}/HydroRIVERS_v10_{region}_shp.zip",
                          f"HydroRIVERS_v10_{region}", "hydrorivers",
                          progress=progress)
            reaches = gpd.read_file(shp, bbox=bbox, columns=["UPLAND_SKM"],
                                    engine="pyogrio")
        except Exception:
            continue
        if reaches is None or reaches.empty:
            continue
        reaches = reaches.assign(km=_km_from(reaches, lat, lon))
        reaches = reaches[reaches["km"] <= search_km]
        if reaches.empty:
            continue
        best = reaches if best is None else __import__("pandas").concat(
            [best, reaches], ignore_index=True)

    if best is None or best.empty:
        lo, hi = ORPHAN_RANGE_KM2
        if lo <= basin_area_km2 <= hi:
            return OutletCheck(
                False, "orphan-outlet",
                f"No mapped river within {search_km:g} km of the outlet, while "
                f"the basin comes back as {basin_area_km2:,.0f} km2. "
                f"HydroRIVERS carries reaches down to about "
                f"{NETWORK_FLOOR_KM2:g} km2, so the network places this point "
                "on a headwater while the polygon describes a catchment of "
                "several hundred. Roughly seven in eight outlets flagged this "
                "way need attention. For the headwater, delineate with "
                "backend='dem'.",
                basin_area_km2=basin_area_km2,
                notes=["no mapped river near an outlet with a mid-sized basin"])
        return OutletCheck(
            True, "no-reach",
            f"No mapped river within {search_km:g} km of the outlet. "
            f"HydroRIVERS carries reaches down to about {NETWORK_FLOOR_KM2:g} "
            "km2 of upstream area, so an outlet on a smaller headwater sits "
            "below what this comparison can see. At that scale the DEM backend "
            "is the instrument to use: it routes flow on a 30 m grid.",
            basin_area_km2=basin_area_km2,
            notes=["below the river network's own resolution floor"])

    big = best.loc[best["UPLAND_SKM"].idxmax()]
    near = best.loc[best["km"].idxmin()]
    largest = float(big["UPLAND_SKM"])
    ratio = basin_area_km2 / largest if largest > 0 else float("inf")

    common = dict(
        basin_area_km2=basin_area_km2,
        largest_upland_km2=round(largest, 2),
        largest_distance_km=round(float(big["km"]), 3),
        nearest_upland_km2=round(float(near["UPLAND_SKM"]), 2),
        nearest_distance_km=round(float(near["km"]), 3),
        ratio=round(ratio, 2),
    )

    if ratio <= ratio_limit:
        return OutletCheck(
            True, "consistent",
            f"The basin is {ratio:.2f} times the {largest:,.0f} km2 draining to "
            f"the largest river within {search_km:g} km, which is the "
            "agreement expected when the outlet is on that river. The check is "
            "deliberately conservative, so read silence as one test passed "
            "rather than as a full verification.",
            **common)

    return OutletCheck(
        False, "over-captured",
        f"The delineated basin is {basin_area_km2:,.0f} km2 while the largest "
        f"river within {search_km:g} km of the outlet drains "
        f"{largest:,.0f} km2, a factor of {ratio:.0f}. That gap points to the "
        "outlet sitting in a sub-basin belonging to a larger river than the "
        "one at the point. Roughly four in five outlets flagged this way need "
        "attention. For a catchment at the smaller scale, delineate with "
        "backend='dem'.",
        suggested_area_km2=round(largest, 2),
        notes=["outlet may be on a different river from the returned basin"],
        **common)


def _km_from(gdf, lat: float, lon: float):
    """Distance in km from (lat, lon) to each geometry, measured on the ground.

    Multiplying a distance in degrees by 110.574 treats a degree of longitude
    as if it were a degree of latitude, which overstates east-west distance by
    1/cos(latitude): half again at 48 degrees, double at 60. A projection centred
    on the outlet measures true distance in every direction.
    """
    local = gdf.to_crs(f"+proj=aeqd +lat_0={lat} +lon_0={lon} +units=m +datum=WGS84")
    from shapely.geometry import Point as _P
    return local.geometry.distance(_P(0, 0)) / 1000.0
