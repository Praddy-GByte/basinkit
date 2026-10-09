# -*- coding: utf-8 -*-
"""BasinKit for ArcGIS Pro.

Click a river anywhere on Earth and get the basin draining into it, with its
elevation, terrain surfaces, land cover, soil, rainfall, surface water, rivers
and Horton-Strahler morphometry -- and, from 0.7.0, a grade for every one of
those layers measured against an independently produced source.

This toolbox does NOT import basinkit, geopandas or rasterio. It starts
basinkit_runner.py with a separate Python interpreter and adds the files that
come back. ArcGIS Pro's own Python environment is never modified, so arcpy's
pinned GDAL and PROJ cannot be broken by installing this.

Not affiliated with, endorsed by, or sponsored by Esri.
Apache-2.0 licence. https://github.com/Praddy-GByte/basinkit
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import arcpy

HERE = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(HERE, "basinkit_runner.py")
PYTHON_SETTING = os.path.join(HERE, "basinkit_python.txt")

def _managed_env_dir():
    """Where BasinKit keeps the environment it creates for itself."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "BasinKit", "env")


def _env_python(env_dir):
    """The interpreter inside a virtual environment."""
    if os.name == "nt":
        return os.path.join(env_dir, "Scripts", "python.exe")
    return os.path.join(env_dir, "bin", "python")

BACKENDS = ["auto", "hydrobasins", "dem", "api", "tdx"]
DEM_PRODUCTS = ["cop30", "cop90", "nasadem", "srtm30"]
SURFACES = ["hillshade", "slope", "aspect", "curvature", "tpi", "tri", "roughness",
            "landform", "flow_accumulation", "streams", "twi", "hand"]
SOIL_PROPERTIES = ["clay", "sand", "silt", "soc", "phh2o", "cec", "nitrogen",
                   "bdod", "cfvo", "ocd", "ocs", "wv0033", "wv1500"]
SOIL_DEPTHS = ["0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm", "100-200cm"]


# ----------------------------------------------------------------- plumbing

def resolve_python():
    """Which interpreter has basinkit.

    Order: the BASINKIT_PYTHON variable, then the path saved by the Configure
    tool, then the interpreter running Pro. The last one only works if the user
    installed basinkit into a cloned Pro environment, which is supported but not
    recommended -- see the README.
    """
    env = os.environ.get("BASINKIT_PYTHON", "").strip()
    if env:
        return env
    if os.path.exists(PYTHON_SETTING):
        try:
            with open(PYTHON_SETTING, "r", encoding="utf-8") as fh:
                saved = fh.read().strip()
            if saved:
                return saved
        except OSError:
            pass
    managed = _env_python(_managed_env_dir())
    if os.path.exists(managed):
        return managed
    return sys.executable


MIN_PYTHON = (3, 10)


