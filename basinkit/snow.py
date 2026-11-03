"""How much of this basin is under permanent ice, and where that ice sits.

For a Himalayan, Andean or Alpine catchment this is usually the first question
asked and the last one answered. Every layer needed for it was already being
fetched -- the land-cover map carries a snow-and-ice class, and the elevation
model is in hand for the terrain products -- and nothing put the two together.

What comes out is three measurements and one refusal.

``ice_pct``
    The share of the basin mapped as permanent snow and ice. Measured by
    *area*, not by counting cells. A cell of a tenth of a degree is 12.3 km2
    at the equator and 2.2 km2 at 80 degrees north, and glaciers live at the
    second latitude, so counting cells would overstate the ice in exactly the
    basins anyone asks about.

``ice_floor_m``
    Where the ice zone begins: the first percentile of the elevations the
    mapped ice occupies, not the minimum. The minimum is one cell, and one
    cell in deep shadow is exactly what a land-cover map gets wrong. On the
    Trishuli the minimum reads 1,458 m -- not a Himalayan terminus -- off 33
    cells in 140,415, while the first percentile reads 4,414 m, which is. The
    single lowest cell is still reported, as ``lowest_mapped_ice_m``, and
    named as probable misclassification when it sits far below the floor.

``above_ice_floor_pct``
    How much of the basin lies at or above that floor -- the share sitting in
    the zone where ice occurs at all. Against the raw minimum this came out as
    100 per cent, which said nothing about anything.

And the refusal, which matters more than the three numbers: **an ice fraction
is not a meltwater fraction.** A basin 30 per cent covered by ice does not
deliver 30 per cent of its flow from melt. That number depends on mass
balance, on how much of the ice is in the ablation zone in a given year, and
on what the rest of the catchment contributes, none of which is measured here
and none of which can be read off a land-cover map. Every output says so.

Given a BasinATLAS row the answer gains three more axes that the land-cover
map cannot supply -- glacier extent, mean annual snow-cover extent and
permafrost extent, each aggregated over the whole upstream area. Those are a
different measurement from the one above and are reported separately rather
than averaged into it: permanent ice in a single mapped year is not the same
quantity as mean annual snow cover.
"""

from __future__ import annotations

from typing import Any

#: ESA WorldCover's class for permanent snow and ice. The same code is used in
#: :mod:`basinkit.quality`, where the class list lives.
SNOW_ICE_CLASS = 70

#: The latitudes ESA WorldCover covers. Outside this band the product has no
#: opinion, and an honest answer says that rather than returning zero per cent
#: -- which is what "no data" would otherwise be mistaken for, in precisely
#: the far-northern basins where the ice is.
WORLDCOVER_LAT_RANGE = (-60.0, 82.75)

#: BasinATLAS attribute-group prefixes this module reads. The full column
#: names are discovered from the row rather than hard-coded, because HydroATLAS
#: spells its columns by convention and a typo here would silently drop an
#: axis instead of failing.
ATLAS_PREFIXES = ("gla", "snw", "prm")

#: What each prefix measures, for the sentence the answer prints.
ATLAS_MEANING = {
    "gla": "glacier extent",
    "snw": "snow cover extent",
    "prm": "permafrost extent",
}

#: The ice zone's lower edge is read as this percentile of the elevations the
#: mapped ice occupies, not as the minimum. The minimum is one cell, and one
#: cell is exactly what a land-cover map gets wrong in deep shadow. Measured
#: on the Trishuli at Syabrubesi, 3,198 km2: the lowest mapped ice sits at
#: 1,458 m, which is not a Himalayan glacier terminus, and 33 cells out of
#: 140,415 -- two hundredths of one per cent -- lie below 2,000 m. The first
#: percentile puts the edge at 4,414 m, which is. Reporting the minimum also
#: made the share of the basin above it 100 per cent, a number that says
#: nothing about anything.
ICE_FLOOR_PERCENTILE = 1.0

#: How far below the floor the single lowest mapped cell has to sit before the
#: answer names it as probable misclassification rather than as a terminus.
FLOOR_OUTLIER_M = 500.0

