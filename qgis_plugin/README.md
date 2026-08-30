# basinkit for QGIS

Click a point on any river in the world. Get the basin above it, and the open
Earth observation data inside it — clipped to the polygon, not to its bounding
box, and without an account anywhere.

<img src="icon.png" alt="basinkit" width="72">

## What you get

Three algorithms in the Processing Toolbox, under **basinkit → River basins**:

**Delineate river basin** — click an outlet on the map canvas, get the upstream
basin as a polygon. Works anywhere on Earth. The output carries its own
provenance: which method ran, which dataset version, the licence, and how far
the outlet had to be moved.

**Fetch basin data layers** — takes a basin polygon and downloads elevation,
land cover, soil, surface water, rivers, lakes and rainfall for it. Everything
outside the polygon is nodata, so the layers drop straight onto a map.

**Basin statistics** — area on an equal-area projection, elevation range,
relief, mean slope, land cover fractions, and an HTML report.

All three are Processing algorithms, so batch mode, the Model Builder and
`qgis_process` work with them.

## Install

**1. Install the Python package.** QGIS ships its own Python and there is still
no official way for a plugin to declare a pip dependency, so this step is
manual. Open the **OSGeo4W Shell** on Windows, or a terminal on macOS and
Linux:

```
python -m pip install --upgrade "basinkit[stac]"
```

If you are unsure which interpreter QGIS uses, install the plugin first and
open it — the message bar will print the exact command for your installation.

**2. Install the plugin.** *Plugins → Manage and Install Plugins → Install from
ZIP*, and pick `basinkit_qgis-0.1.0.zip`.

**3. Restart QGIS.** The provider appears in the Processing Toolbox.

## Put the point on the river

This is the one thing worth knowing. A coordinate a pixel or two off the
channel can return a basin three orders of magnitude too small, and nothing
crashes — during testing, the Rhine at Lobith came back as 271 km² instead of
160,800, because a gauge coordinate sits on the *bank*, and on a big river the
bank belongs to a tiny side catchment.

The plugin guards against this: if a much larger river is within a kilometre,
it snaps to the main stem and tells you so in the log and in the output
attributes. But the guard is a safety net, not a substitute for clicking on the
blue line.

## Which method to use

| method | good for | resolution floor | first run |
|---|---|---|---|
| `auto` | most cases | — | as below |
| `hydrobasins` | any size, including the Amazon | ~130 km² | one ~80 MB download, then cached |
| `dem` | small headwater catchments | one 30 m pixel | DEM tiles for the window |
| `api` | a quick first look | ~90 m | nothing |

`auto` uses HydroBASINS and falls back to DEM routing when the basin sits at the
HydroBASINS resolution floor.

## Sizes and time

A large basin at 10 m is billions of pixels, so raster requests are coarsened
to fit a megapixel budget and the log reports the resolution actually used.
Raise the budget in the advanced parameters if you have the memory, or work on
a sub-basin to keep native resolution.

The first run of anything downloads; later runs read from a cache in your user
cache directory. Set `BASINKIT_CACHE` to move it.

## Licences

Every default layer is CC BY 4.0 or more permissive: redistributable,
commercially usable, attribution required. **Fetch basin data layers** writes a
`LICENSES.txt` next to the data with the terms and citations for exactly the
layers you fetched. Put it in your methods section.

## Data sources

Copernicus DEM GLO-30/90, NASADEM, SRTM · HydroBASINS, HydroRIVERS, HydroLAKES,
BasinATLAS · ESA WorldCover, ESRI Annual LULC · SoilGrids · CHIRPS,
PERSIANN-CDR, TerraClimate · JRC Global Surface Water · Sentinel-2, Sentinel-1
RTC, Landsat Collection 2, HLS.

## Licence

MIT for the plugin and the package. The data carries its own terms.