def py_version(exe):
    """(major, minor) reported by this interpreter, or None."""
    if not exe:
        return None
    try:
        out = subprocess.check_output(
            [exe, "-c", "import sys;sys.stdout.write('%d.%d' % sys.version_info[:2])"],
            stderr=subprocess.STDOUT, universal_newlines=True,
            encoding="utf-8", errors="replace", timeout=60,
            startupinfo=_no_console())
    except Exception:                                        # noqa: BLE001
        return None
    lines = (out or "").strip().splitlines()
    if not lines:
        return None
    parts = lines[-1].strip().split(".")
    try:
        return (int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return None


def _launcher_python(tag):
    """Ask the Windows 'py' launcher where a given version lives."""
    if os.name != "nt":
        return None
    try:
        out = subprocess.check_output(
            ["py", tag, "-c", "import sys;sys.stdout.write(sys.executable)"],
            stderr=subprocess.STDOUT, universal_newlines=True,
            encoding="utf-8", errors="replace", timeout=60,
            startupinfo=_no_console())
    except Exception:                                        # noqa: BLE001
        return None
    out = (out or "").strip().splitlines()
    cand = out[-1].strip() if out else ""
    return cand if cand and os.path.exists(cand) else None


def interpreters():
    """Every interpreter worth considering as a base, best first.

    ArcGIS Pro's own Python comes last on purpose. Pro has shipped Python
    versions older than basinkit supports, and an environment built from one
    of those cannot install basinkit at all.
    """
    seen, out = set(), []

    def add(exe):
        if not exe:
            return
        stem = os.path.splitext(os.path.basename(exe))[0].lower()
        if not stem.startswith("python"):
            return                       # ArcGISPro.exe is not an interpreter
        if exe not in seen and os.path.exists(exe):
            seen.add(exe)
            out.append(exe)

    for tag in ("-3.13", "-3.12", "-3.11", "-3.10"):
        add(_launcher_python(tag))
    try:
        import shutil
        for name in ("python3", "python"):
            add(shutil.which(name))
    except Exception:                                        # noqa: BLE001
        pass

    add(sys.executable)
    names = ["python.exe"] if os.name == "nt" else ["bin/python3", "bin/python"]
    roots = [sys.prefix, getattr(sys, "base_prefix", sys.prefix)]
    if os.name == "nt":
        for pf in (os.environ.get("ProgramFiles", ""),
                   os.environ.get("ProgramFiles(x86)", "")):
            if pf:
                roots.append(os.path.join(pf, "ArcGIS", "Pro", "bin", "Python",
                                          "envs", "arcgispro-py3"))
    for root in roots:
        for name in names:
            add(os.path.join(root, *name.split("/")))
    return out


def base_python():
    """An interpreter new enough to build a basinkit environment from.

    Returns (path, version) or (None, best_version_seen). Inside ArcGIS Pro
    sys.executable is ArcGISPro.exe rather than an interpreter, and Pro's own
    Python may predate the version basinkit needs, so neither is assumed.
    """
    best = None
    for exe in interpreters():
        ver = py_version(exe)
        if ver is None:
            continue
        arcpy.AddMessage("  %s  Python %d.%d" % (exe, ver[0], ver[1]))
        if ver >= MIN_PYTHON:
            return exe, ver
        if best is None or ver > best:
            best = ver
    return None, best


def probe(exe, timeout=60):
    """Return basinkit's version reported by this interpreter, or None."""
    if not exe:
        return None
    try:
        out = subprocess.check_output(
            [exe, "-c", "import basinkit,sys;sys.stdout.write(basinkit.__version__)"],
            stderr=subprocess.STDOUT, universal_newlines=True,
            encoding="utf-8", errors="replace", timeout=timeout,
            startupinfo=_no_console())
    except Exception:                                        # noqa: BLE001
        return None
    out = (out or "").strip().splitlines()
    return out[-1].strip() if out else None


def _no_console():
    """Keep a console window from flashing on Windows."""
    if os.name != "nt":
        return None
    st = subprocess.STARTUPINFO()
    st.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return st


def candidates():
    """Interpreters worth testing, best first. No side effects."""
    seen, out = set(), []

    def add(exe):
        if exe and exe not in seen:
            seen.add(exe)
            out.append(exe)

    add(os.environ.get("BASINKIT_PYTHON", "").strip())
    if os.path.exists(PYTHON_SETTING):
        try:
            with open(PYTHON_SETTING, "r", encoding="utf-8") as fh:
                add(fh.read().strip())
        except OSError:
            pass
    add(_env_python(_managed_env_dir()))
    try:
        import shutil
        for name in ("python3", "python"):
            add(shutil.which(name))
    except Exception:                                        # noqa: BLE001
        pass
    add(sys.executable)
    return [e for e in out if e]


def stream(cmd, timeout=3600):
    """Run a command, relay every line into the messages pane.

    Returns (exit code, everything it printed). Environment creation and pip
    are slow enough that silence would look like a hang, and the text is what
    tells the user which of several quite different things went wrong.
    """
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        universal_newlines=True, encoding="utf-8", errors="replace",
        startupinfo=_no_console())
    kept = []
    for line in proc.stdout:
        line = line.rstrip()
        if line:
            kept.append(line)
            arcpy.AddMessage("    " + line)
    proc.wait(timeout=timeout)
    return proc.returncode, "\n".join(kept)


def _manual_steps():
    return ("Install Python 3.10 or newer from https://www.python.org/downloads/ "
            "(tick 'Add python.exe to PATH'), run "
            "'pip install \"basinkit[all]\"' in a Command Prompt, then put that "
            "python.exe in this tool's first parameter.")


def build_environment(base_exe, env_dir):
    """Create a virtual environment and install basinkit into it.

    The environment is separate from ArcGIS Pro's own, which is the whole
    point: Pro's Python has arcpy with pinned GDAL and PROJ, and installing
    scientific packages into it is the documented way to break ArcGIS Pro.
    Returns the path of the interpreter inside it.
    """
    ver = py_version(base_exe)
    if ver is None:
        arcpy.AddError("Could not run %s. %s" % (base_exe, _manual_steps()))
        raise arcpy.ExecuteError
    if ver < MIN_PYTHON:
        arcpy.AddError(
            "%s is Python %d.%d, and basinkit needs %d.%d or newer, so an "
            "environment built from it cannot install basinkit."
            % (base_exe, ver[0], ver[1], MIN_PYTHON[0], MIN_PYTHON[1]))
        arcpy.AddError(_manual_steps())
        raise arcpy.ExecuteError

    arcpy.AddMessage("Creating an environment for BasinKit")
    arcpy.AddMessage("  location: %s" % env_dir)
    arcpy.AddMessage("  built from: %s (Python %d.%d)" % (base_exe, ver[0], ver[1]))
    arcpy.AddMessage("ArcGIS Pro's own Python is not modified.")

    try:
        os.makedirs(os.path.dirname(env_dir), exist_ok=True)
    except OSError as exc:
        arcpy.AddError("Cannot create %s (%s)." % (os.path.dirname(env_dir), exc))
        raise arcpy.ExecuteError

    if stream([base_exe, "-m", "venv", env_dir], timeout=600)[0] != 0:
        arcpy.AddError("Could not create the environment. " + _manual_steps())
        raise arcpy.ExecuteError

    exe = _env_python(env_dir)
    if not os.path.exists(exe):
        arcpy.AddError("The environment was created but %s is missing." % exe)
        raise arcpy.ExecuteError

    arcpy.AddMessage("Installing basinkit and its dependencies.")
    arcpy.AddMessage("This downloads about 150 MB and takes a few minutes.")
    stream([exe, "-m", "pip", "install", "--upgrade", "pip", "--quiet"], timeout=900)
    code, text = stream([exe, "-m", "pip", "install", "basinkit[all]"], timeout=3600)
    if code != 0:
        low = text.lower()
        if "requires-python" in low or "different python version" in low:
            arcpy.AddError(
                "pip refused every basinkit version because this interpreter is "
                "too old. basinkit needs Python %d.%d or newer."
                % (MIN_PYTHON[0], MIN_PYTHON[1]))
        elif ("could not find a version" in low or "no matching distribution" in low
              or "connection" in low or "timed out" in low or "proxy" in low):
            arcpy.AddError(
                "pip could not fetch basinkit. The message above says why -- "
                "usually no route to pypi.org, or a proxy in the way.")
        else:
            arcpy.AddError("The install did not finish. The message above says why.")
        arcpy.AddError(_manual_steps())
        raise arcpy.ExecuteError
    return exe


