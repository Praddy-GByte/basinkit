"""The classical Horton-Strahler-Schumm parameters, as a Processing algorithm.

The whole set from one run: the per-order table of streams, lengths and
bifurcation ratios, and the linear, areal and relief parameters beside it.

Two things separate this from a morphometry spreadsheet.

**Streams are counted as streams.** A Strahler stream of order *u* runs from
where it is created until another order-*u* stream destroys it. River datasets
store that as several reaches, so counting rows per order inflates every order
above the first and takes the bifurcation ratios with it. Both counts are
reported side by side so the difference is visible rather than assumed.

**The counts are checked.** An order-*u+1* stream forms only where two order-*u*
streams meet, so N(u) >= 2*N(u+1) and the bifurcation ratio can never fall
below two, a constraint Shreve published in 1966. A single-outlet basin has
exactly one stream of its highest order. Counts that break either are reported
as impossible instead of being handed back as numbers to interpret.
"""

from __future__ import annotations

import html

from qgis.core import (
    QgsProcessingException,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterNumber,
)

from ...compat import SOURCE_POLYGON
from .base import BasinkitAlgorithm


class BasinMorphometryAlgorithm(BasinkitAlgorithm):
    """Basin polygon in, the full morphometric set out."""

    BASIN = "BASIN"
    MIN_ORDER = "MIN_ORDER"
    OUTPUT_HTML = "OUTPUT_HTML"

    def name(self) -> str:
        return "basinmorphometry"

    def displayName(self) -> str:          # noqa: N802  (QGIS API name)
        return "Basin morphometry"

    def shortDescription(self) -> str:     # noqa: N802  (QGIS API name)
        return "Horton-Strahler-Schumm parameters, with the stream counts checked."

    def shortHelpString(self) -> str:      # noqa: N802  (QGIS API name)
        return (
            "<p>Computes the classical morphometric parameters for a basin "
            "polygon: streams, lengths and bifurcation ratios per Strahler "
            "order, then drainage density, stream frequency, texture, form "
            "factor, elongation and circularity ratios, relief ratio, "
            "ruggedness and Melton numbers, the hypsometric integral, and the "
            "gradient of the main channel.</p>"
            "<p><b>Streams are not reaches.</b> A river dataset splits one "
            "Strahler stream into several rows, so counting rows inflates "
            "every order above the first. Both counts appear in the table.</p>"
            "<p><b>The counts are checked.</b> N(u) is at least twice "
            "N(u+1), so the bifurcation ratio can never be below 2 (Shreve "
            "1966), and a basin with one outlet has exactly one stream of its "
            "highest order. Counts that break either are reported.</p>"
            "<p>Area, perimeter, basin length and stream lengths are all "
            "measured in one equal-area projection centred on the basin, "
            "because mixing sources corrupts every ratio built from them.</p>"
            "<p>Nothing here is comparable across river networks: drainage "
            "density and bifurcation ratio describe the network measured, not "
            "the basin alone.</p>"
        )

    # -- parameters -------------------------------------------------------
    def initAlgorithm(self, config=None):  # noqa: N802  (QGIS API name)
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.BASIN, "Basin polygon", types=[SOURCE_POLYGON]
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MIN_ORDER,
                "Smallest Strahler order to include (leave at 1)",
                type=QgsProcessingParameterNumber.Type.Integer,
                defaultValue=1, minValue=1, maxValue=9,
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

        min_order = self.parameterAsInt(parameters, self.MIN_ORDER, context) or 1
        report_path = self.parameterAsFileOutput(parameters, self.OUTPUT_HTML, context)

        basin = self.basin_from_layer(source, feedback)
        feedback.setProgress(10)
        self.check_cancelled(feedback)

        feedback.pushInfo("Fetching the river network and the DEM...")
        try:
            m = basin.morphometry(min_order=min_order)
        except Exception as exc:
            raise QgsProcessingException(f"Morphometry failed: {exc}") from exc

        feedback.setProgress(70)
        self.check_cancelled(feedback)

        # -- the per-order table
        feedback.pushInfo("")
        feedback.pushInfo("Order   Streams   Reaches   Length km   Rb")
        for row in m.get("network", []):
            rb = row.get("bifurcation_ratio")
            feedback.pushInfo(
                f"{row['order']:>5}   {row['streams']:>7,}   {row['reaches']:>7,}   "
                f"{row['total_length_km']:>9,.1f}   {'' if rb is None else f'{rb:.2f}'}"
            )

        # -- the warnings, first and loudest
        warnings = m.get("warnings", [])
        if warnings:
            feedback.pushInfo("")
            for w in warnings:
                text = f"[{w['severity']}] {w['message']}"
                if w["severity"] == "impossible":
                    feedback.reportError(text, fatalError=False)
                else:
                    feedback.pushWarning(text)
        else:
            feedback.pushInfo("")
            feedback.pushInfo("Stream counts are internally consistent.")

        results: dict = {}
        for section in ("linear", "areal", "relief"):
            block = m.get(section) or {}
            if block:
                feedback.pushInfo("")
                feedback.pushInfo(section.capitalize())
            for k, v in block.items():
                if v is None:
                    continue
                results[k] = v
                feedback.pushInfo(f"    {k:<38} {v}")

        results["warnings_count"] = len(warnings)
        results["impossible_count"] = sum(
            1 for w in warnings if w["severity"] == "impossible")

        if report_path:
            self._write_report(report_path, basin, m)
            feedback.pushInfo("")
            feedback.pushInfo(f"Report: {report_path}")
            results[self.OUTPUT_HTML] = report_path

        feedback.setProgress(100)
        return results

    # -- report -----------------------------------------------------------
    @staticmethod
    def _write_report(path, basin, m) -> None:
        def esc(x):
            return html.escape(str(x))

        rows = "".join(
            f"<tr><td>{r['order']}</td><td>{r['streams']:,}</td>"
            f"<td>{r['reaches']:,}</td><td>{r['total_length_km']:,.2f}</td>"
            f"<td>{'' if r.get('bifurcation_ratio') is None else r['bifurcation_ratio']}</td>"
            f"<td>{'' if r.get('length_ratio') is None else r['length_ratio']}</td></tr>"
            for r in m.get("network", [])
        )

        warn = ""
        for w in m.get("warnings", []):
            colour = "#B4472F" if w["severity"] == "impossible" else "#8A6410"
            warn += (f'<p class="warn" style="border-left:3px solid {colour}">'
                     f'<b>{esc(w["severity"])}</b> {esc(w["message"])}'
                     f'<br><span class="ref">{esc(w.get("reference", ""))}</span></p>')
        if not warn:
            warn = ('<p class="ok">Stream counts are internally consistent: every '
                    'bifurcation ratio is at least 2, and exactly one stream '
                    'carries the basin\'s highest order.</p>')

        def block(title, mapping):
            if not mapping:
                return ""
            body = "".join(
                f"<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>"
                for k, v in mapping.items() if v is not None)
            return f"<h2>{esc(title)}</h2><table>{body}</table>"

        notes = "".join(f"<li>{esc(n)}</li>" for n in m.get("notes", []))

        doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Basin morphometry</title><style>
