# Verification

Every number on this page was produced by running the package, not by
inspecting it. The scripts are in `verify/`, and every figure below traces to a
single run of `verify/run_delineation.py` against basinkit 0.1.0 on
26 August 2026, not to a mixture of runs.

Prepared by Pradeepika Kaushik.

## Delineation against published gauge areas

Twelve reference gauges, one per major basin, on six continents. The published
areas come from operating agencies and GRDC station records, **not** from
HydroBASINS, so agreement is an external check rather than a tautology.

| basin | basinkit | published | error |
|---|---:|---:|---:|
| Danube @ Bratislava | 131,449 | 131,300 | 0.11% |
| Amazon @ Obidos | 4,671,504 | 4,680,000 | 0.18% |
| Godavari @ Polavaram | 306,750 | 307,800 | 0.34% |
| Mississippi @ Vicksburg | 2,979,823 | 2,964,000 | 0.53% |
| Rhine @ Lobith | 159,776 | 160,800 | 0.64% |
| Sapta Koshi @ Chatara | 54,497 | 54,100 | 0.73% |
| Mekong @ Pakse | 549,061 | 545,000 | 0.75% |
| Columbia @ The Dalles | 619,618 | 613,800 | 0.95% |
| Zambezi @ Victoria Falls | 519,436 | 507,000 | 2.45% |
| Parana @ Corrientes | 2,127,355 | 1,950,000 | 9.10% |
| Niger @ Lokoja | 1,747,192 | 2,074,000 | 15.76% |
| Murray @ Wentworth | 541,385 | 950,000 | 43.01% |

### The distribution, not the best basin

**n = 12.** Median error **0.74%**. Eight of twelve within 1%, nine within
3%. Excluding the three basins whose published figure includes large
non-contributing area (below), n = 9, median 0.64%, worst 2.45%.

Twelve is a small sample and these are large, well-mapped rivers; the gauges
were chosen because their areas are published, which biases toward basins that
have been studied. Quoting a single basin would make the package look four
times more accurate than it is; the Koshi alone reads 0.73%, and the best of the
twelve reads 0.11%. Neither is the number.

The Amazon result is still worth pausing on: 4.67 million km² across 35,625
sub-basins, delineated in 43 seconds, 0.18% from the published figure. That is
what graph traversal buys over raster fill.

### The Murray is not a failure

A 43% shortfall looks like a bug until you look at the water balance:

```
delineated area          541,385 km²
nominal published area   950,000 km²
mean annual rainfall         434 mm
mean annual runoff          27.5 mm
runoff coefficient           0.063
```

A runoff coefficient of 6% over half a million square kilometres is the
signature of a basin most of which does not drain to its own outlet. The
Murray-Darling has vast internally-draining western areas; the 950,000 km²
figure is the nominal basin, while HydroBASINS routes only what actually
reaches Wentworth. **basinkit's answer is the hydrologically contributing
area**, and for most modelling purposes that is the number you want. The
divergence is worth knowing about, not worth hiding.

The Niger and Paraná gaps have the same character on a smaller scale: both have
large arid or wetland zones whose contribution is intermittent.

## MERIT-Hydro: not a check, a migration path

This was presented as independent confirmation. It is better read as the
opposite.

| backend | base grid | source | Koshi |
|---|---|---|---:|
| `hydrobasins` *(default)* | 15 arc-sec, ~460 m | SRTM, February 2000 | 54,497 km² |
| `api` | 3 arc-sec, ~90 m | MERIT-Hydro, error-removed | 54,045 km² |
| `dem` | 1 arc-sec, ~30 m | Copernicus, 2011-2015 | - |

The two agree to **0.8%** with different source DEMs, different algorithms and
no shared code, which is real evidence that neither is badly wrong. But
agreement is not the interesting fact here. The default backend routes on a
quarter-century-old 460 m grid. MERIT-Hydro is five times finer and
hydrologically conditioned. A South Asian toolkit that runs at 90 m is a reason
to exist; one that agrees with the 450 m product is a validation exercise.