def run(argv, messages=None):
    """Run the runner, relay its lines into the Pro messages pane.

    Returns (outputs, result) where outputs is a list of (kind, path).
    """
    exe = resolve_python()
    if not os.path.exists(RUNNER):
        arcpy.AddError("basinkit_runner.py is missing. Keep it in the same "
                       "folder as BasinKit.pyt.")
        raise arcpy.ExecuteError
    cmd = [exe, RUNNER] + [str(a) for a in argv]
    arcpy.AddMessage("Running: " + " ".join(cmd))

    startup = None
    if os.name == "nt":                       # keep a console window from flashing
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, encoding="utf-8", errors="replace",
            startupinfo=startup)
    except FileNotFoundError:
        arcpy.AddError("Could not start '%s'. Set the interpreter with the "
                       "'Set Up BasinKit' tool, or set the BASINKIT_PYTHON "
                       "environment variable." % exe)
        raise arcpy.ExecuteError

    outputs, result, failed = [], {}, None
    for raw in proc.stdout:
        line = raw.rstrip("\n")
        if not line:
            continue
        parts = line.split("\t")
        tag = parts[0]
        if tag == "INFO" and len(parts) > 1:
            arcpy.AddMessage(parts[1])
        elif tag == "OUT" and len(parts) > 2:
            outputs.append((parts[1], parts[2]))
            arcpy.AddMessage("  wrote %s" % os.path.basename(parts[2]))
        elif tag == "RESULT" and len(parts) > 1:
            try:
                result = json.loads(parts[1])
            except ValueError:
                arcpy.AddWarning("Could not read the result line.")
        elif tag == "WARN" and len(parts) > 1:
            arcpy.AddWarning(parts[1])
        elif tag == "ERROR" and len(parts) > 1:
            failed = parts[1]
        else:
            arcpy.AddMessage(line)

    stderr = proc.stderr.read()
    code = proc.wait()

    if failed:
        if stderr:
            arcpy.AddMessage(stderr.strip()[-4000:])
        arcpy.AddError("basinkit: " + failed)
        raise arcpy.ExecuteError
    if code != 0:
        if stderr:
            arcpy.AddError(stderr.strip()[-4000:])
        arcpy.AddError(
            "basinkit_runner exited with code %d. If the message above says a "
            "module is missing, that interpreter does not have basinkit "
            "installed -- run 'Set Up BasinKit', which will build one."
            % code)
        raise arcpy.ExecuteError
    return outputs, result


#: Which geometry each layer the runner writes actually contains. JSONToFeatures
#: needs this told to it: Esri's documentation states that for a .geojson input
#: "you must select the geometry type", and that if the file holds none of the
#: requested type "the output feature class will be empty" -- with no error. So a
#: missing geometry type here would produce empty layers silently, which is the
#: single most common way a GIS tool wastes somebody's afternoon.
GEOMETRY = {"basin": "POLYGON", "subbasins": "POLYGON", "lakes": "POLYGON",
            "rivers": "POLYLINE"}


