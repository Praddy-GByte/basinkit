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
on Copernicus DEM (1 arc-sec). Validated against published gauge areas on six
continents: n = 12, median error 0.74%, eight within 1%. The three basins that
diverge by more than 3% do so because their published figure includes large
non-contributing area, and the write-up says so.

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
