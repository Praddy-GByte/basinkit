"""Regressions for the three faults found in the 0.8.2 QA round.

Vitor Castellar ran the QGIS algorithms against his own reference delineations
in Brazil and reported three separate failures. Each was fixed in 0.8.3 or
0.8.4; each is pinned here, because a fix nobody tests is a fix that comes
back. The fourth test covers the gap those three exposed: a delineation that
returns far less than the river at its outlet used to pass silently, the
mirror of the over-capture case that was already caught.
"""

from __future__ import annotations

import math

import pytest
from shapely.geometry import Polygon

from basinkit.clip import basin_area_km2, laea_crs
from basinkit.verify import OutletCheck


# -------------------------------------------- a northing read as a latitude
def test_a_projected_centroid_is_refused_in_degrees():
    """7,793,981 is a northing in metres, not a latitude.

    Reported from a QGIS layer in a projected CRS: the centroid reached the
    equal-area projection as metres and PROJ failed somewhere far from the
    real mistake. The error now names the mistake at the point it is made.
    """
    with pytest.raises(ValueError) as exc:
        laea_crs(7_793_981.0, 612_345.0)
    message = str(exc.value)
    assert "metres" in message and "degrees" in message
    assert "EPSG:4326" in message, "the message has to say how to fix it"


@pytest.mark.parametrize("lat,lon", [(91.0, 0.0), (-90.5, 0.0), (0.0, 181.0)])
def test_any_centre_outside_the_graticule_is_refused(lat, lon):
    with pytest.raises(ValueError):
        laea_crs(lat, lon)


# ------------------------------------------- the CRS that QGIS could not parse
def test_the_equal_area_crs_is_built_from_a_dict_not_a_proj4_string():
    """Built from a dict so it does not need PROJ to parse a proj4 string.

    Inside QGIS the PROJ that parses such a string is not always the PROJ the
    rest of the stack was built against, which is how this surfaced.
    """
    crs = laea_crs(-19.88, -43.79)
    assert crs.is_projected
    assert "Lambert Azimuthal Equal Area" in crs.coordinate_operation.method_name
    centre = {p.name: p.value for p in crs.coordinate_operation.params}
    assert math.isclose(centre["Latitude of natural origin"], -19.88, abs_tol=1e-6)
    assert math.isclose(centre["Longitude of natural origin"], -43.79, abs_tol=1e-6)


def test_area_km2_is_computed_on_an_equal_area_projection():
    """A square degree at the equator is about 12,363 km2, not 1."""
    square = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    area = basin_area_km2(square)
    assert 12_000 < area < 12_700, area


def test_area_km2_shrinks_with_latitude():
    """The same square degree is much smaller at 60 degrees north."""
    equator = basin_area_km2(Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]))
    high = basin_area_km2(Polygon([(0, 60), (1, 60), (1, 61), (0, 61)]))
    assert high < equator / 1.8, (high, equator)


# ------------------------------------- the boundary that ran past the divide
def test_an_outlet_check_reports_both_directions():
    """Over-capture was caught; under-capture was not, and is the same fault.

    A basin much larger than the river at its outlet means the outlet sits on
    a different river. A basin much smaller means the delineation started
    from a tributary or a truncated reach. Both are wrong answers that used
    to be reported as answers.
    """
    assert OutletCheck(True, "consistent").ok
    assert not OutletCheck(False, "over-captured").ok
    assert not OutletCheck(False, "under-captured").ok


def test_the_outlet_check_carries_the_ratio_against_the_river_at_the_outlet():
    """The ratio against the largest river nearby is not enough.

    Near a confluence the largest river within the search box is a different
    and far bigger river, so a correct basin is legitimately a small fraction
    of it. Only the river actually at the outlet separates a correct answer
    from a truncated one.
    """
    check = OutletCheck(False, "under-captured", basin_area_km2=122.4,
                        nearest_upland_km2=247.3, nearest_ratio=0.495)
    assert check.nearest_ratio is not None
    assert check.nearest_ratio < 0.5
    assert check.suggested_area_km2 is None or check.suggested_area_km2 > 0


# ----------------------------------------------------- against the live data
@pytest.mark.network
def test_the_reported_basin_still_matches_its_published_area():
    """Ribeirao Arrudas, published by the Rio das Velhas committee as 228.37 km2.

    The outlet is the one the committee's own sub-basin drains to. ``auto``
    refines below 2,000 km2 on the elevation model, which is the behaviour the
    QA round was about, and the answer has to stay near a figure nobody in
    this project produced.
    """
    import basinkit as bk

    basin = bk.Basin.from_point(-19.88038, -43.79371)
    published = 228.37
    assert abs(basin.area_km2 - published) / published < 0.08, basin.area_km2
    assert basin.provenance["backend"] == "dem"