def add_to_map(outputs, add_layers=True):
    """Bring the runner's files into the project.

    GeoJSON is converted to a feature class in the default geodatabase, because
    a GeoJSON file is read-only to most of Pro. GeoTIFF is added as it is. CSV is
    left on disk: addDataFromPath returns a Layer and a table is not a layer.
    """
    added = []
    gdb = arcpy.env.workspace or arcpy.env.scratchGDB
    for kind, path in outputs:
        try:
            if kind == "vector":
                stem = os.path.splitext(os.path.basename(path))[0]
                name = arcpy.ValidateTableName(stem, gdb)
                if str(gdb).lower().endswith(".gdb"):
                    target = os.path.join(gdb, name)
                else:
                    # No geodatabase to write into -- leave a shapefile beside
                    # the GeoJSON rather than failing.
                    target = os.path.join(os.path.dirname(path), name + ".shp")
                geom = GEOMETRY.get(stem.lower(), "POLYGON")
                arcpy.conversion.JSONToFeatures(path, target, geom)
                # An empty result here means the geometry type was wrong. Say so
                # rather than handing over a layer with nothing in it.
                try:
                    n = int(arcpy.management.GetCount(target)[0])
                    if n == 0:
                        arcpy.AddWarning(
                            "%s converted to 0 features as %s. The GeoJSON is "
                            "still on disk at %s." % (stem, geom, path))
                    else:
                        arcpy.AddMessage("  %s: %s features" % (stem, format(n, ",")))
                except Exception:                       # noqa: BLE001
                    pass
                added.append(target)
            else:
                added.append(path)
        except Exception as exc:                        # noqa: BLE001
            arcpy.AddWarning("Could not convert %s (%s). The file is still on "
                             "disk." % (os.path.basename(path), exc))
            added.append(path)

    if not add_layers:
        return added
    try:
        aprx = arcpy.mp.ArcGISProject("CURRENT")
        m = aprx.activeMap
        if m is None:
            return added
        for item in added:
            if str(item).lower().endswith((".csv", ".png")):
                continue                    # a table or a figure, not a layer
            try:
                m.addDataFromPath(item)
            except Exception:                           # noqa: BLE001
                arcpy.AddWarning("Added to disk but not to the map: %s" % item)
    except Exception:                                   # noqa: BLE001
        pass                                            # running outside a project
    return added


def p(display, name, datatype="GPString", ptype="Required", direction="Input",
      default=None, multi=False, values=None):
    param = arcpy.Parameter(displayName=display, name=name, datatype=datatype,
                            parameterType=ptype, direction=direction,
                            multiValue=multi)
    if values:
        param.filter.type = "ValueList"
        param.filter.list = list(values)
    if default is not None:
        param.value = default
    return param


def point_params(backend=True, default_backend="auto"):
    """The outlet parameters every tool shares.

    ``default_backend`` exists because two tools cannot use 'auto': the
    sub-catchments and the Arc Hydro export both read the units the
    HydroBASINS traversal walked, and 'auto' refines anything below
    2,000 km2 onto the elevation model, which has no units. Those two
    offered 'auto' as their default and so failed on small catchments after
    the delineation had already been paid for.
    """
    out = [p("Outlet latitude", "lat", "GPDouble"),
           p("Outlet longitude", "lon", "GPDouble")]
    if backend:
        out.append(p("Delineation backend", "backend", default=default_backend,
                     values=BACKENDS))
    out.append(p("Output folder", "out", "DEFolder", direction="Input"))
    return out


def point_args(params, idx_backend=2, idx_out=3, default_backend="auto"):
    args = ["--lat", params[0].value, "--lon", params[1].value]
    if idx_backend is not None:
        args += ["--backend",
                 params[idx_backend].valueAsText or default_backend]
    args += ["--out", params[idx_out].valueAsText]
    return args


class BaseTool(object):
    category = ""

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        for prm in parameters:
            if prm.name == "lat" and prm.value is not None and not -90 <= prm.value <= 90:
                prm.setErrorMessage("Latitude must be between -90 and 90.")
            if prm.name == "lon" and prm.value is not None and not -180 <= prm.value <= 180:
                prm.setErrorMessage("Longitude must be between -180 and 180.")
        return

    def postExecute(self, parameters):
        return


# -------------------------------------------------------------------- tools

