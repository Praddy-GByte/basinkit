"""Summaries of one layer inside the classes of another.

Clipping a raster to a basin is the first half of the job. The second half is
almost always the same question in a different costume: how much rainfall
falls on the cropland, what the mean slope is above two thousand metres, how
much of the forest sits on clay. Everyone writes this themselves, and the two
mistakes are the same every time -- counting cells instead of area, which
overweights the poles, and comparing two rasters on different grids without
putting them on the same one first.
"""

from __future__ import annotations

from .terrain import cell_area_km2

#: Quantiles reported for every zone, alongside the moments.
PERCENTILES = (10, 50, 90)


def _aligned(values, zones):
    """Put ``zones`` on the grid of ``values``, or say why it cannot be done."""
    if getattr(values, "shape", None) == getattr(zones, "shape", None):
        return zones
    try:
        return zones.rio.reproject_match(values)
    except Exception as exc:
        raise ValueError(
            "The two layers are on different grids and could not be matched: "
            f"{values.shape} against {zones.shape}. Fetch both at the same "
            "resolution, or reproject one onto the other first."
        ) from exc


def zonal(values, zones, *, labels: dict | None = None, bins=None,
          decimals: int = 3):
    """Summarise ``values`` inside each class of ``zones``.

    Parameters
    ----------
    values
        The layer being summarised, as ``Basin.dem()`` and friends return it.
    zones
        A categorical layer (land cover, say) or, with ``bins``, a continuous
        one to be cut into bands.
    labels
        Maps a class code to a name. Land-cover arrays carry their own legend,
        which is read automatically when this is not given.
    bins
        Edges for cutting a continuous ``zones`` layer into bands, or an int
        for that many equal-width bands.

    Returns
    -------
    pandas.DataFrame
        One row per zone: area, share of the basin, count, mean, standard
        deviation, minimum, maximum and the percentiles. Area is summed from
        the true size of each cell, not from a cell count, so a basin that
        spans several degrees of latitude is not silently weighted towards its
        southern edge.
    """
    import ast

    import numpy as np
    import pandas as pd

    zones = _aligned(values, zones)
    field = np.asarray(getattr(values, "values", values), dtype="float64")
    zone_values = np.asarray(getattr(zones, "values", zones), dtype="float64")
    if field.ndim == 3 and field.shape[0] == 1:
        field = field[0]
    if zone_values.ndim == 3 and zone_values.shape[0] == 1:
        zone_values = zone_values[0]

    areas = cell_area_km2(values)

    if labels is None:
        declared = getattr(zones, "attrs", {}).get("classes")
        if isinstance(declared, str):
            try:
                labels = ast.literal_eval(declared)
            except (ValueError, SyntaxError):
                labels = None
        elif isinstance(declared, dict):
            labels = declared

    if bins is not None:
        edges = (np.linspace(np.nanmin(zone_values), np.nanmax(zone_values), bins + 1)
                 if np.isscalar(bins) else np.asarray(bins, dtype="float64"))
        keys = np.digitize(zone_values, edges[1:-1], right=False).astype("float64")
        keys = np.where(np.isfinite(zone_values), keys, np.nan)
        labels = {
            i: f"{edges[i]:,.0f} to {edges[i + 1]:,.0f}" for i in range(len(edges) - 1)
        }
    else:
        keys = zone_values

    usable = np.isfinite(field) & np.isfinite(keys)
    total = float(areas[np.isfinite(field)].sum())

    rows = []
    for code in np.unique(keys[usable]):
        picked = usable & (keys == code)
        sample = field[picked]
        area = float(areas[picked].sum())
        row = {
            "zone": (labels or {}).get(int(code), int(code)) if float(code).is_integer()
            else code,
            "code": int(code) if float(code).is_integer() else code,
            "cells": int(picked.sum()),
            "area_km2": round(area, decimals),
            "share": round(area / total, 4) if total else float("nan"),
            "mean": round(float(sample.mean()), decimals),
            "std": round(float(sample.std()), decimals),
            "min": round(float(sample.min()), decimals),
            "max": round(float(sample.max()), decimals),
        }
        for q, value in zip(PERCENTILES, np.percentile(sample, PERCENTILES), strict=True):
            row[f"p{q}"] = round(float(value), decimals)
        rows.append(row)

    frame = pd.DataFrame(rows).sort_values("area_km2", ascending=False)
    return frame.reset_index(drop=True)
