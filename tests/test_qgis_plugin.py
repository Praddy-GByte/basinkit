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
    source = (PLUGIN / "processing_provider" / "algorithms" / "base.py").read_text(encoding="utf-8")
    assert "return self.__class__()" in source
    assert "return self\n" not in source.split("def createInstance")[1][:200]


# -- dependency detection ---------------------------------------------------
# On macOS the plugin told users to run
#     "QGIS.app/Contents/MacOS/QGIS" -m pip install basinkit
# which is the application binary, not an interpreter: it opens a second QGIS
# window and installs nothing. These tests pin the two properties that stop
# that from coming back.

def _deps():
    import importlib.util
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "qgis_plugin" / "deps.py"
    spec = importlib.util.spec_from_file_location("_bk_deps", root)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_bk_deps"] = module
    spec.loader.exec_module(module)
    return module


def test_python_command_never_returns_the_application_binary(tmp_path, monkeypatch):
    """A path is only offered once it is verified to be an interpreter."""
    deps = _deps()

    app = tmp_path / "QGIS.app" / "Contents" / "MacOS"
    app.mkdir(parents=True)
    binary = app / "QGIS"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)

    monkeypatch.setattr(deps.sys, "executable", str(binary))
    monkeypatch.setattr(deps.sys, "prefix", str(app))
    monkeypatch.setattr(deps.platform, "system", lambda: "Darwin")

    assert deps.python_command() is None
    assert deps.install_command(["basinkit"]) is None


def test_python_command_finds_the_interpreter_in_the_bundle(tmp_path, monkeypatch):
    deps = _deps()

    app = tmp_path / "QGIS.app" / "Contents" / "MacOS"
    (app / "bin").mkdir(parents=True)
    binary = app / "QGIS"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    interpreter = app / "bin" / "python3"
    interpreter.write_text("#!/bin/sh\n", encoding="utf-8")
    interpreter.chmod(0o755)

    monkeypatch.setattr(deps.sys, "executable", str(binary))
    monkeypatch.setattr(deps.sys, "prefix", str(app))
    monkeypatch.setattr(deps.platform, "system", lambda: "Darwin")

    assert deps.python_command() == str(interpreter)
    assert deps.install_command(["basinkit"]).startswith(f'"{interpreter}" -m pip')


def test_the_console_fallback_needs_no_path_and_is_always_offered():
    """runpy runs pip inside the interpreter already running, so it cannot
    target the wrong site-packages."""
    deps = _deps()

    snippet = deps.console_command(["basinkit"])
    assert "runpy.run_module" in snippet
    assert "sys.executable" not in snippet
    assert "/" not in snippet.replace("basinkit", "")


# -- Qt6 / QGIS 4 compatibility ---------------------------------------------
# QGIS 4 runs on Qt6, where the short enum aliases were removed. The fully
# scoped names work on both PyQt5 and PyQt6, so there is one correct spelling
# and no version guard is needed. The plugin repository's own checker found 16
# of these; this test stops them coming back.

UNSCOPED = [
    (r"QgsWkbTypes\.(Polygon|MultiPolygon|LineString|Point)\b", "QgsWkbTypes.Type."),
    (r"QgsProcessing\.TypeVector\w+", "QgsProcessing.SourceType."),
    (r"QgsProcessingParameterNumber\.(Integer|Double)\b", "QgsProcessingParameterNumber.Type."),
    (r"QgsProcessingParameter\w*\.Flag\w+", "...Flag.Flag..."),
    (r"QgsFeatureSink\.FastInsert\b", "QgsFeatureSink.Flag.FastInsert"),
]


