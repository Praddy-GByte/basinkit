# BasinKit for ArcGIS Pro

Click a river anywhere on Earth and get the basin draining into it: **70 analyses,
a 72-page PDF and a full GIS layer set from one coordinate**.

This page is the whole setup, start to finish, and then the same run without
ArcGIS Pro at all.

| | |
|---|---|
| Analyses in one run | 70 |
| Tools in the toolbox | 12 |
| Open datasets reached | 19 |
| Accounts or API keys needed | none |
| Licence | MIT |

Not affiliated with, endorsed by, or sponsored by Esri.

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

---

## Step 1 — Install a Python that is not Pro's

This separation is the whole design. ArcGIS Pro's own Python ships `arcpy` with
pinned GDAL and PROJ, and installing scientific packages into it is the standard
way to break ArcGIS Pro. So basinkit goes somewhere else entirely, and the
toolbox talks to it as a separate process.

Download Python 3.12 for Windows from
[python.org](https://www.python.org/downloads/windows/). In the installer, tick
**Add python.exe to PATH** on the first screen.

```bash
pip install "basinkit[all]"
```

Find where that Python lives — you will need this exact path in step 3:

```bash
where python
```

Copy the line ending in `python.exe`. It usually looks like:

```
C:\Users\<you>\AppData\Local\Programs\Python\Python312\python.exe
```

Check it worked:

```bash
python -c "import basinkit; print(basinkit.__version__)"
```

You should see `0.7.0`.

---

## Step 2 — Add the toolbox to ArcGIS Pro

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

**BasinKit** now appears in the Catalog pane with its tools grouped inside.

---

## Step 3 — Point it at that Python, once

Open **BasinKit → Setup → Configure BasinKit**, browse to the `python.exe` path
from step 1, and click Run. It reports the basinkit version and every dependency
it found; anything missing comes back as a warning naming that package.

If you would rather not save a path, set a Windows environment variable
`BASINKIT_PYTHON` to the same `python.exe`. That takes priority over the saved
setting.

---

## Step 4 — Run it

Open **BasinKit → 0 Everything → Complete basin analysis (one click)** and fill
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

In QGIS, basinkit is a Processing provider with nine algorithms — a different,
lighter set, not this 70-analysis run. See the
[QGIS plugin](https://plugins.qgis.org/plugins/basinkit_qgis/).

---

## Which tool does what

Twelve tools. One of them does everything; the other eleven exist so you can take
a single piece into your own model, batch or script. All of them work in
ModelBuilder.

| Tool | Category | What it does |
|---|---|---|
| Complete basin analysis (one click) | 0 Everything | One coordinate in. Seventy analyses out, plus a collage, an illustrated PDF and a manifest that re-runs the whole thing. Start here. |
| Configure BasinKit | Setup | Point the toolbox at the Python interpreter that has basinkit, and check it works. Run this once, before anything else. |
| Delineate basin | 1 Basin | The upstream catchment of one coordinate, as a polygon. |
| Sub-catchments | 1 Basin | The units the basin is assembled from, each carrying `NEXT_DOWN` — the routing table a hydrological model wants. |
| Rivers and lakes | 1 Basin | River reaches with Strahler order and mean discharge, and the lakes inside the basin. |
| Terrain surfaces | 2 Terrain | One elevation download, twelve surfaces derived from it: hillshade, slope, aspect, curvature, TPI, TRI, roughness, landform, flow accumulation, channels, wetness index and height above nearest drainage. |
| Land cover, soil and surface water | 3 Layers | Open Earth-observation layers clipped and masked to the basin polygon — not to its bounding box. |
| Morphometry | 4 Shape and network | Forty-two named parameters in three sets — linear, areal and relief — plus the network by Strahler order. Streams are counted as Strahler streams, not as the raw reaches in the river layer. |
| Zonal statistics | 4 Shape and network | Any raster summarised inside any other raster's classes. |
| Can the DEM carry terrain analysis here? | 5 Does the data support the answer | Five tests against the elevation model's own stated vertical error, with a per-cell map of where the answer is supported and where it is not. |
| Data quality report | 5 Does the data support the answer | New in 0.7.0. Grades elevation, land cover, soil, rainfall, surface water and the delineation itself — each against an independently produced source rather than against itself. |
| Basin report (PDF) | 6 Output | An eight-page PDF: the suitability grade on the cover, every morphometric parameter with its symbol and original reference, and the channel network against Horton's laws. |

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
| "Could not start …" | The Python path is wrong. Re-run Configure BasinKit. |
| A missing-module error | That interpreter does not have basinkit. Run `pip install "basinkit[all]"` in the same Python you pointed at, then Configure BasinKit again. |
| One analysis says "incomplete" | A data server was busy. The run retries once and carries on; the reason is recorded in `manifest.json` and printed on the report's methods page. Run it again later and that layer usually fills in. |
| Nothing appears on the map | Check the output folder. Files are written first and added to the map second — if the files are there, only the map step failed and nothing is lost. |
| Odd behaviour with paths | Spaces in paths are handled, but try an output folder without spaces first. That is the classic failure in this corner of GIS. |

---

## What is not yet proven

**The toolbox has not yet been run inside ArcGIS Pro itself.** No Windows machine
was available.

What *is* tested: every one of the 70 analyses has run on real data, every tool's
parameters and command line are checked automatically, and every `arcpy` call is
checked against Esri's documentation. The run was cross-checked against
CAMELS-US, GAGES-II and USGS StreamStats on USGS gauge 06191500, the Yellowstone
River at Corwin Springs — mean elevation within 0.01%, basin area within 0.13%.
See [Verification](verification.md).

What remains unproven is narrow: how the toolbox lists in the Catalog pane, the
GeoJSON-to-feature-class conversion, and adding layers to the map.

If any of those misbehave, ArcGIS Pro prints the reason in the messages pane.
Send that message — as a comment, a direct message, or a
[GitHub issue](https://github.com/Praddy-GByte/basinkit/issues) — and it gets
fixed. A report that it simply worked is just as useful, and slower to come by.

---

MIT licence. ArcGIS and ArcGIS Pro are trademarks of Esri. Dataset licences are
recorded per-run in `manifest.json`.
