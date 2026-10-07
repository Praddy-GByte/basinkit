# BasinKit for ArcGIS Pro

Click a river anywhere on Earth and get the basin draining into it — with its
elevation, twelve terrain surfaces, land cover, soil, surface water, rivers,
Horton–Strahler morphometry, and a grade for every one of those layers measured
against an independently produced source.

Nineteen open datasets. No account, no API key, nothing downloaded by hand.

*Not affiliated with, endorsed by, or sponsored by Esri. ArcGIS and ArcGIS Pro
are trademarks of Esri.*

---

## It does not touch your ArcGIS Pro Python environment

That is the design, not a side effect.

`arcpy` pins its own GDAL and PROJ. Installing `rasterio` or `geopandas` into a
cloned Pro environment is a well-known way to break Pro, and it is the single
most common complaint about Python toolboxes that depend on the scientific
stack.

So this toolbox **never imports basinkit**. It starts `basinkit_runner.py` with
a *separate* Python interpreter, reads the lines that come back, and adds the
files to your map. Your `arcgispro-py3` environment is left exactly as Esri
shipped it.

```
ArcGIS Pro  ──►  BasinKit.pyt  ──►  subprocess  ──►  basinkit_runner.py
  (arcpy)          (arcpy only)                       (basinkit, no arcpy)
     ▲                                                        │
     └──────────── GeoTIFF / GeoJSON / CSV on disk ◄───────────┘
```

---

## Install

**1. Put these three files in the same folder.** They must stay together:

```
BasinKit.pyt
basinkit_runner.py
basinkit_everything.py
```

**2. Add the toolbox.** In ArcGIS Pro: Catalog pane → right-click **Toolboxes**
→ **Add Toolbox** → pick `BasinKit.pyt`.

**3. Run Set Up BasinKit.** Open **0 Configuration → Set Up BasinKit**, leave
every parameter empty, and run it. It looks for an interpreter that already has
basinkit; if it finds none it builds its own environment in
`%LOCALAPPDATA%\BasinKit\env` and installs basinkit there. You do not need to
install Python first. It then reports the basinkit version and every dependency
it found, and warns about any that are missing.

ArcGIS Pro's own Python is never modified. That is the whole design: Pro's
Python has `arcpy` with pinned GDAL and PROJ, and installing scientific packages
into it is the standard way to break ArcGIS Pro.

**Prefer to do it yourself?** Install basinkit into any Python 3.10 or newer
that is not Pro's, and put that `python.exe` in the tool's first parameter:

```
python -m pip install "basinkit[all]"
```

The environment variable `BASINKIT_PYTHON` works too, and takes priority over
the saved setting.

---

## One click: the whole thing

**1 Comprehensive Analysis → Complete Basin Analysis**

Give it a latitude and a longitude and an output folder. It runs **70 analyses**
and writes:

```
basin.geojson  subbasins.geojson  rivers.geojson  lakes.geojson
dem.tif  hillshade.tif  landcover.tif          ← added to your map
figures/            one PNG per analysis
tables/analyses.csv every number, one row each
records.json        what ran, with the code that ran it
manifest.json       everything needed to reproduce the run
basinkit_collage.png  all the figures in one image
basin_report.pdf      a page per analysis: the code, the picture, the numbers
```

The seventy analyses, by group:

| Group | Count | What is in it |
|---|---|---|
| Delineation | 6 | basin, sub-catchments, rivers, lakes, three independent routes, HydroATLAS attributes |
| Terrain | 14 | elevation, hillshade, slope, aspect, curvature, TPI, TRI, roughness, landform, flow accumulation, channels, wetness index, height above drainage, four elevation models compared |
| Shape and network | 6 | 42 morphometric parameters, the network order by order, Horton's laws, hypsometric curve, drainage-density curve, terrain statistics |
| River | 3 | long profile, discharge down the river, the river's facts |
| Land, soil and water | 21 | two land-cover maps, land-cover change, surface water, eleven soil properties, pH, available water, clay through six depths, zonal statistics |
| Climate | 7 | annual rainfall, monthly climatology, Mann-Kendall trend, SPI-3, SPI-12, water balance, aridity |
| Satellite | 5 | Sentinel-2, NDVI, Sentinel-1 radar, Landsat then and now |
| Does the data support the answer | 8 | five elevation tests, the support map, a grade for each of six layers, elevation split by terrain class |

### It does not stop when one data server does

Every step is run independently. A server that returns 503 is retried once; if it
still fails the step is recorded as incomplete — with the reason — and the run
carries on. The report's methods page lists anything that did not complete, so a
hole in the data is visible rather than silent.

### The manifest is the point

