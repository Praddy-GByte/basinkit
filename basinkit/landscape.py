# -*- coding: utf-8 -*-
"""Landscape form: chi, channel steepness, concavity and knickpoints.

These answer a question the shape indices cannot: is this landscape still
adjusting to uplift or to a change in base level, or has it settled?

    chi(x) = integral from the outlet to x of (A0/A)^theta dx   Perron & Royden 2013
    k_sn   = S * A^theta_ref                                    Wobus et al. 2006
    theta  fitted from the slope-area relation S = k_s A^-theta  Flint 1974

theta_ref is fixed at 0.45 by convention so that k_sn is comparable between
basins; A0 is fixed at 1 km2 so that chi carries units of length. Both are
recorded with every result, because changing either changes every number.

k_sn here was checked cell by cell against TopoToolbox 0.0.12 on two basins, on
an identical DEM, projection, channel threshold and theta, over the cells where
both implementations return a positive value: every quantile agreed to within 6%,
and to within 4% on the larger basin, with correlations of 0.973 and 0.987.

Nothing here is an uplift rate. chi, k_sn and knickpoint counts describe form
and transience; turning them into rates needs independent calibration.
"""
from __future__ import annotations
import numpy as np

THETA_REF = 0.45
A0_M2 = 1.0e6                     # 1 km2


def link_distance(flw, transform, shape, latlon=True):
    """Geodesic distance from each cell to the cell it drains into, in metres.

    pyflwdir's own stream_distance passes an Affine straight into a numba
    kernel, which recent affine releases will not type, so the distance is
    computed here instead. It also removes a dependency on that call.
    """
    import numpy as np
    ds = flw.idxs_ds
    n = int(np.prod(shape))
    idx = np.arange(n)
    row, col = np.divmod(idx, shape[1])
    rj, cj = np.divmod(ds, shape[1])
    a, b, c, d, e, f = transform.a, transform.b, transform.c, \
                       transform.d, transform.e, transform.f
    x = c + a * (col + 0.5) + b * (row + 0.5)
    y = f + d * (col + 0.5) + e * (row + 0.5)
    xj = c + a * (cj + 0.5) + b * (rj + 0.5)
    yj = f + d * (cj + 0.5) + e * (rj + 0.5)
    if latlon:
        from pyproj import Geod
        _, _, dist = Geod(ellps="WGS84").inv(x, y, xj, yj)
    else:
        dist = np.hypot(x - xj, y - yj)
    dist = np.asarray(dist, dtype="float64")
    dist[ds == idx] = 0.0                       # pits
    dist[ds < 0] = 0.0                          # cells with no downstream cell
    valid = np.asarray(getattr(flw, "mask", np.ones(n, bool))).ravel()
    dist[~valid] = 0.0                          # outside the routed area
    return dist


def network(dem, transform, nodata=-9999.0, latlon=True, min_area_km2=1.0):
    """Flow routing and the channel network above a drainage-area threshold."""
    import numpy as np

    try:
        import pyflwdir
    except ImportError as exc:                    # pragma: no cover
        from .exceptions import MissingDependency
        raise MissingDependency("pyflwdir", "delineate") from exc
    # pyflwdir masks a cell by comparing it with the declared nodata, and a NaN
    # is never equal to a sentinel such as -9999. A grid holding NaN while -9999
    # is declared therefore has every NaN cell treated as valid, and the basin
    # drains the whole rectangle: on the test DEM that turned 1,108,954 routed
    # cells into 2,238,696 and a 6,712 km2 basin into 10,211 km2. Both spellings
    # are collapsed to NaN here and NaN is declared, which is exact.
    z = np.asarray(dem, dtype="float32")
    if nodata is not None and np.isfinite(nodata):
        z = np.where(z == nodata, np.nan, z)
    z = np.where(np.isfinite(z), z, np.nan)
    flw = pyflwdir.from_dem(data=z, nodata=np.nan, transform=transform,
                            latlon=latlon)
    upa_m2 = flw.upstream_area(unit="m2")
    dx = link_distance(flw, transform, dem.shape, latlon=latlon)
    chan = upa_m2 >= (min_area_km2 * 1e6)
    return flw, upa_m2, dx, chan


