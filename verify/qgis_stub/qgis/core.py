"""Minimal stand-ins for the QGIS classes the plugin touches.

QGIS cannot be installed here, so this exists to prove the plugin at least
imports, that every algorithm's initAlgorithm runs, and that every parameter
constructor is called with an argument list QGIS would accept. It is a
signature check, not a behaviour check.
"""
import os


class _Enum:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class Qgis:
    QGIS_VERSION_INT = int(os.environ.get("STUB_QGIS_VERSION", "34400"))
    WkbType = _Enum(Polygon="Polygon", MultiPolygon="MultiPolygon",
                    LineString="LineString", Point="Point")
    ProcessingSourceType = _Enum(VectorPolygon="VectorPolygon",
                                 VectorAnyGeometry="VectorAnyGeometry")
    MessageLevel = _Enum(Info=0, Warning=1, Critical=2, Success=3)


class QgsWkbTypes:
    Polygon = "Polygon"; MultiPolygon = "MultiPolygon"
    LineString = "LineString"; Point = "Point"


class QgsProcessing:
    TypeVectorPolygon = "TypeVectorPolygon"


class QgsProcessingUtils:
    LayerHint = _Enum(Raster="Raster", Vector="Vector", UnknownType="Unknown")


class QgsProcessingException(Exception):
    pass


class QgsCoordinateReferenceSystem:
    def __init__(self, definition=""):
        self._definition = definition

    def isValid(self):
        return bool(self._definition)


class QgsField:
    def __init__(self, name, kind=None, *a, **kw):
        self.name, self.kind = name, kind


class QgsFields(list):
    def append(self, field):
        super().append(field)
        return True


class QgsGeometry:
    def __init__(self, wkt=""):
        self._wkt = wkt

    @staticmethod
    def fromWkt(wkt):
        return QgsGeometry(wkt)

    def asWkt(self):
        return self._wkt

    def isEmpty(self):
        return not self._wkt


class QgsFeature:
    def __init__(self, fields=None):
        self.fields, self._geometry, self._attributes = fields, None, []

    def setGeometry(self, geometry):
        self._geometry = geometry

    def geometry(self):
        return self._geometry

    def setAttributes(self, values):
        self._attributes = values


class QgsFeatureSink:
    FastInsert = 1


class _Parameter:
    def __init__(self, name, description="", *args, **kwargs):
        self.name, self.description = name, description
        self.args, self.kwargs = args, kwargs
        self._flags = 0

    def flags(self):
        return self._flags

    def setFlags(self, value):
        self._flags = value


class QgsProcessingParameterPoint(_Parameter):
    pass


class QgsProcessingParameterEnum(_Parameter):
    pass


class QgsProcessingParameterNumber(_Parameter):
    Integer, Double = 0, 1
    FlagAdvanced = 1 << 2


class QgsProcessingParameterBoolean(_Parameter):
    pass


class QgsProcessingParameterFeatureSource(_Parameter):
    pass


class QgsProcessingParameterFeatureSink(_Parameter):
    pass


class QgsProcessingParameterRasterDestination(_Parameter):
    pass


class QgsProcessingParameterFolderDestination(_Parameter):
    pass


class QgsProcessingParameterFileDestination(_Parameter):
    pass


class QgsProcessingContext:
    class LayerDetails:
        def __init__(self, name, project, outputName="", layerTypeHint=None):
            self.name, self.project = name, project
            self.outputName, self.layerTypeHint = outputName, layerTypeHint
            self.forceName, self.groupName, self.layerSortKey = False, "", 0

    def __init__(self):
        self._project = object()
        self.loaded = {}

    def project(self):
        return self._project

    def addLayerToLoadOnCompletion(self, path, details):
        self.loaded[path] = details


class QgsProcessingFeedback:
    def __init__(self):
        self.messages, self.errors, self.warnings, self.progress = [], [], [], 0

    def pushInfo(self, text):
        self.messages.append(text)

    def pushWarning(self, text):
        self.warnings.append(text)

    def reportError(self, text, fatalError=False):
        self.errors.append(text)

    def setProgress(self, value):
        self.progress = value

    def isCanceled(self):
        return False


class QgsProcessingAlgorithm:
    def __init__(self):
        self.parameters = []

    def addParameter(self, parameter):
        self.parameters.append(parameter)
        return True

    def tr(self, text):
        return text

    def invalidSinkError(self, parameters, name):
        return f"invalid sink {name}"

    def invalidSourceError(self, parameters, name):
        return f"invalid source {name}"


class QgsProcessingProvider:
    def __init__(self):
        self.algorithms = []

    def addAlgorithm(self, algorithm):
        self.algorithms.append(algorithm)
        return True

    def icon(self):
        return None


class _Registry:
    def __init__(self):
        self.providers = []

    def addProvider(self, provider):
        self.providers.append(provider)

    def removeProvider(self, provider):
        if provider in self.providers:
            self.providers.remove(provider)


class QgsApplication:
    _registry = _Registry()

    @staticmethod
    def processingRegistry():
        return QgsApplication._registry
