"""The routing graph in Arc Hydro's own field names."""

from __future__ import annotations

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsFeatureSink,
    QgsFields,
    QgsGeometry,
    QgsProcessingException,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterNumber,
    QgsProcessingParameterPoint,
)

from ...compat import (
    FIELD_DOUBLE,
    FIELD_INT,
    FIELD_STRING,
    WKB_LINESTRING,
    WKB_MULTIPOLYGON,
    make_field,
)
from .base import BasinkitAlgorithm

WGS84 = "EPSG:4326"


class ArcHydroExportAlgorithm(BasinkitAlgorithm):
    """Point in; Catchment and DrainageLine layers out, named as Arc Hydro names them."""

    OUTLET = "OUTLET"
    SNAP_KM = "SNAP_KM"
    MIN_ORDER = "MIN_ORDER"
    CATCHMENT = "CATCHMENT"
    DRAINAGE_LINE = "DRAINAGE_LINE"

    def name(self) -> str:
        return "archydroexport"

    def displayName(self) -> str:          # noqa: N802  (QGIS API name)
        return "Export for Arc Hydro"

    def shortDescription(self) -> str:     # noqa: N802  (QGIS API name)
        return "Sub-catchments and reaches with HydroID, HydroCode, NextDownID, AreaSqKm."

    def help_body(self) -> str:
        return (
            "<p>A distributed hydrological model does not want a polygon. It "
            "wants sub-catchments and the links between them. basinkit already "
            "holds that graph, so this is a <b>renaming, not a computation</b>: "
            "every value written out is one basinkit already has, and nothing "
            "is inferred from geometry.</p>"
            "<p>Two layers come back, named as the Arc Hydro data model names "
            "them:</p>"
            "<ul>"
            "<li><b>Catchment</b> -- one row per sub-catchment</li>"
            "<li><b>DrainageLine</b> -- one row per river reach</li>"
            "</ul>"
            "<p>Both carry <b>HydroID</b> (an internal identifier, 1..N), "
            "<b>HydroCode</b> (the unmodified HydroBASINS or HydroRIVERS id), "
            "and <b>NextDownID</b> (the HydroID of the downstream feature, or "
            "<b>-1</b> where there is none). Catchments also carry "
            "<b>AreaSqKm</b>, which is HydroBASINS' own published SUB_AREA "
            "rather than a recomputation.</p>"
            "<p><b>DrainID is deliberately left out.</b> In the Arc Hydro model "
            "it points a drainage line at the catchment containing it. basinkit "
            "does not hold that link, and deriving it here would mean a spatial "
            "join -- a guess about which catchment a reach belongs to. Arc "
            "Hydro's own tools populate it.</p>"
            "<p>The run reports whether the graph is a single tree draining to "
            "one outlet. A table that fails that check is still written, with "
            "the failure named: it belongs to the source data, and repairing it "
            "silently would be worse.</p>"
        )

    # -- parameters -------------------------------------------------------
    def initAlgorithm(self, config=None):  # noqa: N802  (QGIS API name)
        self.addParameter(
            QgsProcessingParameterPoint(
                self.OUTLET, "Basin outlet (click on the map, on the river)")
        )
        snap = QgsProcessingParameterNumber(
            self.SNAP_KM, "Snap to the nearest unit within (km)",
            type=QgsProcessingParameterNumber.Type.Double,
            defaultValue=5.0, minValue=0.0,
        )
        snap.setFlags(snap.flags() | QgsProcessingParameterNumber.Flag.FlagAdvanced)
        self.addParameter(snap)

        order = QgsProcessingParameterNumber(
            self.MIN_ORDER, "Minimum stream order for the reaches",
            type=QgsProcessingParameterNumber.Type.Integer,
            defaultValue=0, minValue=0, maxValue=10,
        )
        order.setFlags(order.flags() | QgsProcessingParameterNumber.Flag.FlagAdvanced)
        self.addParameter(order)

        self.addParameter(
            QgsProcessingParameterFeatureSink(self.CATCHMENT, "Catchment")
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(self.DRAINAGE_LINE, "DrainageLine")
        )

    # -- run --------------------------------------------------------------
    def processAlgorithm(self, parameters, context, feedback):  # noqa: N802
        self.require_basinkit(feedback)
        import basinkit as bk
        from basinkit import archydro as ah

        point = self.parameterAsPoint(
            parameters, self.OUTLET, context, QgsCoordinateReferenceSystem(WGS84))
        snap_km = self.parameterAsDouble(parameters, self.SNAP_KM, context)
        min_order = self.parameterAsInt(parameters, self.MIN_ORDER, context)
        lat, lon = point.y(), point.x()

        feedback.pushInfo(f"Outlet: {lat:.5f}, {lon:.5f}")
        feedback.setProgress(5)
        self.check_cancelled(feedback)

        try:
            basin = bk.Basin.from_point(
                lat, lon, backend="hydrobasins", snap_km=snap_km,
                verify=False, progress=False)
            catchments = ah.catchment_table(basin.subbasins(progress=False))
            reaches = ah.drainage_line_table(
                basin.rivers(min_order=min_order, progress=False))
        except Exception as exc:
            raise QgsProcessingException(
                f"Could not build the routing table: {type(exc).__name__}: {exc}"
            ) from exc

        feedback.pushInfo(f"{len(catchments)} catchments, {len(reaches)} drainage lines")
        feedback.setProgress(60)
        self.check_cancelled(feedback)

        check = ah.check(catchments)
        if check["single_outlet"]:
            feedback.pushInfo(
                "The routing table is a single tree draining to one outlet: "
                "no cycles, no pointers to units that are not here."
            )
        else:
            feedback.pushWarning(
                f"The routing table is not a single tree: "
                f"{check['terminal_units']} terminal units, "
                f"{check['dangling_next_down']} pointers to units that are not "
                f"here, {check['units_in_a_cycle']} units in a cycle. Reported, "
                "not repaired -- it belongs to the source data."
            )
        feedback.pushInfo(
            f"Catchment areas sum to {catchments['AreaSqKm'].sum():,.2f} km2, "
            f"against {basin.area_km2:,.2f} km2 measured on the dissolved "
            "polygon. AreaSqKm is HydroBASINS' own figure, passed through "
            "rather than recomputed."
        )

        catch_id = self._write_catchments(parameters, context, catchments)
        line_id = self._write_lines(parameters, context, reaches)

        feedback.setProgress(100)
        return {self.CATCHMENT: catch_id, self.DRAINAGE_LINE: line_id,
                "CATCHMENTS": int(len(catchments)),
                "DRAINAGE_LINES": int(len(reaches)),
                "SINGLE_OUTLET": bool(check["single_outlet"]),
                "NO_DOWNSTREAM_VALUE": ah.NO_DOWNSTREAM}

    # -- helpers ----------------------------------------------------------
    def _write_catchments(self, parameters, context, frame):
        fields = QgsFields()
        fields.append(make_field("HydroID", FIELD_INT))
        fields.append(make_field("HydroCode", FIELD_STRING))
        fields.append(make_field("NextDownID", FIELD_INT))
        fields.append(make_field("AreaSqKm", FIELD_DOUBLE))
        sink, dest_id = self.parameterAsSink(
            parameters, self.CATCHMENT, context, fields, WKB_MULTIPOLYGON,
            QgsCoordinateReferenceSystem(WGS84))
        if sink is None:
            raise QgsProcessingException(
                self.invalidSinkError(parameters, self.CATCHMENT))
        for _, row in frame.iterrows():
            feature = QgsFeature(fields)
            feature.setGeometry(QgsGeometry.fromWkt(row.geometry.wkt))
            feature.setAttributes([
                int(row["HydroID"]), str(row["HydroCode"]),
                int(row["NextDownID"]), float(row["AreaSqKm"] or 0.0),
            ])
            sink.addFeature(feature, QgsFeatureSink.Flag.FastInsert)
        return dest_id

    def _write_lines(self, parameters, context, frame):
        fields = QgsFields()
        fields.append(make_field("HydroID", FIELD_INT))
        fields.append(make_field("HydroCode", FIELD_STRING))
        fields.append(make_field("NextDownID", FIELD_INT))
        has_length = "LengthKm" in frame.columns
        if has_length:
            fields.append(make_field("LengthKm", FIELD_DOUBLE))
        sink, dest_id = self.parameterAsSink(
            parameters, self.DRAINAGE_LINE, context, fields, WKB_LINESTRING,
            QgsCoordinateReferenceSystem(WGS84))
        if sink is None:
            raise QgsProcessingException(
                self.invalidSinkError(parameters, self.DRAINAGE_LINE))
        for _, row in frame.iterrows():
            feature = QgsFeature(fields)
            feature.setGeometry(QgsGeometry.fromWkt(row.geometry.wkt))
            values = [int(row["HydroID"]), str(row["HydroCode"]),
                      int(row["NextDownID"])]
            if has_length:
                values.append(float(row["LengthKm"] or 0.0))
            feature.setAttributes(values)
            sink.addFeature(feature, QgsFeatureSink.Flag.FastInsert)
        return dest_id