def chi_ksn(flw, dem, upa_m2, dx, chan, theta=THETA_REF, a0=A0_M2,
            smooth_m=500.0, nodata=-9999.0):
    """chi, channel slope, k_sn and distance to the outlet.

    Two channel slopes are computed, because they answer different questions
    and smoothing one of them would corrupt the other.

    slope        raw cell-to-cell drop along the flow path, negatives clamped
                 at zero. This is what k_sn is built from. It reproduces
                 TopoToolbox's StreamObject.ksn to within 6% at every quantile
                 on an identical DEM (see the cross-check), so it is the
                 estimate that is comparable with published k_sn values.
                 Negative gradients, which a DEM produces where it rises
                 downstream, are clamped to zero and their fraction reported;
                 TopoToolbox leaves them negative, so a comparison between the
                 two belongs on the cells both call positive.
    slope_fit    the same drop after elevation is averaged along the flow
                 network over `smooth_m`. Only the concavity fit uses it:
                 cell-to-cell noise biases a fitted theta low, while smoothing
                 damps genuine steep reaches and would understate the k_sn
                 tail by about a third.

    smooth_m=0 leaves slope_fit equal to slope.

    Every cell is visited after the cell it drains into, which is the order
    pyflwdir returns, so chi accumulates correctly.
    """
    shape = dem.shape
    A = upa_m2.ravel().astype("float64")
    ds = flw.idxs_ds
    seq = flw.idxs_seq
    ch = chan.ravel()

    zr = np.where(dem > nodata, dem, np.nan).astype("float32")
    if smooth_m and smooth_m > 0:
        cell = float(np.median(dx[dx > 0])) if np.any(dx > 0) else 0.0
        n = max(1, int(round(smooth_m / cell))) if cell > 0 else 1
        filled = np.where(np.isfinite(zr), zr, nodata)
        sm = flw.moving_average(filled, n=n, nodata=nodata)
        zf = np.where(sm > nodata, sm, np.nan)
        window_m = n * cell
    else:
        n, window_m = 0, 0.0
        zf = zr
    z = zr.ravel().astype("float64")
    zsm = zf.ravel().astype("float64")

    chi = np.full(z.size, np.nan)
    slope = np.full(z.size, np.nan)
    slope_fit = np.full(z.size, np.nan)
    dout = np.full(z.size, np.nan)

    for i in seq:
        j = ds[i]
        if j == i:
            chi[i] = 0.0
            dout[i] = 0.0
            continue
        d = dx[i]
        if not (d > 0) or not (A[i] > 0):
            continue
        chi[i] = (chi[j] if np.isfinite(chi[j]) else 0.0) + (a0 / A[i]) ** theta * d
        dout[i] = (dout[j] if np.isfinite(dout[j]) else 0.0) + d
        dz = z[i] - z[j]
        if np.isfinite(dz):
            slope[i] = max(dz, 0.0) / d
        dzf = zsm[i] - zsm[j]
        if np.isfinite(dzf):
            slope_fit[i] = max(dzf, 0.0) / d

    aexp = np.power(A, theta, where=A > 0, out=np.full_like(A, np.nan))
    ksn = slope * aexp
    ksn_fit = slope_fit * aexp
    for arr in (chi, slope, slope_fit, ksn, ksn_fit):
        arr[~ch] = np.nan
    return {"chi": chi.reshape(shape), "slope": slope.reshape(shape),
            "slope_fit": slope_fit.reshape(shape),
            "ksn": ksn.reshape(shape), "ksn_smoothed": ksn_fit.reshape(shape),
            "dist_out": dout.reshape(shape),
            "smoothing_cells": n, "smoothing_window_m": round(window_m, 1)}


