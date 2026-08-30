"""Static check of the QGIS plugin against stubbed QGIS bindings.

Proves: every module imports, classFactory works, the provider registers three
algorithms, every initAlgorithm runs, every required override exists and
createInstance returns a distinct object. It cannot prove behaviour inside QGIS.
"""
import os, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "qgis_stub"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

failures = []

def check(label, condition, detail=""):
    print(f"{'OK  ' if condition else 'FAIL'} {label}" + (f"  {detail}" if detail else ""))
    if not condition:
        failures.append(label)

version = os.environ.get("STUB_QGIS_VERSION", "34400")
print(f"=== stubbed QGIS_VERSION_INT = {version} ===")

for name in list(sys.modules):
    if name.startswith(("qgis_plugin", "qgis")):
        del sys.modules[name]

import qgis_plugin as basinkit_qgis
check("package imports", True)

plugin = basinkit_qgis.classFactory(iface=None)
check("classFactory returns a plugin", plugin is not None, type(plugin).__name__)
check("has initProcessing", hasattr(plugin, "initProcessing"))
check("has initGui", hasattr(plugin, "initGui"))
check("has unload", hasattr(plugin, "unload"))

plugin.initProcessing()
from qgis.core import QgsApplication
registered = QgsApplication.processingRegistry().providers
check("provider registered", len(registered) == 1, f"{len(registered)}")

provider = registered[0]
provider.loadAlgorithms()
check("provider id", provider.id() == "basinkit", provider.id())
check("three algorithms", len(provider.algorithms) == 3,
      ", ".join(a.name() for a in provider.algorithms))

for algorithm in provider.algorithms:
    label = algorithm.name()
    for method in ("name", "displayName", "group", "groupId", "createInstance",
                   "shortHelpString", "shortDescription", "initAlgorithm",
                   "processAlgorithm"):
        check(f"{label}: has {method}", hasattr(algorithm, method))

    check(f"{label}: name is lowercase alnum", label.isalnum() and label.islower(), label)
    check(f"{label}: groupId is lowercase alnum",
          algorithm.groupId().isalnum() and algorithm.groupId().islower())

    clone = algorithm.createInstance()
    check(f"{label}: createInstance is a new object",
          clone is not algorithm and type(clone) is type(algorithm))

    clone.initAlgorithm()
    names = [p.name for p in clone.parameters]
    check(f"{label}: initAlgorithm added parameters", len(names) > 0, ", ".join(names))
    check(f"{label}: parameter names unique", len(names) == len(set(names)))
    check(f"{label}: help is non-trivial", len(algorithm.shortHelpString()) > 80)

plugin.unload()
check("provider unregistered after unload",
      len(QgsApplication.processingRegistry().providers) == 0)

# The dependency path must never raise on import, only when an algorithm runs.
from qgis_plugin import deps
check("deps.python_command works", isinstance(deps.python_command(), str),
      deps.python_command())
check("deps reports basinkit present", deps.status_message() is None
      or "basinkit" in deps.status_message())

print()
print("FAILURES:", failures if failures else "none")
sys.exit(1 if failures else 0)
