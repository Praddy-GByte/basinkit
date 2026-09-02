# Changelog

## 0.3.3 — 2026-09-02

Versions 0.3.1 and 0.3.2 were QGIS-plugin releases; the Python package was
still at 0.3.0. This is the first package release since then, and it corrects
a number that 0.3.0 got wrong.

### Fixed — `channel_gradient_m_per_km` was not a channel gradient

0.3.0 computed it as total basin relief divided by main channel length. Those
are two different things. The highest point in a basin is a ridge top, usually
far from the head of the main stem, so the old figure reported a fall the
river never makes. On the Koshi it gave 15.1 m/km; the bed actually falls
5,507 m over 572.7 km, which is **9.6 m/km**. On a low-relief basin the error
is larger in proportion, because the ridges dominate the relief while the
channel barely falls.

The gradient is now read from the bed: the DEM is sampled at 400 points along
the main channel from head to mouth, the profile is made monotonic downstream
so that a centreline crossing a bank or a bridge deck cannot invent a fall,
and the gradient is the drop between its two ends over the channel length.
`main_channel_relief_m` reports that drop, so the two inputs are visible.

**If you published a `channel_gradient_m_per_km` from 0.2.0–0.3.0, recompute
it.** `relief_ratio` (H/Lb) is unchanged and was always correct; if the old
number was what you wanted, that is the parameter you wanted.

### Added — `morphometry()` checks its own stream counts

Strahler ordering constrains the counts it produces. An order-*u+1* stream
exists only where two order-*u* streams meet, so N(u) ≥ 2·N(u+1), and the
bifurcation ratio can therefore never be below 2. A basin with one outlet has
exactly one stream of its highest order, because two would join and make a
higher one. Both are constraints, not tendencies.

`morphometry()` now returns a `warnings` list. It is empty when the counts are
consistent. Entries marked `severity="impossible"` mean a constraint is broken
and the table should not be interpreted until that is resolved — in practice
this almost always means dataset reaches were counted instead of Strahler
streams. A third check flags a mean bifurcation ratio outside Strahler's usual
3–5 as `severity="unusual"`, which is a flag and not an error: elongated
basins and clipped networks do this legitimately.

The Koshi and the Shipra both return no warnings.

### Documentation

- `docs/related-work.md` gains a morphometry section. Morphometry is not
  unpackaged: GRASS `r.stream.stats` (Jasiewicz & Metz 2011) has computed the
  full Horton set, with correct stream counting, since 2011, and the QGIS
  repository carries ArcGeek Calculator, Drainage Basin Geomorphology and a
  Hypsometric Curve plugin. The defensible claim is narrower — no *Python*
  library returns these parameters from a coordinate — and it is a packaging
  contribution, not a scientific one. The consistency checks above are the
  part that is not packaging.
- Named as neighbours: AquaFetch (JOSS 2025) and the HARBOR preprint, which
  publish the unified-basin-data idea under other names, and the Sen Hydro
  QGIS plugin, which delineates from a click using the same mghydro backend as
  basinkit's `api` path.
- Kirchner (1993) is cited as a caution against reading geomorphic meaning
  into bifurcation ratios at all.


## 0.3.1 — 2026-09-01

### QGIS plugin
- The plugin repository's automated checker reported 16 Qt6 compatibility
  issues on upload. QGIS 4 runs on Qt6, where the short enum aliases were
  removed, so `QgsWkbTypes.Polygon`, `QgsProcessingParameterNumber.Integer`,
  `QgsFeatureSink.FastInsert` and the rest would have raised at run time on
  QGIS 4. All 16 are now written with their full scope. The scoped spelling
  works on PyQt5 as well, so one code path covers QGIS 3.28 through 4.x and no
  version guard was needed.
- This is the reason `qgisMaximumVersion=4.99` had been an untested claim: the
  plugin declared support for QGIS 4 without ever having been checked against
  it. The checker did the checking.
- A test scans the plugin source for unscoped enums so this class of defect
  cannot return.

## 0.3.0 — 2026-08-31

### Morphometry
- `Basin.morphometry()` computes the classical Horton-Strahler-Schumm
  parameters -- linear, areal and relief -- from the basin polygon, the river
  network and the DEM, with a per-order table of streams, lengths and
  bifurcation ratios.
- Streams are counted as Strahler **streams**, not as the reaches a river
  dataset splits them into. Counting reaches on the Koshi gives bifurcation
  ratios of 2.3, 1.8, 2.0, 1.1, 1.9 and 17.1 -- a ratio of 1.09 is not
  physically possible -- against 4.7, 4.6, 4.3, 5.3, 3.0, 2.0, mean 3.98, which
  is inside Strahler's usual 3-5. This is the difference between a publishable
  table and a wrong one, and it is the reason this is a function rather than a
  worked example.
