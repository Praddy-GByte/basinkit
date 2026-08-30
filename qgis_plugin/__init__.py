"""basinkit for QGIS.

A Processing provider that turns a point on a river into the basin above it and
the open Earth observation data inside it.
"""


def classFactory(iface):          # noqa: N802  (QGIS requires this exact name)
    from .plugin import BasinkitPlugin

    return BasinkitPlugin(iface)
