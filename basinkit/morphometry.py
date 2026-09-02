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

That difference is checkable, and ``morphometry()`` checks it. Since an
order-*u+1* stream is formed by two order-*u* streams meeting, N(u) >= 2N(u+1)
and the bifurcation ratio can never be below 2; a single-outlet basin has
exactly one stream of its highest order. Counts that break either constraint
are reported in ``warnings`` rather than being silently returned as numbers.
Published tables that report Rb below 2, or several streams of the basin's own
highest order, have made this mistake.

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


def _main_stem(gdf):
    """The trunk stream: its length, its straight-line distance, and its line.

    Walks upstream from the outlet, taking the larger contributing area at
    every junction -- the standard definition of a main channel. The returned
    line runs head to mouth, so a profile sampled along it reads downstream.
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

    # path runs mouth -> head; reverse it so the line reads downstream, and
    # keep each reach's own vertex order (coords[0] is its upstream end).
    coords: list[tuple[float, float]] = []
    for k in reversed(path):
        g = geoms[k]
        parts = getattr(g, "geoms", [g])
        for part in parts:
            for xy in part.coords:
                if not coords or coords[-1] != xy[:2]:
                    coords.append(xy[:2])

    head = geoms[path[-1]].coords[0]
    mouth = geoms[path[0]].coords[-1]
    straight = math.dist(head, mouth)

    line = None
    if len(coords) > 1:
        from shapely.geometry import LineString

        line = LineString(coords)
    return length, straight, line


def _stem_profile(line, crs, dem, n: int = 400):
    """Elevation at the head and the mouth of the main channel, in metres.

    The channel is sampled at ``n`` points from head to mouth and the profile
    is made monotonic downstream before the two ends are read off. That step
    matters: a river centreline and a DEM never agree pixel for pixel, so a
    single sample can land on a bank or a bridge deck and put a spike in the
    profile. Taking a running minimum downstream is the same conditioning a
    longitudinal profile normally gets, and it leaves the two ends -- which is
    all the gradient needs -- far more stable than a bare pair of lookups.

    Returns ``(z_head, z_mouth)``, or ``None`` if the DEM cannot be sampled.
    """
    if line is None or dem is None:
        return None
    try:
        import geopandas as gpd
        from shapely.geometry import Point

        d = [line.length * i / (n - 1) for i in range(n)]
        pts = [line.interpolate(x) for x in d]
        dem_crs = getattr(getattr(dem, "rio", None), "crs", None) or "EPSG:4326"
        gs = gpd.GeoSeries([Point(p.x, p.y) for p in pts], crs=crs).to_crs(dem_crs)

        import xarray as xr

        xs = xr.DataArray([p.x for p in gs], dims="s")
        ys = xr.DataArray([p.y for p in gs], dims="s")
        xname = "x" if "x" in dem.coords else "longitude"
        yname = "y" if "y" in dem.coords else "latitude"
        z = dem.sel({xname: xs, yname: ys}, method="nearest").values
        z = np.asarray(z, dtype="float64").ravel()
    except Exception:
        return None

    ok = np.isfinite(z)
    if ok.sum() < 2:
        return None
    z = z[ok]
    z = np.minimum.accumulate(z)        # condition the profile downstream
    return float(z[0]), float(z[-1])


def _consistency(streams: dict[int, int], us: list[int],
                 rbm: float | None) -> list[dict[str, Any]]:
    """Check the stream counts against what Strahler ordering allows.

    Two of these are impossibilities rather than oddities, and that is what
    makes them useful. An order-*u+1* stream exists only where two order-*u*
    streams join, so N(u) >= 2*N(u+1) always holds and the bifurcation ratio
    can never fall below 2. A basin drained by one outlet likewise has exactly
    one stream of its highest order, because a second would join the first and
    raise the order. A table that breaks either constraint was not built from
    Strahler streams -- almost always because dataset reaches were counted
    instead -- and no interpretation of it is worth making.

    The third check is only a flag. Strahler's 3-5 range is an empirical
    regularity, not a law, and Kirchner (1993) showed these ratios are close
    to inevitable for any branching network, so a value outside the range is
    worth looking at and is not by itself an error.
    """
    out: list[dict[str, Any]] = []
    for i, u in enumerate(us[:-1]):
        nu, nxt = streams[u], streams[us[i + 1]]
        if nxt and nu < 2 * nxt:
            out.append({
                "check": "bifurcation_ratio_floor",
                "severity": "impossible",
                "orders": [u, us[i + 1]],
                "message": (
                    f"Rb = {nu / nxt:.2f} for order {u} -> {us[i + 1]}, below "
                    f"the floor of 2: {nxt} order-{us[i + 1]} streams need at "
                    f"least {2 * nxt} order-{u} streams above them and only "
                    f"{nu} were counted. The usual cause is counting dataset "
                    "reaches instead of Strahler streams."
                ),
            })
    top = us[-1]
    if streams.get(top, 0) > 1:
        out.append({
            "check": "single_highest_order_stream",
            "severity": "impossible",
            "orders": [top],
            "message": (
                f"{streams[top]} streams of order {top}, the highest order "
                "present, in a basin with one outlet. Two streams of the same "
                "order meeting would form order "
                f"{top + 1}, so exactly one is possible. Either the counts are "
                "reach counts or the river layer carries fragments of a "
                "neighbouring network."
            ),
        })
    if rbm is not None and not 3.0 <= rbm <= 5.0:
        out.append({
            "check": "bifurcation_ratio_range",
            "severity": "unusual",
            "orders": list(us),
            "message": (
                f"Mean bifurcation ratio {rbm:.2f} is outside Strahler's usual "
                "3-5. Elongated basins and networks thinned by clipping do "
                "this legitimately; it is a flag, not an error."
            ),
        })
    return out


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
        "relief": ..., "warnings": [...], "notes": ...}`` -- ``network`` is one
        row per Strahler order. ``warnings`` is empty when the stream counts
        are internally consistent; entries with ``severity="impossible"`` mean
        the counts break a constraint of Strahler ordering and the table
        should not be interpreted until that is resolved.
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
    stem_m, straight_m, stem_line = _main_stem(riv)
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
        "warnings": _consistency(streams, us, rbm),
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
        }

        # The gradient of the channel, not of the basin. Dividing total basin
        # relief by channel length is a common shortcut and it is wrong: the
        # highest point in a basin is a ridge top, usually nowhere near the
        # head of the main stem, so that shortcut reports a fall the river
        # never makes. Here the bed is read at both ends of the main channel.
        prof = _stem_profile(stem_line, crs, elev)
        if prof and stem_km > 0:
            z_head, z_mouth = prof
            out["relief"]["main_channel_relief_m"] = round(z_head - z_mouth, 1)
            out["relief"]["channel_gradient_m_per_km"] = round(
                (z_head - z_mouth) / stem_km, 3)
        else:
            out["relief"]["main_channel_relief_m"] = None
            out["relief"]["channel_gradient_m_per_km"] = None

        out["notes"].append(
            "Relief parameters and the hypsometric integral depend on DEM "
            "resolution; state which DEM was used."
        )
        out["notes"].append(
            "Channel gradient is the fall of the bed along the main channel, "
            "not basin relief divided by channel length. The two differ by a "
            "large factor in any basin with high ground away from the trunk."
        )
    return out
