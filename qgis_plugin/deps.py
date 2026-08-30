"""Detecting the basinkit Python package, and telling the user how to install it.

QGIS ships its own Python interpreter, and there is still no official mechanism
for a plugin to declare a pip dependency -- the enhancement proposal for it has
been open for years. So the plugin has to detect the gap itself and hand the
user a command that will actually work, which is harder than it sounds: on
Windows ``sys.executable`` is ``qgis-bin.exe``, not ``python.exe``, so the
obvious recipe produces a command that silently does nothing.
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path

#: The pip distribution this plugin needs, and the module it provides.
REQUIRED = {"basinkit": "basinkit"}

#: Extras worth having. The plugin degrades gracefully without them.
OPTIONAL = {"basinkit[stac]": "pystac_client"}


def python_command() -> str:
    """Best guess at the interpreter that owns QGIS's site-packages.

    ``sys.executable`` is wrong on Windows (QGIS bug #45646) and unreliable on
    macOS, so the prefix is searched directly. This follows the approach the
    qpip plugin settled on after hitting all three platforms.
    """
    if (Path(sys.prefix) / "conda-meta").exists():
        return "python"

    if platform.system() == "Windows":
        base = Path(sys.prefix)
        for name in ("python.exe", "python3.exe"):
            candidate = base / name
            if candidate.exists():
                return str(candidate)
        return "python"

    if platform.system() == "Darwin":
        base = Path(sys.prefix) / "bin"
        for name in ("python3", "python"):
            candidate = base / name
            if candidate.exists():
                return str(candidate)

    return sys.executable or "python3"


def missing(mapping: dict[str, str] | None = None) -> list[str]:
    """Which distributions from ``mapping`` cannot be imported."""
    import importlib.util

    absent = []
    for distribution, module in (mapping or REQUIRED).items():
        if importlib.util.find_spec(module) is None:
            absent.append(distribution)
    return absent


def install_command(distributions: list[str] | None = None) -> str:
    """The exact command to paste into a terminal."""
    names = distributions or list(REQUIRED)
    return f'"{python_command()}" -m pip install --upgrade {" ".join(names)}'


def status_message() -> str | None:
    """A ready-to-show message, or ``None`` when everything is present."""
    absent = missing()
    if not absent:
        return None
    return (
        "basinkit needs the Python package "
        f"{', '.join(absent)}, which QGIS does not ship.\n\n"
        "Install it by running this in a terminal, then restart QGIS:\n\n"
        f"    {install_command(absent)}\n\n"
        "On Windows, use the OSGeo4W Shell rather than a plain Command Prompt."
    )


def version() -> str | None:
    try:
        import basinkit

        return basinkit.__version__
    except Exception:
        return None
