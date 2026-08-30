"""Data source adapters.

One module per access pattern, not per dataset, because the pattern is what
actually differs. Raster tiles on anonymous S3, STAC search plus lazy COG
loading, WCS coverage requests, NetCDF time series over HTTP and vector
downloads each need genuinely different plumbing; forcing them all into a
single abstraction (the way a "pure STAC" design has to) makes four of the
five awkward.
"""

from .attributes import hydroatlas
from .climate import chirps, persiann, terraclimate
from .dem import dem, dem_tiles
from .landcover import esri_lulc, worldcover
from .soil import soilgrids
from .stac import stac_search, stac_stack
from .vectors import hydrolakes, hydrorivers
from .water import global_surface_water

__all__ = [
    "dem", "dem_tiles",
    "worldcover", "esri_lulc",
    "soilgrids",
    "chirps", "persiann", "terraclimate",
    "global_surface_water",
    "hydrorivers", "hydrolakes", "hydroatlas",
    "stac_search", "stac_stack",
]
