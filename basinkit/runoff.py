"""The SCS curve number for a basin, from the land cover and soil it already has.

    basin = bk.Basin.from_point(-19.88038, -43.79371)
    cn = basin.curve_number()
    cn["composite_cn"]
    cn["by_cover"]

The curve number is the parameter every design storm in TR-55 practice runs
through, and it is built from two things this package already fetches: what
covers the ground, and how fast the soil under it takes water. Nothing new is
downloaded.

Two judgements are made here, and both are stated in the output rather than
buried, because a curve number quoted without them is not reproducible.

**The hydrologic soil group comes from texture, not from a soil survey.**
Where a national survey exists it assigns A to D directly and should be
preferred. Without one, the standard fallback is the USDA texture class from
the sand and clay fractions, which is what SoilGrids provides globally. It is
a weaker instrument: it sees texture and not depth to a restrictive layer or
to the water table, both of which can move a soil two groups.

**The cover types are mapped from ESA WorldCover, which was not written for
TR-55.** WorldCover's eleven classes are not the agricultural and urban cover
types TR-55 tabulates, so each class is matched to the nearest tabulated one
and that choice is listed in ``cover_mapping``. Pass ``cn_table=`` to replace
it with the condition you actually have.

Antecedent moisture is AMC II, the average condition. ``cn_amc_i`` (dry) and
``cn_amc_iii`` (wet) are given too, since a design runs the wet one.
"""

from __future__ import annotations

#: ESA WorldCover class -> (TR-55 cover type used, CN for groups A, B, C, D).
#: Curve numbers are NRCS TR-55 Table 2-2, antecedent moisture condition II.
COVER_CN = {
    10:  ("Woods, good condition",                 (30, 55, 70, 77)),
    20:  ("Brush-weed-grass, fair condition",      (35, 56, 70, 77)),
    30:  ("Pasture/grassland, good condition",     (39, 61, 74, 80)),
    40:  ("Row crops, straight row, good",         (67, 78, 85, 89)),
    50:  ("Urban residential, 65 percent imperv.", (77, 85, 90, 92)),
    60:  ("Fallow, bare soil",                     (77, 86, 91, 94)),
    70:  ("Snow and ice",                          (98, 98, 98, 98)),
    80:  ("Open water",                            (98, 98, 98, 98)),
    90:  ("Herbaceous wetland",                    (98, 98, 98, 98)),
    95:  ("Mangroves",                             (30, 55, 70, 77)),
    100: ("Moss and lichen",                       (39, 61, 74, 80)),
}

#: USDA texture class -> hydrologic soil group, the standard fallback where no
#: soil survey assigns one. Sandy soils take water fastest, clays slowest.
TEXTURE_HSG = {
    "sand": "A", "loamy sand": "A", "sandy loam": "A",
    "loam": "B", "silt loam": "B", "silt": "B",
    "sandy clay loam": "C",
    "clay loam": "D", "silty clay loam": "D",
    "sandy clay": "D", "silty clay": "D", "clay": "D",
}

_HSG_INDEX = {"A": 0, "B": 1, "C": 2, "D": 3}


def usda_texture(sand_pct: float, clay_pct: float) -> str:
    """The USDA texture class for a sand and clay percentage.

    The twelve classes of the USDA triangle, evaluated in the order the
    triangle's boundaries require: the clay classes first, because a soil can
    satisfy a looser class's bounds while belonging to a tighter one.
    """
    s, c = float(sand_pct), float(clay_pct)
    silt = 100.0 - s - c
    if c >= 40 and silt < 40 and s <= 45:
        return "clay"
    if c >= 40 and silt >= 40:
        return "silty clay"
    if c >= 35 and s >= 45:
        return "sandy clay"
    if 27 <= c < 40 and 20 < s <= 45:
        return "clay loam"
    if 27 <= c < 40 and s <= 20:
        return "silty clay loam"
    if 20 <= c < 35 and silt < 28 and s > 45:
        return "sandy clay loam"
    if 7 <= c < 27 and 28 <= silt < 50 and s <= 52:
        return "loam"
    if silt >= 50 and 12 <= c < 27:
        return "silt loam"
    if silt >= 50 and c < 12:
        return "silt" if silt >= 80 else "silt loam"
    # The three sandy classes are separated by the USDA's own combinations,
    # and the order matters: a sand satisfies loamy sand's bounds as well as
    # its own, and a loamy sand satisfies sandy loam's. Tightest first.
    silt_1_5 = silt + 1.5 * c
    silt_2 = silt + 2.0 * c
    if silt_1_5 < 15:
        return "sand"
    if silt_2 < 30:
        return "loamy sand"
    if c < 20 and s >= 52:
        return "sandy loam"
    return "loam"


