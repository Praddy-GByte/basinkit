# Changelog

## 0.1.0 (unreleased)

First release.

### Delineation
- Three global backends: HydroBASINS graph traversal (default), D8 routing over
  Copernicus DEM via pyflwdir, and the Global Watersheds API.
- `backend="auto"` falls back to DEM routing when a basin sits at the
  HydroBASINS level-12 resolution floor.
- Outlet snapping to the local maximum of upstream area, with a minimum
  drainage threshold so a hillslope point fails loudly instead of returning a
  few hectares.
- Adaptive window growth when a DEM-routed basin reaches the window edge.
- Off-channel advisory: when a unit at least `river_snap_ratio` times larger
  sits within 20 km but outside the snap radius, basinkit warns and records
  `off_channel_candidate` in the provenance *without* moving the point. Found
  by running the README's own example: `from_point(26.5, 85.2)`, advertised as
  "14,384 km2", is 16 km off the Bagmati channel and returns 434 km2. The
  delineation was correct; the coordinate and the documented figure were not,
  and nothing warned. Every user-facing example now uses the Chatara outlet,
  which the network suite checks against the published 54,100 km2, and an
  offline test pins the documented coordinate to that one.

### Testing and CI
- The live-source suite moved out of `CI` into its own weekly `Data sources`
  workflow. Some hosts refuse GitHub's datacenter addresses -- HydroSHEDS
  answers 403 to Actions runners while serving the identical request to a
  laptop -- so gating every push on it painted the badge red for a reason that
  had nothing to do with this repository. `CI` is now purely offline across
  three operating systems and Python 3.10 to 3.13, and red there always means a
  defect here.
- `tests/conftest.py` reports an upstream refusal (403, 404, 429, 5xx, timeout)
  as a *skip* with the reason attached, and leaves a wrong number a failure. A
  monitor you stop reading is not a monitor.

### Data
- Anonymous access to 20 datasets: Copernicus DEM GLO-30/90, NASADEM, SRTM,
  HydroBASINS/RIVERS/LAKES/ATLAS, ESA WorldCover, ESRI annual LULC, SoilGrids,
  CHIRPS v3.0, PERSIANN-CDR, TerraClimate, JRC Global Surface Water,
  Sentinel-2, Sentinel-1 RTC, Landsat C2 L2, HLS.
- Everything is clipped and masked to the basin polygon, not its bounding box.
- Cosine-latitude weighting in zonal means; equal-area projection for areas.
- Memory-budgeted mosaicking with automatic coarsening above 100 Mpx.
- CHIRPS read through HTTP range requests, so only the basin window transfers.

### Fixed during multi-continent verification
- **Outlet snapping for HydroBASINS.** A coordinate on a big river's bank falls
  in a small lateral unit: Rhine at Lobith returned 271 km2 instead of 160,800,
  Godavari at Polavaram 353 instead of 307,800. Now snaps when a unit within
  1 km drains at least 10x more, warns, and records the jump in provenance.
- **Sentinel-2 offset applied twice.** Earth Search pre-applies the baseline
  04.00 BOA offset and flags it while still publishing the nominal -0.1;
  applying both gave negative surface reflectance.
- **Nodata averaged into composites.** Optical nodata is 0, so an unmasked
  median over a basin spanning several MGRS tiles came back 87% zero. Now
  loaded as float32 with NaN, and grouped by solar day.
- **Clip failed on every Dataset.** `Dataset` has no `.values` array, so every
  multi-band STAC result raised. The check is now Dataset-aware and never
  forces a lazy cube.
- **Exported rasters carried no nodata**, so the clip stopped existing outside
  Python. Now declared in the file header.
- **255 averaged into JRC surface water**, producing occurrence above 100%.
- **`outlets="min"` in DEM routing** pulled flow networks toward the window's
  lowest cell.

### Performance
- CHIRPS via HTTP range reads rather than whole-globe downloads: a three-year
  basin series went from 116 s to 24 s.
- TerraClimate fetches its per-variable, per-year files concurrently.
- Pixel budgets on the STAC path, with a lower one for Sentinel-1 RTC, whose
  float32 10 m frames cost far more per pixel than optical COGs.

### Corrections after external review
- **The same basin was quoted with two different reference areas.** The Roadmap
  compared the Koshi against `reported_up_area_km2` (54,581 km2 -- HydroBASINS'
  own bookkeeping) and headlined the resulting 0.15%; Verification correctly
  used the published 54,100 km2 and 0.73%. The first comparison is close to
  circular, since both numbers come from the same polygons. Every document now
  uses the published reference, and `docs/delineation.md` says plainly that the
  internal check is not an accuracy figure. Two regression tests guard it.
