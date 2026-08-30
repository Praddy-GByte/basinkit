"""Delineation via the public Global Watersheds API (no download)."""

from __future__ import annotations

from ..cache import get_json
from ..exceptions import DelineationError

_ENDPOINT = "https://mghydro.com/app/watershed_api"


def delineate_api(lat: float, lon: float, *, precision: str = "high", **_):
    """Fetch an upstream basin polygon from the Global Watersheds service.

    No local data is downloaded, which makes this the quickest way to look at a
    basin. The service auto-downgrades to low precision above ~50,000 km2.

    This is a courtesy endpoint run by one research group, not managed
    infrastructure. basinkit therefore never selects it automatically, and
    stamps ``backend='api'`` into provenance so a downstream reader can tell
    that the geometry did not come from a versioned dataset.
    """
    from shapely.geometry import shape
    from shapely.ops import unary_union

    data = get_json(
        _ENDPOINT, params={"lat": lat, "lng": lon, "precision": precision}, timeout=120
    )
    feats = data.get("features") or []
    if not feats:
        raise DelineationError(
            f"The Global Watersheds service returned no basin for ({lat}, {lon}). "
            "The point is probably off the mapped river network, or outside its "
            "60S-85N coverage. Try backend='dem'."
        )

    geom = unary_union([shape(f["geometry"]) for f in feats])
    from ..clip import basin_area_km2

    return geom, {
        "backend": "api",
        "service": "mghydro Global Watersheds",
        "source_dataset": "MERIT-Hydro (~90 m)",
        "precision": precision,
        "outlet": (lat, lon),
        "area_km2": round(basin_area_km2(geom), 2),
        "license_note": (
            "Geometry derived from MERIT-Hydro (CC BY-NC 4.0 / ODbL). Not "
            "redistributable under a permissive licence -- use the "
            "'hydrobasins' backend (CC BY 4.0) for anything you intend to publish."
        ),
    }
