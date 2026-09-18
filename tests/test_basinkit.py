"""Tests for basinkit.

Offline tests run everywhere. Network tests are marked and validate against
independently known values -- the Koshi basin's area is published by HydroBASINS
itself, and its mean annual rainfall is well documented, so agreement is real
evidence rather than a snapshot of whatever the code happened to produce.
"""

from __future__ import annotations

import base64
import math
import re

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import LineString, Polygon, box

import basinkit as bk
from basinkit import catalog
from basinkit.clip import basin_area_km2
from basinkit.delineate.hydrobasins import REGIONS, candidate_regions
from basinkit.exceptions import DataSourceError
from basinkit.mosaic import estimate_pixels
from basinkit.sources.dem import tile_url


# ---------------------------------------------------------------- catalogue
def test_every_default_layer_is_in_the_catalogue():
    for key in catalog.DEFAULT_STACK:
        assert key in catalog.DATASETS, f"{key} is in DEFAULT_STACK but not catalogued"


def test_default_stack_needs_no_account():
    """The whole promise of the package is that the default path just works."""
    for key in catalog.DEFAULT_STACK:
        ds = catalog.get(key)
        assert ds.auth == "none", f"{ds.name} is in the default stack but needs {ds.auth}"


def test_default_stack_is_commercially_safe():
    for key in catalog.DEFAULT_STACK:
        ds = catalog.get(key)
        assert ds.commercial_ok, f"{ds.name} is default but forbids commercial use"
        assert ds.redistributable, f"{ds.name} is default but forbids redistribution"


def test_restricted_datasets_are_flagged_not_hidden():
    for key in ("merit_hydro", "fabdem", "grdc"):
        ds = catalog.get(key)
        assert not ds.commercial_ok
        assert ds.notes, f"{key} is restricted but carries no explanation"


def test_license_check_raises_on_commercial_use_of_restricted_data():
    with pytest.raises(bk.LicenseError, match="commercial"):
        bk.Basin.check_license("merit_hydro", commercial=True)
    with pytest.raises(bk.LicenseError, match="redistributed"):
        bk.Basin.check_license("grdc", redistribute=True)
    bk.Basin.check_license("cop30", commercial=True, redistribute=True)  # no raise


def test_unknown_dataset_lists_alternatives():
    with pytest.raises(KeyError, match="Available"):
        catalog.get("not_a_dataset")


# ------------------------------------------------------------------- geometry
def test_area_uses_equal_area_projection_not_degrees():
    """One degree square at the equator is ~12,300 km2, not 1."""
    square = box(0, 0, 1, 1)
    area = basin_area_km2(square)
    assert 12_000 < area < 12_500, area


def test_area_shrinks_with_latitude():
    """A degree of longitude narrows toward the poles; area must follow."""
    equator = basin_area_km2(box(0, 0, 1, 1))
    high = basin_area_km2(box(0, 60, 1, 61))
    assert high == pytest.approx(equator * math.cos(math.radians(60.5)), rel=0.02)


def test_bbox_efficiency_is_one_for_a_rectangle():
    b = bk.Basin.from_geometry(box(10, 10, 11, 11))
    assert b.bbox_efficiency == pytest.approx(1.0, rel=1e-6)


def test_bbox_efficiency_is_low_for_a_dendritic_shape():
    """The number that justifies clipping to the polygon instead of the box."""
    diagonal = Polygon([(0, 0), (0.05, 0), (1, 0.95), (1, 1), (0.95, 1), (0, 0.05)])
    b = bk.Basin.from_geometry(diagonal)
    assert b.bbox_efficiency < 0.15


# ----------------------------------------------------------------- delineation
def test_region_lookup_finds_the_right_continent():
    assert "as" in candidate_regions(26.87, 87.15)      # Nepal
    assert "sa" in candidate_regions(-3.1, -60.0)       # Amazon
    assert "af" in candidate_regions(0.0, 32.0)         # Uganda
    assert "na" in candidate_regions(40.0, -100.0)      # US Great Plains


def test_region_lookup_rejects_impossible_points():
    with pytest.raises(bk.DelineationError, match="outside every"):
        candidate_regions(-89.0, 0.0)                    # Antarctica


def test_every_region_extent_is_well_formed():
    for code, (w, s, e, n) in REGIONS.items():
        assert w < e and s < n, code
        assert -180 <= w and e <= 180 and -90 <= s and n <= 90, code


def test_invalid_coordinates_hint_at_the_usual_mistake():
    with pytest.raises(ValueError, match=r"\(lat, lon\)"):
        bk.Basin.from_point(85.2, 26.5 * 10)


# ---------------------------------------------------------------------- URLs
@pytest.mark.parametrize(
    "product,lat,lon,fragment",
    [
        ("cop30", 26, 85, "COG_10_N26_00_E085_00"),
        ("cop30", -34, -58, "COG_10_S34_00_W058_00"),
        ("cop90", 26, 85, "COG_30_N26_00_E085_00"),
        ("nasadem", 26, 85, "n26e085"),
        ("nasadem", -34, -58, "s34w058"),
        ("srtm30", 26, 85, "N26E085"),
    ],
)
def test_tile_urls_encode_hemispheres_correctly(product, lat, lon, fragment):
    assert fragment in tile_url(product, lat, lon)


def test_unknown_dem_product_is_rejected():
    with pytest.raises(ValueError, match="Unknown DEM product"):
        tile_url("cop15", 26, 85)


# -------------------------------------------------------------------- mosaic
def test_pixel_estimate_matches_hand_arithmetic():
    # 1 degree at 10 m (~0.0001 deg) is roughly 10,000 x 10,000
    assert estimate_pixels((0, 0, 1, 1), 0.0001) == 100_000_000


def test_large_extents_would_exceed_the_budget():
    """The Koshi case: 5 degrees at 10 m is over a billion pixels."""
    from basinkit.mosaic import DEFAULT_MAX_PIXELS

    assert estimate_pixels((85, 26, 90, 31), 9e-5) > 10 * DEFAULT_MAX_PIXELS


# -------------------------------------------------------------------- errors
def test_missing_dependency_names_the_extra_to_install():
    exc = bk.MissingDependency("pyflwdir", "delineate")
    assert "pip install 'basinkit[delineate]'" in str(exc)


# ------------------------------------------------------------------- network
@pytest.mark.network
def test_koshi_area_matches_hydrobasins_own_figure():
    """Independent check: our equal-area sum against HydroBASINS' UP_AREA field.

    Agreement to better than 1% validates the graph traversal and the area
    computation at once -- they are derived completely separately.
    """
    b = bk.Basin.from_point(26.87, 87.15, backend="hydrobasins", progress=False)
    reported = b.provenance["reported_up_area_km2"]
    assert b.area_km2 == pytest.approx(reported, rel=0.01)
    assert 50_000 < b.area_km2 < 58_000     # published: ~54,100 km2 at Chatara


@pytest.mark.network
def test_morphometry_lands_in_the_ranges_the_literature_reports():
    """Sanity bounds, not snapshots: these are what natural basins do.

    Strahler put the mean bifurcation ratio of natural basins at 3 to 5. The
    hypsometric integral is a fraction. The independently computed integral and
    the elevation-relief ratio should agree closely -- they did not have to.
    """
    b = bk.Basin.from_point(26.87, 87.15, backend="hydrobasins", progress=False)
    m = b.morphometry()

    lin, ar, rel = m["linear"], m["areal"], m["relief"]
    assert 3.0 <= lin["mean_bifurcation_ratio"] <= 5.0
    assert lin["highest_order"] >= 5
    assert 0 < ar["circularity_ratio"] < 1
    assert 0 < ar["elongation_ratio"] < 1.2
    assert 0 < rel["hypsometric_integral"] < 1
    assert rel["hypsometric_integral"] == pytest.approx(
        rel["elevation_relief_ratio"], abs=0.02)

    # One projection for everything: area and perimeter must be consistent
    # enough that the circularity ratio cannot exceed its geometric maximum.
    assert ar["circularity_ratio"] <= 1.0
    # And the trunk cannot be longer than every stream in the basin.
    assert lin["main_channel_length_km"] < lin["total_stream_length_km"]

    orders = [r["order"] for r in m["network"]]
    assert orders == sorted(orders)
    for row in m["network"]:
        assert row["streams"] <= row["reaches"], (
            "a stream is made of one or more reaches, never fewer")


