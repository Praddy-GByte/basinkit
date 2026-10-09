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
    #: basin area over the upland area of the river AT the outlet. The
    #: ratio above is taken against the largest river in the search box,
    #: which near a confluence is a different river entirely.
    nearest_ratio: float | None = None
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
        if basin_area_km2 > hi:
            # Above the orphan range the measurement that set that range does
            # not apply, because it was made on gauges -- which sit on rivers
            # by definition, so a missing nearby reach there means a
            # floodplain coordinate set back from the mapped centreline. A
            # point someone chose on a map carries no such guarantee: a click
            # in a city centre, on a lake surface or in a desert also finds no
            # reach, and comes back holding whichever unit it landed in. The
            # two cases cannot be told apart from here, so this reports the
            # situation and leaves the answer alone rather than acting on it.
            return OutletCheck(
                True, "no-reach-large",
                f"No mapped river within {search_km:g} km of the outlet, while "
                f"the basin comes back as {basin_area_km2:,.0f} km2. On a "
                "gauge that usually means a coordinate set back from the "
                "mapped channel, and the answer is sound. On a point picked "
                "off a map it can instead mean the point is not on a river at "
                "all -- a street, a lake surface, dry ground -- in which case "
                "what comes back is the catchment of whichever unit contains "
                "it, which may be a river some distance away. Worth checking "
                "that the outlet is where it was meant to be before using "
                "this.",
                basin_area_km2=basin_area_km2,
                notes=["no mapped river near the outlet of a large basin"])
        return OutletCheck(
            True, "no-reach",
            f"No mapped river within {search_km:g} km of the outlet, and the "
            f"basin comes back as {basin_area_km2:,.1f} km2. HydroRIVERS "
            f"carries reaches down to about {NETWORK_FLOOR_KM2:g} km2 of "
            "upstream area, so a genuine headwater at this scale sits below "
            "what this comparison can see, and the DEM backend is the "
            "instrument to use: it routes flow on a 30 m grid. The same two "
            "facts also describe a point that is not on a river -- open "
            "water, a lake surface, ice, dry ground -- where what comes back "
            "is a local hollow in the elevation model rather than a "
            "catchment. Nothing here can tell those two apart; only the "
            "person who placed the point can.",
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

    # Under-capture is the mirror of over-capture, and until now nothing
    # tested for it: a basin can be half of what drains to the river it sits
    # on and still pass, because the ratio above is taken against the largest
    # river in the search box -- near a confluence that is a different and far
    # bigger river, so the ratio is legitimately small for a correct answer.
    # Measured against the river actually at the outlet, the two cases
    # separate cleanly: a correct delineation lands within a few percent of
    # that river's upland area, a truncated one at a fraction of it.
    near_upland = float(near["UPLAND_SKM"])
    near_km = float(near["km"])
    near_ratio = basin_area_km2 / near_upland if near_upland > 0 else float("inf")
    common["nearest_ratio"] = round(near_ratio, 3)

    # The other direction of the same blind spot. Over-capture is measured
    # against the largest river in the search box, and at a confluence that is
    # the river the outlet is NOT on, so a basin can be nine times the stream
    # it sits on and still read as consistent. When the basin matches the
    # larger river instead, the point is simply ambiguous: both answers are
    # real catchments, and only the person who placed the point knows which
    # one was meant.
    if (near_km <= 0.1
            and near_upland >= NETWORK_FLOOR_KM2
            and near_ratio > ratio_limit
            and abs(ratio - 1.0) <= 0.25
            and largest > near_upland * ratio_limit):
        return OutletCheck(
            False, "confluence-ambiguous",
            f"The outlet is within {max(near_km * 1000, 1):.0f} m of two "
            f"channels: one "
            f"draining {near_upland:,.1f} km2 and one draining {largest:,.1f} "
            f"km2. The basin returned is {basin_area_km2:,.1f} km2, which is "
            "the larger of the two. If the smaller stream was meant, move the "
            "point a few hundred metres up that channel, away from the "
            "junction.",
            suggested_area_km2=round(near_upland, 2),
            notes=["outlet sits at a confluence; two catchments are plausible"],
            **common)

    if (near_km <= 0.1
            and near_upland >= NETWORK_FLOOR_KM2
            and near_ratio < 1.0 / ratio_limit):
        return OutletCheck(
            False, "under-captured",
            f"The delineated basin is {basin_area_km2:,.1f} km2 while the "
            f"river at the outlet drains {near_upland:,.1f} km2, so "
            f"{1 - near_ratio:.0%} of the catchment is missing. That points to "
            "the delineation having started from a tributary or a truncated "
            "reach rather than from the channel at the point. Try another "
            "backend, or move the outlet onto the main channel.",
            suggested_area_km2=round(near_upland, 2),
            notes=["returned basin is much smaller than the river at the outlet"],
            **common)

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


# How far a delineation may stand from HydroBASINS' own published upstream
# area before it is reported. This is not a tuned threshold and is not meant to
# be: UP_AREA belongs to a unit's outlet rather than to the clicked point, four
# backends read four different grids, and two of them are a quarter of a
# century apart, so disagreements of tens of percent are ordinary and say
# nothing. A factor of ten is not a disagreement about resolution. Both
# failures this was written for cleared it by a wide margin: a Danube outlet
# that came back as 1.9 km2 against 800,000, and a Thames outlet that came back
# as 73 against 9,948.
MAGNITUDE_FACTOR = 10.0


@dataclass
class MagnitudeCheck:
    """Whether a basin is the right order of magnitude for where it sits."""

    ok: bool
    reason: str
    message: str = ""
    basin_area_km2: float | None = None
    reported_up_area_km2: float | None = None
    unit_area_km2: float | None = None
    hybas_id: int | None = None
    factor: float | None = None

    def __bool__(self) -> bool:
        return self.ok


def check_magnitude(
    lat: float,
    lon: float,
    basin_area_km2: float,
    *,
    factor: float = MAGNITUDE_FACTOR,
    allow_download: bool = False,
) -> MagnitudeCheck:
    """Weigh a basin against HydroBASINS' own published upstream area.

    :func:`check_outlet` is the better instrument and needs HydroRIVERS, which
    is a separate download; where it is absent nothing was checking the answer
    at all. This one reads ``UP_AREA`` out of the HydroBASINS file instead --
    already on disk for anyone who has used the default backend -- and asks
    only whether the two numbers are the same size. It cannot judge a boundary
    and does not try to.

    It is deliberately one-sided about what it concludes: a basin outside the
    band is *reported*, never replaced. Three backends, three grids and a
    coarse reference disagree for legitimate reasons often enough that acting
    on the disagreement would do more harm than naming it.
    """
    from .delineate.hydrobasins import reported_upland_km2

    try:
        ref = reported_upland_km2(lat, lon, allow_download=allow_download)
    except Exception as exc:                                    # noqa: BLE001
        return MagnitudeCheck(True, "check-failed", str(exc)[:200],
                              basin_area_km2=basin_area_km2)
    if ref is None:
        return MagnitudeCheck(
            True, "no-reference",
            "HydroBASINS is not on disk for this region, so the area was not "
            "weighed against its published upstream area.",
            basin_area_km2=basin_area_km2)

    up = float(ref["up_area_km2"])
    common = dict(
        basin_area_km2=basin_area_km2,
        reported_up_area_km2=round(up, 2),
        unit_area_km2=round(float(ref["sub_area_km2"]), 2),
        hybas_id=ref["hybas_id"] or None,
    )
    if basin_area_km2 <= 0:
        return MagnitudeCheck(False, "empty",
                              "The delineated basin has no area.", **common)

    ratio = basin_area_km2 / up
    if ratio < 1.0 / factor:
        return MagnitudeCheck(
            False, "far-too-small",
            f"The delineated basin is {basin_area_km2:,.1f} km2 while "
            f"HydroBASINS puts {up:,.0f} km2 upstream of this point -- a "
            f"factor of {1 / ratio:,.0f}. Two datasets do not differ by that "
            "much over the same ground, so one of the two is describing "
            "somewhere else. Delineate the same point with "
            "backend='hydrobasins' and compare before using this.",
            factor=round(1 / ratio, 1), **common)
    if ratio > factor:
        return MagnitudeCheck(
            False, "far-too-large",
            f"The delineated basin is {basin_area_km2:,.0f} km2 while "
            f"HydroBASINS puts {up:,.0f} km2 upstream of this point -- a "
            f"factor of {ratio:,.0f}. That is the shape of an outlet that "
            "routed onto a larger river than the one at the point. Delineate "
            "the same point with backend='hydrobasins' and compare before "
            "using this.",
            factor=round(ratio, 1), **common)

    return MagnitudeCheck(
        True, "same-order",
        f"The basin is {ratio:.2f} times the {up:,.0f} km2 HydroBASINS "
        "publishes upstream of this point. That reference belongs to the "
        "containing unit's outlet rather than to the point itself, so read "
        "this as an order-of-magnitude agreement and nothing finer.",
        factor=round(ratio, 3), **common)
