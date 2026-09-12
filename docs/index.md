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

Full results, including the twelve named rivers this check replaced as the headline, are in
[Verification](verification.md).