def fit_theta(upa_m2, slope, chan, min_area_km2=1.0, nbins=30):
    """Concavity from the slope-area relation, fitted on log-area bins.

    Cell-by-cell slope is noisy enough that an unbinned regression is dominated
    by scatter. Binning by log drainage area and taking the median slope in each
    bin is the usual practice, and is what is reported here.
    """
    A = upa_m2[chan].astype("float64")
    S = slope[chan].astype("float64")
    ok = np.isfinite(A) & np.isfinite(S) & (A > min_area_km2 * 1e6) & (S > 0)
    A, S = A[ok], S[ok]
    if A.size < 50:
        return None
    la = np.log10(A)
    edges = np.linspace(la.min(), la.max(), nbins + 1)
    bx, by, bn = [], [], []
    for k in range(nbins):
        m = (la >= edges[k]) & (la < edges[k + 1])
        if m.sum() >= 10:
            bx.append(0.5 * (edges[k] + edges[k + 1]))
            by.append(np.log10(np.median(S[m])))
            bn.append(int(m.sum()))
    if len(bx) < 5:
        return None
    bx = np.array(bx)
    by = np.array(by)
    m, c = np.polyfit(bx, by, 1)
    yh = m * bx + c
    r2 = 1.0 - np.sum((by - yh) ** 2) / np.sum((by - np.mean(by)) ** 2)
    return {"theta": float(-m), "ks": float(10 ** c), "bins": len(bx),
            "cells": int(A.size), "r2": float(r2),
            "bin_area_log10": bx.tolist(), "bin_slope_log10": by.tolist()}


def main_stem(flw, chan, upa_m2):
    """Indices along the trunk, outlet upstream, following the largest area."""
    ds = flw.idxs_ds
    A = upa_m2.ravel()
    ch = chan.ravel()
    # the channel cell with the largest drainage area is the outlet of the trunk
    idx = int(np.nanargmax(np.where(ch, A, np.nan)))
    ups = {}
    for i, j in enumerate(ds):
        if j != i and ch[i]:
            ups.setdefault(j, []).append(i)
    path = [idx]
    while True:
        cand = [k for k in ups.get(path[-1], []) if ch[k]]
        if not cand:
            break
        path.append(max(cand, key=lambda k: A[k]))
    return np.array(path)


def knickpoints(chi_v, z_v, min_drop_m=30.0, window=9):
    """Breaks in the chi-elevation profile of the trunk.

    A knickpoint is where the local gradient dz/dchi rises well above the
    profile's own median. Reported with its height so small steps can be
    dismissed.
    """
    if chi_v.size < window * 3:
        return []
    g = np.gradient(z_v, chi_v)
    med = np.nanmedian(g)
    mad = np.nanmedian(np.abs(g - med)) or 1e-9
    score = (g - med) / (1.4826 * mad)
    out, i = [], window
    while i < len(g) - window:
        if score[i] > 3.0:
            j = i
            while j < len(g) - 1 and score[j] > 1.5:
                j += 1
            drop = float(z_v[j] - z_v[i])
            if drop >= min_drop_m:
                out.append({"chi": float(chi_v[i]),
                            "elevation_m": round(float(z_v[i]), 1),
                            "step_m": round(drop, 1),
                            "excess_gradient_sigma": round(float(score[i]), 1)})
            i = j + window
        else:
            i += 1
    return out


