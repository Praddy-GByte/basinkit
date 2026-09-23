"""Detecting the basinkit Python package, and telling the user how to install it.

QGIS ships its own Python interpreter, and there is still no official mechanism
for a plugin to declare a pip dependency -- the enhancement proposal for it has
been open for years. So the plugin has to detect the gap itself and hand the
user something that will actually work, which is harder than it sounds.

``sys.executable`` is not the interpreter on any desktop platform: on Windows it
is ``qgis-bin.exe`` and on macOS it is ``QGIS.app/Contents/MacOS/QGIS``. Handing
either of those to ``-m pip`` does not install anything -- on macOS it opens a
second QGIS window. So a path is only offered when it has been verified to be a
real interpreter, and there is always the Python Console fallback below, which
needs no path at all.
"""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

#: The pip distribution this plugin needs, and the module it provides.
REQUIRED = {"basinkit": "basinkit"}

#: What basinkit's dependencies need. geopandas 1.0 and rasterio both require
#: Python 3.10, so on an older QGIS pip cannot install the package at all and
#: the resulting message ("no module named basinkit") sends people looking for
#: an installation fault that is not there.
MIN_PYTHON = (3, 10)
MIN_QGIS = "3.28"

#: Extras worth having. The plugin degrades gracefully without them.
OPTIONAL = {"basinkit[stac]": "pystac_client"}


def _is_interpreter(path: Path) -> bool:
    """A real python executable, not the application binary beside it."""
    return (path.is_file()
            and os.access(path, os.X_OK)
            and path.name.lower().startswith("python"))


def _candidates() -> list[Path]:
    """Places QGIS's own interpreter is known to sit, most likely first."""
    out: list[Path] = []
    prefix = Path(sys.prefix)
    exe = Path(sys.executable) if sys.executable else None

    if exe is not None:
        out.append(exe)

    if platform.system() == "Windows":
        out += [prefix / "python.exe", prefix / "python3.exe",
                prefix / "Scripts" / "python.exe"]
    else:
        out += [prefix / "bin" / "python3", prefix / "bin" / "python"]

    if platform.system() == "Darwin" and exe is not None:
        # walk up to the .app bundle and try the layouts QGIS has shipped
        for parent in exe.parents:
            if parent.suffix == ".app":
                contents = parent / "Contents"
                out += [contents / "MacOS" / "bin" / "python3",
                        contents / "Resources" / "python" / "bin" / "python3",
                        contents / "Frameworks" / "Python.framework" /
                        "Versions" / "Current" / "bin" / "python3"]
                break

    return out


def python_command() -> str | None:
    """The interpreter that owns QGIS's site-packages, or ``None``.

    Returning ``None`` is deliberate. A wrong path is worse than no path: it
    produces a command that appears to work and installs nothing.
    """
    if (Path(sys.prefix) / "conda-meta").exists():
        return "python"
    for candidate in _candidates():
        try:
            if _is_interpreter(candidate):
                return str(candidate)
        except OSError:
            continue
    return None


def missing(mapping: dict[str, str] | None = None) -> list[str]:
    """Which distributions from ``mapping`` cannot be imported."""
    import importlib.util

    absent = []
    for distribution, module in (mapping or REQUIRED).items():
        if importlib.util.find_spec(module) is None:
            absent.append(distribution)
    return absent


def install_command(distributions: list[str] | None = None) -> str | None:
    """The exact terminal command, or ``None`` if no interpreter was found."""
    interpreter = python_command()
    if interpreter is None:
        return None
    names = distributions or list(REQUIRED)
    return f'"{interpreter}" -m pip install --upgrade {" ".join(names)}'


def console_command(distributions: list[str] | None = None) -> str:
    """Install from inside QGIS, with no interpreter path involved.

    ``runpy`` runs pip in the interpreter that is already running, so the
    packages land in exactly the site-packages QGIS imports from. This works on
    every platform and is the fallback when no interpreter path can be trusted.
    """
    names = distributions or list(REQUIRED)
    args = ", ".join(f'"{n}"' for n in names)
    return ("import runpy, sys\n"
            f'sys.argv = ["pip", "install", "--upgrade", {args}]\n'
            'runpy.run_module("pip", run_name="__main__")')


def python_too_old() -> str | None:
    """A message when this QGIS ships a Python basinkit cannot run on.

    Reported before the missing-package message, because on such a build the
    package is not missing by accident: pip cannot install it here at all.
    """
    if sys.version_info >= MIN_PYTHON:
        return None
    running = ".".join(str(n) for n in sys.version_info[:3])
    return (f"This QGIS runs Python {running}, and basinkit needs "
            f"{MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer, as geopandas and "
            "rasterio do.\n\nUpdate QGIS to "
            f"{MIN_QGIS} or newer (3.34 LTR and 3.40 both ship a new enough "
            "Python), then install the package. Installing it into another "
            "Python on this machine will not help: QGIS imports only its own.")


def status_message() -> str | None:
    """A ready-to-show message, or ``None`` when everything is present."""
    stale = python_too_old()
    if stale is not None:
        return stale

    absent = missing()
    if not absent:
        return None

    head = ("basinkit needs the Python package "
            f"{', '.join(absent)}, which QGIS does not ship.\n\n")
    console = ("Open the QGIS Python Console (Plugins > Python Console), paste "
               "this, then restart QGIS:\n\n"
               + "\n".join("    " + line
                           for line in console_command(absent).splitlines()))

    terminal = install_command(absent)
    if terminal is None:
        return head + console
    return (head + console + "\n\nOr, from a terminal:\n\n    " + terminal
            + "\n\nOn Windows, use the OSGeo4W Shell rather than a plain "
              "Command Prompt.")


def version() -> str | None:
    try:
        import basinkit

        return basinkit.__version__
    except Exception:
        return None
