"""Small shims for API changes across the QGIS versions this plugin supports.

Three renames matter here. The first two would change behaviour silently rather
than raise, so they are decided by version:

* ``QgsField(name, QVariant.Type)`` was deprecated in QGIS 3.38 in favour of a
  ``QMetaType.Type`` argument -- and Qt6, which QGIS 4 is built on, removed the
  ``QVariant.Type`` enum outright.
* ``QgsWkbTypes.Type`` became ``Qgis.WkbType`` in QGIS 3.30.

Those two are resolved by version rather than by a try/except import, because
``QMetaType`` exists under Qt5 as well: importing it successfully says nothing
about whether ``QgsField`` accepts it.

The third, ``QgsProcessing.SourceType`` becoming ``Qgis.ProcessingSourceType``
in QGIS 3.36, is resolved by asking the API whether the enum is there. For an
enum, presence is the whole question.
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


# ``Qgis.ProcessingSourceType`` arrived in QGIS 3.36; before that the same enum
# lives on ``QgsProcessing``. Every algorithm imports this module, so the branch
# has to be right across the whole supported range, 3.28 to 4.x, which includes
# the 3.34 long-term release.
#
# Unlike the ``QgsField`` case above, presence does imply usability for an enum,
# so this asks the API directly. A version number is a proxy for the question;
# ``hasattr`` is the question, and it stays correct through future renames.
if hasattr(Qgis, "ProcessingSourceType"):        # QGIS 3.36 and newer
    SOURCE_POLYGON = Qgis.ProcessingSourceType.VectorPolygon
else:                                            # QGIS 3.28 - 3.34
    from qgis.core import QgsProcessing

    SOURCE_POLYGON = QgsProcessing.SourceType.TypeVectorPolygon

#: ``groupName`` and ``layerSortKey`` on LayerDetails arrived in QGIS 3.32.
SUPPORTS_LAYER_GROUPING = QGIS_VERSION >= 33200
