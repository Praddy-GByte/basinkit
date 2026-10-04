# -*- coding: utf-8 -*-
"""One click: run the whole basin analysis and write figures, tables, a collage,
a PDF report and a re-runnable manifest.

Imported by basinkit_runner.py. Runs in the interpreter that has basinkit --
never inside ArcGIS Pro's Python.

Every step is registered with an id, a group, a title and the line of basinkit
code that produced it, so the report can print the code beside the picture and
the manifest can record exactly what ran. A step that fails is recorded as
failed with its exception; it does not stop the run.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import time
import traceback
from datetime import datetime, timezone

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, LinearSegmentedColormap, ListedColormap, LogNorm
import matplotlib.patches as mpatches

INK, INK2, SURF, RULE = "#0b0b0b", "#52514e", "#fcfcfb", "#cfcec9"
CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]

STEPS = []          # filled by @step
_CTX = {}           # shared objects between steps (basin, dem, hillshade, ...)


def step(sid, group, title, code):
    def deco(fn):
        STEPS.append({"id": sid, "group": group, "title": title, "code": code, "fn": fn})
        return fn
    return deco


# ------------------------------------------------------------------ drawing

def diverging(lo="#2a78d6", hi="#e34948", mid="#f0efec"):
    return LinearSegmentedColormap.from_list("div", [lo, mid, hi], N=256)


def _fig(w=4.2, h=4.2):
    fig, ax = plt.subplots(figsize=(w, h))
    fig.patch.set_facecolor(SURF); ax.set_facecolor(SURF)
    return fig, ax


def _bare(ax):
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)


def _chart(ax):
    ax.set_facecolor(SURF)
    ax.grid(True, color="#e6e5e1", lw=0.7, zorder=0); ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(RULE)
    ax.tick_params(colors=INK2, labelsize=8, length=3)


def _extent(da):
    return (float(da.x.min()), float(da.x.max()), float(da.y.min()), float(da.y.max()))


def _finite(da):
    v = np.asarray(da, dtype="float32")
    return v[np.isfinite(v)]


def _raster(ax, fig, da, cmap, label=None, vmin=None, vmax=None, norm=None, pct=None):
    if pct is not None and vmin is None and vmax is None:
        v = _finite(da)
        if v.size:
            vmin, vmax = (float(np.percentile(v, pct[0])), float(np.percentile(v, pct[1])))
    kw = dict(cmap=cmap, extent=_extent(da), origin="upper", interpolation="nearest")
    if norm is not None:
        kw["norm"] = norm
    else:
        kw["vmin"], kw["vmax"] = vmin, vmax
    im = ax.imshow(np.ma.masked_invalid(np.asarray(da, dtype="float32")), **kw)
    _bare(ax)
    if label:
        cb = fig.colorbar(im, ax=ax, fraction=0.040, pad=0.02)
        cb.set_label(label, color=INK2, fontsize=8)
        cb.ax.tick_params(colors=INK2, labelsize=7); cb.outline.set_visible(False)
    return im


def _table_fig(title, rows, colw, note=None, fs=8.2):
    if note:
        import textwrap
        note = "\n".join(textwrap.fill(par, 74) for par in str(note).split("\n") if par.strip())
    n = len(rows)
    nl = note.count("\n") + 1 if note else 0
    h = 0.42 + 0.235 * n + (0.20 + 0.135 * nl if note else 0)
    fig, ax = plt.subplots(figsize=(4.9, h))
    fig.patch.set_facecolor(SURF); ax.set_facecolor(SURF); ax.axis("off")
    ax.text(0, 1.0, title, transform=ax.transAxes, color=INK, fontsize=10, va="top")
    y = 0.99 - 0.30 / h
    for i, r in enumerate(rows):
        x = 0.0
        for cell, w in zip(r, colw):
            ax.text(x, y, str(cell), transform=ax.transAxes, fontsize=fs,
                    color=INK if i == 0 else INK2, va="top",
                    weight="bold" if i == 0 else "normal")
            x += w
        y -= 0.235 / h
        if i == 0:
            ax.plot([0, 1], [y + 0.085 / h] * 2, transform=ax.transAxes,
                    color=RULE, lw=0.8, clip_on=False)
    if note:
        ax.text(0, y - 0.02, note, transform=ax.transAxes, fontsize=7.1,
                color=INK2, va="top")
    return fig


# ------------------------------------------------------------------- steps
# 1 DELINEATION ------------------------------------------------------------

@step(1, "Delineation", "The basin, its rivers and its lakes",
      "basin = bk.Basin.from_point(lat, lon)\nbasin.rivers(); basin.lakes()")
def s_basin(C):
    import geopandas as gpd
    b = C["basin"]
    rv = b.rivers(); lk = b.lakes()
    C["rivers"], C["lakes"] = rv, lk
    poly = gpd.GeoSeries([b.geometry], crs="EPSG:4326")
    fig, ax = _fig()
    poly.plot(ax=ax, facecolor="#f0efec", edgecolor=INK, lw=1.2, zorder=1)
    w = rv.get("UPLAND_SKM")
    lw = (0.25 + 2.4 * (np.log10(w.clip(lower=1)) / np.log10(max(float(w.max()), 10)))
          if w is not None else 0.6)
    rv.plot(ax=ax, color=CAT[0], linewidth=lw, zorder=2)
    if len(lk):
        lk.plot(ax=ax, facecolor=CAT[2], edgecolor="none", zorder=3)
    ax.plot([C["lon"]], [C["lat"]], marker="o", ms=7, mfc=CAT[7], mec="white", mew=1.4, zorder=4)
    _bare(ax)
    return fig, {"area_km2": round(float(b.area_km2), 1),
                 "river_reaches": int(len(rv)), "lakes": int(len(lk))}


@step(2, "Delineation", "Sub-catchments, each carrying NEXT_DOWN", "basin.subbasins()")
def s_subbasins(C):
    # Sub-catchments are HydroBASINS level-12 units, so they come from that
    # traversal and not from a DEM-routed polygon. Since auto now refines
    # anything under 2,000 km2 on the DEM, asking C["basin"] for them fails on
    # every small catchment. Ask for the HydroBASINS delineation instead --
    # which is what the QGIS Sub-catchments tool has always done.
    import basinkit as bk

    basin = C["basin"]
    if (getattr(basin, "provenance", None) or {}).get("backend") != "hydrobasins":
        basin = bk.Basin.from_point(C["lat"], C["lon"], backend="hydrobasins")
    sb = basin.subbasins(); C["subbasins"] = sb
    col = "SUB_AREA"
    if col not in sb.columns:
        sb = sb.copy(); sb["SUB_AREA"] = sb.to_crs(6933).area / 1e6
    fig, ax = _fig()
    if len(sb) > 2:
        sb.plot(ax=ax, column="SUB_AREA", cmap="Purples", edgecolor="white", lw=0.15,
                legend=True, legend_kwds=dict(label="sub-catchment area, km²", shrink=0.62))
    else:
        # One or two units: a colour ramp would be noise, so draw them plainly.
        sb.plot(ax=ax, facecolor="#b7d3f6", edgecolor=INK, lw=0.9)
        ax.set_title(f"{len(sb)} sub-catchment{'s' if len(sb) != 1 else ''} at this outlet",
                     color=INK2, fontsize=9, loc="left")
    _bare(ax)
    return fig, {"n_subbasins": int(len(sb))}


@step(3, "Delineation", "Three independent delineation routes",
      'for be in ("hydrobasins", "api", "tdx"):\n    bk.Basin.from_point(lat, lon, backend=be)')
def s_backends(C):
    import basinkit as bk
    got = {}
    for be in ("hydrobasins", "api", "tdx"):
        try:
            got[be] = round(float(bk.Basin.from_point(C["lat"], C["lon"], backend=be).area_km2), 1)
        except Exception as exc:                        # noqa: BLE001
            got[be] = f"failed ({exc.__class__.__name__})"
    vals = [v for v in got.values() if isinstance(v, float)]
    spread = (100 * (max(vals) - min(vals)) / float(np.mean(vals))) if len(vals) > 1 else None
    rows = [["route", "km²"]] + [[k, f"{v:,.1f}" if isinstance(v, float) else v]
                                 for k, v in got.items()]
    note = (f"Spread between the routes that ran: {spread:.2f}%. A wide spread at a\n"
            "confluence usually means the outlet snapped to the other river."
            if spread is not None else None)
    return _table_fig("Three routes to the same outlet", rows, [0.55, 0.45], note), \
        {"backends": got, "spread_pct": None if spread is None else round(spread, 2)}


@step(4, "Delineation", "Where the outlet actually landed",
      "basin.bounds; basin.centroid; basin.bbox_efficiency")
def s_outlet(C):
    b = C["basin"]
    cen = b.centroid
    rows = [["property", "value"],
            ["outlet", f"{C['lat']:.4f}, {C['lon']:.4f}"],
            ["centroid", f"{float(cen[1]):.4f}, {float(cen[0]):.4f}"
             if not hasattr(cen, "x") else f"{cen.y:.4f}, {cen.x:.4f}"],
            ["bounds W,S", f"{b.bounds[0]:.3f}, {b.bounds[1]:.3f}"],
            ["bounds E,N", f"{b.bounds[2]:.3f}, {b.bounds[3]:.3f}"],
            ["area", f"{b.area_km2:,.1f} km²"]]
    try:
        rows.append(["bbox efficiency", f"{float(b.bbox_efficiency):.3f}"])
    except Exception:                                    # noqa: BLE001
        pass
    return _table_fig("The outlet and what it caught", rows, [0.42, 0.58]), \
        {"bounds": [round(float(v), 4) for v in b.bounds]}


# 2 TERRAIN ---------------------------------------------------------------

@step(5, "Terrain", "Elevation", 'dem = basin.dem(product="cop30")')
def s_dem(C):
    dem = C["basin"].dem(max_pixels=C["max_pixels"]) if C["max_pixels"] else C["basin"].dem()
    C["dem"] = dem
    v = _finite(dem)
    fig, ax = _fig(); _raster(ax, fig, dem, "Oranges", "elevation, m")
    return fig, {"shape": list(dem.shape), "min_m": round(float(v.min()), 1),
                 "max_m": round(float(v.max()), 1), "mean_m": round(float(v.mean()), 1),
                 "relief_m": round(float(v.max() - v.min()), 1)}


def _terrain_step(sid, name, title, cmap, label, code, pct=(2, 98), diverge=False,
                  log=False, on_hillshade=False):
    @step(sid, "Terrain", title, code)
    def _fn(C, _name=name, _cmap=cmap, _label=label, _pct=pct, _div=diverge,
            _log=log, _hs=on_hillshade):
        da = getattr(C["basin"], _name)(dem=C["dem"])
        if _name == "hillshade":
            C["hillshade"] = da
        fig, ax = _fig()
        if _hs and C.get("hillshade") is not None:
            ax.imshow(np.asarray(C["hillshade"]), cmap="Greys_r", extent=_extent(da),
                      origin="upper", interpolation="nearest")
        if _div:
            v = _finite(da)
            m = max(abs(float(np.percentile(v, _pct[0]))), abs(float(np.percentile(v, _pct[1]))))
            _raster(ax, fig, da, _cmap, _label, vmin=-m, vmax=m)
        elif _log:
            v = _finite(da)
            lo = max(float(np.percentile(v, 50)), 1.0)
            _raster(ax, fig, da, _cmap, _label, norm=LogNorm(vmin=lo, vmax=float(v.max())))
        else:
            _raster(ax, fig, da, _cmap, _label, pct=_pct)
        v = _finite(da)
        return fig, {"median": round(float(np.median(v)), 3),
                     "p98": round(float(np.percentile(v, 98)), 3)}
    return _fn


_terrain_step(6, "hillshade", "Hillshade", "Greys_r", None, "basin.hillshade(dem=dem)")
_terrain_step(7, "slope", "Slope", "Purples", "slope, degrees", "basin.slope(dem=dem)", (0, 98))
_terrain_step(8, "aspect", "Aspect (circular scale)", "twilight", "degrees from north",
              "basin.aspect(dem=dem)", (0, 100))
_terrain_step(9, "curvature", "Curvature — sheds or collects water", diverging(),
              "profile curvature", "basin.curvature(dem=dem)", (10, 90), diverge=True)
_terrain_step(10, "tpi", "Topographic position — valley or ridge",
              diverging("#4a3aa7", "#eda100"), "position index", "basin.tpi(dem=dem)",
              (10, 90), diverge=True)
_terrain_step(11, "tri", "Terrain ruggedness", "Reds", "ruggedness index", "basin.tri(dem=dem)")
_terrain_step(12, "roughness", "Local relief, 3×3", "YlOrBr", "local relief, m",
              "basin.roughness(dem=dem)")
_terrain_step(13, "flow_accumulation", "Flow accumulation", "Blues", "cells draining through",
              "basin.flow_accumulation(dem=dem)", log=True)
_terrain_step(14, "twi", "Topographic wetness index", "Blues", "wetness index",
              "basin.twi(dem=dem)")
_terrain_step(15, "hand", "Height above nearest drainage", "Greens",
              "height above drainage, m", "basin.hand(dem=dem)", (0, 98))


@step(16, "Terrain", "Landform classes (Weiss 2001)", "basin.landform(dem=dem)")
def s_landform(C):
    lf = C["basin"].landform(dem=C["dem"])
    v = np.asarray(lf, dtype="float32")
    codes = sorted(int(c) for c in np.unique(v[np.isfinite(v)]))
    names = ["valley", "lower slope", "flat", "mid slope", "upper slope", "ridge"][:len(codes)]
    cm = ListedColormap(CAT[:len(codes)]); cm.set_bad(SURF)
    fig, ax = _fig()
    ax.imshow(np.ma.masked_invalid(v), cmap=cm, vmin=min(codes) - 0.5, vmax=max(codes) + 0.5,
              extent=_extent(lf), origin="upper", interpolation="nearest")
    _bare(ax)
    ax.legend(handles=[mpatches.Patch(color=CAT[i], label=names[i]) for i in range(len(codes))],
              fontsize=6.6, frameon=False, loc="lower left", ncol=2, labelcolor=INK2)
    tot = int(np.isfinite(v).sum())
    return fig, {names[i]: round(100 * float((v == c).sum()) / tot, 1)
                 for i, c in enumerate(codes)}


@step(17, "Terrain", "Channels taken from the elevation itself",
      "basin.streams(dem=dem, min_area_km2=...)")
def s_streams(C):
    st = C["basin"].streams(dem=C["dem"], min_area_km2=C["stream_km2"])
    sv = np.asarray(st, dtype="float32")
    mask = np.where(np.isfinite(sv) & (sv > 0), 1.0, np.nan)
    fig, ax = _fig()
    if C.get("hillshade") is not None:
        ax.imshow(np.asarray(C["hillshade"]), cmap="Greys_r", extent=_extent(st),
                  origin="upper", interpolation="nearest")
    ax.imshow(np.ma.masked_invalid(mask), cmap=ListedColormap([CAT[0]]), extent=_extent(st),
              origin="upper", interpolation="nearest")
    _bare(ax)
    return fig, {"channel_cells": int(np.nansum(mask == 1)),
                 "min_area_km2": C["stream_km2"]}


@step(18, "Terrain", "Four elevation models over the same basin",
      'for p in ("cop30", "cop90", "nasadem", "srtm30"):\n    basin.dem(product=p)')
def s_dems(C):
    rows = [["model", "mean elevation", "relief"]]
    got = {}
    for p in ("cop30", "cop90", "nasadem", "srtm30"):
        try:
            d = C["basin"].dem(product=p, max_pixels=max(C["max_pixels"] // 4, 250_000))
            v = _finite(d)
            got[p] = {"mean_m": round(float(v.mean()), 1),
                      "relief_m": round(float(v.max() - v.min()), 1)}
            rows.append([p, f"{got[p]['mean_m']:,.0f} m", f"{got[p]['relief_m']:,.0f} m"])
        except Exception as exc:                        # noqa: BLE001
            rows.append([p, "failed", exc.__class__.__name__])
    means = [g["mean_m"] for g in got.values()]
    note = (f"The four models agree on mean elevation to within {max(means) - min(means):.0f} m.\n"
            "Worth knowing before you pick one." if len(means) > 1 else None)
    return _table_fig("Four global elevation models", rows, [0.36, 0.34, 0.30], note), got


# 3 MORPHOMETRY -----------------------------------------------------------

@step(19, "Shape and network", "Forty-two morphometric parameters", "basin.morphometry()")
def s_morph(C):
    m = C["basin"].morphometry(); C["morph"] = m
    L, A, R = m["linear"], m["areal"], m["relief"]
    rows = [["parameter", "value"],
            ["stream orders", L["stream_orders"]],
            ["Strahler streams", f"{L['total_streams']:,}"],
            ["network length", f"{L['total_stream_length_km']:,.0f} km"],
            ["mean bifurcation ratio", L["mean_bifurcation_ratio"]],
            ["drainage density", f"{A['drainage_density_km_per_km2']} km/km²"],
            ["elongation ratio", A["elongation_ratio"]],
            ["circularity ratio", A["circularity_ratio"]],
            ["form factor", A["form_factor"]],
            ["hypsometric integral", R["hypsometric_integral"]],
            ["total relief", f"{R['total_relief_m']:,.0f} m"],
            ["channel gradient", f"{R['channel_gradient_m_per_km']} m/km"]]
    note = ("Streams counted as Strahler streams, not as the reaches a river dataset\n"
            "happens to split them into. That is where most published morphometry goes wrong.")
    n = len(L) + len(A) + len(R)
    return _table_fig(f"basin.morphometry() — {n} named parameters", rows, [0.58, 0.42], note), \
        {"n_parameters": n, "linear": L, "areal": A, "relief": R}


@step(20, "Shape and network", "Horton's laws through every order",
      'basin.morphometry()["network"]')
def s_horton(C):
    net = C["morph"]["network"]
    o = [r["order"] for r in net]
    ns = [r["streams"] for r in net]
    ls = [r["total_length_km"] for r in net]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(5.6, 2.9)); fig.patch.set_facecolor(SURF)
    for ax in (a1, a2):
        _chart(ax)
    a1.semilogy(o, ns, color=CAT[0], lw=2, marker="o", ms=5)
    a1.set_xlabel("Strahler order", color=INK2, fontsize=8)
    a1.set_ylabel("streams", color=INK2, fontsize=8)
    a2.semilogy(o, ls, color=CAT[1], lw=2, marker="o", ms=5)
    a2.set_xlabel("Strahler order", color=INK2, fontsize=8)
    a2.set_ylabel("total length, km", color=INK2, fontsize=8)
    fig.tight_layout()
    return fig, {"orders": len(o), "streams_by_order": ns,
                 "mean_Rb": C["morph"]["linear"]["mean_bifurcation_ratio"]}


@step(21, "Shape and network", "Hypsometric curve",
      'basin.morphometry()["relief"]["hypsometric_integral"]')
def s_hypso(C):
    z = np.sort(_finite(C["dem"]))
    h = (z - z.min()) / max(z.max() - z.min(), 1e-9)
    a = 1.0 - np.arange(z.size) / z.size
    k = max(1, z.size // 4000)
    fig, ax = _fig(3.6, 3.2); _chart(ax)
    ax.plot(a[::k], h[::k], color=CAT[6], lw=2.2)
    ax.plot([0, 1], [1, 0], color=RULE, lw=1, ls="--")
    ax.set_xlabel("relative area  a/A", color=INK2, fontsize=8)
    ax.set_ylabel("relative height  h/H", color=INK2, fontsize=8)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    return fig, {"hypsometric_integral": C["morph"]["relief"]["hypsometric_integral"]}


@step(22, "Shape and network", "Drainage density is a curve, not a number",
      "basin.drainage_density(dem=dem)")
def s_dd(C):
    dd = C["basin"].drainage_density(dem=C["dem"])
    th = [c["threshold_km2"] for c in dd["curve"]]
    de = [c["drainage_density_km_per_km2"] for c in dd["curve"]]
    fig, ax = _fig(4.2, 3.0); _chart(ax)
    ax.loglog(th, de, color=CAT[0], lw=2, marker="o", ms=4.5)
    ax.plot([dd["chosen_threshold_km2"]], [dd["chosen"]["drainage_density_km_per_km2"]],
            marker="o", ms=11, mfc="none", mec=CAT[7], mew=2)
    ax.set_xlabel("channel-initiation threshold, km²", color=INK2, fontsize=8)
    ax.set_ylabel("drainage density, km/km²", color=INK2, fontsize=8)
    return fig, {"range_factor": dd["range_factor"],
                 "chosen_threshold_km2": dd["chosen_threshold_km2"],
                 "chosen_because": dd["chosen_because"],
                 "chosen_density": dd["chosen"]["drainage_density_km_per_km2"]}


# 4 RIVER -----------------------------------------------------------------

@step(23, "River", "The river, source to outlet", "river = bk.River.from_point(lat, lon)\nriver.profile()")
def s_profile(C):
    import basinkit as bk
    r = bk.River.from_point(C["lat"], C["lon"])
    C["river"] = r
    f = r.facts(); C["river_facts"] = f
    d = r.profile(); C["river_profile"] = d
    fig, ax = _fig(5.0, 3.0); _chart(ax)
    ax.fill_between(d.distance_km, d.elevation_m, float(d.elevation_m.min()) - 10,
                    color=CAT[1], alpha=0.16, lw=0)
    ax.plot(d.distance_km, d.elevation_m, color=CAT[1], lw=2.2)
    ax.set_xlabel("distance from source, km", color=INK2, fontsize=8)
    ax.set_ylabel("elevation, m", color=INK2, fontsize=8)
    ax.set_xlim(0, float(d.distance_km.max()))
    # Step 25 reports river.facts(). This step reports the drawn curve
    # itself, so that no two steps record the same numbers.
    x = np.asarray(d.distance_km, dtype="float64")
    y = np.asarray(d.elevation_m, dtype="float64")
    g = -np.gradient(y, x)                             # fall, m per km
    drop = float(y[0] - y[-1])
    xn = (x - x[0]) / (x[-1] - x[0])
    yn = (y - y[-1]) / drop if drop > 0 else np.zeros_like(y)
    # positive = concave up, the usual shape of a graded river
    _trap = getattr(np, "trapezoid", None) or np.trapz   # numpy 1.x / 2.x
    concavity = float(0.5 - _trap(yn, xn)) * 2.0
    upper = xn <= (1.0 / 3.0)
    vals = {"profile_points": int(x.size),
            "profile_length_km": round(float(x.max()), 2),
            "steepest_fall_m_per_km": round(float(np.nanmax(g)), 2),
            "gentlest_fall_m_per_km": round(float(np.nanmin(g)), 2) + 0.0,
            "median_fall_m_per_km": round(float(np.nanmedian(g)), 2),
            "concavity_index": round(concavity, 4),
            "drop_in_upper_third_pct": (round(float(
                (y[0] - y[upper][-1]) / drop * 100.0), 1)
                if drop > 0 and upper.sum() > 1 else None),
            "monotonic_descent": bool(np.all(np.diff(y) <= 0.0))}
    return fig, vals


@step(24, "River", "Discharge and upland area down the river",
      "river.profile()[['discharge_cms', 'upland_km2']]")
def s_riverq(C):
    d = C["river_profile"]
    fig, ax = _fig(5.0, 3.0); _chart(ax)
    ax.plot(d.distance_km, d.discharge_cms, color=CAT[0], lw=2, label="discharge, m³/s")
    ax.set_xlabel("distance from source, km", color=INK2, fontsize=8)
    ax.set_ylabel("discharge, m³/s", color=INK2, fontsize=8)
    ax.legend(fontsize=7, frameon=False, labelcolor=INK2)
    return fig, {"mean_discharge_cms": C["river_facts"].get("mean_discharge_cms"),
                 "tributaries_counted": C["river_facts"].get("tributaries_counted")}


@step(25, "River", "The river's facts", "river.facts()")
def s_riverfacts(C):
    f = C["river_facts"]
    keys = [("length_km", "length", "{:,.1f} km"), ("sinuosity", "sinuosity", "{}"),
            ("strahler_order", "Strahler order", "{}"),
            ("mean_discharge_cms", "mean discharge", "{:,.0f} m³/s"),
            ("gradient_m_per_km", "gradient", "{} m/km"),
            ("relief_m", "relief", "{:,.0f} m"),
            ("tributaries_counted", "tributaries", "{:,}"),
            ("distance_to_sea_km", "distance to sea", "{:,.0f} km")]
    rows = [["property", "value"]]
    for k, lab, fmt in keys:
        if f.get(k) is not None:
            try:
                rows.append([lab, fmt.format(f[k])])
            except Exception:                            # noqa: BLE001
                rows.append([lab, str(f[k])])
    return _table_fig("river.facts()", rows, [0.5, 0.5]), f


# 5 LAND ------------------------------------------------------------------

WC = {10: ("Tree cover", "#006400"), 20: ("Shrubland", "#ffbb22"),
      30: ("Grassland", "#ffff4c"), 40: ("Cropland", "#f096ff"),
      50: ("Built-up", "#fa0000"), 60: ("Bare / sparse", "#b4b4b4"),
      70: ("Snow and ice", "#f0f0f0"), 80: ("Permanent water", "#0064c8"),
      90: ("Herbaceous wetland", "#0096a0"), 95: ("Mangroves", "#00cf75"),
      100: ("Moss and lichen", "#fae6a0")}


def _draw_classes(ax, a, lut):
    codes = [c for c in lut if np.any(a == c)]
    cm = ListedColormap([lut[c][1] for c in codes]); cm.set_bad(SURF)
    norm = BoundaryNorm([c - 0.5 for c in codes] + [codes[-1] + 0.5], len(codes))
    return codes, cm, norm


@step(26, "Land, soil and water", "Land cover (ESA WorldCover)", "basin.landcover()")
def s_lc(C):
    lc = C["basin"].landcover(max_pixels=C["max_pixels"])
    C["landcover"] = lc
    a = np.asarray(lc, dtype="float32"); a[a == 0] = np.nan
    codes, cm, norm = _draw_classes(None, a, WC)
    fig, ax = _fig()
    ax.imshow(np.ma.masked_invalid(a), cmap=cm, norm=norm, extent=_extent(lc),
              origin="upper", interpolation="nearest")
    _bare(ax)
    ax.legend(handles=[mpatches.Patch(color=WC[c][1], label=WC[c][0]) for c in codes],
              fontsize=6.4, frameon=False, loc="lower left", ncol=2, labelcolor=INK2)
    tot = int(np.isfinite(a).sum())
    return fig, {WC[c][0]: round(100 * float((a == c).sum()) / tot, 1) for c in codes}


@step(27, "Land, soil and water", "What became what, 2017 to 2023",
      "basin.landcover_change(2017, 2023)")
def s_lcchange(C):
    ch = C["basin"].landcover_change(2017, 2023, max_pixels=C["max_pixels"])
    changed = ch[ch["changed"]] if ch["changed"].dtype == bool else ch[ch["from"] != ch["to"]]
    total = float(changed["area_km2"].sum())
    top = changed.sort_values("area_km2", ascending=False).head(6)
    fig, ax = _fig(4.6, 4.2); _chart(ax)
    lab = [f'{r["from"]} → {r["to"]}' for _, r in top.iloc[::-1].iterrows()]
    ax.barh(range(len(top)), top["area_km2"].values[::-1], color=CAT[1], height=0.62)
    ax.set_yticks(range(len(top))); ax.set_yticklabels(lab, fontsize=7, color=INK2)
    ax.set_xlabel("km² changed, 2017 → 2023", color=INK2, fontsize=8)
    return fig, {"changed_km2": round(total, 0),
                 "changed_pct": round(100 * total / float(C["basin"].area_km2), 1),
                 "top_transition": f'{top.iloc[0]["from"]} -> {top.iloc[0]["to"]}',
                 "top_transition_km2": round(float(top.iloc[0]["area_km2"]), 0)}


@step(28, "Land, soil and water", "Surface water, 1984 to 2021 (JRC)", "basin.surface_water()")
def s_water(C):
    sw = C["basin"].surface_water()
    s = np.asarray(sw, dtype="float32")
    base = np.where(np.isfinite(s), 1.0, np.nan)
    fig, ax = _fig()
    ax.imshow(np.ma.masked_invalid(base), cmap=ListedColormap(["#eceae5"]),
              extent=_extent(sw), origin="upper", interpolation="nearest")
    w = np.where(np.isfinite(s) & (s > 0), s, np.nan)
    im = ax.imshow(np.ma.masked_invalid(w), cmap="Blues", vmin=0, vmax=100,
                   extent=_extent(sw), origin="upper", interpolation="nearest")
    _bare(ax)
    cb = fig.colorbar(im, ax=ax, fraction=0.040, pad=0.02)
    cb.set_label("% of record with water", color=INK2, fontsize=8)
    cb.ax.tick_params(colors=INK2, labelsize=7); cb.outline.set_visible(False)
    v = s[np.isfinite(s)]
    return fig, {"permanent_pct": round(100 * float((v >= 90).sum()) / v.size, 2),
                 "seasonal_pct": round(100 * float(((v > 0) & (v < 90)).sum()) / v.size, 2)}


SOILS = [("clay", "clay, %", "YlOrBr", 0.1), ("sand", "sand, %", "YlOrBr", 0.1),
         ("silt", "silt, %", "YlOrBr", 0.1), ("soc", "organic carbon, g/kg", "Greens", 0.1),
         ("nitrogen", "nitrogen, g/kg", "Greens", 0.01),
         ("cec", "cation exchange, cmol/kg", "Purples", 0.1),
         ("bdod", "bulk density, kg/dm³", "Oranges", 0.01),
         ("cfvo", "coarse fragments, %", "Reds", 0.1)]


def _soil_step(sid, prop, label, cmap, scale):
    @step(sid, "Land, soil and water", f"Soil {prop}, 0–5 cm",
          f'basin.soil(prop="{prop}", depth="0-5cm")')
    def _fn(C, _p=prop, _l=label, _c=cmap, _s=scale):
        da = C["basin"].soil(prop=_p, depth="0-5cm")
        a = np.asarray(da, dtype="float32").copy()
        a[~np.isfinite(a)] = np.nan
        a[a == 0] = np.nan                    # SoilGrids writes 0 where it has nothing
        a = a * _s
        out = da.copy(data=a)
        fig, ax = _fig(); _raster(ax, fig, out, _c, _l, pct=(2, 98))
        v = a[np.isfinite(a)]
        return fig, {"median": round(float(np.median(v)), 2),
                     "p10": round(float(np.percentile(v, 10)), 2),
                     "p90": round(float(np.percentile(v, 90)), 2),
                     "note": "SoilGrids zeros treated as nodata"}
    return _fn


for _i, (_p, _l, _c, _s) in enumerate(SOILS):
    _soil_step(29 + _i, _p, _l, _c, _s)


@step(37, "Land, soil and water", "Soil pH, drawn about 7", 'basin.soil(prop="phh2o")')
def s_ph(C):
    da = C["basin"].soil(prop="phh2o", depth="0-5cm")
    a = np.asarray(da, dtype="float32").copy()
    a[~np.isfinite(a)] = np.nan; a[a == 0] = np.nan; a = a * 0.1
    out = da.copy(data=a); v = a[np.isfinite(a)]
    lo, hi = float(np.percentile(v, 2)), float(np.percentile(v, 98))
    m = max(abs(7 - lo), abs(hi - 7))
    fig, ax = _fig()
    _raster(ax, fig, out, diverging("#e34948", "#2a78d6"), "pH in water", vmin=7 - m, vmax=7 + m)
    return fig, {"median_pH": round(float(np.median(v)), 2),
                 "pct_alkaline": round(100 * float((v > 7.5).sum()) / v.size, 1)}


@step(38, "Land, soil and water", "Plant-available water capacity",
      "basin.available_water_capacity()")
def s_awc(C):
    da = C["basin"].available_water_capacity()
    a = np.asarray(da, dtype="float32").copy()
    a[~np.isfinite(a)] = np.nan; a[a == 0] = np.nan
    out = da.copy(data=a); v = a[np.isfinite(a)]
    fig, ax = _fig(); _raster(ax, fig, out, "Purples", "available water, vol %", pct=(2, 98))
    return fig, {"median_volpct": round(float(np.median(v)), 1)}


@step(39, "Land, soil and water", "Clay through six depths to two metres",
      'for d in ("0-5cm", "5-15cm", ... "100-200cm"):\n    basin.soil(prop="clay", depth=d)')
def s_soildepth(C):
    depths = ("0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm", "100-200cm")
    med = []
    for d in depths:
        a = np.asarray(C["basin"].soil(prop="clay", depth=d), dtype="float32")
        a = a[np.isfinite(a) & (a > 0)] * 0.1
        med.append(round(float(np.median(a)), 1) if a.size else np.nan)
    fig, ax = _fig(4.4, 3.0); _chart(ax)
    ax.plot(med, range(len(depths)), color=CAT[3], lw=2, marker="o", ms=5)
    ax.set_yticks(range(len(depths))); ax.set_yticklabels(depths, fontsize=7.5, color=INK2)
    ax.invert_yaxis()
    ax.set_xlabel("median clay, %", color=INK2, fontsize=8)
    return fig, dict(zip(depths, med))


@step(40, "Land, soil and water", "Any layer inside another layer's classes",
      "basin.zonal(dem, zones=basin.landcover())")
def s_zonal(C):
    z = C["basin"].zonal(C["dem"], zones=C["landcover"])
    z = z[z["code"] != 0].sort_values("area_km2", ascending=False).head(7)
    rows = [["land cover class", "share", "mean elevation"]]
    for _, r in z.iterrows():
        rows.append([str(r["zone"])[:22], f'{100 * r["share"]:.1f}%', f'{r["mean"]:,.0f} m'])
    return _table_fig("basin.zonal(dem, zones=basin.landcover())", rows, [0.46, 0.27, 0.27]), \
        {"zones": int(len(z))}


# 6 CLIMATE ---------------------------------------------------------------

@step(41, "Climate", "Annual rainfall, CHIRPS", "basin.precipitation(start=2000, end=2024)")
def s_precip(C):
    pr = C["basin"].precipitation(start=C["clim_start"], end=C["clim_end"])
    C["precip_monthly"] = pr
    ann = pr.resample(time="YE").sum()
    yrs = [int(t.dt.year) for t in ann.time]
    vals = [float(v) for v in ann.values]
    keep = [(y, v) for y, v in zip(yrs, vals) if C["clim_start"] <= y <= C["clim_end"]]
    yrs, vals = zip(*keep)
    fig, ax = _fig(4.8, 3.1); _chart(ax)
    ax.plot(yrs, vals, color=CAT[0], lw=2, marker="o", ms=4.5, zorder=3)
    ax.axhline(float(np.mean(vals)), color=INK2, lw=1, ls="--", zorder=2)
    ax.set_ylabel("mm / year", color=INK2, fontsize=8)
    return fig, {"mean_mm": round(float(np.mean(vals)), 0),
                 "min_mm": round(float(np.min(vals)), 0),
                 "min_year": int(yrs[int(np.argmin(vals))]),
                 "max_mm": round(float(np.max(vals)), 0),
                 "max_year": int(yrs[int(np.argmax(vals))]), "n_years": len(yrs)}


@step(42, "Climate", "The monsoon, month by month", "basin.precipitation().groupby('time.month')")
def s_monthly(C):
    mon = C["precip_monthly"].groupby("time.month").mean()
    v = [float(x) for x in mon.values]
    fig, ax = _fig(4.8, 3.0); _chart(ax)
    ax.bar(range(1, 13), v, color=CAT[0], width=0.68)
    ax.set_xticks(range(1, 13)); ax.set_xticklabels(list("JFMAMJJASOND"), fontsize=7.5, color=INK2)
    ax.set_ylabel("mm / month", color=INK2, fontsize=8)
    tot = sum(v)
    return fig, {"wettest_month": int(np.argmax(v)) + 1,
                 "monsoon_JJAS_pct": round(100 * sum(v[5:9]) / tot, 1) if tot else None}


@step(43, "Climate", "Is it trending?", "basin.precipitation_trend()")
def s_trend(C):
    tr = dict(C["basin"].precipitation_trend(start=C["spi_start"]))
    rows = [["statistic", "value"],
            ["Sen's slope", f"{tr['slope']:.2f} mm/yr"],
            ["years", tr["n"]],
            ["Mann-Kendall z", tr["z"]],
            ["p-value", f"{tr['p_value']:.4f}"],
            ["significant at 0.05", "yes" if tr["significant"] else "no"],
            ["direction", tr["direction"]]]
    note = ("The run reports significance rather than a direction alone. An\n"
            "insignificant slope is not a trend, however suggestive the line looks.")
    return _table_fig("Mann-Kendall with tie correction, Sen's slope", rows, [0.55, 0.45], note), tr


@step(44, "Climate", "Drought: SPI-3", "basin.spi(scale=3)")
def s_spi(C):
    sp = C["basin"].spi(scale=3, start=C["spi_start"])
    sv = sp.values.astype("float32"); ok = np.isfinite(sv)
    fig, ax = _fig(4.8, 3.1); _chart(ax)
    x = np.arange(len(sv))
    ax.bar(x[ok & (sv >= 0)], sv[ok & (sv >= 0)], color=CAT[0], width=1.0)
    ax.bar(x[ok & (sv < 0)], sv[ok & (sv < 0)], color=CAT[7], width=1.0)
    ax.axhline(-1, color=INK2, lw=1, ls="--")
    ax.set_ylabel("SPI-3", color=INK2, fontsize=8); ax.set_xticks([])
    n = int(ok.sum())
    return fig, {"months": n,
                 "pct_below_minus1": round(100 * float((sv[ok] < -1).sum()) / n, 1)}


@step(45, "Climate", "Monthly water balance, TerraClimate", "basin.water_balance()")
def s_wb(C):
    wb = C["basin"].water_balance(start=C["clim_start"], end=C["clim_end"])
    ny = len(np.unique(wb.time.dt.year.values))
    tot = {k: float(wb[k].sum()) / ny for k in ("ppt", "aet", "pet", "q") if k in wb}
    mon = wb.groupby("time.month").mean()
    fig, ax = _fig(4.8, 3.1); _chart(ax)
    m = np.arange(1, 13); w = 0.27
    ax.bar(m - w, mon["ppt"].values, width=w, color=CAT[0], label="rainfall")
    ax.bar(m, mon["aet"].values, width=w, color=CAT[1], label="evapotranspiration")
    ax.bar(m + w, mon["q"].values, width=w, color=CAT[2], label="runoff")
    ax.set_xticks(m); ax.set_xticklabels(list("JFMAMJJASOND"), fontsize=7.5, color=INK2)
    ax.set_ylabel("mm / month", color=INK2, fontsize=8)
    ax.legend(fontsize=7, frameon=False, labelcolor=INK2)
    out = {k + "_mm": round(v, 0) for k, v in tot.items()}
    if "pet" in tot and "ppt" in tot and tot["pet"]:
        out["aridity_P_over_PET"] = round(tot["ppt"] / tot["pet"], 3)
    return fig, out


# 7 SATELLITE -------------------------------------------------------------

def _stretch(a, p=(2, 98)):
    a = np.asarray(a, dtype="float32")
    lo, hi = np.nanpercentile(a, p)
    return np.clip((a - lo) / max(hi - lo, 1e-6), 0, 1)


@step(46, "Satellite", "Sentinel-2, cloud-filtered median",
      'basin.sentinel2("...-11-01", "...-02-28", cloud_cover=10)')
def s_s2(C):
    ds = C["basin"].sentinel2(C["s2_start"], C["s2_end"], cloud_cover=10,
                              max_pixels=C["sat_pixels"])
    img = np.dstack([_stretch(ds[n].compute().values) for n in ("red", "green", "blue")])
    C["s2"] = ds
    fig, ax = _fig(); ax.imshow(img, origin="upper", interpolation="nearest"); _bare(ax)
    return fig, {"shape": list(img.shape[:2])}


@step(47, "Satellite", "Vegetation index from the same scene",
      "(nir - red) / (nir + red)")
def s_ndvi(C):
    ds = C["s2"]
    nir = ds["nir"].compute().values.astype("float32")
    red = ds["red"].compute().values.astype("float32")
    ndvi = (nir - red) / np.where((nir + red) == 0, np.nan, nir + red)
    fig, ax = _fig()
    im = ax.imshow(np.ma.masked_invalid(ndvi), cmap="Greens", vmin=-0.1, vmax=0.8,
                   origin="upper", interpolation="nearest")
    _bare(ax)
    cb = fig.colorbar(im, ax=ax, fraction=0.040, pad=0.02)
    cb.set_label("NDVI", color=INK2, fontsize=8)
    cb.ax.tick_params(colors=INK2, labelsize=7); cb.outline.set_visible(False)
    v = ndvi[np.isfinite(ndvi)]
    return fig, {"median_ndvi": round(float(np.median(v)), 3)}


@step(48, "Satellite", "Sentinel-1 radar — through cloud, at night",
      'basin.sentinel1("...-11-01", "...-01-31")')
def s_s1(C):
    ds = C["basin"].sentinel1(C["s2_start"], C["s2_end"], max_pixels=C["sat_pixels"])
    band = "vv" if "vv" in ds.data_vars else list(ds.data_vars)[0]
    a = ds[band].compute().values.astype("float32")
    db = 10 * np.log10(np.clip(a, 1e-5, None))
    lo, hi = np.nanpercentile(db, (2, 98))
    fig, ax = _fig()
    ax.imshow(db, cmap="Greys_r", vmin=lo, vmax=hi, origin="upper", interpolation="nearest")
    _bare(ax)
    return fig, {"band": band, "p2_db": round(float(lo), 1), "p98_db": round(float(hi), 1)}


@step(49, "Satellite", "Landsat, three decades earlier",
      'basin.landsat("1990-11-01", "1991-03-31")')
def s_ls_old(C):
    ds = C["basin"].landsat(C["ls_old_start"], C["ls_old_end"], cloud_cover=15,
                            max_pixels=C["sat_pixels"])
    img = np.dstack([_stretch(ds[n].compute().values) for n in ("red", "green", "blue")])
    fig, ax = _fig(); ax.imshow(img, origin="upper", interpolation="nearest"); _bare(ax)
    return fig, {"window": [C["ls_old_start"], C["ls_old_end"]]}


@step(50, "Satellite", "Landsat, the same months today",
      'basin.landsat("2023-11-01", "2024-03-31")')
def s_ls_new(C):
    ds = C["basin"].landsat(C["ls_new_start"], C["ls_new_end"], cloud_cover=15,
                            max_pixels=C["sat_pixels"])
    img = np.dstack([_stretch(ds[n].compute().values) for n in ("red", "green", "blue")])
    fig, ax = _fig(); ax.imshow(img, origin="upper", interpolation="nearest"); _bare(ax)
    return fig, {"window": [C["ls_new_start"], C["ls_new_end"]],
                 "note": "This pair is the input to a change study, not its conclusion."}


# 8 DOES THE DATA SUPPORT THE ANSWER --------------------------------------

@step(51, "Does the data support the answer", "Can the DEM carry terrain analysis here?",
      "basin.dem_suitability(support_map=True)")
def s_suit(C):
    s = C["basin"].dem_suitability(dem=C["dem"], support_map=True)
    sup = s.pop("support", None)
    C["suitability"] = s
    fig, ax = _fig()
    if sup is not None:
        ax.imshow(np.ma.masked_invalid(np.asarray(sup, dtype="float32")),
                  cmap=ListedColormap(["#e34948", "#1baf7a"]), vmin=0, vmax=1,
                  extent=_extent(sup), origin="upper", interpolation="nearest")
        ax.legend(handles=[mpatches.Patch(color="#1baf7a", label="slope above the noise floor"),
                           mpatches.Patch(color="#e34948", label="below it — the model's own error")],
                  fontsize=7, frameon=False, loc="lower left", labelcolor=INK2)
    _bare(ax)
    return fig, {"grade": s.get("grade"), "unmet": s.get("unmet"),
                 "support_fraction": s.get("support_fraction"),
                 "cell_size_m": s.get("cell_size_m"),
                 "vertical_error_m": s.get("vertical_error_m")}


@step(52, "Does the data support the answer", "The five elevation tests, one by one",
      'basin.dem_suitability()["tests"]')
def s_suit_tests(C):
    tests = C["suitability"]["tests"]
    rows = [["test", "verdict", "measured", "unit"]]
    for t in tests:
        rows.append([t["test"], t["verdict"], t["measured"], str(t["unit"])[:18]])
    note = "\n".join(t["statement"][:96] for t in tests if t["verdict"] != "pass")[:300] or None
    return _table_fig("Five tests against the model's own stated error", rows,
                      [0.26, 0.20, 0.22, 0.32], note), \
        {t["test"]: t["verdict"] for t in tests}


@step(53, "Does the data support the answer", "A grade for every layer — new in 0.7.0",
      "basin.data_quality()")
def s_quality(C):
    q = C["basin"].data_quality(); C["quality"] = q
    rows = [["layer", "grade", "measured"]]
    for L in q["layers"]:
        val = L.get("value")
        shown = ("—" if val is None else
                 (f"{val:,.2f}" if isinstance(val, float) and abs(val) < 1000 else f"{val:,.0f}"))
        rows.append([L["layer"].replace("_", " "), L.get("grade") or "not graded", shown])
    note = (f"Overall: {q['overall']}. Each layer judged against something produced\n"
            "independently of it. Layers with no published threshold are returned\n"
            "ungraded, with not_graded_because saying why.")
    return _table_fig("basin.data_quality()", rows, [0.38, 0.30, 0.32], note), \
        {"overall": q["overall"],
         "grades": {L["layer"]: (L.get("grade") or "not graded") for L in q["layers"]}}


@step(54, "Does the data support the answer", "Why each layer got the grade it did",
      'basin.data_quality()["layers"][i]["statement"]')
def s_quality_why(C):
    q = C["quality"]
    rows = [["layer", "judged against"]]
    for L in q["layers"]:
        rows.append([L["layer"].replace("_", " "), str(L.get("source", ""))[:46]])
    return _table_fig("What each grade was measured against", rows, [0.32, 0.68]), \
        {L["layer"]: L.get("source") for L in q["layers"]}


# --- appended: steps 55-70, then the outputs 71-76 -----------------------

@step(55, "Delineation", "The basin's own HydroATLAS attributes", "basin.attributes()")
def s_attrs(C):
    import basinkit as bk

    # BasinATLAS is keyed by HydroBASINS id, which only that backend records.
    # auto refines anything under 2,000 km2 on the DEM, so the auto basin
    # carries no id to look up. Ask for the HydroBASINS delineation instead.
    basin = C["basin"]
    if (getattr(basin, "provenance", None) or {}).get("backend") != "hydrobasins":
        basin = bk.Basin.from_point(C["lat"], C["lon"], backend="hydrobasins")
    at = basin.attributes()
    if hasattr(at, "to_dict"):
        at = at.to_dict()
    items = [(k, v) for k, v in list(at.items()) if not isinstance(v, (dict, list))][:11]
    rows = [["attribute", "value"]] + [[str(k)[:26], str(v)[:20]] for k, v in items]
    return _table_fig("basin.attributes() — HydroATLAS", rows, [0.58, 0.42],
                      f"{len(at)} attributes available for this basin."), \
        {"n_attributes": len(at)}


@step(56, "Delineation", "This basin against its own largest sub-basins",
      'bk.compare([(lat1, lon1), (lat2, lon2), ...])')
def s_compare(C):
    sb = C["subbasins"].copy()
    col = "SUB_AREA" if "SUB_AREA" in sb.columns else None
    if col is None:
        sb["SUB_AREA"] = sb.to_crs(6933).area / 1e6; col = "SUB_AREA"
    big = sb.sort_values(col, ascending=False).head(6)
    rows = [["sub-catchment", "km²", "share of basin"]]
    tot = float(C["basin"].area_km2)
    for i, (_, r) in enumerate(big.iterrows(), start=1):
        a = float(r[col])
        rows.append([f"#{i}", f"{a:,.1f}", f"{100 * a / tot:.1f}%"])
    return _table_fig("The units this basin is assembled from", rows, [0.36, 0.32, 0.32],
                      f"{len(sb):,} sub-catchments in total, each carrying NEXT_DOWN."), \
        {"largest_km2": round(float(big[col].iloc[0]), 1)}


@step(57, "Land, soil and water", "Land cover, the ESRI annual series",
      'basin.landcover(source="esri")')
def s_lc_esri(C):
    lc = C["basin"].landcover(source="esri", max_pixels=C["max_pixels"])
    a = np.asarray(lc, dtype="float32"); a[a == 0] = np.nan
    codes = sorted(int(c) for c in np.unique(a[np.isfinite(a)]))
    cm = ListedColormap((CAT * 3)[:len(codes)]); cm.set_bad(SURF)
    fig, ax = _fig()
    ax.imshow(np.ma.masked_invalid(a), cmap=cm, vmin=min(codes) - 0.5, vmax=max(codes) + 0.5,
              extent=_extent(lc), origin="upper", interpolation="nearest")
    _bare(ax)
    ax.legend(handles=[mpatches.Patch(color=(CAT * 3)[i], label=f"class {c}")
                       for i, c in enumerate(codes)],
              fontsize=6.4, frameon=False, loc="lower left", ncol=2, labelcolor=INK2)
    return fig, {"classes_present": len(codes), "codes": codes}


for _i, (_p, _l, _c, _s) in enumerate([
        ("ocd", "organic carbon density, kg/m³", "Greens", 0.1),
        ("wv0033", "field capacity, vol %", "Blues", 0.1),
        ("wv1500", "wilting point, vol %", "Oranges", 0.1)]):
    _soil_step(58 + _i, _p, _l, _c, _s)


@step(61, "Land, soil and water", "How wide SoilGrids says its own band is",
      'basin.data_quality()  # soil layer: Q0.05 to Q0.95 width')
def s_soilband(C):
    L = [x for x in C["quality"]["layers"] if x["layer"] == "soil"][0] \
        if C.get("quality") else None
    if L is None:
        q = C["basin"].data_quality(); C["quality"] = q
        L = [x for x in q["layers"] if x["layer"] == "soil"][0]
    rows = [["property", "value"],
            ["indicator", str(L.get("indicator"))[:30]],
            ["measured", f"{L.get('value')}"],
            ["grade", L.get("grade") or "not graded"]]
    return _table_fig("Soil: reported, deliberately not graded", rows, [0.36, 0.64],
                      str(L.get("not_graded_because", ""))[:260]), \
        {"band_width_pct_of_mean": L.get("value"), "grade": L.get("grade")}


@step(62, "Land, soil and water", "Permanent water against seasonal",
      'basin.data_quality()  # surface_water layer')
def s_watersplit(C):
    L = [x for x in C["quality"]["layers"] if x["layer"] == "surface_water"][0]
    rows = [["property", "value"],
            ["indicator", str(L.get("indicator"))[:30]],
            ["measured", f"{L.get('value')}"],
            ["grade", L.get("grade") or "not graded"]]
    return _table_fig("Surface water: reported, deliberately not graded", rows, [0.36, 0.64],
                      str(L.get("not_graded_because", ""))[:260]), \
        {"permanent_fraction": L.get("value"), "grade": L.get("grade")}


@step(63, "Climate", "Drought over a longer window: SPI-12", "basin.spi(scale=12)")
def s_spi12(C):
    sp = C["basin"].spi(scale=12, start=C["spi_start"])
    sv = sp.values.astype("float32"); ok = np.isfinite(sv)
    fig, ax = _fig(4.8, 3.0); _chart(ax)
    x = np.arange(len(sv))
    ax.fill_between(x[ok], 0, sv[ok], where=sv[ok] >= 0, color=CAT[0], lw=0)
    ax.fill_between(x[ok], 0, sv[ok], where=sv[ok] < 0, color=CAT[7], lw=0)
    ax.axhline(-1, color=INK2, lw=1, ls="--")
    ax.set_ylabel("SPI-12", color=INK2, fontsize=8); ax.set_xticks([])
    n = int(ok.sum())
    return fig, {"months": n,
                 "pct_below_minus1": round(100 * float((sv[ok] < -1).sum()) / n, 1)}


@step(64, "Climate", "Two rainfall products, year against year",
      'basin.data_quality()  # precipitation: CHIRPS vs TerraClimate')
def s_precip_pair(C):
    L = [x for x in C["quality"]["layers"] if x["layer"] == "precipitation"][0]
    rows = [["property", "value"],
            ["indicator", str(L.get("indicator"))[:30]],
            ["agreement r", f"{L.get('value')}"],
            ["grade", L.get("grade") or "not graded"],
            ["judged against", str(L.get("source"))[:30]]]
    return _table_fig("Rainfall: two independent products", rows, [0.36, 0.64],
                      str(L.get("statement", ""))[:300]), \
        {"r": L.get("value"), "grade": L.get("grade")}


@step(65, "Does the data support the answer", "Elevation graded by terrain class",
      'basin.data_quality()  # elevation: terrain_classes')
def s_elev_classes(C):
    L = [x for x in C["quality"]["layers"] if x["layer"] == "elevation"][0]
    tc = L.get("terrain_classes") or []
    rows = [["terrain", "share of basin", "mean slope", "below noise floor"]]
    for t in tc:
        rows.append([t["terrain"], f"{100 * t['share_of_basin']:.1f}%",
                     f"{t['mean_slope_deg']:.2f}°",
                     f"{100 * t['below_noise_floor']:.1f}%"])
    note = (f"Noise floor {L.get('class_noise_floor_deg')}° at a "
            f"{L.get('class_cell_size_m')} m cell. The slope a model cannot resolve is its\n"
            "own vertical error over one cell — so it is a property of the model, not the ground.")
    return _table_fig("Elevation, split by terrain class", rows,
                      [0.24, 0.26, 0.24, 0.26], note), \
        {"classes": {t["terrain"]: round(t["share_of_basin"], 4) for t in tc},
         "noise_floor_deg": L.get("class_noise_floor_deg")}


@step(66, "Does the data support the answer", "Two land-cover maps, where they disagree",
      'basin.data_quality()  # landcover: WorldCover vs ESRI')
def s_lc_agree(C):
    L = [x for x in C["quality"]["layers"] if x["layer"] == "landcover"][0]
    rows = [["property", "value"],
            ["agreement", f"{L.get('value')}"],
            ["grade", L.get("grade")],
            ["judged against", str(L.get("source"))[:30]]]
    return _table_fig("Land cover: one map against another", rows, [0.36, 0.64],
                      str(L.get("statement", ""))[:300]), \
        {"agreement": L.get("value"), "grade": L.get("grade")}


@step(67, "Does the data support the answer", "The boundary, against real gauges",
      'basin.data_quality()  # delineation')
def s_delin(C):
    L = [x for x in C["quality"]["layers"] if x["layer"] == "delineation"][0]
    rows = [["property", "value"],
            ["indicator", str(L.get("indicator"))[:30]],
            ["grade", L.get("grade")],
            ["judged against", str(L.get("source"))[:30]]]
    return _table_fig("Delineation, validated blind", rows, [0.36, 0.64],
                      str(L.get("statement", ""))[:300]), \
        {"grade": L.get("grade")}


@step(68, "Shape and network", "Every stream order, counted properly",
      'basin.morphometry()["network"]')
def s_network_table(C):
    net = C["morph"]["network"]
    rows = [["order", "streams", "reaches", "length km", "Rb"]]
    for r in net:
        rows.append([r["order"], f'{r["streams"]:,}', f'{r.get("reaches", ""):,}'
                     if r.get("reaches") else "", f'{r["total_length_km"]:,.0f}',
                     r.get("bifurcation_ratio", "")])
    note = ("Strahler streams in one column, the reaches a river dataset splits them\n"
            "into in the next. Confusing the two is the commonest morphometry error.")
    return _table_fig("The network, order by order", rows,
                      [0.16, 0.20, 0.20, 0.24, 0.20], note), \
        {"orders": len(net),
         "streams_total": sum(r["streams"] for r in net),
         "reaches_total": sum(r.get("reaches", 0) for r in net)}


@step(69, "Shape and network", "Terrain in one table", "basin.terrain_stats()")
def s_terrain_stats(C):
    ts = C["basin"].terrain_stats()
    rows = [["statistic", "value"]]
    for k, v in list(ts.items())[:12]:
        rows.append([str(k)[:26], f"{v:,.3f}" if isinstance(v, float) else str(v)[:20]])
    return _table_fig("basin.terrain_stats()", rows, [0.56, 0.44]), \
        {k: v for k, v in ts.items() if isinstance(v, (int, float))}


@step(70, "Does the data support the answer", "Which datasets this run was allowed to use",
      "basin.license_report()")
def s_licences(C):
    import basinkit as bk
    ds = bk.catalog.implemented()
    rows = [["dataset", "licence"]]
    for d in ds[:12]:
        rows.append([str(d.name)[:30], str(d.license)[:16]])
    return _table_fig(f"{len(ds)} open datasets, none needing an account", rows,
                      [0.62, 0.38],
                      "Every layer above carries its licence into its own .attrs, and\n"
                      "download_all() writes a LICENSES.txt beside the files."), \
        {"n_datasets": len(ds),
         "licences": sorted({str(d.license) for d in ds})}


# ------------------------------------------------------------------ driver

def _sha(path, cap=8 * 1024 * 1024):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        h.update(fh.read(cap))
    return h.hexdigest()[:16]


def run_everything(basin, lat, lon, out, *, max_pixels=4_000_000, sat_pixels=1_200_000,
                   stream_km2=5.0, clim_start=2000, clim_end=2024, spi_start=1985,
                   skip=(), emit=print):
    """Run every registered step. Returns (records, context)."""
    import basinkit as bk

    figs = os.path.join(out, "figures"); os.makedirs(figs, exist_ok=True)
    tabs = os.path.join(out, "tables"); os.makedirs(tabs, exist_ok=True)

    C = dict(basin=basin, lat=lat, lon=lon, max_pixels=max_pixels, sat_pixels=sat_pixels,
             stream_km2=stream_km2, clim_start=clim_start, clim_end=clim_end,
             spi_start=spi_start,
             s2_start=f"{clim_end - 1}-11-01", s2_end=f"{clim_end}-02-28",
             ls_old_start="1990-11-01", ls_old_end="1991-03-31",
             ls_new_start=f"{clim_end - 1}-11-01", ls_new_end=f"{clim_end}-03-31")
    _CTX.clear(); _CTX.update(C)

    records = []
    for s in STEPS:
        if s["id"] in skip or s["group"] in skip:
            records.append({**{k: s[k] for k in ("id", "group", "title", "code")},
                            "status": "skipped"})
            continue
        t0 = time.time()
        try:
            emit(f"INFO\t[{s['id']:>2}/{len(STEPS)}] {s['title']}")
            # Data servers time out and return 503 under load. One retry turns
            # most of those into a completed step instead of a hole in the report.
            for attempt in range(2):
                try:
                    fig, vals = s["fn"](C)
                    break
                except Exception as exc:                # noqa: BLE001
                    transient = any(t in str(exc) for t in
                                    ("503", "502", "504", "Timeout", "timed out",
                                     "Connection", "Temporarily"))
                    if attempt == 0 and transient:
                        emit("INFO\t     server busy, retrying once in 5s")
                        plt.close("all"); time.sleep(5); continue
                    raise
            name = f"{s['id']:02d}_{s['title'][:44].lower().replace(' ', '_').replace('/', '-')}"
            name = "".join(ch for ch in name if ch.isalnum() or ch in "_-")
            path = os.path.join(figs, name + ".png")
            fig.savefig(path, dpi=130, bbox_inches="tight", facecolor=SURF)
            plt.close(fig)
            records.append({**{k: s[k] for k in ("id", "group", "title", "code")},
                            "status": "ok", "figure": path, "values": vals,
                            "seconds": round(time.time() - t0, 1)})
        except Exception as exc:                        # noqa: BLE001
            plt.close("all")
            emit(f"INFO\t     failed: {exc.__class__.__name__}: {exc}")
            records.append({**{k: s[k] for k in ("id", "group", "title", "code")},
                            "status": "failed",
                            "error": f"{exc.__class__.__name__}: {exc}",
                            "traceback": traceback.format_exc()[-1500:],
                            "seconds": round(time.time() - t0, 1)})

    # tables the GIS can join to
    import csv
    vals_path = os.path.join(tabs, "analyses.csv")
    with open(vals_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "group", "analysis", "status", "key", "value"])
        for r in records:
            if r["status"] != "ok":
                w.writerow([r["id"], r["group"], r["title"], r["status"], "", ""])
                continue
            for k, v in (r.get("values") or {}).items():
                w.writerow([r["id"], r["group"], r["title"], "ok", k,
                            json.dumps(v, default=str) if isinstance(v, (dict, list)) else v])
    with open(os.path.join(out, "records.json"), "w", encoding="utf-8") as fh:
        json.dump([{k: v for k, v in r.items() if k != "traceback"} for r in records],
                  fh, indent=1, default=str)
    return records, C, vals_path


def write_manifest(path, records, C, extra=None):
    """Everything needed to run this again and get the same numbers."""
    import basinkit as bk
    mods = {}
    for n in ("numpy", "geopandas", "rasterio", "rioxarray", "xarray", "pyproj",
              "shapely", "matplotlib", "pandas"):
        try:
            mods[n] = __import__(n).__version__
        except Exception:                                # noqa: BLE001
            mods[n] = None
    try:
        datasets = [{"key": d.key, "name": d.name, "license": d.license,
                     "route": getattr(d, "route", None)}
                    for d in bk.catalog.implemented()]
    except Exception:                                    # noqa: BLE001
        datasets = []
    man = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "outlet": {"lat": C["lat"], "lon": C["lon"]},
        "choices": {k: C[k] for k in ("max_pixels", "sat_pixels", "stream_km2",
                                      "clim_start", "clim_end", "spi_start")},
        "basinkit_version": bk.__version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": mods,
        "datasets_available": datasets,
        "steps": [{k: r[k] for k in ("id", "group", "title", "code", "status")
                   if k in r} for r in records],
        "counts": {"total": len(records),
                   "ok": sum(1 for r in records if r["status"] == "ok"),
                   "failed": sum(1 for r in records if r["status"] == "failed"),
                   "skipped": sum(1 for r in records if r["status"] == "skipped")},
        "note": ("Re-run basinkit_runner.py everything with the same outlet and the "
                 "same choices to reproduce these numbers. Datasets are cited by key "
                 "and licence, not redistributed."),
    }
    if extra:
        man.update(extra)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(man, fh, indent=1, default=str)
    return man


# ---------------------------------------------------------------- outputs

def build_collage(records, path, title, subtitle, tiles, footer):
    """Every figure in one image."""
    from PIL import Image, ImageDraw, ImageFont
    figs = [r["figure"] for r in records if r["status"] == "ok" and r.get("figure")]
    if not figs:
        return None
    S = (252, 252, 251); I = (11, 11, 11); I2 = (82, 81, 78); R = (207, 206, 201)

    def font(sz, bold=False):
        for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf" % ("-Bold" if bold else ""),
                  "C:/Windows/Fonts/arial%s.ttf" % ("bd" if bold else ""),
                  "/System/Library/Fonts/Supplemental/Arial%s.ttf" % (" Bold" if bold else "")):
            if os.path.exists(p):
                return ImageFont.truetype(p, sz)
        return ImageFont.load_default()

    COLS, CW, CH, GAP, PAD, HEAD = 6, 468, 404, 18, 34, 300
    rows = (len(figs) + COLS - 1) // COLS
    W = PAD * 2 + COLS * CW + (COLS - 1) * GAP
    H = HEAD + PAD + rows * CH + (rows - 1) * GAP + 96
    cv = Image.new("RGB", (W, H), S); d = ImageDraw.Draw(cv)

    d.text((PAD, 30), subtitle.upper(), font=font(19, True), fill=I2)
    d.text((PAD, 62), title, font=font(52, True), fill=I)
    d.text((PAD, 128), footer, font=font(19), fill=I2, spacing=7)
    x = PAD; ty = HEAD - 110
    for big, small in tiles:
        d.line([(x, ty), (x, ty + 74)], fill=R, width=2)
        d.text((x + 14, ty + 2), str(big), font=font(31, True), fill=I)
        d.text((x + 14, ty + 46), small, font=font(16), fill=I2)
        x += (W - PAD * 2) // max(len(tiles), 1)
    d.line([(PAD, HEAD - 8), (W - PAD, HEAD - 8)], fill=R, width=2)

    for i, f in enumerate(figs):
        r, c = divmod(i, COLS)
        cx = PAD + c * (CW + GAP); cy = HEAD + PAD + r * (CH + GAP)
        im = Image.open(f).convert("RGB")
        sc = min((CW - 10) / im.width, (CH - 10) / im.height)
        im = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.LANCZOS)
        cv.paste(im, (cx + (CW - im.width) // 2, cy + (CH - im.height) // 2))

    fy = H - 70
    d.line([(PAD, fy - 16), (W - PAD, fy - 16)], fill=R, width=2)
    d.text((PAD, fy), "pip install basinkit      ·      ArcGIS Pro: BasinKit toolbox"
                      "      ·      MIT      ·      doi.org/10.5281/zenodo.22181933",
           font=font(19), fill=I2)
    cv.save(path, optimize=True)
    return path


def build_report(records, path, C, manifest):
    """A page per analysis: what was run, the code that ran it, and the picture."""
    from matplotlib.backends.backend_pdf import PdfPages
    import matplotlib.image as mpimg

    ok = [r for r in records if r["status"] == "ok"]
    failed = [r for r in records if r["status"] == "failed"]
    q = C.get("quality") or {}
    grade = q.get("overall", "—")

    with PdfPages(path) as pdf:
        # --- cover
        fig = plt.figure(figsize=(8.27, 11.69)); fig.patch.set_facecolor(SURF)
        fig.text(0.08, 0.93, f"BASINKIT {manifest['basinkit_version']}  ·  COMPLETE BASIN ANALYSIS",
                 fontsize=10.5, color=INK2, weight="bold")
        fig.text(0.08, 0.875, "One click.", fontsize=34, color=INK, weight="bold")
        fig.text(0.08, 0.828, f"{len(ok)} analyses.", fontsize=34, color=INK, weight="bold")
        fig.text(0.08, 0.752,
                 f"Every number and every picture in this report came from one\n"
                 f"coordinate — {C['lat']:.4f} N, {C['lon']:.4f} E — in a single run.\n"
                 f"No account, no API key, nothing downloaded by hand.",
                 fontsize=11.5, color=INK2, linespacing=1.6)
        tiles = [(f"{float(C['basin'].area_km2):,.0f} km²", "basin delineated"),
                 (f"{manifest['counts']['ok']}", "analyses completed"),
                 (f"{len(manifest.get('datasets_available', []))}", "open datasets reached"),
                 (grade, "the grade the run gave itself")]
        y = 0.665
        for big, small in tiles:
            fig.text(0.08, y, str(big), fontsize=19, color=INK, weight="bold")
            fig.text(0.08, y - 0.021, small, fontsize=9.5, color=INK2)
            y -= 0.052
        fig.lines.append(plt.Line2D([0.08, 0.92], [0.455, 0.455], transform=fig.transFigure,
                                    color=RULE, lw=1.2))
        # contents
        from collections import Counter
        counts = Counter(r["group"] for r in ok)
        fig.text(0.08, 0.425, "CONTENTS", fontsize=9.5, color=INK2, weight="bold")
        y = 0.395
        for g, n in counts.items():
            fig.text(0.08, y, g, fontsize=11, color=INK)
            fig.text(0.86, y, str(n), fontsize=11, color=INK2, ha="right")
            y -= 0.030
        if failed:
            fig.text(0.08, y - 0.02, f"{len(failed)} step(s) did not complete; they are "
                     "listed on the methods page with the reason.", fontsize=8.5, color=INK2)
        fig.text(0.08, 0.06, "MIT licence  ·  Python 3.10+  ·  ArcGIS Pro 3.x\n"
                 "doi.org/10.5281/zenodo.22181933", fontsize=9, color=INK2, linespacing=1.5)
        pdf.savefig(fig, facecolor=SURF); plt.close(fig)

        # --- one page per analysis
        last_group = None
        for r in ok:
            fig = plt.figure(figsize=(8.27, 11.69)); fig.patch.set_facecolor(SURF)
            if r["group"] != last_group:
                fig.text(0.08, 0.955, r["group"].upper(), fontsize=9.5, color=INK2, weight="bold")
                last_group = r["group"]
            fig.text(0.08, 0.915, f"{r['id']:02d}", fontsize=26, color=RULE, weight="bold")
            fig.text(0.155, 0.922, r["title"], fontsize=15, color=INK, weight="bold",
                     wrap=True)
            fig.text(0.08, 0.878, r["code"], fontsize=9.2, color=INK2, family="monospace",
                     linespacing=1.55, va="top")
            nlines = r["code"].count("\n") + 1
            img_top = 0.855 - 0.021 * nlines
            try:
                im = mpimg.imread(r["figure"])
                h_px, w_px = im.shape[:2]
                PW, PH = 8.27, 11.69                     # page, inches
                avail_w_in = 0.84 * PW
                avail_h_in = max(img_top - 0.135, 0.15) * PH
                ar = w_px / h_px
                box_w_in = min(avail_w_in, avail_h_in * ar)
                box_h_in = box_w_in / ar
                left = 0.08 + (avail_w_in - box_w_in) / 2 / PW
                ax = fig.add_axes([left, img_top - box_h_in / PH,
                                   box_w_in / PW, box_h_in / PH])
                ax.imshow(im); ax.axis("off")
            except Exception:                            # noqa: BLE001
                pass
            vals = r.get("values") or {}
            flat = [(k, v) for k, v in vals.items()
                    if not isinstance(v, (dict, list)) and v is not None][:6]
            y = 0.115
            for k, v in flat:
                fig.text(0.08, y, f"{k}", fontsize=8.6, color=INK2)
                fig.text(0.50, y, f"{v}", fontsize=8.6, color=INK)
                y -= 0.017
            pdf.savefig(fig, facecolor=SURF); plt.close(fig)

        # --- methods
        fig = plt.figure(figsize=(8.27, 11.69)); fig.patch.set_facecolor(SURF)
        fig.text(0.08, 0.95, "METHODS AND PROVENANCE", fontsize=9.5, color=INK2, weight="bold")
        fig.text(0.08, 0.905, "How to get these numbers again", fontsize=17,
                 color=INK, weight="bold")
        body = [
            f"Outlet                {C['lat']:.5f}, {C['lon']:.5f}",
            f"Run                   {manifest['created_utc']}",
            f"basinkit              {manifest['basinkit_version']}",
            f"Python                {manifest['python']}",
            "",
            "Choices that change the answer",
        ]
        for k, v in manifest["choices"].items():
            body.append(f"  {k:<18} {v}")
        body += ["", "Package versions"]
        for k, v in manifest["packages"].items():
            body.append(f"  {k:<18} {v}")
        body += ["", "Steps", f"  completed          {manifest['counts']['ok']}",
                 f"  failed             {manifest['counts']['failed']}",
                 f"  skipped            {manifest['counts']['skipped']}"]
        if failed:
            body += ["", "Did not complete"]
            for r in failed[:8]:
                body.append(f"  {r['id']:02d} {r['title'][:38]}  {r['error'][:40]}")
        fig.text(0.08, 0.855, "\n".join(body), fontsize=8.4, color=INK2,
                 family="monospace", va="top", linespacing=1.5)
        fig.text(0.08, 0.10,
                 "Datasets are cited by key and licence, never redistributed. Where a\n"
                 "licence or a national data policy forbids reproducing the primary data\n"
                 "in a report, the manifest still records which dataset, which version and\n"
                 "which access route produced the number.",
                 fontsize=9, color=INK2, linespacing=1.6)
        pdf.savefig(fig, facecolor=SURF); plt.close(fig)

        d = pdf.infodict()
        d["Title"] = "BasinKit complete basin analysis"
        d["Subject"] = f"Outlet {C['lat']:.5f}, {C['lon']:.5f}"
        d["Creator"] = f"basinkit {manifest['basinkit_version']}"
    return path