def test_no_unscoped_qt_enums():
    """Every Qt/QGIS enum must be spelled with its full scope."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "qgis_plugin"
    bad = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in str(path):
            continue
        text = path.read_text(encoding="utf-8")
        for pattern, fix in UNSCOPED:
            for hit in re.finditer(pattern, text):
                # already scoped forms contain the scope name, skip them
                if ".Type." in hit.group(0) or ".Flag." in hit.group(0) \
                        or ".SourceType." in hit.group(0):
                    continue
                line = text[:hit.start()].count("\n") + 1
                bad.append(f"{path.relative_to(root)}:{line}  "
                           f"{hit.group(0)}  -> use {fix}")
    assert not bad, "unscoped enums break QGIS 4 (Qt6):\n  " + "\n  ".join(bad)


def test_no_algorithm_asks_a_sink_for_its_fields():
    """QgsFeatureSink has no fields(); the fields object the algorithm built
    for parameterAsSink is what QgsFeature needs.

    Landscape form asked the sink, which worked only while a basin happened to
    have no knickpoints to write. Five small sub-basins of the Koshi, run
    through all eleven tools, failed on three of them for this reason.
    """
    import pathlib
    import re

    algorithms = (pathlib.Path(__file__).resolve().parents[1]
                  / "qgis_plugin" / "processing_provider" / "algorithms")
    offenders = []
    for path in sorted(algorithms.glob("*.py")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\bsink\w*\.fields\(\)", line):
                offenders.append(f"{path.name}:{n}: {line.strip()}")
    assert not offenders, offenders


def test_the_report_algorithm_does_not_raise_the_packages_pixel_budget():
    """The QGIS default must not exceed basinkit.report.REPORT_MAX_PIXELS.

    The report is the one caller that cannot survive running out of memory,
    because inside QGIS the kill takes QGIS with it. The package budgets the
    grid to REPORT_MAX_PIXELS, but the algorithm passed max_pixels= explicitly,
    so its own default decided -- and it stood at 40 Mpx, ten times the limit
    the package had just set. Measured on the Juniata inside QGIS 3.34: 245 s
    and 5.61 GB at 40, 26 s and 1.26 GB at 4, for the same eight pages. A
    larger grid buys nothing, because every raster a page draws is decimated
    to DRAW_MAX_PX first.
    """
    import pathlib
    import re

    from basinkit.report import REPORT_MAX_PIXELS

    # read from the file rather than imported: importing the algorithm pulls
    # in qgis.core, and this suite has to run where QGIS is not installed
    source = (pathlib.Path(__file__).resolve().parents[1] / "qgis_plugin"
              / "processing_provider" / "algorithms" / "report.py"
              ).read_text(encoding="utf-8")
    found = re.search(r"^REPORT_MEGAPIXELS\s*=\s*(\d+)", source, re.M)
    assert found, "report.py no longer names its budget REPORT_MEGAPIXELS"
    REPORT_MEGAPIXELS = int(found.group(1))

    assert REPORT_MEGAPIXELS * 1_000_000 <= REPORT_MAX_PIXELS, (
        f"the algorithm defaults to {REPORT_MEGAPIXELS} Mpx while the package "
        f"budgets {REPORT_MAX_PIXELS // 1_000_000} Mpx"
    )


def test_every_raster_budget_default_is_within_what_it_costs():
    """No algorithm may default to a grid it cannot hold in memory.

    report.py costs about 270 bytes per pixel because every page derives
    arrays of its own; the rest route or sample one grid at a time and cost
    about 60. Four gigabytes is the ceiling basinkit's own DEM guard uses
    (DEFAULT_MAX_MEMORY_GB), and QGIS is already holding a project on top of
    it, so a default that reaches the ceiling on its own is not a default.
    """
    import pathlib
    import re

    from basinkit.delineate.dem import DEFAULT_MAX_MEMORY_GB

    algorithms = (pathlib.Path(__file__).resolve().parents[1]
                  / "qgis_plugin" / "processing_provider" / "algorithms")
    over = []
    for path in sorted(algorithms.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "MAX_MEGAPIXELS" not in text:
            continue
        # from the parameter's own name forward to its defaultValue, which
        # sits a few lines below it past other bracketed arguments
        start = text.index("self.MAX_MEGAPIXELS,")
        match = re.search(r"defaultValue=(\w+)", text[start:start + 400])
        assert match, f"{path.name}: MAX_MEGAPIXELS has no defaultValue"
        raw = match.group(1)
        if raw.isdigit():
            megapixels = int(raw)
        else:
            found = re.search(rf"^{re.escape(raw)}\s*=\s*(\d+)", text,
                              re.M)
            assert found, f"{path.name}: cannot read {raw}"
            megapixels = int(found.group(1))
        per_pixel = 270 if path.name == "report.py" else 60
        gb = megapixels * 1_000_000 * per_pixel / 1024 ** 3
        if gb > DEFAULT_MAX_MEMORY_GB:
            over.append(f"{path.name}: {megapixels} Mpx is about "
                        f"{gb:.1f} GB at {per_pixel} bytes a pixel")
    assert not over, over
