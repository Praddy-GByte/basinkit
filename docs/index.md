<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/logo-wordmark-dark.svg">
  <img src="assets/logo-wordmark-light.svg" alt="basinkit" width="420">
</picture>

**There is no basin-native data acquisition layer for South Asia.** HyRiver is
US-only. rabpro and eodag take bounding boxes. basinkit is that missing layer,
and it works everywhere else too: click a river anywhere on Earth and get an
analysis-ready basin package. The basin polygon, elevation, land cover, soil,
rainfall, surface water and rivers clipped to it, the river's own profile, and
the full Horton-Strahler-Schumm morphometry, with no account anywhere in the
chain.

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
```

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

**It clips to the polygon, not the box.** A dendritic basin can occupy under a
quarter of its own bounding box. Every `Basin` exposes `bbox_efficiency` so you
can see this for yourself. A bbox download of such a basin throws away three
quarters of what it transferred, and every "basin average" computed from it is
contaminated with a neighbour's pixels.

**It needs no account.** Not for the DEM, not for Sentinel-2, not for Landsat,
not for terrain-corrected radar. Nineteen of the twenty-six catalogued datasets
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

Twelve reference gauges on six continents, checked against operating-agency
figures rather than against HydroBASINS itself:

| basin | basinkit | published | error |
|---|---:|---:|---:|
| Danube @ Bratislava | 131,449 | 131,300 | 0.1% |
| Amazon @ Óbidos | 4,671,504 | 4,680,000 | 0.2% |
| Godavari @ Polavaram | 306,750 | 307,800 | 0.3% |
| Mississippi @ Vicksburg | 2,979,823 | 2,964,000 | 0.5% |
| Sapta Koshi @ Chatara | 54,497 | 54,100 | 0.7% |
| Rhine @ Lobith | 159,776 | 160,800 | 0.6% |

**n = 12, median error 0.74%**, eight within 1% and nine within 3%. Twelve
is a small sample of large, well-mapped rivers; they were chosen because their
areas are published, which biases toward basins that have been studied. The
three that diverge by more than 3% do so for a physical reason, not a
delineation error, and the full write-up says which.

The Amazon (4.67 million km², 35,625 sub-basins) takes 43 seconds. Rainfall,
reflectance and radar are checked the same way: CHIRPS lands inside the
published Koshi climatology, a Sentinel-2 July composite gives an NDVI median of
0.82 over temperate farmland, Sentinel-1 RTC gives −9.3 dB over vegetated land.

Full results, including the three basins that diverge and why, are in
[Verification](https://praddy-gbyte.github.io/basinkit/verification/).

---

## Install

```bash
pip install basinkit              # core: delineation, DEM, land cover, soil, climate
pip install "basinkit[all]"       # + STAC imagery, DEM routing, interactive maps
```

Optional extras: `stac` (Sentinel/Landsat), `delineate` (D8 routing via
pyflwdir), `climate` (NetCDF), `viz` (leafmap, matplotlib).

---

## Delineation: three backends, because one is not enough

| backend | how it works | best for | resolution floor |
|---|---|---|---|
| `hydrobasins` *(default)* | walks the `NEXT_DOWN` graph over HydroBASINS level-12 units | any size, offline once cached, CC BY 4.0 | ~130 km² unit |
| `dem` | D8 routing with `pyflwdir` over a fresh Copernicus DEM window | small headwater catchments | one 30 m pixel |
| `api` | the public Global Watersheds service | a quick first look, zero download | ~90 m |

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

The default routes on a quarter-century-old 460 m grid. That is fine for a
large basin and wrong for a small or heavily modified one, which is what the
other two backends are for.

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
| `precipitation()` | CHIRPS v3.0 / PERSIANN-CDR / TerraClimate | 0.05-0.25° | no |
| `water_balance()` | TerraClimate P/AET/PET/Q/soil + closure residual | 4 km | no |
| `surface_water()` | JRC Global Surface Water (37 years of Landsat) | 30 m | no |
| `sentinel2()` | Sentinel-2 L2A via Earth Search | 10 m | no |
| `landsat()` | Landsat C2 L2, 1982→ via Planetary Computer | 30 m | no |
| `sentinel1()` | Sentinel-1 RTC, terrain-corrected, global | 10 m | no |
| `rivers()` / `lakes()` | HydroRIVERS / HydroLAKES | vector | no |
| `attributes()` | BasinATLAS: 281 pre-computed basin attributes | vector | no |

**Documented but not fetchable** (`basinkit catalog` marks these `DOC`):
ERA5-Land, GPM IMERG, GloFAS and GRACE need an account and a client basinkit
does not ship; MERIT Hydro, FABDEM and GRDC are licence-gated or have no API at
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

`qgis_plugin/` is a Processing provider with three algorithms: delineate a
basin from a canvas click, fetch layers clipped to it, and basin statistics.
Being Processing algorithms, they work in batch mode, in the Model Builder and
under `qgis_process`.

Install the zip through *Plugins → Manage and Install Plugins → Install from
ZIP*. QGIS ships its own Python and there is still no official way for a plugin
to declare a pip dependency, so `basinkit` itself is installed separately; the
plugin prints the exact command for your installation.

## Citation

If basinkit is useful in published work, please cite it *and* the underlying
datasets. `Basin.license_report()` prints the citations for the layers you
actually used.

## Licence

MIT for the code. The data carries its own terms; see `LICENSE` and
`basinkit catalog`.
