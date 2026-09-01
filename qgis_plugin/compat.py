"""Small shims for API changes across the QGIS versions this plugin supports.

Two renames matter here, and both would be silent breakages rather than clean
errors:

* ``QgsField(name, QVariant.Type)`` was deprecated in QGIS 3.38 in favour of a
  ``QMetaType.Type`` argument -- and Qt6, which QGIS 4 is built on, removed the
  ``QVariant.Type`` enum outright.
* ``QgsWkbTypes.Type`` became ``Qgis.WkbType`` in QGIS 3.30.

Both are resolved by version, not by a try/except import: ``QMetaType`` exists
under Qt5 too, so importing it successfully says nothing about whether
``QgsField`` will accept it.
"""

from __future__ import annotations

from qgis.core import Qgis

QGIS_VERSION = Qgis.QGIS_VERSION_INT

if QGIS_VERSION >= 33800:
    from qgis.PyQt.QtCore import QMetaType

    FIELD_STRING = QMetaType.Type.QString
    FIELD_DOUBLE = QMetaType.Type.Double
    FIELD_INT = QMetaType.Type.LongLong
else:                                            # QGIS 3.28 - 3.36
    from qgis.PyQt.QtCore import QVariant

    FIELD_STRING = QVariant.String
    FIELD_DOUBLE = QVariant.Double
    FIELD_INT = QVariant.LongLong

if QGIS_VERSION >= 33000:
    WKB_POLYGON = Qgis.WkbType.Polygon
    WKB_MULTIPOLYGON = Qgis.WkbType.MultiPolygon
    WKB_LINESTRING = Qgis.WkbType.LineString
    WKB_POINT = Qgis.WkbType.Point
else:
    from qgis.core import QgsWkbTypes

    WKB_POLYGON = QgsWkbTypes.Type.Polygon
    WKB_MULTIPOLYGON = QgsWkbTypes.Type.MultiPolygon
    WKB_LINESTRING = QgsWkbTypes.Type.LineString
    WKB_POINT = QgsWkbTypes.Type.Point


def make_field(name: str, kind):
    from qgis.core import QgsField

    return QgsField(name, kind)


if QGIS_VERSION >= 33000:
    SOURCE_POLYGON = Qgis.ProcessingSourceType.VectorPolygon
else:
    from qgis.core import QgsProcessing

    SOURCE_POLYGON = QgsProcessing.SourceType.TypeVectorPolygon

#: ``groupName`` and ``layerSortKey`` on LayerDetails arrived in QGIS 3.32.
SUPPORTS_LAYER_GROUPING = QGIS_VERSION >= 33200
