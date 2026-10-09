"""The SCS curve number, and the two judgements it rests on.

Neither judgement is defensible in silence: the hydrologic soil group comes
from texture rather than a soil survey, and ESA WorldCover's classes are not
the cover types TR-55 tabulates. Both are returned with the number, and these
tests hold them to that.
"""

from __future__ import annotations

import pytest

from basinkit.runoff import COVER_CN, TEXTURE_HSG, usda_texture

HSG_LETTERS = {"A", "B", "C", "D"}


# ------------------------------------------------------- the texture triangle
@pytest.mark.parametrize("sand,clay,expected", [
    (92, 3, "sand"),
    (82, 6, "loamy sand"),
    (65, 10, "sandy loam"),
    (40, 18, "loam"),
    (20, 15, "silt loam"),
    (10, 5, "silt"),
    (60, 28, "sandy clay loam"),
    (32, 32, "clay loam"),
    (10, 33, "silty clay loam"),
    (52, 42, "sandy clay"),
    (6, 47, "silty clay"),
    (20, 55, "clay"),
])
def test_usda_texture_at_the_centre_of_each_class(sand, clay, expected):
    assert usda_texture(sand, clay) == expected


def test_every_texture_class_has_a_soil_group():
    """A texture with no group would silently drop cells from the composite."""
    produced = set()
    for sand in range(0, 101, 2):
        for clay in range(0, 101 - sand, 2):
            produced.add(usda_texture(sand, clay))
    missing = produced - set(TEXTURE_HSG)
    assert not missing, f"no hydrologic soil group for {sorted(missing)}"


def test_the_groups_run_sand_to_clay():
    """Sandy soils take water fastest, clays slowest. A is fast, D is slow."""
    assert TEXTURE_HSG["sand"] == "A"
    assert TEXTURE_HSG["clay"] == "D"
    assert set(TEXTURE_HSG.values()) <= HSG_LETTERS


def test_texture_is_stable_either_side_of_a_boundary():
    """Two neighbouring compositions must not jump two groups apart."""
    order = {"A": 0, "B": 1, "C": 2, "D": 3}
    for sand in range(0, 96, 5):
        for clay in range(0, 96 - sand, 5):
            here = order[TEXTURE_HSG[usda_texture(sand, clay)]]
            there = order[TEXTURE_HSG[usda_texture(sand + 2, clay)]]
            assert abs(here - there) <= 2, (sand, clay)


# ------------------------------------------------------------ the TR-55 table
def test_the_cover_table_is_well_formed():
    for code, (label, values) in COVER_CN.items():
        assert isinstance(code, int)
        assert label, code
        assert len(values) == 4, f"{code} needs a curve number per soil group"
        assert all(0 < v <= 100 for v in values), code


def test_curve_numbers_rise_from_group_a_to_group_d():
    """Within one cover type, slower soil cannot produce less runoff."""
    for code, (label, values) in COVER_CN.items():
        assert list(values) == sorted(values), f"{label} ({code}) is out of order"


def test_sealed_and_bare_surfaces_shed_more_than_woods():
    woods = COVER_CN[10][1]
    built = COVER_CN[50][1]
    bare = COVER_CN[60][1]
    for i in range(4):
        assert built[i] > woods[i]
        assert bare[i] > woods[i]


def test_water_sheds_everything():
    for code in (80, 90):
        assert COVER_CN[code][1] == (98, 98, 98, 98)


def test_every_worldcover_class_in_the_table_is_a_real_one():
    from basinkit.sources.landcover import WORLDCOVER_CLASSES as classes

    unknown = set(COVER_CN) - set(classes)
    assert not unknown, f"not ESA WorldCover classes: {sorted(unknown)}"


# ------------------------------------------- antecedent moisture and retention
@pytest.mark.parametrize("cn", [40.0, 60.0, 77.6, 90.0])
def test_the_moisture_conversions_bracket_the_average_condition(cn):
    """Chow's relations: dry is below the average, wet above it."""
    amc_i = 4.2 * cn / (10 - 0.058 * cn)
    amc_iii = 23 * cn / (10 + 0.13 * cn)
    assert amc_i < cn < amc_iii
    assert 0 < amc_i < 100
    assert 0 < amc_iii <= 100


@pytest.mark.parametrize("cn,retention_mm", [
    (100.0, 0.0),
    (80.0, 63.5),
    (50.0, 254.0),
])
def test_potential_retention_follows_the_tr55_definition(cn, retention_mm):
    assert 25400.0 / cn - 254.0 == pytest.approx(retention_mm, abs=0.01)


def test_initial_abstraction_is_a_fifth_of_the_retention():
    s = 25400.0 / 77.6 - 254.0
    assert 0.2 * s == pytest.approx(14.67, abs=0.05)
