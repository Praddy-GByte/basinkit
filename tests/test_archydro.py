"""Arc Hydro export: a renaming, so the test is that nothing is invented.

No network. Every frame here is built by hand, so a wrong identifier or a lost
value is a defect in basinkit and nothing else.
"""

from __future__ import annotations

import pytest

pytest.importorskip("geopandas")

import geopandas as gpd  # noqa: E402
from shapely.geometry import LineString, Polygon  # noqa: E402

from basinkit import archydro as AH  # noqa: E402


def _box(i):
    return Polygon([(i, 0), (i + 1, 0), (i + 1, 1), (i, 1)])


def _catchments():
    """Four units: 3 and 4 drain into 2, 2 drains into 1, 1 is the outlet."""
    return gpd.GeoDataFrame(
        {"HYBAS_ID": [7120409910, 7120412090, 7120412250, 7120412100],
         "NEXT_DOWN": [0, 7120409910, 7120412090, 7120412090],
         "SUB_AREA": [156.3, 21.5, 39.2, 248.8],
         "UP_AREA": [465.8, 309.5, 39.2, 248.8]},
        geometry=[_box(i) for i in range(4)], crs="EPSG:4326")


def _rivers():
    return gpd.GeoDataFrame(
        {"HYRIV_ID": [70422326, 70422327, 70422914],
         "NEXT_DOWN": [70422914, 70422914, 0],
         "LENGTH_KM": [1.2, 3.4, 5.6]},
        geometry=[LineString([(i, 0), (i + 1, 1)]) for i in range(3)],
        crs="EPSG:4326")


def test_hydroid_is_compact_and_unique():
    c = AH.catchment_table(_catchments())
    assert sorted(c["HydroID"]) == [1, 2, 3, 4]
    assert c["HydroID"].is_unique


def test_the_original_identifier_survives_in_hydrocode():
    src = _catchments()
    c = AH.catchment_table(src)
    assert list(c["HydroCode"]) == [str(v) for v in src["HYBAS_ID"]]
    # and it is a string, because HydroCode is a public code, not a number
    assert all(isinstance(v, str) for v in c["HydroCode"])


def test_nextdownid_points_at_the_hydroid_of_the_downstream_unit():
    c = AH.catchment_table(_catchments()).set_index("HYBAS_ID")
    hid = dict(zip(c.index, c["HydroID"]))
    assert c.loc[7120412090, "NextDownID"] == hid[7120409910]
    assert c.loc[7120412250, "NextDownID"] == hid[7120412090]
    assert c.loc[7120412100, "NextDownID"] == hid[7120412090]


def test_the_outlet_gets_minus_one():
    c = AH.catchment_table(_catchments()).set_index("HYBAS_ID")
    assert c.loc[7120409910, "NextDownID"] == AH.NO_DOWNSTREAM == -1


def test_a_pointer_outside_the_set_also_becomes_minus_one():
    """The basin's own outlet drains to a unit that was never walked."""
    src = _catchments()
    src.loc[0, "NEXT_DOWN"] = 7120400000            # a real id, not in this set
    c = AH.catchment_table(src)
    assert c.loc[0, "NextDownID"] == AH.NO_DOWNSTREAM


def test_areasqkm_is_the_source_value_unchanged():
    src = _catchments()
    c = AH.catchment_table(src)
    assert list(c["AreaSqKm"]) == list(src["SUB_AREA"])


def test_nothing_from_the_source_is_dropped():
    src = _catchments()
    c = AH.catchment_table(src)
    assert set(src.columns) <= set(c.columns)
    assert len(c) == len(src)


def test_drainid_is_not_invented():
    c = AH.catchment_table(_catchments())
    r = AH.drainage_line_table(_rivers())
    assert "DrainID" not in c.columns
    assert "DrainID" not in r.columns


def test_drainage_lines_get_the_same_treatment():
    r = AH.drainage_line_table(_rivers()).set_index("HYRIV_ID")
    assert r.loc[70422914, "NextDownID"] == AH.NO_DOWNSTREAM
    assert r.loc[70422326, "NextDownID"] == r.loc[70422327, "NextDownID"]
    assert r.loc[70422326, "NextDownID"] == int(
        AH.drainage_line_table(_rivers()).set_index("HYRIV_ID")
        .loc[70422914, "HydroID"])
    assert r.loc[70422327, "LengthKm"] == 3.4


def test_a_missing_source_field_is_named_rather_than_guessed():
    src = _catchments().drop(columns=["NEXT_DOWN"])
    with pytest.raises(ValueError, match="NEXT_DOWN"):
        AH.catchment_table(src)
    with pytest.raises(ValueError, match="HYRIV_ID"):
        AH.drainage_line_table(_rivers().drop(columns=["HYRIV_ID"]))


def test_check_passes_a_single_tree():
    chk = AH.check(AH.catchment_table(_catchments()))
    assert chk == {"units": 4, "terminal_units": 1, "dangling_next_down": 0,
                   "units_in_a_cycle": 0, "single_outlet": True}


def test_check_reports_two_outlets_rather_than_hiding_them():
    src = _catchments()
    src.loc[3, "NEXT_DOWN"] = 0                     # a second terminal unit
    chk = AH.check(AH.catchment_table(src))
    assert chk["terminal_units"] == 2
    assert chk["single_outlet"] is False


def test_check_reports_a_cycle():
    src = _catchments()
    src.loc[0, "NEXT_DOWN"] = 7120412090            # 1 -> 2 -> 1
    chk = AH.check(AH.catchment_table(src))
    assert chk["units_in_a_cycle"] > 0
    assert chk["single_outlet"] is False


def test_check_reports_a_dangling_pointer():
    """A NEXT_DOWN that names a unit outside this set is not dangling: it is the
    basin outlet and becomes -1. A HydroID that is not in the table is."""
    c = AH.catchment_table(_catchments())
    c.loc[1, "NextDownID"] = 999
    chk = AH.check(c)
    assert chk["dangling_next_down"] == 1
    assert chk["single_outlet"] is False


def test_geometry_is_untouched():
    src = _catchments()
    c = AH.catchment_table(src)
    assert c.crs == src.crs
    assert all(a.equals(b) for a, b in zip(c.geometry, src.geometry))
