"""Characterise a basin: morphometry, land cover fractions, and an HTML report."""

from __future__ import annotations

import html
import json

from qgis.core import (
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFileDestination,
)

from ...compat import SOURCE_POLYGON
from .base import BasinkitAlgorithm


class BasinStatisticsAlgorithm(BasinkitAlgorithm):
    """Basin polygon in, numbers out."""

    BASIN = "BASIN"
    LANDCOVER = "LANDCOVER"
    OUTPUT_HTML = "OUTPUT_HTML"

    def name(self) -> str:
        return "basinstatistics"

    def displayName(self) -> str:          # noqa: N802  (QGIS API name)
        return "Basin statistics"

    def shortDescription(self) -> str:     # noqa: N802  (QGIS API name)
        return "Area, relief, mean slope and land cover fractions for a basin."

    def shortHelpString(self) -> str:      # noqa: N802  (QGIS API name)
        return (
            "<p>Summarises a basin polygon: area computed on an equal-area "
            "projection centred on the basin itself (not in degrees, which is "
            "the usual shortcut and wrong by up to a factor of two), "
            "elevation range, relief, mean slope, and optionally the fraction "
            "of the basin in each land cover class.</p>"
            "<p><b>Bounding-box efficiency</b> is the share of the bounding "
            "box the basin actually occupies. A long dendritic catchment can "
            "drop below 25%, which is how much of a bbox-based download would "
            "have belonged to a neighbouring basin.</p>"
            "<p>Numbers go to the log and to an HTML report; they are also "
            "returned as algorithm outputs, so a model can branch on them.</p>"
        )

    # -- parameters -------------------------------------------------------
    def initAlgorithm(self, config=None):  # noqa: N802  (QGIS API name)
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.BASIN, "Basin polygon", types=[SOURCE_POLYGON]
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.LANDCOVER,
                "Include land cover fractions (downloads 10 m land cover)",
                defaultValue=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterFileDestination(
                self.OUTPUT_HTML, "Report", "HTML files (*.html)", optional=True,
                createByDefault=True,
            )
        )

    # -- run --------------------------------------------------------------
    def processAlgorithm(self, parameters, context, feedback):  # noqa: N802
        self.require_basinkit(feedback)

        source = self.parameterAsSource(parameters, self.BASIN, context)
        if source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.BASIN))

        want_landcover = self.parameterAsBoolean(parameters, self.LANDCOVER, context)
        report_path = self.parameterAsFileOutput(parameters, self.OUTPUT_HTML, context)

        basin = self.basin_from_layer(source, feedback)
        feedback.setProgress(10)

        results = {
            "area_km2": round(basin.area_km2, 2),
            "bbox_efficiency": round(basin.bbox_efficiency, 4),
            "centroid_lat": round(basin.centroid[0], 5),
            "centroid_lon": round(basin.centroid[1], 5),
        }

        feedback.pushInfo(f"Area                    {results['area_km2']:,} km2")
        feedback.pushInfo(
            f"Bounding-box efficiency {results['bbox_efficiency']:.0%}  "
            "(share of the bbox the basin occupies)"
        )
        self.check_cancelled(feedback)

        try:
            terrain = basin.terrain_stats()
            results.update({k: v for k, v in terrain.items() if k != "area_km2"})
            feedback.pushInfo(
                f"Elevation               {terrain['elev_min_m']:,.0f} to "
                f"{terrain['elev_max_m']:,.0f} m "
                f"(mean {terrain['elev_mean_m']:,.0f} m)"
            )
            feedback.pushInfo(f"Relief                  {terrain['relief_m']:,.0f} m")
            feedback.pushInfo(f"Mean slope              {terrain['slope_mean_deg']:.2f} deg")
        except Exception as exc:
            feedback.reportError(f"Terrain statistics failed: {exc}", fatalError=False)
            terrain = {}

        feedback.setProgress(60)
        self.check_cancelled(feedback)

        fractions = {}
        if want_landcover:
            try:
                from basinkit.sources.landcover import class_fractions

                fractions = class_fractions(basin.landcover(progress=False))
                feedback.pushInfo("Land cover:")
                for name, fraction in fractions.items():
                    feedback.pushInfo(f"    {name:<28} {fraction:6.1%}")
                results["landcover_json"] = json.dumps(
                    {k: round(float(v), 4) for k, v in fractions.items()}
                )
            except Exception as exc:
                feedback.reportError(f"Land cover failed: {exc}", fatalError=False)

        if report_path:
            self._write_report(report_path, basin, results, terrain, fractions)
            feedback.pushInfo(f"Report: {report_path}")
            results[self.OUTPUT_HTML] = report_path

        feedback.setProgress(100)
        return results

    # -- report -----------------------------------------------------------
    @staticmethod
    def _write_report(path, basin, results, terrain, fractions) -> None:
        def rows(mapping):
            return "\n".join(
                f"<tr><th>{html.escape(str(k))}</th>"
                f"<td>{html.escape(str(v))}</td></tr>"
                for k, v in mapping.items()
            )

        summary = {
            "Area (km2)": f"{results['area_km2']:,}",
            "Bounding-box efficiency": f"{results['bbox_efficiency']:.1%}",
            "Centroid (lat, lon)": f"{results['centroid_lat']}, {results['centroid_lon']}",
        }
        landcover_rows = "\n".join(
            f"<tr><th>{html.escape(name)}</th><td>{fraction:.1%}</td></tr>"
            for name, fraction in fractions.items()
        )

        document = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Basin statistics</title>
<style>
 body {{ font-family: system-ui, sans-serif; margin: 2rem; max-width: 46rem;
        color: #12191c; background: #fff; }}
 h1 {{ font-size: 1.4rem; margin: 0 0 .2rem; }}
 p.sub {{ color: #63706f; margin: 0 0 1.6rem; }}
 h2 {{ font-size: .78rem; letter-spacing: .12em; text-transform: uppercase;
       color: #0b6fa4; margin: 1.8rem 0 .4rem; }}
 table {{ border-collapse: collapse; width: 100%; }}
 th, td {{ text-align: left; padding: .45rem .6rem .45rem 0;
           border-bottom: 1px solid #e2e8e6; font-weight: 400; }}
 th {{ color: #3a4649; width: 60%; }}
 td {{ text-align: right; font-variant-numeric: tabular-nums; }}
 footer {{ margin-top: 2rem; font-size: .82rem; color: #63706f;
           border-top: 1px solid #d5dcd9; padding-top: .8rem; }}
</style></head><body>
<h1>Basin statistics</h1>
<p class="sub">Generated by basinkit for QGIS.</p>
<h2>Geometry</h2><table>{rows(summary)}</table>
{f'<h2>Terrain</h2><table>{rows(terrain)}</table>' if terrain else ''}
{f'<h2>Land cover</h2><table>{landcover_rows}</table>' if landcover_rows else ''}
<h2>Provenance</h2><table>{rows(basin.provenance) or '<tr><td>none</td></tr>'}</table>
<footer>Area is computed on a Lambert azimuthal equal-area projection centred
on the basin. Slope is derived from the elevation gradient with pixel size
corrected for latitude.</footer>
</body></html>"""
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(document)