The obstacle is not technical: the 90 m path is already implemented as the
`api` backend. It is licensing: MERIT-Hydro is CC BY-NC 4.0 or ODbL, acquisition
cannot be automated, and the current route depends on one research group's
server. Making 90 m the *default* means solving distribution, not routing.

## Rainfall against published climatology

Sapta Koshi basin, 2010-2019:

| product | basin mean | published range |
|---|---:|---|
| CHIRPS v3.0 | 1,335 mm/yr | 1,200-1,500 mm/yr |
| TerraClimate | 1,002 mm/yr | - |

CHIRPS lands inside the published band. TerraClimate reads 25% lower, which is
a known characteristic rather than a defect: it is downscaled from coarse
reanalysis and systematically under-resolves orographic enhancement in high
mountains. **For a Himalayan or Andean basin, prefer CHIRPS.** TerraClimate's
value is its water balance terms, not its rainfall.

## Optical imagery end to end

Rur basin at Jülich (1,555 km²), Sentinel-2 median composite, July-August 2023:

| quantity | value | expected |
|---|---:|---|
| red reflectance (mean) | 0.047 | 0.03-0.08 for vegetated land |
| NIR reflectance (mean) | 0.290 | 0.25-0.40 |
| **NDVI (median)** | **0.82** | 0.6-0.85, temperate cropland and forest in July |
| finite fraction | 0.500 | bbox efficiency 0.509 |

Getting a correct NDVI requires the search, the nodata masking, the scale, the
offset, the solar-day grouping, the composite and the polygon clip all to be
right at once. It is the single most informative check in the suite.

Sentinel-1 RTC on the same basin returns a mean γ⁰ of **−9.3 dB**, within the
published −15 to −5 dB range for vegetated land.

## Clipping

The finite fraction of every clipped layer tracks `bbox_efficiency` to within a
couple of percent: Sentinel-2 0.500 against 0.509, Landsat 0.514, Sentinel-1
0.514, exported GeoTIFFs 0.602 against 0.601 on the Danube. That is the clip
doing exactly what it claims, measured rather than asserted.

## The catalogue audit

Rating the package honestly meant auditing what it claims against what it does.
Two things came out of that.

**Eight of twenty-six catalogued datasets had no fetcher.** The catalogue listed
them with resolution, licence and access route, and `grace` and `hydroatlas`
even showed `auth=none, commercial=yes`, so a reader would reasonably conclude
they could be downloaded. Fixed three ways: `hydroatlas` is now implemented,
`grace` was corrected to `auth=account` (the CSR anonymous mirror was
unreachable; the working route is JPL via Earthdata Login), and the remaining
six raise `NotImplementedSource` carrying the access route and licence.

```
>>> basinkit.catalog.require("glofas")
NotImplementedSource: GloFAS v4 (CEMS-Floods) is catalogued but basinkit
cannot fetch it yet.
    Access : CEMS Early Warning Data Store (ewds.climate.copernicus.eu/api)
    Licence: CEMS-Floods licence
    Auth   : account required
    Once you have it locally, pass the geometry to
    basinkit.clip.clip_raster() to cut it to the basin.
```

**Seven public methods had never been executed.** `plot()` was one of them, and
it crashed on NumPy 2.x: `ndarray.ptp()` was removed in NumPy 2.0 while
`pyproject` allows `numpy>=1.24`. `explore()` was another: leafmap simply was
not installed, so the interactive path had never run at all. Both now have
tests, and one of those tests scans the whole package for every NumPy-2-removed
API.

## BasinATLAS as an independent check

Implementing BasinATLAS produced an unplanned validation. It ships its own mean
elevation per basin, derived from a different DEM by a different group:

| quantity | BasinATLAS | basinkit (COP-DEM) |
|---|---:|---:|
| Koshi mean elevation | 3,782 m | 3,786 m |

**0.1% apart.** Its precipitation reads 851 mm/yr against CHIRPS's 1,335, the
same orographic under-resolution seen in TerraClimate, and for the same reason:
BasinATLAS's climate layers come from WorldClim, downscaled from coarse
gridded data.

## Defects this found

Verification is only worth doing if it changes the code. It changed twelve
things, and every one is now a regression test.

