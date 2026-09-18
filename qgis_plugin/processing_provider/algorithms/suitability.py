"""Whether the elevation model supports the terrain analysis asked of it."""

from __future__ import annotations

import os

from qgis.core import (
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterNumber,
    QgsProcessingUtils,
)

from ...compat import SOURCE_POLYGON, SUPPORTS_LAYER_GROUPING
from .base import BasinkitAlgorithm


class DemSuitabilityAlgorithm(BasinkitAlgorithm):
    """Basin polygon in, a grade and the measurements behind it out."""

    BASIN = "BASIN"
    SUPPORT_MAP = "SUPPORT_MAP"
    MAX_MEGAPIXELS = "MAX_MEGAPIXELS"
    FOLDER = "FOLDER"

    def name(self) -> str:
        return "demsuitability"

    def displayName(self) -> str:          # noqa: N802  (QGIS API name)
        return "Elevation data suitability"

    def shortDescription(self) -> str:     # noqa: N802  (QGIS API name)
        return "Grade whether the elevation model can carry this basin's terrain analysis."

    def shortHelpString(self) -> str:      # noqa: N802  (QGIS API name)
        return (
            "<p>Slope, aspect, curvature, wetness, height above drainage and "
            "every relief parameter come from one elevation raster. Whether "
            "those numbers mean anything depends on whether that raster can "
            "resolve the terrain in <i>this</i> basin, which is a different "
            "question in a gorge and on a coastal plain.</p>"
            "<p>Five measurements, each against a stated threshold:</p>"
            "<ul>"
            "<li><b>filling</b> -- how much of the surface depression filling "
            "had to invent</li>"
            "<li><b>slope</b> -- how many slopes fall below "
            "arctan(vertical error / cell size), the angle at which a gradient "
            "is only the model's own error</li>"
            "<li><b>relief</b> -- total relief against that vertical error</li>"
            "<li><b>water</b> -- the largest level surface, as a share of the "
            "basin</li>"
            "<li><b>coverage</b> -- cells inside the basin with no elevation "
            "at all</li>"
            "</ul>"
            "<p>The result is <b>HIGH</b>, <b>MODERATE</b> or <b>LIMITED</b>, "
            "with the numbers that produced it written to a CSV, and "
            "optionally a raster marking every cell that was neither raised by "
            "filling nor below the noise floor.</p>"
            "<p><b>It grades the terrain products, not the basin boundary.</b> "
            "Delineation accuracy is a separate question, measured separately. "
            "Tested on 133 gauges against an independently produced elevation "
            "model: where the grade says HIGH the two models agree about the "
            "slope field at r = 0.94, where it says LIMITED at r = 0.76.</p>"
        )

    # -- parameters -------------------------------------------------------
    def initAlgorithm(self, config=None):  # noqa: N802  (QGIS API name)
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.BASIN, "River basin polygon", types=[SOURCE_POLYGON])
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.SUPPORT_MAP,
                "Also write the per-cell support raster", defaultValue=True)
        )
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

        want_map = self.parameterAsBool(parameters, self.SUPPORT_MAP, context)
        budget = self.parameterAsInt(parameters, self.MAX_MEGAPIXELS, context) * 1_000_000
        folder = self.parameterAsString(parameters, self.FOLDER, context)
        os.makedirs(folder, exist_ok=True)

        basin = self.basin_from_layer(source, feedback)
        feedback.pushInfo(f"Basin area: {basin.area_km2:,.1f} km2")
        feedback.setProgress(10)
        self.check_cancelled(feedback)

        from basinkit.suitability import suitability

        dem = basin.dem(max_pixels=budget, progress=False)
        result = suitability(basin, dem=dem, support_map=want_map)
        feedback.setProgress(70)

        grade = result["grade"]
        feedback.pushInfo("")
        feedback.pushInfo(f"ELEVATION DATA SUITABILITY: {grade}")
        feedback.pushInfo(
            f"{result['product']}, assumed vertical error "
            f"{result['vertical_error_m']:.1f} m, cell {result['cell_size_m']:.0f} m")
        feedback.pushInfo("")
        feedback.pushInfo(
            f"{'test':<11}{'verdict':<11}{'measured':>12}{'advisory':>11}{'unmet':>9}   unit")
        for test in result["tests"]:
            measured = test["measured"]
            feedback.pushInfo(
                f"{test['test']:<11}{test['verdict']:<11}"
                f"{'-' if measured is None else f'{measured:.3f}':>12}"
                f"{test['advisory_at']:>11}{test['unmet_at']:>9}   {test['unit']}")
        feedback.pushInfo("")
        for test in result["tests"]:
            if test["verdict"] != "pass":
                feedback.pushWarning(f"[{test['verdict']}] {test['statement']}")
        feedback.pushInfo(result["statement"])

        rows = ["test,verdict,measured,unit,advisory_at,unmet_at,statement"]
        for test in result["tests"]:
            statement = '"' + str(test["statement"]).replace('"', "'") + '"'
            rows.append(
                f"{test['test']},{test['verdict']},{test['measured']},"
                f"{test['unit']},{test['advisory_at']},{test['unmet_at']},{statement}")
        rows.append("")
        rows.append(f"grade,{grade},,,,,\"{str(result['statement']).replace(chr(34), chr(39))}\"")
        rows.append(f"product,{result['product']},,,,,")
        rows.append(f"vertical_error_m,{result['vertical_error_m']},,,,,")
        rows.append(f"cell_size_m,{result['cell_size_m']},,,,,")
        rows.append(f"basin_km2,{result['basin_km2']},,,,,")

        csv_path = os.path.join(folder, "dem_suitability.csv")
        with open(csv_path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(rows) + "\n")
        feedback.pushInfo(f"Measurements written to {csv_path}")

        raster_path = None
        if want_map and result.get("support") is not None:
            import numpy as np

            support = result["support"]
            if support.rio.nodata is None:
                support = support.rio.write_nodata(np.nan, encoded=False)
            raster_path = os.path.join(folder, "dem_support.tif")
            support.rio.to_raster(raster_path, compress="deflate", tiled=True)
            fraction = result.get("support_fraction")
            feedback.pushInfo(
                "Support raster written: 1 where the model carries the cell, "
                "0 where it does not"
                + (f", {fraction:.0%} of the basin supported" if fraction else ""))
            self._load_on_completion(context, raster_path,
                                     f"Elevation support ({grade})")

        feedback.setProgress(100)
        out = {self.FOLDER: folder, "GRADE": grade, "CSV": csv_path,
               "UNMET": ",".join(result["unmet"]),
               "ADVISORY": ",".join(result["advisory"])}
        if raster_path:
            out["SUPPORT_RASTER"] = raster_path
        return out

    # -- helpers ----------------------------------------------------------
    @staticmethod
    def _load_on_completion(context, path, label):
        if context.project() is None:
            return
        details = QgsProcessingContext.LayerDetails(
            label, context.project(), label, QgsProcessingUtils.LayerHint.Raster)
        details.forceName = True
        if SUPPORTS_LAYER_GROUPING:
            details.groupName = "basinkit terrain"
        context.addLayerToLoadOnCompletion(path, details)
