"""Static checks on the QGIS plugin.

QGIS cannot be installed in CI, so these validate the two things that break a
plugin before it ever runs: metadata the repository will reject, and code that
does not import. The behavioural checks live in ``qgis_plugin/`` and are run
against stubbed bindings by ``verify/``.
"""

from __future__ import annotations

import configparser
import pathlib
import re

import pytest

PLUGIN = pathlib.Path(__file__).resolve().parent.parent / "qgis_plugin"

#: What plugins.qgis.org actually enforces (validator.py PLUGIN_REQUIRED_METADATA).
#: Note `tracker`: the documentation table marks it optional and the site
#: rejects uploads without it.
REQUIRED = ("name", "description", "version", "qgisMinimumVersion",
            "author", "email", "about", "tracker", "repository")


def metadata() -> dict:
    parser = configparser.ConfigParser()
    parser.read(PLUGIN / "metadata.txt", encoding="utf-8")
    return {k.lower(): v for k, v in parser.items("general")}


@pytest.mark.parametrize("field", REQUIRED)
def test_required_metadata_present(field):
    assert metadata().get(field.lower(), "").strip(), f"{field} is required on upload"


def test_supports_qt6_is_absent():
    """Removed from QGIS core; leaving it in is dead metadata."""
    assert "supportsqt6" not in metadata()


def test_has_processing_provider_uses_an_accepted_value():
    """QGIS parses only 'yes' or 'true', case-insensitively. '1' does nothing."""
    assert metadata().get("hasprocessingprovider", "").lower() in ("yes", "true")


def test_version_is_a_release_number():
    assert re.match(r"^\d+\.\d+(\.\d+)?$", metadata()["version"])


def test_declares_compatibility_with_qgis_4():
    assert metadata().get("qgismaximumversion", "").startswith("4.")


def test_category_is_one_of_the_accepted_values():
    assert metadata().get("category", "Vector") in (
        "Raster", "Vector", "Database", "Mesh", "Web"
    )


def test_icon_exists_and_is_a_raster():
    icon = metadata().get("icon", "")
    assert icon.lower().endswith((".png", ".jpg", ".jpeg"))
    assert (PLUGIN / icon).exists()


def test_external_dependency_is_stated_in_about():
    """A repository rule: pip dependencies must be declared in `about`."""
    about = metadata().get("about", "").lower()
    assert "basinkit" in about
    assert "depend" in about or "pip" in about


def test_class_factory_is_defined():
    source = (PLUGIN / "__init__.py").read_text(encoding="utf-8")
    assert "def classFactory(" in source


def test_plugin_folder_does_not_shadow_the_pip_package():
    """A folder named `basinkit` on QGIS's sys.path would hide the package it needs."""
    assert PLUGIN.name != "basinkit"


def test_every_module_compiles():
    import py_compile

    for path in sorted(PLUGIN.rglob("*.py")):
        py_compile.compile(str(path), doraise=True)


def test_provider_registers_in_init_processing_not_only_init_gui():
    """qgis_process calls initProcessing() and never initGui().

    Registering only in initGui makes the algorithms invisible to the CLI, to
    headless runs and to the model runner outside the GUI.
    """
    source = (PLUGIN / "plugin.py").read_text(encoding="utf-8")
    assert "def initProcessing" in source
    assert "addProvider" in source
    init_processing = source.index("def initProcessing")
    init_gui = source.index("def initGui")
    assert source.index("addProvider") > init_processing
    assert source.index("addProvider") < init_gui, (
        "addProvider must sit inside initProcessing, which initGui calls"
    )


def test_algorithm_names_follow_the_processing_rules():
    """Names must be lowercase alphanumeric with no spaces, per the API contract."""
    for path in (PLUGIN / "processing_provider" / "algorithms").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for match in re.finditer(r'def name\(self\)[^\n]*\n\s+return "([^"]+)"', source):
            name = match.group(1)
            assert name.isalnum() and name.islower(), f"{path.name}: {name}"


def test_create_instance_returns_a_new_object():
    """Processing clones the algorithm per run; returning self leaks state."""
    source = (PLUGIN / "processing_provider" / "algorithms" / "base.py").read_text()
    assert "return self.__class__()" in source
    assert "return self\n" not in source.split("def createInstance")[1][:200]
