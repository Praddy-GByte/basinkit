"""Carving a known channel into the elevation before it is routed.

The constant-depth version of this looked right and did nothing: lowering
every cell on a line by a fixed amount keeps the terrain's own rises, so a
line crossing a divide still climbs it and the router fills both halves as
hollows. On a validated basin it moved the area by 0.00 km2 at any depth up to
150 m. These tests pin the property that actually makes it work -- the carved
path descends the whole way -- rather than the fact that something was lowered.
"""

from __future__ import annotations

import numpy as np
import pytest
from rasterio.transform import from_origin
from shapely.geometry import LineString, Point

from basinkit.condition import _cells_along, burn_streams


@pytest.fixture
def grid():
    """A 1-degree grid at 0.01 degrees, with a ridge down the middle."""
    n = 100
    transform = from_origin(0.0, 1.0, 0.01, 0.01)
    x = np.arange(n)
    # Two valleys either side of a ridge at column 50.
    profile = 100.0 + 400.0 * np.exp(-((x - 50) ** 2) / (2 * 12.0 ** 2))
    elevation = np.tile(profile, (n, 1)).astype("float32")
    return elevation, transform


def test_cells_along_is_ordered_and_has_no_gaps(grid):
    _, transform = grid
    line = LineString([(0.05, 0.5), (0.95, 0.5)])
    rows, cols = _cells_along(line, transform, (100, 100))
    assert rows.size > 50, "a line across the grid has to touch most columns"
    steps = np.abs(np.diff(cols))
    assert steps.max() <= 1, "consecutive cells must be neighbours, not jumps"
    assert len(set(zip(rows.tolist(), cols.tolist(), strict=True))) == rows.size


def test_a_carved_line_descends_the_whole_way_over_a_ridge(grid):
    """The property the whole feature rests on."""
    elevation, transform = grid
    line = LineString([(0.05, 0.5), (0.95, 0.5)])

    before_rows, before_cols = _cells_along(line, transform, elevation.shape)
    before = elevation[before_rows, before_cols]
    assert before.max() - before.min() > 300, "the test ridge has to be a ridge"
    assert np.diff(before).max() > 0, "and the bare terrain has to climb it"

    out, record = burn_streams(elevation, transform, [line], depth_m=20.0)
    after = out[before_rows, before_cols]

    assert record["burned"] is True
    assert record["method"] == "carved to a monotonic descent"
    assert np.diff(after).max() <= 0, "the carved channel must never climb"
    assert out.shape == elevation.shape


def test_carving_leaves_the_rest_of_the_grid_alone(grid):
    elevation, transform = grid
    line = LineString([(0.05, 0.5), (0.95, 0.5)])
    out, _ = burn_streams(elevation, transform, [line], depth_m=20.0)
    changed = np.abs(out - elevation) > 1e-6
    assert changed.sum() < 0.05 * elevation.size, "only the channel should move"
    assert (out <= elevation + 1e-6).all(), "carving lowers, it never raises"


def test_the_drop_per_cell_is_respected(grid):
    elevation, transform = grid
    line = LineString([(0.05, 0.5), (0.95, 0.5)])
    out, _ = burn_streams(elevation, transform, [line], depth_m=5.0, drop_m=0.5)
    rows, cols = _cells_along(line, transform, elevation.shape)
    after = out[rows, cols]
    climbing = np.diff(after)
    assert climbing.max() <= 0
    # Where the bare terrain climbed, the carve had to impose the full drop.
    assert climbing.min() <= -0.5 + 1e-9


def test_lines_outside_the_window_warn_and_change_nothing(grid):
    elevation, transform = grid
    far = LineString([(50.0, 50.0), (51.0, 50.0)])
    with pytest.warns(UserWarning, match="outside the elevation window"):
        out, record = burn_streams(elevation, transform, [far])
    assert record["burned"] is False
    assert np.array_equal(out, elevation)


def test_an_empty_stream_set_is_refused():
    elevation = np.zeros((10, 10), dtype="float32")
    transform = from_origin(0.0, 1.0, 0.1, 0.1)
    with pytest.raises(ValueError, match="No usable geometry"):
        burn_streams(elevation, transform, [])


def test_a_point_is_not_a_channel(grid):
    """A point has no direction to carve along, so it is skipped, not crashed."""
    elevation, transform = grid
    out, record = burn_streams(elevation, transform, [Point(0.5, 0.5)],
                               depth_m=10.0)
    assert record["burned"] is True
    assert record["carved_cells"] == 0


def test_the_record_says_the_answer_was_forced(grid):
    """Provenance has to let a forced basin be told from a found one."""
    elevation, transform = grid
    line = LineString([(0.05, 0.5), (0.95, 0.5)])
    _, record = burn_streams(elevation, transform, [line])
    assert "forced" in record["warning"]
    assert record["burn_depth_m"] == pytest.approx(20.0)
    assert record["n_lines"] == 1
