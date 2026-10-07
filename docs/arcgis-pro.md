# BasinKit for ArcGIS Pro

Click a river anywhere on Earth and get the basin draining into it: **70 analyses,
a 72-page PDF and a full GIS layer set from one coordinate**.

This page is the whole setup, start to finish, and then the same run without
ArcGIS Pro at all.

| | |
|---|---|
| Analyses in one run | 70 |
| Tools in the toolbox | 14 |
| Open datasets reached | 19 |
| Accounts or API keys needed | none |
| Licence | Apache-2.0 |

Not affiliated with, endorsed by, or sponsored by Esri.

---

## Why you need BasinKit in ArcGIS Pro

**It brings the data.** Nineteen open datasets arrive already clipped and masked
to the basin polygon — elevation, land cover, soil to two metres, rainfall,
surface water, rivers, lakes, satellite imagery. No account, no API key, nothing
downloaded by hand, nothing stitched together from tiles.

**It starts from a coordinate.** One latitude and longitude. The basin, its
sub-catchments carrying `NEXT_DOWN`, its rivers with Strahler order and mean
discharge, and its lakes — without needing a DEM that covers an upstream area
you have not measured yet.

**Forty-two morphometric parameters, with their references.** Linear, areal and
relief, plus the channel network by Strahler order. Streams are counted as
Strahler streams, not as the raw reaches in the river layer.

**Landscape form, not just shape.** Chi, normalised channel steepness, concavity
and knickpoints — whether the landscape is still adjusting or has settled. k_sn
agrees with TopoToolbox to within 6% at every quantile on an identical DEM, and
its median moves under 2% across a fourfold change in cell size.

**A grade for every layer.** `data_quality()` measures elevation, land cover,
soil, rainfall, surface water and the delineation itself against an
independently produced source, and says which of them can carry the weight your
study puts on it. Where it cannot judge, it says so rather than guessing.

**Seventy analyses from one click.** Each one a figure and a set of
measurements, written out as a 72-page PDF, a collage, one CSV row per number,
and a manifest recording every choice, version and licence the run used — enough
to run it again and get the same numbers.

**It hands off to your model.** The sub-catchments and reaches export with Arc
Hydro's own field names — `HydroID`, `HydroCode`, `NextDownID`, `AreaSqKm`, on
layers called Catchment and DrainageLine — so Arc Hydro's tools read them
without being told anything about basinkit. It is a renaming, not a computation:
every value written is one basinkit already holds.

**Layers on your map.** Basin, sub-catchments, rivers and lakes as feature
classes; elevation, hillshade and land cover as rasters. Every tool works in
ModelBuilder, and nothing here needs the Spatial Analyst extension.

Apache-2.0 licence.

---

## Before you start


