"""Upstream basin delineation backends.

Three backends, because no single one is right for every basin:

``hydrobasins``
    Graph traversal over HydroBASINS level-12 sub-basins. Global, CC BY 4.0,
    offline once cached, and fast at any basin size because upstream
    aggregation is a walk over the ``NEXT_DOWN`` field rather than a raster
    fill.

    **Base grid: 15 arc-seconds, about 460 m, from February 2000 SRTM.**
    HydroBASINS is extracted from the HydroSHEDS core layers at that
    resolution, so this backend inherits it. Two consequences worth stating
    plainly: the resolution floor is the level-12 unit (~130 km2 median), and
    the flow network is a quarter-century-old DEM. For most basins that is
    fine. For a small or heavily modified catchment it is not, and the other
    two backends exist for exactly that case.

``dem``
    D8 flow routing with ``pyflwdir`` over a freshly downloaded Copernicus DEM
    window. **Base grid: 1 arc-second, about 30 m, from 2011-2015 radar.**
    Fifteen times finer than the default and a decade newer, so it is the right
    instrument for small catchments; its working range reaches about
    10,000 km2, since cost grows with basin area and the window has to contain
    the whole basin.

``api``
    The public Global Watersheds service, backed by MERIT-Hydro.
    **Base grid: 3 arc-seconds, about 90 m, multi-error-removed.** Five times
    finer than the default and hydrologically conditioned rather than raw SRTM.
    No download at all, so it is the fastest first look -- but it is one
    research group's server and MERIT-Hydro's licence is non-commercial, so
    basinkit never makes it the default and records both facts in provenance.

``auto`` picks between them from the drainage area implied by the outlet.

Base resolution, side by side:

===============  =================  ==================  ====================
backend          grid               source              conditioned
===============  =================  ==================  ====================
``hydrobasins``  15 arc-sec, 460 m  SRTM, Feb 2000      HydroSHEDS
``api``          3 arc-sec, 90 m    MERIT-Hydro         yes, error-removed
``dem``          1 arc-sec, 30 m    Copernicus, 2011-15  no, routed on the fly
===============  =================  ==================  ====================
"""

from .api import delineate_api
from .dem import delineate_dem
from .hydrobasins import delineate_hydrobasins
from .tdx import delineate_tdx

__all__ = ["delineate_api", "delineate_dem", "delineate_hydrobasins", "delineate"]

_BACKENDS = {
    "hydrobasins": delineate_hydrobasins,
    "dem": delineate_dem,
    "api": delineate_api,
    "tdx": delineate_tdx,
}

#: Backends that ``auto`` will never reach for on its own. TDX-Hydro is
#: CC BY-SA: a derivative redistributed from it inherits the ShareAlike
#: obligation, and every other default here is CC BY 4.0 or more permissive.
#: Inheriting a copyleft term is a decision to take deliberately, not one to
#: discover in a licence report afterwards.
_OPT_IN = ("tdx",)


def delineate(lat: float, lon: float, backend: str = "auto", **kwargs):
    """Delineate the upstream basin of ``(lat, lon)``.

    Returns
    -------
    (shapely.geometry, dict)
        The basin polygon in EPSG:4326 and a provenance dict recording which
        backend and dataset version produced it. The provenance travels with
        the basin so a result is always attributable.
    """
    if backend == "auto":
        return _auto(lat, lon, **kwargs)
    try:
        fn = _BACKENDS[backend]
    except KeyError:
        raise ValueError(
            f"Unknown backend {backend!r}. Choose from: "
            f"{', '.join(_BACKENDS)} or 'auto'."
        ) from None
    return fn(lat, lon, **kwargs)