#: Elevation bands for the breakdown, in metres. Five hundred is coarse enough
#: that every band holds enough cells to mean something and fine enough to show
#: a snowline: on the Trishuli the ice goes from 0.9 per cent of the 4,000 to
#: 4,500 m band to 95.3 per cent above 6,500 m.
ELEVATION_BAND_M = 500.0

#: The eight compass sectors, each 45 degrees wide and centred on its bearing.
ASPECT_SECTORS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")

#: Slope classes, in degrees. The top class is open.
SLOPE_BREAKS_DEG = (0.0, 10.0, 20.0, 30.0, 45.0)

#: Below this share of the basin, ice is reported as present but not treated
#: as a feature of the catchment. A tenth of a per cent of a large basin is a
#: few mapped cells, and at 10 m those are as likely to be shadow or cloud as
#: ice.
TRACE_PCT = 0.1


def _ice_mask(landcover):
    """Where the land-cover map says permanent snow and ice."""
    import numpy as np

    values = np.asarray(getattr(landcover, "values", landcover)).squeeze()
    return values == SNOW_ICE_CLASS


def _atlas_block(attributes) -> dict[str, Any]:
    """Glacier, snow and permafrost extent from a BasinATLAS row.

    Columns are picked by prefix and by the upstream extent code, so a
    renamed or reordered table is read correctly and a missing one is reported
    as missing rather than as zero.
    """
    row = attributes
    # A GeoDataFrame of one row, a Series, or a plain mapping all arrive here.
    if hasattr(row, "iloc") and getattr(row, "ndim", 1) == 2:
        if len(row) == 0:
            return {}
        row = row.iloc[0]
    items = row.items() if hasattr(row, "items") else {}

    out: dict[str, Any] = {}
    for name, value in items:
        if not isinstance(name, str):
            continue
        parts = name.split("_")
        if len(parts) < 3 or parts[0] not in ATLAS_PREFIXES:
            continue
        if not parts[2].startswith("u"):      # upstream aggregation only
            continue
        try:
            out[name] = round(float(value), 3)
        except (TypeError, ValueError):
            continue
    return out