class Configure(BaseTool):
    def __init__(self):
        self.label = "Set Up BasinKit"
        self.description = (
            "Find a Python interpreter that has basinkit, or build one. Leave "
            "every parameter empty and run it: BasinKit looks for a suitable "
            "interpreter and, if it finds none, creates its own environment "
            "and installs basinkit into it. ArcGIS Pro's own Python is never "
            "modified.")
        self.category = "0 Configuration"

    def getParameterInfo(self):
        return [p("Python executable (leave empty to set one up)", "python",
                  "DEFile", ptype="Optional"),
                p("Build an environment if none is found", "auto", "GPBoolean",
                  ptype="Optional", default=True),
                p("Only test the current setting", "test_only", "GPBoolean",
                  ptype="Optional", default=False)]

    def _save(self, exe):
        with open(PYTHON_SETTING, "w", encoding="utf-8") as fh:
            fh.write(exe)
        arcpy.AddMessage("Saved: %s" % exe)

    def execute(self, parameters, messages):
        chosen = parameters[0].valueAsText
        auto = parameters[1].value if parameters[1].value is not None else True
        test_only = bool(parameters[2].value)

        if test_only:
            exe = resolve_python()
        elif chosen:
            arcpy.AddMessage("Checking %s" % chosen)
            ver = probe(chosen)
            if ver is None:
                arcpy.AddError(
                    "That interpreter does not have basinkit. Run "
                    "'pip install \"basinkit[all]\"' with it, or leave this "
                    "parameter empty and let BasinKit build its own.")
                raise arcpy.ExecuteError
            arcpy.AddMessage("  basinkit %s" % ver)
            self._save(chosen)
            exe = chosen
        else:
            exe = None
            arcpy.AddMessage("Looking for an interpreter that has basinkit.")
            for cand in candidates():
                ver = probe(cand)
                arcpy.AddMessage("  %s  %s"
                                 % (cand, ("basinkit " + ver) if ver else "no"))
                if ver:
                    exe = cand
                    break
            if exe:
                self._save(exe)
            elif auto:
                arcpy.AddMessage("None found. Looking for a Python to build one from.")
                base, seen = base_python()
                if base is None:
                    if seen is None:
                        arcpy.AddError("No Python interpreter was found at all.")
                    else:
                        arcpy.AddError(
                            "The newest Python found is %d.%d, and basinkit needs "
                            "%d.%d or newer." % (seen[0], seen[1],
                                                 MIN_PYTHON[0], MIN_PYTHON[1]))
                    arcpy.AddError(_manual_steps())
                    raise arcpy.ExecuteError
                exe = build_environment(base, _managed_env_dir())
                ver = probe(exe)
                if ver is None:
                    arcpy.AddError("The environment was built but basinkit "
                                   "still does not import from it.")
                    raise arcpy.ExecuteError
                arcpy.AddMessage("basinkit %s is installed." % ver)
                self._save(exe)
            else:
                arcpy.AddError(
                    "No interpreter with basinkit was found. Tick 'Build an "
                    "environment if none is found', or install basinkit "
                    "yourself and point this tool at that python.exe.")
                raise arcpy.ExecuteError

        arcpy.AddMessage("Testing %s" % exe)
        old = os.environ.get("BASINKIT_PYTHON")
        os.environ["BASINKIT_PYTHON"] = exe
        try:
            _, res = run(["selftest"], messages)
        finally:
            if old is None:
                os.environ.pop("BASINKIT_PYTHON", None)
            else:
                os.environ["BASINKIT_PYTHON"] = old
        arcpy.AddMessage("basinkit %s on Python %s"
                         % (res.get("basinkit"), res.get("python")))
        missing = []
        for mod, ver in (res.get("dependencies") or {}).items():
            if str(ver).startswith("MISSING"):
                arcpy.AddWarning("  %s: %s" % (mod, ver))
                missing.append(mod)
            else:
                arcpy.AddMessage("  %s %s" % (mod, ver))
        if missing:
            arcpy.AddWarning(
                "Install the missing packages with: \"%s\" -m pip install %s"
                % (exe, " ".join(missing)))
        else:
            arcpy.AddMessage("Ready. Open 1 Comprehensive Analysis to run.")


class Delineate(BaseTool):
    def __init__(self):
        self.label = "Delineate Basin"
        self.description = ("The upstream catchment of one coordinate, as a "
                            "polygon. No account and no API key.")
        self.category = "2 Basin Delineation"

    def getParameterInfo(self):
        return point_params()

    def execute(self, parameters, messages):
        outs, res = run(["delineate"] + point_args(parameters), messages)
        add_to_map(outs)
        arcpy.AddMessage("Basin area: %s km2" % format(res.get("area_km2", 0), ",.1f"))


class SubBasins(BaseTool):
    def __init__(self):
        self.label = "Sub-Catchments"
        self.description = ("The units the basin is assembled from, each carrying "
                            "NEXT_DOWN -- the routing table a model wants.")
        self.category = "2 Basin Delineation"

    def getParameterInfo(self):
        return point_params(default_backend="hydrobasins")

    def execute(self, parameters, messages):
        outs, res = run(
            ["subbasins"]
            + point_args(parameters, default_backend="hydrobasins"), messages)
        add_to_map(outs)


class RiversLakes(BaseTool):
    def __init__(self):
        self.label = "Rivers and Lakes"
        self.description = "River reaches with stream order and discharge, and lakes."
        self.category = "2 Basin Delineation"

    def getParameterInfo(self):
        prm = point_params()
        prm.insert(3, p("Minimum stream order", "min_order", "GPLong",
                        ptype="Optional", default=0))
        prm.insert(4, p("Also fetch lakes", "lakes", "GPBoolean",
                        ptype="Optional", default=True))
        return prm

    def execute(self, parameters, messages):
        args = ["rivers", "--lat", parameters[0].value, "--lon", parameters[1].value,
                "--backend", parameters[2].valueAsText or "auto",
                "--min-order", parameters[3].value or 0,
                "--out", parameters[5].valueAsText]
        if parameters[4].value:
            args.append("--lakes")
        outs, res = run(args, messages)
        add_to_map(outs)


