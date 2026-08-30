import json, time, traceback, warnings
warnings.filterwarnings("ignore")
import numpy as np
import basinkit as bk

out = {}
def run(name, fn):
    t = time.time()
    try:
        r = fn()
        out[name] = {"ok": True, "s": round(time.time()-t,1), "info": r}
        print(f"OK   {name:<20} {time.time()-t:6.1f}s  {json.dumps(r, default=str)[:300]}", flush=True)
    except Exception as e:
        out[name] = {"ok": False, "s": round(time.time()-t,1), "error": f"{type(e).__name__}: {e}",
                     "tb": traceback.format_exc()[-500:]}
        print(f"FAIL {name:<20} {time.time()-t:6.1f}s  {type(e).__name__}: {str(e)[:200]}", flush=True)

small = bk.Basin.from_point(50.923, 6.357, backend="hydrobasins", progress=False)

def stats(ds, band):
    a = ds[band].compute() if hasattr(ds, "data_vars") else ds
    v = np.asarray(a.values, dtype="float64"); f = np.isfinite(v)
    return {"shape": list(a.shape), "finite_frac": round(float(f.mean()), 3),
            "range": [round(float(v[f].min()),3), round(float(v[f].max()),3)] if f.any() else None,
            "mean": round(float(v[f].mean()),3) if f.any() else None}

run("landsat",  lambda: stats(small.landsat("2023-06-01","2023-09-30", cloud_cover=15), "red"))
run("sentinel1",lambda: stats(small.sentinel1("2023-06-01","2023-07-31"), "vv"))
run("esri_lulc",lambda: stats(small.landcover(year=2023, source="esri"), "data"))
run("persiann", lambda: {k: round(float(v),2) for k,v in
        [("mean_mm_day", small.precipitation(2022, 2022, source="persiann").mean()),
         ("n", small.precipitation(2022, 2022, source="persiann").size)]})

# --- Murray: is the shortfall non-contributing area, or a bug? ---
def murray():
    b = bk.Basin.from_point(-34.108, 141.913, backend="hydrobasins", progress=False)
    tc = b.water_balance(2000, 2019)
    ppt = float(tc["ppt"].mean())*12
    q   = float(tc["q"].mean())*12
    return {"area_km2": round(b.area_km2), "published_nominal_km2": 950000,
            "hydrobasins_up_area": round(b.provenance["reported_up_area_km2"]),
            "mean_annual_ppt_mm": round(ppt,1), "mean_annual_runoff_mm": round(q,2),
            "runoff_coefficient": round(q/ppt, 4),
            "note": "a runoff coefficient near zero over a basin this size means most of it does not route to the outlet"}
run("murray_diagnosis", murray)

# --- backend cross-check on the same outlet ---
def cross():
    lat, lon = 26.870, 87.150
    res = {}
    for backend in ("hydrobasins", "api"):
        try:
            b = bk.Basin.from_point(lat, lon, backend=backend, progress=False)
            res[backend] = round(b.area_km2, 1)
        except Exception as e:
            res[backend] = f"{type(e).__name__}: {e}"
    if all(isinstance(v,(int,float)) for v in res.values()):
        a, c = res["hydrobasins"], res["api"]
        res["relative_difference"] = round(abs(a-c)/max(a,c), 4)
    return res
run("backend_crosscheck", cross)

# --- CHIRPS vs TerraClimate on the same basin, independent sensors ---
def rain_cross():
    b = bk.Basin.from_point(26.870, 87.150, backend="hydrobasins", progress=False)
    ch = float(b.precipitation(2010, 2019, progress=False).mean())*12
    tc = float(b.water_balance(2010, 2019)["ppt"].mean())*12
    return {"chirps_mm_yr": round(ch,1), "terraclimate_mm_yr": round(tc,1),
            "relative_difference": round(abs(ch-tc)/max(ch,tc), 3)}
run("rainfall_crosscheck", rain_cross)

json.dump(out, open("/home/claude/verify/rest.json","w"), indent=2, default=str)
print("DONE", flush=True)
