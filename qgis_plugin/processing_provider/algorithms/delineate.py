"""Delineate the river basin upstream of a point."""

from __future__ import annotations

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsFeatureSink,
    QgsFields,
    QgsGeometry,
    QgsProcessingException,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterNumber,
    QgsProcessingParameterPoint,
)

from ...compat import (
    FIELD_DOUBLE,
    FIELD_INT,
    FIELD_STRING,
    WKB_MULTIPOLYGON,
    make_field,
)
from .base import BasinkitAlgorithm

WGS84 = "EPSG:4326"

BACKENDS = ["auto", "hydrobasins", "dem", "api"]

BACKEND_HELP = """\
<b>auto</b> (recommended) uses HydroBASINS and falls back to DEM routing when \
the basin sits at the HydroBASINS resolution floor.<br>
<b>hydrobasins</b> walks the upstream graph over HydroBASINS level-12 units. \
Works at any basin size and is fast even for the Amazon, but cannot resolve a \
headwater catchment smaller than about 130 km&sup2;. First use downloads one \
regional file (~80 MB), cached afterwards.<br>
<b>dem</b> routes flow over a freshly downloaded Copernicus DEM. Resolves down \
to a single 30 m pixel, so it is the right choice for small catchments and the \
wrong one for large ones.<br>
<b>api</b> queries a public web service. No download at all, so it is the \
quickest first look, but it is one research group's server and its output \
derives from a non-commercial dataset."""


