"""Run the algorithms' real processAlgorithm bodies against stubbed QGIS.

This is the part that matters: the wiring test proves the plugin loads, this
proves the data actually flows through to a written output.
"""
import os, pathlib, sys, tempfile, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "qgis_stub"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from qgis.core import (QgsCoordinateReferenceSystem, QgsProcessingContext,
                       QgsProcessingFeedback)

failures = []
def check(label, ok, detail=""):
    print(f"{'OK  ' if ok else 'FAIL'} {label}" + (f"  {detail}" if detail else ""), flush=True)
    if not ok: failures.append(label)


class Point:
    def __init__(self, x, y): self._x, self._y = x, y
    def x(self): return self._x
    def y(self): return self._y


class Sink:
    def __init__(self): self.features = []
    def addFeature(self, feature, flags=None):
        self.features.append(feature); return True


# ---------------------------------------------------------------- delineate
from qgis_plugin.processing_provider.algorithms.delineate import DelineateBasinAlgorithm

alg = DelineateBasinAlgorithm()
alg.initAlgorithm()
sink = Sink()
alg.parameterAsPoint = lambda p, n, c, crs=None: Point(87.150, 26.870)
alg.parameterAsPointCrs = lambda p, n, c: QgsCoordinateReferenceSystem("EPSG:4326")
alg.parameterAsEnum = lambda p, n, c: 1                 # hydrobasins
alg.parameterAsDouble = lambda p, n, c: 5.0 if n == "SNAP_KM" else 10.0
alg.parameterAsSink = lambda *a, **k: (sink, "memory:basin")

context, feedback = QgsProcessingContext(), QgsProcessingFeedback()
result = alg.processAlgorithm({}, context, feedback)

check("delineate returns the output key", "OUTPUT" in result, str(result))
check("delineate wrote one feature", len(sink.features) == 1)
feature = sink.features[0]
area = feature._attributes[0]
check("delineate area matches the published Koshi figure",
      50_000 < area < 58_000, f"{area:,.0f} km2 (published ~54,100)")
check("delineate geometry is real WKT",
      feature.geometry().asWkt().upper().startswith(("POLYGON", "MULTIPOLYGON")),
      feature.geometry().asWkt()[:28])
check("delineate recorded provenance",
      feature._attributes[2] == "hydrobasins" and bool(feature._attributes[3]),
      f"{feature._attributes[2]} / {feature._attributes[3][:40]}")
check("delineate recorded the licence", "CC BY" in str(feature._attributes[4]),
      str(feature._attributes[4]))
check("delineate logged progress", feedback.progress == 100)

wkt_koshi = feature.geometry().asWkt()

# ------------------------------------------------------- riverbank snapping
alg2 = DelineateBasinAlgorithm(); alg2.initAlgorithm()
sink2 = Sink()
alg2.parameterAsPoint = lambda p, n, c, crs=None: Point(6.110, 51.840)   # Rhine @ Lobith
alg2.parameterAsPointCrs = lambda p, n, c: QgsCoordinateReferenceSystem("EPSG:4326")
alg2.parameterAsEnum = lambda p, n, c: 1
alg2.parameterAsDouble = lambda p, n, c: 5.0 if n == "SNAP_KM" else 10.0
alg2.parameterAsSink = lambda *a, **k: (sink2, "memory:rhine")
fb2 = QgsProcessingFeedback()
alg2.processAlgorithm({}, QgsProcessingContext(), fb2)
rhine_area = sink2.features[0]._attributes[0]
check("riverbank outlet snaps to the main stem",
      140_000 < rhine_area < 180_000, f"{rhine_area:,.0f} km2 (published 160,800)")
check("the snap is surfaced as a warning to the user",
      any("bank of a much larger river" in w for w in fb2.warnings),
      f"{len(fb2.warnings)} warning(s)")

# ------------------------------------------------------------ fetch layers
from qgis_plugin.processing_provider.algorithms.fetch_layers import FetchBasinLayersAlgorithm


class Source:
    def __init__(self, wkt):
        from qgis.core import QgsFeature, QgsGeometry
        f = QgsFeature(); f.setGeometry(QgsGeometry.fromWkt(wkt))
        self._features = [f]
    def getFeatures(self):
        return self._features


folder = tempfile.mkdtemp()
alg3 = FetchBasinLayersAlgorithm(); alg3.initAlgorithm()
alg3.parameterAsSource = lambda p, n, c: Source(wkt_koshi)
alg3.parameterAsEnums = lambda p, n, c: [0, 5]                 # DEM + rivers
alg3.parameterAsInt = lambda p, n, c: {"START_YEAR": 2022, "END_YEAR": 2022,
                                       "MAX_MEGAPIXELS": 20}[n]
alg3.parameterAsString = lambda p, n, c: folder
ctx3, fb3 = QgsProcessingContext(), QgsProcessingFeedback()
result3 = alg3.processAlgorithm({}, ctx3, fb3)

check("fetch wrote layers", result3.get("LAYERS_WRITTEN", 0) >= 1, str(result3))
files = sorted(os.listdir(folder))
check("DEM written", "dem.tif" in files, ", ".join(files))
check("licences written", "LICENSES.txt" in files)
check("layers queued for the project, not added directly", len(ctx3.loaded) >= 1,
      f"{len(ctx3.loaded)} queued")

import rasterio, numpy as np
with rasterio.open(os.path.join(folder, "dem.tif")) as src:
    check("exported DEM declares nodata", src.nodata is not None, str(src.nodata))
    band = src.read(1, masked=True)
    masked = float(np.asarray(band.mask).mean())
    check("exported DEM is masked to the polygon", 0.3 < masked < 0.7, f"{masked:.3f}")

# -------------------------------------------------------------- statistics
from qgis_plugin.processing_provider.algorithms.statistics import BasinStatisticsAlgorithm

report = os.path.join(folder, "report.html")
alg4 = BasinStatisticsAlgorithm(); alg4.initAlgorithm()
alg4.parameterAsSource = lambda p, n, c: Source(wkt_koshi)
alg4.parameterAsBoolean = lambda p, n, c: False
alg4.parameterAsFileOutput = lambda p, n, c: report
result4 = alg4.processAlgorithm({}, QgsProcessingContext(), QgsProcessingFeedback())

check("statistics returns area", 50_000 < result4.get("area_km2", 0) < 58_000,
      f"{result4.get('area_km2'):,}")
check("statistics returns terrain", result4.get("elev_max_m", 0) > 8000,
      f"max {result4.get('elev_max_m')} m")
check("report written", os.path.exists(report) and os.path.getsize(report) > 500)

print()
print("FAILURES:", failures if failures else "none")
sys.exit(1 if failures else 0)
