"""The Basin object: one outlet in, every open layer out."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import catalog
from .exceptions import LicenseError


class Basin:
    """An upstream river basin and everything open that can be clipped to it.

    Create one from an outlet coordinate and every layer method afterwards is
    masked to the polygon, not to its bounding box::

        import basinkit as bk

        basin = bk.Basin.from_point(26.87, 87.15)    # Sapta Koshi at Chatara
        basin.area_km2
        dem = basin.dem()                            # xarray, clipped + masked
        lc  = basin.landcover()
        rain = basin.precipitation(2000, 2024)       # basin-mean monthly series
        basin.download_all("koshi/")                 # the whole default stack

    Attributes
    ----------
    geometry : shapely geometry
        Basin polygon in EPSG:4326.
    provenance : dict
        Which backend and which dataset version produced the polygon. This
        travels with the basin so that a result is always attributable, and it
        is written into every export.
    """

    def __init__(self, geometry, provenance: dict | None = None) -> None:
        self.geometry = geometry
        self.provenance = provenance or {}
        self._cache: dict[str, Any] = {}

    # -- constructors ------------------------------------------------------
    @classmethod
    def from_point(
        cls, lat: float, lon: float, *, backend: str = "auto", **kwargs
    ) -> Basin:
        """Delineate the basin upstream of an outlet coordinate.

        Parameters
        ----------
        backend
            ``'auto'`` (default), ``'hydrobasins'``, ``'dem'`` or ``'api'``.
            See :mod:`basinkit.delineate` for what each one is good at.
        """
        from .delineate import delineate

        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError(
                f"({lat}, {lon}) is not a valid lat/lon. Note the order is "
                "(lat, lon) -- swapping them is the usual cause."
            )
        geom, prov = delineate(lat, lon, backend=backend, **kwargs)
        return cls(geom, prov)

    @classmethod
    def from_geometry(cls, geometry, provenance: dict | None = None) -> Basin:
        """Wrap a polygon you already have (a gauge basin, an official boundary)."""
        return cls(geometry, provenance or {"backend": "user-supplied"})

    @classmethod
    def from_file(cls, path: str | Path) -> Basin:
        """Load a basin from any vector file geopandas can read."""
        import geopandas as gpd

        gdf = gpd.read_file(path)
        if gdf.crs and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs("EPSG:4326")
        return cls(gdf.union_all(), {"backend": "file", "path": str(path)})

    # -- properties --------------------------------------------------------
    @property
    def area_km2(self) -> float:
        """Basin area via an equal-area projection centred on the basin itself."""
        if "area" not in self._cache:
            from .clip import basin_area_km2

            self._cache["area"] = basin_area_km2(self.geometry)
        return self._cache["area"]

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return self.geometry.bounds

    @property
    def centroid(self) -> tuple[float, float]:
        c = self.geometry.centroid
        return (c.y, c.x)

    @property
    def bbox_efficiency(self) -> float:
        """Basin area as a fraction of its bounding-box area.

        This is the number that justifies polygon clipping. A compact basin
        scores near 0.7; a long dendritic one can drop below 0.25, meaning a
        bbox-based download wastes three quarters of everything it transfers
        and biases every basin average with a neighbour's pixels.
        """
        from shapely.geometry import box

        from .clip import basin_area_km2

        return self.area_km2 / basin_area_km2(box(*self.geometry.bounds))

    def __repr__(self) -> str:
        backend = self.provenance.get("backend", "?")
        lat, lon = self.centroid
        return (
            f"<Basin area={self.area_km2:,.0f} km2 "
            f"centroid=({lat:.3f}, {lon:.3f}) backend={backend!r}>"
        )

    # -- layers ------------------------------------------------------------
    def dem(self, product: str = "cop30", **kwargs):
        """Elevation, clipped and masked to the basin."""
        from .sources.dem import dem

        return dem(self.geometry, product=product, **kwargs)

    def landcover(self, year: int | None = None, source: str = "worldcover",
                  **kwargs):
        """Land cover, as a 2-D array with its class legend in ``.attrs``.

        ``worldcover`` is ESA WorldCover at 10 m (2020 or 2021); ``esri`` is the
        ESRI / Impact Observatory annual series. Both return the same shape of
        object, and each carries its own legend -- the two number their classes
        differently, and code 10 is tree cover in one and cloud in the other.

        ``year=None`` means 2021 for WorldCover and the latest year published
        for this location for ESRI.
        """
        from .sources.landcover import esri_lulc, worldcover

        if source == "worldcover":
            return worldcover(self.geometry, year=year or 2021, **kwargs)
        if source == "esri":
            return esri_lulc(self.geometry, year=year, **kwargs)
        raise ValueError(f"Unknown land cover source {source!r}: use 'worldcover' or 'esri'.")

    def soil(self, prop: str = "clay", depth: str = "0-5cm", **kwargs):
        """A SoilGrids property. See :data:`basinkit.sources.soil.PROPERTIES`."""
        from .sources.soil import soilgrids

        return soilgrids(self.geometry, prop=prop, depth=depth, **kwargs)

    def available_water_capacity(self, depth: str = "0-5cm"):
        """Plant-available water capacity (field capacity minus wilting point)."""
        from .sources.soil import available_water_capacity

        return available_water_capacity(self.geometry, depth=depth)

    def precipitation(self, start=2000, end=None, source: str = "chirps", **kwargs):
        """Basin-mean rainfall time series. ``chirps``, ``persiann`` or ``terraclimate``."""
        from .sources.climate import chirps, persiann, terraclimate

        if source == "chirps":
            return chirps(self.geometry, start, end, **kwargs)
        if source == "persiann":
            return persiann(self.geometry, str(start), end, **kwargs)
        if source == "terraclimate":
            return terraclimate(self.geometry, ("ppt",), int(start), end, **kwargs)
        raise ValueError(
            f"Unknown precipitation source {source!r}: use 'chirps', 'persiann' "
            "or 'terraclimate'."
        )

    def water_balance(self, start: int = 2000, end: int | None = None):
        """Monthly P / AET / PET / Q / soil-moisture balance from TerraClimate."""
        from .sources.climate import water_balance

        return water_balance(self.geometry, start, end)

    def surface_water(self, layer: str = "occurrence", **kwargs):
        """JRC Global Surface Water: a pre-reduced 37-year Landsat water stack."""
        from .sources.water import global_surface_water

        return global_surface_water(self.geometry, layer=layer, **kwargs)

    def attributes(self, prefixes: tuple[str, ...] | None = None, **kwargs):
        """281 pre-computed BasinATLAS attributes for this basin.

        The row returned belongs to the outlet's HydroBASINS unit, and its
        ``_u`` columns are already aggregated over everything upstream -- so
        this characterises the whole catchment without touching a raster.

        Costs one 2.7 GB download the first time, then nothing.
        """
        from .sources.attributes import describe, hydroatlas

        hybas_id = self.provenance.get("outlet_hybas_id")
        if hybas_id is None:
            raise ValueError(
                "BasinATLAS is keyed by HydroBASINS id, which only the "
                "'hydrobasins' backend records. Re-delineate with "
                "backend='hydrobasins', or pass a geometry to "
                "basinkit.sources.attributes.hydroatlas() directly."
            )
        gdf = hydroatlas(hybas_id=hybas_id, prefixes=prefixes, **kwargs)
        return describe(gdf.iloc[0])

    def rivers(self, min_order: int = 0, **kwargs):
        """HydroRIVERS reaches inside the basin, with discharge and stream order."""
        from .sources.vectors import hydrorivers

        return hydrorivers(self.geometry, min_order=min_order, **kwargs)

    def lakes(self, min_area_km2: float = 0.0, **kwargs):
        """HydroLAKES water bodies inside the basin."""
        from .sources.vectors import hydrolakes

        return hydrolakes(self.geometry, min_area_km2=min_area_km2, **kwargs)

    def sentinel2(self, start: str, end: str, *, cloud_cover: float = 20,
                  bands: list[str] | None = None, composite: str | None = "median",
                  **kwargs):
        """Sentinel-2 L2A over the basin, cloud-filtered and optionally composited."""
        from .sources.stac import composite as reduce_time
        from .sources.stac import stac_search, stac_stack

        stack_kw = _stack_kwargs(kwargs)
        items = stac_search(
            "sentinel2", geometry=self.geometry, start=start, end=end,
            cloud_cover=cloud_cover, **kwargs
        )
        ds = stac_stack(items, self.geometry, bands=bands or ["blue", "green", "red", "nir"],
                        collection="sentinel2", **stack_kw)
        return reduce_time(ds, composite) if composite else ds

    def landsat(self, start: str, end: str, *, cloud_cover: float = 20,
                bands: list[str] | None = None, composite: str | None = "median",
                **kwargs):
        """Landsat Collection 2 Level-2 over the basin (1982 to present)."""
        from .sources.stac import composite as reduce_time
        from .sources.stac import stac_search, stac_stack

        stack_kw = _stack_kwargs(kwargs)
        items = stac_search(
            "landsat", geometry=self.geometry, start=start, end=end,
            cloud_cover=cloud_cover, **kwargs
        )
        ds = stac_stack(items, self.geometry, bands=bands or ["blue", "green", "red", "nir08"],
                        collection="landsat", **stack_kw)
        return reduce_time(ds, composite) if composite else ds

    def sentinel1(self, start: str, end: str, *, bands: list[str] | None = None,
                  composite: str | None = "median", **kwargs):
        """Sentinel-1 RTC: terrain-corrected radar, so it works through cloud."""
        from .sources.stac import composite as reduce_time
        from .sources.stac import stac_search, stac_stack

        stack_kw = _stack_kwargs(kwargs)
        items = stac_search(
            "sentinel1_rtc", geometry=self.geometry, start=start, end=end, **kwargs
        )
        ds = stac_stack(items, self.geometry, bands=bands or ["vv", "vh"],
                        collection="sentinel1_rtc", **stack_kw)
        return reduce_time(ds, composite) if composite else ds

    # -- summaries ---------------------------------------------------------
    # -- terrain surfaces -------------------------------------------------
    #
    # Each of these is computed from the elevation array, so passing ``dem=``
    # lets one download serve all of them.

    def slope(self, *, dem=None, degrees: bool = True, **kwargs):
        """Steepest descent at every cell, in degrees by default."""
        from .terrain import slope

        return slope(self.dem(**kwargs) if dem is None else dem, degrees=degrees)

    def aspect(self, *, dem=None, **kwargs):
        """Which way each slope faces, clockwise from north. Flat is NaN."""
        from .terrain import aspect

        return aspect(self.dem(**kwargs) if dem is None else dem)

    def hillshade(self, *, dem=None, azimuth: float = 315.0,
                  altitude: float = 45.0, z_factor: float = 1.0, **kwargs):
        """Shaded relief, 0 to 1, for a figure that reads as terrain."""
        from .terrain import hillshade

        return hillshade(self.dem(**kwargs) if dem is None else dem,
                         azimuth=azimuth, altitude=altitude, z_factor=z_factor)

    def curvature(self, *, dem=None, **kwargs):
        """Profile curvature: positive where the ground sheds, negative where
        it collects."""
        from .terrain import curvature

        return curvature(self.dem(**kwargs) if dem is None else dem)

    def flow_accumulation(self, *, dem=None, **kwargs):
        """Cells draining through each cell, routed over this basin's own DEM."""
        from .terrain import flow_accumulation

        return flow_accumulation(self.dem(**kwargs) if dem is None else dem)

    def twi(self, *, dem=None, **kwargs):
        """Topographic wetness index: where water gathers and ground saturates."""
        from .terrain import twi

        return twi(self.dem(**kwargs) if dem is None else dem)

    def hand(self, *, dem=None, min_area_km2: float = 1.0, **kwargs):
        """Height above the nearest drainage: the terrain layer flood work wants."""
        from .terrain import hand

        return hand(self.dem(**kwargs) if dem is None else dem,
                    min_area_km2=min_area_km2)

    def tpi(self, *, dem=None, window: int = 11, **kwargs):
        """Topographic position index: height above the surrounding ground."""
        from .terrain import tpi

        return tpi(self.dem(**kwargs) if dem is None else dem, window=window)

    def tri(self, *, dem=None, **kwargs):
        """Terrain ruggedness index: how far a cell sits from its neighbours."""
        from .terrain import tri

        return tri(self.dem(**kwargs) if dem is None else dem)

    def roughness(self, *, dem=None, **kwargs):
        """Local relief within each cell's 3x3 neighbourhood."""
        from .terrain import roughness

        return roughness(self.dem(**kwargs) if dem is None else dem)

    def landform(self, *, dem=None, window: int = 11, **kwargs):
        """Six slope-position classes: valley, slopes, flat, ridge."""
        from .terrain import landform

        return landform(self.dem(**kwargs) if dem is None else dem, window=window)

    def drainage_density(self, *, dem=None, thresholds=None,
                         chosen_km2=None, **kwargs):
        """Drainage density across the range of defensible thresholds.

        Not one number: the density moves by a large factor across channel
        initiation thresholds that are all defensible, so the curve and the
        threshold used are what make the figure comparable with anyone else's.
        """
        from .terrain import drainage_density

        return drainage_density(self.dem(**kwargs) if dem is None else dem,
                                thresholds=thresholds, chosen_km2=chosen_km2)

    def report(self, path, *, title=None, dem=None, rivers=None, **kwargs):
        """Write the eight-page PDF report for this basin.

        Cover with the elevation data suitability grade, elevation and
        hypsometry, slope and aspect, the shape of the ground, the channel
        network and Horton's laws, the morphometric table with symbols and
        references, what the answer rests on, and a methods page.
        """
        from .report import report

        return report(self, path, title=title,
                      dem=self.dem(**kwargs) if dem is None else dem,
                      rivers=rivers)

    def dem_suitability(self, *, dem=None, support_map: bool = False, **kwargs):
        """Whether the elevation model supports terrain analysis in this basin.

        Five measured tests -- depression filling, the slope noise floor,
        relief against the model's vertical error, level water surfaces and
        missing coverage -- combined into ``HIGH``, ``MODERATE`` or
        ``LIMITED``. It grades the terrain products, not the basin boundary.
        """
        from .suitability import suitability

        return suitability(self, dem=self.dem(**kwargs) if dem is None else dem,
                           support_map=support_map)

    def streams(self, *, dem=None, min_area_km2: float = 1.0, **kwargs):
        """The channel network routed from this basin's own elevation."""
        from .terrain import streams

        return streams(self.dem(**kwargs) if dem is None else dem,
                       min_area_km2=min_area_km2)

    def zonal(self, values, zones=None, *, bins=None, labels=None, **kwargs):
        """Summarise one layer inside the classes of another.

        ``basin.zonal(basin.precipitation_grid, basin.landcover())`` answers
        how much rain falls on each land-cover class; passing ``bins`` cuts a
        continuous layer such as elevation into bands instead. Area is summed
        from the true size of every cell, so a basin spanning several degrees
        of latitude is not weighted towards its southern edge.
        """
        from .zonal import zonal

        if zones is None:
            zones = self.landcover(**kwargs)
        return zonal(values, zones, labels=labels, bins=bins)

    def landcover_change(self, start: int, end: int, *, source: str = "esri",
                         **kwargs):
        """What became what, between two years, in square kilometres.

        Only the ESRI annual series carries a year for every year, so that is
        the default here even though ``landcover()`` defaults to WorldCover.
        The diagonal is the ground that did not change; everything off it is a
        transition, and the table is the honest form of a deforestation or
        urban-growth figure because it shows what the loss became.
        """
        import numpy as np
        import pandas as pd

        from .sources.landcover import _declared_classes
        from .terrain import cell_area_km2

        first = self.landcover(year=start, source=source, **kwargs)
        second = self.landcover(year=end, source=source, **kwargs)
        if first.shape != second.shape:
            second = second.rio.reproject_match(first)

        legend = _declared_classes(first) or {}
        a = np.asarray(first.values, dtype="float64")
        b = np.asarray(second.values, dtype="float64")
        areas = cell_area_km2(first)
        usable = np.isfinite(a) & np.isfinite(b) & (a > 0) & (b > 0)

        rows = []
        for code_from in np.unique(a[usable]):
            for code_to in np.unique(b[usable]):
                picked = usable & (a == code_from) & (b == code_to)
                if not picked.any():
                    continue
                rows.append({
                    "from": legend.get(int(code_from), int(code_from)),
                    "to": legend.get(int(code_to), int(code_to)),
                    "area_km2": round(float(areas[picked].sum()), 3),
                    "changed": bool(code_from != code_to),
                })
        frame = pd.DataFrame(rows).sort_values("area_km2", ascending=False)
        frame.attrs["years"] = (start, end)
        return frame.reset_index(drop=True)

    def precipitation_trend(self, *, start: int = 1985, end: int | None = None,
                            alpha: float = 0.05, **kwargs):
        """Is rainfall over this basin trending, and by how much a year."""
        from .climate import trend

        series = self.precipitation(start=start, end=end, **kwargs)
        s = series.to_series() if hasattr(series, "to_series") else series
        yearly = s.groupby(s.index.year).sum()
        yearly.index = __import__("pandas").to_datetime(
            [f"{int(y)}-01-01" for y in yearly.index]
        )
        return trend(yearly, alpha=alpha)

    def spi(self, *, scale: int = 3, start: int = 1985, end: int | None = None,
            **kwargs):
        """Standardized Precipitation Index over this basin, month by month."""
        from .climate import spi

        series = self.precipitation(start=start, end=end, **kwargs)
        s = series.to_series() if hasattr(series, "to_series") else series
        return spi(s, scale=scale)

    def subbasins(self, **kwargs):
        """The sub-catchments this basin is assembled from, with their routing.

        ``delineate`` dissolves the HydroBASINS units it walked into a single
        polygon. This hands back the pieces instead, each with ``NEXT_DOWN``,
        which is the routing graph itself: every distributed model wants
        sub-catchments and the links between them, and nothing here has to be
        inferred from geometry afterwards.

        Available for the ``hydrobasins`` backend, which is the default.
        """
        from .delineate.hydrobasins import upstream_units

        prov = self.provenance
        if prov.get("backend") != "hydrobasins":
            raise ValueError(
                "subbasins() reads the units the HydroBASINS traversal walked, "
                f"and this basin came from the {prov.get('backend', 'unknown')!r} "
                "backend. Delineate with backend='hydrobasins' to get them."
            )
        return upstream_units(
            prov["region"], prov["outlet_hybas_id"], prov.get("level", 12), **kwargs
        )

    def terrain_stats(self) -> dict:
        """Elevation, relief and mean slope: the standard morphometry."""
        import numpy as np

        elev = self.dem()
        vals = np.asarray(elev.values, dtype="float64")
        vals = vals[np.isfinite(vals)]
        if vals.size == 0:
            return {}

        # Slope comes from the same routine the slope map uses, which keeps
        # nodata as nodata. Filling the space around the polygon with zeros
        # before differencing puts a plain around the basin and a cliff at its
        # edge, and the mean then answers to those instead: on the Helmand
        # above the Kajaki Dam, which fills 43% of its bounding box, it read 7
        # degrees where the basin's own slopes average 16. That is the
        # bounding-box mistake this package exists to avoid, made against
        # itself.
        from .terrain import slope as _slope_of

        slope = np.asarray(_slope_of(elev).values, dtype="float64")
        finite_slope = slope[np.isfinite(slope)]

        return {
            "area_km2": round(self.area_km2, 2),
            "elev_min_m": round(float(vals.min()), 1),
            "elev_max_m": round(float(vals.max()), 1),
            "elev_mean_m": round(float(vals.mean()), 1),
            "relief_m": round(float(vals.max() - vals.min()), 1),
            "slope_mean_deg": (round(float(finite_slope.mean()), 2)
                               if finite_slope.size else None),
            "bbox_efficiency": round(self.bbox_efficiency, 3),
        }

    def morphometry(self, **kwargs) -> dict:
        """The classical Horton-Strahler-Schumm morphometric parameters.

            m = basin.morphometry()
            m["areal"]["drainage_density_km_per_km2"]
            m["network"]        # one row per Strahler order

        Counts Strahler *streams*, not the reaches a river dataset splits them
        into, and measures area, perimeter and every length in one equal-area
        projection. Both matter: on the Koshi, counting reaches turns the
        bifurcation ratios into values that are not physically possible.

        See :mod:`basinkit.morphometry` for what each parameter is and for what
        the numbers can and cannot be compared against.
        """
        from .morphometry import morphometry

        return morphometry(self, **kwargs)

    def summary(self, *, terrain: bool = True, landcover: bool = True) -> dict:
        """A one-call characterisation of the basin."""
        out: dict[str, Any] = {
            "area_km2": round(self.area_km2, 2),
            "centroid_lat_lon": [round(v, 5) for v in self.centroid],
            "bounds": [round(v, 5) for v in self.bounds],
            "bbox_efficiency": round(self.bbox_efficiency, 3),
            "provenance": self.provenance,
        }
        if terrain:
            try:
                out["terrain"] = self.terrain_stats()
            except Exception as exc:
                out["terrain"] = {"error": str(exc)}
        if landcover:
            try:
                from .sources.landcover import class_fractions

                out["landcover_fractions"] = class_fractions(self.landcover())
            except Exception as exc:
                out["landcover_fractions"] = {"error": str(exc)}
        return out

    # -- licensing ---------------------------------------------------------
    def license_report(self, layers: tuple[str, ...] | None = None) -> str:
        """Attribution and licence text for the layers you used.

        Print this into your methods section. Every layer basinkit fetches by
        default is CC BY 4.0 or more permissive, which means it can be
        redistributed and used commercially -- but only if it is attributed.
        """
        keys = layers or catalog.DEFAULT_STACK
        lines = ["Data sources and licences", "=" * 26, ""]
        for key in keys:
            try:
                ds = catalog.get(key)
            except KeyError:
                continue
            lines.append(f"{ds.name}")
            lines.append(f"    Licence : {ds.license}")
            lines.append(f"    Access  : {ds.route}")
            if ds.citation:
                lines.append(f"    Cite    : {ds.citation}")
            if not ds.commercial_ok:
                lines.append("    WARNING : commercial use not permitted")
            if not ds.redistributable:
                lines.append("    WARNING : redistribution not permitted")
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def check_license(key: str, *, commercial: bool = False,
                      redistribute: bool = False) -> None:
        """Raise if a dataset's licence forbids the intended use."""
        ds = catalog.get(key)
        if commercial and not ds.commercial_ok:
            raise LicenseError(
                f"{ds.name} is licensed {ds.license}, which forbids commercial use. "
                f"{ds.notes}"
            )
        if redistribute and not ds.redistributable:
            raise LicenseError(
                f"{ds.name} may not be redistributed under {ds.license}. {ds.notes}"
            )

    # -- export ------------------------------------------------------------
    def to_geojson(self, path: str | Path | None = None) -> str:
        import geopandas as gpd

        gdf = gpd.GeoDataFrame(
            {"area_km2": [self.area_km2],
             "backend": [self.provenance.get("backend", "")],
             "source": [self.provenance.get("source_dataset", "")]},
            geometry=[self.geometry], crs="EPSG:4326",
        )
        if path:
            gdf.to_file(path, driver="GeoJSON")
            return str(path)
        return gdf.to_json()

    def download_all(
        self,
        outdir: str | Path,
        layers: tuple[str, ...] = ("dem", "landcover", "soil", "surface_water",
                                   "precipitation", "rivers"),
        *,
        start: int = 2000,
        end: int | None = None,
        progress: bool = True,
    ) -> dict:
        """Fetch the default stack and write it to ``outdir``.

        This is the "give me everything" button. Each layer is attempted
        independently, so one failing source (a polar basin with no CHIRPS, say)
        does not abort the rest -- failures are recorded in the manifest
        alongside the successes.
        """
        outdir = Path(outdir)
        outdir.mkdir(parents=True, exist_ok=True)

        manifest: dict[str, Any] = {
            "basin": {
                "area_km2": round(self.area_km2, 2),
                "bounds": list(self.bounds),
                "centroid_lat_lon": list(self.centroid),
            },
            "provenance": self.provenance,
            "layers": {},
            "failed": {},
        }

        self.to_geojson(outdir / "basin.geojson")
        manifest["layers"]["basin"] = "basin.geojson"

        def _write_raster(da, name: str) -> str:
            fp = outdir / f"{name}.tif"
            # Declare nodata in the file header. The array is already masked
            # outside the basin, but without a declared nodata value QGIS and
            # ArcGIS paint that area solid black instead of transparent, and
            # rasterio's masked read returns no mask at all -- so a correctly
            # clipped raster looks and behaves like an unclipped one the moment
            # it leaves Python.
            import numpy as np

            if da.rio.nodata is None:
                if np.issubdtype(da.dtype, np.floating):
                    da = da.rio.write_nodata(np.nan, encoded=False)
                else:
                    da = da.rio.write_nodata(0, encoded=False)
            da.rio.to_raster(fp, compress="deflate", tiled=True)
            return fp.name

        jobs = {
            "dem": lambda: _write_raster(self.dem(progress=progress), "dem"),
            "landcover": lambda: _write_raster(
                self.landcover(progress=progress), "landcover"
            ),
            "soil": lambda: _write_raster(self.soil("clay"), "soil_clay_0-5cm"),
            "surface_water": lambda: _write_raster(
                self.surface_water(progress=progress), "surface_water_occurrence"
            ),
            "precipitation": lambda: self._write_series(
                self.precipitation(start, end), outdir, "precipitation_chirps"
            ),
            "rivers": lambda: self._write_vector(
                self.rivers(progress=progress), outdir, "rivers"
            ),
            "lakes": lambda: self._write_vector(
                self.lakes(progress=progress), outdir, "lakes"
            ),
        }

        for name in layers:
            if name not in jobs:
                manifest["failed"][name] = f"unknown layer {name!r}"
                continue
            try:
                manifest["layers"][name] = jobs[name]()
            except Exception as exc:
                manifest["failed"][name] = f"{type(exc).__name__}: {exc}"

        (outdir / "LICENSES.txt").write_text(self.license_report())
        manifest["layers"]["licenses"] = "LICENSES.txt"
        (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
        return manifest

    @staticmethod
    def _write_series(da, outdir: Path, name: str) -> str:
        fp = outdir / f"{name}.csv"
        da.to_dataframe().to_csv(fp)
        return fp.name

    @staticmethod
    def _write_vector(gdf, outdir: Path, name: str) -> str:
        fp = outdir / f"{name}.gpkg"
        if len(gdf) == 0:
            return f"{name}: none within basin"
        gdf.to_file(fp, driver="GPKG")
        return fp.name

    # -- viz ---------------------------------------------------------------
    def export_3d(self, path: str | Path, **kwargs):
        """Write an interactive 3D page for this basin: terrain, imagery, rivers.

        One self-contained HTML file with everything embedded, so it opens with
        no network. See :func:`basinkit.viz3d.export_3d` for the options.

            basin.export_3d("koshi.html")
            basin.export_3d("koshi.html", texture=None)   # elevation only, small

        This is a way of looking at the layers this package fetches. It makes no
        claim the other methods do not already make.
        """
        from .viz3d import export_3d

        return export_3d(self, path, **kwargs)

    def explore(self, **kwargs):
        """Interactive map of the basin. Needs ``pip install 'basinkit[viz]'``."""
        from .viz import explore

        return explore(self, **kwargs)

    def plot(self, **kwargs):
        """Static matplotlib figure: hypsometry, boundary and river network."""
        from .viz import plot

        return plot(self, **kwargs)


#: Options that shape the raster rather than the search. The pixel-budget
#: warning tells people to pass ``max_pixels=`` or ``resolution=``; before these
#: were routed to the stacking step, doing what it said raised a TypeError.
_STACK_OPTIONS = ("max_pixels", "resolution", "crs", "chunks", "clip", "nodata",
                  "mask_nodata", "scale")


def _stack_kwargs(kwargs: dict) -> dict:
    return {k: kwargs.pop(k) for k in _STACK_OPTIONS if k in kwargs}