def snow_ice(basin, *, dem=None, landcover=None, attributes=None,
             year: int = 2021, max_pixels: int | None = None,
             ice_mask: bool = False, breakdowns: bool = True) -> dict[str, Any]:
    """Permanent snow and ice in this basin, and the elevations it occupies.

    Parameters
    ----------
    basin
        A :class:`~basinkit.basin.Basin`.
    dem, landcover
        Already-fetched layers, to avoid downloading them twice. Without the
        elevation model the area is still measured and the elevation
        statistics are reported as not evaluated, rather than guessed.
    attributes
        A BasinATLAS row, from :func:`basinkit.sources.attributes.hydroatlas`.
        Optional, and it is a 2.7 GB download the first time, so nothing here
        requires it: without it the answer rests on the land-cover map, which
        was being fetched anyway.
    year
        The ESA WorldCover epoch to read.
    breakdowns
        Also cross the ice against elevation, aspect and slope. The elevation
        model is already in hand by this point and the three surfaces are
        computed from it, so this costs arithmetic and nothing downloaded.
    ice_mask
        Also return ``mask``: 1 where the land cover maps permanent snow and
        ice, 0 elsewhere inside the basin, and nodata outside it. A number is
        what a report needs; a layer is what anyone looking at a glacier
        actually wants.

    Returns
    -------
    dict
        ``ice_pct``, ``ice_km2``, the elevation band the ice occupies,
        ``above_lowest_ice_pct``, the BasinATLAS axes when a row was given,
        ``statement``, ``limits`` and ``source``.
    """
    import numpy as np

    from .terrain import cell_area_km2

    lat, lon = basin.centroid
    south, north = WORLDCOVER_LAT_RANGE
    covered = south <= lat <= north

    out: dict[str, Any] = {
        "basin_km2": round(float(basin.area_km2), 3),
        "centroid_lat_lon": [round(lat, 5), round(lon, 5)],
        "mapped_year": year,
        "covered_by_land_cover": covered,
    }

    if not covered:
        out.update({
            "ice_pct": None, "ice_km2": None,
            "statement": (
                f"This basin is centred at {lat:.2f} degrees, outside the "
                f"{south} to {north} that ESA WorldCover covers, so the "
                "land-cover map has no opinion about ice here. That is not "
                "the same as no ice, and it must not be read as zero."
            ),
            "limits": _limits(covered=False),
            "source": f"ESA WorldCover {year} (outside coverage)",
        })
        out.update(_atlas_section(attributes))
        return out

    cover = landcover if landcover is not None else basin.landcover(
        year=year, source="worldcover",
        **({"max_pixels": max_pixels} if max_pixels else {}))

    mask = _ice_mask(cover)
    area = cell_area_km2(cover)
    inside = np.isfinite(np.asarray(getattr(cover, "values", cover),
                                    dtype="float64").squeeze())
    basin_km2_mapped = float(area[inside].sum())
    ice_km2 = float(area[mask].sum())
    ice_pct = (ice_km2 / basin_km2_mapped * 100) if basin_km2_mapped else 0.0

    out.update({
        "ice_km2": round(ice_km2, 4),
        "ice_pct": round(ice_pct, 4),
        "mapped_cells": int(mask.sum()),
        "measured_by": "area, not cell count",
    })

    # --- where the ice sits ---------------------------------------------
    elevation = dem if dem is not None else None
    if elevation is None:
        try:
            elevation = basin.dem(**({"max_pixels": max_pixels} if max_pixels else {}))
        except Exception as exc:                        # pragma: no cover
            elevation = None
            out["elevation_note"] = f"Elevation not read: {exc}"

    if elevation is not None and ice_km2 > 0:
        out.update(_elevation_band(cover, mask, elevation))
        if breakdowns and out.get("elevation_evaluated"):
            out["breakdowns"] = _breakdowns(cover, mask, elevation)
    elif ice_km2 == 0:
        out["elevation_evaluated"] = False
    else:
        out["elevation_evaluated"] = False

    if ice_mask:
        values = np.asarray(getattr(cover, "values", cover),
                            dtype="float64").squeeze()
        painted = np.where(mask, 1.0, 0.0)
        painted[~np.isfinite(values)] = np.nan
        out["mask"] = _wrap_mask(cover, painted)

    out.update(_atlas_section(attributes))
    out["statement"] = _statement(out)
    out["limits"] = _limits(covered=True)
    out["source"] = (f"ESA WorldCover {year}, class {SNOW_ICE_CLASS} "
                     "(permanent snow and ice)"
                     + (", with BasinATLAS v1.0" if out.get("atlas") else ""))
    out["note"] = ("An ice fraction is not a meltwater fraction. Nothing here "
                   "measures how much of this basin's flow comes from melt.")
    return out


def _wrap_mask(cover, painted):
    """The ice mask, carrying the land cover's own georeferencing."""
    from .terrain import _wrap

    return _wrap(cover, painted, "snow_ice",
                 "1 = permanent snow and ice",
                 "ESA WorldCover class 70, on the land-cover grid")


def _elevation_band(cover, mask, elevation) -> dict[str, Any]:
    """The elevations the mapped ice occupies, and the basin above them."""
    import numpy as np

    from .terrain import _as_array, cell_area_km2

    z = _as_array(elevation)
    # The land cover is 10 m and the elevation model 30 m, so the mask is put
    # on the elevation grid rather than the other way round: matching upwards
    # would multiply the array by nine for a statistic that does not need it.
    try:
        ice = mask
        if mask.shape != z.shape:
            matched = (cover == SNOW_ICE_CLASS).astype("float32")
            matched = matched.rio.reproject_match(elevation)
            ice = np.asarray(matched.values).squeeze() > 0.5
    except Exception as exc:                            # pragma: no cover
        return {"elevation_evaluated": False,
                "elevation_note": f"Grids could not be matched: {exc}"}

    picked = ice & np.isfinite(z)
    if not picked.any():
        return {"elevation_evaluated": False,
                "elevation_note": "No ice cell survived onto the elevation grid."}

    values = z[picked]
    floor = float(np.percentile(values, ICE_FLOOR_PERCENTILE))
    lowest = float(values.min())
    below = int((values < floor).sum())

    area = cell_area_km2(elevation)
    usable = np.isfinite(z)
    total = float(area[usable].sum())
    above = float(area[usable & (z >= floor)].sum())

    return {
        "elevation_evaluated": True,
        "ice_floor_m": round(floor, 1),
        "ice_floor_percentile": ICE_FLOOR_PERCENTILE,
        "lowest_mapped_ice_m": round(lowest, 1),
        "cells_below_floor": below,
        "median_ice_m": round(float(np.median(values)), 1),
        "highest_ice_m": round(float(values.max()), 1),
        "above_ice_floor_pct": round(above / total * 100, 2) if total else None,
        "floor_outlier": bool(floor - lowest > FLOOR_OUTLIER_M),
    }


