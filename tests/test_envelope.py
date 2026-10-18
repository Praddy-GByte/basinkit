"""The validation envelope, and the guard that keeps it honest.

The point of the envelope is that the numbers in it are the numbers that were
measured. A table copied into a module is a table that can drift from its
source, so the first two tests here recompute it from the benchmark files in
``verify/benchmarks`` and fail if a single figure has moved.
"""

from __future__ import annotations

import csv
import pathlib

import pytest

from basinkit.envelope import (
    ACCURACY_BY_SIZE,
    EDGE_MEDIAN_PCT,
    INSIDE_MEDIAN_PCT,
    NOT_CHARACTERISED,
    TERRAIN_STUDY,
    TERRAIN_STUDY_GAUGES,
    TERRAIN_STUDY_KM2,
    validation_envelope,
)

BENCHMARKS = pathlib.Path(__file__).resolve().parents[1] / "verify" / "benchmarks"


def _rows(name: str) -> list[dict[str, str]]:
    text = pathlib.Path(BENCHMARKS / name).read_text(encoding="utf-8")
    body = [line for line in text.splitlines() if not line.startswith("#")]
    return list(csv.DictReader(body))


def test_size_table_matches_the_published_benchmark():
    published = _rows("accuracy_by_size.csv")
    assert len(published) == len(ACCURACY_BY_SIZE)
    by_lower = {entry["lower"]: entry for entry in ACCURACY_BY_SIZE}
    for row in published:
        lower = float(row["lower_km2"]) if row["lower_km2"] else None
        assert lower in by_lower, f"no envelope band for lower={lower}"
        entry = by_lower[lower]
        upper = float(row["upper_km2"]) if row["upper_km2"] else None
        assert entry["upper"] == upper
        assert entry["median_error_pct"] == float(row["median_error_pct"])
        assert entry["within_20_pct"] == int(row["within_20_pct"])
        assert entry["within_5_pct"] == int(row["within_5_pct"])


def test_terrain_ranges_match_the_grade_validation_run():
    rows = [r for r in _rows("grade_validation.csv")
            if r["relief_ratio"] not in ("", "nan")]
    assert len(rows) == TERRAIN_STUDY_GAUGES
    areas = [float(r["reported_area_km2"]) for r in rows]
    assert (round(min(areas), 1), round(max(areas), 1)) == TERRAIN_STUDY_KM2

    columns = {"filling": "filling_pct", "slope": "slope_below_floor_pct",
               "water": "water_pct", "relief": "relief_ratio",
               "coverage": "coverage_pct"}
    assert set(columns) == set(TERRAIN_STUDY)
    for axis, column in columns.items():
        values = sorted(float(r[column]) for r in rows)
        ref = TERRAIN_STUDY[axis]

        def q(p, values=values):
            return values[int(round(p * (len(values) - 1)))]

        assert ref["min"] == pytest.approx(values[0], abs=0.005)
        assert ref["max"] == pytest.approx(values[-1], abs=0.005)
        for p, key in ((0.05, "p05"), (0.5, "p50"), (0.95, "p95")):
            assert ref[key] == pytest.approx(q(p), abs=0.005), f"{axis} {key}"


def test_the_small_basin_is_told_the_error_measured_at_its_size():
    # The whole reason the module exists: 181% is in the published table and
    # was never in the output.
    out = validation_envelope(area_km2=61.0)
    assert out["position"] == "outside"
    assert out["size"]["median_error_pct"] == 181.0
    assert out["size"]["within_5_pct"] == 0
    assert "181%" in out["axes"][0]["statement"]
    assert "not the figure basinkit is usually quoted for" in out["statement"]


@pytest.mark.parametrize("area_km2,position", [
    (1.0, "outside"),          # 181% median
    (99.999, "outside"),
    (100.0, "outside"),        # 30% median
    (499.0, "outside"),
    (500.0, "edge"),           # 8.9% median
    (1999.0, "edge"),
    (2000.0, "inside"),        # 1.7% median
    (9999.0, "inside"),
    (10000.0, "inside"),       # 1.3%
    (100000.0, "inside"),      # 0.3%
    (3_000_000.0, "inside"),
])
def test_every_size_lands_in_the_band_the_table_gives_it(area_km2, position):
    out = validation_envelope(area_km2=area_km2)
    assert out["position"] == position
    band = out["size"]
    if position == "inside":
        assert band["median_error_pct"] <= INSIDE_MEDIAN_PCT
    elif position == "edge":
        assert INSIDE_MEDIAN_PCT < band["median_error_pct"] <= EDGE_MEDIAN_PCT
    else:
        assert band["median_error_pct"] > EDGE_MEDIAN_PCT


