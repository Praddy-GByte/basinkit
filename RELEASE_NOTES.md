First release.

**What it does.** Give it a coordinate anywhere on Earth. It delineates the
upstream basin and returns open Earth observation layers clipped and masked to
that polygon, not to its bounding box, and without an account anywhere in the
chain.

```python
import basinkit as bk

basin = bk.Basin.from_point(26.87, 87.15)   # Sapta Koshi at Chatara
basin.area_km2                               # 54,497
basin.dem(); basin.landcover(); basin.precipitation(2010, 2023)
basin.download_all("koshi/")
```

**Delineation.** Three global backends: HydroBASINS graph traversal (default,
15 arc-sec base), MERIT-Hydro via a public service (3 arc-sec), and D8 routing
on Copernicus DEM (1 arc-sec). Validated blind against agency-published
catchment areas at 2,550 gauges in 99 countries on six continents, and the
accuracy is reported by catchment size because it varies by three orders of
magnitude across that range: 0.3% median error above 100,000 km2, 181% below
100 km2. The default backend walks sub-basins of about 130 km2, so it cannot
resolve anything smaller, and it now says so instead of returning a confident
number.

**Data.** Nineteen datasets fetchable today, every one of them anonymous:
Copernicus DEM, NASADEM, SRTM, HydroBASINS/RIVERS/LAKES/ATLAS, ESA WorldCover,
ESRI annual LULC, SoilGrids, CHIRPS, PERSIANN-CDR, TerraClimate, JRC Global
Surface Water, Sentinel-2, Sentinel-1 RTC, Landsat Collection 2, HLS. Seven more
are catalogued but not fetchable and say so rather than pretending.

**Licensing is code, not documentation.** One machine-readable table drives the
fetchers, the CLI and `Basin.license_report()`, so the licence shown is the
licence that applied.

**QGIS.** A Processing provider ships in `qgis_plugin/`: delineate from a canvas
click, fetch layers clipped to the basin, basin statistics.

**Testing.** 73 offline and 17 live tests, across three operating systems and
Python 3.10 to 3.13. Eleven defects were found during verification and are all
listed openly. Nine of them produced answers that looked entirely reasonable,
which is the argument for checking against published values rather than
snapshots. The last one was the README's own example, caught on release day.

Full validation write-up: `docs/verification.md`.
