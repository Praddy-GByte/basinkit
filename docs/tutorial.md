# Tutorial

This is the long-form walkthrough. If you want the runnable version instead,
open the [Quickstart notebook](notebooks/01_quickstart.ipynb): same material,
in cells you can execute.

---

## What basinkit is for

You have a point on a river. You want the catchment that drains into it, and
you want elevation, land cover, soil, rainfall and imagery for that catchment,
clipped to the actual basin, not to a rectangle around it.

Done by hand, that is a two-day job for someone who has done it before, and a
two-week job for someone who hasn't:

1. Download a continental HydroSHEDS shapefile and trace the basin upstream by hand
2. Register for Earthdata; work out which SRTM tiles you need; download forty of them
3. Mosaic, reproject, clip
4. Repeat on a different portal, with a different login, for land cover
5. Repeat again, in a different file format, for rainfall

basinkit is those five steps as five function calls, with **no account, login
or API key for any of its default sources.**

It is worth being clear about the part that goes wrong silently. The common
errors in that manual workflow are not crashes; they are wrong numbers that
look fine: area computed in square degrees, nodata values averaged into a mean,
scale factors never applied, a basin clipped to its bounding box so that half
the "basin mean" is actually the neighbouring catchment. basinkit gets those
right, and that is most of what it is for.

## Install

```bash
pip install basinkit          # core
pip install "basinkit[all]"   # everything, including the imagery stack
```

Python 3.10 or newer. On Windows, if `pip` fails while building GDAL or
rasterio, install those two from conda-forge first and then re-run:

```bash
conda install -c conda-forge gdal rasterio
```

---

## Step 1: Get the basin

```python
import basinkit as bk

basin = bk.Basin.from_point(26.87, 87.15)   # Sapta Koshi at Chatara
basin
```

```
<Basin area=54,497 km2 centroid=(27.974, 87.021) backend='hydrobasins'>
```

Note the argument order: **latitude first, then longitude.** Swapping them is
the single most common mistake, and basinkit raises rather than silently
delineating a basin in the wrong hemisphere.

### Put the point on the river

This matters more than anything else on this page. A coordinate that sits a
pixel or two off the channel (on the bank, on a road beside the river) can
return a basin three orders of magnitude too small, and **nothing crashes**.
You get a polygon, it looks plausible, and every number downstream is wrong.

basinkit defends against this by snapping to the nearest river reach and
recording how far it moved, in `basin.provenance`. Read that field:

```python
basin.provenance["snap_km"]        # how far the outlet was moved, in km
basin.provenance["backend"]        # which delineation route ran
```

If the snap distance is large and unexpected, your coordinate was wrong.

### Choosing a backend

```python
basin = bk.Basin.from_point(26.87, 87.15, backend="dem")
```

| backend | base grid | source | best for |
|---|---|---|---|
| `hydrobasins` | 15 arc-sec (~460 m) | SRTM, Feb 2000 | large basins; fast at any size |
| `api` | 3 arc-sec (~90 m) | MERIT-Hydro | mid-size basins, error-corrected |
| `dem` | 1 arc-sec (~30 m) | Copernicus DEM | small headwater catchments |
| `auto` | - | picks for you | the default; start here |

`hydrobasins` walks a pre-computed upstream graph, so it is fast whether the
basin is 50 km² or 5,000,000 km². `dem` routes flow on the fly, which is slower
but resolves small catchments the coarse grid cannot see. **If your basin is
smaller than about 100 km², use `backend="dem"`.**

### Check the answer before you trust it

```python
print(f"computed  {basin.area_km2:,.0f} km2")
print(f"reported  {basin.provenance['reported_up_area_km2']:,.0f} km2")
```

`area_km2` is computed here, by reprojecting to an equal-area projection
centred on your basin, not by summing degrees. `reported_up_area_km2` comes
from HydroBASINS and is derived completely independently. If the two disagree
by more than a few percent, something is wrong with the outlet.

Against published gauge areas at twelve gauges on six continents, the median
error is 0.74%. Where basinkit disagrees, the reason is written down; see
[Verification](verification.md).

### Why the polygon matters

```python
basin.bbox_efficiency    # 0.55 → the basin fills 55% of its bounding box
```