@pytest.mark.network
def test_esri_year_is_never_quietly_substituted():
    """Asking for a year with no data must fail, not hand back its neighbour.

    Every ESRI annual item ends at 00:00 on 1 January, so a naive year window
    matches the *previous* year's map at the boundary instant. Asking for 2024
    returned the 2023 map, with an array that looked entirely correct -- the
    kind of error that shifts a whole change analysis by one year.
    """
    import basinkit.sources.landcover as lc_mod
    from basinkit.sources.landcover import esri_years

    geom = bk.Basin.from_point(27.962, 85.184, backend="hydrobasins",
                               progress=False).geometry
    years = esri_years(geom)
    assert years and all(2016 < y < 2100 for y in years)

    missing = max(years) + 1
    with pytest.raises(DataSourceError, match=str(missing)):
        lc_mod.esri_lulc(geom, year=missing)

    da = lc_mod.esri_lulc(geom, year=max(years))
    assert da.ndim == 2, f"land cover must come back 2-D, got {da.dims}"
    assert da.attrs["basinkit_year"] == max(years)


@pytest.mark.network
def test_export_3d_writes_a_page_that_stands_alone(tmp_path):
    """The exported file must carry everything it needs, including the renderer.

    The whole point is a file that opens on a laptop with no network. If the
    renderer were left as a CDN link, the page would be blank exactly where it
    is needed most.
    """
    b = bk.Basin.from_point(26.87, 87.15, backend="hydrobasins", progress=False)
    out = b.export_3d(tmp_path / "koshi.html", texture=None, mesh_width=128,
                      min_order=6)

    html = out.read_text(encoding="utf-8")
    assert out.stat().st_size > 200_000
    assert "cdnjs.cloudflare.com" not in html, "the renderer must be embedded"
    assert "THREE.WebGLRenderer" in html
    assert '<script id="payload"' in html
    for slot in ("__TITLE__", "__SUBTITLE__", "__CREDIT__", "__PAYLOAD__",
                 "__EX__", "__HASTEX__"):
        assert slot not in html, f"{slot} was never filled in"
    assert "Copernicus DEM" in html
    # Exported without imagery, the page must not open on the satellite
    # material: there is no texture, so it would render a black mesh and read
    # as broken rather than as deliberately plain.
    assert "var HAS_TEXTURE = false;" in html


@pytest.mark.network
def test_koshi_dem_spans_the_himalaya():
    b = bk.Basin.from_point(26.87, 87.15, backend="hydrobasins", progress=False)
    stats = b.terrain_stats()
    assert stats["elev_min_m"] < 200          # Gangetic plain at the outlet
    assert stats["elev_max_m"] > 8_000        # Everest is inside this basin
    assert stats["bbox_efficiency"] < 0.7


@pytest.mark.network
def test_koshi_rainfall_matches_published_climatology():
    b = bk.Basin.from_point(26.87, 87.15, backend="hydrobasins", progress=False)
    rain = b.precipitation(2020, 2022, progress=False)
    annual = float(rain.mean()) * 12
    assert 900 < annual < 1_800, f"{annual:.0f} mm/yr is outside the published range"


@pytest.mark.network
def test_outlet_off_the_network_fails_loudly():
    with pytest.raises((bk.OutletSnapError, bk.DelineationError)):
        bk.Basin.from_point(0.0, -140.0, backend="hydrobasins", progress=False)


@pytest.mark.network
def test_surface_water_occurrence_stays_a_percentage():
    """Regression: averaging the 255 nodata sentinel produced values above 100."""
    import numpy as np

    b = bk.Basin.from_point(26.87, 87.15, backend="hydrobasins", progress=False)
    occ = b.surface_water(progress=False)
    vals = np.asarray(occ.values, dtype="float64")
    vals = vals[np.isfinite(vals)]
    assert vals.max() <= 100.0, f"occurrence reached {vals.max()}"


# =========================================================================
# Regression tests for defects found during multi-continent verification.
# Each one encodes a specific way the package produced a plausible-looking
# wrong answer, so none of them can come back silently.
# =========================================================================

def test_clip_handles_datasets_not_just_dataarrays():
    """A Dataset has no ``.values`` array.

    Reaching for one picks up an unrelated method instead, which is how a clip
    that worked on every single-band raster failed on every multi-band STAC
    result -- the only kind that matters for imagery.
    """
    import numpy as np
    import xarray as xr

    from basinkit.clip import _all_nodata, _as_arrays

    da = xr.DataArray(
        np.ones((4, 4)), dims=("y", "x"),
        coords={"y": np.arange(4.0), "x": np.arange(4.0)},
    )
    ds = xr.Dataset({"red": da, "nir": da * 2})

    assert len(_as_arrays(ds)) == 2
    assert len(_as_arrays(da)) == 1
    assert not _all_nodata(ds)
    assert _all_nodata(xr.Dataset({"red": da * np.nan}))


def test_clip_never_forces_a_lazy_cube():
    """The empty-result check must not compute a dask-backed stack.

    Forcing it would throw away the laziness that makes a multi-gigabyte STAC
    cube usable in the first place.
    """
    import numpy as np
    import xarray as xr

    from basinkit.clip import _is_worth_checking

    eager = xr.DataArray(np.ones((4, 4)), dims=("y", "x"))
    assert _is_worth_checking(eager)

    pytest.importorskip("dask")
    lazy = eager.chunk({"x": 2})
    assert not _is_worth_checking(lazy)


def test_stac_scaling_is_read_from_metadata_not_hardcoded():
    """Scale and offset differ by mission and by processing baseline.

    Hard-coding either produces reflectances that look plausible and are wrong
    by a constant factor, so they are read from each asset's raster:bands.
    """
    from basinkit.sources.stac import asset_scaling

    class Asset:
        def __init__(self, fields):
            self.extra_fields = fields

    class Item:
        def __init__(self, assets, props=None):
            self.assets = assets
            self.properties = props or {}

    landsat = Item({"red": Asset({"raster:bands": [
        {"scale": 2.75e-05, "offset": -0.2, "nodata": 0}]})})
    got = asset_scaling([landsat], ["red"])["red"]
    assert got["scale"] == 2.75e-05
    assert got["offset"] == -0.2
    assert got["nodata"] == 0


def test_sentinel2_offset_is_not_applied_twice():
    """Earth Search pre-applies the baseline-04.00 BOA offset and flags it.

    It still publishes the nominal -0.1 in raster:bands, so applying that too
    yields negative surface reflectance -- measured at a mean of -0.05 over a
    green catchment before this guard existed.
    """
    from basinkit.sources.stac import asset_scaling

    class Asset:
        def __init__(self, fields):
            self.extra_fields = fields

    class Item:
        def __init__(self, assets, props):
            self.assets = assets
            self.properties = props

    band = {"raster:bands": [{"scale": 0.0001, "offset": -0.1, "nodata": 0}]}

    applied = Item({"red": Asset(band)}, {"earthsearch:boa_offset_applied": True})
    assert asset_scaling([applied], ["red"])["red"]["offset"] == 0.0

    not_applied = Item({"red": Asset(band)}, {"earthsearch:boa_offset_applied": False})
    assert asset_scaling([not_applied], ["red"])["red"]["offset"] == -0.1


def test_sentinel1_gets_a_smaller_pixel_budget_than_optical():
    """RTC frames are float32 at 10 m over 20k-by-30k pixels.

    A byte of RTC costs far more network time than a byte of Sentinel-2, so it
    cannot share the optical budget without the first call appearing to hang.
    """
    from basinkit.sources.stac import DEFAULT_PIXEL_BUDGET, PIXEL_BUDGET

    assert PIXEL_BUDGET["sentinel1_rtc"] < DEFAULT_PIXEL_BUDGET


def test_persiann_accepts_a_bare_year():
    from basinkit.sources.climate import _as_date

    assert _as_date(2020) == "2020-01-01"
    assert _as_date("2020") == "2020-01-01"
    assert _as_date(2020, end_of_year=True) == "2020-12-31"
    assert _as_date("2020-03-15") == "2020-03-15"


def test_available_water_capacity_cannot_be_negative():
    """Field capacity below wilting point is prediction noise, not a soil."""
    import inspect

    from basinkit.sources.soil import available_water_capacity

    assert "awc >= 0" in inspect.getsource(available_water_capacity)


# ---------------------------------------------------------------- network
@pytest.mark.network
def test_outlet_on_a_riverbank_snaps_to_the_main_stem():
    """Rhine at Lobith: the containing level-12 unit drains 270 km2.

    The main-stem unit, 200 m away, drains 158,835 km2. Taking the containing
    unit returns a basin three orders of magnitude too small -- and because
    HydroBASINS' own UP_AREA agrees with it, every internal consistency check
    still passes. This is the wrong answer that never announces itself.
    """
    with pytest.warns(UserWarning, match="bank of a much larger river"):
        b = bk.Basin.from_point(51.840, 6.110, backend="hydrobasins", progress=False)

    assert b.area_km2 == pytest.approx(160_800, rel=0.15)
    assert b.provenance["snapped_to_main_stem"] is True
    assert b.provenance["snap_ratio"] > 100
    assert b.provenance["snap_distance_km"] < 1.0