def _atlas_section(attributes) -> dict[str, Any]:
    if attributes is None:
        return {}
    block = _atlas_block(attributes)
    if not block:
        return {"atlas": {}, "atlas_note":
                "A BasinATLAS row was given but carried no glacier, snow or "
                "permafrost column aggregated upstream."}
    readable = {}
    for name, value in block.items():
        meaning = ATLAS_MEANING.get(name.split("_")[0], name.split("_")[0])
        readable[name] = {"measures": meaning, "percent": value}
    return {"atlas": readable}


def _ordinal(value: float) -> str:
    """1 -> 1st, 2 -> 2nd, 5 -> 5th. The sentence read "the 1th percentile"."""
    whole = int(value)
    if value != whole:
        return f"{value:g}th"
    if 10 <= whole % 100 <= 20:
        return f"{whole}th"
    return f"{whole}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(whole % 10, 'th') }".replace(" ", "")


def _statement(out: dict[str, Any]) -> str:
    """The plain-language answer, built from what was actually measured."""
    pct = out.get("ice_pct")
    if pct is None:
        return "Ice was not measured."
    if pct == 0:
        head = ("No cell in this basin is mapped as permanent snow or ice in "
                f"ESA WorldCover {out['mapped_year']}. Seasonal snow that melts "
                "before the mapped composite is not in that class, so this says "
                "nothing about whether snow falls here.")
        return head + " " + _atlas_sentence(out)
    if pct < TRACE_PCT:
        head = (f"{out['ice_km2']:.2f} km2 of this basin is mapped as permanent "
                f"snow and ice, {pct:.3f} per cent of it. At that share, over "
                f"{out['mapped_cells']:,} cells of a 10 m map, shadow and cloud "
                "are as likely an explanation as ice.")
    else:
        head = (f"{out['ice_km2']:,.2f} km2 of this basin is mapped as permanent "
                f"snow and ice, {pct:.2f} per cent of its area. The share is "
                "measured by area rather than by counting cells, which at these "
                "latitudes is a different number.")
    if out.get("elevation_evaluated"):
        head += (f" The ice zone runs from about {out['ice_floor_m']:,.0f} m up to "
                 f"{out['highest_ice_m']:,.0f} m, with a median of "
                 f"{out['median_ice_m']:,.0f} m, and "
                 f"{out['above_ice_floor_pct']:.1f} per cent of the basin lies at "
                 "or above that floor. The floor is the "
                 f"{_ordinal(out['ice_floor_percentile'])} percentile of the elevations "
                 "the ice occupies rather than the single lowest cell, because "
                 "one cell is what a land-cover map gets wrong in deep shadow.")
        if out.get("floor_outlier"):
            head += (f" The lowest cell mapped as ice here sits at "
                     f"{out['lowest_mapped_ice_m']:,.0f} m, "
                     f"{out['ice_floor_m'] - out['lowest_mapped_ice_m']:,.0f} m "
                     f"below that floor, with {out['cells_below_floor']:,} cells "
                     "beneath it. Read those as misclassification, not as a "
                     "terminus.")
        else:
            head += (" The floor approximates a terminus or a snowline; it is "
                     "read off a map rather than surveyed.")
    head += (" An ice fraction is not a meltwater fraction: how much of this "
             "basin's flow comes from melt is not measured here and cannot be "
             "read off a land-cover map.")
    return head + " " + _atlas_sentence(out)


