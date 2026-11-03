"""Permanent snow and ice: the measurement, and the four things it is not.

The tests that matter here are not the arithmetic. They are the refusals: a
basin outside the land-cover product's latitudes must not read as zero ice, an
ice fraction must never be presented as a meltwater fraction, and a share
measured at 80 degrees north must be computed by area rather than by counting
cells -- which is where the glaciers are, and where the two answers differ
most.
"""

from __future__ import annotations

import numpy as np
import pytest

rioxarray = pytest.importorskip("rioxarray")
xr = pytest.importorskip("xarray")

from basinkit.snow import (  # noqa: E402
    FLOOR_OUTLIER_M,
    ICE_FLOOR_PERCENTILE,
    SNOW_ICE_CLASS,
    TRACE_PCT,
    WORLDCOVER_LAT_RANGE,
    _atlas_block,
    snow_ice,
)


def _raster(values, *, lat0=28.0, lon0=85.0, res=0.01, dtype="float32"):
    """A small georeferenced grid, in degrees, like the ones basinkit fetches."""
    values = np.asarray(values, dtype=dtype)
    rows, cols = values.shape
    y = lat0 - res * (np.arange(rows) + 0.5)
    x = lon0 + res * (np.arange(cols) + 0.5)
    da = xr.DataArray(values, dims=("y", "x"), coords={"y": y, "x": x})
    return da.rio.write_crs("EPSG:4326")


class _Basin:
    """Only the three things snow_ice() reads off a Basin."""

    def __init__(self, cover, dem=None, *, lat=28.0, lon=85.0, km2=1000.0):
        self._cover, self._dem = cover, dem
        self.centroid = (lat, lon)
        self.area_km2 = km2

    def landcover(self, **kwargs):
        return self._cover

    def dem(self, **kwargs):
        if self._dem is None:
            raise RuntimeError("no elevation in this stub")
        return self._dem


def _cover_with_ice(n_ice, shape=(10, 10)):
    grid = np.full(shape, 30.0, dtype="float32")        # grass/shrub
    flat = grid.reshape(-1)
    flat[:n_ice] = SNOW_ICE_CLASS
    return _raster(grid)


def test_a_basin_with_no_ice_says_so_and_does_not_claim_more():
    out = snow_ice(_Basin(_cover_with_ice(0)))
    assert out["ice_pct"] == 0
    assert out["ice_km2"] == 0
    assert "no cell" in out["statement"].lower()
    # Zero mapped ice is not zero snowfall, and the sentence has to say it.
    assert "seasonal snow" in out["statement"].lower()


def test_ice_is_measured_by_area_and_not_by_counting_cells():
    # Ten of a hundred cells are ice. At 28 N a degree of longitude is shorter
    # than a degree of latitude, but every cell in one row has the same area,
    # so a block of whole rows must come out at exactly ten per cent while a
    # cell count would too -- the test that separates them is the latitude one
    # below. This one fixes the simple case so a regression is visible.
    out = snow_ice(_Basin(_cover_with_ice(10)))
    assert out["ice_pct"] == pytest.approx(10.0, abs=0.01)
    assert out["measured_by"] == "area, not cell count"


def test_at_high_latitude_area_and_cell_count_disagree():
    # Ice in the top row, at 80 N, where cells are small; the rest of the
    # basin at lower latitudes. Counting cells would call this 10 per cent.
    grid = np.full((10, 10), 30.0, dtype="float32")
    grid[0, :] = SNOW_ICE_CLASS
    cover = _raster(grid, lat0=80.0, res=0.05)
    out = snow_ice(_Basin(cover, lat=79.0))
    by_count = 10.0
    assert out["ice_pct"] != pytest.approx(by_count, abs=0.05), (
        "area weighting made no difference at 80 N, which cannot be right")
    assert out["mapped_cells"] == 10


def test_a_basin_outside_the_product_is_not_reported_as_ice_free():
    # The failure this guards against: no data read as zero per cent, in
    # exactly the far-southern and far-northern basins that have the ice.
    out = snow_ice(_Basin(_cover_with_ice(10), lat=-70.0))
    assert out["covered_by_land_cover"] is False
    assert out["ice_pct"] is None
    assert "must not be read as zero" in out["statement"]
    assert any("outside the latitudes" in line for line in out["limits"])


@pytest.mark.parametrize("lat", [WORLDCOVER_LAT_RANGE[0] - 0.01,
                                 WORLDCOVER_LAT_RANGE[1] + 0.01])
def test_the_coverage_edges_are_the_published_ones(lat):
    assert snow_ice(_Basin(_cover_with_ice(1), lat=lat))["ice_pct"] is None