@pytest.mark.network
def test_snapping_leaves_a_correct_outlet_alone():
    """Koshi at Chatara already sits on the main stem; nothing should move."""
    b = bk.Basin.from_point(26.870, 87.150, backend="hydrobasins", progress=False)
    assert "snapped_to_main_stem" not in b.provenance
    assert b.area_km2 == pytest.approx(54_100, rel=0.05)


@pytest.mark.network
@pytest.mark.parametrize(
    "name,lat,lon,published,tol",
    [
        ("Danube @ Bratislava", 48.140,  17.110,   131_300, 0.10),
        ("Amazon @ Obidos",     -1.947, -55.511, 4_680_000, 0.10),
        ("Mekong @ Pakse",      15.117, 105.800,   545_000, 0.10),
        ("Godavari @ Polavaram", 17.240, 81.650,   307_800, 0.10),
    ],
)
def test_areas_match_published_figures_across_continents(name, lat, lon, published, tol):
    """External check on four continents against operating-agency figures."""
    b = bk.Basin.from_point(lat, lon, backend="hydrobasins", progress=False)
    assert b.area_km2 == pytest.approx(published, rel=tol), name


@pytest.mark.network
def test_two_independent_delineation_datasets_agree():
    """HydroBASINS (graph traversal) vs the MERIT-Hydro-backed service.

    Different source DEMs, different algorithms, no shared code. Agreement is
    real evidence; a large divergence would mean one of them is wrong.
    """
    hb = bk.Basin.from_point(26.870, 87.150, backend="hydrobasins", progress=False)
    api = bk.Basin.from_point(26.870, 87.150, backend="api")
    assert api.area_km2 == pytest.approx(hb.area_km2, rel=0.05)


@pytest.mark.network
def test_sentinel2_returns_physical_reflectance():
    """The full optical chain, checked against a value with a known answer.

    A temperate cropland-and-forest basin in July has a published NDVI around
    0.6 to 0.85. Getting that requires the search, the nodata masking, the
    scale, the offset, the composite and the clip all to be right.
    """
    import numpy as np

    b = bk.Basin.from_point(50.923, 6.357, backend="hydrobasins", progress=False)
    ds = b.sentinel2("2023-07-01", "2023-08-31", cloud_cover=10)

    red = np.asarray(ds["red"].compute().values, dtype="float64")
    nir = np.asarray(ds["nir"].compute().values, dtype="float64")
    good = np.isfinite(red) & np.isfinite(nir)

    assert red[good].mean() > 0, "negative mean reflectance means a double-applied offset"
    assert 0 < red[good].mean() < 0.2

    ndvi = (nir[good] - red[good]) / (nir[good] + red[good])
    assert 0.55 < float(np.median(ndvi)) < 0.95


@pytest.mark.network
def test_clipping_masks_the_polygon_not_the_bounding_box():
    """The finite fraction of a clipped stack should track bbox efficiency."""
    import numpy as np

    b = bk.Basin.from_point(50.923, 6.357, backend="hydrobasins", progress=False)
    ds = b.sentinel2("2023-07-01", "2023-08-31", cloud_cover=10)
    finite = np.isfinite(np.asarray(ds["red"].compute().values)).mean()
    assert finite == pytest.approx(b.bbox_efficiency, abs=0.08)


@pytest.mark.network
def test_exported_rasters_declare_their_nodata():
    """A masked array that loses its nodata on write is not actually delivered.

    The pixels outside the basin are NaN in memory, but a GeoTIFF with no
    declared nodata renders them as solid black in QGIS and comes back
    unmasked from rasterio -- so the clip silently stops existing the moment
    the file leaves Python.
    """
    import tempfile

    import numpy as np
    import rasterio

    b = bk.Basin.from_point(48.140, 17.110, backend="hydrobasins", progress=False)
    with tempfile.TemporaryDirectory() as tmp:
        manifest = b.download_all(tmp, layers=("dem",), progress=False)
        assert "dem" in manifest["layers"], manifest["failed"]
        with rasterio.open(f"{tmp}/{manifest['layers']['dem']}") as src:
            assert src.nodata is not None, "exported raster has no declared nodata"
            arr = src.read(1, masked=True)
            masked_fraction = float(np.asarray(arr.mask).mean())
        assert masked_fraction == pytest.approx(1 - b.bbox_efficiency, abs=0.08)


def test_no_numpy_2_removed_apis():
    """``ndarray.ptp()`` and friends were removed in NumPy 2.0.

    ``pyproject`` allows ``numpy>=1.24``, so a method form that only exists in
    1.x breaks on every current install -- and it breaks at call time, deep
    inside a plotting helper the test suite was not exercising.
    """
    import pathlib
    import re

    removed = re.compile(
        r"\.ptp\(\)|\.itemset\(|np\.(float_|NaN|NAN|Inf|INF|alltrue|product"
        r"|cumproduct|round_|string_|unicode_|in1d|row_stack|trapz|sometrue)\b"
    )
    root = pathlib.Path(__file__).resolve().parent.parent / "basinkit"
    offenders = [
        f"{path.name}:{i}: {line.strip()}"
        for path in root.rglob("*.py")
        for i, line in enumerate(path.read_text().splitlines(), 1)
        if removed.search(line) and "removed in NumPy 2.0" not in line
    ]
    assert not offenders, "NumPy 2.0 removed these:\n" + "\n".join(offenders)


def test_plot_renders_without_a_display():
    """The static figure path had never been executed until it was audited."""
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg")

    import numpy as np
    import rioxarray  # noqa: F401  (registers the .rio accessor)
    import xarray as xr
    from shapely.geometry import box

    from basinkit import viz

    basin = bk.Basin.from_geometry(box(17.0, 48.0, 17.4, 48.4))

    # Feed it a synthetic DEM so the test needs no network.
    xs = np.linspace(17.0, 17.4, 40)
    ys = np.linspace(48.4, 48.0, 40)
    elev = xr.DataArray(
        np.outer(np.linspace(200, 900, 40), np.ones(40)).astype("float32"),
        dims=("y", "x"), coords={"y": ys, "x": xs},
    ).rio.write_crs("EPSG:4326")

    basin.dem = lambda **kwargs: elev
    basin.rivers = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("no network"))

    fig = viz.plot(basin)
    assert fig is not None
    titles = [ax.get_title() for ax in fig.axes]
    assert any("Elevation" in t for t in titles)
    assert any("Hypsometry" in t for t in titles)
    # A linear elevation ramp has a hypsometric integral of exactly 0.5.
    hyps = next(t for t in titles if "Hypsometry" in t)
    assert "0.50" in hyps, hyps


# =========================================================================
# The catalogue must not promise what the code cannot deliver.
# =========================================================================

def test_default_stack_is_actually_implemented():
    for key in catalog.DEFAULT_STACK:
        assert catalog.get(key).implemented, f"{key} is default but has no fetcher"


def test_unimplemented_datasets_raise_with_instructions():
    """A catalogue entry with no fetcher must say so, and say what to do."""
    for ds in catalog.unimplemented():
        with pytest.raises(bk.NotImplementedSource) as exc:
            catalog.require(ds.key)
        message = str(exc.value)
        assert ds.route in message, f"{ds.key} does not tell the user where to get it"
        assert "clip_raster" in message, f"{ds.key} does not say what to do with it"


def test_require_returns_implemented_datasets_unchanged():
    assert catalog.require("cop30").key == "cop30"


def test_catalogue_table_marks_what_cannot_be_fetched():
    rendered = catalog.table()
    assert "DOC" in rendered
    assert "fetch=DOC" in rendered


def test_implemented_and_unimplemented_partition_the_catalogue():
    assert len(catalog.implemented()) + len(catalog.unimplemented()) == len(catalog.DATASETS)
    assert catalog.implemented(), "nothing is implemented?"


def test_basinatlas_extent_code_is_read_from_the_right_position():
    """Extent is the first letter of the third token, not a trailing suffix.

    ``pre_mm_uyr`` is upstream, ``run_mm_syr`` is the local sub-catchment,
    ``dis_m3_pyr`` is at the pour point. Treating it as a suffix matches
    nothing at all, which is how ``attributes()`` first returned an empty dict.
    """
    from basinkit.sources.attributes import describe

    row = {
        "HYBAS_ID": 1, "UP_AREA": 100.0,
        "pre_mm_uyr": 851, "run_mm_syr": 400, "dis_m3_pyr": 1600,
    }
    upstream = describe(row, extent="u")
    assert "precipitation [pre_mm_uyr]" in upstream
    assert not any("run_mm_syr" in k for k in upstream)

    local = describe(row, extent="s")
    assert any("run_mm_syr" in k for k in local)


def test_basinatlas_scaled_integers_are_decoded():
    """Read raw, the Koshi appears to average 50 degrees C and a 204 degree slope."""
    from basinkit.sources.attributes import describe

    out = describe({"tmp_dc_uyr": 50, "slp_dg_uav": 204, "ari_ix_uav": 88})
    assert out["air temperature (degC) [tmp_dc_uyr]"] == 5.0
    assert out["slope (degrees) [slp_dg_uav]"] == 20.4
    assert out["aridity index (index) [ari_ix_uav]"] == 0.88


