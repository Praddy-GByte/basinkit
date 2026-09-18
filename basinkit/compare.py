"""One row per basin, for the times there is never only one basin.

Research does not ask about a catchment. It asks about twenty of them, or two
hundred, and then wants them side by side in a table. Written by hand that
loop always ends the same way: one coordinate fails, the loop dies, and an
hour of downloads is lost. Here a failure is a row with a reason in it and the
run carries on.
"""

from __future__ import annotations

from typing import Any

#: What every row carries even when no layers are asked for.
_SHAPE_FIELDS = ("area_km2", "bbox_efficiency", "centroid_lat", "centroid_lon")


def compare(points, *, layers: tuple[str, ...] = ("terrain",),
            labels=None, progress: bool = False, **kwargs):
    """Delineate every point and return the basins as one table.

    Parameters
    ----------
    points
        An iterable of ``(lat, lon)``.
    layers
        Which extra blocks to fill in. ``terrain`` reads the elevation model;
        ``landcover`` adds the fraction of the basin in each class;
        ``precipitation`` adds mean annual rainfall. Each one costs downloads
        per basin, so the default asks for the cheapest useful set.
    labels
        Names for the rows. Defaults to the coordinates.

    Returns
    -------
    pandas.DataFrame
        One row per point. A point that could not be delineated still gets a
        row, with ``error`` filled in and the rest left empty, so the table
        always lines up with the input and a failure is visible rather than
        silently missing.
    """
    import pandas as pd

    from .basin import Basin

    coordinates = [tuple(p) for p in points]
    names = list(labels) if labels is not None else [f"{a}, {b}" for a, b in coordinates]
    if len(names) != len(coordinates):
        raise ValueError(
            f"{len(names)} labels for {len(coordinates)} points; they must match."
        )

    rows: list[dict[str, Any]] = []
    for name, (lat, lon) in zip(names, coordinates, strict=True):
        row: dict[str, Any] = {"label": name, "lat": lat, "lon": lon, "error": None}
        try:
            basin = Basin.from_point(lat, lon, progress=progress, **kwargs)
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
            rows.append(row)
            continue

        row["area_km2"] = round(basin.area_km2, 2)
        row["bbox_efficiency"] = round(basin.bbox_efficiency, 4)
        row["centroid_lat"] = round(basin.centroid[0], 5)
        row["centroid_lon"] = round(basin.centroid[1], 5)
        row["backend"] = basin.provenance.get("backend")

        for layer in layers:
            try:
                row.update(_block(basin, layer, progress=progress))
            except Exception as exc:
                row[f"{layer}_error"] = f"{type(exc).__name__}: {exc}"
        rows.append(row)

    frame = pd.DataFrame(rows)
    return frame.dropna(axis=1, how="all")


def _block(basin, layer: str, *, progress: bool) -> dict[str, Any]:
    if layer == "terrain":
        stats = basin.terrain_stats()
        return {k: v for k, v in stats.items() if k not in ("area_km2", "bbox_efficiency")}

    if layer == "landcover":
        from .sources.landcover import class_fractions

        fractions = class_fractions(basin.landcover(progress=progress))
        return {f"lc_{name}": round(share, 4) for name, share in fractions.items()}

    if layer == "precipitation":
        import pandas as pd

        series = basin.precipitation(progress=progress)
        s = series.to_series() if hasattr(series, "to_series") else pd.Series(series)
        yearly = s.groupby(s.index.year).sum()
        return {"rain_mm_per_year": round(float(yearly.mean()), 1)}

    if layer == "morphometry":
        morph = basin.morphometry()
        linear, areal = morph.get("linear", {}), morph.get("areal", {})
        return {
            "highest_order": linear.get("highest_order"),
            "bifurcation_ratio": linear.get("mean_bifurcation_ratio"),
            "drainage_density": areal.get("drainage_density_km_per_km2"),
        }

    raise ValueError(
        f"Unknown layer {layer!r}. Choose from terrain, landcover, "
        "precipitation, morphometry."
    )
