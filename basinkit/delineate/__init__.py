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
    answer for small catchments, and the wrong one for large ones: cost grows
    with basin area and the window must contain the whole basin.

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

__all__ = ["delineate_api", "delineate_dem", "delineate_hydrobasins", "delineate"]

_BACKENDS = {
    "hydrobasins": delineate_hydrobasins,
    "dem": delineate_dem,
    "api": delineate_api,
}


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
    """Prefer HydroBASINS; fall back to the DEM router for tiny headwaters."""
    from ..exceptions import DelineationError

    min_area = kwargs.pop("min_area_km2", 25.0)
    try:
        geom, prov = delineate_hydrobasins(lat, lon, **kwargs)
    except DelineationError:
        return delineate_dem(lat, lon, **kwargs)

    if prov.get("area_km2", 1e9) < min_area:
        # A single level-12 unit means the outlet is inside a headwater cell and
        # HydroBASINS cannot see the real divide. Refine on the DEM.
        try:
            return delineate_dem(lat, lon, **kwargs)
        except Exception:
            prov["warning"] = (
                "Basin is at the HydroBASINS level-12 resolution floor and DEM "
                "refinement failed; the polygon may be a whole level-12 unit "
                "rather than the true upstream area."
            )
    return geom, prov
