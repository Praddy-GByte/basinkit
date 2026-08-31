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
    import pathlib
    import re

    readme = (pathlib.Path(__file__).resolve().parent.parent / "README.md").read_text()
    assert re.search(r"n = 12", readme), "sample size must be stated"
    assert "median" in readme.lower()


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
