"""Concentration time: six empirical formulas, and the spread between them.

Each is recomputed here from its published definition rather than compared
against a stored number, so a change to the implementation has to survive the
equation and not merely a snapshot of whatever it produced last.
"""

from __future__ import annotations

import math

import pytest

from basinkit.response import METHODS, concentration_time

# A basin with every input the formulas need. The values are the Ribeirao
# Arrudas run, so the test exercises a real combination rather than round
# numbers that hide an exponent mistake.
MORPH = {
    "areal": {"area_km2": 234.854},
    "linear": {"main_channel_length_km": 24.297, "basin_length_km": 22.147},
    "relief": {
        "channel_gradient_m_per_km": 13.725,
        "elevation_mean_m": 1004.7,
        "elevation_min_m": 709.8,
        "main_channel_relief_m": 333.5,
    },
}

A = MORPH["areal"]["area_km2"]
L_KM = MORPH["linear"]["main_channel_length_km"]
L_M = L_KM * 1000.0
S = MORPH["relief"]["channel_gradient_m_per_km"] / 1000.0
H = MORPH["relief"]["main_channel_relief_m"]
DZ = MORPH["relief"]["elevation_mean_m"] - MORPH["relief"]["elevation_min_m"]


@pytest.fixture(scope="module")
def result():
    return concentration_time(MORPH)


def test_kirpich_matches_its_definition(result):
    assert result["estimates"]["kirpich_min"] == pytest.approx(
        0.0195 * L_M ** 0.77 * S ** -0.385, rel=1e-3)


def test_california_matches_its_definition(result):
    assert result["estimates"]["california_min"] == pytest.approx(
        60 * (0.871 * L_KM ** 3 / H) ** 0.385, rel=1e-3)


def test_kirpich_and_california_are_the_same_equation(result):
    """They agree by construction here, not by corroboration.

    California uses the relief of the watercourse where Kirpich uses its
    slope, and morphometry() computes that slope as relief over length. The
    two are then algebraically identical, and counting both as independent
    estimates would overstate how much the methods agree.
    """
    # Not bit-identical: morphometry() hands over a gradient already rounded
    # to three decimals, so the two forms of one equation part company in the
    # fifth significant figure. They agree far closer than any two genuinely
    # different formulas here, which disagree by factors.
    assert result["estimates"]["kirpich_min"] == pytest.approx(
        result["estimates"]["california_min"], rel=1e-3)
    assert result["n_distinct_values"] < result["n_formulas"]
    assert "same equation" in result["note"]
    assert "Algebraically identical to Kirpich" in METHODS["california"]["caution"]


def test_giandotti_matches_its_definition(result):
    assert result["estimates"]["giandotti_min"] == pytest.approx(
        60 * (4 * math.sqrt(A) + 1.5 * L_KM) / (0.8 * math.sqrt(DZ)), rel=1e-3)


def test_ventura_matches_its_definition(result):
    assert result["estimates"]["ventura_min"] == pytest.approx(
        60 * 0.1272 * math.sqrt(A / S), rel=1e-3)


def test_temez_matches_its_definition(result):
    assert result["estimates"]["temez_min"] == pytest.approx(
        60 * 0.3 * (L_KM / S ** 0.25) ** 0.76, rel=1e-3)


def test_bransby_williams_matches_its_definition(result):
    assert result["estimates"]["bransby_williams_min"] == pytest.approx(
        0.605 * L_KM / (A ** 0.1 * (S * 100) ** 0.2) * 60, rel=1e-3)


def test_the_spread_is_reported_and_is_large(result):
    values = list(result["estimates"].values())
    assert result["shortest_min"] == pytest.approx(min(values))
    assert result["longest_min"] == pytest.approx(max(values))
    assert result["spread_factor"] == pytest.approx(max(values) / min(values),
                                                    rel=1e-3)
    assert result["spread_factor"] > 2, (
        "on a real basin these formulas disagree by a factor of several, and "
        "a tool that returns one number has hidden that")


def test_lag_time_is_six_tenths_of_the_median(result):
    assert result["lag_time_min"] == pytest.approx(
        round(0.6 * result["median_min"], 1), abs=1e-9), (
        "the lag and the median are both reported to a tenth of a minute, so "
        "they have to agree at that precision")


def test_every_method_declares_what_it_was_fitted_to():
    for name, entry in METHODS.items():
        assert entry["citation"], name
        assert entry["fitted_to"], name
        assert entry["caution"], name


def test_the_inputs_are_returned_so_the_numbers_can_be_checked(result):
    assert result["inputs"]["area_km2"] == A
    assert result["inputs"]["main_channel_length_km"] == L_KM
    assert result["inputs"]["channel_slope_m_per_m"] == pytest.approx(S, rel=1e-4)


def test_a_basin_with_no_channel_says_so_rather_than_guessing():
    with pytest.raises(ValueError, match="main_channel_length_km"):
        concentration_time({"areal": {"area_km2": 10.0},
                            "linear": {"basin_length_km": 3.0},
                            "relief": {}})


def test_no_usable_slope_is_refused_rather_than_returned_empty():
    with pytest.raises(ValueError, match="No formula could be evaluated"):
        concentration_time({
            "areal": {"area_km2": 10.0},
            "linear": {"main_channel_length_km": 5.0, "basin_length_km": 3.0},
            "relief": {},
        })