body{{font:15px/1.6 -apple-system,Segoe UI,Roboto,sans-serif;color:#1a1a1a;
background:#fff;max-width:860px;margin:0 auto;padding:32px 22px 80px}}
h1{{font-size:26px;margin:0 0 6px}} h2{{font-size:13px;letter-spacing:.1em;
text-transform:uppercase;color:#0E6B57;margin:34px 0 8px}}
table{{border-collapse:collapse;width:100%;font-size:14px;margin:0 0 8px}}
th,td{{border-bottom:1px solid #e6ebe9;padding:7px 10px;text-align:left}}
th{{font-weight:600;width:52%}} td{{font-variant-numeric:tabular-nums}}
thead th{{font-size:11px;letter-spacing:.07em;text-transform:uppercase;
color:#6b7772;width:auto}}
.warn,.ok{{padding:10px 14px;margin:0 0 10px;background:#f6f7f5;font-size:14px}}
.ok{{border-left:3px solid #0E6B57}}
.ref{{color:#6b7772;font-size:12.5px}}
.sub{{color:#4c5c56;margin:0 0 22px}} ul{{color:#4c5c56;font-size:13.5px}}
</style></head><body>
<h1>Basin morphometry</h1>
<p class="sub">Area {basin.area_km2:,.1f} km&sup2;, centred on
{basin.centroid[0]:.4f}, {basin.centroid[1]:.4f}. Horton-Strahler-Schumm
parameters, with the stream counts tested against what Strahler ordering
allows.</p>

<h2>Consistency</h2>
{warn}

<h2>Network by Strahler order</h2>
<table><thead><tr><th>Order</th><th>Streams</th><th>Dataset reaches</th>
<th>Total length km</th><th>Bifurcation ratio</th><th>Length ratio</th>
</tr></thead><tbody>{rows}</tbody></table>

{block("Linear", m.get("linear"))}
{block("Areal", m.get("areal"))}
{block("Relief", m.get("relief"))}

<h2>Notes</h2><ul>{notes}</ul>
</body></html>"""
        with open(path, "w", encoding="utf8") as fh:
            fh.write(doc)
