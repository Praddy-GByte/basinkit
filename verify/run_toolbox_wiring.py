# -*- coding: utf-8 -*-
"""Check every ArcGIS Pro tool's parameters and command line without ArcGIS Pro.

The toolbox and the runner are two files that have to agree. A tool that reads
the wrong parameter index, or sends a flag the runner does not define, fails only
once someone clicks Run inside ArcGIS Pro -- which is the slowest possible place
to find out. This loads BasinKit.pyt against a stub arcpy, instantiates every
tool, builds its parameters, fills them with sample values, captures the command
line it would run, and parses that command line with the runner's own parser.

    python verify/run_toolbox_wiring.py

Exits non-zero on the first disagreement and prints what disagreed. No network,
no arcpy, no ArcGIS licence.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOLBOX_DIR = os.path.join(ROOT, "arcgis_toolbox")
PYT = os.path.join(TOOLBOX_DIR, "BasinKit.pyt")
RUNNER = os.path.join(TOOLBOX_DIR, "basinkit_runner.py")

SAMPLES = {"GPDouble": 45.11188, "GPLong": 3, "GPBoolean": True,
           "GPString": None, "DEFolder": None, "DERasterDataset": None,
           "GPRasterLayer": None, "DEFile": None}
NAMED = {"lat": 45.11188, "lon": -110.79438, "out": os.path.join("C:\\", "work")}

# Tools that legitimately never call the runner. Their execute() is not run,
# because it acts on the machine rather than building a command line.
NO_RUNNER = {
    "Set Up BasinKit": "it builds a Python environment instead of calling the "
                       "runner, and outside ArcGIS Pro it correctly refuses "
                       "because there is no interpreter to find",
}


class _Filter:
    def __init__(self):
        self.type = None
        self.list = []


class _Parameter:
    """Just enough of arcpy.Parameter for getParameterInfo and execute."""

    def __init__(self, displayName="", name="", datatype="GPString",
                 parameterType="Required", direction="Input", multiValue=False):
        self.displayName = displayName
        self.name = name
        self.datatype = datatype
        self.parameterType = parameterType
        self.direction = direction
        self.multiValue = multiValue
        self.filter = _Filter()
        self._value = None
        self.errors = []

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, v):
        self._value = v

    @property
    def valueAsText(self):
        return None if self._value is None else str(self._value)

    def setErrorMessage(self, msg):
        self.errors.append(msg)


class _ExecuteError(Exception):
    pass


def _stub_arcpy():
    m = types.ModuleType("arcpy")
    m.Parameter = _Parameter
    m.ExecuteError = _ExecuteError
    m.AddMessage = lambda *a, **k: None
    m.AddWarning = lambda *a, **k: None
    m.AddError = lambda *a, **k: None
    m.SetProgressorLabel = lambda *a, **k: None
    m.env = types.SimpleNamespace(workspace=None, overwriteOutput=True)
    m.management = types.SimpleNamespace()
    m.conversion = types.SimpleNamespace()
    m.mp = types.SimpleNamespace(ArcGISProject=lambda *a, **k: None)
    m.Exists = lambda *a, **k: False
    return m


def _load(path, name):
    # .pyt is not a suffix Python's importer knows, so the loader is named.
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_file_location(name, path, loader=loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _fill(params):
    for prm in params:
        if prm.value is not None:                 # a default the tool set itself
            continue
        if prm.name in NAMED:
            prm.value = NAMED[prm.name]
        elif prm.filter.list:
            prm.value = prm.filter.list[0]
        elif prm.datatype in SAMPLES and SAMPLES[prm.datatype] is not None:
            prm.value = SAMPLES[prm.datatype]
        else:
            prm.value = os.path.join("C:\\", "work", prm.name)
    return params


def main():
    sys.modules["arcpy"] = _stub_arcpy()
    tb = _load(PYT, "basinkit_pyt")
    runner = _load(RUNNER, "basinkit_runner_under_test")
    parser = runner.build_parser()

    captured = []
    tb.run = lambda argv, messages=None: (captured.append(list(argv)), ([], {}))[1]
    tb.add_to_map = lambda *a, **k: None

    toolbox = tb.Toolbox()
    tools = list(toolbox.tools)
    if not tools:
        print("FAIL: the toolbox lists no tools")
        return 1
    print("%d tools in %s" % (len(tools), os.path.basename(PYT)))

    labels, failures = {}, []
    for cls in tools:
        tool = cls()
        label = getattr(tool, "label", "")
        cat = getattr(tool, "category", "")
        desc = getattr(tool, "description", "")
        if not label:
            failures.append("%s has no label" % cls.__name__)
        if not cat:
            failures.append("%s (%s) has no category" % (cls.__name__, label))
        if not desc:
            failures.append("%s (%s) has no description" % (cls.__name__, label))
        if label in labels:
            failures.append("two tools share the label %r: %s and %s"
                            % (label, labels[label], cls.__name__))
        labels[label] = cls.__name__

        params = tool.getParameterInfo()
        names = [prm.name for prm in params]
        if len(names) != len(set(names)):
            failures.append("%s repeats a parameter name: %s" % (label, names))
        tool.updateParameters(params)
        _fill(params)
        tool.updateMessages(params)
        for prm in params:
            if prm.errors:
                failures.append("%s: validation rejected its own sample value "
                                "for %s: %s" % (label, prm.name, prm.errors))

        if label in NO_RUNNER:
            print("  %-46s not executed: %s" % (label, NO_RUNNER[label]))
            continue

        captured.clear()
        try:
            tool.execute(params, None)
        except _ExecuteError as exc:
            failures.append("%s raised ExecuteError: %s" % (label, exc))
            continue
        except Exception as exc:                       # noqa: BLE001
            failures.append("%s raised %s: %s" % (label, exc.__class__.__name__, exc))
            continue

        if not captured:
            print("  %-46s no runner call (nothing to check)" % label)
            continue
        for argv in captured:
            argv = [str(a) for a in argv]
            try:
                ns = parser.parse_args(argv)
            except SystemExit:
                failures.append("%s builds a command line the runner will not "
                                "accept: %s" % (label, " ".join(argv)))
                continue
            if getattr(ns, "func", None) is None:
                failures.append("%s: subcommand %r has no handler" % (label, argv[0]))
            print("  %-46s %s" % (label, " ".join(argv)))

    if failures:
        print("\n%d problem(s):" % len(failures))
        for f in failures:
            print("  - " + f)
        return 1
    print("\nEvery tool's parameters and command line agree with the runner.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