def test_attributes_needs_a_hydrobasins_delineation():
    """BasinATLAS is keyed by HydroBASINS id, so other backends cannot use it."""
    from shapely.geometry import box

    basin = bk.Basin.from_geometry(box(0, 0, 1, 1))
    with pytest.raises(ValueError, match="hydrobasins"):
        basin.attributes()


# =========================================================================
# Paths an audit found had never been executed.
# =========================================================================

def test_from_file_round_trips_a_basin():
    import tempfile

    from shapely.geometry import box

    original = bk.Basin.from_geometry(box(17.0, 48.0, 17.4, 48.4))
    with tempfile.TemporaryDirectory() as tmp:
        path = f"{tmp}/basin.geojson"
        original.to_geojson(path)
        loaded = bk.Basin.from_file(path)
    assert loaded.area_km2 == pytest.approx(original.area_km2, rel=1e-6)
    assert loaded.provenance["backend"] == "file"


def test_from_file_reprojects_to_wgs84():
    import tempfile

    import geopandas as gpd
    from shapely.geometry import box

    with tempfile.TemporaryDirectory() as tmp:
        path = f"{tmp}/utm.geojson"
        gpd.GeoDataFrame(
            geometry=[box(600_000, 5_300_000, 640_000, 5_340_000)], crs="EPSG:32633"
        ).to_file(path, driver="GeoJSON")
        loaded = bk.Basin.from_file(path)
    west, south, east, north = loaded.bounds
    assert -180 <= west <= 180 and -90 <= south <= 90
    assert loaded.area_km2 == pytest.approx(1_600, rel=0.02)   # 40 km x 40 km


def test_dem_backend_refuses_a_basin_larger_than_its_window():
    """Growing past the ceiling must raise, not return a truncated basin.

    A basin that reaches the edge of the DEM window is partly off-map. Silently
    returning it would be a plausible-looking answer that is simply missing an
    arbitrary piece.
    """
    import inspect

    from basinkit.delineate import dem as dem_backend

    source = inspect.getsource(dem_backend.delineate_dem)
    assert "max_window_deg" in source
    assert "too large for the DEM backend" in source


def test_dem_backend_excludes_window_edge_cells_when_snapping():
    """An edge cell absorbs everything leaving the window.

    Its upstream area is an artefact of where the raster was cropped, so
    snapping onto one returns a basin that is mostly off-map.
    """
    import numpy as np

    from basinkit.delineate.dem import _snap_to_stream

    uparea = np.full((21, 21), 0.01)
    uparea[0, :] = 9_999.0          # edge: huge, but an artefact
    uparea[10, 12] = 40.0           # the real channel

    row, col, area = _snap_to_stream(None, uparea, 10, 10, search_px=8,
                                     min_uparea_km2=1.0)
    assert (row, col) == (10, 12)
    assert area == 40.0


def test_snap_fails_loudly_when_nothing_nearby_is_a_channel():
    import numpy as np

    from basinkit.delineate.dem import _snap_to_stream

    with pytest.raises(bk.OutletSnapError, match="hillslope"):
        _snap_to_stream(None, np.full((21, 21), 0.01), 10, 10,
                        search_px=5, min_uparea_km2=1.0)


def test_explore_returns_a_map_object():
    """The interactive path had never run: leafmap was not installed."""
    pytest.importorskip("leafmap")
    from shapely.geometry import box

    basin = bk.Basin.from_geometry(box(17.0, 48.0, 17.4, 48.4))
    basin.provenance["outlet"] = (48.2, 17.2)
    m = basin.explore()
    assert m is not None
    assert hasattr(m, "add_gdf") or hasattr(m, "add_child")


def test_explore_zoom_scales_with_basin_size():
    pytest.importorskip("leafmap")
    from shapely.geometry import box

    small = bk.Basin.from_geometry(box(17.0, 48.0, 17.05, 48.05))
    large = bk.Basin.from_geometry(box(10.0, 40.0, 30.0, 55.0))
    assert small.explore().zoom > large.explore().zoom


@pytest.mark.network
def test_basinatlas_agrees_with_our_own_dem():
    """BasinATLAS ships a mean elevation; basinkit computes one from COP-DEM.

    Two entirely separate pipelines over the same catchment. If they disagree,
    one of them is wrong.
    """
    b = bk.Basin.from_point(26.870, 87.150, backend="hydrobasins", progress=False)
    attrs = b.attributes(prefixes=("ele", "pre", "tmp", "slp"))

    theirs = attrs["elevation [ele_mt_uav]"]
    ours = b.terrain_stats()["elev_mean_m"]
    assert float(theirs) == pytest.approx(ours, rel=0.05)

    # Scaled integers must arrive decoded, not raw.
    assert -25 < attrs["air temperature (degC) [tmp_dc_uyr]"] < 35
    assert 0 <= attrs["slope (degrees) [slp_dg_uav]"] < 60


# =========================================================================
# The referee found the same basin quoted with two different reference areas
# across two documents, and the flattering one had become the headline. These
# guard the distinction that caused it.
# =========================================================================

def test_internal_and_external_checks_are_not_confused_in_the_docs():
    """``reported_up_area_km2`` is HydroBASINS' own bookkeeping, not a reference.

    Comparing a HydroBASINS-derived polygon to it is close to circular: it can
    catch a bug in the traversal and nothing else. Quoting it as accuracy made
    the Koshi read 0.15% instead of 0.73%.
    """
    import pathlib

    doc = (pathlib.Path(__file__).resolve().parent.parent
           / "docs" / "delineation.md").read_text()
    assert "not an accuracy figure" in doc
    assert "54,100" in doc, "the published reference must appear beside the internal one"


# ------------------------------------------------------------ morphometry


def test_strahler_streams_are_not_dataset_reaches():
    """A stream of order u runs until another order-u stream destroys it.

    River datasets store one stream as several reaches, so counting rows per
    order inflates every order above the first. On the Koshi that turns the
    bifurcation ratios into 2.3, 1.8, 2.0, 1.1, 1.9, 17.1 -- a ratio of 1.09
    is not physically possible -- against 4.7, 4.6, 4.3, 5.3, 3.0, 2.0 when
    streams are counted properly.

    Network below: 1 and 2 are headwaters joining at 3, which is order 2 and
    continues through 4 and 6. 5 is a headwater joining the trunk at 6.
    Three order-1 streams; ONE order-2 stream carried by three reaches.
    """
    from basinkit.morphometry import _streams_per_order

    ids       = [1, 2, 3, 4, 5, 6]
    next_down = [3, 3, 4, 6, 6, 0]
    orders    = [1, 1, 2, 2, 1, 2]

    assert _streams_per_order(ids, next_down, orders) == {1: 3, 2: 1}

    naive = {u: orders.count(u) for u in set(orders)}
    assert naive == {1: 3, 2: 3}, "the naive count is what this must not do"


def test_a_stream_with_no_continuation_counts_once():
    from basinkit.morphometry import _streams_per_order

    assert _streams_per_order([1, 2, 3], [3, 3, 0], [1, 1, 2]) == {1: 2, 2: 1}


def test_bifurcation_ratio_below_two_is_reported_as_impossible():
    """Rb < 2 is not a low value; it is an arithmetic impossibility.

    Every order-(u+1) stream is made by two order-u streams joining, so
    N(u) >= 2*N(u+1). Three order-2 streams cannot sit above two order-3
    streams. A published table that shows this counted reaches.
    """
    from basinkit.morphometry import _consistency

    w = _consistency({1: 20, 2: 3, 3: 2}, [1, 2, 3], rbm=4.0)
    floor = [x for x in w if x["check"] == "bifurcation_ratio_floor"]
    assert len(floor) == 1
    assert floor[0]["severity"] == "impossible"
    assert floor[0]["orders"] == [2, 3]
    assert "1.50" in floor[0]["message"]


def test_a_clean_network_raises_nothing():
    from basinkit.morphometry import _consistency

    assert _consistency({1: 16, 2: 4, 3: 1}, [1, 2, 3], rbm=4.0) == []


def test_more_than_one_stream_of_the_highest_order_is_impossible():
    """Two order-3 streams in a 3rd-order basin would meet and make order 4."""
    from basinkit.morphometry import _consistency

    w = _consistency({1: 40, 2: 12, 3: 5}, [1, 2, 3], rbm=4.0)
    top = [x for x in w if x["check"] == "single_highest_order_stream"]
    assert len(top) == 1
    assert top[0]["severity"] == "impossible"


