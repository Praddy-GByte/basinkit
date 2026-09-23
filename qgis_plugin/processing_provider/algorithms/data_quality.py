"""A quality indicator for every layer, not only for the elevation model."""

from __future__ import annotations

import os

from qgis.core import (
    QgsProcessingException,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterNumber,
)

from ...compat import SOURCE_POLYGON
from .base import BasinkitAlgorithm

LAYER_NAMES = ("elevation", "landcover", "soil", "precipitation", "surface_water", "delineation")


class DataQualityAlgorithm(BasinkitAlgorithm):
    """Basin polygon in, one graded line per layer out."""

    BASIN = "BASIN"
    LAYERS = "LAYERS"
    YEAR = "YEAR"
    FOLDER = "FOLDER"

    def name(self) -> str:
        return "dataquality"

    def displayName(self) -> str:          # noqa: N802  (QGIS API name)
        return "Data quality report"

    def shortDescription(self) -> str:     # noqa: N802  (QGIS API name)
        return "Grade every layer against something produced independently of it."

    def shortHelpString(self) -> str:      # noqa: N802  (QGIS API name)
        return (
            "<p>The elevation suitability grade answers one question. This "
            "answers it for the rest of the stack, by measuring each layer "
            "against something that was not made from it:</p>"
            "<ul>"
            "<li><b>elevation</b> -- the suitability grade, and the same "
            "noise-floor measurement split by terrain class, so a basin that "
            "is part plain and part mountain is not reported as one number</li>"
            "<li><b>land cover</b> -- ESA WorldCover against the ESRI annual "
            "map for the same year, over the classes both of them define</li>"
            "<li><b>soil</b> -- the width of SoilGrids' own 5th to 95th "
            "percentile range, reported and not graded, because that range is "
            "wide everywhere and a threshold would be invented</li>"
            "<li><b>precipitation</b> -- CHIRPS against TerraClimate, year by "
            "year: their correlation and the difference between their means</li>"
            "<li><b>surface water</b> -- permanent against seasonal water, "
            "reported and not graded, because the JRC record carries no "
            "per-pixel confidence</li>"
            "<li><b>delineation</b> -- the river-network check and the "
            "accuracy regime for a basin of this size</li>"
            "</ul>"
            "<p>Every threshold is a choice and is written into the output "
            "beside the measurement it judged.</p>"
        )

    # -- parameters -------------------------------------------------------
    def initAlgorithm(self, config=None):  # noqa: N802  (QGIS API name)
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.BASIN, "River basin polygon", types=[SOURCE_POLYGON])
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.LAYERS, "Layers to check", options=list(LAYER_NAMES),
                allowMultiple=True, defaultValue=list(range(len(LAYER_NAMES))))
        )
        year = QgsProcessingParameterNumber(
            self.YEAR, "Year for the land cover comparison",
            type=QgsProcessingParameterNumber.Type.Integer,
            defaultValue=2021, minValue=2017, maxValue=2030)
        year.setFlags(year.flags() | QgsProcessingParameterNumber.Flag.FlagAdvanced)
        self.addParameter(year)
        self.addParameter(
            QgsProcessingParameterFolderDestination(self.FOLDER, "Output folder")
        )

    # -- run --------------------------------------------------------------
    def processAlgorithm(self, parameters, context, feedback):  # noqa: N802
        self.require_basinkit(feedback)

        source = self.parameterAsSource(parameters, self.BASIN, context)
        if source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.BASIN))

        picked = self.parameterAsEnums(parameters, self.LAYERS, context)
        layers = tuple(LAYER_NAMES[i] for i in picked) or LAYER_NAMES
        year = self.parameterAsInt(parameters, self.YEAR, context)
        folder = self.parameterAsString(parameters, self.FOLDER, context)
        os.makedirs(folder, exist_ok=True)

        basin = self.basin_from_layer(source, feedback)
        feedback.pushInfo(f"Basin area: {basin.area_km2:,.1f} km2")
        feedback.pushInfo(f"Checking: {', '.join(layers)}")
        self.check_cancelled(feedback)

        from basinkit.quality import data_quality

        result = data_quality(basin, layers=layers, year=year, progress=False)
        feedback.setProgress(85)

        feedback.pushInfo("")
        feedback.pushInfo(f"DATA QUALITY: {result['overall']}")
        feedback.pushInfo("")
        feedback.pushInfo(f"{'layer':<16}{'grade':<12}{'measured':>12}   indicator")
        for row in result["layers"]:
            value = row.get("value")
            feedback.pushInfo(
                f"{row['layer']:<16}{str(row.get('grade') or 'not graded'):<12}"
                f"{'-' if value is None else f'{value:.3f}' if isinstance(value, float) else value:>12}"
                f"   {row.get('indicator') or ''}")
        feedback.pushInfo("")
        for row in result["layers"]:
            if row.get("error"):
                feedback.pushWarning(f"[{row['layer']}] {row['error']}")
            elif row.get("grade") in ("MODERATE", "LIMITED"):
                feedback.pushWarning(f"[{row['layer']}] {row['statement']}")
            else:
                feedback.pushInfo(f"[{row['layer']}] {row['statement']}")

        rows = ["layer,grade,value,indicator,source,statement"]
        for row in result["layers"]:
            statement = '"' + str(row.get("statement", "")).replace('"', "'") + '"'
            rows.append(
                f"{row['layer']},{row.get('grade') or 'not graded'},{row.get('value')},"
                f"\"{row.get('indicator') or ''}\",\"{row.get('source', '')}\",{statement}")
        rows.append("")
        rows.append(f"overall,{result['overall']},,,,\"{result['note']}\"")
        csv_path = os.path.join(folder, "data_quality.csv")
        with open(csv_path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(rows) + "\n")
        feedback.pushInfo(f"Written to {csv_path}")
        feedback.setProgress(100)
        return {self.FOLDER: folder, "OVERALL": result["overall"], "CSV": csv_path}
