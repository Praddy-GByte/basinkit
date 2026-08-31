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

        items = stac_search(
            "sentinel2", geometry=self.geometry, start=start, end=end,
            cloud_cover=cloud_cover, **kwargs
        )
        ds = stac_stack(items, self.geometry, bands=bands or ["blue", "green", "red", "nir"],
                        collection="sentinel2")
        return reduce_time(ds, composite) if composite else ds

    def landsat(self, start: str, end: str, *, cloud_cover: float = 20,
                bands: list[str] | None = None, composite: str | None = "median",
                **kwargs):
        """Landsat Collection 2 Level-2 over the basin (1982 to present)."""
        from .sources.stac import composite as reduce_time
        from .sources.stac import stac_search, stac_stack

        items = stac_search(
            "landsat", geometry=self.geometry, start=start, end=end,
            cloud_cover=cloud_cover, **kwargs
        )
        ds = stac_stack(items, self.geometry, bands=bands or ["blue", "green", "red", "nir08"],
                        collection="landsat")
        return reduce_time(ds, composite) if composite else ds

    def sentinel1(self, start: str, end: str, *, bands: list[str] | None = None,
                  composite: str | None = "median", **kwargs):
        """Sentinel-1 RTC: terrain-corrected radar, so it works through cloud."""
        from .sources.stac import composite as reduce_time
        from .sources.stac import stac_search, stac_stack

        items = stac_search(
            "sentinel1_rtc", geometry=self.geometry, start=start, end=end, **kwargs
        )
        ds = stac_stack(items, self.geometry, bands=bands or ["vv", "vh"],
                        collection="sentinel1_rtc")
        return reduce_time(ds, composite) if composite else ds

    # -- summaries ---------------------------------------------------------
    def terrain_stats(self) -> dict:
        """Elevation, relief and mean slope: the standard morphometry."""
        import numpy as np

        elev = self.dem()
        vals = np.asarray(elev.values, dtype="float64")
        vals = vals[np.isfinite(vals)]
        if vals.size == 0:
            return {}

        res = abs(float(elev.rio.resolution()[0]))
        lat = self.centroid[0]
        cell_m = res * 111_320 * np.cos(np.deg2rad(lat))
        gy, gx = np.gradient(np.nan_to_num(np.asarray(elev.values, dtype="float64")))
        slope = np.degrees(np.arctan(np.hypot(gx, gy) / max(cell_m, 1e-6)))

        return {
            "area_km2": round(self.area_km2, 2),
            "elev_min_m": round(float(vals.min()), 1),
            "elev_max_m": round(float(vals.max()), 1),
            "elev_mean_m": round(float(vals.mean()), 1),
            "relief_m": round(float(vals.max() - vals.min()), 1),
            "slope_mean_deg": round(float(np.nanmean(slope)), 2),
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