Everything below is masked to the **polygon**, not to the box. For a long, thin
or dendritic basin, a bounding-box download can be more than half water you did
not ask for, and if you then take a mean, that half is in your answer.

---

## Step 2: Ask for data

Every method returns data already clipped and masked to the basin, in EPSG:4326.

### Terrain

```python
dem = basin.dem()                     # Copernicus GLO-30, metres
stats = basin.terrain_stats()
```

`terrain_stats()` returns the standard morphometry:

```python
{'area_km2': 54497.1, 'elev_min_m': 70.7, 'elev_max_m': 8733.0,
 'elev_mean_m': 3785.9, 'relief_m': 8662.3, 'slope_mean_deg': 12.86,
 'bbox_efficiency': 0.546}
```

For very large basins basinkit coarsens automatically rather than trying to
hold a billion pixels in memory. The factor it used is recorded in
`dem.attrs["basinkit_coarsen_factor"]`, so you always know what resolution you
actually got.

### Land cover

```python
lc = basin.landcover()                       # ESA WorldCover, 10 m
lc = basin.landcover(source="esri", year=2023)   # Esri annual, 2017-2024

from basinkit.sources.landcover import class_fractions
class_fractions(lc)      # {'Tree cover': 0.31, 'Grassland': 0.22, ...}
```

### Soil

```python
clay = basin.soil("clay", depth="0-5cm")       # SoilGrids
awc  = basin.available_water_capacity()        # volumetric %
```

Plant-available water capacity is field capacity minus wilting point.
SoilGrids publishes both but not the difference, and its native projection is
Interrupted Goode Homolosine; basinkit does the subtraction and the
reprojection for you.

### Rainfall and water balance

```python
rain = basin.precipitation(2000, 2024)              # CHIRPS, mm/month
rain = basin.precipitation(source="terraclimate")   # or persiann
wb   = basin.water_balance(2015, 2020)              # ppt, aet, pet, q, soil
```

`precipitation()` returns a **basin-mean monthly time series**, weighted by
cosine of latitude so that high-latitude cells are not over-counted. It is not
a raster.

`water_balance()` returns a Dataset. Its `residual` term is P − AET − Q:
storage change plus model error. Look at it before you trust any single
component.

### Surface water, rivers and lakes

```python
occ    = basin.surface_water("occurrence")   # JRC, 37 years of Landsat, %
rivers = basin.rivers(min_order=4)           # HydroRIVERS, GeoDataFrame
lakes  = basin.lakes(min_area_km2=1.0)       # HydroLAKES, GeoDataFrame
```

### Pre-computed basin attributes

```python
attrs = basin.attributes()      # 281 BasinATLAS variables
```

These are already aggregated over everything upstream, so they characterise the
whole catchment without touching a raster. They cost one 2.7 GB download the
first time and nothing after that. Requires `backend="hydrobasins"`, because
BasinATLAS is keyed by HydroBASINS id.

### Satellite imagery

```python
s2 = basin.sentinel2("2023-10-01", "2023-12-31", cloud_cover=15)
ls = basin.landsat("1990-01-01", "1990-12-31")        # back to 1982
s1 = basin.sentinel1("2023-01-01", "2023-03-31")      # radar, sees through cloud
```

Dates are strings. By default these return a **median composite** over the
period, which suppresses cloud without needing a cloud mask. Pass
`composite=None` to get the full time stack instead.

---

## Step 3: Save it

```python
manifest = basin.download_all("koshi/")
manifest["layers"]
```

Writes to `koshi/`:

```
basin.geojson        the basin polygon
dem.tif              elevation
landcover.tif        land cover classes
soil.tif             soil property
surface_water.tif    JRC occurrence
precipitation.csv    basin-mean monthly series
rivers.gpkg          river reaches
manifest.json        what was fetched, from where, and what failed
```

Each layer is attempted independently, so one failing source (a polar basin
with no CHIRPS coverage, say) does not abort the rest. Failures land in
`manifest["failed"]` with the reason, rather than raising.

Every GeoTIFF is written with its **nodata value declared in the header**. This
sounds like a detail; it is the difference between your clip appearing correctly
in QGIS and appearing as a grey rectangle.

### See it in three dimensions