@pytest.mark.network
def test_tdx_takes_the_catchment_that_contains_the_outlet():
    """This test used to assert the truncated answer, and has been rewritten.

    When it was written, TDX-Hydro took the reach whose recorded point was
    nearest, which at this outlet is a stub: it returned 122 km2 of a 228 km2
    basin, and the test pinned the fact that the outlet check at least said
    so. The backend now takes the unit catchment that *contains* the outlet,
    so the answer is about 241 km2 and the outlet check passes -- which made
    the old assertion fail for the right reason. What is worth pinning now is
    the agreement itself.

    Note what this episode cost: that stale test was the only cover the
    under-capture branch had, and it is skipped whenever HydroRIVERS is not
    cached, which is most machines. The branch is now unit-tested offline
    below.
    """
    import basinkit as bk
    from basinkit.verify import check_outlet

    basin = bk.Basin.from_point(-19.88038, -43.79371, backend="tdx")
    assert 200.0 < basin.area_km2 < 280.0, basin.area_km2
    assert basin.provenance["outlet_reach_chosen_by"] == "containing catchment"

    check = check_outlet(-19.88038, -43.79371, basin.area_km2,
                         allow_download=False)
    if check.reason in ("not-cached", "no-coverage"):
        pytest.skip("HydroRIVERS is not downloaded, so nothing was checked.")
    assert check.ok, check.message
    assert check.nearest_ratio is not None
    assert 0.8 < check.nearest_ratio < 1.25, check.nearest_ratio


# ------------------------- the outlet-check branches, without a 100 MB download
def _stub_river_network(monkeypatch, reaches, region="sa"):
    """Put a handful of reaches where check_outlet will read them.

    ``reaches`` is ``(upland_km2, lon, lat)`` per reach. Everything else in
    the function -- the distance projection, the nearest and largest picks,
    the branch conditions -- runs for real against them.
    """
    import geopandas as gpd
    from shapely.geometry import Point

    monkeypatch.setattr("basinkit.delineate.hydrobasins.candidate_regions",
                        lambda lat, lon: [region])
    monkeypatch.setattr("basinkit.sources.vectors.RIVER_REGIONS", [region],
                        raising=False)
    monkeypatch.setattr("basinkit.sources.vectors._unpack",
                        lambda *a, **k: "not read; read_file is stubbed")
    frame = gpd.GeoDataFrame(
        {"UPLAND_SKM": [float(r[0]) for r in reaches]},
        geometry=[Point(r[1], r[2]) for r in reaches],
        crs="EPSG:4326",
    )
    monkeypatch.setattr("geopandas.read_file", lambda *a, **k: frame)


def test_a_basin_at_half_of_its_own_river_is_reported(monkeypatch):
    """The failure the TDX stub produced: 122 km2 where 247 drains in."""
    from basinkit.verify import check_outlet

    lat, lon = -19.88038, -43.79371
    _stub_river_network(monkeypatch, [(247.3, lon, lat)])

    check = check_outlet(lat, lon, 122.4, allow_download=True)
    assert not check.ok
    assert check.reason == "under-captured"
    assert check.nearest_ratio < 0.5
    assert check.suggested_area_km2 == 247.3
    assert "missing" in check.message


def test_an_outlet_between_two_channels_is_called_ambiguous(monkeypatch):
    """A basin nine times the stream it sits on used to read as consistent.

    The ratio is taken against the largest river in the search box, and at a
    confluence that is the river the outlet is *not* on.
    """
    from basinkit.verify import check_outlet

    lat, lon = -19.88038, -43.79371
    _stub_river_network(monkeypatch, [
        (247.3, lon, lat),                    # the stream at the point
        (2_269.86, lon + 0.004, lat),         # the trunk, a few hundred metres off
    ])

    check = check_outlet(lat, lon, 2_269.0, allow_download=True)
    assert not check.ok
    assert check.reason == "confluence-ambiguous"
    assert "247.3" in check.message and "2,269.9" in check.message


def test_a_basin_that_matches_its_river_passes(monkeypatch):
    from basinkit.verify import check_outlet

    lat, lon = -19.88038, -43.79371
    _stub_river_network(monkeypatch, [(241.4, lon, lat)])

    check = check_outlet(lat, lon, 241.0, allow_download=True)
    assert check.ok
    assert check.reason == "consistent"


def test_a_basin_many_times_its_river_is_still_reported(monkeypatch):
    """Over-capture, the direction that was already caught. Kept honest."""
    from basinkit.verify import check_outlet

    lat, lon = -19.88038, -43.79371
    _stub_river_network(monkeypatch, [(40.0, lon + 0.012, lat)])

    check = check_outlet(lat, lon, 383.0, allow_download=True)
    assert not check.ok
    assert check.reason == "over-captured"
    assert check.suggested_area_km2 == 40.0
