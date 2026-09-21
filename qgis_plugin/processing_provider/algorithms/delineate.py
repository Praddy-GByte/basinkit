"""Delineate the river basin upstream of a point."""

from __future__ import annotations

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsFeatureSink,
    QgsFields,
    QgsGeometry,
    QgsProcessingException,
    QgsProcessingParameterBoolean,
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

BACKENDS = ["auto", "hydrobasins", "dem", "api", "tdx"]

BACKEND_HELP = """\
<b>auto</b> (recommended) uses HydroBASINS, then checks the answer against the \
river network and re-routes on the DEM when the two disagree about which river \
the outlet is on. On 300 gauges with agency-published areas, drawn after the \
check was designed and used nowhere else, it corrected 20 answers, left 280 \
alone and made none worse.<br>
<b>hydrobasins</b> walks the upstream graph over HydroBASINS level-12 units. \
Works at any basin size and is fast even for the Amazon, but cannot resolve a \
headwater catchment smaller than about 130 km&sup2;. First use downloads one \
regional file (~80 MB), cached afterwards.<br>
<b>dem</b> routes flow over a freshly downloaded Copernicus DEM. Resolves down \
to a single 30 m pixel. On 59 catchments under 2,000 km2 it matched the agency \
figure within 20 percent on 68 percent of them against 34 percent for \
HydroBASINS, and it beat both pysheds and WhiteboxTools on the identical \
raster. Its working range reaches about 10,000 km2, above which the \
sub-basin route is both faster and more accurate.<br>
<b>api</b> queries a public web service. No download at all, so it is the \
quickest first look, but it is one research group's server and its output \
derives from a non-commercial dataset.<br>
<b>tdx</b> walks a reach-level graph built from TanDEM-X at 12 m, one \
catchment polygon per stream reach instead of one per 130 km&sup2; unit. On \
360 gauges between 100 and 500 km2 it cut the median area error from 32.5 \
percent to 10.5 percent and was the better answer on two thirds of them. It \
is never chosen automatically, for one reason: TDX-Hydro is CC BY-SA 4.0, and \
ShareAlike travels into anything derived from it and redistributed, while \
every other layer here is CC BY 4.0 or more permissive. Needs \
<code>pip install "basinkit[tdx]"</code>, and the republication it reads \
omits twelve of the sixty-two regions, Greenland and much of Arctic North \
America among them."""


