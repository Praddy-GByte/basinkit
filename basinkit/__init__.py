"""basinkit -- point to river basin to every open Earth observation layer.

Give it an outlet coordinate anywhere on Earth. It delineates the upstream
basin, then fetches DEM, land cover, soil, rainfall, surface water and satellite
imagery **clipped and masked to that polygon** -- not to its bounding box, and
not behind a login.

    import basinkit as bk

    basin = bk.Basin.from_point(26.87, 87.15)    # Sapta Koshi at Chatara
    print(basin)
    dem = basin.dem()
    basin.download_all("koshi/")

Every layer in the default stack is anonymous and licensed CC BY 4.0 or more
permissive. Datasets that need an account (ERA5-Land, IMERG, GloFAS) or whose
licence restricts use (MERIT Hydro, FABDEM, MSWEP, GRDC) are opt-in and
announce themselves before the first byte moves. ``basinkit.catalog.table()``
shows the whole picture.
"""

from . import cache, catalog, clip, delineate, sources
from .basin import Basin
from .exceptions import (
    BasinkitError,
    DataSourceError,
    DelineationError,
    LicenseError,
    MissingDependency,
    NotImplementedSource,
    OutletSnapError,
)

__version__ = "0.3.3"

__all__ = [
    "Basin",
    "catalog", "cache", "clip", "delineate", "sources",
    "BasinkitError", "DelineationError", "OutletSnapError",
    "DataSourceError", "LicenseError", "MissingDependency",
    "NotImplementedSource",
    "__version__",
]
