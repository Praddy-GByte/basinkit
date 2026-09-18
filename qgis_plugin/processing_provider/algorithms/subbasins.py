"""The sub-catchments a basin is assembled from, with their routing."""

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
    WKB_MULTIPOLYGON,
    make_field,
)
from .base import BasinkitAlgorithm

WGS84 = "EPSG:4326"


class SubBasinsAlgorithm(BasinkitAlgorithm):
    """Point in, the sub-catchments upstream of it, each with its outflow."""

    OUTLET = "OUTLET"
    SNAP_KM = "SNAP_KM"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        return "subbasins"

    def displayName(self) -> str:          # noqa: N802  (QGIS API name)
        return "Sub-catchments and their routing"

    def shortDescription(self) -> str:     # noqa: N802  (QGIS API name)
        return "The pieces the basin is made of, each pointing at the one it drains into."

    def shortHelpString(self) -> str:      # noqa: N802  (QGIS API name)
        return (
            "<p>'Delineate river basin' dissolves the sub-catchments it walked "
            "into a single polygon. This hands back the pieces instead, each "
            "carrying <b>NEXT_DOWN</b>: the id of the sub-catchment it drains "
            "into.</p>"
            "<p>That is the routing graph itself. Every distributed "
            "rainfall-runoff model wants sub-catchments and the links between "
            "them, and this way nothing has to be inferred from geometry "
            "afterwards -- no shared-edge tests, no guessing which neighbour "
            "is downstream.</p>"
            "<p>Exactly one sub-catchment drains out of the set: the outlet. "
            "Its NEXT_DOWN points at a unit that is not in the layer, or at 0 "
            "where the catchment reaches the sea. That is the check worth "
            "running on the result -- if more than one drains out, the "
            "selection is not a single connected catchment.</p>"
            "<p>Uses the HydroBASINS backend, which is what carries the "
            "routing field. Sub-catchments average about 130 km2, so a "
            "catchment much smaller than that comes back as a single piece.</p>"
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
        self.addParameter(
            QgsProcessingParameterFeatureSink(self.OUTPUT, "Sub-catchments")
        )

    # -- run --------------------------------------------------------------
    def processAlgorithm(self, parameters, context, feedback):  # noqa: N802
        self.require_basinkit(feedback)
        import basinkit as bk

        point = self.parameterAsPoint(
            parameters, self.OUTLET, context, QgsCoordinateReferenceSystem(WGS84))
        snap_km = self.parameterAsDouble(parameters, self.SNAP_KM, context)
        lat, lon = point.y(), point.x()

        feedback.pushInfo(f"Outlet: {lat:.5f}, {lon:.5f}")
        feedback.setProgress(5)
        self.check_cancelled(feedback)

        try:
            basin = bk.Basin.from_point(
                lat, lon, backend="hydrobasins", snap_km=snap_km,
                verify=False, progress=False)
            units = basin.subbasins(progress=False)
        except Exception as exc:
            raise QgsProcessingException(
                f"Could not assemble the sub-catchments: {type(exc).__name__}: "
                f"{exc}"
            ) from exc

        feedback.setProgress(70)
        self.check_cancelled(feedback)

        ids = set(units["HYBAS_ID"].astype("int64").tolist())
        leaving = [int(v) for v in units["NEXT_DOWN"].astype("int64").tolist()
                   if int(v) not in ids]
        feedback.pushInfo(
            f"{len(units)} sub-catchments, {sum(float(v) for v in units['SUB_AREA']):,.0f} "
            f"km2 summed against {basin.area_km2:,.0f} km2 measured on the "
            "dissolved polygon."
        )
        if len(leaving) == 1:
            feedback.pushInfo(
                "Exactly one sub-catchment drains out of the set, which is "
                "what a single connected catchment looks like."
            )
        else:
            feedback.pushWarning(
                f"{len(leaving)} sub-catchments drain out of the set. A "
                "connected catchment has exactly one. Check the outlet: it may "
                "sit between two rivers."
            )

        fields = QgsFields()
        fields.append(make_field("HYBAS_ID", FIELD_INT))
        fields.append(make_field("NEXT_DOWN", FIELD_INT))
        fields.append(make_field("SUB_AREA", FIELD_DOUBLE))
        fields.append(make_field("UP_AREA", FIELD_DOUBLE))
        fields.append(make_field("ENDO", FIELD_INT))
        fields.append(make_field("COAST", FIELD_INT))
        fields.append(make_field("is_outlet", FIELD_INT))

        sink, dest_id = self.parameterAsSink(
            parameters, self.OUTPUT, context, fields, WKB_MULTIPOLYGON,
            QgsCoordinateReferenceSystem(WGS84))
        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))

        for _, unit in units.iterrows():
            feature = QgsFeature(fields)
            feature.setGeometry(QgsGeometry.fromWkt(unit.geometry.wkt))
            next_down = int(unit["NEXT_DOWN"])
            feature.setAttributes([
                int(unit["HYBAS_ID"]),
                next_down,
                float(unit.get("SUB_AREA", 0) or 0),
                float(unit.get("UP_AREA", 0) or 0),
                int(unit.get("ENDO", 0) or 0),
                int(unit.get("COAST", 0) or 0),
                int(next_down not in ids),
            ])
            sink.addFeature(feature, QgsFeatureSink.Flag.FastInsert)

        feedback.setProgress(100)
        return {self.OUTPUT: dest_id, "SUBBASINS": len(units)}