- **Accuracy is now reported as a distribution.** n = 12, median 0.74%, eight
  within 1%, nine within 3% -- instead of the single most flattering basin. The
  sample size and its bias (large, well-mapped rivers with published areas) are
  stated.
- **"Not one of these raised an exception" was false.** Two of the ten defects
  did; both were found by auditing untested methods rather than by the suite.
- **Every delineation figure now traces to one run** of
  `verify/run_delineation.py`, not to a mixture of runs. The Rhine row had been
  carried over from before the distance fix.
- **The base grid of each backend is stated**, in the module docstring, the
  README and both reports. HydroBASINS is extracted from HydroSHEDS at 15
  arc-seconds, so the default routes on a ~460 m grid built from February 2000
  SRTM. It was the most load-bearing undisclosed fact about the package.
- **MERIT-Hydro is reframed from cross-check to migration path.** At 3
  arc-seconds it is five times finer than the default and hydrologically
  conditioned; the `api` backend already implements that path. What blocks it
  as a default is its non-commercial licence and unautomatable acquisition, not
  the routing.
- Both reports carry a byline and an anchor date.

### Logo
- An animated multicolour mark in `assets/`: four coloured tributaries joining
  one river inside a basin divide. The colour carries the idea -- many open
  data sources, one basin -- rather than decorating it.
- Respects `prefers-reduced-motion`, follows the viewer's colour scheme, and
  ships pinned light and dark wordmarks because GitHub's theme and the
  browser's `prefers-color-scheme` can disagree.
- Lettering is Archivo glyph outlines, not live text: an SVG shown through
  `<img>` cannot load a web font.
- Geometry is generated rather than hand-drawn -- a wobbling polar radius for
  the divide, endpoints clamped against it so nothing pokes through, and plain
  downstream-sagging arcs for the tributaries.

### QGIS plugin
- A Processing provider in `qgis_plugin/`: delineate a basin from a canvas
  click, fetch layers clipped to it, and basin statistics with an HTML report.
- Registration happens in `initProcessing()` with `initGui()` forwarding to it,
  so the algorithms are visible to `qgis_process` and headless runs, not only
  to the desktop GUI.
- `compat.py` covers two silent breakages across supported QGIS versions:
  `QgsField` took a `QMetaType` argument from 3.38 (and Qt6, which QGIS 4 uses,
  removed `QVariant.Type` outright), and `Qgis.WkbType` replaced
  `QgsWkbTypes.Type` in 3.30.
- Checked against stubbed bindings at four QGIS versions, plus an end-to-end
  run of the real `processAlgorithm` bodies. 22 further tests validate the
  metadata against what plugins.qgis.org actually enforces -- which is not what
  its documentation table says.

### Honesty pass on the catalogue
- Every entry now carries an explicit `implemented` flag. Seven datasets were
  listed as if they were fetchable when no fetcher existed; asking for one now
  raises `NotImplementedSource` carrying the access route, the licence and what
  to do with the data once you have it. `basinkit catalog` marks them `DOC`.
- `grace` was listed as needing no account. The reliable route is JPL via
  Earthdata Login; the CSR anonymous mirror was unreachable when checked.
  Corrected rather than left optimistic.
- A test asserts every key in `DEFAULT_STACK` is anonymous, commercially safe,
  redistributable **and** implemented.

### Added
- **BasinATLAS** (`Basin.attributes()`): 281 pre-computed environmental
  variables per sub-basin. The `_u` columns are already aggregated upstream, so
  one lookup characterises a whole catchment without touching a raster. Its
  mean elevation for the Koshi agrees with basinkit's own COP-DEM computation
  to 0.1%.
- Scaled integers are decoded: read raw, the Koshi appears to average 50 degrees
  Celsius and a 204 degree slope.
- `Basin.plot()` crashed on NumPy 2.x (`ndarray.ptp()` was removed in 2.0) and
  had never been executed by any test. Fixed, with a test that scans the
  package for every NumPy-2-removed API.

### Verified
- Test suite run on Python 3.10, 3.11 and 3.12 — the CI matrix previously
  claimed three versions and only one had ever run.
- Paths an audit found untested and now covered: `explore()` with leafmap,
  `plot()`, `from_file()` including reprojection, the DEM backend's window-edge
  exclusion and its refusal to return a truncated basin.

### Licensing
- Machine-readable catalogue driving the fetchers, the CLI and
  `Basin.license_report()`.
- `Basin.check_license()` raises on restricted use.
- MERIT Hydro, FABDEM, MSWEP and GRDC are catalogued but opt-in and flagged.