**ArcGIS Pro on Windows.** ArcGIS Pro does not run on macOS. Esri's own supported
route for a Mac is Parallels Desktop with Windows 11 ARM installed as the guest
operating system — see
[Run ArcGIS Pro on a Mac](https://doc.esri.com/en/arcgis-pro/latest/get-started/run-pro-on-a-mac.html).

**You do not need the Spatial Analyst extension.** basinkit does its own
computation and never calls Esri's Hydrology tools.

**No ArcGIS Pro at all?** Skip to [Without ArcGIS Pro](#without-arcgis-pro). The
engine is plain Python and produces the identical 70 analyses, report and
manifest.

**You do not need to install Python first.** Step 2 sets one up for you.

---

## Step 1 — Add the toolbox to ArcGIS Pro

Unzip `BasinKit-for-ArcGIS-Pro.zip` anywhere, for example `C:\Tools\BasinKit\`.
Three files must sit side by side in that folder. If they get separated, the
toolbox names the missing one.

```
BasinKit.pyt
basinkit_runner.py
basinkit_everything.py
```

1. Open ArcGIS Pro and open or create a project.
2. In the **Catalog** pane, right-click **Toolboxes** and choose **Add Toolbox**.
3. Browse to `BasinKit.pyt` and click OK.

**BasinKit** now appears in the Catalog pane with its toolsets inside.

---

## Step 2 — Run Set Up BasinKit, once

Open **BasinKit → 0 Configuration → Set Up BasinKit**, leave every parameter
empty, and click Run.

It looks for an interpreter that already has basinkit. If it finds none, it
builds its own environment and installs basinkit into it. Nothing to download
first, and no Python to install by hand.

**ArcGIS Pro's own Python is never modified.** That separation is the whole
design: Pro's Python ships `arcpy` with pinned GDAL and PROJ, and installing
scientific packages into it is the documented way to break ArcGIS Pro. BasinKit
builds a separate environment and talks to it as another process.

The environment goes in `%LOCALAPPDATA%\BasinKit\env`. The install downloads
about 150 MB and takes a few minutes; every line appears in the messages pane,
so you can see it working.

When it finishes it reports the basinkit version and every dependency it found.

### If you would rather do it yourself

Install Python 3.12 from [python.org](https://www.python.org/downloads/windows/),
ticking **Add python.exe to PATH**, then:

```bash
pip install "basinkit[all]"
where python
```

Put that `python.exe` path into the tool's first parameter instead. Setting a
Windows environment variable `BASINKIT_PYTHON` to the same path works too, and
takes priority over the saved setting.

---

## Step 3 — Run it

Open **BasinKit → 1 Comprehensive Analysis → Complete Basin Analysis** and fill
in three things. Leave the rest on default.

| Field | What to put |
|---|---|
| Outlet latitude | `45.11188` |
| Outlet longitude | `-110.79438` |
| Output folder | an **empty** folder, e.g. `C:\Work\yellowstone` |

Progress appears in the messages pane as each of the 70 analyses finishes. A run
takes twenty minutes to about an hour. A 6,800 km² basin at a 3,000,000-pixel
budget took roughly an hour and a half with satellite imagery included. It is not
frozen — each analysis prints a line when it completes.

### What lands on your map

```
basin · subbasins · rivers · lakes     feature classes
dem · hillshade · landcover            rasters
```

### What lands in the output folder

| File | What it is |
|---|---|
| `basin_report.pdf` | A page per analysis: the code that ran, the picture, the numbers |
| `basinkit_collage.png` | All 70 figures in one image |
| `figures/` | One PNG per analysis |
| `tables/analyses.csv` | Every number, one row each |
| `manifest.json` | Everything needed to reproduce the run — versions, choices, licences |
| `records.json` | What ran, and the code that ran it |

### The 70, by group

| Group | Analyses |
|---|---|
| Delineation | 6 |
| Terrain | 14 |
| Shape and network | 6 |
| River | 3 |
| Climate | 7 |
| Land, soil and water | 21 |
| Satellite | 5 |
| Does the data support the answer | 8 |

---

## Without ArcGIS Pro

The engine never imports `arcpy`. If you only want to check the science, or you
have no ArcGIS licence, run the same thing from a terminal — same 70 analyses,
same report, same manifest.

```bash
pip install "basinkit[all]"
python basinkit_runner.py everything --lat 45.11188 --lon -110.79438 --out yellowstone
```

`basinkit_runner.py` is in the same zip as the toolbox, and also in
`arcgis_toolbox/` in the repository.

In QGIS, basinkit is a Processing provider with eleven algorithms — a different,
lighter set, not this 70-analysis run. See the
[QGIS plugin](https://plugins.qgis.org/plugins/basinkit_qgis/).

---

## Which tool does what

Fourteen tools. One of them does everything; the other thirteen exist so you can take
a single piece into your own model, batch or script. All of them work in
ModelBuilder.

| Tool | Category | What it does |
|---|---|---|
| Complete Basin Analysis | 1 Comprehensive Analysis | One coordinate in. Seventy analyses out, plus a collage, an illustrated PDF and a manifest that re-runs the whole thing. Start here. |
| Set Up BasinKit | 0 Configuration | Finds an interpreter with basinkit, or builds one and installs it. Run this once, before anything else. |
| Delineate Basin | 2 Basin Delineation | The upstream catchment of one coordinate, as a polygon. |
| Sub-Catchments | 2 Basin Delineation | The units the basin is assembled from, each carrying `NEXT_DOWN` — the routing table a hydrological model wants. |
| Rivers and Lakes | 2 Basin Delineation | River reaches with Strahler order and mean discharge, and the lakes inside the basin. |
| Terrain Surfaces | 3 Surface Derivatives | One elevation download, twelve surfaces derived from it: hillshade, slope, aspect, curvature, TPI, TRI, roughness, landform, flow accumulation, channels, wetness index and height above nearest drainage. |
| Land Cover, Soil and Surface Water | 4 Thematic Rasters | Open Earth-observation layers clipped and masked to the basin polygon — not to its bounding box. |
| Morphometric Parameters | 5 Morphometry and Drainage Network | Forty-two named parameters in three sets — linear, areal and relief — plus the network by Strahler order. Streams are counted as Strahler streams, not as the raw reaches in the river layer. |
| Zonal Statistics | 5 Morphometry and Drainage Network | Any raster summarised inside any other raster's classes. |
| DEM Suitability Assessment | 6 Quality Assessment | Five tests against the elevation model's own stated vertical error, with a per-cell map of where the answer is supported and where it is not. |
| Data Quality Report | 6 Quality Assessment | New in 0.7.0. Grades elevation, land cover, soil, rainfall, surface water and the delineation itself — each against an independently produced source rather than against itself. |
| Landscape Form (Chi and Channel Steepness) | 5 Morphometry and Drainage Network | Chi, normalised channel steepness, concavity and knickpoints. Whether the landscape is still adjusting, or has settled. k_sn was checked cell by cell against TopoToolbox on two basins and agrees to within 6% at every quantile. |
| Basin Report (PDF) | 7 Report Generation | An eight-page PDF: the suitability grade on the cover, every morphometric parameter with its symbol and original reference, and the channel network against Horton's laws. |
| Export for Arc Hydro | 8 Model Coupling | The sub-catchments and reaches with Arc Hydro field names: `HydroID`, `HydroCode`, `NextDownID`, `AreaSqKm`. A GeoPackage with Catchment and DrainageLine layers, plus the same two tables as CSV. `DrainID` is deliberately left out: it needs a reach-to-catchment link basinkit does not hold, and a spatial join would be a guess. |

---

## The settings that actually matter

Everything else can stay on default.

| Setting | Default | Change it when |
|---|---|---|
| Pixel budget for the DEM | 4,000,000 | Lower it (say 1,000,000) for a quick first look. Raise it for a final run on a small basin. |
| Channel-initiation threshold | 5.0 km² | This single choice changes drainage density and stream counts more than anything else. The run reports the whole curve, so you can see what your choice cost. |
| Skip satellite imagery | off | Tick it to cut the run by about a third. |
| Climate window | 2000–2024 | Match it to whatever period you need to defend. |

---

## If something goes wrong

| Message | What it means |
|---|---|
| "Could not start …" | The Python path is wrong. Re-run Set Up BasinKit. |
| A missing-module error | That interpreter does not have basinkit. Re-run Set Up BasinKit and let it build its own environment. |
| One analysis says "incomplete" | A data server was busy. The run retries once and carries on; the reason is recorded in `manifest.json` and printed on the report's methods page. Run it again later and that layer usually fills in. |
| Nothing appears on the map | Check the output folder. Files are written first and added to the map second — if the files are there, only the map step failed and nothing is lost. |
| Odd behaviour with paths | Spaces in paths are handled, but try an output folder without spaces first. That is the classic failure in this corner of GIS. |

---

## What is not yet proven

**What has been run inside ArcGIS Pro.** The toolbox loads and lists all of its
toolsets in the Catalog pane, and **Set Up BasinKit** has been run there — where
it correctly reported that ArcGIS Pro's own Python 3.9 is below the 3.10 that
basinkit requires, and named that as the reason rather than guessing at a
firewall.

**What has not.** No complete analysis run inside ArcGIS Pro has been reported
yet, so the GeoJSON-to-feature-class conversion and the step that adds layers to
the map are still unproven in Pro itself.

What *is* tested: every one of the 70 analyses has run on real data; every tool's
parameters and command line are checked on every commit by
[`verify/run_toolbox_wiring.py`](https://github.com/Praddy-GByte/basinkit/blob/main/verify/run_toolbox_wiring.py),
which loads the toolbox against a stub `arcpy` and parses each tool's command
line with the runner's own parser; and every `arcpy` call is checked against
Esri's documentation. The run was cross-checked against CAMELS-US, GAGES-II and
USGS StreamStats on USGS gauge 06191500, the Yellowstone River at Corwin Springs
— mean elevation within 0.01%, basin area within 0.13%. Channel steepness was
cross-checked cell by cell against TopoToolbox. See
[Verification](verification.md).

If any of those misbehave, ArcGIS Pro prints the reason in the messages pane.
Send that message — as a comment, a direct message, or a
[GitHub issue](https://github.com/Praddy-GByte/basinkit/issues) — and it gets
fixed. A report that it simply worked is just as useful, and slower to come by.

---

Apache-2.0 licence. ArcGIS and ArcGIS Pro are trademarks of Esri. Dataset licences are
recorded per-run in `manifest.json`.
