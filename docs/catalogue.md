# Data catalogue

Generated from `basinkit/catalog.py`, the same table the fetchers read.
Run `basinkit catalog` for the live version.

**19 of 26 datasets can be fetched today**; 19 need no account.

Entries marked **documented only** are ones basinkit knows about but cannot download -- asking for one raises an error carrying the access route and licence, rather than pretending to be a feature.


## Climate

### `chirps` -- CHIRPS v3.0

| | |
|---|---|
| Resolution | 0.05 degree |
| Temporal | 1981 to near-real-time |
| Coverage | 60N-60S |
| Licence | Public domain |
| Access | https://data.chc.ucsb.edu/products/CHIRPS/v3.0/ (anonymous) |
| Fetchable by basinkit | yes |
| Commercial use | yes |
| Redistribution | yes |

v3.0 is gauge-undercatch corrected and systematically wetter than v2.0. basinkit refuses to concatenate v2 and v3 into one series.

### `era5_land` -- ERA5-Land **documented only** **[account]**

| | |
|---|---|
| Resolution | 0.1 degree (~9 km), hourly |
| Temporal | 1950 to present (~6 day lag) |
| Coverage | Global |
| Licence | CC BY 4.0 |
| Access | Copernicus CDS via cdsapi (ECMWF account + personal access token) |
| Fetchable by basinkit | **no** |
| Commercial use | yes |
| Redistribution | yes |

Requires a free account and a one-time manual licence click per dataset, and requests are queued for minutes to hours. Never put it on a synchronous path. Use reanalysis-era5-land-timeseries for point extraction: far faster than gridded pulls.

### `imerg` -- GPM IMERG V07 **documented only** **[account]**

| | |
|---|---|
| Resolution | 0.1 degree, 30-min |
| Temporal | 1998-06 to present |
| Coverage | Global |
| Licence | CC BY 4.0 |
| Access | NASA earthaccess (Earthdata Login) |
| Fetchable by basinkit | **no** |
| Commercial use | yes |
| Redistribution | yes |

The Planetary Computer mirror is abandoned and returns zero items. Go through NASA.

### `persiann` -- PERSIANN-CDR v1r1

| | |
|---|---|
| Resolution | 0.25 degree, daily |
| Temporal | 1983-01-01 to present |
| Coverage | 60N-60S |
| Licence | No constraints on access or use |
| Access | NOAA NCEI ERDDAP griddap (server-side spatial and temporal subsetting) |
| Fetchable by basinkit | yes |
| Commercial use | yes |
| Redistribution | yes |

Underused: ERDDAP subsets server-side, so a 40-year basin series is one small request rather than a terabyte of tiles.

### `terraclimate` -- TerraClimate

| | |
|---|---|
| Resolution | 1/24 degree (~4 km), monthly |
| Temporal | 1958 to present |
| Coverage | Global land |
| Licence | CC0-1.0 |
| Access | climate.northwestknowledge.net (anonymous NetCDF) |
| Fetchable by basinkit | yes |
| Commercial use | yes |
| Redistribution | yes |

Carries q (runoff), aet, pet, def and soil moisture, so a first-order water balance needs no other source. CC0: the most permissive licence in the catalogue.


## Hydrography

### `hydroatlas` -- BasinATLAS / RiverATLAS v1.0

| | |
|---|---|
| Resolution | vector, 281 attributes |
| Temporal | static |
| Coverage | Global |
| Licence | CC BY 4.0 |
| Access | figshare article 9890531 (resolve file IDs via the anonymous API) |
| Fetchable by basinkit | yes |
| Commercial use | yes |
| Redistribution | yes |

281 pre-computed environmental attributes per basin. The fastest way to characterise a catchment without downloading a single raster.

### `hydrobasins` -- HydroBASINS v1c (Pfafstetter levels 1-12)

| | |
|---|---|
| Resolution | vector, level 12 median ~130 km2 |
| Temporal | static |
| Coverage | Global ex-Antarctica |
| Licence | CC BY 4.0 |
| Access | https://data.hydrosheds.org/file/hydrobasins/standard/ |
| Fetchable by basinkit | yes |
| Commercial use | yes |
| Redistribution | yes |

basinkit's default delineation backend: the NEXT_DOWN field makes upstream aggregation a graph traversal instead of a raster fill.

*Cite:* Lehner, B. & Grill, G. (2013). Hydrological Processes 27(15).

### `hydrolakes` -- HydroLAKES v1.0

| | |
|---|---|
| Resolution | 1.4M lakes >10 ha |
| Temporal | static |
| Coverage | Global |
| Licence | CC BY 4.0 |
| Access | https://data.hydrosheds.org/file/hydrolakes/ |
| Fetchable by basinkit | yes |
| Commercial use | yes |
| Redistribution | yes |

### `hydrorivers` -- HydroRIVERS v1.0

