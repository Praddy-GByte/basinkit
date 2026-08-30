"""JRC Global Surface Water: a pre-reduced 37-year Landsat water stack.

Worth being explicit about what this is, because people routinely rebuild it
by hand: Pekel et al. classified every Landsat scene from 1984 to 2021 and
published the result as six global 30 m layers. If the question is "where is
there water, how often, and is it permanent or seasonal", this already answers
it -- there is no reason to spend a week of cloud compute recreating it.
"""

from __future__ import annotations

import math

from ..cache import download
from ..exceptions import DataSourceError

GSW = "https://storage.googleapis.com/global-surface-water/downloads2021"

LAYERS = {
    "occurrence": "Percent of months with water present, 1984-2021",
    "change": "Change in occurrence intensity between 1984-1999 and 2000-2021",
    "seasonality": "Number of months water was present in 2021",
    "recurrence": "Interannual frequency of water return",
    "transitions": "Categorical change class over the record",
    "extent": "Maximum water extent ever observed",
}


def _tile(layer: str, lat: int, lon: int) -> str:
    ns = f"{abs(lat)}{'N' if lat >= 0 else 'S'}"
    ew = f"{abs(lon)}{'E' if lon >= 0 else 'W'}"
    return f"{GSW}/{layer}/{layer}_{ew}_{ns}v1_4_2021.tif"


def global_surface_water(
    geometry, layer: str = "occurrence", *, clip: bool = True,
    max_pixels: int | None = None, progress: bool = True
):
    """Fetch one JRC Global Surface Water layer, clipped to the basin."""
    if layer not in LAYERS:
        raise ValueError(f"Unknown layer {layer!r}. Available: {', '.join(LAYERS)}")

    w, s, e, n = geometry.bounds
    paths = []
    # 10x10 degree tiles indexed by their north-west corner.
    for lat in range(math.ceil(n / 10) * 10, math.floor(s / 10) * 10 - 1, -10):
        for lon in range(math.floor(w / 10) * 10, math.ceil(e / 10) * 10 + 1, 10):
            try:
                paths.append(
                    download(
                        _tile(layer, lat, lon), namespace=f"gsw/{layer}",
                        progress=progress, timeout=300, expected_min_bytes=1024,
                    )
                )
            except DataSourceError:
                continue

    if not paths:
        raise DataSourceError(
            "No Global Surface Water tiles for this basin. Coverage is 78N-56S."
        )

    from .landcover import _mosaic_and_clip

    return _mosaic_and_clip(
        paths, geometry, clip, name=layer,
        attrs={"long_name": LAYERS[layer],
               "basinkit_product": "JRC Global Surface Water v1.4 (1984-2021)",
               "license": "CC BY 4.0",
               "citation": "Pekel, J.-F. et al. (2016). Nature 540, 418-422."},
        # 255 is JRC's nodata sentinel; averaging it in produces
        # occurrence values above 100%.
        categorical=(layer == "transitions"), max_pixels=max_pixels,
        src_nodata=255,
    )


def permanent_water_fraction(geometry) -> float:
    """Fraction of basin area under water at least 90% of the time."""
    import numpy as np

    occ = global_surface_water(geometry, "occurrence")
    vals = np.asarray(occ.values, dtype="float64").ravel()
    vals = vals[np.isfinite(vals)]
    vals = vals[vals <= 100]
    if vals.size == 0:
        return 0.0
    return float((vals >= 90).sum() / vals.size)
