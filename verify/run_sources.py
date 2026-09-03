"""Exercise every source adapter that has never been run.

Small basin on purpose: STAC imagery over a 4-million-km2 basin is not a test,
it is a denial-of-service against yourself.
"""
import json, pathlib, time, traceback, warnings
warnings.filterwarnings("ignore")
HERE = pathlib.Path(__file__).resolve().parent
import numpy as np
import basinkit as bk

# Rur at Julich, Germany -- ~2,100 km2, temperate, well mapped, small enough
# that 10 m imagery is a sane request.
b = bk.Basin.from_point(50.923, 6.357, backend="hydrobasins", progress=False)
print(f"test basin: {b.area_km2:,.0f} km2  bbox_eff {b.bbox_efficiency:.2f}", flush=True)

def describe(r):
    import xarray as xr
    if hasattr(r, "columns"):                       # GeoDataFrame
        return {"kind": "vector", "rows": len(r), "cols": list(r.columns)[:6]}
    if isinstance(r, xr.Dataset):
        out = {"kind": "dataset", "dims": dict(r.sizes), "vars": list(r.data_vars)[:8]}
        v = list(r.data_vars)
        if v:
            a = np.asarray(r[v[0]].values, dtype="float64"); a = a[np.isfinite(a)]
            if a.size:
                out["first_var_range"] = [round(float(a.min()), 3), round(float(a.max()), 3)]
        return out
    a = np.asarray(r.values, dtype="float64"); a = a[np.isfinite(a)]
    return {"kind": "array", "shape": list(r.shape),
            "range": [round(float(a.min()), 3), round(float(a.max()), 3)] if a.size else None,
            "finite_frac": round(float(a.size) / max(r.size, 1), 3),
            "crs": str(getattr(r.rio, "crs", None)) if hasattr(r, "rio") else None}

CASES = [
    ("sentinel2",    lambda: b.sentinel2("2023-06-01", "2023-09-30", cloud_cover=10)),
    ("landsat",      lambda: b.landsat("2023-06-01", "2023-09-30", cloud_cover=10)),
    ("sentinel1_rtc",lambda: b.sentinel1("2023-06-01", "2023-07-31")),
    ("esri_lulc",    lambda: b.landcover(year=2023, source="esri")),
    ("hydrolakes",   lambda: b.lakes(progress=False)),
    ("persiann",     lambda: b.precipitation(2022, source="persiann", start="2022-01-01", end="2022-03-31")),
    ("hydroriv_ord", lambda: b.rivers(min_order=1, progress=False)),
    ("soil_profile", lambda: __import__("basinkit.sources.soil", fromlist=["x"]).soil_profile(*b.centroid[::-1])),
    ("gsw_seasonality", lambda: b.surface_water("seasonality", progress=False)),
    ("terrain_stats",lambda: b.terrain_stats()),
    ("summary",      lambda: b.summary()),
]

results = {}
for name, fn in CASES:
    t = time.time()
    try:
        r = fn()
        info = r if isinstance(r, dict) else describe(r)
        results[name] = {"ok": True, "seconds": round(time.time() - t, 1), "info": info}
        print(f"OK   {name:<16} {time.time()-t:6.1f}s  {json.dumps(info, default=str)[:220]}", flush=True)
    except Exception as exc:
        results[name] = {"ok": False, "seconds": round(time.time() - t, 1),
                         "error": f"{type(exc).__name__}: {exc}",
                         "tb": traceback.format_exc()[-500:]}
        print(f"FAIL {name:<16} {time.time()-t:6.1f}s  {type(exc).__name__}: {str(exc)[:200]}", flush=True)

json.dump(results, open(HERE / "sources.json", "w"), indent=2, default=str)
print("DONE", flush=True)
