# Changelog

## 0.6.0 -- 2026-09-18

### Two measurements widened enough to carry their claims

The twelve-metre backend was measured on 60 gauges in two regions. It is now
measured on 360 between 100 and 500 km2 across eight GEOGLOWS regions on four
continents, drawn by seed before any result was seen. The claim holds: median
area error 32.5% against 10.5%, within 20% of the published figure on 38%
against 58%, and the better answer on 66% of them. The gain is largest at
100-200 km2 and closes by 350-500 km2, which is the mechanism behaving as
claimed rather than a number that happened to come out well.

The suitability grade is now tested against something it was not fitted to.
Computing the grade from Copernicus GLO-30 and then asking NASADEM to describe
the same ground, the correlation between the two slope fields runs 0.935 at
HIGH and 0.756 at LIMITED across 133 gauges (Mann-Whitney z = -4.84,
p = 1.3e-06). The grade predicts whether two independently produced elevation
models agree about the terrain.

It also does not predict catchment area error, and the verification page now
says so with the numbers, because the two questions are separate and the grade
was only ever about the first.

Both samples and both scripts are in `verify/`, so the numbers on the
verification page can be recomputed rather than taken on trust.

### The reach index is decoded once, not once per call

`backend="tdx"` re-read and re-decoded the 6.8 million row reach index on every
delineation. One delineation never noticed; a hundred spent most of their wall
clock on it. The decoded arrays are now held for the life of the process.

### An eight-page report, ready for a thesis

`Basin.report("basin.pdf")` writes everything basinkit computes about a basin
onto A4, with the suitability grade on the cover rather than in a footnote and
every parameter carrying its symbol, unit and original reference. Eight pages:
elevation and hypsometry, slope and aspect with their distributions and an
aspect rose, curvature and slope position and ruggedness and the landform
classes, the channel network with Horton's laws, the full morphometric table,
what the answer rests on, and a methods page with the software versions,
licences and citations.

Two pages depend on the river network. Without it they are replaced by a page
that says which parameters are missing and why, rather than by a partial table
that reads like a complete one.

The report states outright that its two drainage densities are different
measurements: one from the mapped river network, one from the channels routed
off this elevation raster. On the Koyna they are 0.37 and 1.38 km/km2. Neither
is wrong; quoting one as the other is.

### Drainage density as a curve, not a number

`Basin.drainage_density()` reports drainage density across an order of
magnitude either side of a slope-scaled channel-initiation threshold, after
Montgomery and Dietrich (1988), and says which threshold was chosen and why.

Drainage density is the most quoted parameter in basin morphometry and the
least comparable, because it is not a property of a basin: it is a function of
where you decide a channel begins. On the Koyna it moves by a factor of eleven
across that span. A single figure without its threshold cannot be compared
with anyone else's, and now the threshold comes with it.

### The shape of the ground

`Basin.tpi()`, `Basin.tri()`, `Basin.roughness()` and `Basin.landform()`:
topographic position index (Weiss 2001), terrain ruggedness index (Riley et
al. 1999), local relief (Wilson et al. 2007), and the six slope-position
classes the first two imply. The position index uses a summed-area table, so
an eleven-cell window costs the same as a three-cell one.

The ruggedness index carries a caveat in its own docstring, and a test that
holds the caveat true: on a smooth uniform slope it largely restates the
gradient, because it is not a residual after removing the local trend. A
perfectly smooth thirty percent plane scores about 82 m on a 110 m grid. It
separates rough ground from smooth ground at a given gradient, not rough
ground from steep ground.

### The elevation model has to earn the terrain analysis

`Basin.dem_suitability()` grades whether this basin's elevation raster can
carry the terrain products computed from it. Five measurements, each against a
stated threshold: how much of the surface depression filling had to invent;
how many slopes fall below `arctan(vertical error / cell size)`, the angle at
which a gradient is the model's own error; relief against that vertical error;
the largest level surface, as a share of the basin; and cells inside the basin
with no elevation at all. The result is HIGH, MODERATE or LIMITED with the
numbers that produced it, a plain-language statement, and `support_map=True`
for a per-cell raster of which ground the answer actually rests on.

This is the per-basin half of an accuracy claim. The published tables say what
error to expect across thousands of gauges at a given catchment size, which is
a statement about the population. It cannot say whether the basin in front of
you is one of the good cases. Three worked examples, each on Copernicus
GLO-30:

| basin | grade | what decided it |
|---|---|---|
| Koshi at Chatara, 54,497 km2 | HIGH | every test passed; 90% of cells supported |
| Koyna Dam, 903 km2 | LIMITED | the Shivsagar reservoir is 8.6% of the basin |
| Hillsborough, Florida, 436 km2 | LIMITED | filling raised 53% of cells, 94% of slopes sit below the noise floor, 4% of cells supported |

