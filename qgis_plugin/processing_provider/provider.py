"""The Processing provider that carries basinkit's algorithms."""

from __future__ import annotations

import os

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from .algorithms.delineate import DelineateBasinAlgorithm
from .algorithms.fetch_layers import FetchBasinLayersAlgorithm
from .algorithms.morphometry import BasinMorphometryAlgorithm
from .algorithms.statistics import BasinStatisticsAlgorithm


class BasinkitProvider(QgsProcessingProvider):
    """Groups the basinkit algorithms in the Processing Toolbox."""

    def loadAlgorithms(self) -> None:      # noqa: N802  (QGIS API name)
        for algorithm in (
            DelineateBasinAlgorithm(),
            FetchBasinLayersAlgorithm(),
            BasinStatisticsAlgorithm(),
            BasinMorphometryAlgorithm(),
        ):
            self.addAlgorithm(algorithm)

    def id(self) -> str:
        return "basinkit"

    def name(self) -> str:
        return "basinkit"

    def longName(self) -> str:             # noqa: N802  (QGIS API name)
        return "basinkit - river basins and open Earth observation data"

    def icon(self) -> QIcon:
        path = os.path.join(os.path.dirname(__file__), os.pardir, "icon.png")
        return QIcon(path) if os.path.exists(path) else QgsProcessingProvider.icon(self)