- Area, perimeter, basin length and every stream length are measured in one
  local equal-area projection. Mixing a perimeter from one projection with a
  dataset's own stored lengths corrupts every ratio built from them, and the
  circularity ratio is especially unforgiving.
- The hypsometric integral is computed from the curve and reported beside the
  elevation-relief ratio, which is derived differently; on the Koshi they agree
  to four decimal places.
- The output carries its own caveats: drainage density, stream frequency and
  bifurcation ratio describe the network measured, not the basin, and are not
  comparable across networks.

### Visualisation
- Two defects found by exporting real basins rather than test ones:
  `texture=None` opened on the satellite material with no texture to draw, so
  the page rendered a black mesh and read as broken; and the depth fog used
  fixed distances, which looked right on a 70 km catchment and swallowed a
  350 km one entirely. Fog now scales with the basin, and a page exported
  without imagery opens in the elevation view with the satellite button
  disabled. On a mountain basin a linear ramp collapses to one flat tone, because
  most of the terrain sits in the upper part of its own range.

### QGIS plugin
- The plugin version now tracks the package version.
- Fixed a defect found by installing the plugin on macOS rather than by reading
  the code: the "package missing" notice built its pip command from
  `sys.executable`, which on macOS is `QGIS.app/Contents/MacOS/QGIS` -- the
  application binary. Following the instruction opened a second QGIS window and
  installed nothing. The plugin now offers a path only after verifying it is a
  python executable, and always offers a Python Console snippet that runs pip
  through `runpy` inside the interpreter already running, so it cannot target
  the wrong site-packages. The docstring had warned about exactly this on
  Windows; macOS had the same hole.

### Logo
- The drainage inside the bowl of the `b` was four near-horizontal strokes
  meeting the stem at right angles, which read as a comb, or as an `E`, rather
  than as a river network. It is now a generated dendritic network: one trunk
  descending to a single outlet, junctions that open downstream at acute angles,
  tributaries aimed at whichever bank has open catchment in front of it, and
  stroke widths that taper from trunk to headwater.
- `logo-small.svg` is a reduced version of the same network, used for the 64 px
  and 32 px rasters and the QGIS plugin icon; the full mark carries more detail
  than those sizes can hold.
- The generator lives in `assets/build/build_network.py`, so the mark is
  reproducible rather than hand-drawn.
- Fixed: the wordmark's `prefers-reduced-motion` rule was overridden by the
  general `.tittle` rule that follows it, so both `i` dots stayed invisible for
  anyone who had asked for less motion.

## 0.2.0 — 2026-08-31

### Fixed
Four defects in the ESRI annual land-cover path, found by trying to build a
year-by-year change animation. All four are now regression tests.

- **The wrong year, silently.** Every annual item ends at 00:00 on 1 January,
  so a naive year window matches the *previous* year's map at the boundary
  instant. `landcover(source="esri", year=2024)` returned the 2023 map, and the
  array looked entirely correct. 2024 was also the package default. A year with
  no data now raises and lists the years that exist; `year=None` takes the
  latest published for that location, rather than a constant that rots.
- **The wrong legend.** `class_fractions()` always used the WorldCover class
  numbers. ESRI numbers its classes differently, and code 10 is tree cover in
  one scheme and cloud in the other -- so ESRI cloud was reported as forest.
  The legend now travels with the array in `.attrs` and is read from there.
- **The wrong type.** `esri_lulc()` returned a Dataset while `worldcover()`
  returned a DataArray, and a Dataset has no `.values` array -- reaching for one
  picks up the method. This is the same defect that once broke clipping on every
  multi-band STAC result; it was fixed there and left standing here. Both
  sources now return a 2-D `uint8` DataArray.
- **The wrong mosaic.** A basin spanning two ESRI tiles got them stacked along a
  time axis rather than mosaicked. They are complementary in space, not repeat
  looks, so they are now combined first-valid: averaging class codes would
  invent classes that do not exist.

### Visualisation
- `Basin.export_3d()` writes the basin as one self-contained interactive page:
  a terrain mesh from the DEM, a Sentinel-2 median composite draped over it,
  and the river network animated downhill. Imagery, geometry and the renderer
  are all embedded, so the file opens on a laptop with no network -- which is
  the situation many of the people this package is for actually work in.
  `texture=None` skips the imagery for a much smaller, DEM-only page.
- The elevation tint maps colour to the *rank* of an elevation rather than its
  value. On a mountain basin a linear ramp collapses to one flat tone, because
  most of the terrain sits in the upper part of its own range.

## 0.1.0 — 2026-08-30

First release. On PyPI as `basinkit`; archived at
[10.5281/zenodo.22181934](https://doi.org/10.5281/zenodo.22181934).

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