class Terrain(BaseTool):
    def __init__(self):
        self.label = "Terrain Surfaces"
        self.description = ("One elevation download, twelve surfaces derived from "
                            "it: hillshade, slope, aspect, curvature, TPI, TRI, "
                            "roughness, landform, flow accumulation, channels, "
                            "wetness index and height above nearest drainage.")
        self.category = "3 Surface Derivatives"

    def getParameterInfo(self):
        prm = point_params()
        prm.insert(3, p("Elevation model", "dem_product", default="cop30",
                        values=DEM_PRODUCTS))
        prm.insert(4, p("Surfaces", "surfaces", multi=True, values=SURFACES,
                        default="hillshade;slope;aspect"))
        prm.insert(5, p("Pixel budget (0 = the package default)", "max_pixels",
                        "GPLong", ptype="Optional", default=0))
        return prm

    def execute(self, parameters, messages):
        chosen = (parameters[4].valueAsText or "").split(";")
        chosen = [s.strip() for s in chosen if s.strip()]
        args = ["terrain", "--lat", parameters[0].value, "--lon", parameters[1].value,
                "--backend", parameters[2].valueAsText or "auto",
                "--dem-product", parameters[3].valueAsText or "cop30",
                "--out", parameters[6].valueAsText]
        if chosen:
            args += ["--surfaces"] + chosen
        if parameters[5].value:
            args += ["--max-pixels", parameters[5].value]
        outs, res = run(args, messages)
        add_to_map(outs)


class Layers(BaseTool):
    def __init__(self):
        self.label = "Land Cover, Soil and Surface Water"
        self.description = ("Open Earth observation layers clipped and masked to "
                            "the basin polygon, not to its bounding box.")
        self.category = "4 Thematic Rasters"

    def getParameterInfo(self):
        prm = point_params()
        prm.insert(3, p("Layers", "layers", multi=True,
                        values=["landcover", "soil", "surface_water"],
                        default="landcover"))
        prm.insert(4, p("Land cover source", "landcover_source", ptype="Optional",
                        default="worldcover", values=["worldcover", "esri"]))
        prm.insert(5, p("Soil property", "soil_property", ptype="Optional",
                        default="clay", values=SOIL_PROPERTIES))
        prm.insert(6, p("Soil depth", "soil_depth", ptype="Optional",
                        default="0-5cm", values=SOIL_DEPTHS))
        prm.insert(7, p("Pixel budget (0 = the package default)", "max_pixels",
                        "GPLong", ptype="Optional", default=0))
        return prm

    def updateParameters(self, parameters):
        chosen = (parameters[3].valueAsText or "")
        parameters[4].enabled = "landcover" in chosen
        parameters[5].enabled = parameters[6].enabled = "soil" in chosen
        return

    def execute(self, parameters, messages):
        chosen = [s.strip() for s in (parameters[3].valueAsText or "").split(";") if s.strip()]
        args = ["layers", "--lat", parameters[0].value, "--lon", parameters[1].value,
                "--backend", parameters[2].valueAsText or "auto",
                "--landcover-source", parameters[4].valueAsText or "worldcover",
                "--soil-property", parameters[5].valueAsText or "clay",
                "--soil-depth", parameters[6].valueAsText or "0-5cm",
                "--out", parameters[8].valueAsText]
        if chosen:
            args += ["--layers"] + chosen
        if parameters[7].value:
            args += ["--max-pixels", parameters[7].value]
        outs, res = run(args, messages)
        add_to_map(outs)


class Morphometry(BaseTool):
    def __init__(self):
        self.label = "Morphometric Parameters"
        self.description = ("Forty-two named parameters in three sets -- linear, "
                            "areal and relief -- plus the network by Strahler "
                            "order. Streams are counted as Strahler streams, not "
                            "as the reaches a river dataset splits them into.")
        self.category = "5 Morphometry and Drainage Network"

    def getParameterInfo(self):
        return point_params()

    def execute(self, parameters, messages):
        outs, res = run(["morphometry"] + point_args(parameters), messages)
        add_to_map(outs)


class Zonal(BaseTool):
    def __init__(self):
        self.label = "Zonal Statistics"
        self.description = "Any raster summarised inside any other raster's classes."
        self.category = "5 Morphometry and Drainage Network"

    def getParameterInfo(self):
        prm = point_params()
        prm.insert(3, p("Values raster", "values", "DERasterDataset"))
        prm.insert(4, p("Zones raster (blank = the basin's land cover)", "zones",
                        "DERasterDataset", ptype="Optional"))
        return prm

    def execute(self, parameters, messages):
        args = ["zonal", "--lat", parameters[0].value, "--lon", parameters[1].value,
                "--backend", parameters[2].valueAsText or "auto",
                "--values", parameters[3].valueAsText,
                "--out", parameters[5].valueAsText]
        if parameters[4].valueAsText:
            args += ["--zones", parameters[4].valueAsText]
        outs, res = run(args, messages)
        add_to_map(outs)