| what | how it showed up |
|---|---|
| **Outlet on a riverbank** | Rhine at Lobith returned 271 km² instead of 160,800. The point sits in a 270 km² bank unit; the main stem is 200 m away. Godavari at Polavaram, same story, 454 m. HydroBASINS' own `UP_AREA` agreed with the tiny answer, so every internal check still passed. Fixed by snapping when a nearby unit drains ≥10× more, with a warning. |
| **Sentinel-2 offset applied twice** | Earth Search pre-applies the baseline-04.00 BOA offset and flags it, while still publishing the nominal −0.1. Applying it again gave a **mean reflectance of −0.05** over a green catchment. |
| **Nodata averaged into composites** | Optical products encode "no observation" as 0. A basin straddles several MGRS tiles, so most scenes cover a fraction of it, and an unmasked Sentinel-2 median came back **87% zero**. |
| **Clip broken on every Dataset** | `Dataset` has no `.values` array; reaching for one picks up a method. The clip worked on every single-band raster and failed on every multi-band STAC result. |
| **Rasters exported without nodata** | Correctly masked in memory, then written to GeoTIFF with no declared nodata, so QGIS paints the outside solid black and rasterio returns no mask. The clip silently stopped existing the moment the file left Python. |
| **Nodata sentinel averaged in mosaics** | JRC surface water uses 255 without declaring it, so an averaging resample produced occurrence values of **101%**. |
| **`outlets="min"` in flow routing** | Routes a whole DEM window to its lowest cell. A river with 2,500 km² upstream came back with 0.2 km² at the same coordinate, purely because the window shifted. |
| **`Basin.plot()` broken on NumPy 2** | `ndarray.ptp()` was removed in NumPy 2.0; `pyproject` allows `numpy>=1.24`. Found only by auditing which methods no test had ever called. |
| **BasinATLAS extent code misread** | Extent is the first letter of a column's *third* token (`pre_mm_uyr` upstream, `run_mm_syr` sub-catchment), not a trailing suffix. Read as a suffix it matched nothing and `attributes()` returned an empty dict. |
| **BasinATLAS scaled integers** | Stored as integers to keep the tables compact. Read raw, the Koshi averages 50 °C and a 204° slope. |
| **The README's own example was wrong** | Found on release day by running it. `from_point(26.5, 85.2)`, advertised as "14,384 km²", sits 16 km off the Bagmati channel and returns 434 km². The delineation was correct and HydroBASINS' `UP_AREA` agreed with it to 0.2%; the *coordinate* was wrong and the printed figure had gone stale. The first code block a new user ran disagreed with its own output by a factor of thirty. Fixed by moving every documented example to the Chatara outlet the network suite verifies, adding an off-channel advisory warning, and pinning the documented coordinate to the tested one. |
| **ESRI land cover returned the wrong year** | Found while trying to build a year-by-year change animation. Every annual item ends at 00:00 on 1 January, so a naive year window matches the previous year's map at the boundary instant: asking for 2024 (the package default) returned the 2023 map. Nothing raised, and the array was entirely valid. Three more defects sat in the same code path: the WorldCover legend applied to ESRI codes (reporting cloud as forest), a Dataset returned where a DataArray was expected, and two tiles stacked on a time axis instead of mosaicked. |

Ten of the twelve produce answers that look entirely plausible: an empty
dict, a negative reflectance, a 271 km² Rhine. **Only two of the twelve raised an
exception**, and both were found by auditing which methods no test had ever
called, not by the suite. That is the argument for checking against published
values rather than snapshots: a snapshot test would have locked the other eight
in as the expected answer.

## Platform coverage

| | offline suite | notes |
|---|---|---|
| Python 3.10 | 31 passed, 2 skipped | skips are optional extras not in `[dev]` |
| Python 3.11 | 48 passed | full extras installed |
| Python 3.12 | 31 passed, 2 skipped | |
| Windows, macOS | **not run** | CI declares them; nobody has executed them |

Linux only so far. The CI matrix claims three operating systems and three
Python versions; two of the three Pythons are now real, the two other operating
systems are still a claim.
