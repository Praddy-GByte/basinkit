"""The eight-page report, from a basin polygon."""

from __future__ import annotations

from qgis.core import (
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
)

from ...compat import SOURCE_POLYGON
from .base import BasinkitAlgorithm

#: The budget basinkit.report.REPORT_MAX_PIXELS sets, in megapixels.
#:
#: It is written out rather than imported because this module has to import
#: cleanly when the basinkit package is absent -- that is the case the plugin
#: exists to explain, and an import error here would stop it loading at all.
#:
#: 40 stood here before, which overrode the package budget rather than
#: following it, so the one caller that cannot survive running out of memory
#: ran at ten times the limit. Measured on the Juniata (8,805 km2) inside
#: QGIS 3.34: at 40 the report took 245 s and 5.61 GB, at 4 it took 26 s and
#: 1.26 GB, and both wrote the same eight pages within 6 KB of each other.
#: Nothing was gained by the larger grid, because every raster a page draws is
#: decimated to DRAW_MAX_PX anyway.
REPORT_MEGAPIXELS = 4


class BasinReportAlgorithm(BasinkitAlgorithm):
    """Basin polygon in, a publication-ready PDF out."""

    BASIN = "BASIN"
    TITLE = "TITLE"
    WITH_NETWORK = "WITH_NETWORK"
    MAX_MEGAPIXELS = "MAX_MEGAPIXELS"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        return "basinreport"

    def displayName(self) -> str:          # noqa: N802  (QGIS API name)
        return "Basin report (PDF)"

    def shortDescription(self) -> str:     # noqa: N802  (QGIS API name)
        return "Eight A4 pages: terrain, network, morphometry, and what it all rests on."

    def help_body(self) -> str:
        return (
            "<p>Everything basinkit computes about a basin, on eight A4 pages a "
            "thesis chapter or a manuscript appendix can use directly.</p>"
            "<ol>"
            "<li>Cover: where, how big, which backend, and the elevation data "
            "suitability grade</li>"
            "<li>Elevation, hillshade, the hypsometric curve and the elevation "
            "distribution</li>"
            "<li>Slope and aspect, with slope classes and an aspect rose</li>"
            "<li>Curvature, slope position, ruggedness and the landform classes</li>"
            "<li>The channel network and Horton's laws</li>"
            "<li>The morphometric parameters, each with its symbol, unit and "
            "original reference</li>"
            "<li>What the answer rests on: the suitability scorecard, the "
            "per-cell support map and the drainage-density curve</li>"
            "<li>Methods: sources, licences, software versions and what to cite</li>"
            "</ol>"
            "<p>Pages 5 and 6 need the river network, which is a separate "
            "download of a few hundred megabytes the first time in a region. "
            "Without it they are replaced by a page naming the parameters that "
            "are missing and why, rather than by a partial table that reads "
            "like a complete one.</p>"
            "<p>Takes a minute or two. Needs matplotlib, which comes with "
            "<code>pip install \"basinkit[viz]\"</code>.</p>"
        )

    # -- parameters -------------------------------------------------------
    def initAlgorithm(self, config=None):  # noqa: N802  (QGIS API name)
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.BASIN, "River basin polygon", types=[SOURCE_POLYGON])
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.TITLE, "Title on the cover", defaultValue="", optional=True)
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.WITH_NETWORK,
                "Include the channel network and morphometry "
                "(downloads the regional rivers file the first time)",
                defaultValue=True)
        )
        budget = QgsProcessingParameterNumber(
            self.MAX_MEGAPIXELS, "Raster budget (megapixels)",
            type=QgsProcessingParameterNumber.Type.Integer,
            defaultValue=REPORT_MEGAPIXELS, minValue=1, maxValue=4000,
        )
        budget.setFlags(budget.flags() | QgsProcessingParameterNumber.Flag.FlagAdvanced)
        self.addParameter(budget)
        self.addParameter(
            QgsProcessingParameterFileDestination(
                self.OUTPUT, "Report", fileFilter="PDF files (*.pdf)")
        )

    # -- run --------------------------------------------------------------
    def processAlgorithm(self, parameters, context, feedback):  # noqa: N802
        self.require_basinkit(feedback)

        source = self.parameterAsSource(parameters, self.BASIN, context)
        if source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.BASIN))

        title = (self.parameterAsString(parameters, self.TITLE, context) or "").strip()
        with_network = self.parameterAsBool(parameters, self.WITH_NETWORK, context)
        budget = self.parameterAsInt(parameters, self.MAX_MEGAPIXELS, context) * 1_000_000
        path = self.parameterAsFileOutput(parameters, self.OUTPUT, context)

        basin = self.basin_from_layer(source, feedback)
        feedback.pushInfo(f"Basin area: {basin.area_km2:,.1f} km2")
        feedback.setProgress(5)
        self.check_cancelled(feedback)

        rivers = None
        if not with_network:
            feedback.pushInfo(
                "Channel network left out, so pages 5 and 6 will say which "
                "parameters are missing rather than print a partial table.")
        else:
            feedback.pushInfo("Fetching the river network for pages 5 and 6.")
            try:
                rivers = basin.rivers(progress=False)
            except Exception as exc:
                feedback.pushWarning(
                    f"The river network could not be prepared "
                    f"({type(exc).__name__}: {exc}). The report will say so on "
                    "the page where it belongs."
                )
        feedback.setProgress(25)
        self.check_cancelled(feedback)

        feedback.pushInfo("Drawing eight pages. This takes a minute or two.")
        try:
            from basinkit.report import report

            dem = basin.dem(max_pixels=budget, progress=False)
            written = report(basin, path, title=title or None, dem=dem,
                             rivers=rivers, progress=False)
        except Exception as exc:
            raise QgsProcessingException(
                f"The report could not be produced: {type(exc).__name__}: {exc}\n"
                "Drawing needs matplotlib. Install it with "
                'pip install "basinkit[viz]" into the Python QGIS uses, then '
                "restart QGIS."
            ) from exc

        feedback.pushInfo(f"Report written to {written}")
        feedback.setProgress(100)
        return {self.OUTPUT: written}