```python
basin.export_3d("koshi.html")                 # terrain + Sentinel-2 + rivers
basin.export_3d("koshi.html", texture=None)   # terrain only, much smaller
```

Writes one self-contained HTML file (imagery, elevation, river geometry and
the renderer are all embedded), so it opens from a memory stick on a laptop
with no network. Drag to orbit, scroll to zoom, toggle between the satellite
composite and an elevation tint, and stretch the vertical exaggeration.

The imagery window matters. The default is post-monsoon, which is usually the
cleanest; give it a dry-season window for your own region:

```python
basin.export_3d("basin.html", start="2024-11-01", end="2025-01-31",
                cloud_cover=10, mesh_width=512)
```

The first call downloads the renderer once into the cache; after that the
export works offline. `texture=None` needs nothing beyond the DEM and produces
a file a fraction of the size.

One choice worth knowing about, since it changes what you see: the elevation
tint maps colour to each point's **rank**, not its elevation. On a mountain
basin, where most of the land sits in the upper part of its own range, a linear
ramp collapses into one flat tone and the drainage network disappears.

---

## Step 4: Without writing any Python

Install the QGIS plugin (`Plugins → Manage and Install Plugins → Install from
ZIP`), then open the Processing Toolbox. Three algorithms appear under
**basinkit**:

| Algorithm | What it does |
|---|---|
| **Delineate river basin** | Point in, basin polygon out |
| **Fetch basin data layers** | Basin polygon in, clipped rasters out |
| **Basin statistics** | Area, relief, mean slope, land cover fractions as HTML |

The normal sequence is to run the first, check the polygon on the canvas, then
feed it to the second. The plugin needs the `basinkit` Python package; if it is
missing, it prints the exact `pip` command for QGIS's own Python, which is not
the same Python as your terminal.

---

## Step 5: Attribution

```python
print(basin.license_report(("hydrobasins", "cop30", "worldcover", "chirps")))
```

Prints licence and citation text for the layers you actually used. Paste it
into your methods section.

Every default layer is CC BY 4.0 or more permissive, which means you may
redistribute it and use it commercially, **provided you attribute it.** That is
not decoration; it is the licence condition.

```python
bk.Basin.check_license("cop30", commercial=True)   # raises if not permitted
```

The licence table in basinkit is executable. Datasets whose terms forbid
redistribution are blocked at the API rather than described in a footnote:
`merit_hydro`, `grdc` and `fabdem` will not silently download.

---

## When something goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| Basin is absurdly small | Outlet was off the channel, or on the bank | Move the point onto the river; check `provenance["snap_km"]` |
| Basin is in the wrong place entirely | Lat and lon swapped | Latitude first |
| Small headwater returns nothing sensible | Basin below the coarse grid's resolution | `backend="dem"` |
| `attributes()` raises | BasinATLAS needs a HydroBASINS id | `backend="hydrobasins"` |
| Raster looks like a grey rectangle in QGIS | Older export without declared nodata | Re-export with current version |
| Very slow on a continental basin | Pixel budget is coarsening a huge mosaic | Expected; check `basinkit_coarsen_factor` |
| Plugin says `basinkit` is not installed | QGIS uses its own Python | Run the pip command the plugin prints, then restart QGIS |
| `Access denied (403)` from `data.hydrosheds.org` | Some hosts refuse datacenter addresses (cloud VMs, CI runners, some campus proxies) | Run it from a normal network, or download the file once elsewhere and drop it in the cache directory (`BASINKIT_CACHE` sets where that is) |

---

## What basinkit does not do

It is an acquisition layer, not a modelling one. There is no rainfall-runoff
model, no calibration, no forecasting, no routing. It gives you the data a
model needs, correctly clipped and correctly scaled: the first twenty percent
of a project, which happens to be where most of the lost weeks and most of the
silent errors are.

For the modelling step, feed its output to wflow, SWAT, Raven or HBV.

---

## Next

- [Quickstart notebook](notebooks/01_quickstart.ipynb): the same material, runnable
- [Delineation](delineation.md): how each backend works and where each fails
- [Data catalogue](catalogue.md): all 26 datasets, what is implemented, what each is licensed under
- [Verification](verification.md): the twelve-gauge test and the disagreements
- [Related work](related-work.md): what else exists and where basinkit differs