def _atlas_sentence(out: dict[str, Any]) -> str:
    atlas = out.get("atlas")
    if not atlas:
        return ("Glacier, snow-cover and permafrost extent aggregated over the "
                "whole upstream area are available from BasinATLAS, which is a "
                "2.7 GB download once; pass attributes= to include them.")
    parts = [f"{v['measures']} {v['percent']:g}% [{k}]" for k, v in atlas.items()]
    return ("BasinATLAS reports, over the whole upstream area: "
            + ", ".join(parts)
            + ". Those are a different measurement from the mapped year above "
              "and are not averaged into it.")


def _limits(*, covered: bool) -> list[str]:
    """What this answer does not establish, stated rather than implied."""
    limits = [
        "An ice fraction is not a meltwater fraction. Melt contribution "
        "depends on mass balance and on how much of the ice is in the "
        "ablation zone in a given year, none of which is measured here.",
        "ESA WorldCover's snow-and-ice class is permanent cover in one mapped "
        "year. Seasonal snow is not in it, and no trend can be read from a "
        "single epoch.",
        "At 10 m, deep shadow in high relief is a known source of "
        "misclassification, and glaciers sit in exactly that terrain.",
    ]
    if not covered:
        limits.insert(0, "This basin lies outside the latitudes ESA WorldCover "
                         "covers, so no ice measurement was possible at all.")
    else:
        limits.append(f"ESA WorldCover covers {WORLDCOVER_LAT_RANGE[0]} to "
                      f"{WORLDCOVER_LAT_RANGE[1]} degrees. Antarctica is "
                      "outside HydroSHEDS entirely, so no basin is delineated "
                      "there to begin with.")
    return limits


def _ice_on_dem(cover, mask, elevation):
    """The ice mask on the elevation model's own grid."""
    import numpy as np

    from .terrain import _as_array

    z = _as_array(elevation)
    if mask.shape == z.shape:
        return mask & np.isfinite(z), z
    matched = (cover == SNOW_ICE_CLASS).astype("float32").rio.reproject_match(elevation)
    return (np.asarray(matched.values).squeeze() > 0.5) & np.isfinite(z), z


def _rows(area, ok, ice, values, edges, labels, total_ice):
    """One row per class: how much ice it holds, and how icy the class is."""
    out = []
    for (lo, hi), label in zip(edges, labels, strict=True):
        sel = ok & (values >= lo) & (values < hi)
        class_km2 = float(area[sel].sum())
        ice_km2 = float(area[sel & ice].sum())
        if class_km2 == 0 and ice_km2 == 0:
            continue
        out.append({
            "class": label,
            "ice_km2": round(ice_km2, 3),
            "pct_of_ice": round(ice_km2 / total_ice * 100, 2) if total_ice else None,
            "pct_of_class_that_is_ice": (round(ice_km2 / class_km2 * 100, 2)
                                         if class_km2 else None),
            "class_km2": round(class_km2, 3),
        })
    return out


