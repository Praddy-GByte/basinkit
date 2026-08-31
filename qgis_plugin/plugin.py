"""Plugin entry point.

A Processing-provider-only plugin, so there is no toolbar and no dialog of its
own -- everything appears in the Processing Toolbox, which gets batch mode and
the Model Builder for free.

Registration happens in ``initProcessing()``, and ``initGui()`` forwards to it.
That order matters: ``qgis_process``, the headless CLI, calls
``initProcessing()`` and never ``initGui()``, so registering only in the latter
makes the algorithms invisible outside the desktop GUI.
"""

from __future__ import annotations

from qgis.core import QgsApplication

from . import deps


class BasinkitPlugin:
    """Registers the basinkit Processing provider."""

    def __init__(self, iface=None) -> None:
        self.iface = iface
        self.provider = None
        self._warned = False

    # -- Processing -------------------------------------------------------
    def initProcessing(self) -> None:      # noqa: N802  (QGIS API name)
        from .processing_provider.provider import BasinkitProvider

        self.provider = BasinkitProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    # -- GUI --------------------------------------------------------------
    def initGui(self) -> None:             # noqa: N802  (QGIS API name)
        self.initProcessing()
        self._warn_about_missing_dependencies()

    def unload(self) -> None:
        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None

    # -- helpers ----------------------------------------------------------
    def _warn_about_missing_dependencies(self) -> None:
        """Say what is missing, once, in the message bar.

        The algorithms are registered either way. Hiding them when the
        dependency is absent would leave the user with no plugin and no
        explanation; showing them and failing with a clear message at run time
        is the friendlier failure.
        """
        message = deps.status_message()
        if message is None or self._warned or self.iface is None:
            return
        self._warned = True

        from qgis.core import Qgis, QgsMessageLog

        # The full instructions are several lines and the message bar is one,
        # so the bar points at the log, where the snippet can be selected and
        # copied. Putting a command in the bar also meant printing "None" on
        # any platform where no interpreter path could be trusted.
        QgsMessageLog.logMessage(message, "basinkit", Qgis.MessageLevel.Warning)
        self.iface.messageBar().pushMessage(
            "basinkit",
            "Python package missing. See the basinkit tab of the Log Messages "
            "panel for the two ways to install it.",
            level=Qgis.MessageLevel.Warning,
            duration=15,
        )