def test_the_bands_are_contiguous_and_cover_every_area():
    ordered = sorted(ACCURACY_BY_SIZE,
                     key=lambda e: (e["lower"] is not None, e["lower"] or 0.0))
    assert ordered[0]["lower"] is None
    assert ordered[-1]["upper"] is None
    for lower, upper in zip(ordered, ordered[1:], strict=False):
        assert lower["upper"] == upper["lower"]


def _suitability(**measured):
    defaults = {"filling": 7.6, "slope": 66.9, "water": 0.05,
                "relief": 131.2, "coverage": 0.0}
    defaults.update(measured)
    return {"grade": "HIGH",
            "tests": [{"test": name, "measured": value, "verdict": "pass",
                       "evaluated": True}
                      for name, value in defaults.items()]}


def test_a_suitability_result_adds_the_terrain_axes():
    out = validation_envelope(area_km2=8805.0, suitability=_suitability())
    axes = {a["axis"] for a in out["axes"]}
    assert axes == {"size", "filling", "slope", "water", "relief", "coverage"}
    assert out["position"] == "inside"
    assert out["outside"] == [] and out["edge"] == []


def test_a_void_in_the_basin_puts_it_outside_the_set():
    # Every basin in the terrain study was fully covered, so missing
    # elevation is outside by definition rather than merely unusual.
    out = validation_envelope(area_km2=8805.0, suitability=_suitability(coverage=3.0))
    assert out["position"] == "outside"
    assert out["outside"] == ["coverage"]


def test_a_descriptor_in_the_tail_is_reported_as_the_edge():
    out = validation_envelope(area_km2=8805.0, suitability=_suitability(water=4.0))
    assert out["position"] == "edge"
    assert out["edge"] == ["water"]


def test_heavy_filling_carries_the_measured_direction_and_not_a_factor():
    out = validation_envelope(area_km2=8805.0, suitability=_suitability(filling=30.0))
    filling = next(a for a in out["axes"] if a["axis"] == "filling")
    assert "two to three times" in filling["statement"]
    assert "direction and not as a factor" in filling["statement"]


def test_a_test_that_was_not_evaluated_is_not_compared():
    result = _suitability()
    for entry in result["tests"]:
        if entry["test"] == "filling":
            entry["evaluated"] = False
    out = validation_envelope(area_km2=8805.0, suitability=result)
    assert "filling" not in {a["axis"] for a in out["axes"]}


def test_the_uncharacterised_conditions_are_always_named():
    for area in (61.0, 8805.0, 250000.0):
        out = validation_envelope(area_km2=area)
        named = [entry["axis"] for entry in NOT_CHARACTERISED]
        assert [e["axis"] for e in out["not_characterised"]] == named
        for axis in named:
            assert axis in out["statement"]
        for entry in out["not_characterised"]:
            assert entry["why"] and entry["measure"]


def test_the_envelope_does_not_claim_to_check_the_boundary():
    out = validation_envelope(area_km2=8805.0)
    assert "check_outlet" in out["note"]
    assert "suitability" in out["note"]


def test_it_refuses_to_guess_an_area():
    with pytest.raises(TypeError):
        validation_envelope()


def test_an_explicit_area_wins_over_the_basin():
    class Stub:
        area_km2 = 250000.0

    assert validation_envelope(Stub())["size"]["median_error_pct"] == 0.3
    assert validation_envelope(Stub(), area_km2=61.0)["size"][
        "median_error_pct"] == 181.0


def test_the_two_kinds_of_outside_are_worded_differently():
    # A 135 km2 basin was measured -- at 30% -- so saying nothing resembled
    # it would be false. A basin with a void in it was measured by nothing.
    by_size = validation_envelope(area_km2=135.0)
    assert "did measure basins of this size" in by_size["statement"]
    assert "resembled this one" not in by_size["statement"]

    by_descriptor = validation_envelope(area_km2=8805.0,
                                        suitability=_suitability(coverage=3.0))
    assert "no basin in the terrain study resembled this one" in \
        by_descriptor["statement"]
    assert "did measure basins of this size" not in by_descriptor["statement"]
