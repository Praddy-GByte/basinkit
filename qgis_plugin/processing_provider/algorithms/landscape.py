"""Landscape form: chi, channel steepness, concavity and knickpoints."""

from __future__ import annotations

import csv
import os

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsFeatureSink,
    QgsFields,
    QgsGeometry,
    QgsPointXY,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterNumber,
    QgsProcessingUtils,
)

from ...compat import (
    FIELD_DOUBLE,
    SOURCE_POLYGON,
    SUPPORTS_LAYER_GROUPING,
    WKB_POINT,
    make_field,
)
from .base import BasinkitAlgorithm


class LandscapeFormAlgorithm(BasinkitAlgorithm):
    """Basin polygon in; chi and steepness rasters out, knickpoints on the map."""

    BASIN = "BASIN"
    MIN_AREA_KM2 = "MIN_AREA_KM2"
    THETA_REF = "THETA_REF"
    SMOOTH_M = "SMOOTH_M"
    MAX_MEGAPIXELS = "MAX_MEGAPIXELS"
    FOLDER = "FOLDER"
    KNICKPOINTS = "KNICKPOINTS"

    def name(self) -> str:
        return "landscapeform"

    def displayName(self) -> str:          # noqa: N802  (QGIS API name)
        return "Landscape form (chi and channel steepness)"

    def shortDescription(self) -> str:     # noqa: N802  (QGIS API name)
        return "Is this river still changing, or has it settled?"

    def shortHelpString(self) -> str:      # noqa: N802  (QGIS API name)
        return (
            "<p>The shape indices describe what a basin looks like. None of "
            "them says whether that shape is still adjusting. This does.</p>"
            "<p><b>chi</b> is the integral from the outlet upstream of "
            "(A0/A)^theta dx (Perron &amp; Royden 2013). A river in equilibrium "
            "plots as a straight line against it, so a break in that line is a "
            "knickpoint you can see rather than infer.</p>"
            "<p><b>k_sn</b>, normalised channel steepness, is S&#183;A^theta_ref "
            "(Wobus et al. 2006). theta_ref is fixed at 0.45 and A0 at 1 km2 by "
            "convention, so the number is comparable between basins.</p>"
            "<p><b>Knickpoints</b> come back as a point layer, each carrying the "
            "height of its step and how far its local gradient stands above the "
            "profile's own median.</p>"
            "<p>k_sn was checked cell by cell against TopoToolbox on two basins "
            "and agrees to within 6% at every quantile; its median moves under "
            "2% across a fourfold change in cell size. The knickpoint "
            "<i>count</i> is not that stable -- quote it with its cell size. "
            "Nothing here is an uplift rate: chi, k_sn and knickpoints describe "
            "form and transience, and turning them into rates needs independent "
            "calibration.</p>"
        )

    # -- parameters -------------------------------------------------------
    def initAlgorithm(self, config=None):  # noqa: N802  (QGIS API name)
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.BASIN, "River basin polygon", types=[SOURCE_POLYGON],
            )
        )
        drainage = QgsProcessingParameterNumber(
            self.MIN_AREA_KM2,
            "Channel starts where this much area drains to a cell (km2)",
            type=QgsProcessingParameterNumber.Type.Double,
            defaultValue=1.0, minValue=0.001,
        )
        self.addParameter(drainage)

        theta = QgsProcessingParameterNumber(
            self.THETA_REF, "Reference concavity",
            type=QgsProcessingParameterNumber.Type.Double,
            defaultValue=0.45, minValue=0.05, maxValue=1.0,
        )
        theta.setFlags(theta.flags() | QgsProcessingParameterNumber.Flag.FlagAdvanced)
        self.addParameter(theta)

        smooth = QgsProcessingParameterNumber(
            self.SMOOTH_M, "Smoothing window for the concavity fit (m)",
            type=QgsProcessingParameterNumber.Type.Double,
            defaultValue=500.0, minValue=0.0,
        )
        smooth.setFlags(smooth.flags() | QgsProcessingParameterNumber.Flag.FlagAdvanced)
        self.addParameter(smooth)

        budget = QgsProcessingParameterNumber(
            self.MAX_MEGAPIXELS, "Raster budget (megapixels)",
            type=QgsProcessingParameterNumber.Type.Integer,
            defaultValue=60, minValue=1, maxValue=4000,
        )
        budget.setFlags(budget.flags() | QgsProcessingParameterNumber.Flag.FlagAdvanced)
        self.addParameter(budget)

        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.FOLDER, "Output folder (rasters, profile, figure)")
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(self.KNICKPOINTS, "Knickpoints")
        )

    # -- run --------------------------------------------------------------
    def processAlgorithm(self, parameters, context, feedback):  # noqa: N802
        self.require_basinkit(feedback)

        source = self.parameterAsSource(parameters, self.BASIN, context)
        if source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.BASIN))

        min_area = self.parameterAsDouble(parameters, self.MIN_AREA_KM2, context)
        theta = self.parameterAsDouble(parameters, self.THETA_REF, context)
        smooth = self.parameterAsDouble(parameters, self.SMOOTH_M, context)
        budget = self.parameterAsInt(parameters, self.MAX_MEGAPIXELS, context) * 1_000_000
        folder = self.parameterAsString(parameters, self.FOLDER, context)
        os.makedirs(folder, exist_ok=True)

        basin = self.basin_from_layer(source, feedback)
        feedback.pushInfo(f"Basin area: {basin.area_km2:,.1f} km2")
        feedback.setProgress(5)
        self.check_cancelled(feedback)

        dem = basin.dem(max_pixels=budget, progress=False)
        feedback.pushInfo(f"Elevation raster: {dem.shape[-2]} x {dem.shape[-1]} cells")
        feedback.pushInfo("Routing flow and building the channel network.")
        feedback.setProgress(20)
        self.check_cancelled(feedback)

        from basinkit import landscape as ls

        try:
            result = ls.analyse(dem, min_area_km2=min_area, theta_ref=theta,
                                smooth_m=smooth)
        except Exception as exc:
            raise QgsProcessingException(
                f"The landscape analysis failed: {type(exc).__name__}: {exc}"
            ) from exc

        summary = result["summary"]
        feedback.pushInfo(
            f"{summary['channel_cells']:,} channel cells above {min_area:g} km2"
        )
        feedback.pushInfo(
            f"k_sn median {summary['ksn_median']}, 90th {summary['ksn_p90']}"
        )
        feedback.pushInfo(
            f"{summary['knickpoints']} knickpoints on a "
            f"{summary['trunk_length_km']} km trunk"
        )
        feedback.setProgress(70)
        self.check_cancelled(feedback)

        # what each number is worth, in the log where the numbers are
        for what, sentence in ls.confidence(result).items():
            feedback.pushInfo(f"  {what}: {sentence}")
        for limit in ls.limits(result):
            feedback.pushWarning(limit)

        written = self._write_outputs(result, dem, folder, context, feedback)
        feedback.setProgress(90)

        sink, dest_id, fields = self._knickpoint_sink(parameters, context, dem)
        for point in result["knickpoints"]:
            feature = QgsFeature(fields)
            feature.setGeometry(
                QgsGeometry.fromPointXY(QgsPointXY(point["x"], point["y"])))
            feature.setAttributes([
                round(float(point["chi"]), 2),
                float(point["elevation_m"]),
                float(point["step_m"]),
                float(point["excess_gradient_sigma"]),
                round(float(point.get("distance_to_outlet_m", 0.0)) / 1000.0, 3),
            ])
            sink.addFeature(feature, QgsFeatureSink.Flag.FastInsert)

        feedback.pushInfo(f"Wrote {', '.join(written)} to {folder}")
        feedback.setProgress(100)
        out = {self.FOLDER: folder, self.KNICKPOINTS: dest_id}
        out.update({k: v for k, v in summary.items()
                    if isinstance(v, (int, float, str)) and k != "note"})
        return out

    # -- helpers ----------------------------------------------------------
    def _knickpoint_sink(self, parameters, context, dem):
        fields = QgsFields()
        fields.append(make_field("chi_m", FIELD_DOUBLE))
        fields.append(make_field("elevation_m", FIELD_DOUBLE))
        fields.append(make_field("step_m", FIELD_DOUBLE))
        fields.append(make_field("excess_gradient_sigma", FIELD_DOUBLE))
        fields.append(make_field("distance_to_outlet_km", FIELD_DOUBLE))
        crs = QgsCoordinateReferenceSystem(str(dem.rio.crs))
        sink, dest_id = self.parameterAsSink(
            parameters, self.KNICKPOINTS, context, fields, WKB_POINT, crs)
        if sink is None:
            raise QgsProcessingException(
                self.invalidSinkError(parameters, self.KNICKPOINTS))
        # The fields travel back with the sink. QgsFeatureSink has no fields()
        # of its own, so asking it for them crashed on any basin that actually
        # had a knickpoint to write -- which is most of them.
        return sink, dest_id, fields

    def _write_outputs(self, result, dem, folder, context, feedback):
        """Rasters, the trunk profile and the figure. Each failure is its own."""
        import numpy as np
        import rasterio

        written = []
        transform = dem.rio.transform()
        crs = dem.rio.crs
        for name in ("chi", "ksn"):
            path = os.path.join(folder, f"{name}.tif")
            try:
                array = np.asarray(result["rasters"][name], dtype="float32")
                with rasterio.open(
                    path, "w", driver="GTiff", height=array.shape[0],
                    width=array.shape[1], count=1, dtype="float32", crs=crs,
                    transform=transform, nodata=float("nan"), compress="deflate",
                ) as dst:
                    dst.write(array, 1)
                written.append(f"{name}.tif")
                self._load_on_completion(context, path, name)
            except Exception as exc:
                feedback.reportError(
                    f"{name}.tif could not be written: {type(exc).__name__}: {exc}")

        trunk = result["trunk"]
        path = os.path.join(folder, "trunk_profile.csv")
        try:
            with open(path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["chi_m", "elevation_m", "distance_to_outlet_m",
                                 "x", "y"])
                for i in range(len(trunk["chi_m"])):
                    writer.writerow([
                        round(float(trunk["chi_m"][i]), 2),
                        round(float(trunk["elevation_m"][i]), 2),
                        round(float(trunk["distance_to_outlet_m"][i]), 1),
                        round(float(trunk["x"][i]), 6),
                        round(float(trunk["y"][i]), 6),
                    ])
            written.append("trunk_profile.csv")
        except Exception as exc:
            feedback.reportError(
                f"trunk_profile.csv could not be written: {type(exc).__name__}: {exc}")

        path = os.path.join(folder, "landscape_form.png")
        try:
            from basinkit import landscape as ls

            ls.figure(result, path=path)
            written.append("landscape_form.png")
        except Exception as exc:
            feedback.pushInfo(
                f"The figure could not be drawn ({type(exc).__name__}: {exc}). "
                "Every number and file above is unaffected.")
        return written

    @staticmethod
    def _load_on_completion(context, path, label):
        """Queue the raster for the project; layers cannot be added from here."""
        if context.project() is None:
            return
        details = QgsProcessingContext.LayerDetails(
            label, context.project(), label, QgsProcessingUtils.LayerHint.Raster)
        details.forceName = True
        if SUPPORTS_LAYER_GROUPING:
            details.groupName = "basinkit landscape form"
        context.addLayerToLoadOnCompletion(path, details)