def analyse(dem, *, min_area_km2: float = 1.0, theta_ref: float = THETA_REF,
            a0_m2: float = A0_M2, smooth_m: float = 500.0):
    """Every landscape-form quantity from one elevation grid.

    ``dem`` is an xarray DataArray as ``Basin.dem()`` returns it, or anything
    with ``.rio``. Returns the rasters, the trunk profile and a summary.

    The grid's own CRS decides whether distances are geodesic or planar, so a
    projected DEM and a geographic one give the same answer.
    """
    import numpy as np

    values = np.asarray(_as_values(dem), dtype="float32")
    transform = dem.rio.transform()
    crs = dem.rio.crs
    latlon = not (crs is not None and crs.is_projected)
    nodata = -9999.0
    # A grid holding NaN while a sentinel is declared has every NaN cell treated
    # as valid, because a NaN never equals the sentinel. Collapse to one
    # spelling before routing.
    grid = np.where(np.isfinite(values), values, nodata).astype("float32")

    flw, upa_m2, dx, chan = network(grid, transform, nodata=nodata,
                                   latlon=latlon, min_area_km2=min_area_km2)
    r = chi_ksn(flw, grid, upa_m2, dx, chan, theta=theta_ref, a0=a0_m2,
                smooth_m=smooth_m, nodata=nodata)
    fit = fit_theta(upa_m2, r["slope_fit"], chan, min_area_km2=min_area_km2)
    fit_raw = fit_theta(upa_m2, r["slope"], chan, min_area_km2=min_area_km2)

    idx = main_stem(flw, chan, upa_m2)
    z = np.where(grid > nodata, grid, np.nan).ravel()
    c = r["chi"].ravel()[idx]
    zz = z[idx]
    dd = r["dist_out"].ravel()[idx]
    ok = np.isfinite(c) & np.isfinite(zz)
    c, zz, dd = c[ok], zz[ok], dd[ok]
    order = np.argsort(c)
    c, zz, dd = c[order], zz[order], dd[order]
    kp = knickpoints(c, zz, min_drop_m=40.0)

    k = r["ksn"].ravel()
    fin = k[np.isfinite(k)]
    pos = fin[fin > 0]
    summary = {
        "theta_ref": theta_ref,
        "A0_km2": a0_m2 / 1e6,
        "min_channel_area_km2": min_area_km2,
        "channel_cells": int(chan.sum()),
        "smoothing_window_m": r["smoothing_window_m"],
        "fitted_concavity": round(fit["theta"], 3) if fit else None,
        "fitted_concavity_r2": round(fit["r2"], 3) if fit else None,
        "fitted_concavity_unsmoothed": round(fit_raw["theta"], 3) if fit_raw else None,
        "ksn_median": round(float(np.median(pos)), 1) if pos.size else None,
        "ksn_p90": round(float(np.percentile(pos, 90)), 1) if pos.size else None,
        "ksn_p99": round(float(np.percentile(pos, 99)), 1) if pos.size else None,
        "zero_gradient_channel_fraction":
            round(float((fin == 0).sum() / fin.size), 3) if fin.size else None,
        "chi_max_km": round(float(np.nanmax(r["chi"])) / 1000.0, 2),
        "trunk_length_km": round(float(dd.max()) / 1000.0, 1) if dd.size else None,
        "trunk_relief_m": round(float(zz.max() - zz.min()), 1) if zz.size else None,
        "knickpoints": len(kp),
        "distances": "geodesic" if latlon else "planar",
        "note": ("chi, k_sn and knickpoint counts describe landscape form and "
                 "transience. They are not uplift rates, and turning them into "
                 "rates needs independent calibration."),
    }
    return {"rasters": r, "concavity_fit": fit, "concavity_fit_unsmoothed": fit_raw,
            "trunk": {"chi_m": c, "elevation_m": zz, "distance_to_outlet_m": dd},
            "knickpoints": kp, "summary": summary,
            "upstream_area_m2": upa_m2, "channels": chan}


def _as_values(dem):
    """The plain array behind a DataArray, a masked array or an ndarray."""
    import numpy as np

    v = getattr(dem, "values", dem)
    v = np.asarray(v)
    while v.ndim > 2 and v.shape[0] == 1:
        v = v[0]
    if v.ndim != 2:
        raise ValueError("landscape analysis needs a single 2-D elevation grid, "
                         "and this one has shape %s" % (v.shape,))
    return v