The Florida basin is the one to read twice. It is also the station where the
DEM backend's own area error is +99%, so the grade names the case before the
number misleads anyone.

It grades the terrain products, not the basin boundary. Delineation accuracy
is a separate question, measured separately in the verification page. An
unknown product is assumed to be the least accurate of the four, because
assuming better than is known would turn an unsupported answer into a passing
grade.

### A twelve-metre backend for small catchments

`backend="tdx"` delineates over TDX-Hydro, the reach-level hydrography NGA
derived from TanDEM-X at 12 m. One catchment polygon per stream reach replaces
the ~130 km2 HydroBASINS unit, which is the whole of the default backend's
weakness below 500 km2. On 360 gauges between 100 and 500 km2, across eight
GEOGLOWS regions on four continents, drawn by seed before any result was seen,
median area error fell from 32.5% to 10.5% and the share within 20% of the
published area rose from 38% to 58%. It is the better answer on 66% of them.

It is opt-in and `auto` will not reach for it. TDX-Hydro is CC BY-SA 4.0, and
ShareAlike travels into anything derived from it and redistributed; every other
default in the catalogue is CC BY 4.0 or more permissive. The catalogue entry
says so, and the backend is reachable only by naming it.

Reads the GEOGLOWS v2 republication on AWS Open Data, which serves byte ranges
where NGA's own download does not. That republication omits twelve of NGA's
sixty-two regions, Greenland and much of Arctic North America among them.
Needs `pip install "basinkit[tdx]"` for the Parquet reader; the catchment file
for a region is read in batches, so peak memory stays near 2 GB rather than
loading a half-gigabyte table whole.

### Terrain surfaces from the elevation already fetched

`basinkit.terrain` adds slope, aspect, hillshade, curvature, flow accumulation,
the channel network, the topographic wetness index and height above nearest
drainage, all reachable as `Basin` methods. Every one is computed from the
array `dem()` already returns, so passing `dem=` lets a single download serve
all of them.

Cell spacing is taken per row from that row's latitude. A cell 0.001 degrees
wide spans 111 m at the equator and 56 m at 60 degrees north, and dividing by
one assumed width reported a high-latitude basin as twice as steep as it is.

Flow accumulation treats ground outside the polygon as nodata rather than
filling it with elevation. Filled, every neighbouring catchment became a ridge
draining inwards: on the Koshi the outlet accumulated 1.85 million cells from
a basin of 1.01 million. It now accumulates exactly the basin.

Height above nearest drainage is measured on the same depression-filled
surface the routing used. Measured against raw elevation instead, every filled
pit came back below its own outlet, and the most flood-prone ground in the
basin read as negative.

### Sub-catchments, with their routing

`Basin.subbasins()` returns the HydroBASINS units the traversal walked rather
than only their union, each carrying `NEXT_DOWN`. That is the routing graph
itself, so a distributed model gets its sub-catchments and their links without
inferring anything from geometry. On the Koshi: 423 units summing to 54,580
km2 against a measured 54,497, with exactly one draining out of the set.

### Summaries inside classes

`Basin.zonal()` summarises any layer inside the classes of another, or inside
bands cut from a continuous one. Area is summed from the true size of every
cell, so a basin spanning several degrees of latitude is not weighted towards
its southern edge.

`Basin.landcover_change()` returns what became what between two years of the
ESRI annual series, in square kilometres, with the diagonal left in so that a
deforestation figure shows what the loss became.

### Trends and drought

`Basin.precipitation_trend()` runs Mann-Kendall with tie correction and Sen's
slope; `Basin.spi()` returns the Standardized Precipitation Index by ranking
each calendar month against its own history. Neither imports scipy, which this
package does not declare.

### More than one basin

`basinkit.compare()` delineates a list of coordinates into one table, one row
per point. A coordinate that fails gets a row with the reason in it rather
than ending the run, so an afternoon of downloads is not lost to a single bad
point.

## 0.5.0 (2026-09-09)

### Compatibility across the whole supported QGIS range

`Qgis.ProcessingSourceType` arrived in QGIS 3.36; before that the same enum
lives on `QgsProcessing`. The plugin now resolves it by asking the API, so it
loads identically on 3.28 through 4.x, including the 3.34 long-term release.
`tests/test_qgis_api.py` loads every algorithm against a real QGIS, and a CI job
runs it on Ubuntu's QGIS 3.34.

### Accuracy reported by catchment size

Blind validation against agency-published catchment areas at 2,550 gauges in
99 countries on six continents, 2,740 delineations in all:

| catchment area | median error | within 20% |
|---|---:|---:|
| above 100,000 km2 | 0.3% | 92% |
| 10,000 to 100,000 | 1.3% | 92% |
| 2,000 to 10,000 | 1.7% | 96% |
| 500 to 2,000 | 8.9% | 78% |
| 100 to 500 | 30% | 40% |
| below 100 | 181% | 22% |

HydroBASINS level-12 units average about 130 km2, which sets the scale the
default backend resolves. Below roughly 2,000 km2 the DEM backend is the right
instrument, and the package now says so at the point where it matters.

### Added: `basinkit.verify`

`check_outlet` confirms a delineated basin against HydroRIVERS. When the basin
exceeds twice the area draining to the largest river within 2 km of the outlet,
it reports it: 85% of the outlets it flags need attention, and it stays quiet on
97% of the ones that do not, with precision from 75% in Europe to 93% in Africa.
A second condition covers an outlet with no mapped river within 2 km and a basin
between 100 and 1,000 km2, at 87% precision and 1.2% false alarms, measured
separately on two samples.

The radius is 2 km for a measured reason: at 1 km the refinement step acted on a
Mekong gauge whose only nearby reach drained 5.9 km2. Two kilometres finds the
river a gauge is actually on.

### Changed: `auto` covers both ends of the resolution range

The existing route re-ran on the DEM when the sub-basin result came back at the
grid's floor. The complementary case is an outlet on a small stream inside a
unit belonging to the trunk river.

`auto` now refines on the DEM when two independent sources agree on a smaller
catchment: the river network shows the point draining far less than the polygon
covers, **and** a DEM delineation lands within a factor of two of that river's
upstream area. Across 300 gauges drawn after this was designed and used nowhere
else in it: **19 improved, 279 unchanged, 0 reduced**, with the median error
where it acted falling from 1,731% to 4.3%. Where the DEM does not corroborate,
the sub-basin polygon stands and the question is reported.

Refinement acts only when the river it judges by lies within 1 km of the outlet.
Beyond that the point is not on that river, and a DEM delineation of the same
point describes the same local drain, so the two sources stop being independent.
Every refinement that improved a result had its river within 0.91 km.

Median cost is +1.6 s. The check runs when the river network is already cached;
pass `verify="download"` to fetch it, or `verify=False` to skip it.

### Added: the package names what kind of place the outlet is in

An endorheic system, a coastal strip draining straight to the ocean, and an
outlet with nothing draining into it are each reported in provenance and in the
plugin. The last is what a lake surface and a sub-grid headwater have in common,
and naming it turns a surprising number into a described situation.

### Changed: the consistency line compares against an independent source

The plugin's consistency line now reports the result against the river network.
The outlet unit's own upstream-area field agrees with the assembled area to
within 1% almost everywhere, so it confirms the traversal rather than the choice
of outlet.

### Changed: messages are matched to their cause

A coordinate outside the network's coverage, one beyond the snap distance, and
one on a hillslope rather than in a channel each get their own guidance and
their own remedy.

### Fixed: `progress` is accepted by every source

`soilgrids`, `available_water_capacity`, `persiann`, `terraclimate`,
`water_balance` and `describe` now take the argument that `dem` and `landcover`
already did, so a script can pass it uniformly. A test asserts every source
accepts it.

### Added: `verify/run_outputs.py` and `verify/run_bad_clicks.py`

The first checks the layers rather than the polygon: that the raster is masked
to the divide, by rasterising the polygon independently and comparing; that the
area agrees with a geodesic area from pyproj; that the morphometric identities
hold; and that rainfall and elevation land inside published figures. On the
Sapta Koshi and the Danube every check passes, `Rc x Cc^2` comes to 1.0000, and
basin rainfall lands at 1,333 and 1,044 mm/yr against published ranges of
1,200-1,900 and 600-1,200.

The second covers outlets that are not on rivers: oceans, cities, lake surfaces,
deserts, the poles, and swapped coordinates.

A complete package for a 54,497 km2 basin takes 26 seconds once cached.

### Also

- The twelve named rivers are a demonstration rather than the headline
  validation, and are labelled as such in all eight places they appeared.
- Against pysheds and WhiteboxTools on identical 30 m rasters across 59
  catchments under 2,000 km2, the DEM backend returned a basin for every
  station, matched the agency figure within 20% on 68% of them against 56% and
  51%, and had the lowest median error.

## 0.4.0 (2026-09-04)

### Added: `River`, the river above a point

`Basin` answers "what drains into here". `River` answers "what is the river
that arrives here", which is the question people ask first.

```python
river = bk.River.from_point(23.1793, 75.7849)
river.report("shipra.html")
```