class Suitability(BaseTool):
    def __init__(self):
        self.label = "DEM Suitability Assessment"
        self.description = ("Five tests against the elevation model's own stated "
                            "vertical error, with a per-cell map of where the "
                            "answer is supported and where it is not.")
        self.category = "6 Quality Assessment"

    def getParameterInfo(self):
        prm = point_params()
        prm.insert(3, p("Also write the per-cell support map", "support_map",
                        "GPBoolean", ptype="Optional", default=True))
        return prm

    def execute(self, parameters, messages):
        args = ["suitability", "--lat", parameters[0].value, "--lon", parameters[1].value,
                "--backend", parameters[2].valueAsText or "auto",
                "--out", parameters[4].valueAsText]
        if parameters[3].value:
            args.append("--support-map")
        outs, res = run(args, messages)
        add_to_map(outs)
        grade = res.get("grade")
        say = arcpy.AddWarning if grade in ("LIMITED", "UNSUITABLE") else arcpy.AddMessage
        say("Grade: %s" % grade)
        if res.get("unmet"):
            arcpy.AddWarning("Tests not met: %s" % ", ".join(res["unmet"]))
        if res.get("statement"):
            arcpy.AddMessage(res["statement"])


class DataQuality(BaseTool):
    def __init__(self):
        self.label = "Data Quality Report"
        self.description = ("New in 0.7.0. Grades elevation, land cover, soil, "
                            "rainfall, surface water and the delineation itself, "
                            "each against an independently produced source rather "
                            "than against itself. Layers for which no published "
                            "threshold exists come back ungraded, with the reason "
                            "stated rather than a cut-off invented.")
        self.category = "6 Quality Assessment"

    def getParameterInfo(self):
        return point_params()

    def execute(self, parameters, messages):
        outs, res = run(["quality"] + point_args(parameters), messages)
        add_to_map(outs)
        arcpy.AddMessage("Overall: %s" % res.get("overall"))
        for layer, grade in (res.get("grades") or {}).items():
            line = "  %-14s %s" % (layer, grade)
            if grade in ("LIMITED", "UNSUITABLE"):
                arcpy.AddWarning(line)
            else:
                arcpy.AddMessage(line)


class Report(BaseTool):
    def __init__(self):
        self.label = "Basin Report (PDF)"
        self.description = ("An eight-page PDF: the suitability grade on the cover, "
                            "every morphometric parameter with its symbol and "
                            "original reference, the channel network against "
                            "Horton's laws, and a methods page carrying software "
                            "versions and licences.")
        self.category = "7 Report Generation"

    def getParameterInfo(self):
        prm = point_params()
        prm.insert(3, p("Title", "title", ptype="Optional"))
        return prm

    def execute(self, parameters, messages):
        args = ["report", "--lat", parameters[0].value, "--lon", parameters[1].value,
                "--backend", parameters[2].valueAsText or "auto",
                "--out", parameters[4].valueAsText]
        if parameters[3].valueAsText:
            args += ["--title", parameters[3].valueAsText]
        outs, res = run(args, messages)
        arcpy.AddMessage("Report: %s" % res.get("report"))


class Everything(BaseTool):
    def __init__(self):
        self.label = "Complete Basin Analysis"
        self.description = (
            "One coordinate in. Seventy analyses out, plus a collage, an "
            "illustrated PDF report and a manifest that re-runs. Writes the "
            "basin, sub-catchments, rivers, lakes, elevation, hillshade and "
            "land cover as GIS layers and adds them to the map. Expect twenty "
            "minutes to an hour depending on basin size and the pixel budget.")
        self.category = "1 Comprehensive Analysis"

    def getParameterInfo(self):
        prm = point_params()
        prm.insert(3, p("Title for the report and collage", "title", ptype="Optional"))
        prm.insert(4, p("Pixel budget for the elevation model", "max_pixels", "GPLong",
                        ptype="Optional", default=4000000))
        prm.insert(5, p("Pixel budget for satellite imagery", "sat_pixels", "GPLong",
                        ptype="Optional", default=1200000))
        prm.insert(6, p("Channel-initiation threshold, km²", "stream_km2", "GPDouble",
                        ptype="Optional", default=5.0))
        prm.insert(7, p("Climate window: first year", "clim_start", "GPLong",
                        ptype="Optional", default=2000))
        prm.insert(8, p("Climate window: last year", "clim_end", "GPLong",
                        ptype="Optional", default=2024))
        prm.insert(9, p("Skip satellite imagery (much faster)", "skip_satellite",
                        "GPBoolean", ptype="Optional", default=False))
        prm.insert(10, p("Also write every layer into one folder", "download_all",
                         "GPBoolean", ptype="Optional", default=False))
        prm.insert(11, p("Also export an interactive 3D page", "export_3d",
                         "GPBoolean", ptype="Optional", default=False))
        return prm

    def updateMessages(self, parameters):
        BaseTool.updateMessages(self, parameters)
        cs, ce = parameters[7], parameters[8]
        if cs.value and ce.value and ce.value <= cs.value:
            ce.setErrorMessage("The last year must be after the first year.")
        return

    def execute(self, parameters, messages):
        args = ["everything",
                "--lat", parameters[0].value, "--lon", parameters[1].value,
                "--backend", parameters[2].valueAsText or "auto",
                "--stream-km2", parameters[6].value or 5.0,
                "--clim-start", parameters[7].value or 2000,
                "--clim-end", parameters[8].value or 2024,
                "--out", parameters[12].valueAsText]
        if parameters[3].valueAsText:
            args += ["--title", parameters[3].valueAsText]
        if parameters[4].value:
            args += ["--max-pixels", parameters[4].value]
        if parameters[5].value:
            args += ["--sat-pixels", parameters[5].value]
        if parameters[9].value:
            args.append("--skip-satellite")
        if parameters[10].value:
            args.append("--download-all")
        if parameters[11].value:
            args.append("--export-3d")

        arcpy.AddMessage("This runs the whole sweep. Progress appears below as each "
                         "analysis finishes; a step whose data server is busy is "
                         "retried once and then recorded as incomplete rather than "
                         "stopping the run.")
        outs, res = run(args, messages)

        # only the GIS layers belong on the map; the report, collage, manifest
        # and CSVs are files the user opens themselves
        layers = [(k, v) for k, v in outs
                  if k in ("vector", "raster")
                  and not str(v).lower().endswith((".pdf", ".png", ".json", ".csv", ".html"))]
        add_to_map(layers)

        arcpy.AddMessage("")
        arcpy.AddMessage("%s analyses completed, %s incomplete, %s skipped."
                         % (res.get("analyses_completed"), res.get("analyses_failed"),
                            res.get("analyses_skipped")))
        grade = res.get("overall_grade")
        say = arcpy.AddWarning if grade in ("LIMITED", "UNSUITABLE") else arcpy.AddMessage
        say("Overall data-quality grade for this basin: %s" % grade)
        arcpy.AddMessage("Basin area: %s km2" % format(res.get("area_km2") or 0, ",.1f"))
        arcpy.AddMessage("GIS layers added: %s" % res.get("gis_layers"))
        for label, key in (("Report", "report"), ("Collage", "collage"),
                           ("Manifest", "manifest")):
            if res.get(key):
                arcpy.AddMessage("%-9s %s" % (label + ":", res[key]))


