# BasinKit for ArcGIS Pro — setup, start to finish

Print this, or open it on the Windows machine. Fifteen minutes, once.

---

## Before you start

You need **ArcGIS Pro on Windows**. ArcGIS Pro does not run on macOS. Esri's own
supported route for a Mac is Parallels Desktop:
https://doc.esri.com/en/arcgis-pro/latest/get-started/run-pro-on-a-mac.html

You do **not** need the Spatial Analyst extension. BasinKit does its own
computation; it never calls Esri's Hydrology tools.

---

## Step 1 — Put the three files in one folder

Unzip `BasinKit-for-ArcGIS-Pro.zip` anywhere you like, for example
`C:\Tools\BasinKit\`. The folder must contain all three, side by side:

```
BasinKit.pyt
basinkit_runner.py
basinkit_everything.py
```

If they get separated the toolbox will tell you which one is missing.

---

## Step 2 — Add the toolbox to ArcGIS Pro

1. Open ArcGIS Pro and open (or create) a project.
2. In the **Catalog** pane, right-click **Toolboxes**.
3. Choose **Add Toolbox**.
4. Browse to `C:\Tools\BasinKit\BasinKit.pyt` and click OK.

**BasinKit** now appears in the Catalog pane with its tools grouped inside.

---

## Step 3 — Run Set Up BasinKit  (do this once)

Open **BasinKit → 0 Configuration → Set Up BasinKit**, leave every parameter
empty, and click **Run**.

It looks for an interpreter that already has basinkit. If it finds none, it
builds its own environment and installs basinkit into it. You do not need to
install Python first.

**ArcGIS Pro's own Python is never modified.** That separation is the whole
design: Pro's Python has `arcpy` with pinned GDAL and PROJ, and installing
scientific packages into it is the standard way to break ArcGIS Pro. BasinKit
builds a separate environment and talks to it as another process.

The environment goes in `%LOCALAPPDATA%\BasinKit\env`. The install downloads
about 150 MB and takes a few minutes. Every line appears in the messages pane,
so you can watch it work -- it is not frozen.

When it finishes it reports the basinkit version and every dependency it found.

### If you would rather set it up yourself

Install Python 3.12 from https://www.python.org/downloads/windows/, ticking
**Add python.exe to PATH**, then:

```
pip install "basinkit[all]"
where python
```

Put that `python.exe` path into the tool's first parameter instead. A Windows
environment variable `BASINKIT_PYTHON` pointing at the same interpreter works
too, and takes priority over the saved setting.

---

## Step 4 — Run it

Open **BasinKit → 1 Comprehensive Analysis → Complete Basin Analysis**.

Fill in three things:

| Field | What to put |
|---|---|
| Outlet latitude | e.g. `45.11188` |
| Outlet longitude | e.g. `-110.79438` |
| Output folder | an **empty** folder, e.g. `C:\Work\yellowstone` |

Leave everything else on its default and click **Run**.

Progress appears in the messages pane as each of the 70 analyses finishes.

### What you get

Added to your map automatically:

```
basin  ·  subbasins  ·  rivers  ·  lakes        (feature classes)
dem  ·  hillshade  ·  landcover                 (rasters)
```

Written into the output folder:

```
basin_report.pdf        a page per analysis: the code, the picture, the numbers
basinkit_collage.png    all 70 figures in one image
figures\                one PNG per analysis
tables\analyses.csv     every number, one row each
manifest.json           everything needed to reproduce the run
records.json            what ran, and the code that ran it
```

---

## The settings that actually matter

Everything else can stay on default.

| Setting | Default | Change it when |
|---|---|---|
| **Pixel budget for the elevation model** | 4,000,000 | Lower it (say 1,000,000) for a quick first look. Raise it for the final run on a small basin. |
| **Channel-initiation threshold, km²** | 5.0 | This is the single choice that most changes drainage density and stream counts. The run reports the whole curve, so you can see what your choice cost. |
| **Skip satellite imagery** | off | Tick it to cut the run by about a third. |
| **Climate window** | 2000–2024 | Match it to whatever period you need to defend. |

---

## How long it takes

Twenty minutes to about an hour, depending on basin size and pixel budget.
A 6,800 km² basin at a 3,000,000 pixel budget took roughly an hour and a half
with satellite imagery included.

It is not frozen. Each analysis prints a line when it finishes.

---

## If something goes wrong

**"Could not start …"** — the Python path is wrong. Re-run Set Up BasinKit.

**A missing-module error** — that interpreter does not have basinkit. Re-run Set Up BasinKit and let it build its own environment.

**One analysis reports "incomplete"** — a data server was busy. The run retries
once and then carries on; the reason is recorded in `manifest.json` and printed
on the report's methods page. Run it again later and that layer usually fills in.

**Nothing at all appears on the map** — check the output folder. The files are
written first and added to the map second, so if the files are there, only the
map step failed and nothing is lost.

**Paths with spaces** — they are handled, but if anything behaves oddly, try an
output folder with no spaces in its name first. That is the classic failure in
this corner of GIS.

---

## One honest note

The toolbox's own logic has been tested: every analysis has been run on real
data, and every tool's parameters and command line have been checked
automatically. But it has **not yet been run inside ArcGIS Pro itself** — no
Windows machine was available. The parts that remain unproven are narrow: how
the toolbox lists in the Catalog pane, the GeoJSON-to-feature-class conversion,
and adding layers to the map.

If any of those misbehave, the message in Pro's messages pane will say which
step and why. Send that message and it can be fixed.

---

MIT licence · Not affiliated with, endorsed by, or sponsored by Esri.
https://github.com/Praddy-GByte/basinkit · https://doi.org/10.5281/zenodo.22181933
