"""How much of the basin is under permanent ice, and where that ice sits."""

from __future__ import annotations

import os

from qgis.core import (
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterNumber,
)

from ...compat import SOURCE_POLYGON
from .base import BasinkitAlgorithm

#: The land-cover budget, in megapixels. ESA WorldCover is 10 m, so a
#: Himalayan basin of a few thousand square kilometres is tens of megapixels
#: at native resolution and is coarsened to fit. Four is the package budget.
MEGAPIXELS = 4


class SnowIceAlgorithm(BasinkitAlgorithm):
    """Basin polygon in, the ice fraction and the ice zone out."""

    BASIN = "BASIN"
    YEAR = "YEAR"
    MAX_MEGAPIXELS = "MAX_MEGAPIXELS"
    ICE_MASK = "ICE_MASK"
    FOLDER = "FOLDER"

    def name(self) -> str:
        return "snowice"

    def displayName(self) -> str:          # noqa: N802  (QGIS API name)
        return "Snow and ice"

    def shortDescription(self) -> str:     # noqa: N802  (QGIS API name)
        return "Permanent snow and ice in the basin, and the elevations it occupies."

    def help_body(self) -> str:
        return (
            "<p>For a Himalayan, Andean or Alpine catchment this is usually "
            "the first question asked and the last one answered. Both layers "
            "it needs were already being fetched: the land-cover map carries "
            "a snow-and-ice class, and the elevation model is in hand for the "
            "terrain products.</p>"
            "<ul>"
            "<li><b>ice share</b> -- measured by area, not by counting cells. "
            "A cell is 12.3 km2 at the equator and 2.2 km2 at 80 degrees "
            "north, and glaciers live at the second latitude.</li>"
            "<li><b>the ice zone</b> -- where ice begins, its median and its "
            "top. The floor is the first percentile of the elevations the ice "
            "occupies, not the lowest cell: one cell in deep shadow is "
            "exactly what a land-cover map gets wrong. On the Trishuli the "
            "lowest mapped cell reads 1,458 m, which is not a Himalayan "
            "terminus, off 33 cells in 140,415; the first percentile reads "
            "4,414 m, which is.</li>"
            "<li><b>the stray cells</b> -- the lowest mapped cell is still "
            "reported, and named as probable misclassification when it sits "
            "far below the floor rather than quietly dropped.</li>"
            "</ul>"
            "<p><b>An ice fraction is not a meltwater fraction.</b> A basin "
            "7 per cent covered by ice does not deliver 7 per cent of its "
            "flow from melt. That depends on mass balance and on how much of "
            "the ice is in the ablation zone in a given year, none of which "
            "is measured here and none of which can be read off a land-cover "
            "map.</p>"
            "<p>ESA WorldCover covers 60S to 82.75N. Outside it the answer "
            "says the map has no opinion, rather than reporting zero per "
            "cent -- which is what no data would otherwise be mistaken for, "
            "in precisely the basins that have the ice.</p>"
        )

    # -- parameters -------------------------------------------------------
    def initAlgorithm(self, config=None):  # noqa: N802  (QGIS API name)
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.BASIN, "River basin polygon", types=[SOURCE_POLYGON])
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.ICE_MASK, "Also write the ice mask as a raster",
                defaultValue=True)
        )
        year = QgsProcessingParameterNumber(
            self.YEAR, "ESA WorldCover year",
            type=QgsProcessingParameterNumber.Type.Integer,
            defaultValue=2021, minValue=2020, maxValue=2030)
        year.setFlags(year.flags() | QgsProcessingParameterNumber.Flag.FlagAdvanced)
        self.addParameter(year)
        budget = QgsProcessingParameterNumber(
            self.MAX_MEGAPIXELS, "Maximum megapixels per layer",
            type=QgsProcessingParameterNumber.Type.Integer,
            defaultValue=MEGAPIXELS, minValue=1, maxValue=200)
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

        year = self.parameterAsInt(parameters, self.YEAR, context)
        budget = self.parameterAsInt(parameters, self.MAX_MEGAPIXELS, context) * 1_000_000
        want_mask = self.parameterAsBool(parameters, self.ICE_MASK, context)
        folder = self.parameterAsString(parameters, self.FOLDER, context)
        os.makedirs(folder, exist_ok=True)

        basin = self.basin_from_layer(source, feedback)
        feedback.pushInfo(f"Basin area: {basin.area_km2:,.1f} km2")
        feedback.setProgress(10)
        self.check_cancelled(feedback)

        from basinkit.snow import snow_ice

        result = snow_ice(basin, year=year, max_pixels=budget, ice_mask=want_mask)
        feedback.setProgress(75)

        feedback.pushInfo("")
        if not result["covered_by_land_cover"]:
            feedback.pushWarning(result["statement"])
        else:
            feedback.pushInfo(
                f"PERMANENT SNOW AND ICE: {result['ice_pct']:.2f}% of the basin "
                f"({result['ice_km2']:,.2f} km2)")
            if result.get("elevation_evaluated"):
                feedback.pushInfo(
                    f"Ice zone: {result['ice_floor_m']:,.0f} m to "
                    f"{result['highest_ice_m']:,.0f} m, median "
                    f"{result['median_ice_m']:,.0f} m")
                feedback.pushInfo(
                    f"{result['above_ice_floor_pct']:.1f}% of the basin lies at or "
                    "above the ice floor")
                if result.get("floor_outlier"):
                    feedback.pushWarning(
                        f"The lowest cell mapped as ice sits at "
                        f"{result['lowest_mapped_ice_m']:,.0f} m, "
                        f"{result['ice_floor_m'] - result['lowest_mapped_ice_m']:,.0f} m "
                        f"below the floor, with {result['cells_below_floor']:,} cells "
                        "beneath it. Those are misclassification, not a terminus.")
            feedback.pushInfo("")
            feedback.pushInfo(result["statement"])

        feedback.pushInfo("")
        for line in result["limits"]:
            feedback.pushWarning(line)

        rows = ["measurement,value,unit"]
        for key, unit in (("ice_km2", "km2"), ("ice_pct", "percent of basin"),
                          ("ice_floor_m", "m"), ("median_ice_m", "m"),
                          ("highest_ice_m", "m"),
                          ("above_ice_floor_pct", "percent of basin"),
                          ("lowest_mapped_ice_m", "m"),
                          ("cells_below_floor", "cells"),
                          ("mapped_cells", "cells"), ("basin_km2", "km2")):
            if key in result:
                rows.append(f"{key},{result[key]},\"{unit}\"")
        rows.append("")
        rows.append('statement,"' + str(result["statement"]).replace('"', "'") + '",')
        for i, line in enumerate(result["limits"], start=1):
            rows.append(f'limit_{i},"' + str(line).replace('"', "'") + '",')
        rows.append(f'source,"{result["source"]}",')
        csv_path = os.path.join(folder, "snow_ice.csv")
        with open(csv_path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(rows) + "\n")
        feedback.pushInfo(f"Measurements written to {csv_path}")

        raster_path = None
        if want_mask and result.get("mask") is not None:
            import numpy as np

            mask = result["mask"]
            if mask.rio.nodata is None:
                mask = mask.rio.write_nodata(np.nan, encoded=False)
            raster_path = os.path.join(folder, "snow_ice.tif")
            mask.rio.to_raster(raster_path, compress="deflate", tiled=True)
            feedback.pushInfo(
                "Ice mask written: 1 where the land-cover map says permanent "
                f"snow and ice, 0 elsewhere in the basin -- {raster_path}")

        feedback.setProgress(100)
        out = {self.FOLDER: folder, "CSV": csv_path,
               "ICE_PCT": result.get("ice_pct"),
               "ICE_KM2": result.get("ice_km2"),
               "ICE_FLOOR_M": result.get("ice_floor_m")}
        if raster_path:
            out["ICE_MASK"] = raster_path
        return out
