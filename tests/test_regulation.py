"""Tests for regulation(). Each one names the mistake it is there to stop."""
import types

import pandas as pd
import pytest

from basinkit.regulation import (
    DOR_BANDS,
    ENVELOPE_CAUTION_DOR,
    REGULATED_LAKE,
    RESERVOIR,
    _band,
    regulation,
)


def _lakes(rows):
    return pd.DataFrame(rows, columns=[
        "Lake_name", "Lake_type", "Grand_id", "Lake_area",
        "Vol_total", "Vol_res", "Wshd_area"])


def _rivers(dis, upland):
    return pd.DataFrame({"DIS_AV_CMS": dis, "UPLAND_SKM": upland})


def _basin(area, lakes, rivers):
    b = types.SimpleNamespace()
    b.area_km2 = area
    b.lakes = lambda: lakes
    b.rivers = lambda: rivers
    return b


def test_a_basin_with_only_natural_lakes_is_not_called_regulated():
    """A lake is not a reservoir. Counting every water body as storage would
    make every Himalayan tarn into a dam."""
    b = _basin(3197.7, _lakes([[None, 1, 0, 0.4, 3.39, 0.0, 62.6]]),
               _rivers([50.0], [3000.0]))
    out = regulation(b)
    assert out["reservoirs"] == 0
    assert out["degree_of_regulation_pct"] == 0.0
    assert "no reservoir" in out["statement"]


def test_an_empty_inventory_is_reported_as_absence_not_as_zero():
    """HydroLAKES records water bodies above 10 hectares. Nothing found means
    nothing was recorded, which is not the same as nothing being there."""
    b = _basin(100.0, _lakes([]), _rivers([1.0], [100.0]))
    out = regulation(b)
    assert out["reservoirs"] == 0
    assert "not a survey" in out["statement"]


def test_the_outlet_reach_is_the_largest_upstream_area_not_the_largest_flow():
    """Near a confluence the nearest reach can be a tributary. Picking by
    upstream area picks the main stem."""
    b = _basin(1000.0,
               _lakes([["R", RESERVOIR, 1, 5.0, 500.0, 500.0, 900.0]]),
               _rivers([10.0, 8.0], [950.0, 40.0]))
    out = regulation(b)
    assert out["mean_annual_flow_cms"] == 10.0


def test_summed_upstream_area_is_flagged_when_it_exceeds_the_basin():
    """Two reservoirs in series each count the whole catchment above them.
    Adding them is arithmetic, not area, and the output must say so."""
    b = _basin(1000.0, _lakes([
        ["lower", RESERVOIR, 1, 10.0, 400.0, 400.0, 900.0],
        ["upper", RESERVOIR, 2, 5.0, 200.0, 200.0, 500.0],
    ]), _rivers([10.0], [1000.0]))
    out = regulation(b)
    assert out["summed_upstream_km2"] == 1400.0
    assert out["summed_upstream_exceeds_basin"] is True
    assert out["largest_reservoir_upstream_km2"] == 900.0
    assert "upper bound and not an area" in out["statement"]


def test_degree_of_regulation_is_storage_over_one_years_flow():
    """10 m3/s is 315.6 million m3 a year. Storage of that size is one year's
    flow, and the band below 100 is the one that still says so -- a reservoir
    holding exactly a year is not yet holding more than a year."""
    b = _basin(1000.0,
               _lakes([["R", RESERVOIR, 1, 5.0, 315.36, 315.36, 900.0]]),
               _rivers([10.0], [1000.0]))
    out = regulation(b)
    assert out["degree_of_regulation_pct"] == pytest.approx(100.0, abs=0.5)
    assert out["band"] == "strongly regulated"

    over = _basin(1000.0,
                  _lakes([["R", RESERVOIR, 1, 5.0, 631.2, 631.2, 900.0]]),
                  _rivers([10.0], [1000.0]))
    assert regulation(over)["band"] == "over-year storage"


def test_a_heavily_regulated_basin_withdraws_the_error_figures():
    """The part a tool does not usually say about itself: above the caution
    threshold the honest answer is no error bar, not a wider one."""
    b = _basin(1000.0,
               _lakes([["R", RESERVOIR, 1, 5.0, 2000.0, 2000.0, 900.0]]),
               _rivers([10.0], [1000.0]))
    out = regulation(b)
    assert out["degree_of_regulation_pct"] > ENVELOPE_CAUTION_DOR
    assert "none of those figures is known to have been measured" in out["envelope_note"]


def test_a_lightly_regulated_basin_is_not_given_false_comfort():
    b = _basin(1000.0,
               _lakes([["R", RESERVOIR, 1, 1.0, 3.0, 3.0, 100.0]]),
               _rivers([10.0], [1000.0]))
    out = regulation(b)
    assert out["degree_of_regulation_pct"] < ENVELOPE_CAUTION_DOR
    assert "weak reassurance" in out["envelope_note"]


def test_unknown_flow_is_unknown_and_never_zero():
    """A basin with no modelled reach has an unknown degree of regulation.
    Reporting 0 would read as 'unregulated', which is the opposite."""
    b = _basin(1000.0,
               _lakes([["R", RESERVOIR, 1, 5.0, 500.0, 500.0, 900.0]]),
               _rivers([], []))
    out = regulation(b)
    assert out["degree_of_regulation_pct"] is None
    assert "unknown rather than zero" in out["envelope_note"]


def test_regulated_lakes_count_as_regulation():
    """A natural lake with a control structure holds water on somebody's
    instruction. Type 3 is regulation even though the basin is natural."""
    b = _basin(1000.0,
               _lakes([["L", REGULATED_LAKE, 0, 20.0, 400.0, 100.0, 800.0]]),
               _rivers([10.0], [1000.0]))
    out = regulation(b)
    assert out["reservoirs"] == 1
    assert out["biggest"][0]["type"] == "regulated lake"


def test_the_bands_cover_every_value_without_a_gap():
    """A number that falls between two bands would come back as 'unknown'
    while being perfectly well known."""
    for lo, hi, _ in DOR_BANDS:
        assert _band(lo) != "unknown"
        if hi is not None:
            assert _band(hi - 1e-9) != "unknown"
    assert _band(0.0) != "unknown"
    assert _band(1e6) == "over-year storage"


def test_every_answer_refuses_to_be_read_as_water_availability():
    b = _basin(1000.0,
               _lakes([["R", RESERVOIR, 1, 5.0, 500.0, 500.0, 900.0]]),
               _rivers([10.0], [1000.0]))
    out = regulation(b)
    assert "not measured here" in out["not_measured"]
    assert "Operating rules" in out["not_measured"]
