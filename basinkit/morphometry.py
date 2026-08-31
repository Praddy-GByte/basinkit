"""Drainage-basin morphometry: the classical Horton-Strahler-Schumm parameters.

    basin = bk.Basin.from_point(26.87, 87.15)
    m = basin.morphometry()
    m["areal"]["drainage_density_km_per_km2"]
    m["relief"]["ruggedness_number"]

Two decisions in here change the numbers enough to be worth stating plainly,
because most published tables get at least one of them wrong.

**Streams are not reaches.** A Strahler stream of order *u* runs from where it
is created until it is destroyed by meeting another order-*u* stream. River
datasets store that as several reaches, so counting rows per order inflates the
stream count for every order above the first. On the Koshi it turns the
bifurcation ratios into 2.3, 1.8, 2.0, 1.1, 1.9, 17.1 -- values that are not
physically possible -- where counting streams gives 4.7, 4.6, 4.3, 5.3, 3.0,
2.0, mean 3.98, which is squarely in Strahler's usual 3-5. A stream of order
*u* is counted here where no order-*u* reach drains into it.

**Everything is measured in one projection.** Area, perimeter, basin length and
stream length all come from a Lambert azimuthal equal-area projection centred
on the basin. Mixing sources -- a perimeter in one projection with the river
dataset's own stored lengths -- quietly corrupts every ratio built from them,
and the circularity ratio (4*pi*A/P^2) is especially unforgiving.

Nothing here is comparable across river networks. Drainage density, stream
frequency and bifurcation ratio are properties of the network you measured, not
of the basin: a denser network gives a denser answer. Two studies of the same
basin from different sources are not measuring the same thing, and any
comparison has to say which network it used.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def _laea(lat: float, lon: float) -> str:
    return (f"+proj=laea +lat_0={lat} +lon_0={lon} "
            "+x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs")


def _streams_per_order(ids, next_down, orders) -> dict[int, int]:
    """Count Strahler streams, not the reaches a dataset splits them into."""
    order_of = dict(zip(ids, orders, strict=False))
    continues: set = set()
    for _rid, dn, od in zip(ids, next_down, orders, strict=False):
        if dn and dn in order_of and order_of[dn] == od:
            continues.add(dn)          # dn is the downstream half of one stream
    counts: dict[int, int] = {}
    for rid, od in zip(ids, orders, strict=False):
        if rid not in continues:
            counts[int(od)] = counts.get(int(od), 0) + 1
    return dict(sorted(counts.items()))


def _main_stem(gdf) -> tuple[float, float]:
    """Length of the trunk stream, and its straight-line distance, in metres.

    Walks upstream from the outlet, taking the larger contributing area at
    every junction -- the standard definition of a main channel.
    """
    ids = gdf["HYRIV_ID"].to_numpy()
    dn = gdf["NEXT_DOWN"].to_numpy()
    up = gdf["UPLAND_SKM"].to_numpy()
    geoms = list(gdf.geometry)
    by_id = {int(i): k for k, i in enumerate(ids)}

    upstream: dict[int, list[int]] = {}
    for k, d in enumerate(dn):
        if d and int(d) in by_id:
            upstream.setdefault(int(d), []).append(k)

    cur = int(np.argmax(up))            # the outlet reach drains the most
    length, path = 0.0, []
    while True:
        path.append(cur)
        length += geoms[cur].length
        kids = upstream.get(int(ids[cur]), [])
        if not kids:
            break
        cur = max(kids, key=lambda k: up[k])

    head = geoms[path[-1]].coords[0]
    mouth = geoms[path[0]].coords[-1]
    straight = math.dist(head, mouth)
    return length, straight


def morphometry(basin, *, min_order: int = 1, dem=None,
                rivers=None) -> dict[str, Any]:
    """Compute the standard morphometric parameters for ``basin``.

    Parameters
    ----------
    min_order
        Smallest Strahler order to include. Leave at 1: dropping the small
        streams changes drainage density, stream frequency and every ratio
        derived from them.
    dem, rivers
        Pass already-fetched layers to avoid refetching them.

    Returns
    -------
    dict
        ``{"basin": ..., "network": [...], "linear": ..., "areal": ...,
        "relief": ..., "notes": ...}`` -- ``network`` is one row per Strahler
        order.
    """
    import geopandas as gpd

    lat, lon = basin.centroid
    crs = _laea(lat, lon)

    poly = gpd.GeoSeries([basin.geometry], crs="EPSG:4326").to_crs(crs).iloc[0]
    area_m2 = float(poly.area)
    perim_m = float(poly.length)

    # Basin length: the longest straight line across the basin. Schumm's
    # definition (the axis parallel to the main drainage line) is not
    # reproducible without a judgement call, so the diameter is used and the
    # main channel length is reported beside it for anyone who wants Schumm's.
    hull = np.asarray(poly.convex_hull.exterior.coords)
    d2 = ((hull[:, None, :] - hull[None, :, :]) ** 2).sum(-1)
    basin_len_m = float(np.sqrt(d2.max()))

    riv = rivers if rivers is not None else basin.rivers(min_order=min_order)
    if "ORD_STRA" not in riv.columns:
        raise ValueError(
            "morphometry needs Strahler orders; the river layer has no "
            f"ORD_STRA column (has {list(riv.columns)})"
        )
    riv = riv.to_crs(crs)
    riv = riv.assign(_len_m=riv.geometry.length)

    orders = riv["ORD_STRA"].astype(int).to_numpy()
    streams = _streams_per_order(riv["HYRIV_ID"].astype(int).tolist(),
                                 riv["NEXT_DOWN"].astype(int).tolist(),
                                 orders.tolist())
    lengths = riv.groupby("ORD_STRA")["_len_m"].sum().to_dict()
    reaches = riv.groupby("ORD_STRA").size().to_dict()

    us = sorted(streams)
    net = []
    for i, u in enumerate(us):
        nu, lu = streams[u], float(lengths.get(u, 0.0)) / 1000.0
        row = {"order": u, "streams": nu, "reaches": int(reaches.get(u, 0)),
               "total_length_km": round(lu, 3),
               "mean_length_km": round(lu / nu, 4) if nu else None}
        if i + 1 < len(us):
            nxt = streams[us[i + 1]]
            row["bifurcation_ratio"] = round(nu / nxt, 3) if nxt else None
        if i:
            prev = float(lengths.get(us[i - 1], 0.0)) / 1000.0
            pn = streams[us[i - 1]]
            row["length_ratio"] = (round((lu / nu) / (prev / pn), 3)
                                   if nu and pn and prev else None)
        net.append(row)

    rbs = [r["bifurcation_ratio"] for r in net if r.get("bifurcation_ratio")]
    rls = [r["length_ratio"] for r in net if r.get("length_ratio")]
    rbm = float(np.mean(rbs)) if rbs else None

    # Strahler's weighted mean weights each ratio by the streams involved in it.
    wsum = wnum = 0.0
    for i, u in enumerate(us[:-1]):
        nu, nxt = streams[u], streams[us[i + 1]]
        if nxt:
            w = nu + nxt
            wnum += (nu / nxt) * w
            wsum += w
    wrb = wnum / wsum if wsum else None

    total_len_km = sum(float(v) for v in lengths.values()) / 1000.0
    total_streams = sum(streams.values())
    area_km2 = area_m2 / 1e6
    perim_km = perim_m / 1000.0
    lb_km = basin_len_m / 1000.0

    dd = total_len_km / area_km2
    fs = total_streams / area_km2
    stem_m, straight_m = _main_stem(riv)
    stem_km = stem_m / 1000.0

    linear = {
        "stream_orders": len(us),
        "highest_order": max(us),
        "total_streams": total_streams,
        "total_stream_length_km": round(total_len_km, 2),
        "mean_bifurcation_ratio": round(rbm, 3) if rbm else None,
        "weighted_mean_bifurcation_ratio": round(wrb, 3) if wrb else None,
        "mean_stream_length_ratio": round(float(np.mean(rls)), 3) if rls else None,
        "rho_coefficient": (round(float(np.mean(rls)) / rbm, 4)
                            if rls and rbm else None),
        "length_of_overland_flow_km": round(1 / (2 * dd), 4),
        "basin_length_km": round(lb_km, 3),
        "basin_perimeter_km": round(perim_km, 3),
        "main_channel_length_km": round(stem_km, 3),
        # Trunk-scale, not the reach-scale sinuosity of a meander study: this
        # is the whole main channel against the straight line from its head to
        # the outlet, so basin shape is in it as well as meandering.
        "main_channel_sinuosity": (round(stem_m / straight_m, 4)
                                   if straight_m > 0 else None),
    }

    n1 = streams.get(min(us), 0)
    areal = {
        "area_km2": round(area_km2, 3),
        "drainage_density_km_per_km2": round(dd, 4),
        "stream_frequency_per_km2": round(fs, 4),
        "drainage_texture_per_km": round(total_streams / perim_km, 4),
        "texture_ratio_per_km": round(n1 / perim_km, 4),
        "form_factor": round(area_km2 / lb_km ** 2, 4),
        "elongation_ratio": round(2 * math.sqrt(area_km2 / math.pi) / lb_km, 4),
        "circularity_ratio": round(4 * math.pi * area_km2 / perim_km ** 2, 4),
        "compactness_coefficient": round(0.2821 * perim_km / math.sqrt(area_km2), 4),
        "shape_factor": round(lb_km ** 2 / area_km2, 4),
        "lemniscate_ratio": round(lb_km ** 2 / (4 * area_km2), 4),
        "constant_of_channel_maintenance_km2_per_km": round(1 / dd, 4),
        "infiltration_number": round(dd * fs, 4),
        "drainage_intensity": round(fs / dd, 4),
        "length_area_relation": round(1.4 * area_km2 ** 0.6, 3),
        "fitness_ratio": round(stem_km / perim_km, 4),
        "wandering_ratio": round(stem_km / lb_km, 4),
    }

    out: dict[str, Any] = {
        "basin": {"centroid_lat_lon": [round(lat, 5), round(lon, 5)],
                  "projection": crs},
        "network": net,
        "linear": linear,
        "areal": areal,
        "notes": [
            "Streams counted as Strahler streams, not as dataset reaches.",
            "Area, perimeter and all lengths measured in one local "
            "equal-area projection.",
            "Drainage density, stream frequency and bifurcation ratio "
            "describe the river network used, not the basin alone, and are "
            "not comparable across networks.",
        ],
    }

    elev = dem if dem is not None else basin.dem()
    z = np.asarray(elev.values, dtype="float64")
    z = z[np.isfinite(z)]
    if z.size:
        zmin, zmax, zmean = float(z.min()), float(z.max()), float(z.mean())
        H_km = (zmax - zmin) / 1000.0
        # The integral of the real hypsometric curve, with the
        # elevation-relief ratio beside it -- they should agree closely, and a
        # gap between them is a sign the DEM is truncated.
        frac = np.linspace(0, 1, 512)
        zc = np.percentile(z, (1 - frac) * 100)
        hi = float(np.trapezoid((zc - zmin) / max(zmax - zmin, 1e-9), frac))
        out["relief"] = {
            "elevation_min_m": round(zmin, 1),
            "elevation_max_m": round(zmax, 1),
            "elevation_mean_m": round(zmean, 1),
            "total_relief_m": round(zmax - zmin, 1),
            "relief_ratio": round(H_km / lb_km, 5),
            "relative_relief": round((zmax - zmin) / perim_m * 100, 4),
            "ruggedness_number": round(H_km * dd, 4),
            "melton_ruggedness_number": round(H_km / math.sqrt(area_km2), 4),
            "hypsometric_integral": round(hi, 4),
            "elevation_relief_ratio": round((zmean - zmin) / max(zmax - zmin, 1e-9), 4),
            "channel_gradient_m_per_km": round((zmax - zmin) / stem_km, 3),
        }
        out["notes"].append(
            "Relief parameters and the hypsometric integral depend on DEM "
            "resolution; state which DEM was used."
        )
    return out