The main stem is traced from the outlet upstream, taking the larger
contributing area at every junction. What comes back: course length, sinuosity,
Strahler order, modelled mean discharge, source and mouth with their
elevations, the fall of the bed and its gradient, the distance still to run to
the sea, every tributary joining the main stem with the share of the flow it
carries, and the longitudinal profile sampled from the DEM. `report()` writes
all of it as one self-contained HTML page with the long profile drawn and the
confluences that matter marked on it.

Three limits are stated beside the numbers rather than in a footnote, because
the page gets screenshotted and the caveat has to travel with the figure. The
river ends where you clicked, so `distance_to_sea_km` records what is left
below it. Discharge is HydroRIVERS' modelled long-term natural average and does
not know about dams or abstraction. HydroRIVERS maps reaches down to about
10 square kilometres of catchment, so the source sits at the top of the mapped
network rather than at the spring.

No new dependency and no new data source: the same HydroRIVERS download that
serves `Basin` serves this.

### Changed: what the package says it is

The one-line description led with "delineate", which is the crowded word.
QGIS already has QCT Watershed, DDM HydroLogic, Sen Hydro and GRASS for
delineation, and a reader who sees that word first stops reading. Worse, the
description never mentioned morphometry at all, so an independent reviewer
assessing the plugin did not notice it exists.

The description now leads with the outcome and names morphometry, in
`pyproject.toml`, `qgis_plugin/metadata.txt`, the README and the docs home
page. Nothing about the software changed; what changed is that the software
now says what it does.


## 0.3.3 (2026-09-02)

Versions 0.3.1 and 0.3.2 were QGIS-plugin releases; the Python package was
still at 0.3.0. This is the first package release since then, and it corrects
a number that 0.3.0 got wrong.

### Fixed: `channel_gradient_m_per_km` was not a channel gradient

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

**If you published a `channel_gradient_m_per_km` from 0.2.0-0.3.0, recompute
it.** `relief_ratio` (H/Lb) is unchanged and was always correct; if the old
number was what you wanted, that is the parameter you wanted.

### Added: `morphometry()` checks its own stream counts

Strahler ordering constrains the counts it produces. An order-*u+1* stream
exists only where two order-*u* streams meet, so N(u) ≥ 2·N(u+1), and the
bifurcation ratio can therefore never be below 2. A basin with one outlet has
exactly one stream of its highest order, because two would join and make a
higher one. Both are constraints, not tendencies.

`morphometry()` now returns a `warnings` list. It is empty when the counts are
consistent. Entries marked `severity="impossible"` mean a constraint is broken
and the table should not be interpreted until that is resolved; in practice
this almost always means dataset reaches were counted instead of Strahler
streams. A third check flags a mean bifurcation ratio outside Strahler's usual
3-5 as `severity="unusual"`, which is a flag and not an error: elongated
basins and clipped networks do this legitimately.

The Koshi and the Shipra both return no warnings.

### Documentation

- `docs/related-work.md` gains a morphometry section. Morphometry is not
  unpackaged: GRASS `r.stream.stats` (Jasiewicz & Metz 2011) has computed the
  full Horton set, with correct stream counting, since 2011, and the QGIS
  repository carries ArcGeek Calculator, Drainage Basin Geomorphology and a
  Hypsometric Curve plugin. The defensible claim is narrower: no *Python*
  library returns these parameters from a coordinate, and it is a packaging
  contribution, not a scientific one. The consistency checks above are the
  part that is not packaging.
- Named as neighbours: AquaFetch (JOSS 2025) and the HARBOR preprint, which
  publish the unified-basin-data idea under other names, and the Sen Hydro
  QGIS plugin, which delineates from a click using the same mghydro backend as
  basinkit's `api` path.
- Kirchner (1993) is cited as a caution against reading geomorphic meaning
  into bifurcation ratios at all.


## 0.3.1 (2026-09-01)

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

## 0.3.0 (2026-08-31)

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

## 0.2.0 (2026-08-31)

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

## 0.1.0 (2026-08-30)

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
- Test suite run on Python 3.10, 3.11 and 3.12. The CI matrix previously
  claimed three versions and only one had ever run.
- Paths an audit found untested and now covered: `explore()` with leafmap,
  `plot()`, `from_file()` including reprojection, the DEM backend's window-edge
  exclusion and its refusal to return a truncated basin.

### Licensing
- Machine-readable catalogue driving the fetchers, the CLI and
  `Basin.license_report()`.
- `Basin.check_license()` raises on restricted use.
- MERIT Hydro, FABDEM, MSWEP and GRDC are catalogued but opt-in and flagged.
