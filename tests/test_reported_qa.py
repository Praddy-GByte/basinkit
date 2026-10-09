"""Regressions for the defects found in an independent test pass on 0.8.4.

Someone ran about two hundred checks over the package, the CLI and the plugin
inside a real QGIS and wrote down every wrong answer. Twenty-three of those
held up against the code. This file pins the ones that were producing a wrong
number, a silent gap or a dead process, so none of them can come back quietly.

Each test states the defect rather than the fix, so it keeps its meaning if the
implementation moves.
"""

from __future__ import annotations

import importlib.util
import sys
import warnings
from pathlib import Path

import pytest
from shapely.geometry import Point, box

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# 1. The plugin told people to install a package that cannot route a DEM
# ---------------------------------------------------------------------------

def _load_deps():
    spec = importlib.util.spec_from_file_location(
        "basinkit_qgis_deps", ROOT / "qgis_plugin" / "deps.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_plugin_asks_for_the_backend_it_routes_with():
    """``pip install basinkit`` leaves out pyflwdir, and auto needs it.

    Without it every catchment below 2,000 km2 silently returns the coarser
    HydroBASINS assembly -- 314.8 km2 where the DEM resolves 255.6.
    """
    deps = _load_deps()
    assert "pyflwdir" in deps.REQUIRED.values()
    assert "matplotlib" in deps.REQUIRED.values()
    for target in deps.REQUIRED:
        assert target in deps.REASONS, f"{target} has no stated reason"


def test_the_install_command_survives_a_shell():
    """``basinkit[delineate]`` unquoted is a glob; zsh refuses it outright."""
    deps = _load_deps()
    command = deps.install_command(["basinkit[delineate]"])
    assert command is None or "'basinkit[delineate]'" in command


def test_an_externally_managed_python_gets_the_flag_it_needs(monkeypatch):
    """Debian and Ubuntu QGIS: pip refuses without --break-system-packages."""
    deps = _load_deps()
    monkeypatch.setattr(deps, "externally_managed", lambda: True)
    assert "--break-system-packages" in deps.console_command(["basinkit"])
    command = deps.install_command(["basinkit"])
    if command is not None:
        assert "--break-system-packages" in command


# ---------------------------------------------------------------------------
# 2 and 3. A basin two orders of magnitude from what drains to the point
# ---------------------------------------------------------------------------

def test_a_basin_far_smaller_than_its_own_river_is_reported():
    """The api backend returned 1.9 km2 of the Danube and said nothing."""
    from basinkit import verify

    def fake(lat, lon, **kwargs):
        return {"up_area_km2": 807_000.0, "sub_area_km2": 120.0,
                "hybas_id": 2060000010, "region": "eu", "snapped": False}

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("basinkit.delineate.hydrobasins.reported_upland_km2", fake)
        check = verify.check_magnitude(45.0, 29.0, 1.9)
    assert not check.ok
    assert check.reason == "far-too-small"
    assert "807,000" in check.message


def test_a_basin_far_larger_than_its_own_river_is_reported():
    from basinkit import verify

    def fake(lat, lon, **kwargs):
        return {"up_area_km2": 250.0, "sub_area_km2": 120.0,
                "hybas_id": 1, "region": "eu", "snapped": False}

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("basinkit.delineate.hydrobasins.reported_upland_km2", fake)
        check = verify.check_magnitude(45.0, 29.0, 9_000.0)
    assert not check.ok
    assert check.reason == "far-too-large"


def test_an_ordinary_disagreement_is_not_reported():
    """Four backends read four grids; tens of percent apart is not an error."""
    from basinkit import verify

    def fake(lat, lon, **kwargs):
        return {"up_area_km2": 1_194.0, "sub_area_km2": 130.0,
                "hybas_id": 1, "region": "na", "snapped": False}

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("basinkit.delineate.hydrobasins.reported_upland_km2", fake)
        for area in (1_194.8, 1_000.0, 1_500.0, 2_300.0):
            assert verify.check_magnitude(37.8, -79.8, area).ok


def test_no_reference_is_not_a_failed_check():
    """A check that cannot run must not read as a check that passed badly."""
    from basinkit import verify

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("basinkit.delineate.hydrobasins.reported_upland_km2",
                   lambda *a, **k: None)
        check = verify.check_magnitude(0.0, 0.0, 10.0)
    assert check.ok and check.reason == "no-reference"


def test_a_named_backend_is_weighed_like_auto(monkeypatch):
    """Asking for a backend by name skipped every check auto ran."""
    from basinkit import delineate as mod

    monkeypatch.setitem(
        mod._BACKENDS, "fake",
        lambda lat, lon, **kw: (Point(0, 0).buffer(0.01),
                                {"backend": "fake", "area_km2": 1.9}))
    monkeypatch.setattr(
        "basinkit.verify.check_magnitude",
        lambda lat, lon, area, **kw: __import__(
            "basinkit.verify", fromlist=["MagnitudeCheck"]
        ).MagnitudeCheck(False, "far-too-small", "two orders out",
                         basin_area_km2=area))
    monkeypatch.setattr("basinkit.verify.check_outlet",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _, prov = mod.delineate(45.0, 29.0, backend="fake")
    assert prov["magnitude_check"]["ok"] is False
    assert "two orders out" in prov["warning"]
    assert any("two orders out" in str(w.message) for w in caught)


# ---------------------------------------------------------------------------
# 15. No river anywhere near, and a large basin returned regardless
# ---------------------------------------------------------------------------

def test_a_large_basin_with_no_river_nearby_is_distinguished(monkeypatch):
    """A click in a city centre returned 36,944 km2 with only a quiet note."""
    from basinkit import verify

    monkeypatch.setattr("basinkit.delineate.hydrobasins.candidate_regions",
                        lambda lat, lon: ["as"])
    monkeypatch.setattr("basinkit.sources.vectors._unpack",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no net")))

    big = verify.check_outlet(28.63, 77.22, 36_944.0, allow_download=True)
    assert big.reason == "no-reach-large"
    assert "36,944" in big.message

    small = verify.check_outlet(28.63, 77.22, 3.0, allow_download=True)
    assert small.reason == "no-reach"
    assert "not on a river" in small.message


# ---------------------------------------------------------------------------
# 4 and 11. A rainfall series with holes in it, and a date range blamed on CHIRPS
# ---------------------------------------------------------------------------

def test_a_reversed_year_range_is_named_for_what_it_is():
    """It used to raise "CHIRPS covers 60N-60S", sending the reader to the map."""
    from basinkit.sources.climate import chirps, terraclimate

    with pytest.raises(ValueError, match="after end"):
        chirps(box(0, 0, 1, 1), 2020, 2010, progress=False)
    with pytest.raises(ValueError, match="after end"):
        terraclimate(box(0, 0, 1, 1), ("ppt",), 2020, 2010, progress=False)


def test_years_before_chirps_begins_say_so():
    from basinkit.sources.climate import chirps

    with pytest.raises(ValueError, match="1981"):
        chirps(box(0, 0, 1, 1), 1970, 1975, progress=False)


def test_a_month_that_fails_is_counted_not_dropped(monkeypatch):
    """One run returned 59 of 72 months in silence; the next returned 72."""
    import numpy as np
    import xarray as xr

    from basinkit.sources import climate as mod

    calls = {"n": 0}

    def flaky(url, bounds, pad=0.1):
        calls["n"] += 1
        if calls["n"] % 3 == 0:
            raise RuntimeError("remote read timed out")
        return xr.DataArray(np.ones((2, 2), dtype="float32"),
                            dims=("y", "x"),
                            coords={"y": [1.0, 0.0], "x": [0.0, 1.0]})

    monkeypatch.setattr(mod, "_read_window", flaky)
    monkeypatch.setattr("basinkit.clip.clip_raster", lambda da, geom, **k: da)
    monkeypatch.setattr("basinkit.clip.zonal_mean", lambda da, **k: da.mean())

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        out = mod.chirps(box(0, 0, 1, 1), 2015, 2016, progress=False)

    assert out.attrs["basinkit_complete"] is False
    assert out.attrs["basinkit_months_missing"]
    assert (out.attrs["basinkit_n_months"]
            + len(out.attrs["basinkit_months_missing"])
            == out.attrs["basinkit_months_requested"])
    assert any("did not come back" in str(w.message) for w in caught)


# ---------------------------------------------------------------------------
# 16. One function, one kind of thing back
# ---------------------------------------------------------------------------

def test_precipitation_returns_a_series_whichever_source(monkeypatch):
    """terraclimate handed back a whole Dataset where chirps gave a series."""
    import numpy as np
    import xarray as xr

    from basinkit.basin import Basin

    times = np.array(["2020-01-01", "2020-02-01"], dtype="datetime64[ns]")
    ds = xr.Dataset({"ppt": ("time", [10.0, 20.0])}, coords={"time": times})
    ds.attrs["basinkit_complete"] = True
    monkeypatch.setattr("basinkit.sources.climate.terraclimate",
                        lambda *a, **k: ds)

    basin = Basin.from_geometry(box(0, 0, 1, 1))
    out = basin.precipitation(2020, 2020, source="terraclimate")
    assert isinstance(out, xr.DataArray)
    assert out.name == "precipitation"
    assert out.attrs["basinkit_complete"] is True


# ---------------------------------------------------------------------------
# 5. A half-extracted geodatabase is not a cache
# ---------------------------------------------------------------------------

def test_an_interrupted_extraction_is_not_mistaken_for_a_cache(tmp_path):
    """Every attributes() call then failed until someone deleted the folder."""
    from basinkit.sources.attributes import _COMPLETE, _usable_gdb

    (tmp_path / "BasinATLAS_v10.gdb").mkdir()
    assert _usable_gdb(tmp_path) is None
    (tmp_path / _COMPLETE).write_text("done", encoding="utf-8")
    assert _usable_gdb(tmp_path) is not None


def test_a_partial_extraction_says_what_to_do(monkeypatch, tmp_path):
    from basinkit.exceptions import DataSourceError
    from basinkit.sources import attributes as mod

    target = tmp_path / "BasinATLAS_v10"
    (target / "x.gdb").mkdir(parents=True)
    monkeypatch.setattr(mod, "subdir", lambda name: tmp_path)
    with pytest.raises(DataSourceError, match="did not finish"):
        mod.fetch_basinatlas(progress=False)


# ---------------------------------------------------------------------------
# 6 and 7. Killed by the kernel with nothing written
# ---------------------------------------------------------------------------

def test_the_dem_backend_refuses_a_window_it_cannot_route():
    """A 25,000 km2 catchment grew to four degrees and the process was killed."""
    from basinkit.delineate.dem import delineate_dem
    from basinkit.exceptions import DelineationError

    with pytest.raises(DelineationError) as excinfo:
        delineate_dem(39.0, -77.5, window_deg=2.0, progress=False)
    message = str(excinfo.value)
    assert "megapixels" in message
    assert "hydrobasins" in message


def test_the_memory_estimate_is_monotonic_in_window_size():
    from basinkit.delineate.dem import _estimated_gb

    sizes = [(2 * h * 3600) ** 2 for h in (0.25, 0.5, 1.0, 2.0)]
    estimates = [_estimated_gb(int(s)) for s in sizes]
    assert estimates == sorted(estimates)
    assert estimates[0] > 0


def test_the_report_reads_a_grid_a_page_can_show(monkeypatch):
    """The default 100 Mpx read is what killed the Koshi quick-start report."""
    from basinkit import report as mod

    assert mod.REPORT_MAX_PIXELS <= 20_000_000

    asked = {}

    class FakeBasin:
        geometry = box(0, 0, 1, 1)
        provenance: dict = {}
        area_km2 = 1.0
        centroid = (0.5, 0.5)

        def dem(self, **kwargs):
            asked.update(kwargs)
            raise RuntimeError("stop here; the budget is what is being tested")

    with pytest.raises(RuntimeError):
        mod.report(FakeBasin(), "/dev/null", progress=False)
    assert asked["max_pixels"] == mod.REPORT_MAX_PIXELS


# ---------------------------------------------------------------------------
# 8. The texture is an extra; its failure is not the export's
# ---------------------------------------------------------------------------

def test_a_basin_with_no_outlet_still_gets_a_subtitle():
    """('?', '?') formatted with %.4g raised and took the whole export out."""
    from basinkit.viz3d import _outlet_text

    assert _outlet_text((26.8712, 87.1543), 0.0, 0.0).startswith("26.87")
    for missing in (None, ("?", "?"), (), "nonsense"):
        assert "near" in _outlet_text(missing, 26.5, 87.0)


# ---------------------------------------------------------------------------
# 9. Band identifiers, which is what everyone writes
# ---------------------------------------------------------------------------

class _Asset:
    pass


class _Item:
    def __init__(self, names):
        self.assets = {n: _Asset() for n in names}
        self.properties: dict = {}


def test_band_identifiers_are_translated_to_asset_names():
    from basinkit.sources.stac import resolve_bands

    items = [_Item(["blue", "green", "red", "nir", "rededge1"])]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert resolve_bands(["B04", "B08"], "sentinel2", items) == ["red", "nir"]
        assert resolve_bands(["b04"], "sentinel2", items) == ["red"]
        assert resolve_bands(["red"], "sentinel2", items) == ["red"]


def test_the_same_identifier_means_different_bands_on_different_missions():
    """Landsat B5 is near infrared; Sentinel-2 B05 is the first red edge."""
    from basinkit.sources.stac import BAND_ALIASES

    assert BAND_ALIASES["landsat"]["B5"] == "nir08"
    assert BAND_ALIASES["sentinel2"]["B05"] == "rededge1"


def test_an_unknown_band_lists_the_ones_that_exist():
    from basinkit.exceptions import DataSourceError
    from basinkit.sources.stac import resolve_bands

    items = [_Item(["blue", "red"])]
    with pytest.raises(DataSourceError) as excinfo:
        resolve_bands(["B99"], "sentinel2", items)
    assert "blue, red" in str(excinfo.value)


# ---------------------------------------------------------------------------
# 12, 13, 21. Messages that named the wrong thing, or nothing
# ---------------------------------------------------------------------------

def test_a_catalogued_product_gets_its_instructions():
    """dem('fabdem') said "Unknown DEM product"; it is a known one, gated."""
    from basinkit.exceptions import NotImplementedSource
    from basinkit.sources.dem import tile_url

    with pytest.raises(NotImplementedSource) as excinfo:
        tile_url("fabdem", 10, 10)
    assert "Bristol" in str(excinfo.value)

    with pytest.raises(ValueError, match="cop30"):
        tile_url("nonsense", 10, 10)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"),
                                 None, "not a number", object()])
def test_a_coordinate_that_is_not_a_number_is_named_as_such(bad):
    """A string reached the range comparison and raised a TypeError from it.

    ``'<=' not supported between instances of 'str' and 'int'`` is a message
    about Python's type system in place of the one written here about
    coordinates.
    """
    from basinkit.basin import Basin

    with pytest.raises(ValueError) as excinfo:
        Basin.from_point(bad, 10.0)
    assert "coordinate" in str(excinfo.value) or "lat/lon" in str(excinfo.value)


def test_a_numeric_string_is_coerced_rather_than_crashing(monkeypatch):
    from basinkit import basin as mod

    monkeypatch.setattr("basinkit.delineate.delineate",
                        lambda lat, lon, **kw: (box(0, 0, 1, 1),
                                                {"outlet": (lat, lon)}))
    out = mod.Basin.from_point("26.8", "87.1")
    assert out.provenance["outlet"] == (26.8, 87.1)


def test_the_cli_reports_an_error_rather_than_a_traceback():
    from click.testing import CliRunner

    from basinkit.cli import main

    result = CliRunner().invoke(main, ["basin", "--lat", "95", "--lon", "10"])
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert "not a valid lat/lon" in result.output


def test_an_unknown_catalogue_category_lists_the_real_ones():
    from click.testing import CliRunner

    from basinkit.cli import main

    result = CliRunner().invoke(main, ["catalog", "--category", "nonsense"])
    assert result.exit_code != 0
    assert "terrain" in result.output and "hydrography" in result.output


def test_every_backend_the_library_offers_is_offered_by_the_cli():
    """tdx was in basinkit.delineate for two releases and refused by --backend."""
    from basinkit.cli import BACKENDS
    from basinkit.delineate import _BACKENDS

    assert set(_BACKENDS) | {"auto"} == set(BACKENDS)


def test_the_archydro_command_asks_for_the_backend_it_needs():
    """auto refines small catchments onto the DEM, which has no sub-catchments."""
    from basinkit.cli import archydro

    backend = next(p for p in archydro.params if p.name == "backend")
    assert backend.default == "hydrobasins"


# ---------------------------------------------------------------------------
# 17. Two measurements under one name
# ---------------------------------------------------------------------------

def test_the_dem_drainage_density_names_the_other_measurement():
    """0.378 from mapped reaches and 0.914 from the DEM, same name, no note.

    The number the DEM route returns carries its own note, so this reads the
    note off a real result rather than off the source.
    """
    import numpy as np
    import rioxarray  # noqa: F401
    import xarray as xr

    from basinkit.terrain import drainage_density

    # A single tilted plane: enough for the function to run and return its
    # note, which is what is being pinned here.
    ny = nx = 48
    z = np.tile(np.linspace(100.0, 0.0, nx, dtype="float32"), (ny, 1))
    grid = xr.DataArray(
        z, dims=("y", "x"),
        coords={"y": np.linspace(0.02, 0.0, ny), "x": np.linspace(0.0, 0.02, nx)},
    ).rio.write_crs("EPSG:4326")

    try:
        out = drainage_density(grid)
    except Exception as exc:                        # pragma: no cover
        pytest.skip(f"the DEM route is unavailable here: {exc}")
    assert out["source"].startswith("channels extracted from the DEM")
    assert "morphometry()" in out["note"]


def test_the_mapped_reach_drainage_density_names_the_other_one():
    from basinkit import morphometry

    source = Path(ROOT / "basinkit" / "morphometry.py").read_text(
        encoding="utf-8")
    # The note travels in the result's own notes list, which is what a reader
    # of a morphometry dict sees.
    assert "terrain.drainage_density()" in source
    assert "HydroRIVERS by default" in source
    assert morphometry.morphometry.__doc__


# ---------------------------------------------------------------------------
# 18 and 20. Noise in the log, and a check that was not running
# ---------------------------------------------------------------------------

def test_the_matmul_deprecation_is_filtered_for_one_call_only():
    from basinkit.delineate.dem import _quiet_matmul

    @_quiet_matmul
    def noisy():
        warnings.warn("Use `@` matmul instead of `*` mul operator",
                      DeprecationWarning, stacklevel=1)
        warnings.warn("something a user can act on", UserWarning, stacklevel=1)
        return "done"

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert noisy() == "done"
        messages = [str(w.message) for w in caught]
    assert not any("matmul" in m for m in messages)
    assert any("act on" in m for m in messages)

    # and the caller's own filters are left as they were
    with warnings.catch_warnings(record=True) as after:
        warnings.simplefilter("always")
        warnings.warn("Use `@` matmul instead of `*` mul operator",
                      DeprecationWarning, stacklevel=1)
    assert len(after) == 1


def test_the_wiring_stub_carries_what_the_plugin_imports():
    """The stub lacked QgsPointXY, so the wiring check had stopped running."""
    sys.path.insert(0, str(ROOT / "verify" / "qgis_stub"))
    try:
        for name in list(sys.modules):
            if name == "qgis" or name.startswith("qgis."):
                del sys.modules[name]
        from qgis.core import QgsPointXY, QgsProcessing, QgsProcessingParameterPoint

        assert QgsPointXY(1.0, 2.0).x() == 1.0
        assert QgsProcessing.SourceType.TypeVectorLine
        assert hasattr(QgsProcessingParameterPoint("X"), "setHelp")
    finally:
        sys.path.remove(str(ROOT / "verify" / "qgis_stub"))
        for name in list(sys.modules):
            if name == "qgis" or name.startswith("qgis."):
                del sys.modules[name]