def test_an_unusual_bifurcation_ratio_is_flagged_but_not_called_wrong():
    """Strahler's 3-5 is an empirical range, not a constraint."""
    from basinkit.morphometry import _consistency

    w = _consistency({1: 100, 2: 10, 3: 1}, [1, 2, 3], rbm=9.33)
    assert [x["severity"] for x in w] == ["unusual"]


def test_channel_gradient_follows_the_bed_not_the_basin_relief():
    """A ridge top is not the head of the main channel.

    The DEM here is a plain that falls 10 m over the 1 degree the channel
    crosses, with one 2000 m peak away from the river. Basin relief divided
    by channel length would report about 18 m/km; the bed falls about 0.09.
    """
    import numpy as np
    import rioxarray  # noqa: F401
    import xarray as xr
    from shapely.geometry import LineString

    from basinkit.morphometry import _stem_profile

    lons = np.linspace(85.0, 86.0, 101)
    lats = np.linspace(27.0, 27.5, 51)
    z = np.tile(np.linspace(1010.0, 1000.0, 101), (51, 1))
    z[45, 90] = 3000.0                       # a peak nowhere near the channel
    dem = xr.DataArray(z, coords={"y": lats, "x": lons}, dims=("y", "x"))
    dem = dem.rio.write_crs("EPSG:4326")

    line = LineString([(85.0, 27.05), (86.0, 27.05)])
    z_head, z_mouth = _stem_profile(line, "EPSG:4326", dem, n=50)

    assert z_head - z_mouth == pytest.approx(10.0, abs=0.5)
    assert (z_head - z_mouth) / 111.0 < 0.2   # not the 18 m/km relief shortcut


def test_a_spike_in_the_profile_does_not_become_the_gradient():
    """A centreline crossing a bank pixel must not invent a fall."""
    import numpy as np
    import rioxarray  # noqa: F401
    import xarray as xr
    from shapely.geometry import LineString

    from basinkit.morphometry import _stem_profile

    lons = np.linspace(85.0, 86.0, 101)
    z = np.tile(np.linspace(100.0, 90.0, 101), (3, 1))
    z[:, 50] = 400.0                          # a bridge deck on the centreline
    dem = xr.DataArray(z, coords={"y": [27.0, 27.05, 27.1], "x": lons},
                       dims=("y", "x")).rio.write_crs("EPSG:4326")

    z_head, z_mouth = _stem_profile(
        LineString([(85.0, 27.05), (86.0, 27.05)]), "EPSG:4326", dem, n=101)
    assert z_head == pytest.approx(100.0, abs=1.0)
    assert z_mouth == pytest.approx(90.0, abs=1.0)


def test_morphometry_needs_strahler_orders():
    """Without orders none of the linear parameters mean anything."""
    from basinkit.morphometry import morphometry

    class _NoOrders:
        centroid = (27.0, 85.0)
        geometry = box(85.0, 27.0, 85.1, 27.1)

        def rivers(self, **kw):
            return gpd.GeoDataFrame(
                {"HYRIV_ID": [1]},
                geometry=[LineString([(85.0, 27.0), (85.1, 27.1)])],
                crs="EPSG:4326")

    with pytest.raises(ValueError, match="ORD_STRA"):
        morphometry(_NoOrders())


# ------------------------------------------------------------- land cover


class _Item:
    def __init__(self, ident, start=None):
        self.id = ident
        self.properties = {"start_datetime": start} if start else {}


def test_item_year_prefers_the_declared_coverage_window():
    from basinkit.sources.landcover import _item_year

    assert _item_year(_Item("45R-2023", "2023-01-01T00:00:00Z")) == 2023
    assert _item_year(_Item("45R-2019")) == 2019        # falls back to the id
    assert _item_year(_Item("weird")) is None


def test_class_fractions_reads_the_legend_off_the_array():
    """WorldCover and ESRI number their classes differently.

    Code 10 is tree cover in one scheme and cloud in the other. Defaulting to
    WorldCover for every raster reported ESRI cloud as forest, in a dictionary
    that looked entirely reasonable. The legend now travels with the data.
    """
    import xarray as xr

    from basinkit.sources.landcover import (
        ESRI_CLASSES,
        WORLDCOVER_CLASSES,
        class_fractions,
    )

    grid = np.full((4, 4), 10, dtype="uint8")

    esri = xr.DataArray(grid, dims=("y", "x"),
                        attrs={"classes": str(ESRI_CLASSES)})
    assert class_fractions(esri) == {"Clouds": 1.0}

    wc = xr.DataArray(grid, dims=("y", "x"),
                      attrs={"classes": str(WORLDCOVER_CLASSES)})
    assert class_fractions(wc) == {"Tree cover": 1.0}

    assert class_fractions(xr.DataArray(grid, dims=("y", "x"))) == {"Tree cover": 1.0}


def test_class_fractions_survives_a_dataset():
    """A Dataset has no ``.values`` array -- it has a ``.values`` method.

    This is the same defect that once broke clipping on every multi-band STAC
    result. It was fixed there and left standing here, which is why the ESRI
    land-cover path raised on a TypeError from deep inside numpy.
    """
    import xarray as xr

    from basinkit.sources.landcover import class_fractions

    da = xr.DataArray(np.full((3, 3), 20, dtype="uint8"), dims=("y", "x"))
    assert class_fractions(da.to_dataset(name="data")) == {"Shrubland": 1.0}

    two = xr.Dataset({"a": da, "b": da})
    with pytest.raises(ValueError, match="one land-cover band"):
        class_fractions(two)


def test_class_fractions_handles_integer_rasters():
    """Land cover is categorical integers; np.isfinite is float-only."""
    import xarray as xr

    from basinkit.sources.landcover import class_fractions

    grid = np.array([[10, 10, 20], [0, 20, 20]], dtype="uint8")   # 0 = nodata
    out = class_fractions(xr.DataArray(grid, dims=("y", "x")))
    assert out == {"Shrubland": 0.6, "Tree cover": 0.4}


# ---------------------------------------------------------------- 3D export


def _fake_dem(values):
    """A minimal stand-in for what Basin.dem() returns."""
    import xarray as xr

    arr = np.asarray(values, dtype="float32")
    return xr.DataArray(
        arr, dims=("y", "x"),
        coords={"y": np.linspace(1, 0, arr.shape[0]),
                "x": np.linspace(0, 1, arr.shape[1])})


def test_heights_reserve_zero_for_outside_the_basin():
    """The mesh needs to know where the basin is not, or it fills its own holes.

    0 is the sentinel; every real elevation packs into 1..65535. Getting this
    wrong makes the lowest point in the basin indistinguishable from the void
    around it, and the terrain grows a skirt.
    """
    from basinkit.viz3d import _heights

    grid = np.array([[100.0, 200.0, np.nan],
                     [150.0, 250.0, 300.0]], dtype="float32")
    b64, meta = _heights(_fake_dem(grid), mesh_width=8)

    packed = np.frombuffer(base64.b64decode(b64), dtype="<u2")
    assert meta["zmin"] == 100.0 and meta["zmax"] == 300.0
    assert meta["h"] == 2 and meta["w"] == 3
    assert packed[2] == 0, "the NaN cell must pack to the outside-basin sentinel"
    assert packed[0] == 1, "the minimum elevation must be 1, not 0"
    assert packed.max() == 65535


def test_heights_refuse_an_empty_basin():
    from basinkit.viz3d import _heights

    with pytest.raises(ValueError, match="empty"):
        _heights(_fake_dem(np.full((3, 3), np.nan)), mesh_width=8)


def test_rivers_are_normalised_into_basin_coordinates():
    from basinkit.viz3d import _rivers

    gdf = gpd.GeoDataFrame(
        {"UPLAND_SKM": [12.0]},
        geometry=[LineString([(10.0, 20.0), (11.0, 21.0)])], crs="EPSG:4326")
    lines = _rivers(gdf, (10.0, 20.0, 11.0, 21.0))

    assert len(lines) == 1
    assert lines[0]["p"] == [[0.0, 0.0], [1.0, 1.0]]
    assert lines[0]["u"] == 12.0


def test_the_3d_template_has_no_unfilled_slots():
    """Every placeholder must be one the exporter actually fills.

    The template is a 13 KB blob of HTML, CSS and JavaScript. A renamed token
    would leave a literal ``__TITLE__`` on a published page, and no other test
    would notice.
    """
    from basinkit import viz3d

    slots = set(re.findall(r"__[A-Z_]+__", viz3d._TEMPLATE))
    assert slots == {"__THREE__", "__TITLE__", "__SUBTITLE__", "__FACTS__",
                     "__CREDIT__", "__EX__", "__PAYLOAD__", "__HASTEX__"}


def test_facts_table_renders_pairs():
    from basinkit.viz3d import _facts_html

    assert _facts_html(None) == ""
    html = _facts_html({"Basin area": "3,198 km²"})
    assert "<dt>Basin area</dt><dd>3,198 km²</dd>" in html