`manifest.json` records the outlet, every choice that changes the answer (pixel
budget, channel-initiation threshold, climate window), the basinkit and package
versions, the platform, and every dataset with its licence. Run the tool again
with the same manifest values and you get the same numbers.

Datasets are cited by key and licence, never redistributed. Where a national data
policy forbids reproducing primary data in a report — India's 2013
Hydro-Meteorological Data Dissemination Policy does exactly this for the Indus and
the Ganga–Brahmaputra–Meghna — the manifest still records which dataset, which
version and which access route produced the number.

### How long it takes

Roughly twenty minutes to an hour, depending on basin size and the pixel budgets.
Tick **Skip satellite imagery** to cut it by about a third. The pixel budgets are
the main lever: lower them for a first look, raise them for the final run.


## The tools

| Group | Tool | What it gives you |
|---|---|---|
| 0 Configuration | Set Up BasinKit | Finds an interpreter with basinkit, or builds one and installs it |
| **1 Comprehensive Analysis** | **Complete Basin Analysis** | **All 70, plus collage, PDF report and manifest** |
| 2 Basin Delineation | Delineate Basin | The upstream catchment polygon of one coordinate |
| 2 Basin Delineation | Sub-Catchments | The units it is assembled from, each with `NEXT_DOWN` |
| 2 Basin Delineation | Rivers and Lakes | Reaches with stream order and discharge; lakes |
| 3 Surface Derivatives | Terrain Surfaces | One elevation download, up to twelve surfaces from it |
| 4 Thematic Rasters | Land Cover, Soil and Surface Water | Clipped and masked to the polygon, not the bounding box |
| 5 Morphometry and Drainage Network | Morphometric Parameters | 42 named parameters, plus the network by Strahler order |
| 5 Morphometry and Drainage Network | Landscape Form (Chi and Channel Steepness) | **New in 0.8.0** — chi, normalised channel steepness, concavity and knickpoints. Checked cell by cell against TopoToolbox, within 6% at every quantile |
| 5 Morphometry and Drainage Network | Zonal Statistics | Any raster summarised inside any other raster's classes |
| 6 Quality Assessment | DEM Suitability Assessment | Five tests, plus a per-cell support map |
| 6 Quality Assessment | Data Quality Report | **New in 0.7.0** — a grade for every layer |
| 7 Report Generation | Basin Report (PDF) | Eight pages, methods and licences included |
| 8 Model Coupling | Export for Arc Hydro | **New in 0.8.0** — sub-catchments and reaches as `Catchment` and `DrainageLine`, with `HydroID`, `HydroCode`, `NextDownID` and `AreaSqKm` |

### Backends

`auto` lets the package choose. `hydrobasins`, `api`, `tdx` and `dem` are four
independent routes to the same outlet — running two and comparing is the cheapest
sanity check there is.

### A note on outlets at confluences

Snapping is ambiguous within a few hundred metres of a confluence: a coordinate
at the junction can pick up the other river's basin. If two backends disagree
sharply, move the outlet a few kilometres upstream and run again.

---

## What "data quality report" actually does

Six layers, each judged against something produced independently of it:

- **elevation** — against the model's own stated vertical error, split by terrain class
- **land cover** — ESA WorldCover against the ESRI annual map, same year
- **soil** — against SoilGrids' own published 5th–95th percentile band
- **rainfall** — CHIRPS against TerraClimate, annual totals
- **surface water** — permanent against seasonal
- **delineation** — against 2,550 gauges in 99 countries, blind

Two of those come back **ungraded on purpose**. No published threshold says a
SoilGrids interval is too wide to use, or a permanent-water share too low, so the
tool reports the measurement, writes into `not_graded_because` why it will not
grade it, and leaves the judgement to you. Inventing a cut-off and printing it as
though it were established would have been worse.

---

## Outputs

Everything lands in the output folder you choose, in formats Pro reads natively:

- `*.tif` — GeoTIFF rasters, added to the map as they are
- `*.geojson` — converted to a feature class in your default geodatabase
- `*.csv` — tables

---

## Licence and citation

Apache-2.0. Releases up to 0.8.4 were MIT and remain MIT. The licence does
not grant the name: a fork must carry its own.

If you use it in published work, please cite:

> Kaushik, P. (2026). *basinkit: basin-scale acquisition of open Earth
> observation data* (Version 0.8.2) [Computer software]. Zenodo.
> https://doi.org/10.5281/zenodo.22181933

The underlying datasets carry their own licences — `Basin.license_report()`
prints them.

- Source: https://github.com/Praddy-GByte/basinkit
- Docs: https://praddy-gbyte.github.io/basinkit
- PyPI: https://pypi.org/project/basinkit
- QGIS version: https://plugins.qgis.org/plugins/basinkit_qgis/