class DelineateBasinAlgorithm(BasinkitAlgorithm):
    """Point in, upstream basin polygon out."""

    OUTLET = "OUTLET"
    BACKEND = "BACKEND"
    SNAP_KM = "SNAP_KM"
    RIVER_SNAP_RATIO = "RIVER_SNAP_RATIO"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        return "delineatebasin"

    def displayName(self) -> str:          # noqa: N802  (QGIS API name)
        return "Delineate river basin"

    def shortDescription(self) -> str:     # noqa: N802  (QGIS API name)
        return "Find the basin draining into a point, anywhere on Earth."

    def shortHelpString(self) -> str:      # noqa: N802  (QGIS API name)
        return (
            "<p>Click a point on a river and get the basin that drains into "
            "it, as a polygon in EPSG:4326.</p>"
            "<p><b>Put the point on the river.</b> A coordinate a pixel or two "
            "off the channel can return a basin three orders of magnitude too "
            "small, and nothing crashes. If the point lands on the bank of a "
            "much larger river, the algorithm snaps to the main stem and says "
            "so in the log and in the output attributes.</p>"
            f"<p>{BACKEND_HELP}</p>"
            "<p>The output carries its own provenance: which backend ran, "
            "which dataset version, the licence, and how far the outlet was "
            "moved.</p>"
        )

    # -- parameters -------------------------------------------------------
    def initAlgorithm(self, config=None):  # noqa: N802  (QGIS API name)
        self.addParameter(
            QgsProcessingParameterPoint(
                self.OUTLET,
                "Basin outlet (click on the map, on the river)",
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.BACKEND,
                "Delineation method",
                options=BACKENDS,
                defaultValue=0,
            )
        )

        snap = QgsProcessingParameterNumber(
            self.SNAP_KM,
            "Snap to the nearest unit within (km)",
            type=QgsProcessingParameterNumber.Type.Double,
            defaultValue=5.0,
            minValue=0.0,
        )
        snap.setFlags(snap.flags() | QgsProcessingParameterNumber.Flag.FlagAdvanced)
        self.addParameter(snap)

        ratio = QgsProcessingParameterNumber(
            self.RIVER_SNAP_RATIO,
            "Snap to a nearby main stem when it drains this many times more "
            "(0 disables)",
            type=QgsProcessingParameterNumber.Type.Double,
            defaultValue=10.0,
            minValue=0.0,
        )
        ratio.setFlags(ratio.flags() | QgsProcessingParameterNumber.Flag.FlagAdvanced)
        self.addParameter(ratio)

        self.addParameter(
            QgsProcessingParameterFeatureSink(self.OUTPUT, "River basin")
        )

    # -- run --------------------------------------------------------------
    def processAlgorithm(self, parameters, context, feedback):  # noqa: N802
        self.require_basinkit(feedback)
        import basinkit as bk

        point = self.parameterAsPoint(
            parameters, self.OUTLET, context, QgsCoordinateReferenceSystem(WGS84)
        )
        source_crs = self.parameterAsPointCrs(parameters, self.OUTLET, context)
        if not source_crs.isValid():
            feedback.pushWarning(
                "The outlet carries no CRS, so it was taken as raw EPSG:4326 "
                "lon/lat without reprojection. Check the coordinate if the "
                "result looks wrong."
            )

        backend = BACKENDS[self.parameterAsEnum(parameters, self.BACKEND, context)]
        snap_km = self.parameterAsDouble(parameters, self.SNAP_KM, context)
        ratio = self.parameterAsDouble(parameters, self.RIVER_SNAP_RATIO, context)

        lat, lon = point.y(), point.x()
        feedback.pushInfo(f"Outlet: {lat:.5f}, {lon:.5f}  (backend: {backend})")
        feedback.pushInfo(
            "First use of the 'hydrobasins' backend downloads one regional "
            "file of about 80 MB. Later runs are instant."
        )
        feedback.setProgress(5)
        self.check_cancelled(feedback)

        import warnings

        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                basin = bk.Basin.from_point(
                    lat, lon,
                    backend=backend,
                    snap_km=snap_km,
                    river_snap_ratio=ratio or None,
                    progress=False,
                )
                for warning in caught:
                    feedback.pushWarning(str(warning.message))
        except Exception as exc:
            raise QgsProcessingException(
                f"Delineation failed: {exc}\n\n"
                "The usual cause is an outlet that is not on a mapped river. "
                "Move the point onto the blue line, raise the snap distance, "
                "or try the 'dem' backend for a small headwater catchment."
            ) from exc

        feedback.setProgress(70)
        self.check_cancelled(feedback)

        provenance = basin.provenance
        feedback.pushInfo(f"Basin area: {basin.area_km2:,.1f} km2")
        feedback.pushInfo(
            f"Bounding-box efficiency: {basin.bbox_efficiency:.0%} "
            "(the share of the bounding box the basin actually occupies)"
        )
        reported = provenance.get("reported_up_area_km2")
        if reported:
            difference = abs(basin.area_km2 - reported) / reported
            feedback.pushInfo(
                f"Source dataset reports {reported:,.1f} km2 "
                f"({difference:.2%} from the computed area)"
            )

        fields = QgsFields()
        fields.append(make_field("area_km2", FIELD_DOUBLE))
        fields.append(make_field("bbox_eff", FIELD_DOUBLE))
        fields.append(make_field("backend", FIELD_STRING))
        fields.append(make_field("source", FIELD_STRING))
        fields.append(make_field("licence", FIELD_STRING))
        fields.append(make_field("outlet_lat", FIELD_DOUBLE))
        fields.append(make_field("outlet_lon", FIELD_DOUBLE))
        fields.append(make_field("n_units", FIELD_INT))
        fields.append(make_field("snapped_km", FIELD_DOUBLE))
        fields.append(make_field("snap_ratio", FIELD_DOUBLE))
        fields.append(make_field("citation", FIELD_STRING))

        sink, dest_id = self.parameterAsSink(
            parameters, self.OUTPUT, context,
            fields, WKB_MULTIPOLYGON, QgsCoordinateReferenceSystem(WGS84),
        )
        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))

        feature = QgsFeature(fields)
        feature.setGeometry(QgsGeometry.fromWkt(basin.geometry.wkt))
        feature.setAttributes([
            round(basin.area_km2, 3),
            round(basin.bbox_efficiency, 4),
            provenance.get("backend", ""),
            provenance.get("source_dataset", ""),
            provenance.get("license", provenance.get("license_note", "")),
            lat,
            lon,
            int(provenance.get("n_units", 0) or 0),
            float(provenance.get("snap_distance_km", 0) or 0),
            float(provenance.get("snap_ratio", 0) or 0),
            provenance.get("citation", ""),
        ])
        sink.addFeature(feature, QgsFeatureSink.Flag.FastInsert)

        feedback.setProgress(100)
        return {self.OUTPUT: dest_id}