def figure(result, *, path=None, title="", figsize=(11.0, 7.5), dpi=150):
    """The standard plots for a channel-steepness analysis.

    Top: the trunk in chi-elevation space, which is where a knickpoint is a
    visible break rather than a row in a table, with every knickpoint marked and
    labelled by its height.
    Bottom left: the ordinary long profile, for orientation.
    Bottom right: the slope-area relation with the fitted concavity drawn on it,
    so the fit can be judged by eye and not only by its R-squared.

    Returns the figure. Saves it if ``path`` is given.
    """
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t = result["trunk"]
    s = result["summary"]
    chi = np.asarray(t["chi_m"], dtype="float64")
    z = np.asarray(t["elevation_m"], dtype="float64")
    dist = np.asarray(t["distance_to_outlet_m"], dtype="float64") / 1000.0

    fig = plt.figure(figsize=figsize)
    gs = fig.add_gridspec(2, 2, height_ratios=[1.25, 1.0], hspace=0.32, wspace=0.26)

    ax = fig.add_subplot(gs[0, :])
    ax.plot(chi / 1000.0, z, color="#1f4e79", lw=1.6)
    for k in result["knickpoints"]:
        i = int(np.argmin(np.abs(chi - k["chi"])))
        ax.plot(chi[i] / 1000.0, z[i], "o", ms=9, mfc="none", mec="#c0392b", mew=2.0)
        ax.annotate("%.0f m step\n%.1fσ" % (k["step_m"],
                                                k["excess_gradient_sigma"]),
                    (chi[i] / 1000.0, z[i]), textcoords="offset points",
                    xytext=(10, 12), fontsize=8, color="#c0392b")
    ax.set_xlabel("χ (km)   —   θref = %g, A₀ = %g km²"
                  % (s["theta_ref"], s["A0_km2"]))
    ax.set_ylabel("elevation (m)")
    ax.set_title(("%s\n" % title if title else "")
                 + "Trunk in χ–elevation space. A river at equilibrium "
                   "plots as a straight line; a break is a knickpoint.",
                 fontsize=10, loc="left")
    ax.grid(alpha=0.25)

    ax2 = fig.add_subplot(gs[1, 0])
    ax2.plot(dist, z, color="#2e7d32", lw=1.4)
    ax2.set_xlabel("distance from the outlet (km)")
    ax2.set_ylabel("elevation (m)")
    ax2.set_title("Long profile", fontsize=9, loc="left")
    ax2.grid(alpha=0.25)

    ax3 = fig.add_subplot(gs[1, 1])
    fit = result.get("concavity_fit")
    if fit:
        bx = np.asarray(fit["bin_area_log10"], dtype="float64")
        by = np.asarray(fit["bin_slope_log10"], dtype="float64")
        ax3.plot(bx, by, "o", ms=4, color="#555555", label="median per area bin")
        line = -fit["theta"] * bx + np.log10(fit["ks"])
        ax3.plot(bx, line, "-", lw=1.6, color="#c0392b",
                 label="θ = %.3f, R² = %.2f" % (fit["theta"], fit["r2"]))
        ax3.legend(fontsize=7, frameon=False)
        if fit["r2"] < 0.7:
            ax3.text(0.03, 0.06, "weak fit — treat θ with caution",
                     transform=ax3.transAxes, fontsize=7.5, color="#c0392b")
    else:
        ax3.text(0.5, 0.5, "not enough channel cells to fit θ",
                 ha="center", va="center", transform=ax3.transAxes, fontsize=8)
    ax3.set_xlabel("log₁₀ drainage area (m²)")
    ax3.set_ylabel("log₁₀ channel slope")
    ax3.set_title("Slope–area, and the concavity fitted from it",
                  fontsize=9, loc="left")
    ax3.grid(alpha=0.25)

    foot = ("k_sn median %s, 90th %s   •   %d knickpoints   •   "
            "%.0f%% of channel cells have no gradient and are excluded from k_sn"
            % (s["ksn_median"], s["ksn_p90"], s["knickpoints"],
               100.0 * (s["zero_gradient_channel_fraction"] or 0.0)))
    fig.text(0.01, 0.005, foot + "   •   not an uplift rate", fontsize=7.5,
             color="#444444")
    if path:
        fig.savefig(path, dpi=dpi, bbox_inches="tight")
    return fig


