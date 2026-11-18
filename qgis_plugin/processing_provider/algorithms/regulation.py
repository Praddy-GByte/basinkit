"""How much of the basin's water passes through something somebody operates."""

from __future__ import annotations

import os

from qgis.core import (
    QgsProcessingException,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterNumber,
)

from ...compat import SOURCE_POLYGON
from .base import BasinkitAlgorithm


class RegulationAlgorithm(BasinkitAlgorithm):
    """Basin polygon in, the reservoirs and the degree of regulation out."""

    BASIN = "BASIN"
    MIN_STORAGE = "MIN_STORAGE"
    FOLDER = "FOLDER"

    def name(self) -> str:
        return "regulation"

    def displayName(self) -> str:          # noqa: N802  (QGIS API name)
        return "Reservoirs and regulation"

    def shortDescription(self) -> str:     # noqa: N802  (QGIS API name)
        return ("Reservoirs upstream, what they hold, and whether basinkit's "
                "own error figures were measured on a basin like this one.")

    def help_body(self) -> str:
        return (
            "<p>A delineation is a statement about terrain. It says where "
            "water would go if nothing had been built. Dams, diversions and "
            "inter-basin transfers break that statement, and the blind "
            "validation behind basinkit's published error figures recorded "
            "no degree of regulation for any of its 2,550 gauges.</p>"
            "<p>Nothing new is downloaded. HydroLAKES is already fetched for "
            "the lakes layer and carries, per water body, whether it is a "
            "reservoir, how much it holds and the area draining to it; "
            "HydroRIVERS is already fetched for the river network and "
            "carries the modelled long-term flow. The arithmetic between "
            "them is the part that was missing.</p>"
            "<ul>"
            "<li><b>degree of regulation</b> -- storage as a share of one "
            "year's flow, in bands that are read rather than ranked. A basin "
            "that can hold a tenth of its annual flow behaves differently "
            "from one that can hold four years of it.</li>"
            "<li><b>two area numbers, not one</b> -- the largest single "
            "reservoir's upstream area is unambiguous. The sum of every "
            "reservoir's upstream area is not an area at all, because "
            "reservoirs in series each count the whole catchment above them, "
            "so it is reported as an upper bound and labelled as one.</li>"
            "<li><b>the error bar</b> -- above ten per cent, the answer says "
            "that none of basinkit's published error figures is known to "
            "have been measured on a basin held back like this one. The "
            "honest answer there is not a wider error bar; it is none.</li>"
            "</ul>"
            "<p><b>It reports how much water can be held, not how much there "
            "is.</b> Operating rules, release schedules, current storage and "
            "whether any of this water is actually available are decisions "
            "and measurements, and nothing here observes either. The ratio "
            "has a modelled long-term flow in its denominator, not a gauged "
            "one.</p>"
            "<p>HydroLAKES records water bodies above 10 hectares. A basin "
            "with none found is a basin with none recorded, which is not the "
            "same as a basin with none: a run-of-river intake holds no "
            "stored volume and would not appear here even where it exists.</p>"
        )

    # -- parameters -------------------------------------------------------
    def initAlgorithm(self, config=None):  # noqa: N802  (QGIS API name)
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.BASIN, "River basin polygon", types=[SOURCE_POLYGON])
        )
        floor = QgsProcessingParameterNumber(
            self.MIN_STORAGE, "Ignore reservoirs below this storage (million m3)",
            type=QgsProcessingParameterNumber.Type.Double,
            defaultValue=0.0, minValue=0.0)
        floor.setFlags(floor.flags() | QgsProcessingParameterNumber.Flag.FlagAdvanced)
        self.addParameter(floor)
        self.addParameter(
            QgsProcessingParameterFolderDestination(self.FOLDER, "Output folder")
        )

    # -- run --------------------------------------------------------------
    def processAlgorithm(self, parameters, context, feedback):  # noqa: N802
        self.require_basinkit(feedback)

        source = self.parameterAsSource(parameters, self.BASIN, context)
        if source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.BASIN))

        floor = self.parameterAsDouble(parameters, self.MIN_STORAGE, context)
        folder = self.parameterAsString(parameters, self.FOLDER, context)
        os.makedirs(folder, exist_ok=True)

        basin = self.basin_from_layer(source, feedback)
        feedback.pushInfo(f"Basin area: {basin.area_km2:,.1f} km2")
        feedback.setProgress(10)
        self.check_cancelled(feedback)

        from basinkit.regulation import regulation

        result = regulation(basin, min_storage_mcm=floor)
        feedback.setProgress(75)

        feedback.pushInfo("")
        feedback.pushInfo(
            f"RESERVOIRS: {result['reservoirs']} holding "
            f"{result['storage_mcm']:,.0f} million m3")
        if result.get("degree_of_regulation_pct") is not None:
            feedback.pushInfo(
                f"Degree of regulation: {result['degree_of_regulation_pct']:,.1f}% "
                f"of one year's flow -- {result['band']}")
        if result.get("largest_reservoir_upstream_pct"):
            feedback.pushInfo(
                f"The largest single reservoir sits below "
                f"{result['largest_reservoir_upstream_pct']:.1f}% of the basin")
        if result.get("summed_upstream_exceeds_basin"):
            feedback.pushWarning(
                f"Every reservoir's own upstream area sums to "
                f"{result['summed_upstream_km2']:,.0f} km2, more than the basin "
                "itself, because reservoirs in series each count the whole "
                "catchment above them. That sum is an upper bound, not an area.")

        feedback.pushInfo("")
        feedback.pushInfo(result["statement"])
        if result.get("envelope_note"):
            feedback.pushInfo("")
            feedback.pushWarning(result["envelope_note"])
        if result.get("not_measured"):
            feedback.pushWarning(result["not_measured"])

        rows = ["measurement,value,unit"]
        for key, unit in (("reservoirs", "count"),
                          ("natural_lakes", "count"),
                          ("storage_mcm", "million m3"),
                          ("man_made_storage_mcm", "million m3"),
                          ("mean_annual_flow_cms", "m3/s"),
                          ("degree_of_regulation_pct", "percent of annual flow"),
                          ("largest_reservoir_upstream_km2", "km2"),
                          ("largest_reservoir_upstream_pct", "percent of basin"),
                          ("summed_upstream_km2", "km2 (upper bound)"),
                          ("basin_km2", "km2")):
            if result.get(key) is not None:
                rows.append(f"{key},{result[key]},\"{unit}\"")
        if result.get("band"):
            rows.append(f'band,"{result["band"]}",')
        rows.append("")
        rows.append('statement,"' + str(result["statement"]).replace('"', "'") + '",')
        for key in ("envelope_note", "not_measured"):
            if result.get(key):
                rows.append(f'{key},"' + str(result[key]).replace('"', "'") + '",')
        rows.append(f'source,"{result["source"]}",')
        csv_path = os.path.join(folder, "regulation.csv")
        with open(csv_path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(rows) + "\n")
        feedback.pushInfo(f"Measurements written to {csv_path}")

        table_path = None
        if result.get("biggest"):
            table = ["name,type,grand_id,storage_mcm,upstream_km2,lake_area_km2"]
            for row in result["biggest"]:
                name = str(row.get("name") or "").replace('"', "'")
                table.append(
                    f'"{name}",{row["type"]},{row["grand_id"] or ""},'
                    f'{row["storage_mcm"]},{row["upstream_km2"]},{row["lake_area_km2"]}')
            table_path = os.path.join(folder, "reservoirs.csv")
            with open(table_path, "w", encoding="utf-8") as handle:
                handle.write("\n".join(table) + "\n")
            feedback.pushInfo(f"Reservoir table written to {table_path}")

        feedback.setProgress(100)
        out = {self.FOLDER: folder, "CSV": csv_path,
               "RESERVOIRS": result.get("reservoirs"),
               "STORAGE_MCM": result.get("storage_mcm"),
               "DEGREE_OF_REGULATION_PCT": result.get("degree_of_regulation_pct")}
        if table_path:
            out["RESERVOIR_TABLE"] = table_path
        return out