def curve_number(basin, *, cn_table=None, max_pixels=None, progress=True) -> dict:
    """Composite curve number for a basin, with the distribution behind it.

    Parameters
    ----------
    cn_table
        ``{worldcover_class: (label, (cn_a, cn_b, cn_c, cn_d))}`` to replace
        the default mapping. Use it when the cover condition on the ground is
        not the one assumed here.
    max_pixels
        Passed to the land cover fetch, so this honours the same budget as the
        rest of a run. The soil is served at 250 m for the basin bounds and
        takes no budget.

    Returns
    -------
    dict
        ``composite_cn`` area-weighted over every cell that has both a cover
        class and a soil group, the AMC I and III variants, the breakdown by
        cover and by soil group, the mapping used, and the fraction of the
        basin that could not be classified.
    """
    import numpy as np

    table = dict(cn_table or COVER_CN)

    lc = basin.landcover(max_pixels=max_pixels, progress=progress)
    # SoilGrids is requested for the basin bounds at its native 250 m, so it
    # carries no pixel budget: there is nothing to coarsen.
    sand = basin.soil(prop="sand", depth="0-5cm", progress=progress)
    clay = basin.soil(prop="clay", depth="0-5cm", progress=progress)

    # Land cover is 10 m and SoilGrids 250 m. The soil is put on the cover's
    # grid rather than the other way round: coarsening the cover to 250 m
    # would dissolve exactly the built-up and riparian strips that move a
    # curve number most.
    sand = sand.rio.reproject_match(lc)
    clay = clay.rio.reproject_match(lc)

    cover = np.asarray(lc.values).squeeze()
    sand_a = np.asarray(sand.values, dtype="float32").squeeze()
    clay_a = np.asarray(clay.values, dtype="float32").squeeze()

    # SoilGrids ships the fractions in g/kg, which is ten times a percentage.
    if np.nanmax(sand_a) > 100:
        sand_a = sand_a / 10.0
    if np.nanmax(clay_a) > 100:
        clay_a = clay_a / 10.0

    good = (np.isfinite(sand_a) & np.isfinite(clay_a)
            & np.isin(cover, list(table)))
    total_cells = int(np.isin(cover, list(table)).sum())
    if not good.any():
        raise ValueError(
            "No cell in this basin has both a land cover class and a soil "
            "texture, so no curve number can be composed. SoilGrids has gaps "
            "over open water and bare rock; basin.soil() shows the coverage."
        )

    # One texture lookup per distinct rounded pair rather than per cell: a
    # basin of ten million cells holds a few hundred distinct pairs.
    s_r = np.round(sand_a[good]).astype("int16")
    c_r = np.round(clay_a[good]).astype("int16")
    cov = cover[good]
    pairs, inverse = np.unique(np.stack([s_r, c_r]), axis=1, return_inverse=True)
    hsg_of_pair = np.array(
        [_HSG_INDEX[TEXTURE_HSG[usda_texture(int(p0), int(p1))]]
         for p0, p1 in zip(pairs[0], pairs[1], strict=True)], dtype="int8")
    hsg = hsg_of_pair[inverse]

    cn = np.empty(cov.shape, dtype="float32")
    by_cover: dict[str, dict] = {}
    for code, (label, values) in table.items():
        m = cov == code
        if not m.any():
            continue
        cn_cells = np.take(np.asarray(values, dtype="float32"), hsg[m])
        cn[m] = cn_cells
        by_cover[label] = {
            "worldcover_class": int(code),
            "share_pct": round(100.0 * m.sum() / good.sum(), 2),
            "mean_cn": round(float(cn_cells.mean()), 1),
        }

    composite = float(cn.mean())
    groups, counts = np.unique(hsg, return_counts=True)
    by_group = {["A", "B", "C", "D"][int(g)]: round(100.0 * n / hsg.size, 2)
                for g, n in zip(groups, counts, strict=True)}

    # Chow's conversions between antecedent moisture conditions.
    amc_i = 4.2 * composite / (10 - 0.058 * composite)
    amc_iii = 23 * composite / (10 + 0.13 * composite)
    # Potential maximum retention, in millimetres.
    retention_mm = 25400.0 / composite - 254.0

    return {
        "composite_cn": round(composite, 1),
        "cn_amc_i_dry": round(amc_i, 1),
        "cn_amc_iii_wet": round(amc_iii, 1),
        "potential_retention_mm": round(retention_mm, 1),
        "initial_abstraction_mm": round(0.2 * retention_mm, 1),
        "by_cover": dict(sorted(by_cover.items(),
                                key=lambda kv: -kv[1]["share_pct"])),
        "hydrologic_soil_group_pct": by_group,
        "cells_used": int(good.sum()),
        "cells_unclassified_pct": round(
            100.0 * (total_cells - int(good.sum())) / max(total_cells, 1), 2),
        "cover_mapping": {int(k): v[0] for k, v in table.items()},
        "assumptions": {
            "curve_numbers": "NRCS TR-55 Table 2-2, antecedent moisture II.",
            "soil_group": "USDA texture class from SoilGrids sand and clay at "
                          "0-5 cm, mapped to A-D. A national soil survey "
                          "assigns the group directly and should be preferred "
                          "where one exists; texture alone cannot see depth to "
                          "a restrictive layer or to the water table.",
            "cover_types": "ESA WorldCover classes matched to the nearest "
                           "TR-55 cover type; see cover_mapping, and pass "
                           "cn_table= to replace it.",
            "initial_abstraction": "Ia = 0.2S, the TR-55 default. Published "
                                   "work since has argued for 0.05S, which "
                                   "raises computed runoff.",
        },
    }
