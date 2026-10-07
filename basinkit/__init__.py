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

from . import (
               archydro,
               cache,
               catalog,
               climate,
               clip,
               delineate,
               landscape,
               quality,
               report,
               sources,
               suitability,
               terrain,
)
from .basin import Basin
from .compare import compare
from .exceptions import (
               BasinkitError,
               DataSourceError,
               DelineationError,
               LicenseError,
               MissingDependency,
               NotImplementedSource,
               OutletSnapError,
)
from .river import Confluence, River

__version__ = "0.9.0"

# Authorship. These travel with every install, every wheel and every import, so
# that the person a user credits is never a guess.
__author__ = "Pradeepika Kaushik"
__email__ = "pradeepika.kaushik@gmail.com"
__license__ = "Apache-2.0"
__copyright__ = "Copyright (c) 2026 Pradeepika Kaushik"
# Concept DOI: always resolves to the newest release. The version DOI for this
# release is in CITATION.cff.
__doi__ = "10.5281/zenodo.22181933"
__citation__ = (
    f"Kaushik, P. (2026). basinkit: basin-scale acquisition of open Earth "
    f"observation data (version {__version__}) [Computer software]. "
    f"https://doi.org/{__doi__}"
)

__all__ = [
    "Basin",
    "River",
    "compare",
    "terrain",
    "suitability",
    "quality",
    "report",
    "climate",
    "Confluence",
    "catalog", "cache", "clip", "delineate", "sources",
    "landscape", "archydro",
    "BasinkitError", "DelineationError", "OutletSnapError",
    "DataSourceError", "LicenseError", "MissingDependency",
    "NotImplementedSource",
    "__version__",
    "__author__",
    "__citation__",
    "__doi__",
]