| | |
|---|---|
| Resolution | vector, 8.5M reaches |
| Temporal | static |
| Coverage | Global |
| Licence | CC BY 4.0 |
| Access | https://data.hydrosheds.org/file/hydrorivers/ |
| Fetchable by basinkit | yes |
| Commercial use | yes |
| Redistribution | yes |

Carries discharge and stream order attributes per reach.


## Hydrology

### `glofas` -- GloFAS v4 (CEMS-Floods) **documented only** **[account]**

| | |
|---|---|
| Resolution | 0.05 degree river network, daily |
| Temporal | 1979 to present |
| Coverage | 70N-70S |
| Licence | CEMS-Floods licence |
| Access | CEMS Early Warning Data Store (ewds.climate.copernicus.eu/api) |
| Fetchable by basinkit | **no** |
| Commercial use | yes |
| Redistribution | **no** |

Moved off the main CDS. Needs its own ECMWF token, separate from ERA5. Pre-migration code fails with 'dataset not found'.

### `grace` -- GRACE / GRACE-FO mascons RL06.3 **documented only** **[account]**

| | |
|---|---|
| Resolution | 0.5 degree grid (~300 km effective) |
| Temporal | 2002-04 to present |
| Coverage | Global |
| Licence | NASA public domain |
| Access | JPL PO.DAAC via earthaccess (Earthdata Login). The CSR anonymous mirror was unreachable when this was last checked. |
| Fetchable by basinkit | **no** |
| Commercial use | yes |
| Redistribution | yes |

Effective resolution is ~300 km, so it is meaningless below roughly 200,000 km2. Apply the provided scale factors and subtract the GIA correction or the storage anomalies will be wrong.

### `grdc` -- GRDC river discharge **documented only** **[gated]**

| | |
|---|---|
| Resolution | ~10,000 stations |
| Temporal | 1806 to present |
| Coverage | Global |
| Licence | GRDC terms: no commercial use, no redistribution at all |
| Access | Web portal order form only. No API exists. |
| Fetchable by basinkit | **no** |
| Commercial use | **no** |
| Redistribution | **no** |

The strictest licence here: you may not cache it, ship it, or put it in a demo notebook. basinkit will locate the nearest stations and hand you the order link, and will not touch the values.


## Imagery

### `hls` -- HLS v2.0 (HLSS30 / HLSL30)

| | |
|---|---|
| Resolution | 30 m harmonised |
| Temporal | 2013 to present (2020+ anonymously) |
| Coverage | Global land |
| Licence | NASA public domain |
| Access | Planetary Computer STAC for 2020+; NASA Earthdata login before that |
| Fetchable by basinkit | yes |
| Commercial use | yes |
| Redistribution | yes |

### `landsat` -- Landsat Collection 2 Level-2 (4/5/7/8/9)

| | |
|---|---|
| Resolution | 30 m |
| Temporal | 1982 to present |
| Coverage | Global |
| Licence | US public domain |
| Access | Planetary Computer STAC (anonymous SAS signing) |
| Fetchable by basinkit | yes |
| Commercial use | yes |
| Redistribution | yes |

Use Planetary Computer, not Earth Search: the latter points at the requester-pays usgs-landsat bucket, which silently costs money.

### `sentinel1_rtc` -- Sentinel-1 RTC

| | |
|---|---|
| Resolution | 10 m gamma-0 |
| Temporal | 2014-10-10 to present |
| Coverage | Global |
| Licence | CC BY 4.0 |
| Access | Planetary Computer STAC (anonymous SAS signing) |
| Fetchable by basinkit | yes |
| Commercial use | yes |
| Redistribution | yes |

Radiometrically terrain-corrected, so unlike plain GRD it is usable for flood mapping in relief. Cloud-independent inundation mapping with no account.

### `sentinel2` -- Sentinel-2 L2A

| | |
|---|---|
| Resolution | 10/20/60 m |
| Temporal | 2015-06-27 to present |
| Coverage | Global |
| Licence | Copernicus open (attribution) |
| Access | Earth Search v1 STAC -> s3://sentinel-cogs (fully anonymous COG) |
| Fetchable by basinkit | yes |
| Commercial use | yes |
| Redistribution | yes |

The cleanest optical route that exists: no token layer at all.


## Landcover

### `esri_lulc` -- ESRI / Impact Observatory 10 m Annual LULC

| | |
|---|---|
| Resolution | 10 m, 9 classes |
| Temporal | 2017-2024 |
| Coverage | Global |
| Licence | CC BY 4.0 |
| Access | Planetary Computer STAC io-lulc-annual-v02 |
| Fetchable by basinkit | yes |
| Commercial use | yes |
| Redistribution | yes |

The only anonymous annual land-cover time series. Use this, not WorldCover, when you need change over time.

### `worldcover` -- ESA WorldCover v100/v200

| | |
|---|---|
| Resolution | 10 m, 11 classes |
| Temporal | 2020 and 2021 epochs |
| Coverage | 60S-82.75N |
| Licence | CC BY 4.0 |
| Access | s3://esa-worldcover (anonymous COG, 3x3 degree tiles) |
| Fetchable by basinkit | yes |
| Commercial use | yes |
| Redistribution | yes |