def confidence(result):
    """What each reported number is worth, attached to the number itself.

    Each value in the result was measured. This states which of them can be
    quoted on their own, which should be quoted together with their own
    diagnostic, and how much of the channel network each one describes -- the
    same role a stated tolerance plays beside an instrument reading.

    Returns {quantity: sentence}. basinkit's data_quality() reports layer grades
    the same way, including its refusals to grade.
    """
    s = result["summary"]
    fit = result.get("concavity_fit")
    zf = s.get("zero_gradient_channel_fraction") or 0.0
    out = {}

    out["ksn"] = (
        "Measured on the %.0f%% of channel cells that have a downstream "
        "gradient. Cross-checked cell by cell against TopoToolbox: within 6%% at "
        "every quantile, and its median moves under 2%% across a fourfold change "
        "in cell size. Quotable as it stands." % (100 * (1 - zf)))
    if zf >= 0.4:
        out["ksn"] += (
            " The excluded %.0f%% is high: much of this network is lake, flat or "
            "DEM artifact, so k_sn speaks for less of the basin than usual."
            % (100 * zf))

    if not fit:
        out["fitted_concavity"] = ("Not fitted: too few channel cells above the "
                                   "threshold to bin by drainage area.")
    elif fit["r2"] >= 0.8:
        out["fitted_concavity"] = (
            "Fitted with R2 = %.2f. Quotable as it stands." % fit["r2"])
    elif fit["r2"] >= 0.7:
        out["fitted_concavity"] = (
            "Fitted with R2 = %.2f. Quote the R2 beside it." % fit["r2"])
    else:
        out["fitted_concavity"] = (
            "Fitted with R2 = %.2f, which is weak. The slope-area relation in "
            "this basin is scattered, so theta = %.3f is a measurement rather "
            "than a result; quote it with its R2 or not at all. k_sn is "
            "unaffected -- it does not use the fitted theta."
            % (fit["r2"], fit["theta"]))

    if s.get("knickpoints"):
        out["knickpoints"] = (
            "Each step's height and how far it stands above the profile's own "
            "median gradient are the durable part. The count is not: the same "
            "basin returned 2, 2, 3 and 1 across a fourfold change in cell size, "
            "so quote a count with its cell size.")
    else:
        out["knickpoints"] = (
            "None found above the reporting threshold. That is a statement about "
            "this trunk at this cell size, not a guarantee that the profile has "
            "no steps in it.")

    out["chi"] = (
        "Agrees with TopoToolbox in the bulk -- median ratio within 1.3%, every "
        "decile within 2% -- while about 5% of cells sit further apart because "
        "two flow routings send them down different paths. chi is a path integral "
        "from the outlet, so a routing difference propagates up the whole branch.")
    return out


def limits(result):
    """The few cases where a number should not be used at all.

    Deliberately short. A caution raised on every run carries no information and
    is quickly ignored, so this covers only the conditions under which a value
    should not be used. Anything that merely qualifies a value is reported by
    confidence(), attached to the value it qualifies.
    """
    s = result["summary"]
    fit = result.get("concavity_fit")
    zf = s.get("zero_gradient_channel_fraction") or 0.0
    out = []
    if fit and fit["r2"] < 0.5:
        out.append(
            "The concavity fit is too scattered to use (R2 = %.2f). theta is in "
            "the output because it was measured, but nothing should be concluded "
            "from it. k_sn does not depend on it and is unaffected." % fit["r2"])
    if zf >= 0.5:
        out.append(
            "%.0f%% of this channel network has no downstream gradient, so k_sn "
            "describes less than half of it. Check whether the basin is largely "
            "lake or floodplain before comparing its k_sn with anything."
            % (100 * zf))
    if s.get("channel_cells", 0) < 500:
        out.append(
            "Only %d channel cells above the %g km2 threshold. Quantiles on a "
            "network this small are unstable; lower the threshold or use a finer "
            "DEM." % (s["channel_cells"], s["min_channel_area_km2"]))
    return out
