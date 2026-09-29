"""Landscape form: chi, channel steepness, concavity, knickpoints.

No network. Every case runs on a surface whose answer is known in advance, so a
wrong number is a defect here and not a data source having a bad day.
"""

from __future__ import annotations

import numpy as np
import pytest

pyflwdir = pytest.importorskip("pyflwdir")
rasterio = pytest.importorskip("rasterio")

from basinkit import landscape as L  # noqa: E402


def _plane(nrow=60, ncol=60, top=600.0, cell=100.0):
    """A uniform slope draining to one edge, in a projected grid."""
    from rasterio.transform import from_origin

    z = np.tile(np.linspace(top, 0.0, ncol), (nrow, 1)).astype("float32")
    return z, from_origin(0.0, nrow * cell, cell, cell)


def _v_valley(nrow=80, ncol=80, cell=100.0):
    """A converging valley: elevation falls downstream and inwards."""
    from rasterio.transform import from_origin

    r = np.arange(nrow)[:, None]
    c = np.arange(ncol)[None, :]
    z = (1000.0 - 8.0 * c + 0.6 * np.abs(r - nrow // 2)).astype("float32")
    return z, from_origin(0.0, nrow * cell, cell, cell)


def test_theta_ref_and_a0_are_the_documented_conventions():
    assert L.THETA_REF == 0.45
    assert L.A0_M2 == 1.0e6


def test_nan_and_sentinel_nodata_route_identically():
    """A NaN never equals -9999, so the two spellings must be reconciled.

    A grid holding NaN while a sentinel is declared has every NaN cell treated
    as valid, and the basin then drains the whole rectangle. network() takes a
    sentinel, so the caller's job is to hand it one spelling; this pins that the
    two agree once reconciled.
    """
    z, tr = _plane()
    z_nan = z.copy()
    z_nan[10:20, 10:20] = np.nan
    z_sent = np.where(np.isfinite(z_nan), z_nan, -9999.0).astype("float32")

    _, upa_a, _, chan_a = L.network(z_sent, tr, nodata=-9999.0, latlon=False)
    z_back = np.where(z_sent == -9999.0, np.nan, z_sent).astype("float32")
    _, upa_b, _, chan_b = L.network(z_back, tr, nodata=np.nan, latlon=False)

    assert int(chan_a.sum()) == int(chan_b.sum())
    assert np.nanmax(upa_a) == pytest.approx(np.nanmax(upa_b))


def test_routed_cells_equal_valid_cells():
    z, tr = _plane()
    z[30:40, 30:40] = -9999.0
    valid = int((z != -9999.0).sum())
    flw, _, _, _ = L.network(z, tr, nodata=-9999.0, latlon=False)
    assert int(np.asarray(flw.mask).sum()) == valid


def test_chi_never_decreases_going_upstream():
    """The defining property: chi is an integral from the outlet upstream."""
    z, tr = _v_valley()
    flw, upa, dx, chan = L.network(z, tr, nodata=-9999.0, latlon=False,
                                   min_area_km2=0.05)
    r = L.chi_ksn(flw, z, upa, dx, chan, smooth_m=0.0, nodata=-9999.0)
    chi = r["chi"].ravel()
    assert np.isfinite(chi).sum() > 0
    assert np.nanmin(chi) >= 0.0

    # every channel cell's chi is at least that of the cell it drains into
    ds = flw.idxs_ds
    ch = chan.ravel()
    i = np.where(ch & np.isfinite(chi))[0]
    j = ds[i]
    ok = (j != i) & np.isfinite(chi[j])
    assert ok.sum() > 100
    assert np.all(chi[i][ok] >= chi[j][ok] - 1e-9)

    # and it rises along the trunk, from the outlet to the head
    path = L.main_stem(flw, chan, upa)
    trunk = chi[path]
    trunk = trunk[np.isfinite(trunk)]
    assert np.all(np.diff(trunk) >= -1e-9)
    assert trunk[-1] > trunk[0]


def test_ksn_on_a_uniform_slope_is_slope_times_area_to_theta():
    """The definition itself, on a surface where the slope is known exactly."""
    z, tr = _plane(top=600.0, cell=100.0)          # 600 m over 59 cells of 100 m
    flw, upa, dx, chan = L.network(z, tr, nodata=-9999.0, latlon=False,
                                   min_area_km2=0.05)
    r = L.chi_ksn(flw, z, upa, dx, chan, smooth_m=0.0, nodata=-9999.0)
    ksn, slope = r["ksn"], r["slope"]
    m = np.isfinite(ksn) & np.isfinite(slope) & (slope > 0)
    assert m.sum() > 0
    expect = slope[m] * np.power(upa[m].astype("float64"), L.THETA_REF)
    assert np.allclose(ksn[m], expect, rtol=1e-12)
    # The plane's own gradient, in case the flow path is read wrongly. D8 on a
    # perfectly uniform plane resolves the tie diagonally, so the drop is taken
    # over 141.4 m rather than 100 m and the gradient is the cardinal one over
    # root 2. Both are correct D8 answers; anything else is not.
    cardinal = 600.0 / 59.0 / 100.0
    got = float(np.median(slope[m]))
    assert got == pytest.approx(cardinal, rel=0.05) or \
        got == pytest.approx(cardinal / np.sqrt(2.0), rel=0.05), got


def test_smoothing_touches_the_fit_slope_and_not_ksn():
    z, tr = _v_valley()
    rng = np.random.default_rng(0)
    z = (z + rng.normal(0.0, 2.0, z.shape)).astype("float32")
    flw, upa, dx, chan = L.network(z, tr, nodata=-9999.0, latlon=False,
                                   min_area_km2=0.05)
    raw = L.chi_ksn(flw, z, upa, dx, chan, smooth_m=0.0, nodata=-9999.0)
    sm = L.chi_ksn(flw, z, upa, dx, chan, smooth_m=500.0, nodata=-9999.0)

    a, b = raw["ksn"], sm["ksn"]
    m = np.isfinite(a) & np.isfinite(b)
    assert np.allclose(a[m], b[m], rtol=1e-9), "smoothing must not change k_sn"

    f, g = raw["slope_fit"], sm["slope_fit"]
    m = np.isfinite(f) & np.isfinite(g)
    assert not np.allclose(f[m], g[m]), "smoothing must change the fit slope"
    assert sm["smoothing_window_m"] > 0
    assert raw["smoothing_window_m"] == 0


def test_fitted_concavity_recovers_a_planted_exponent():
    """Build S = k A^-theta exactly, then check fit_theta reads theta back."""
    area = np.logspace(6.1, 9.0, 4000)             # m2, above the 1 km2 floor
    theta = 0.47
    slope = 0.3 * area ** (-theta)
    chan = np.ones(area.size, bool)
    fit = L.fit_theta(area, slope, chan, min_area_km2=1.0, nbins=30)
    assert fit is not None
    assert fit["theta"] == pytest.approx(theta, abs=0.01)
    assert fit["r2"] > 0.99


def test_knickpoints_finds_a_planted_step_and_ignores_a_straight_profile():
    # a river profile in chi-elevation space rises upstream, so a knickpoint is
    # a reach where it rises much faster than the rest of the profile
    chi = np.linspace(0.0, 10000.0, 400)
    smooth = 0.15 * chi
    assert L.knickpoints(chi, smooth, min_drop_m=40.0) == []

    stepped = smooth.copy()
    stepped[200:] += 150.0                          # a 150 m step at the middle
    found = L.knickpoints(chi, stepped, min_drop_m=40.0)
    assert len(found) >= 1
    assert any(k["step_m"] >= 40.0 for k in found)


def test_main_stem_follows_the_largest_drainage_area():
    z, tr = _v_valley()
    flw, upa, dx, chan = L.network(z, tr, nodata=-9999.0, latlon=False,
                                   min_area_km2=0.05)
    path = L.main_stem(flw, chan, upa)
    assert path.size > 10
    a = upa.ravel()[path]
    # area never increases as the walk goes upstream
    assert np.all(np.diff(a) <= 1e-6)


def test_analyse_summary_reports_its_own_settings():
    pytest.importorskip("rioxarray")
    import rioxarray  # noqa: F401
    import xarray as xr
    from rasterio.transform import from_origin

    z, tr = _v_valley()
    da = xr.DataArray(z, dims=("y", "x"),
                      coords={"y": np.arange(z.shape[0]), "x": np.arange(z.shape[1])})
    da = da.rio.write_transform(from_origin(0.0, z.shape[0] * 100.0, 100.0, 100.0))
    da = da.rio.write_crs("EPSG:32612")

    r = L.analyse(da, min_area_km2=0.05)
    s = r["summary"]
    assert s["theta_ref"] == 0.45
    assert s["A0_km2"] == 1.0
    assert s["min_channel_area_km2"] == 0.05
    assert s["distances"] == "planar"
    assert s["channel_cells"] > 0
    assert "not uplift rates" in s["note"]


def _fake(**summary):
    base = {"theta_ref": 0.45, "A0_km2": 1.0, "min_channel_area_km2": 1.0,
            "channel_cells": 5000, "zero_gradient_channel_fraction": 0.1,
            "knickpoints": 0}
    base.update(summary)
    return {"summary": base, "concavity_fit": None}


def test_confidence_speaks_for_every_reported_quantity():
    c = L.confidence(_fake())
    assert set(c) == {"ksn", "fitted_concavity", "knickpoints", "chi"}
    assert all(isinstance(v, str) and v.strip() for v in c.values())
    # no unformatted percent escapes leaking into user-facing text
    assert not any("%%" in v for v in c.values())


def test_a_good_concavity_fit_is_called_quotable_and_a_weak_one_is_not():
    good = _fake()
    good["concavity_fit"] = {"r2": 0.91, "theta": 0.45}
    weak = _fake()
    weak["concavity_fit"] = {"r2": 0.68, "theta": 0.46}
    assert "Quotable as it stands" in L.confidence(good)["fitted_concavity"]
    txt = L.confidence(weak)["fitted_concavity"]
    assert "weak" in txt and "0.68" in txt
    # and it must say k_sn is not dragged down with it
    assert "k_sn is unaffected" in txt


def test_confidence_reports_how_much_of_the_network_ksn_covers():
    c = L.confidence(_fake(zero_gradient_channel_fraction=0.33))
    assert "67%" in c["ksn"]
    high = L.confidence(_fake(zero_gradient_channel_fraction=0.45))
    assert "speaks for less of the basin" in high["ksn"]


def test_limits_stays_quiet_on_an_ordinary_run():
    """A caution on every run is not a caution. This pins that."""
    r = _fake()
    r["concavity_fit"] = {"r2": 0.82, "theta": 0.44}
    assert L.limits(r) == []


def test_limits_speaks_only_when_a_number_should_not_be_used():
    r = _fake()
    r["concavity_fit"] = {"r2": 0.41, "theta": 0.3}
    assert any("too scattered to use" in w for w in L.limits(r))

    r = _fake(zero_gradient_channel_fraction=0.62)
    assert any("less than half" in w for w in L.limits(r))

    r = _fake(channel_cells=120)
    assert any("unstable" in w for w in L.limits(r))


def test_a_weak_fit_alone_is_a_qualification_and_not_a_limit():
    """R2 0.68 qualifies theta; it does not stop anyone using the run."""
    r = _fake()
    r["concavity_fit"] = {"r2": 0.68, "theta": 0.46}
    assert L.limits(r) == []
    assert "weak" in L.confidence(r)["fitted_concavity"]


def _binary(node):
    """Is this open() call in binary mode? Then no encoding applies."""
    import ast

    mode = ""
    if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
        mode = str(node.args[1].value)
    for k in node.keywords:
        if k.arg == "mode" and isinstance(k.value, ast.Constant):
            mode = str(k.value.value)
    return "b" in mode


def test_every_text_file_read_or_written_states_its_encoding():
    """Windows defaults to cp1252, so an unstated encoding is a latent bug.

    ``read_text()`` and ``write_text()`` without ``encoding=`` use the platform
    default. On Linux and macOS that is UTF-8 and nothing goes wrong; on Windows
    it is cp1252, and the first non-ASCII character in a source file, a cached
    JSON or a written licence report raises a UnicodeError. It passes review on
    a Mac and fails on a user's machine, which is the worst way to find out.

    The check parses rather than pattern-matches, because a call whose argument
    itself contains brackets defeats a regular expression. No default ruff rule
    covers this, which is why it is a test.
    """
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    watched = {"read_text", "write_text"}
    offenders = []
    for folder in ("basinkit", "tests", "arcgis_toolbox", "qgis_plugin"):
        base = root / folder
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:                     # not ours to police
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                stated = any(k.arg == "encoding" for k in node.keywords)
                if (isinstance(node.func, ast.Attribute)
                        and node.func.attr in watched and not stated):
                    offenders.append(f"{path.relative_to(root)}:{node.lineno}: "
                                     f"{node.func.attr}() without an encoding")
                elif (isinstance(node.func, ast.Name) and node.func.id == "open"
                        and not stated and not _binary(node)):
                    offenders.append(f"{path.relative_to(root)}:{node.lineno}: "
                                     "open() in text mode without an encoding")
    assert not offenders, (
        "read_text/write_text without an explicit encoding breaks on Windows:\n"
        + "\n".join(offenders))


def test_the_trunk_and_its_knickpoints_carry_map_coordinates():
    """A knickpoint belongs on a map, not only in a table.

    QGIS and ArcGIS Pro both want a point layer. Without coordinates travelling
    with the result, every caller would have to re-derive the trunk to place
    them, which is the kind of duplication that drifts.
    """
    pytest.importorskip("rioxarray")
    import xarray as xr
    from rasterio.transform import from_origin

    z, _ = _v_valley()
    # rioxarray derives the transform from the coordinates when they exist, so
    # the coordinates are built to match the grid the test is asserting about.
    x0, y0, cell = 500000.0, 4000000.0, 100.0
    xs = x0 + cell * (np.arange(z.shape[1]) + 0.5)
    ys = y0 - cell * (np.arange(z.shape[0]) + 0.5)
    da = xr.DataArray(z, dims=("y", "x"), coords={"y": ys, "x": xs})
    da = da.rio.write_transform(from_origin(x0, y0, cell, cell))
    da = da.rio.write_crs("EPSG:32612")

    r = L.analyse(da, min_area_km2=0.05)
    t = r["trunk"]
    assert {"x", "y", "crs"} <= set(t)
    assert len(t["x"]) == len(t["chi_m"]) == len(t["y"])
    assert str(t["crs"]) == "EPSG:32612"

    # the coordinates are inside the grid the transform describes
    assert t["x"].min() >= x0
    assert t["x"].max() <= x0 + cell * z.shape[1]
    assert t["y"].max() <= y0
    assert t["y"].min() >= y0 - cell * z.shape[0]

    for k in r["knickpoints"]:
        assert {"x", "y", "distance_to_outlet_m"} <= set(k)
        assert t["x"].min() <= k["x"] <= t["x"].max()
        assert t["y"].min() <= k["y"] <= t["y"].max()
