"""Is the output right, or does it merely look right?

    python verify/run_outputs.py

Delineation is validated at length elsewhere. This covers everything else the
package returns, because a correct boundary carries authority and the values
inside it have to earn the same confidence.

Five questions, each answerable without taking the package's word for anything:

1. Is the clipping real? The headline claim is that layers come back masked to
   the divide, not cropped to a rectangle. That is checkable: rasterise the
   polygon independently and compare which cells are missing.
2. Is the area right? Measured here in an equal-area projection, and checked
   against a geodesic area computed on the ellipsoid by pyproj, which shares no
   code with it.
3. Is the morphometry internally consistent? A morphometric table reports more
   numbers than it has freedoms, and the surplus is a set of identities that
   hold by definition. A table that breaks one has an arithmetic error in it.
4. Are the values physically plausible? Basin rainfall and elevation against
   figures published by other people for the same basins.
5. How long does the whole thing take?

Anything that fails is printed as a failure. This is not a demonstration.
"""
from __future__ import annotations

import math
import sys
import time
import warnings

import numpy as np

warnings.filterwarnings("ignore")
import basinkit as bk  # noqa: E402

# Basins whose figures other people have published, so the check is external.
CASES = [
    {"name": "Sapta Koshi at Chatara", "lat": 26.87, "lon": 87.15,
     "area_km2": 54_100,
     "rain_mm": (1_200, 1_900),   # Himalayan monsoon basin, published range
     "elev_m": (60, 8_800)},      # outlet on the Terai, headwaters on Everest
    {"name": "Danube at Bratislava", "lat": 48.14, "lon": 17.11,
     "area_km2": 131_300,
     "rain_mm": (600, 1_200),
     "elev_m": (120, 4_100)},     # Alpine headwaters
]

FAILS: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"    {'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""),
          flush=True)
    if not ok:
        FAILS.append(f"{label}: {detail}")


def geodesic_area_km2(geom) -> float:
    """Area on the WGS84 ellipsoid, computed by pyproj, sharing no code with
    the equal-area projection basinkit uses."""
    from pyproj import Geod

    geod = Geod(ellps="WGS84")
    total = 0.0
    polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
    for poly in polys:
        a, _ = geod.geometry_area_perimeter(poly)
        total += abs(a)
    return total / 1e6


def clipping_is_real(basin, arr) -> tuple[bool, str]:
    """Compare the raster's own nodata pattern against the polygon, rasterised
    here rather than by the package."""
    import geopandas as gpd
    from rasterio.features import rasterize

    da = arr.squeeze()
    transform = da.rio.transform()
    shape = (da.sizes[da.rio.y_dim], da.sizes[da.rio.x_dim])
    inside = rasterize([(basin.geometry, 1)], out_shape=shape,
                       transform=transform, fill=0, dtype="uint8").astype(bool)

    values = np.asarray(da.values, dtype="float64")
    has_data = np.isfinite(values)
    nod = da.rio.nodata
    if nod is not None and np.isfinite(nod):
        has_data &= (values != nod)

    outside = ~inside
    leaked = int((has_data & outside).sum())
    box_cells = int(outside.sum())
    kept = int((has_data & inside).sum())
    inside_cells = int(inside.sum())

    # A bbox crop would leave every cell outside the polygon populated.
    leak_share = leaked / max(box_cells, 1)
    covered = kept / max(inside_cells, 1)
    return (leak_share < 0.02 and covered > 0.95,
            f"{100*leak_share:.2f} % of cells outside the divide carry data, "
            f"{100*covered:.1f} % of cells inside do")