class DelineateBasinAlgorithm(BasinkitAlgorithm):
    """Point in, upstream basin polygon out."""

    OUTLET = "OUTLET"
    BACKEND = "BACKEND"
    VERIFY = "VERIFY"
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
            QgsProcessingParameterBoolean(
                self.VERIFY,
                "Check the answer against the river network "
                "(downloads the regional rivers file, a few hundred MB, "
                "the first time)",
                defaultValue=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(self.OUTPUT, "River basin")
        )

    # -- run --------------------------------------------------------------
    @staticmethod
    def _guidance(exc, lat, lon) -> str:
        """What failed, where, and the two things most often behind it."""
        return (
            f"Delineation at {lat:.5f}, {lon:.5f} stopped: "
            f"{type(exc).__name__}: {exc}\n\n"
            "Two things account for most failures here. A point far from any "
            "mapped river cannot be snapped, so move it onto the channel or "
            "raise the snap distance. And a point clicked in a projected layer "
            "is only as good as that layer's CRS, so check the outlet reads as "
            "latitude and longitude in the log above. If neither applies, the "
            "full traceback is in the basinkit tab of the Log Messages panel."
        )

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
                "lon/lat without reprojection. Confirm the coordinate reads "
                "as you expect before using the result."
            )

        backend = BACKENDS[self.parameterAsEnum(parameters, self.BACKEND, context)]
        snap_km = self.parameterAsDouble(parameters, self.SNAP_KM, context)
        verify = self.parameterAsBool(parameters, self.VERIFY, context)
        ratio = self.parameterAsDouble(parameters, self.RIVER_SNAP_RATIO, context)

        lat, lon = point.y(), point.x()
        feedback.pushInfo(f"Outlet: {lat:.5f}, {lon:.5f}  (backend: {backend})")
        if backend in ("auto", "hydrobasins"):
            feedback.pushInfo(
                "First use of this backend downloads one regional HydroBASINS "
                "file of about 80 MB. Later runs are instant."
            )
        if verify and backend in ("auto",):
            feedback.pushInfo(
                "Checking the answer against the river network. The first "
                "check in a region downloads the regional HydroRIVERS file; "
                "untick the box above to skip it."
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
                    # 'download' fetches the river network if it is missing;
                    # False skips the check. The parameter above says which,
                    # so nothing large is ever fetched without being asked for.
                    verify="download" if verify else False,
                    progress=False,
                )
                for warning in caught:
                    feedback.pushWarning(str(warning.message))
        except Exception as exc:
            raise QgsProcessingException(self._guidance(exc, lat, lon)) from exc

        feedback.setProgress(70)
        self.check_cancelled(feedback)

        provenance = basin.provenance
        feedback.pushInfo(f"Basin area: {basin.area_km2:,.1f} km2")
        if provenance.get("backend") == "hydrobasins" and basin.area_km2 < 500:
            feedback.pushWarning(
                "This catchment is at the scale where the 'dem' backend is the "
                "right tool: it routes flow on a 30 m elevation model and "
                "resolves catchments down to a single pixel, while the default "
                "backend works from sub-basins averaging about 130 km2. "
                "Validation across 2,550 gauges puts the crossover near "
                "2,000 km2. Re-run with backend 'dem' for a result at this "
                "scale."
            )
        feedback.pushInfo(
            f"Bounding-box efficiency: {basin.bbox_efficiency:.0%} "
            "(the share of the bounding box the basin actually occupies)"
        )
        # The consistency line compares the result against the river network,
        # which is an independent source. The outlet unit's own UP_AREA field
        # agrees with the assembled area to within one percent almost
        # everywhere, so it confirms the traversal rather than the choice of
        # outlet, and the river network is what tests the latter.
        check = provenance.get("outlet_check") or {}
        if check.get("reason") == "consistent":
            feedback.pushInfo(
                f"Consistency: the basin is {check['ratio']:.2f} times the "
                f"{check['largest_river_upland_km2']:,.0f} km2 draining to the "
                "largest river within 2 km of the outlet, which is the "
                "agreement expected when the outlet is on that river. The test "
                "is deliberately conservative and flags about a third of "
                "questionable outlets, so treat silence as one check passed "
                "rather than as a full verification."
            )
        elif check.get("reason") in ("no-reach", "not-cached", "no-coverage"):
            feedback.pushInfo(
                "Consistency: not tested. "
                + str(provenance.get("note") or
                      "No river network was available for this point.")
            )

        if provenance.get("endorheic"):
            feedback.pushInfo(
                "This outlet sits in an endorheic system: the basin drains to "
                "an inland sink rather than to the sea, so there is no "
                "downstream continuation to look for."
            )
        if provenance.get("coastal"):
            feedback.pushInfo(
                "This is a coastal unit, draining straight to the ocean rather "
                "than joining a larger river."
            )
        if provenance.get("nothing_upstream"):
            feedback.pushInfo(
                "Nothing drains into this outlet, so the polygon is the single "
                "sub-basin containing the point rather than an assembled "
                "catchment. That is what a lake surface, a coastal strip and a "
                "headwater below the grid's resolution all look like here. For "
                "a headwater, the 'dem' backend resolves down to 30 m."
            )

        switched = provenance.get("switched_from")
        if switched:
            feedback.pushInfo(
                f"Refined on the elevation model. The sub-basin route gives "
                f"{switched['area_km2']:,.1f} km2 for this point; the 30 m "
                "routing and the river network agree on the smaller "
                "catchment reported above. " + switched["reason"]
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