def _auto(lat: float, lon: float, **kwargs):
    """HydroBASINS first, with the resolution range covered at both ends.

    A level-12 sub-basin averages about 130 km2, and both ends of that scale
    need attention.

    **Below it.** A result of a single unit means the outlet sits inside a
    headwater cell, finer than the sub-basin grid describes, so the DEM answers
    instead. That route has been here since the first release.

    **Across it.** An outlet on a small stream falls inside a unit whose own
    outlet may be on the trunk river, and the polygon returned is then the
    trunk's catchment. The geometry alone gives no sign of this, since the
    traversal is exact either way and the dataset's ``UP_AREA`` agrees with the
    assembled area to within one percent on 95 percent of stations.

    So the river network is consulted, and the answer is refined only when two
    independent sources agree on a smaller catchment: the largest river near
    the outlet drains far less than the polygon covers, *and* a DEM delineation
    of the same point lands within a factor of two of that river's upstream
    area. Across 300 gauges drawn after this was designed, that combination
    improved 19 results, left 279 unchanged and reduced none. Where the network
    raises the question and the DEM does not corroborate, the sub-basin polygon
    stands and the question is reported, which is the more conservative of the
    two available answers.
    """
    import warnings as _warnings

    from ..exceptions import DelineationError

    min_area = kwargs.pop("min_area_km2", 25.0)
    # True checks only when the river network is already on disk; 'download'
    # fetches it if needed; False skips the check entirely.
    verify = kwargs.pop("verify", True)
    # A DEM window covers a catchment of a few thousand square kilometres, so
    # a suggested area above this is outside the backend's working range and
    # the sub-basin route stays authoritative.
    dem_ceiling = kwargs.pop("dem_ceiling_km2", 5_000.0)
    # The check searches 2 km so that a gauge sitting a little off the trunk
    # still finds its own river. Acting on what it finds is a stricter
    # question: a river a kilometre away is not the river the click is on, and
    # a DEM delineation of that click describes the same local drain, so the
    # two sources stop being independent.
    #
    # Measured: all 25 corrective switches that were right had their
    # corroborating reach within 0.91 km, median 0.15 km. Five places where
    # refinement would not have helped -- a city centre, a lake surface, a
    # desert, an Arctic island -- all had theirs beyond 1.3 km. The gate only
    # ever holds a refinement back, so its cost is a refinement not made.
    act_within_km = kwargs.pop("act_within_km", 1.0)

    try:
        geom, prov = delineate_hydrobasins(lat, lon, **kwargs)
    except DelineationError:
        return delineate_dem(lat, lon, **kwargs)

    area = prov.get("area_km2", 1e9)

    if area < min_area:
        # A single level-12 unit means the outlet is inside a headwater cell,
        # finer than the sub-basin grid resolves. Refine on the DEM.
        try:
            return delineate_dem(lat, lon, **kwargs)
        except Exception:
            prov["note"] = (
                "This catchment is at the scale of a single level-12 sub-basin, "
                "so the polygon is that unit. The DEM backend resolves finer "
                "when a 30 m window is available for this location."
            )
        return geom, prov

    if not verify:
        return geom, prov

    from ..verify import check_outlet

    try:
        # allow_download stays False by default so that asking for a basin
        # never silently starts a few hundred megabytes of river network. When
        # the network is already cached -- which it is for anyone who has drawn
        # rivers or run morphometry -- the check runs for free. Callers that
        # want it either way pass verify='download'.
        check = check_outlet(
            lat, lon, area,
            progress=kwargs.get("progress", False),
            allow_download=(verify == "download"),
        )
    except Exception:
        return geom, prov

    prov["outlet_check"] = {
        "ok": check.ok, "reason": check.reason, "ratio": check.ratio,
        "largest_river_upland_km2": check.largest_upland_km2,
    }
    if check.ok:
        if check.reason == "no-reach":
            prov["note"] = check.message
        return geom, prov

    # Only the ratio check offers a corroborating figure to test the DEM
    # against. The orphan-outlet check has none by construction -- it fires
    # because nothing is mapped nearby -- so it warns and changes nothing.
    # Switching on it was tried and helped 7 of 9 while breaking a correct
    # answer, which on nine stations is not evidence.
    suggested = check.suggested_area_km2 or 0.0
    too_far = (check.largest_distance_km is not None
               and check.largest_distance_km > act_within_km)
    if too_far:
        prov["warning"] = (
            check.message + " The nearest river large enough to judge this by "
            f"is {check.largest_distance_km:.1f} km from the outlet, far enough "
            "that it describes a different place, so the sub-basin result "
            "stands. Placing the outlet on the mapped river gives the network "
            "something to confirm it against."
        )
        _warnings.warn(prov["warning"], stacklevel=2)
        return geom, prov

    if 0 < suggested <= dem_ceiling:
        try:
            # Bound the corrective attempt. The check only fires with a
            # suggested area under dem_ceiling, and a basin that size fits in a
            # window well under a degree, so there is no reason to let the DEM
            # backend double its window up to four degrees hunting for a divide
            # that is not there. Without this cap a false alarm -- about one
            # call in twenty-five -- costs eighteen seconds and changes
            # nothing; with it, a few.
            probe = dict(kwargs)
            probe.setdefault("window_deg", 0.25)
            probe["max_window_deg"] = 1.0
            dem_geom, dem_prov = delineate_dem(lat, lon, **probe)
            dem_area = float(dem_prov.get("area_km2") or 0.0)
            agrees = (dem_area > 0 and suggested > 0
                      and max(dem_area, suggested) / min(dem_area, suggested) < 2.0)
            if agrees:
                dem_prov["outlet_check"] = prov["outlet_check"]
                dem_prov["switched_from"] = {
                    "backend": "hydrobasins",
                    "area_km2": round(area, 2),
                    "reason": (
                        f"The HydroBASINS polygon was {check.ratio:.0f} times "
                        f"the {suggested:,.0f} km2 draining to the largest "
                        "river within 1 km of the outlet, and this DEM "
                        f"delineation of {dem_area:,.1f} km2 agrees with that "
                        "river. Two independent sources against one."
                    ),
                }
                _warnings.warn(dem_prov["switched_from"]["reason"], stacklevel=2)
                return dem_geom, dem_prov
        except Exception:
            pass

    prov["warning"] = check.message
    _warnings.warn(check.message, stacklevel=2)
    return geom, prov