def _breakdowns(cover, mask, elevation) -> dict[str, Any]:
    """The ice crossed against elevation, aspect and slope.

    Three questions the ice fraction on its own cannot answer: at what height
    does ice take over, which way does it face, and how steep is the ground it
    sits on. Every input is already in hand -- the elevation model was fetched
    for the terrain products and aspect and slope are computed from it -- so
    this adds arithmetic and no download.
    """
    import numpy as np

    from .terrain import aspect as aspect_of
    from .terrain import cell_area_km2
    from .terrain import slope as slope_of

    ice, z = _ice_on_dem(cover, mask, elevation)
    ok = np.isfinite(z)
    area = cell_area_km2(elevation)
    total_ice = float(area[ice].sum())
    if total_ice == 0:
        return {}

    out: dict[str, Any] = {}

    # --- elevation ---------------------------------------------------------
    lo = float(np.floor(z[ice].min() / ELEVATION_BAND_M) * ELEVATION_BAND_M)
    # One band past the highest ice, not the ceiling of it: a maximum that
    # lands exactly on a boundary would otherwise fall outside every band,
    # and the breakdown would quietly account for less ice than there is.
    hi = float(np.floor(z[ice].max() / ELEVATION_BAND_M) * ELEVATION_BAND_M
               + ELEVATION_BAND_M)
    edges = [(e, e + ELEVATION_BAND_M)
             for e in np.arange(lo, hi, ELEVATION_BAND_M)]
    labels = [f"{int(a):,} to {int(b):,} m" for a, b in edges]
    out["elevation"] = {
        "unit": "m",
        "rows": _rows(area, ok, ice, z, edges, labels, total_ice),
        "reads": "Where ice takes over. The share of each band that is ice is "
                 "the snowline, read off the map rather than assumed.",
    }

    # --- aspect ------------------------------------------------------------
    asp = np.asarray(getattr(aspect_of(elevation), "values", None)).squeeze()
    rows = []
    for i, name in enumerate(ASPECT_SECTORS):
        low, high = (i * 45 - 22.5) % 360, (i * 45 + 22.5) % 360
        sector = ((asp >= low) | (asp < high)) if low > high else \
                 ((asp >= low) & (asp < high))
        sector = sector & ok
        class_km2 = float(area[sector].sum())
        ice_km2 = float(area[sector & ice].sum())
        rows.append({
            "class": name,
            "ice_km2": round(ice_km2, 3),
            "pct_of_ice": round(ice_km2 / total_ice * 100, 2),
            "pct_of_class_that_is_ice": (round(ice_km2 / class_km2 * 100, 2)
                                         if class_km2 else None),
            "class_km2": round(class_km2, 3),
        })
    out["aspect"] = {"unit": "compass sector", "rows": rows,
                     "reads": _aspect_reads(rows, float(elevation["y"].values.mean()))}

    # --- slope -------------------------------------------------------------
    slp = np.asarray(getattr(slope_of(elevation), "values", None)).squeeze()
    breaks = list(SLOPE_BREAKS_DEG) + [90.0]
    edges = list(zip(breaks[:-1], breaks[1:], strict=True))
    labels = [f"{int(a)} to {int(b)} deg" for a, b in edges]
    out["slope"] = {
        "unit": "degrees",
        "rows": _rows(area, ok, ice, slp, edges, labels, total_ice),
        "reads": "Steep ice is glacier and avalanche-fed; near-level ice at "
                 "altitude is plateau or icefield. The split says which this "
                 "basin holds.",
    }
    return out


def _aspect_reads(rows, mean_lat: float) -> str:
    """What the aspect split says -- including when it says the wrong thing.

    Away from the equator, ice usually favours the poleward-facing slopes,
    which get less sun. Where the measurement leans the other way, the first
    suspect is not glaciology but the land-cover map: the shaded faces are the
    ones a classifier loses. Saying which way it leans is the useful part;
    deciding why needs a glacier inventory this does not have.
    """
    by = {r["class"]: (r["pct_of_class_that_is_ice"] or 0.0) for r in rows}
    shaded = ("N", "NE", "NW") if mean_lat >= 0 else ("S", "SE", "SW")
    sunlit = ("S", "SE", "SW") if mean_lat >= 0 else ("N", "NE", "NW")
    cool = sum(by[s] for s in shaded) / len(shaded)
    warm = sum(by[s] for s in sunlit) / len(sunlit)
    spread = max(by.values()) - min(by.values())
    side = "poleward" if mean_lat >= 0 else "equatorward"
    head = (f"The {side}-facing sectors are {cool:.1f} per cent ice against "
            f"{warm:.1f} per cent on the sunlit ones, a spread of "
            f"{spread:.1f} points across all eight.")
    if cool >= warm:
        return head + (" That is the usual direction: less sun, more ice held.")
    return head + (
        " That is the opposite of the usual direction, and the first suspect "
        "is the land-cover map rather than the glaciology -- shaded slopes are "
        "the ones a classifier loses. Settling it needs a glacier inventory, "
        "which this does not have. The spread is small either way."
    )