def test_documented_example_uses_one_verified_coordinate():
    """Every user-facing example must use the outlet the network tests check.

    The README once advertised ``from_point(26.5, 85.2)`` returning
    "14,384 km2". That coordinate sits 16 km off the Bagmati channel and
    actually returns 434 km2 -- so the first code block any new user ran
    disagreed with its own printed output by a factor of thirty. The figure
    had gone stale and nothing was watching it.

    Nothing here can re-check the area offline. What it can do is stop the
    documented coordinate drifting away from the one
    ``test_koshi_area_matches_hydrobasins_up_area`` actually verifies.
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parent.parent
    files = ["README.md", "docs/index.md", "docs/tutorial.md",
             "basinkit/__init__.py", "basinkit/basin.py", "basinkit/cli.py"]

    found = set()
    for name in files:
        text = (root / name).read_text()
        found |= set(re.findall(r"from_point\(\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)", text))
        found |= set(re.findall(r"--lat\s+(-?\d+\.?\d*)\s+--lon\s+(-?\d+\.?\d*)", text))

    assert found, "no example coordinate found in the documentation at all"
    assert found == {("26.87", "87.15")}, (
        f"documented examples use {sorted(found)}; only the verified Chatara "
        "outlet (26.87, 87.15) may appear, because that is the one the network "
        "suite checks against the published 54,100 km2"
    )


def test_readme_quotes_a_distribution_not_a_single_basin():
    """The README must not offer one flattering accuracy figure.

    It used to lead with twelve hand-picked gauges and a median error of 0.74
    percent. That figure describes those twelve, which were selected because their
    areas are published and are therefore large, well-mapped rivers. Blind
    validation across 2,550 gauges puts the median error below 100 km2 at 181
    percent, so the accuracy belongs to a size band rather than to the tool.

    So this asserts three things: a sample size is stated, the accuracy is
    broken out by catchment size, and no headline figure appears without that
    context.
    """
    import pathlib
    import re

    readme = (pathlib.Path(__file__).resolve().parent.parent / "README.md").read_text()

    assert re.search(r"\b\d[\d,]{2,}\s+gauges\b", readme), (
        "the sample size must be stated, and it must be the blind sample "
        "rather than the twelve demonstration basins"
    )
    assert "median" in readme.lower()

    # Reported by size, which is the only way these numbers mean anything.
    for band in ("100,000", "10,000", "2,000", "below 100"):
        assert band in readme, f"accuracy is not broken out around {band} km2"

    # The old headline, and its descendants, must not reappear unqualified.
    for banned in ("median error is 0.74", "below one percent",
                   "under one percent"):
        assert banned not in readme.lower(), (
            f"{banned!r} is the single-figure claim this test exists to stop"
        )


@pytest.mark.network
def test_published_reference_is_used_for_the_accuracy_claim():
    """The Koshi against its published area, not against HydroBASINS' own field."""
    b = bk.Basin.from_point(26.870, 87.150, backend="hydrobasins", progress=False)

    published = 54_100                     # operating-agency figure at Chatara
    internal = b.provenance["reported_up_area_km2"]

    external_error = abs(b.area_km2 - published) / published
    internal_error = abs(b.area_km2 - internal) / internal

    assert internal_error < external_error, (
        "the internal check is expected to be the flattering one -- that is "
        "exactly why it must not be quoted as accuracy"
    )
    assert 0.004 < external_error < 0.02

def test_every_source_accepts_progress():
    """One argument, spelled the same way, everywhere.

    `basin.dem(progress=False)` worked while `basin.soil(progress=False)`
    raised TypeError, because the Basin methods forward **kwargs and only some
    of the underlying source functions declared the argument. A script that
    silences one of them should not have to know which ones support it, and the
    failure only appears at runtime, on the call that downloads.
    """
    import inspect

    from basinkit.sources import attributes, climate, landcover, soil, vectors, water

    # basinkit.sources re-exports a function called dem, which shadows the
    # module of the same name, so this one is imported by its full path.
    from basinkit.sources.dem import dem as dem_fn

    functions = [
        dem_fn, landcover.worldcover,
        soil.soilgrids, soil.available_water_capacity,
        climate.chirps, climate.persiann, climate.terraclimate,
        climate.water_balance,
        vectors.hydrorivers, vectors.hydrolakes,
        water.global_surface_water,
        attributes.hydroatlas, attributes.describe,
    ]
    missing = [
        f.__name__ for f in functions
        if "progress" not in inspect.signature(f).parameters
        and not any(p.kind is p.VAR_KEYWORD
                    for p in inspect.signature(f).parameters.values())
    ]
    assert not missing, f"these reject progress=: {missing}"


def test_the_corrective_switch_is_gated_on_distance():
    """A river a kilometre away is not the river the click is on.

    The corrective re-delineation fires when the river network and a DEM
    routing of the same point agree that HydroBASINS over-captured. Those two
    stop being independent when the click is not on a river at all: both then
    describe whatever drain happens to be nearby. Central Delhi went from
    36,944 km2 to 18 before this gate existed.

    All 25 corrective switches that were right had their corroborating reach
    within 0.91 km; five clicks that would have been rewritten wrongly all had
    theirs beyond 1.3 km. The gate only ever prevents a switch, so its worst
    case is a correction not made, and it cost one in 300 gauges.
    """
    import inspect

    from basinkit.delineate import _auto

    source = inspect.getsource(_auto)
    assert "act_within_km" in source, "the distance gate is gone"
    assert "largest_distance_km" in source, (
        "the gate must test how far the corroborating river is"
    )


def test_a_refusal_buried_in_the_chain_is_still_an_upstream_outage():
    """The weekly run must stay readable when a helper replaces the exception.

    HydroSHEDS answers 403 to datacenter addresses. Where that download sits
    inside a ``pytest.warns`` block, pytest reports ``DID NOT WARN`` and the
    refusal survives only as ``__context__``. Reading the outermost exception
    alone painted the weekly source check red three runs in a row for a reason
    that had nothing to do with this package.
    """
    import conftest

    refusal = DataSourceError(
        "Access denied (403) for https://data.hydrosheds.org/file/x.zip"
    )
    try:
        try:
            raise refusal
        except DataSourceError:
            # Implicit chaining is the whole point: this is what pytest.warns
            # does, so `from` would destroy the case under test.
            raise AssertionError("DID NOT WARN")  # noqa: B904
    except AssertionError as exc:
        assert conftest._upstream_refusal(exc) is refusal, (
            "a refusal in the exception chain must still read as an outage"
        )

    assert conftest._upstream_refusal(refusal) is refusal
    assert conftest._upstream_refusal(
        DataSourceError("returned 12 km2 at Lobith, published area 158,835")
    ) is None, "a wrong number must stay a failure"


def test_the_stac_catalogue_speaks_in_data_source_errors():
    """A catalogue that cannot be opened must not surface as a library error.

    ``Client.open`` performs a network request, so it raises pystac's own
    exception type. Callers catch ``DataSourceError``; anything else reaches
    the user as a traceback instead of a sentence.
    """
    import basinkit.sources.stac as stac_mod

    def refuse(_url):
        raise RuntimeError("APIError: 503 Service Unavailable")

    original = stac_mod._client
    stac_mod._client = refuse
    try:
        with pytest.raises(DataSourceError, match=r"\(503\)"):
            stac_mod.stac_search("esri_lulc", bbox=(0.0, 0.0, 0.1, 0.1))
    finally:
        stac_mod._client = original


def test_rivers_consult_every_candidate_region(monkeypatch):
    """A basin on a seam must not come back with an empty river network.

    HydroSHEDS regional extents overlap. The lower Magdalena sits inside the
    North American extent as well as the South American one, and the North
    American file carries none of its reaches, so stopping at the first
    candidate returned zero rivers for a basin that has tens of thousands.
    """
    import geopandas as gpd
    from shapely.geometry import box

    from basinkit.delineate.hydrobasins import candidate_regions
    from basinkit.sources import vectors

    assert candidate_regions(10.25, -74.92)[0] == "na", (
        "this test is only meaningful while the first candidate is the wrong one"
    )

    geom = box(-75.2, 10.0, -74.6, 10.5)
    consulted: list[str] = []

    monkeypatch.setattr(vectors, "_unpack",
                        lambda url, name, namespace, progress=True: name)

    def fake_read_file(path, bbox=None):
        consulted.append(path)
        if path.endswith("_na"):
            return gpd.GeoDataFrame({"ORD_STRA": []}, geometry=[], crs="EPSG:4326")
        return gpd.GeoDataFrame({"ORD_STRA": [6]}, geometry=[geom], crs="EPSG:4326")

    monkeypatch.setattr(gpd, "read_file", fake_read_file)

    out = vectors.hydrorivers(geom, progress=False)

    assert any(p.endswith("_na") for p in consulted), "the first candidate was skipped"
    assert any(p.endswith("_sa") for p in consulted), (
        "the second candidate must be consulted when the first yields nothing"
    )
    assert len(out) == 1, "the reaches from the second region were dropped"
    assert out.attrs["basinkit_regions"] == ["sa"]


