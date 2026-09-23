# basinkit

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/logo-wordmark-dark.svg">
  <img src="assets/logo-wordmark-light.svg" alt="basinkit" width="440">
</picture>

[![PyPI](https://img.shields.io/pypi/v/basinkit?logo=pypi&logoColor=white)](https://pypi.org/project/basinkit/)
[![DOI](https://zenodo.org/badge/1351760570.svg)](https://doi.org/10.5281/zenodo.22181933)
[![Tests](https://github.com/Praddy-GByte/basinkit/actions/workflows/ci.yml/badge.svg)](https://github.com/Praddy-GByte/basinkit/actions)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**Click a river anywhere on Earth. Get an analysis-ready basin package: the
basin polygon, elevation, land cover, soil, rainfall, surface water and rivers
clipped to it, the river's own profile, and the full Horton-Strahler-Schumm
morphometry. No account, login or credential anywhere in the chain.**

Existing tools each stop somewhere. HyRiver and watershed-workflow are US-only.
rabpro is global but needs Google Earth Engine and MERIT-Hydro credentials.
hydromt's account-free catalogue covers a single Italian basin. mghydro is
global and account-free but is a web app returning zonal statistics, not
polygon-masked arrays. See [docs/related-work.md](docs/related-work.md) for the
clause-by-clause comparison.

```python
import basinkit as bk

basin = bk.Basin.from_point(26.87, 87.15)    # Sapta Koshi at Chatara
print(basin)
# <Basin area=54,497 km2 centroid=(27.974, 87.021) backend='hydrobasins'>
# published area at this gauge: ~54,100 km2

dem   = basin.dem()                          # clipped and masked to the polygon
land  = basin.landcover()
soil  = basin.available_water_capacity()
rain  = basin.precipitation(2000, 2024)      # basin-mean monthly series
water = basin.surface_water()                # 37 years of Landsat, pre-reduced

basin.download_all("koshi/")                 # the whole stack, one call
basin.export_3d("koshi.html")                # an interactive 3D page
morph = basin.morphometry()                  # Horton-Strahler-Schumm, in full

river = bk.River.from_point(26.87, 87.15)    # the river arriving at that point
river.report("koshi-river.html")             # one page: course, profile, tributaries
```

**New here?** The [tutorial](docs/tutorial.md) walks through the whole thing:
why each step exists, what every method returns and in what units, how to save
it, and what to do when a basin comes back the wrong size.

Or without writing any Python at all:

```bash
pip install basinkit
basinkit fetch --lat 26.87 --lon 87.15 --out koshi/
```

Or without a terminal either: there is a **QGIS plugin** in `qgis_plugin/`.
Click an outlet on the map canvas and the basin and its data land in your
project. See [its README](qgis_plugin/README.md).

> **Not affiliated with [EPA BASINS](https://www.epa.gov/hydrowq/better-assessment-science-integrating-point-and-non-point-sources-basins)
> or [BasinMaker](https://github.com/dustming/basinmaker).** BASINS is a US
> EPA desktop modelling system; BasinMaker builds lake-aware routing structures
> from data you supply. basinkit is a global data-acquisition package: a
> coordinate goes in, a delineated basin and its open Earth observation data
> come out.

---

## Why this exists

If you work on a river basin in the United States, this problem is solved:
[HyRiver](https://docs.hyriver.io) and
[watershed-workflow](https://github.com/environmental-modeling-workflows/watershed-workflow)
will hand you a delineated catchment and every layer that goes with it.

Everywhere else, you assemble it by hand. You clone a delineation script,
download tens of gigabytes of MERIT tiles, wait half an hour, and then start
again from scratch on the data side, because `eodag`, `earthaccess`,
`pystac-client` and every other downloader takes a **bounding box** and returns
**whole scenes**. Nothing joins the two halves, and nothing clips to the basin.

basinkit is that missing join, for the whole planet.

The precise claim, and the four packages that make it non-obvious, are in
[Related work](docs/related-work.md), including the two that do this better
than basinkit within their own scope.

### Three things it does that the alternatives do not

**It clips to the polygon, not the box.** Measured on sixteen major basins
spanning 54,000 km2 to the Amazon's 4.67 million, a catchment fills between
42% and 62% of its own bounding box, median 54%. Every `Basin` exposes
`bbox_efficiency`, so the figure for yours is one attribute away. Roughly half
of what a bounding-box download transfers is therefore somebody else's
catchment, and those pixels sit inside every "basin average" computed from it.

**It needs no account.** Not for the DEM, not for Sentinel-2, not for Landsat,
not for terrain-corrected radar. Nineteen of the twenty-seven catalogued datasets
are fetchable today, and every one of those is anonymous.
Compare: MERIT Hydro is behind a Google Form and an emailed Dropbox password;
the OpenTopography API allows fifty calls a day on a non-academic key; Earth
Engine requires a Google Cloud project and forbids commercial use on the free
tier. basinkit routes around all of it.

**It tells you what you are allowed to do with the result, and what it cannot
get you.** `basinkit catalog` and `Basin.license_report()` read from the same
machine-readable table the fetchers use, so the licence shown is the licence
that applied. The seven datasets basinkit documents but cannot download are
marked `DOC`, and asking for one raises an error carrying the access route and
the licence rather than quietly pretending to be a feature. Every default
layer is CC BY 4.0 or more permissive: redistributable, commercially usable,
attribution required. The restricted ones (MERIT Hydro, FABDEM, MSWEP, GRDC)
are opt-in and say so before the first byte moves.

---

## Does it work?

Blind validation against **2,740 delineations at 2,550 gauges in 99 countries**
on six continents, whose catchment areas are published by the national agencies
that operate them. The samples were drawn by seed before any result was seen and
nothing was dropped afterwards, failures included.

The answer depends almost entirely on catchment size, so it is reported that
way rather than as one number:

| catchment area | median error | within 20% | within 5% |
|---|---:|---:|---:|
| above 100,000 km2 | 0.3% | 92% | 78% |
| 10,000 to 100,000 | 1.3% | 92% | 86% |
| 2,000 to 10,000 | 1.7% | 96% | 58% |
| 500 to 2,000 | 8.9% | 78% | 35% |
| 100 to 500 | 30% | 40% | 15% |
| below 100 | 181% | 22% | 0% |

**And that table is about the population, not about your basin.** It says what
error to expect across thousands of gauges at a given catchment size. It cannot
say whether the one in front of you is a case it was kind to.
`Basin.dem_suitability()` answers the second half by measuring the basin
itself: how much of the surface depression filling had to invent, how many
slopes fall below the angle at which a gradient is only the model's vertical
error, relief against that error, the largest level surface as a share of the
basin, and cells with no elevation at all. Each against a stated threshold,
combined into HIGH, MODERATE or LIMITED, with a per-cell raster of which ground
the answer rests on.

| basin | grade | what decided it |
|---|---|---|
| Koshi at Chatara, 54,497 km2 | HIGH | every test passed; 90% of cells supported |
| Koyna Dam, 903 km2 | LIMITED | the Shivsagar reservoir is 8.6% of the basin |
| Hillsborough, Florida, 436 km2 | LIMITED | 53% of cells raised by filling, 94% of slopes below the noise floor, 4% supported |

Florida is the one to read twice: it is also the station where the DEM
backend's own area error is +99%, so the grade names the case before the
number misleads anyone.

And one command writes the lot to paper: `basin.report("basin.pdf")` produces
eight A4 pages with the suitability grade on the cover, every morphometric
parameter carrying its symbol and original reference, the channel network
against Horton's laws, the per-cell support map, and a methods page with the
software versions and licences. It is the thing a thesis chapter or a
manuscript appendix actually needs, and it takes about a minute.

The default backend walks HydroBASINS level-12 units, which average about
130 km2, so that is the scale it resolves. Below it, an outlet falls inside a
unit whose own outlet may be on the trunk river, and the polygon returned is
the trunk's catchment. The geometry gives no sign of this by itself, since the
traversal reproduces HydroBASINS' own upstream area on 95% of stations either
way.

So basinkit confirms every answer against the river network. Where that check
raises a question, **85% of those outlets need attention**, and it stays quiet
on 97% of the ones that do not. Where the network and a 30 m elevation model
agree on a smaller catchment, the answer is refined on the elevation model: on
300 gauges drawn after all of this was designed and used nowhere else, that
improved 19 results, left 279 unchanged, and **reduced none**.

On 59 catchments under 2,000 km2 the DEM backend was compared against pysheds
and WhiteboxTools on identical rasters. All three agree with each other to
within 5% on three quarters of stations, which locates the small-catchment
limit in the resolution of pre-computed sub-basins rather than in any one
implementation. basinkit returned a basin for every station and had the lowest
median error of the three.

A quarter of the gauges sit outside what any of the four methods reproduces, at
every snapping distance tried. Where four independent methods agree with each
other and differ from the reference, the reference is the variable: a
coordinate on a neighbouring tributary, or a published area measured at a
different structure. About 75% is the ceiling this catalogue supports for any
tool.

The Amazon (4.67 million km2, 35,625 sub-basins) takes 43 seconds. Rainfall,
reflectance and radar are checked separately: CHIRPS lands inside the published
Koshi climatology, a Sentinel-2 July composite gives an NDVI median of 0.82 over
temperate farmland, Sentinel-1 RTC gives -9.3 dB over vegetated land.

Full results, including the twelve named rivers this check replaced as the
headline, are in
[Verification](https://praddy-gbyte.github.io/basinkit/verification/).

### And a grade for every other layer too

Suggested by Prof. Dr. B. Mishra, who asked for quality indicators reported per
terrain type, basin size and data source rather than for the elevation model
alone. `Basin.data_quality()` measures each layer against something produced
independently of it: land cover as the agreement between ESA WorldCover and the
ESRI annual series, rainfall as CHIRPS against TerraClimate, soil as the width
of SoilGrids' own published 90% interval, surface water as the permanent-to-
seasonal split, delineation as the network check plus the accuracy regime for a
basin of this size -- and elevation as the suitability grade split by terrain
class, because a basin that is part plain and part mountain is not one number.

The Salzach at Salzburg, 4,510 km2, comes back LIMITED overall, and the reason
is the rainfall rather than the terrain: CHIRPS and TerraClimate track each
other at r = 0.60 there and differ by 17% in the mean. The elevation model is
HIGH -- but on the 11% of the basin that is flat valley floor, 63% of slopes
fall below the angle a 52 m cell can resolve, and only the per-terrain split
says so.

Two layers come back with no grade at all. Nobody publishes a threshold that
says a SoilGrids interval is too wide to use, or that a permanent-water share is
too low, so those report the measurement and say in `not_graded_because` why
they will not be graded, instead of inventing a cut-off and printing it as
though it were established. Every threshold that does exist is printed beside
the measurement it judged.

Details in
[Data quality](https://praddy-gbyte.github.io/basinkit/data-quality/).

---

## Install

**Needs Python 3.10 or newer** (geopandas 1.0 and rasterio do), and **QGIS 3.28
or newer** for the plugin. QGIS 3.28 and later ship a new enough Python;
anything older cannot install basinkit at all.

```bash
pip install basinkit              # core: delineation, DEM, land cover, soil, climate
pip install "basinkit[all]"       # + STAC imagery, DEM routing, interactive maps
```

Optional extras: `stac` (Sentinel/Landsat), `delineate` (D8 routing via
pyflwdir), `climate` (NetCDF), `viz` (leafmap, matplotlib).

---

## Delineation: four backends, because one is not enough

| backend | how it works | best for | resolution floor |
|---|---|---|---|
| `hydrobasins` *(default)* | walks the `NEXT_DOWN` graph over HydroBASINS level-12 units | any size, offline once cached, CC BY 4.0 | ~130 km² unit |
| `dem` | D8 routing with `pyflwdir` over a fresh Copernicus DEM window | small headwater catchments | one 30 m pixel |
| `api` | the public Global Watersheds service | a quick first look, zero download | ~90 m |
| `tdx` *(opt-in)* | walks the reach graph over TDX-Hydro unit catchments | small catchments, where it cuts the error by three quarters | one reach |

`backend="auto"` uses HydroBASINS, then falls back to DEM routing when the
result sits at the level-12 resolution floor and the true divide is invisible
to it.

**Say the base grid out loud**, because it is the most load-bearing fact about
any delineation tool and most of them bury it:

| backend | grid | source | conditioned |
|---|---|---|---|
| `hydrobasins` *(default)* | 15 arc-sec, ~460 m | SRTM, February 2000 | HydroSHEDS |
| `api` | 3 arc-sec, ~90 m | MERIT-Hydro | yes, error-removed |
| `dem` | 1 arc-sec, ~30 m | Copernicus, 2011-2015 | routed on the fly |
| `tdx` *(opt-in)* | 12 m | TanDEM-X, via GEOGLOWS v2 | yes, TauDEM |

The default routes on a quarter-century-old 460 m grid. That is fine for a
large basin and wrong for a small or heavily modified one, which is what the
other backends are for.

`backend="tdx"` is the answer to the small-catchment band. TDX-Hydro is derived
from TanDEM-X at 12 m and carries one catchment polygon per stream reach, so a
basin of a few hundred square kilometres is described by its own ground rather
than by the 130 km² cell that happens to contain its outlet. Measured against
published gauge areas on 360 catchments between 100 and 500 km², across eight
GEOGLOWS regions on four continents, drawn by seed before any result was seen:

| backend | median error | within 20% |
|---|---:|---:|
| `hydrobasins` | 32.5% | 38% |
| `tdx` | 10.5% | 58% |

It is better on 66% of them, and the gain is where it should be: on catchments
of 100-200 km² the median error falls from 61% to 11%, and by 350-500 km², as
the basin grows past a level-12 unit, the two converge.

It is opt-in and `auto` never reaches for it, for one reason: TDX-Hydro is
CC BY-SA 4.0. Every other default here is CC BY 4.0 or more permissive, and
ShareAlike travels into anything derived from it and redistributed. That is a
term to accept deliberately. It also needs `pip install "basinkit[tdx]"` for
the Parquet reader, and GEOGLOWS omits twelve of NGA's sixty-two regions,
Greenland and much of Arctic North America among them.

Two failure modes are handled explicitly rather than silently:

- **Outlet not on the channel.** A coordinate off the modelled stream by one
  pixel routes a few hectares instead of a few hundred km². The DEM backend
  snaps to the local maximum of upstream area and reports how far it moved.
- **Basin larger than the DEM window.** If the delineated basin touches the
  window edge the answer is wrong, so the window doubles and routing re-runs,
  up to a bound.

Whichever backend ran is recorded in `basin.provenance` and written into every
export. A polygon always says where it came from.

---

## What you can fetch

| layer | dataset | resolution | account |
|---|---|---|---|
| `dem()` | Copernicus GLO-30 / GLO-90 / NASADEM / SRTM | 30-90 m | no |
| `landcover()` | ESA WorldCover / ESRI annual LULC | 10 m | no |
| `soil()` | SoilGrids 250 m, 13 properties, 6 depths | 250 m | no |
| `available_water_capacity()` | derived: field capacity − wilting point | 250 m | no |
| `precipitation()` | CHIRPS v3.0 / TerraClimate | 0.05° / ~4 km | no |
| `water_balance()` | TerraClimate P/AET/PET/Q/soil + closure residual | 4 km | no |
| `surface_water()` | JRC Global Surface Water (37 years of Landsat) | 30 m | no |
| `sentinel2()` | Sentinel-2 L2A via Earth Search | 10 m | no |
| `landsat()` | Landsat C2 L2, 1982→ via Planetary Computer | 30 m | no |
| `sentinel1()` | Sentinel-1 RTC, terrain-corrected, global | 10 m | no |
| `rivers()` / `lakes()` | HydroRIVERS / HydroLAKES | vector | no |
| `attributes()` | BasinATLAS: 281 pre-computed basin attributes | vector | no |

**Documented but not fetchable** (`basinkit catalog` marks these `DOC`):
ERA5-Land, GPM IMERG, GloFAS and GRACE need an account and a client basinkit
does not ship; PERSIANN-CDR lost the NOAA endpoint basinkit read it from; MERIT Hydro, FABDEM and GRDC are licence-gated or have no API at
all. Asking for one returns instructions, not a stack trace.

### The fast way to characterise a basin

`attributes()` returns BasinATLAS's 281 pre-computed variables: climate,
physiography, land cover, soil, geology, human footprint. Its `_u` columns are
already aggregated over everything upstream, so one lookup describes the whole
catchment without touching a raster:

```python
basin.attributes(prefixes=("pre", "tmp", "ele", "slp"))
# {'precipitation [pre_mm_uyr]': 851,
#  'air temperature (degC) [tmp_dc_uyr]': 5.0,
#  'elevation [ele_mt_uav]': 3782,
#  'slope (degrees) [slp_dg_uav]': 20.4}
```

Costs one 2.7 GB download, once. Note the decoded units: BasinATLAS stores
several variables as scaled integers, and read raw the Koshi appears to average
50 °C and a 204° slope.

---

## Notes worth knowing

A few things basinkit handles that trip up hand-rolled pipelines:

- **Copernicus GLO-30 is not literally global.** Some national tiles are absent
  from the public bucket. basinkit falls back per tile to GLO-90 and then the
  OpenTopography mirror, and records which source filled each one.
- **SoilGrids is in Interrupted Goode Homolosine.** A WCS request built from a
  raw lon/lat bbox silently returns a coverage from the wrong place. basinkit
  reprojects the request and the result.
- **Basin means need cosine weighting.** On a geographic grid, pixel area
  shrinks with latitude. Ignoring that biases a large basin's mean toward its
  poleward end.
- **Area in degrees is wrong.** `area_km2` reprojects to an equal-area
  projection centred on the basin itself.
- **CHIRPS v3.0 is wetter than v2.0** by construction. basinkit will not splice
  the two into one series.
- **Landsat from Earth Search is requester-pays**: anonymous users get a 403,
  authenticated ones get a bill. basinkit takes Landsat from Planetary
  Computer instead.
- **BasinATLAS encodes extent in the middle of a column name**, not as a
  suffix: `pre_mm_uyr` is upstream, `run_mm_syr` is the local sub-catchment.
- **`ndarray.ptp()` was removed in NumPy 2.0**, and a test now scans the whole
  package for that and every other removed API.

---

## QGIS

`qgis_plugin/` is a Processing provider with nine algorithms: delineate a
basin from a canvas click, hand back the sub-catchments it was assembled from
with their routing, fetch layers clipped to it, compute the terrain surfaces,
grade whether the elevation model can carry them, grade every other layer
against something independent of it, basin statistics, the full morphometry,
and the eight-page PDF report. Being Processing algorithms, they all work in
batch mode, in the Model Builder and under `qgis_process`.

**QGIS 3.28 or newer.** Older builds ship Python 3.7 or 3.8, which basinkit's
dependencies do not support, so the package cannot be installed there at all.

Install the plugin from *Plugins → Manage and Install Plugins*, search
"basinkit". QGIS ships its own Python and there is still no official way for a
plugin to declare a pip dependency, so `basinkit` itself is installed
separately; the plugin prints the exact command for your installation. The
surest route, on every platform, is from inside QGIS -- *Plugins → Python
Console*, then:

```python
import runpy, sys
sys.argv = ["pip", "install", "--upgrade", "basinkit"]
runpy.run_module("pip", run_name="__main__")
```

That installs into the interpreter QGIS itself imports from. On Windows, a
terminal install must use the **OSGeo4W Shell**, not the ordinary Command
Prompt. `!pip install` works only in Jupyter; the QGIS console does not
understand it.

## Citation

If basinkit is useful in published work, please cite it *and* the underlying
datasets. `Basin.license_report()` prints the citations for the layers you
actually used.

## Licence

MIT for the code. The data carries its own terms; see `LICENSE` and
`basinkit catalog`.
