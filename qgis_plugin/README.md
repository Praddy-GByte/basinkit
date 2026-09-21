# basinkit for QGIS

Click a point on any river in the world. Get the basin above it, and the open
Earth observation data inside it, clipped to the polygon, not to its bounding
box, and without an account anywhere.

<img src="icon.png" alt="basinkit" width="72">

## What you get

Eight algorithms in the Processing Toolbox, under **basinkit → River basins**:

**Delineate river basin**: click an outlet on the map canvas, get the upstream
basin as a polygon. Works anywhere on Earth. The output carries its own
provenance: which method ran, which dataset version, the licence, and how far
the outlet had to be moved.

**Sub-catchments and their routing**: the pieces a basin is assembled from,
each carrying `NEXT_DOWN`, the id of the sub-catchment it drains into. That is
the routing graph itself, which is what a distributed rainfall-runoff model
wants and what otherwise has to be inferred from geometry afterwards. Exactly
one sub-catchment drains out of the set, and the algorithm says so or warns
that more than one does.

**Fetch basin data layers**: takes a basin polygon and downloads elevation,
land cover, soil, surface water, rivers, lakes and rainfall for it. Everything
outside the polygon is nodata, so the layers drop straight onto a map.

**Terrain surfaces**: slope, aspect, hillshade, curvature, topographic position
index, terrain ruggedness index, local relief, slope-position classes, flow
accumulation, the channel network, the topographic wetness index and height
above nearest drainage. All of them come from one elevation download rather
than one per surface, so asking for ten costs the same fetch as asking for one.
Cell size is taken per row from that row's latitude: a cell 0.001 degrees wide
spans 111 m at the equator and 56 m at 60 degrees north, and dividing by one
assumed width reports a high-latitude basin as about twice as steep as it is.

**Elevation data suitability**: whether the elevation model can carry any of
the above in this particular basin. Five measurements against stated
thresholds, combined into HIGH, MODERATE or LIMITED, plus a per-cell raster of
which ground the answer rests on. Tested on 133 gauges against an
independently produced elevation model: where it says HIGH the two models
agree about the slope field at r = 0.94, where it says LIMITED at r = 0.76.
Read this one before quoting any terrain number.

**Basin morphometry**: the classical Horton-Strahler-Schumm set from one run.
Streams, lengths and bifurcation ratios per Strahler order; drainage density,
stream frequency, texture, form factor, elongation and circularity ratios,
relief ratio, ruggedness and Melton numbers, the hypsometric integral, and the
gradient of the main channel. Streams are counted as Strahler streams, not as
the reaches a river dataset splits them into, and both counts are shown side by
side. The counts are then tested against what Strahler ordering allows: N(u) is
at least twice N(u+1), so the bifurcation ratio can never fall below 2 (Shreve
1966), and a basin with one outlet has exactly one stream of its highest order.
Counts that break either are reported rather than returned as numbers.

**Basin statistics**: area on an equal-area projection, elevation range,
relief, mean slope, land cover fractions, and an HTML report.

**Basin report (PDF)**: eight A4 pages a thesis chapter or a manuscript
appendix can use directly. Cover with the suitability grade, elevation and
hypsometry, slope and aspect with an aspect rose, the shape of the ground, the
channel network against Horton's laws, the full morphometric table with every
parameter's symbol and original reference, what the answer rests on, and a
methods page with software versions, licences and citations. Pages five and six
need the river network; without it they say which parameters are missing and
why, rather than printing a partial table that reads like a complete one.

## How this differs from the other basin plugins

The QGIS repository already has plugins that delineate from a clicked point.
**Sen Hydro - Watershed Delineation** does it well, and through the same public
Global Watersheds service (mghydro.com) that this plugin can also use, so the
delineation step overlaps and there is no point pretending otherwise. What is
different here:

**The data comes back as layers.** Elevation, land cover, soil, rainfall,
surface water, rivers and lakes are fetched and clipped to the polygon, as
rasters and vectors you can style and analyse. Not a statistics table, not a
report.

**Morphometry.** The full Horton-Strahler-Schumm set from one algorithm, with
Strahler streams counted as streams rather than as the reaches a river dataset
splits them into. That distinction changes the bifurcation ratios enough to
change what a table means, and the algorithm now flags counts that Strahler
ordering makes impossible.

**It works offline.** The default backend walks the HydroBASINS level-12 graph
from a locally cached copy, so after the first download no network is needed.
The mghydro path is there as a quick alternative, not as the only route. Note
that its MERIT-Hydro lineage is CC BY-NC, so that one path is not clean for
commercial work; the plugin records which backend ran.

**Everything is a Processing algorithm**, so it runs in batch mode, in the
Model Builder and under `qgis_process`.

All four are Processing algorithms, so batch mode, the Model Builder and
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
open it; the message bar will print the exact command for your installation.

**2. Install the plugin.** *Plugins → Manage and Install Plugins → Install from
ZIP*, and pick `basinkit_qgis-0.1.0.zip`.

**3. Restart QGIS.** The provider appears in the Processing Toolbox.

## Put the point on the river

This is the one thing worth knowing. A coordinate a pixel or two off the
channel can return a basin three orders of magnitude too small, and nothing
crashes. During testing, the Rhine at Lobith came back as 271 km² instead of
160,800, because a gauge coordinate sits on the *bank*, and on a big river the
bank belongs to a tiny side catchment.

The plugin guards against this: if a much larger river is within a kilometre,
it snaps to the main stem and tells you so in the log and in the output
attributes. But the guard is a safety net, not a substitute for clicking on the
blue line.

## Which method to use

| method | good for | resolution floor | first run |
|---|---|---|---|
| `auto` | most cases | - | as below |
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
TerraClimate · JRC Global Surface Water · Sentinel-2, Sentinel-1
RTC, Landsat Collection 2, HLS.

## Licence

MIT for the plugin and the package. The data carries its own terms.
