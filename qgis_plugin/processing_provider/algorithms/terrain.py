"""Terrain surfaces derived from the basin's own elevation."""

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

#: (label, filename stem, needs routing) in the order shown in the dialog.
#: "Needs routing" marks the ones that route flow over the elevation model and
#: so cost far more than a local window operation.
SURFACES = [
    ("Slope (degrees)", "slope", False),
    ("Aspect (degrees from north)", "aspect", False),
    ("Hillshade", "hillshade", False),
    ("Profile curvature", "curvature", False),
    ("Topographic position index", "tpi", False),
    ("Terrain ruggedness index", "tri", False),
    ("Local relief (roughness)", "roughness", False),
    ("Slope position classes", "landform", False),
    ("Flow accumulation", "flow_accumulation", True),
    ("Channel network", "streams", True),
    ("Topographic wetness index", "twi", True),
    ("Height above nearest drainage", "hand", True),
]


class TerrainSurfacesAlgorithm(BasinkitAlgorithm):
    """Basin polygon in, a folder of terrain rasters out."""

    BASIN = "BASIN"
    SURFACES = "SURFACES"
    MIN_AREA_KM2 = "MIN_AREA_KM2"
    TPI_WINDOW = "TPI_WINDOW"
    MAX_MEGAPIXELS = "MAX_MEGAPIXELS"
    FOLDER = "FOLDER"

    def name(self) -> str:
        return "terrainsurfaces"

    def displayName(self) -> str:          # noqa: N802  (QGIS API name)
        return "Terrain surfaces"

    def shortDescription(self) -> str:     # noqa: N802  (QGIS API name)
        return "Slope, aspect, curvature, wetness and height above drainage."

    def shortHelpString(self) -> str:      # noqa: N802  (QGIS API name)
        return (
            "<p>Every surface here is computed from one elevation raster, "
            "downloaded once and clipped to the basin, so asking for ten of "
            "them costs one download rather than ten.</p>"
            "<p><b>Cell size is taken per row from that row's latitude.</b> A "
            "cell 0.001 degrees wide spans 111 m at the equator and 56 m at "
            "60 degrees north. Dividing by one assumed width reports a "
            "high-latitude basin as about twice as steep as it is, which is a "
            "mistake easy to make and hard to notice.</p>"
            "<p><b>Height above nearest drainage</b> is the drop from each "
            "cell to the channel it drains into, following the flow path "
            "rather than the straight line. It is the layer flood work "
            "actually wants: elevation alone says nothing about how far above "
            "the water a place sits.</p>"
            "<p>The last four surfaces route flow over the whole basin and "
            "take noticeably longer than the rest. Ground outside the polygon "
            "is treated as nodata rather than filled, so accumulation counts "
            "only cells inside this basin.</p>"
            "<p>Run <b>Elevation data suitability</b> on the same basin to see "
            "whether the elevation model can carry these numbers at all.</p>"
        )

    # -- parameters -------------------------------------------------------
    def initAlgorithm(self, config=None):  # noqa: N802  (QGIS API name)
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.BASIN, "River basin polygon", types=[SOURCE_POLYGON],
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.SURFACES, "Surfaces",
                options=[label for label, _, _ in SURFACES],
                allowMultiple=True, defaultValue=[0, 1, 2],
            )
        )

        drainage = QgsProcessingParameterNumber(
            self.MIN_AREA_KM2,
            "Channel starts where this much area drains to a cell (km2)",
            type=QgsProcessingParameterNumber.Type.Double,
            defaultValue=1.0, minValue=0.001,
        )
        drainage.setFlags(
            drainage.flags() | QgsProcessingParameterNumber.Flag.FlagAdvanced)
        self.addParameter(drainage)

        window = QgsProcessingParameterNumber(
            self.TPI_WINDOW, "Position index window (cells, odd)",
            type=QgsProcessingParameterNumber.Type.Integer,
            defaultValue=11, minValue=3, maxValue=101,
        )
        window.setFlags(window.flags() | QgsProcessingParameterNumber.Flag.FlagAdvanced)
        self.addParameter(window)

        budget = QgsProcessingParameterNumber(
            self.MAX_MEGAPIXELS, "Raster budget (megapixels)",
            type=QgsProcessingParameterNumber.Type.Integer,
            defaultValue=60, minValue=1, maxValue=4000,
        )
        budget.setFlags(budget.flags() | QgsProcessingParameterNumber.Flag.FlagAdvanced)
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

        chosen = self.parameterAsEnums(parameters, self.SURFACES, context)
        if not chosen:
            raise QgsProcessingException("Select at least one surface.")

        min_area = self.parameterAsDouble(parameters, self.MIN_AREA_KM2, context)
        window = self.parameterAsInt(parameters, self.TPI_WINDOW, context)
        if window % 2 == 0:
            window += 1
            feedback.pushInfo(f"Window rounded up to {window} cells, which has a centre.")
        budget = self.parameterAsInt(parameters, self.MAX_MEGAPIXELS, context) * 1_000_000
        folder = self.parameterAsString(parameters, self.FOLDER, context)
        os.makedirs(folder, exist_ok=True)

        basin = self.basin_from_layer(source, feedback)
        feedback.pushInfo(f"Basin area: {basin.area_km2:,.1f} km2")
        feedback.pushInfo("Fetching the elevation model once for every surface.")
        feedback.setProgress(5)
        self.check_cancelled(feedback)

        dem = basin.dem(max_pixels=budget, progress=False)
        feedback.pushInfo(f"Elevation raster: {dem.shape[-2]} x {dem.shape[-1]} cells")
        feedback.setProgress(20)

        from basinkit import terrain as tr

        makers = {
            "slope": lambda: tr.slope(dem),
            "aspect": lambda: tr.aspect(dem),
            "hillshade": lambda: tr.hillshade(dem),
            "curvature": lambda: tr.curvature(dem),
            "tpi": lambda: tr.tpi(dem, window=window),
            "tri": lambda: tr.tri(dem),
            "roughness": lambda: tr.roughness(dem),
            "landform": lambda: tr.landform(dem, window=window),
            "flow_accumulation": lambda: tr.flow_accumulation(dem),
            "streams": lambda: tr.streams(dem, min_area_km2=min_area),
            "twi": lambda: tr.twi(dem),
            "hand": lambda: tr.hand(dem, min_area_km2=min_area),
        }

        written, failed = [], []
        for step, index in enumerate(chosen, start=1):
            label, stem, routed = SURFACES[index]
            self.check_cancelled(feedback)
            feedback.pushInfo(
                f"{label}..." + (" (routing flow over the basin)" if routed else ""))
            try:
                array = makers[stem]()
                path = os.path.join(folder, f"{stem}.tif")
                self._write(array, path)
                written.append((path, label))
                self._load_on_completion(context, path, f"{label}")
            except Exception as exc:
                failed.append(label)
                feedback.reportError(f"{label} failed: {type(exc).__name__}: {exc}")
            feedback.setProgress(20 + 75 * step / len(chosen))

        if not written:
            raise QgsProcessingException(
                "No surface could be produced. The messages above say why for "
                "each one."
            )
        feedback.pushInfo(f"Wrote {len(written)} surfaces to {folder}")
        if failed:
            feedback.pushWarning(
                f"{len(failed)} did not: {', '.join(failed)}. The rest are "
                "unaffected -- each surface is computed on its own."
            )
        feedback.setProgress(100)
        return {self.FOLDER: folder, "SURFACES_WRITTEN": len(written),
                "SURFACES_FAILED": len(failed)}

    # -- helpers ----------------------------------------------------------
    @staticmethod
    def _write(array, path):
        import numpy as np

        if array.rio.nodata is None:
            array = array.rio.write_nodata(np.nan, encoded=False)
        array.rio.to_raster(path, compress="deflate", tiled=True)

    @staticmethod
    def _load_on_completion(context, path, label):
        """Queue the raster for the project; layers cannot be added from here.

        processAlgorithm runs on a worker thread, so Processing adds the layer
        on the main thread once the run finishes.
        """
        if context.project() is None:
            return
        details = QgsProcessingContext.LayerDetails(
            label, context.project(), label, QgsProcessingUtils.LayerHint.Raster)
        details.forceName = True
        if SUPPORTS_LAYER_GROUPING:
            details.groupName = "basinkit terrain"
        context.addLayerToLoadOnCompletion(path, details)
