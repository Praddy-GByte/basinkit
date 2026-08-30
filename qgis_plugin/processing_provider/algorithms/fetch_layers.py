"""Fetch open Earth observation layers for a basin, clipped to its polygon."""

from __future__ import annotations

import os

from qgis.core import (
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterNumber,
    QgsProcessingUtils,
)

from ...compat import SOURCE_POLYGON, SUPPORTS_LAYER_GROUPING
from .base import BasinkitAlgorithm

#: (label, filename stem, raster?) in the order shown in the dialog.
LAYERS = [
    ("Elevation (Copernicus GLO-30)", "dem", True),
    ("Land cover (ESA WorldCover 10 m)", "landcover", True),
    ("Soil clay content (SoilGrids)", "soil_clay", True),
    ("Available water capacity (SoilGrids)", "soil_awc", True),
    ("Surface water occurrence (JRC)", "surface_water", True),
    ("Rivers (HydroRIVERS)", "rivers", False),
    ("Lakes (HydroLAKES)", "lakes", False),
    ("Monthly rainfall, basin mean (CHIRPS)", "precipitation", None),
]


class FetchBasinLayersAlgorithm(BasinkitAlgorithm):
    """Basin polygon in, a folder of clipped layers out."""

    BASIN = "BASIN"
    LAYERS = "LAYERS"
    START_YEAR = "START_YEAR"
    END_YEAR = "END_YEAR"
    MAX_MEGAPIXELS = "MAX_MEGAPIXELS"
    FOLDER = "FOLDER"

    def name(self) -> str:
        return "fetchbasinlayers"

    def displayName(self) -> str:          # noqa: N802  (QGIS API name)
        return "Fetch basin data layers"

    def shortDescription(self) -> str:     # noqa: N802  (QGIS API name)
        return "Download open Earth observation layers clipped to a basin polygon."

    def shortHelpString(self) -> str:      # noqa: N802  (QGIS API name)
        return (
            "<p>Takes a basin polygon -- typically the output of "
            "<i>Delineate river basin</i> -- and downloads open data clipped "
            "and masked to it. Everything outside the polygon is nodata, not "
            "black, so the layers drop straight onto a map.</p>"
            "<p>No account is needed for any of these sources.</p>"
            "<p><b>Size.</b> A large basin at 10 m is billions of pixels, so "
            "requests are coarsened to fit the megapixel budget and the log "
            "reports the resolution actually used. Raise the budget if you "
            "have the memory, or work on a sub-basin to keep native "
            "resolution.</p>"
            "<p><b>Time.</b> The first run downloads; later runs read from the "
            "cache. Rainfall is fetched as a basin-mean monthly series and "
            "written as CSV.</p>"
        )

    # -- parameters -------------------------------------------------------
    def initAlgorithm(self, config=None):  # noqa: N802  (QGIS API name)
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.BASIN, "Basin polygon", types=[SOURCE_POLYGON]
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.LAYERS,
                "Layers to fetch",
                options=[label for label, _, _ in LAYERS],
                allowMultiple=True,
                defaultValue=[0, 1, 4, 5],
            )
        )

        start = QgsProcessingParameterNumber(
            self.START_YEAR, "Rainfall: first year",
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=2015, minValue=1981, maxValue=2100,
        )
        start.setFlags(start.flags() | QgsProcessingParameterNumber.FlagAdvanced)
        self.addParameter(start)

        end = QgsProcessingParameterNumber(
            self.END_YEAR, "Rainfall: last year",
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=2023, minValue=1981, maxValue=2100,
        )
        end.setFlags(end.flags() | QgsProcessingParameterNumber.FlagAdvanced)
        self.addParameter(end)

        budget = QgsProcessingParameterNumber(
            self.MAX_MEGAPIXELS, "Raster budget (megapixels)",
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=100, minValue=1, maxValue=4000,
        )
        budget.setFlags(budget.flags() | QgsProcessingParameterNumber.FlagAdvanced)
        self.addParameter(budget)

        self.addParameter(
            QgsProcessingParameterFolderDestination(self.FOLDER, "Output folder")
        )

    # -- run --------------------------------------------------------------
    def processAlgorithm(self, parameters, context, feedback):  # noqa: N802
        self.require_basinkit(feedback)

        source = self.parameterAsSource(parameters, self.BASIN, context)
        if source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.BASIN))

        chosen = self.parameterAsEnums(parameters, self.LAYERS, context)
        if not chosen:
            raise QgsProcessingException("Select at least one layer to fetch.")

        start = self.parameterAsInt(parameters, self.START_YEAR, context)
        end = self.parameterAsInt(parameters, self.END_YEAR, context)
        budget = self.parameterAsInt(parameters, self.MAX_MEGAPIXELS, context) * 1_000_000
        folder = self.parameterAsString(parameters, self.FOLDER, context)
        os.makedirs(folder, exist_ok=True)

        basin = self.basin_from_layer(source, feedback)
        feedback.pushInfo(
            f"Basin: {basin.area_km2:,.1f} km2, bounding-box efficiency "
            f"{basin.bbox_efficiency:.0%}"
        )

        jobs = self._build_jobs(basin, budget, start, end)
        written: dict[str, str] = {}
        failed: dict[str, str] = {}

        for index, position in enumerate(chosen):
            self.check_cancelled(feedback)
            label, stem, is_raster = LAYERS[position]
            feedback.pushInfo(f"--- {label}")
            feedback.setProgress(int(100 * index / max(len(chosen), 1)))

            try:
                path = jobs[stem](folder)
            except Exception as exc:
                failed[label] = f"{type(exc).__name__}: {exc}"
                feedback.reportError(f"    failed: {exc}", fatalError=False)
                continue

            if path is None:
                failed[label] = "nothing inside the basin"
                feedback.pushWarning("    nothing of this layer falls inside the basin")
                continue

            written[label] = path
            feedback.pushInfo(f"    written: {os.path.basename(path)}")
            if is_raster is not None:
                self._load_on_completion(context, path, label, is_raster)

        if not written:
            raise QgsProcessingException(
                "Nothing could be fetched.\n"
                + "\n".join(f"  {k}: {v}" for k, v in failed.items())
            )

        licences = os.path.join(folder, "LICENSES.txt")
        with open(licences, "w", encoding="utf-8") as handle:
            handle.write(basin.license_report())
        feedback.pushInfo(f"Licences and citations written to {licences}")

        feedback.setProgress(100)
        return {self.FOLDER: folder, "LAYERS_WRITTEN": len(written),
                "LAYERS_FAILED": len(failed)}

    # -- helpers ----------------------------------------------------------
    def _build_jobs(self, basin, budget, start, end):
        """One callable per layer, so a failure isolates to that layer."""

        def raster(getter, stem):
            def run(folder):
                array = getter()
                path = os.path.join(folder, f"{stem}.tif")
                import numpy as np

                if array.rio.nodata is None:
                    if np.issubdtype(array.dtype, np.floating):
                        array = array.rio.write_nodata(np.nan, encoded=False)
                    else:
                        array = array.rio.write_nodata(0, encoded=False)
                array.rio.to_raster(path, compress="deflate", tiled=True)
                return path
            return run

        def vector(getter, stem):
            def run(folder):
                frame = getter()
                if frame is None or len(frame) == 0:
                    return None
                path = os.path.join(folder, f"{stem}.gpkg")
                frame.to_file(path, driver="GPKG")
                return path
            return run

        def series(folder):
            table = basin.precipitation(start, end, progress=False)
            path = os.path.join(folder, "precipitation_chirps.csv")
            table.to_dataframe().to_csv(path)
            return path

        return {
            "dem": raster(
                lambda: basin.dem(max_pixels=budget, progress=False), "dem"),
            "landcover": raster(
                lambda: basin.landcover(max_pixels=budget, progress=False), "landcover"),
            "soil_clay": raster(
                lambda: basin.soil("clay"), "soil_clay_0-5cm"),
            "soil_awc": raster(
                lambda: basin.available_water_capacity(), "soil_awc_0-5cm"),
            "surface_water": raster(
                lambda: basin.surface_water(max_pixels=budget, progress=False),
                "surface_water_occurrence"),
            "rivers": vector(lambda: basin.rivers(progress=False), "rivers"),
            "lakes": vector(lambda: basin.lakes(progress=False), "lakes"),
            "precipitation": series,
        }

    @staticmethod
    def _load_on_completion(context, path, label, is_raster):
        """Queue the file to be added to the project after the run finishes.

        Layers must never be added from inside processAlgorithm -- it runs on a
        worker thread. Processing adds them on the main thread afterwards.
        """
        if context.project() is None:
            return                          # headless run: nothing to load into

        hint = (QgsProcessingUtils.LayerHint.Raster if is_raster
                else QgsProcessingUtils.LayerHint.Vector)
        details = QgsProcessingContext.LayerDetails(label, context.project(), label, hint)
        details.forceName = True
        if SUPPORTS_LAYER_GROUPING:
            details.groupName = "basinkit"
        context.addLayerToLoadOnCompletion(path, details)
