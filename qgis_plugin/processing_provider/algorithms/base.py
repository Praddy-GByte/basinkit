"""Shared plumbing for the basinkit algorithms."""

from __future__ import annotations

from qgis.core import QgsProcessingAlgorithm, QgsProcessingException

from ... import deps

# Appended to every algorithm help panel. The Processing dialog is where a
# user stands at the moment they decide what to write in a methods section,
# so the citation belongs there and not only in the README.
CITATION_HTML = (
    "<p><small>If basinkit contributes to published work, please cite "
    "Kaushik, P. (2026). <i>basinkit: basin-scale acquisition of open "
    "Earth observation data</i>. "
    "<a href=\"https://doi.org/10.5281/zenodo.22181933\">"
    "doi.org/10.5281/zenodo.22181933</a> -- and cite the datasets a run "
    "actually used; Basin.license_report() lists them.</small></p>"
)


class BasinkitAlgorithm(QgsProcessingAlgorithm):
    """Base class: consistent grouping, and one place for the dependency check."""

    def group(self) -> str:
        return "River basins"

    def groupId(self) -> str:              # noqa: N802  (QGIS API name)
        return "riverbasins"

    def help_body(self) -> str:
        """The algorithm's own help text. Subclasses override this."""
        return ""

    def shortHelpString(self) -> str:      # noqa: N802  (QGIS API name)
        # Defined once here so no algorithm can ship without the citation.
        return self.help_body() + CITATION_HTML

    def helpUrl(self) -> str:              # noqa: N802  (QGIS API name)
        return "https://praddy-gbyte.github.io/basinkit/"

    def createInstance(self):              # noqa: N802  (QGIS API name)
        # Must be a NEW object. Processing clones the algorithm for every run,
        # every batch row and every model node; returning self leaks state
        # between them.
        return self.__class__()

    # -- helpers ----------------------------------------------------------
    @staticmethod
    def require_basinkit(feedback=None):
        """Import basinkit or fail with something the user can act on."""
        message = deps.status_message()
        if message is not None:
            raise QgsProcessingException(message)
        import basinkit

        if feedback is not None:
            feedback.pushInfo(f"basinkit {basinkit.__version__}")
        return basinkit

    @staticmethod
    def check_cancelled(feedback) -> None:
        # QGIS spells it with one l.
        if feedback is not None and feedback.isCanceled():
            raise QgsProcessingException("Cancelled by the user.")

    @staticmethod
    def basin_from_layer(source, feedback=None):
        """Build a basinkit Basin from the polygon features of a layer.

        The layer is transformed to EPSG:4326 first. basinkit works in lon/lat
        throughout, and a projected layer used to arrive here as metres, which
        PROJ then rejected as a latitude.
        """
        from qgis.core import (
            QgsCoordinateReferenceSystem,
            QgsCoordinateTransform,
            QgsGeometry,
            QgsProject,
        )
        from shapely import wkt
        from shapely.ops import unary_union

        import basinkit as bk

        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        source_crs = source.sourceCrs()
        transform = None
        if source_crs.isValid() and source_crs != wgs84:
            transform = QgsCoordinateTransform(source_crs, wgs84,
                                               QgsProject.instance())
            if feedback is not None:
                feedback.pushInfo(
                    f"Basin layer is {source_crs.authid()}; reprojecting to "
                    "EPSG:4326, which is what basinkit works in."
                )

        geometries = []
        for feature in source.getFeatures():
            geometry = feature.geometry()
            if geometry is None or geometry.isEmpty():
                continue
            if transform is not None:
                geometry = QgsGeometry(geometry)
                geometry.transform(transform)
            geometries.append(wkt.loads(geometry.asWkt()))

        if not geometries:
            raise QgsProcessingException(
                "The basin layer has no usable geometry. Run 'Delineate river "
                "basin' first, or pass a polygon layer."
            )

        merged = unary_union(geometries)
        if feedback is not None and len(geometries) > 1:
            feedback.pushInfo(
                f"Merged {len(geometries)} features into one basin."
            )
        return bk.Basin.from_geometry(merged, crs="EPSG:4326")