class Landscape(BaseTool):
    def __init__(self):
        self.label = "Landscape Form (Chi and Channel Steepness)"
        self.description = (
            "chi, normalised channel steepness, concavity and knickpoints. "
            "Whether the landscape is still adjusting, or has settled. "
            "k_sn agrees with TopoToolbox to within 6% at every quantile.")
        self.category = "5 Morphometry and Drainage Network"

    def getParameterInfo(self):
        prm = point_params()
        prm.insert(3, p("Channel-initiation area (km2)", "min_area_km2", "GPDouble",
                        ptype="Optional", default=1.0))
        prm.insert(4, p("Reference concavity", "theta_ref", "GPDouble",
                        ptype="Optional", default=0.45))
        prm.insert(5, p("Smoothing window for the concavity fit (m)", "smooth_m",
                        "GPDouble", ptype="Optional", default=500.0))
        prm.insert(6, p("Pixel budget for the DEM", "max_pixels", "GPLong",
                        ptype="Optional", default=0))
        return prm

    def execute(self, parameters, messages):
        args = ["landscape", "--lat", parameters[0].value, "--lon", parameters[1].value,
                "--backend", parameters[2].valueAsText or "auto",
                "--min-area-km2", parameters[3].value or 1.0,
                "--theta-ref", parameters[4].value or 0.45,
                "--smooth-m", 500.0 if parameters[5].value is None
                else parameters[5].value,
                "--max-pixels", parameters[6].value or 0,
                "--out", parameters[7].valueAsText]
        outs, res = run(args, messages)
        add_to_map(outs)


class ArcHydro(BaseTool):
    def __init__(self):
        self.label = "Export for Arc Hydro"
        self.description = (
            "The sub-catchments and river reaches with Arc Hydro field names: "
            "HydroID, HydroCode, NextDownID, AreaSqKm. A GeoPackage with "
            "Catchment and DrainageLine layers, plus the same two tables as CSV. "
            "A renaming, not a computation -- every value is one basinkit "
            "already holds.")
        self.category = "8 Model Coupling"

    def getParameterInfo(self):
        prm = point_params(default_backend="hydrobasins")
        prm.insert(3, p("Minimum stream order", "min_order", "GPLong",
                        ptype="Optional", default=0))
        return prm

    def execute(self, parameters, messages):
        args = ["archydro", "--lat", parameters[0].value, "--lon", parameters[1].value,
                "--backend", parameters[2].valueAsText or "hydrobasins",
                "--min-order", parameters[3].value or 0,
                "--out", parameters[4].valueAsText]
        outs, res = run(args, messages)
        add_to_map(outs)


class Toolbox(object):
    def __init__(self):
        self.label = "BasinKit"
        self.alias = "basinkit"
        self.description = (
            "Click a river anywhere on Earth and get an analysis-ready basin "
            "package. Nineteen open datasets, no account, no API key. "
            "Not affiliated with or endorsed by Esri.")
        self.tools = [Configure, Everything, Delineate, SubBasins, RiversLakes, Terrain,
                      Layers, Morphometry, Landscape, Zonal, Suitability, DataQuality,
                      Report, ArcHydro]