def test_the_elevation_band_is_read_off_the_elevation_model():
    grid = np.full((10, 10), 30.0, dtype="float32")
    grid[:3, :] = SNOW_ICE_CLASS                 # ice in the top three rows
    cover = _raster(grid)
    z = np.tile(np.linspace(7000, 3000, 10)[:, None], (1, 10))   # high in the north
    out = snow_ice(_Basin(cover, _raster(z)))
    assert out["elevation_evaluated"] is True
    assert out["highest_ice_m"] == pytest.approx(7000, abs=1)
    assert out["median_ice_m"] == pytest.approx(6555, abs=2)
    assert out["ice_floor_m"] == pytest.approx(6111, abs=20)
    assert out["floor_outlier"] is False
    assert 25 < out["above_ice_floor_pct"] <= 35
    assert "ice zone runs from" in out["statement"]


def test_one_misclassified_cell_does_not_become_the_terminus():
    """The Trishuli case, in miniature.

    Measured on the real basin: the lowest cell mapped as ice sits at 1,458 m,
    off 33 cells in 140,415, while the first percentile sits at 4,414 m. The
    minimum also made the share of the basin above it 100 per cent. A statistic
    one bad cell can destroy is not a statistic, so the floor is a percentile
    and the stray cell is named as what it is.
    """
    grid = np.full((40, 40), 30.0, dtype="float32")
    grid[:10, :] = SNOW_ICE_CLASS            # the real ice, high up
    grid[39, 0] = SNOW_ICE_CLASS             # one cell of shadow, far below
    z = np.tile(np.linspace(7000, 1000, 40)[:, None], (1, 40))
    out = snow_ice(_Basin(_raster(grid), _raster(z)))

    assert out["lowest_mapped_ice_m"] == pytest.approx(1000, abs=5)
    assert out["ice_floor_m"] > 5000, "one stray cell dragged the floor down"
    assert out["floor_outlier"] is True
    assert out["cells_below_floor"] >= 1
    assert out["above_ice_floor_pct"] < 100, (
        "the floor was the minimum again, so the whole basin is 'above' it")
    assert "misclassification, not as a terminus" in out["statement"]
    assert out["ice_floor_m"] - out["lowest_mapped_ice_m"] > FLOOR_OUTLIER_M


def test_the_floor_is_a_percentile_and_says_which_one():
    grid = np.full((20, 20), 30.0, dtype="float32")
    grid[:5, :] = SNOW_ICE_CLASS
    z = np.tile(np.linspace(6000, 2000, 20)[:, None], (1, 20))
    out = snow_ice(_Basin(_raster(grid), _raster(z)))
    assert out["ice_floor_percentile"] == ICE_FLOOR_PERCENTILE
    assert "1st percentile" in out["statement"]
    assert "1th" not in out["statement"]
    assert "single lowest cell" in out["statement"]


def test_without_an_elevation_model_the_band_is_not_guessed():
    out = snow_ice(_Basin(_cover_with_ice(10), None))
    assert out["elevation_evaluated"] is False
    assert "lowest_ice_m" not in out


def test_a_trace_of_ice_is_called_a_trace():
    out = snow_ice(_Basin(_cover_with_ice(1, shape=(40, 40))))
    assert out["ice_pct"] < TRACE_PCT
    assert "shadow and cloud" in out["statement"]


def test_every_answer_refuses_to_be_read_as_meltwater():
    # The single most likely misreading, so it is asserted on every path.
    for basin in (_Basin(_cover_with_ice(0)),
                  _Basin(_cover_with_ice(10)),
                  _Basin(_cover_with_ice(10), _raster(np.full((10, 10), 5000.0)))):
        out = snow_ice(basin)
        assert any("meltwater fraction" in line for line in out["limits"])
    out = snow_ice(_Basin(_cover_with_ice(10)))
    assert "not a meltwater fraction" in out["statement"]
    assert "not a meltwater fraction" in out["note"]


def test_basinatlas_columns_are_found_by_prefix_not_by_name():
    row = {"HYBAS_ID": 4120000010, "gla_pc_use": 12.5, "snw_pc_uyr": 41.0,
           "prm_pc_use": 88.0, "gla_pc_sse": 3.0,      # sub-catchment: ignored
           "pre_mm_uyr": 1400, "geometry": None}
    picked = _atlas_block(row)
    assert set(picked) == {"gla_pc_use", "snw_pc_uyr", "prm_pc_use"}
    assert picked["gla_pc_use"] == 12.5


def test_the_atlas_axes_are_reported_separately_and_not_averaged_in():
    row = {"gla_pc_use": 12.5, "snw_pc_uyr": 41.0, "prm_pc_use": 88.0}
    out = snow_ice(_Basin(_cover_with_ice(10)), attributes=row)
    assert out["atlas"]["gla_pc_use"]["measures"] == "glacier extent"
    assert "not averaged into it" in out["statement"]
    # The land-cover measurement must be untouched by the atlas row.
    assert out["ice_pct"] == pytest.approx(10.0, abs=0.01)


