"""Load the plugin against a real QGIS, if one is installed.

The rest of the plugin tests read ``metadata.txt``. None of them imports an
algorithm, so an enum that moved between QGIS releases is invisible to them.
``Qgis.ProcessingSourceType`` arrived in 3.36 and lives on ``QgsProcessing``
before that, and resolving it wrongly stops every algorithm at import. QGIS 3.34
is a long-term release and is what this runs against.

Nothing here needs a display, a network or the basinkit package: QGIS runs
offscreen and basinkit is stubbed, because what is under test is whether the
plugin's own API usage is valid for the QGIS actually installed.

Skipped when there is no QGIS. That is the usual case in CI, so the value is in
running it on the QGIS versions the plugin claims to support:

    QT_QPA_PLATFORM=offscreen python -m pytest tests/test_qgis_api.py
"""

from __future__ import annotations

import importlib.machinery
import os
import sys
import types

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

qgis_core = pytest.importorskip(
    "qgis.core", reason="QGIS Python bindings are not installed")

PLUGIN_PARENT = str(__import__("pathlib").Path(__file__).resolve().parents[1])
if PLUGIN_PARENT not in sys.path:
    sys.path.insert(0, PLUGIN_PARENT)


@pytest.fixture(scope="module")
def qgis_app():
    app = qgis_core.QgsApplication([], False)
    qgis_core.QgsApplication.setPrefixPath("/usr", True)
    app.initQgis()
    yield app
    app.exitQgis()


@pytest.fixture(scope="module", autouse=True)
def stub_basinkit():
    """A module object standing in for the package, so imports resolve."""
    mod = types.ModuleType("basinkit")
    mod.__spec__ = importlib.machinery.ModuleSpec("basinkit", loader=None)
    mod.__version__ = "0.7.0"
    mod.__file__ = "/stub/basinkit/__init__.py"
    sys.modules.setdefault("basinkit", mod)
    yield


def test_compat_resolves_on_this_qgis(qgis_app):
    """Every symbol compat exports must exist for the installed QGIS."""
    from qgis_plugin import compat

    assert compat.SOURCE_POLYGON is not None
    for name in ("FIELD_STRING", "FIELD_DOUBLE", "FIELD_INT",
                 "WKB_POLYGON", "WKB_MULTIPOLYGON", "WKB_LINESTRING",
                 "WKB_POINT"):
        assert getattr(compat, name) is not None, name


def test_make_field_accepts_the_type_compat_chose(qgis_app):
    """QgsField has to take the field type compat picked for this version.

    Presence of QMetaType says nothing about whether QgsField accepts it, which
    is why compat decides this one by version rather than by a try/except.
    """
    from qgis.core import QgsField

    from qgis_plugin import compat

    field = compat.make_field("area_km2", compat.FIELD_DOUBLE)
    assert isinstance(field, QgsField)
    assert field.name() == "area_km2"


def test_every_algorithm_loads_and_initialises(qgis_app):
    """What QGIS does the moment the plugin is enabled.

    An algorithm that raises here is one that never reaches the toolbox.
    """
    from qgis_plugin.processing_provider.provider import BasinkitProvider

    provider = BasinkitProvider()
    provider.loadAlgorithms()
    algorithms = provider.algorithms()
    assert algorithms, "the provider registered no algorithms"

    for alg in algorithms:
        clone = alg.create()
        clone.initAlgorithm({})
        assert clone.name()
        assert clone.displayName()
        assert clone.parameterDefinitions(), f"{clone.name()} has no parameters"


def test_delineation_offers_the_river_network_check(qgis_app):
    """The check is what makes a wrong answer visible, so it must be reachable."""
    from qgis_plugin.processing_provider.algorithms.delineate import (
        DelineateBasinAlgorithm,
    )

    alg = DelineateBasinAlgorithm()
    alg.initAlgorithm({})
    names = [p.name() for p in alg.parameterDefinitions()]
    assert "VERIFY" in names
    assert "BACKEND" in names
    assert "OUTLET" in names


def test_the_reassurance_line_is_gone(qgis_app):
    """It agreed within 1 percent on 98 percent of catastrophically wrong
    answers, so it read as a pass on exactly the results that needed a flag."""
    from qgis_plugin.processing_provider.algorithms import delineate

    source = __import__("pathlib").Path(delineate.__file__).read_text(encoding="utf-8")
    assert "from the computed area)" not in source


def test_basin_from_layer_reprojects_a_projected_layer(qgis_app):
    """A projected basin layer must reach basinkit in lon/lat.

    The plugin read each feature's WKT in the layer's own CRS and handed it to
    Basin.from_geometry, which assumes EPSG:4326. A UTM layer therefore arrived
    as metres, and the equal-area projection built from its centroid was given
    a northing of 7,793,981 as a latitude. That failed twice over, in
    basin_area_km2 and again in morphometry.
    """
    from qgis.core import (
        QgsCoordinateReferenceSystem,
        QgsCoordinateTransform,
        QgsFeature,
        QgsGeometry,
        QgsProject,
        QgsVectorLayer,
    )

    import basinkit as bk
    from qgis_plugin.processing_provider.algorithms.base import BasinkitAlgorithm

    captured = {}

    def from_geometry(geometry, provenance=None, crs=None):
        captured["geometry"] = geometry
        captured["crs"] = crs
        return object()

    bk.Basin = type("Basin", (), {"from_geometry": staticmethod(from_geometry)})

    # A square over eastern Nepal, held in UTM 45N: exactly the shape of layer
    # that broke, where every coordinate is a six- or seven-figure number.
    utm = QgsGeometry.fromWkt(
        "POLYGON((87.0 26.6, 87.4 26.6, 87.4 27.0, 87.0 27.0, 87.0 26.6))")
    utm.transform(QgsCoordinateTransform(
        QgsCoordinateReferenceSystem("EPSG:4326"),
        QgsCoordinateReferenceSystem("EPSG:32645"),
        QgsProject.instance()))

    layer = QgsVectorLayer("Polygon?crs=EPSG:32645", "basin", "memory")
    feature = QgsFeature()
    feature.setGeometry(utm)
    layer.dataProvider().addFeatures([feature])

    BasinkitAlgorithm.basin_from_layer(layer)

    assert captured["crs"] == "EPSG:4326"
    minx, miny, maxx, maxy = captured["geometry"].bounds
    assert -180 <= minx <= 180 and -90 <= miny <= 90, (
        f"geometry reached basinkit as {captured['geometry'].bounds}, "
        "which is metres, not degrees"
    )
    assert minx == pytest.approx(87.0, abs=1e-3)
    assert miny == pytest.approx(26.6, abs=1e-3)
