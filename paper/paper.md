---
title: 'basinkit: basin-scale acquisition and analysis of open Earth observation data from a single coordinate'
tags:
  - Python
  - hydrology
  - geomorphology
  - river basins
  - watershed delineation
  - Earth observation
  - QGIS
  - ArcGIS Pro
authors:
  - name: Pradeepika Kaushik
    orcid: 0000-0000-0000-0000
    affiliation: 1
affiliations:
  - name: AFFILIATION TO BE SUPPLIED
    index: 1
date: 2 October 2026
bibliography: paper.bib
---

# Summary

`basinkit` turns a single coordinate on a river into an analysis-ready basin
package. Given a latitude and longitude, it delineates the upstream basin,
retrieves open Earth observation layers clipped and masked to that polygon
rather than to its bounding box, extracts the profile of the river arriving at
the point together with its tributaries, and computes the classical
Horton–Strahler–Schumm morphometry [@horton1945; @strahler1957; @schumm1956]
with streams counted as Strahler streams rather than as the reaches a river
dataset happens to split them into. From version 0.8.0 it also describes the
form of the channel network: the integral variable $\chi$ [@perron2013],
normalised channel steepness $k_{sn}$ [@wobus2006] with the concavity fitted
from Flint's law [@flint1974], and the knickpoints found along the trunk.

Nineteen datasets are reachable without an account, login or credential.
Results are returned as masked arrays, GeoDataFrames and tables, and can be
written as GeoTIFFs, feature classes, a CSV of every computed number, an
illustrated PDF report, and a manifest recording every dataset version,
parameter and licence, so that a run can be reproduced. The same analyses are
available from Python, from a command-line interface, from a QGIS Processing
provider, and from an ArcGIS Pro Python toolbox that requires no Spatial
Analyst licence.

# Statement of need

Assembling the data for a single river basin is routine work that is rarely
quick. The analyst must find a flow-direction product, delineate the basin,
locate elevation, land cover, soil, rainfall and surface-water layers, clip and
mask each to the basin rather than to its extent, reconcile their projections
and resolutions, and record what was used. The work is repeated for every
basin and is seldom reproducible from the record left behind.

Several packages solve parts of this. `watershed-workflow` performs the whole
pipeline well but is scoped to the conterminous United States; `HyRiver` is
likewise US-only. `rabpro` [@schwenk2022] is global and masks to the basin, but
requires a Google Earth Engine account and MERIT-Hydro credentials and returns
zonal statistics rather than the data. `hydromt` [@eilander2023] delineates
globally and auto-downloads without an account, but its account-free catalogue
is a sample covering one Italian basin, its global catalogue is reachable only
from within its home institution's network, and it clips by extent with a
buffer rather than by polygon mask. Web services such as mghydro Global
Watersheds are global and account-free but are applications, not libraries.

No existing open-source package provides, through one installable API and
without an account, login or credential for any default source, the complete
chain from an arbitrary global outlet coordinate to a delineated basin polygon
to multiple Earth observation datasets returned as polygon-masked gridded
arrays. `basinkit` provides that chain, and adds the morphometric and
channel-form analyses that are usually the reason the data was wanted.

# Validation

Delineation was validated blind against agency-published catchment areas at
2,550 gauges in 99 countries on six continents, drawn by seed from the Global
Streamflow Indices and Metadata archive [@do2018] before any result was seen,
using each station's original agency coordinate rather than the adjusted
coordinate the archive supplies. Accuracy is reported by catchment size rather
than as a single figure, because it varies by three orders of magnitude across
that range: the median area error falls from 181% below 100 km² to 0.3% above
100,000 km². On the same 30 m rasters, median area error for catchments under
2,000 km² was 4.6% for `basinkit`, 8.6% for WhiteboxTools, 17.6% for `pysheds`
and 41.6% for the HydroBASINS units alone.

Channel steepness was cross-checked cell by cell against the TopoToolbox
implementation [@schwanghart2014] on two independent basins under identical
grids, channel thresholds and reference concavity: over cells where both report
a positive gradient, every quantile agreed to within 6% and the distributions
correlated at $r = 0.973$ and $r = 0.987$. Knickpoint detection was tested so
that it could fail: the same basin was run with and without the gorge below the
gauge on Fall Creek, New York, and the tool reported one knickpoint with a
65.8 m step in the first case and none in the second, having been told nothing
about the waterfall.

`basinkit` additionally grades its own inputs. Six layers are judged against
independently produced sources rather than against themselves, and layers for
which no published threshold exists are returned ungraded with the reason
stated. Quantities the package cannot support — an uplift rate, an erosional
stage — are documented as such, as are the sensitivities of knickpoint counts
and the concavity fit to cell size.

# Acknowledgements

`basinkit` builds on `pyflwdir`, `rasterio`, `rioxarray`, `xarray`,
`geopandas`, `shapely`, `pyproj` and `numpy`, and uses `leafmap` [@wu2021] for
interactive output.

# References