def test_importing_basinkit_does_not_need_the_dataframe_stack():
    """``import basinkit`` must work where pandas and geopandas are absent.

    tests/conftest.py imports the package, so every pytest run imports it,
    including the QGIS job, whose system interpreter carries the QGIS bindings
    and nothing else. A module-level ``from pandas import ...`` in one source
    file was enough to turn that job into a collection error, and the failure
    named pytest rather than the import that caused it. Every heavy dependency
    is imported inside the function that needs it; this keeps it that way.
    """
    import subprocess
    import sys

    script = (
        "import sys\n"
        "BLOCK = {'pandas', 'geopandas'}\n"
        "class Blocker:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name.split('.')[0] in BLOCK:\n"
        "            raise ImportError(name)\n"
        "        return None\n"
        "sys.meta_path.insert(0, Blocker())\n"
        "import basinkit\n"
        "from basinkit.exceptions import DataSourceError\n"
        "print('ok')\n"
    )
    done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert done.returncode == 0, (
        "importing basinkit reached pandas or geopandas at module level:\n"
        + done.stderr[-1500:]
    )


def _synthetic_dem(*, slope_m_per_m=0.1, centre_lat=0.0, n=51, deg=0.001):
    """A plane tilting down to the east, on a geographic grid at a chosen band."""
    import numpy as np
    import rioxarray  # noqa: F401  (registers the .rio accessor)
    import xarray as xr

    x = np.arange(n) * deg
    y = centre_lat + (np.arange(n) - n // 2) * deg
    metres_east = x * 111_320.0 * math.cos(math.radians(centre_lat))
    field = np.repeat((1000.0 - slope_m_per_m * metres_east)[None, :], n, axis=0)
    da = xr.DataArray(field, coords={"y": y[::-1], "x": x}, dims=("y", "x"))
    return da.rio.write_crs("EPSG:4326")


def test_slope_recovers_the_gradient_of_a_known_plane():
    """A plane of known steepness must come back at that steepness."""
    from basinkit.terrain import slope

    dem = _synthetic_dem(slope_m_per_m=0.1)
    middle = slope(dem).values[10:-10, 10:-10]
    expected = math.degrees(math.atan(0.1))
    assert abs(float(middle.mean()) - expected) < 0.05, (
        f"a 10 percent plane should read {expected:.2f} degrees, "
        f"got {float(middle.mean()):.2f}"
    )


def test_slope_accounts_for_the_shrinking_degree_of_longitude():
    """The same grid of degrees is a smaller grid of metres near the poles.

    A cell 0.001 degrees wide spans about 111 m at the equator and 56 m at 60
    degrees north. Dividing the same height difference by the same assumed
    width would report a high-latitude basin as roughly twice as steep as it
    is, which then propagates into every ruggedness and relief-ratio figure.
    """
    from basinkit.terrain import slope

    equator = _synthetic_dem(slope_m_per_m=0.1, centre_lat=0.0)
    high = _synthetic_dem(slope_m_per_m=0.1, centre_lat=60.0)

    a = float(slope(equator).values[10:-10, 10:-10].mean())
    b = float(slope(high).values[10:-10, 10:-10].mean())
    assert abs(a - b) < 0.1, (
        "the same physical plane read differently at two latitudes: "
        f"{a:.2f} vs {b:.2f} degrees"
    )


def test_aspect_points_down_the_slope_and_leaves_flat_ground_undecided():
    """Aspect is a compass bearing; flat ground has none and must not read north."""
    import numpy as np

    from basinkit.terrain import aspect

    dem = _synthetic_dem(slope_m_per_m=0.1)          # falls towards the east
    facing = aspect(dem).values[10:-10, 10:-10]
    assert abs(float(np.nanmean(facing)) - 90.0) < 1.0, (
        f"a plane falling east should face 90 degrees, got {float(np.nanmean(facing)):.1f}"
    )

    flat = aspect(_synthetic_dem(slope_m_per_m=0.0)).values
    assert np.isnan(flat).all(), "flat ground must be undecided, not north-facing"


def test_hillshade_stays_inside_its_range():
    import numpy as np

    from basinkit.terrain import hillshade

    shaded = hillshade(_synthetic_dem(slope_m_per_m=0.3)).values
    assert np.nanmin(shaded) >= 0.0 and np.nanmax(shaded) <= 1.0


def test_terrain_layers_keep_their_georeferencing():
    """A derived layer that loses its CRS cannot be written or overlaid."""
    from basinkit.terrain import aspect, hillshade, slope

    dem = _synthetic_dem()
    for fn in (slope, aspect, hillshade):
        out = fn(dem)
        assert out.rio.crs == dem.rio.crs, f"{fn.__name__} dropped the CRS"
        assert out.shape == dem.shape, f"{fn.__name__} changed the shape"
        assert out.attrs.get("units"), f"{fn.__name__} declared no units"


def test_subbasins_refuses_a_backend_it_cannot_serve():
    """The units exist only for the traversal backend; say so, do not guess."""
    from shapely.geometry import box

    from basinkit.basin import Basin

    basin = Basin(box(0, 0, 1, 1), {"backend": "dem"})
    with pytest.raises(ValueError, match="hydrobasins"):
        basin.subbasins()


@pytest.mark.network
def test_subbasins_return_a_closed_routing_graph():
    """The pieces must tile the basin and point at each other correctly.

    ``NEXT_DOWN`` is the routing graph. If it is sound, exactly one unit in an
    upstream set drains to something outside that set, and that one is the
    outlet. More than one means the traversal collected a neighbouring
    catchment as well, which is the failure this guards.
    """
    basin = bk.Basin.from_point(26.87, 87.15, progress=False)
    units = basin.subbasins(progress=False)

    assert len(units) > 1, "a 54,000 km2 basin is not one level-12 unit"
    for column in ("HYBAS_ID", "NEXT_DOWN", "SUB_AREA"):
        assert column in units.columns, f"{column} is what makes these routable"

    leaving = units[~units["NEXT_DOWN"].isin(units["HYBAS_ID"])]
    assert len(leaving) == 1, (
        f"{len(leaving)} units drain outside the set; a single catchment has one outlet"
    )

    declared = float(units["SUB_AREA"].sum())
    assert abs(declared - basin.area_km2) / basin.area_km2 < 0.02, (
        f"the units sum to {declared:,.0f} km2 but the basin measures "
        f"{basin.area_km2:,.0f} km2"
    )


@pytest.mark.network
def test_flow_accumulation_drains_the_basin_and_nothing_else():
    """Every cell in a catchment drains to its outlet, and no cell outside does.

    Routing over a rectangular window fills the corners with ground that
    belongs to neighbouring catchments. Left as elevation, that ground becomes
    a ridge draining inwards and the accumulation exceeds the number of cells
    in the basin, which then inflates every wetness index computed from it.
    """
    import numpy as np

    basin = bk.Basin.from_point(26.87, 87.15, progress=False)
    dem = basin.dem(max_pixels=2_000_000)
    inside = int(np.isfinite(np.asarray(dem.values)).sum())

    accumulated = np.asarray(basin.flow_accumulation(dem=dem).values)
    largest = float(np.nanmax(accumulated))

    assert largest <= inside, (
        f"the outlet accumulates {largest:,.0f} cells from a basin of {inside:,}"
    )
    assert largest > 0.5 * inside, (
        f"the outlet accumulates only {largest:,.0f} of {inside:,} cells, so the "
        "network is draining somewhere other than the outlet"
    )

    wetness = np.asarray(basin.twi(dem=dem).values)
    finite = wetness[np.isfinite(wetness)]
    assert 0 < float(np.median(finite)) < 20, (
        f"a median wetness index of {float(np.median(finite)):.1f} is outside "
        "every published range"
    )


def test_zonal_weights_by_area_not_by_cell_count():
    """A cell is not the same size everywhere, and a count pretends it is.

    On a geographic grid a cell at 60 degrees north covers half the ground of
    one at the equator. Summing cells rather than their areas reports the two
    halves of a north-south basin as equal, which is wrong by a factor of two
    at the ends of the range.
    """
    import numpy as np

    from basinkit.zonal import zonal

    dem = _synthetic_dem(slope_m_per_m=0.0, centre_lat=45.0, n=41, deg=0.01)
    split = np.broadcast_to(np.where(np.arange(41)[:, None] < 20, 1.0, 2.0), (41, 41))
    zones = dem.copy(data=split.copy())
    values = dem.copy(data=np.ones((41, 41)))

    table = zonal(values, zones, labels={1: "north", 2: "south"})
    north = table.loc[table["zone"] == "north"].iloc[0]
    south = table.loc[table["zone"] == "south"].iloc[0]

    assert north["cells"] < south["cells"], "the halves were split unevenly by design"
    # The northern half has fewer rows but its cells are the smaller ones, so
    # counting cells and measuring ground must not give the same ranking.
    per_cell_north = north["area_km2"] / north["cells"]
    per_cell_south = south["area_km2"] / south["cells"]
    assert per_cell_north < per_cell_south, (
        "cells further north must measure smaller: "
        f"{per_cell_north:.4f} against {per_cell_south:.4f} km2"
    )


def test_zonal_reports_the_statistics_it_promises():
    import numpy as np

    from basinkit.zonal import zonal

    dem = _synthetic_dem(slope_m_per_m=0.0, n=21, deg=0.01)
    split = np.broadcast_to(np.where(np.arange(21)[None, :] < 10, 1.0, 2.0), (21, 21))
    zones = dem.copy(data=split.copy())
    field = np.where(np.arange(21)[None, :] < 10, 5.0, 25.0)
    values = dem.copy(data=np.broadcast_to(field, (21, 21)).copy())

    table = zonal(values, zones, labels={1: "left", 2: "right"})
    assert set(table["zone"]) == {"left", "right"}
    assert float(table.loc[table["zone"] == "left", "mean"].iloc[0]) == 5.0
    assert float(table.loc[table["zone"] == "right", "mean"].iloc[0]) == 25.0
    assert abs(float(table["share"].sum()) - 1.0) < 1e-6, "shares must cover the basin"
    for column in ("p10", "p50", "p90", "std", "min", "max"):
        assert column in table.columns


def test_the_trend_test_finds_a_planted_trend_and_leaves_noise_alone():
    """A rank test that cannot find a real trend, or invents one, is worthless."""
    import numpy as np
    import pandas as pd

    from basinkit.climate import trend

    index = pd.date_range("1980-01-01", periods=480, freq="MS")
    noise = np.random.default_rng(7).normal(0, 5, 480)

    rising = trend(pd.Series(100 + np.arange(480) * 0.05 + noise, index=index))
    assert rising["significant"] and rising["direction"] == "increasing"
    assert abs(rising["slope"] - 0.6) < 0.1, (
        f"a planted 0.6 per year came back as {rising['slope']:.3f}"
    )

    flat = trend(pd.Series(100 + noise, index=index))
    assert not flat["significant"], (
        f"noise alone was called a trend at p={flat['p_value']}"
    )


def test_the_trend_test_refuses_a_sample_too_small_to_mean_anything():
    import pandas as pd

    from basinkit.climate import trend

    with pytest.raises(ValueError, match="at least ten"):
        trend(pd.Series([1.0, 2.0, 3.0]))


def test_spi_is_standardised_and_says_where_its_ceiling_is():
    """SPI is a z-score, so it must centre on zero and sit near unit spread."""
    import numpy as np
    import pandas as pd

    from basinkit.climate import spi

    index = pd.date_range("1985-01-01", periods=480, freq="MS")
    seasonal = 50 + 40 * np.sin(2 * np.pi * (index.month - 6) / 12)
    rainfall = pd.Series(
        np.clip(seasonal + np.random.default_rng(3).normal(0, 12, 480), 0, None),
        index=index,
    )

    z = spi(rainfall, scale=3).dropna()
    assert abs(float(z.mean())) < 0.05, f"SPI centred on {float(z.mean()):.3f}"
    assert 0.8 < float(z.std()) < 1.1, f"SPI spread {float(z.std()):.3f}"
    # Forty years behind each calendar month bounds the extreme; the docstring
    # says so, and the number has to match the claim.
    assert float(z.abs().max()) < 2.1, (
        "a ranked index cannot exceed the ceiling its record length sets"
    )


def test_comparing_basins_records_a_failure_instead_of_losing_the_run(monkeypatch):
    """One bad coordinate must not discard the basins that worked."""
    from basinkit.basin import Basin
    from basinkit.compare import compare
    from basinkit.exceptions import DelineationError

    calls = []

    def fake_from_point(lat, lon, **kwargs):
        calls.append((lat, lon))
        if lon == 0.0:
            raise DelineationError("nothing here but ocean")
        from shapely.geometry import box

        return Basin(box(lon, lat, lon + 0.1, lat + 0.1),
                     {"backend": "hydrobasins", "region": "as"})

    monkeypatch.setattr(Basin, "from_point", staticmethod(fake_from_point))

    table = compare(
        [(10.0, 20.0), (0.0, 0.0), (30.0, 40.0)],
        labels=["first", "ocean", "third"], layers=(),
    )

    assert len(table) == 3, "every input point must get a row"
    assert len(calls) == 3, "a failure must not stop the ones after it"
    import pandas as pd

    assert table.loc[table["label"] == "ocean", "error"].iloc[0]
    assert pd.isna(table.loc[table["label"] == "first", "error"].iloc[0]), (
        "a basin that worked must carry no error"
    )
    assert float(table.loc[table["label"] == "third", "area_km2"].iloc[0]) > 0


def test_comparing_refuses_labels_that_do_not_line_up():
    from basinkit.compare import compare

    with pytest.raises(ValueError, match="they must match"):
        compare([(1.0, 2.0), (3.0, 4.0)], labels=["only one"])


@pytest.mark.network
def test_height_above_drainage_is_never_negative():
    """Nothing can sit below the channel it drains into.

    Routing fills depressions; measuring against the raw elevation afterwards
    puts every filled pit below its own outlet and returns negative heights,
    which then read as the most flood-prone ground in the basin. Routing and
    measuring have to happen on the same surface.
    """
    import numpy as np

    basin = bk.Basin.from_point(26.87, 87.15, progress=False)
    heights = np.asarray(basin.hand(dem=basin.dem(max_pixels=2_000_000)).values)
    finite = heights[np.isfinite(heights)]

    assert finite.min() >= -1e-6, (
        f"{int((finite < -1e-6).sum()):,} cells came back below their own channel, "
        f"the lowest at {finite.min():,.1f} m"
    )
    assert finite.max() > 100, (
        "a Himalayan basin has ground far above its rivers; "
        f"the highest here is {finite.max():.1f} m"
    )


@pytest.mark.network
def test_land_cover_change_accounts_for_the_whole_basin():
    """Every square kilometre ends up somewhere in the transition table."""
    basin = bk.Basin.from_point(26.87, 87.15, progress=False)
    from basinkit.sources.landcover import esri_years

    years = esri_years(basin.geometry)
    table = basin.landcover_change(min(years), max(years), max_pixels=3_000_000)

    assert {"from", "to", "area_km2", "changed"} <= set(table.columns)
    total = float(table["area_km2"].sum())
    assert abs(total - basin.area_km2) / basin.area_km2 < 0.02, (
        f"the transitions sum to {total:,.0f} km2 against a basin of "
        f"{basin.area_km2:,.0f}"
    )
    assert bool(table.loc[~table["changed"], "area_km2"].sum()
                > table.loc[table["changed"], "area_km2"].sum()), (
        "most of a basin does not change land cover in six years; "
        "more change than stability means the two years are misaligned"
    )


def test_the_twelve_metre_backend_is_never_chosen_for_you():
    """A ShareAlike dataset must be asked for, not arrived at.

    Every other default in this package is CC BY 4.0 or more permissive.
    TDX-Hydro is CC BY-SA, which travels into anything derived from it and
    redistributed. A user who never named it cannot inherit a copyleft term
    from a backend the package picked on their behalf.
    """
    import inspect

    from basinkit.delineate import _OPT_IN, _auto

    assert "tdx" in _OPT_IN, "the ShareAlike backend must be marked opt-in"
    source = inspect.getsource(_auto)
    assert "tdx" not in source, (
        "backend='auto' reaches for the ShareAlike dataset; it must not"
    )


def test_the_catalogue_states_the_sharealike_obligation():
    """A licence field that says only 'open' is the failure this guards."""
    from basinkit import catalog

    entry = catalog.DATASETS["tdx_hydro"]
    assert entry.license == "CC BY-SA 4.0"
    assert entry.auth == "none", "the route is anonymous and should say so"
    assert "sharealike" in entry.extras
    assert "ShareAlike" in entry.notes, (
        "the obligation has to be in the note a user actually reads"
    )


def test_the_twelve_metre_backend_asks_for_pyarrow_by_name(monkeypatch):
    """A missing optional dependency must name itself and its extra."""
    import builtins

    from basinkit.delineate import tdx
    from basinkit.exceptions import MissingDependency

    real_import = builtins.__import__

    def refuse(name, *args, **kwargs):
        if name == "pyarrow":
            raise ImportError("no pyarrow here")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse)
    with pytest.raises(MissingDependency, match="pyarrow"):
        tdx._parquet_reader()
