"""Shared plumbing for the basinkit algorithms."""

from __future__ import annotations

from qgis.core import QgsProcessingAlgorithm, QgsProcessingException

from ... import deps


class BasinkitAlgorithm(QgsProcessingAlgorithm):
    """Base class: consistent grouping, and one place for the dependency check."""

    def group(self) -> str:
        return "River basins"

    def groupId(self) -> str:              # noqa: N802  (QGIS API name)
        return "riverbasins"

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
        """Build a basinkit Basin from the first polygon feature of a layer."""
        from shapely import wkt
        from shapely.ops import unary_union

        import basinkit as bk

        geometries = []
        for feature in source.getFeatures():
            geometry = feature.geometry()
            if geometry is None or geometry.isEmpty():
                continue
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
        return bk.Basin.from_geometry(merged)
