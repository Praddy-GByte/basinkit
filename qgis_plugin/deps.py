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

#: What the plugin cannot work without, as ``install target -> module it
#: provides``.
#:
#: ``basinkit`` alone is not enough, and that gap was doing real damage. The
#: package's core dependencies do not include pyflwdir, which is what the DEM
#: backend routes with -- and ``auto`` reaches for the DEM backend on every
#: catchment below 2,000 km2, which is most of the ones people delineate from
#: a click. Without it those basins came back as the HydroBASINS level-12
#: assembly instead: coarser, larger, and with nothing on the face of the
#: answer to say a different backend had produced it. A 259 km2 catchment
#: measured 314.8 km2 that way, 21.6 percent high, against 255.6 km2 with
#: pyflwdir present.
#:
#: matplotlib is the same shape of problem one step along: the report
#: algorithm is one of the eleven, and without matplotlib it is the one that
#: fails. Telling someone at install time costs a line; telling them when
#: they run it costs them the run.
REQUIRED = {
    "basinkit": "basinkit",
    "basinkit[delineate]": "pyflwdir",
    "basinkit[viz]": "matplotlib",
}

#: Why each target is needed, for the message. Keyed as REQUIRED is.
REASONS = {
    "basinkit": "the package itself",
    "basinkit[delineate]": (
        "pyflwdir, which the DEM backend routes with -- without it every "
        "catchment below 2,000 km2 falls back to the coarser HydroBASINS "
        "answer"
    ),
    "basinkit[viz]": "matplotlib, which draws the eight-page report",
}

#: What basinkit's dependencies need. geopandas 1.0 and rasterio both require
#: Python 3.10, so on an older QGIS pip cannot install the package at all and
#: the resulting message ("no module named basinkit") sends people looking for
#: an installation fault that is not there.
MIN_PYTHON = (3, 10)
MIN_QGIS = "3.28"

#: Extras worth having. The plugin degrades gracefully without them, and says
#: which algorithm is affected at the point of use.
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


def externally_managed() -> bool:
    """Whether pip here will refuse to install anything (PEP 668).

    Debian and Ubuntu mark their system Python as externally managed and ship
    QGIS against it, so the command this module printed came back as
    ``error: externally-managed-environment`` and the plugin looked broken on
    two of the most common Linux desktops. The marker is a file beside the
    standard library, so this is a question that can be answered rather than
    guessed at.
    """
    import sysconfig

    for key in ("stdlib", "purelib", "platstdlib"):
        root = sysconfig.get_path(key)
        if root and (Path(root).parent / "EXTERNALLY-MANAGED").exists():
            return True
        if root and (Path(root) / "EXTERNALLY-MANAGED").exists():
            return True
    return False


def _pip_flags() -> list[str]:
    """The flags pip needs on this installation, and no others."""
    flags = ["--upgrade"]
    if externally_managed():
        flags.append("--break-system-packages")
    return flags


def _quote(name: str) -> str:
    """Quote an install target so a shell does not eat the extras bracket.

    ``basinkit[delineate]`` is a glob pattern to bash and zsh. Unquoted, zsh
    refuses the command outright ("no matches found") and bash passes a
    literal that pip then cannot parse. This is the difference between a
    command that works when pasted and one that does not.
    """
    return f"'{name}'" if any(c in name for c in "[]") else name


def install_command(distributions: list[str] | None = None) -> str | None:
    """The exact terminal command, or ``None`` if no interpreter was found."""
    interpreter = python_command()
    if interpreter is None:
        return None
    names = distributions or list(REQUIRED)
    parts = " ".join(_quote(n) for n in names)
    return (f'"{interpreter}" -m pip install '
            f'{" ".join(_pip_flags())} {parts}')


def console_command(distributions: list[str] | None = None) -> str:
    """Install from inside QGIS, with no interpreter path involved.

    ``runpy`` runs pip in the interpreter that is already running, so the
    packages land in exactly the site-packages QGIS imports from. This works on
    every platform and is the fallback when no interpreter path can be trusted.
    No shell is involved, so the extras brackets need no quoting here.
    """
    names = distributions or list(REQUIRED)
    args = ", ".join(f'"{n}"' for n in [*_pip_flags(), *names])
    return ("import runpy, sys\n"
            f'sys.argv = ["pip", "install", {args}]\n'
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

    if absent == ["basinkit"]:
        head = ("basinkit needs the Python package basinkit, which QGIS does "
                "not ship.\n\n")
    else:
        lines = "\n".join(f"    {name} -- {REASONS.get(name, 'needed')}"
                           for name in absent)
        head = ("basinkit needs Python packages QGIS does not ship:\n\n"
                f"{lines}\n\n")
    console = ("Open the QGIS Python Console (Plugins > Python Console), paste "
               "this, then restart QGIS:\n\n"
               + "\n".join("    " + line
                           for line in console_command(absent).splitlines()))

    terminal = install_command(absent)
    if terminal is None:
        return head + console
    tail = ("\n\nOn Windows, use the OSGeo4W Shell rather than a plain "
            "Command Prompt.")
    if externally_managed():
        tail += (
            "\n\nThis QGIS runs on a system Python that the distribution "
            "marks as externally managed (Debian and Ubuntu do), so pip "
            "refuses to install into it without --break-system-packages, "
            "which is already in the command above. If pip then stops on a "
            "package the distribution itself installed -- pyproj and "
            "jsonschema are the two that come up -- adding --ignore-installed "
            "for those gets past it, at the cost of shadowing the "
            "distribution's copies with pip's. Installing into a separate "
            "environment instead will not help: QGIS imports only from its "
            "own Python."
        )
    return (head + console + "\n\nOr, from a terminal:\n\n    " + terminal
            + tail)


def version() -> str | None:
    try:
        import basinkit

        return basinkit.__version__
    except Exception:
        return None