v100 and v200 use different algorithms. ESA says explicitly they are not comparable for change detection, so basinkit refuses to difference them.


## Soil

### `soilgrids` -- SoilGrids 250 m v2.0

| | |
|---|---|
| Resolution | 250 m, 6 depths |
| Temporal | static |
| Coverage | Global |
| Licence | CC BY 4.0 |
| Access | ISRIC WCS (maps.isric.org) and REST point query |
| Fetchable by basinkit | yes |
| Commercial use | yes |
| Redistribution | yes |

Native CRS is Interrupted Goode Homolosine. basinkit reprojects the request bbox for you; hand-rolled WCS calls that skip this land in the wrong hemisphere. wv0033 and wv1500 are field capacity and wilting point.


## Terrain

### `cop30` -- Copernicus DEM GLO-30

| | |
|---|---|
| Resolution | 1 arc-sec (~30 m) |
| Temporal | 2011-2015 acquisition, 2021 product |
| Coverage | Global minus withheld tiles (e.g. Armenia/Azerbaijan) |
| Licence | Copernicus DEM free-and-open licence |
| Access | AWS Open Data s3://copernicus-dem-30m (anonymous COG) |
| Fetchable by basinkit | yes |
| Commercial use | yes |
| Redistribution | yes |

Not literally complete: a few national tiles are absent from the public bucket. basinkit falls back to GLO-90 and then the OpenTopography mirror for those, and records which source filled each tile.

*Cite:* European Space Agency (2021). Copernicus DEM GLO-30.

### `cop90` -- Copernicus DEM GLO-90

| | |
|---|---|
| Resolution | 3 arc-sec (~90 m) |
| Temporal | 2011-2015 |
| Coverage | Truly global |
| Licence | Copernicus DEM free-and-open licence |
| Access | AWS Open Data s3://copernicus-dem-90m (anonymous COG) |
| Fetchable by basinkit | yes |
| Commercial use | yes |
| Redistribution | yes |

Gap-filler for GLO-30 holes and the sane choice for basins >100,000 km2.

### `fabdem` -- FABDEM V1-2 **documented only** **[gated]**

| | |
|---|---|
| Resolution | 1 arc-sec, bare-earth |
| Temporal | 2023 |
| Coverage | 80N-60S |
| Licence | CC BY-NC-SA 4.0 |
| Access | University of Bristol data repository (manual) |
| Fetchable by basinkit | **no** |
| Commercial use | **no** |
| Redistribution | **no** |

LICENCE LANDMINE. Non-commercial AND ShareAlike: anything you derive from it inherits those terms. Opt-in only; basinkit prints the licence before the first byte is fetched.

### `merit_hydro` -- MERIT Hydro v1.0.1 **documented only** **[gated]**

| | |
|---|---|
| Resolution | 3 arc-sec (~90 m) |
| Temporal | 2019 |
| Coverage | 90N-60S |
| Licence | CC BY-NC 4.0 or ODbL 1.0 |
| Access | Google Form -> emailed password -> Dropbox (no API exists) |
| Fetchable by basinkit | **no** |
| Commercial use | **no** |
| Redistribution | **no** |

Hydrologically conditioned flow direction, HAND and upstream area, and the best product of its kind. But acquisition cannot be automated and both licence options poison a permissive package. Opt-in, bring your own copy.

### `nasadem` -- NASADEM HGT v001

| | |
|---|---|
| Resolution | 1 arc-sec (~30 m) |
| Temporal | Feb 2000 (reprocessed) |
| Coverage | 60N-56S |
| Licence | NASA public domain |
| Access | OpenTopography S3 mirror (anonymous) or Planetary Computer STAC |
| Fetchable by basinkit | yes |
| Commercial use | yes |
| Redistribution | yes |

Best SRTM-lineage DEM: void-filled with ASTER and ICESat, better geolocation.

### `srtm30` -- SRTM GL1 v003

| | |
|---|---|
| Resolution | 1 arc-sec (~30 m) |
| Temporal | Feb 2000 |
| Coverage | 60N-56S |
| Licence | NASA public domain |
| Access | OpenTopography S3 mirror (anonymous) |
| Fetchable by basinkit | yes |
| Commercial use | yes |
| Redistribution | yes |

Voids over water and steep terrain. Prefer NASADEM or COP30 unless you specifically need the original SRTM epoch.


## Water

### `jrc_gsw` -- JRC Global Surface Water v1.4

| | |
|---|---|
| Resolution | 30 m |
| Temporal | 1984-03 to 2021-12 |
| Coverage | 78N-56S |
| Licence | CC BY 4.0 |
| Access | storage.googleapis.com/global-surface-water (anonymous, 10x10 deg tiles) |
| Fetchable by basinkit | yes |
| Commercial use | yes |
| Redistribution | yes |

This is a pre-reduced 37-year Landsat water stack. It is what most people spend a week of Earth Engine compute recreating.