def test_without_an_atlas_row_the_answer_says_where_to_get_one():
    out = snow_ice(_Basin(_cover_with_ice(10)))
    assert "atlas" not in out
    assert "BasinATLAS" in out["statement"]


def test_an_atlas_row_with_nothing_relevant_says_so_rather_than_nothing():
    out = snow_ice(_Basin(_cover_with_ice(10)),
                   attributes={"pre_mm_uyr": 1400, "HYBAS_ID": 1})
    assert out["atlas"] == {}
    assert "carried no glacier" in out["atlas_note"]


@pytest.mark.parametrize("value,expected", [
    (1, "1st"), (2, "2nd"), (3, "3rd"), (4, "4th"), (5, "5th"),
    (11, "11th"), (12, "12th"), (13, "13th"), (21, "21st"), (0.5, "0.5th"),
])
def test_the_percentile_is_written_as_an_ordinal(value, expected):
    from basinkit.snow import _ordinal

    assert _ordinal(value) == expected


def _basin_with_ice_high_up(rows=40, cols=40):
    """Ice in the top rows, elevation falling north to south."""
    grid = np.full((rows, cols), 30.0, dtype="float32")
    grid[:10, :] = SNOW_ICE_CLASS
    z = np.tile(np.linspace(7000, 3000, rows)[:, None], (1, cols))
    return _Basin(_raster(grid), _raster(z))


def test_the_breakdowns_cross_the_ice_against_three_surfaces():
    out = snow_ice(_basin_with_ice_high_up())
    assert set(out["breakdowns"]) == {"elevation", "aspect", "slope"}
    for name in ("elevation", "aspect", "slope"):
        block = out["breakdowns"][name]
        assert block["rows"], f"{name} came back empty"
        assert block["reads"]


def test_each_breakdown_accounts_for_all_of_the_ice():
    out = snow_ice(_basin_with_ice_high_up())
    for name, block in out["breakdowns"].items():
        share = sum(r["pct_of_ice"] for r in block["rows"])
        assert share == pytest.approx(100, abs=1.5), f"{name} sums to {share}"


def test_a_breakdown_row_says_both_how_much_ice_and_how_icy_the_class_is():
    # Two different questions: "where is the ice" and "how much of that
    # ground is ice". A row that answers only the first cannot show a snowline.
    rows = snow_ice(_basin_with_ice_high_up())["breakdowns"]["elevation"]["rows"]
    top = max(rows, key=lambda r: r["pct_of_class_that_is_ice"])
    assert top["pct_of_class_that_is_ice"] > 50
    assert all(r["class_km2"] > 0 for r in rows)
    assert all(0 <= r["pct_of_class_that_is_ice"] <= 100 for r in rows)


def test_the_elevation_bands_span_the_ice_and_nothing_falls_outside_them():
    # The bug this caught: ice whose maximum lands exactly on a band boundary
    # fell outside every band, and the breakdown silently accounted for 90 per
    # cent of the ice while reporting shares that summed to 90.
    out = snow_ice(_basin_with_ice_high_up())
    rows = out["breakdowns"]["elevation"]["rows"]
    first = float(rows[0]["class"].split(" to ")[0].replace(",", ""))
    last = float(rows[-1]["class"].split(" to ")[1].replace(",", "").replace(" m", ""))
    assert first <= out["lowest_mapped_ice_m"]
    assert last > out["highest_ice_m"]
    assert sum(r["ice_km2"] for r in rows) == pytest.approx(out["ice_km2"], rel=.02)


def test_aspect_names_the_direction_and_flags_the_wrong_one():
    """The honest half: away from the equator ice usually favours the shaded
    slopes, and where the measurement says otherwise the first suspect is the
    land-cover map, not the glaciology. On the real Trishuli it does say
    otherwise, by 14.3 against 14.9 per cent.
    """
    reads = snow_ice(_basin_with_ice_high_up())["breakdowns"]["aspect"]["reads"]
    assert "poleward" in reads
    assert "per cent ice against" in reads
    assert ("usual direction" in reads)


def test_breakdowns_can_be_turned_off():
    out = snow_ice(_basin_with_ice_high_up(), breakdowns=False)
    assert "breakdowns" not in out
    assert out["ice_pct"] > 0


def test_no_ice_means_no_breakdowns_rather_than_empty_rows():
    out = snow_ice(_Basin(_cover_with_ice(0), _raster(np.full((10, 10), 5000.0))))
    assert out.get("breakdowns") in (None, {})