def morphometry_identities(m: dict) -> None:
    """Definitional relations a morphometric table cannot break.

    Rc = 4 pi A / P^2 and Cc = P / (2 sqrt(pi A)) are the same shape measured
    twice, so Rc * Cc^2 = 1 exactly. Re = 2 sqrt(A/pi) / Lb and Rf = A / Lb^2,
    so Re = (2/sqrt(pi)) sqrt(Rf). The isoperimetric inequality forces Rc <= 1.
    """
    areal = m.get("areal") or {}
    linear = m.get("linear") or {}
    relief = m.get("relief") or {}
    everything = {**areal, **linear, **relief}

    def g(*names):
        for n in names:
            for k, v in everything.items():
                if k.lower().startswith(n) and isinstance(v, (int, float)):
                    return float(v), k
        return None, None

    rc, rc_k = g("circularity")
    cc, cc_k = g("compactness")
    re_, re_k = g("elongation")
    rf, rf_k = g("form_factor", "form")
    dd, dd_k = g("drainage_density")
    lo, lo_k = g("length_of_overland", "overland")

    if rc is not None and cc is not None:
        prod = rc * cc * cc
        check(f"Rc * Cc^2 = 1   ({rc_k}={rc:.4f}, {cc_k}={cc:.4f})",
              abs(prod - 1) < 0.02, f"product = {prod:.4f}")
    if re_ is not None and rf is not None and rf > 0:
        expect = 2 / math.sqrt(math.pi) * math.sqrt(rf)
        check(f"Re = 1.128 sqrt(Rf)   ({re_k}={re_:.4f}, {rf_k}={rf:.4f})",
              abs(re_ - expect) < 0.02, f"expected {expect:.4f}")
    if rc is not None:
        check("Rc <= 1 (isoperimetric inequality)", rc <= 1.001, f"Rc = {rc:.4f}")
    if dd is not None and lo is not None and dd > 0:
        expect = 1 / (2 * dd)
        check(f"Lo = 1 / (2 Dd)   ({lo_k}={lo:.4f})",
              abs(lo - expect) < max(0.02 * expect, 0.002),
              f"expected {expect:.4f}")

    net = m.get("network") or []
    for row in net:
        rb = row.get("bifurcation_ratio")
        if rb is not None:
            check(f"Rb >= 2 at order {row['order']} (Shreve 1966)",
                  rb >= 2 - 1e-9, f"Rb = {rb:.3f}")
    if net:
        top = max(net, key=lambda r: r["order"])
        check("exactly one stream of the highest order",
              top["streams"] == 1, f"{top['streams']} of order {top['order']}")


def main() -> int:
    for case in CASES:
        print(f"\n{'=' * 74}\n{case['name']}\n{'=' * 74}", flush=True)
        t0 = time.time()
        basin = bk.Basin.from_point(case["lat"], case["lon"],
                                    backend="hydrobasins", progress=False)
        t_delin = time.time() - t0

        # --- area, against an independent computation
        geod = geodesic_area_km2(basin.geometry)
        rel = abs(basin.area_km2 - geod) / geod
        check("equal-area and geodesic areas agree",
              rel < 0.01,
              f"{basin.area_km2:,.0f} vs {geod:,.0f} km2, {100*rel:.2f} % apart")

        pub = case["area_km2"]
        err = 100 * abs(basin.area_km2 - pub) / pub
        check("area matches the published figure", err < 5,
              f"{basin.area_km2:,.0f} vs {pub:,} km2, {err:.1f} % out")

        # --- clipping
        t0 = time.time()
        dem = basin.dem(progress=False)
        t_dem = time.time() - t0
        ok, detail = clipping_is_real(basin, dem)
        check("the DEM is masked to the divide, not cropped to a box", ok, detail)

        eff = basin.bbox_efficiency
        print(f"          the basin fills {eff:.0%} of its bounding box, so a box "
              f"download would be {1/eff:.1f}x the data")

        # --- elevation plausibility
        v = np.asarray(dem.squeeze().values, dtype="float64")
        v = v[np.isfinite(v)]
        nod = dem.rio.nodata
        if nod is not None and np.isfinite(nod):
            v = v[v != nod]
        lo_e, hi_e = case["elev_m"]
        check("elevation range is physically plausible",
              v.min() >= lo_e - 200 and v.max() <= hi_e + 300,
              f"{v.min():.0f} to {v.max():.0f} m, expected about {lo_e} to {hi_e}")

        # --- rainfall against published climatology
        t0 = time.time()
        try:
            rain = basin.precipitation(2001, 2020)
            t_rain = time.time() - t0
            # chirps returns a basin-mean monthly series as an xarray object
            vals = np.asarray(getattr(rain, "values", rain), dtype="float64").ravel()
            vals = vals[np.isfinite(vals)]
            annual = float(vals.sum()) / (len(vals) / 12.0)
            lo_r, hi_r = case["rain_mm"]
            check("basin mean rainfall matches published climatology",
                  lo_r <= annual <= hi_r,
                  f"{annual:,.0f} mm/yr, published range {lo_r:,}-{hi_r:,}")
        except Exception as exc:
            t_rain = time.time() - t0
            check("rainfall retrieved", False, f"{type(exc).__name__}: {exc}")

        # --- morphometry identities
        t0 = time.time()
        try:
            m = basin.morphometry()
            t_morph = time.time() - t0
            morphometry_identities(m)
        except Exception as exc:
            t_morph = time.time() - t0
            check("morphometry computed", False, f"{type(exc).__name__}: {exc}")

        print(f"\n    time: delineation {t_delin:.1f}s, DEM {t_dem:.1f}s, "
              f"rainfall {t_rain:.1f}s, morphometry {t_morph:.1f}s, "
              f"total {t_delin+t_dem+t_rain+t_morph:.0f}s")

    print(f"\n{'=' * 74}")
    if FAILS:
        print(f"{len(FAILS)} CHECK(S) FAILED")
        for f in FAILS:
            print("  " + f)
    else:
        print("every check passed")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
