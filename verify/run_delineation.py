"""Continental delineation check.

Two independent comparisons per basin:
  internal -- our equal-area sum vs HydroBASINS' own UP_AREA field
  external -- our area vs the operating agency's published figure
"""
import json, sys, time, traceback, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/claude/verify")

import basinkit as bk
from basins import REFERENCE

results = []
for name, lat, lon, published, tol, rain, region in REFERENCE:
    row = {"name": name, "lat": lat, "lon": lon, "published_km2": published,
           "tol": tol, "expected_region": region}
    t = time.time()
    try:
        b = bk.Basin.from_point(lat, lon, backend="hydrobasins", progress=False)
        p = b.provenance
        reported = p.get("reported_up_area_km2", 0)
        row.update({
            "ok": True,
            "seconds": round(time.time() - t, 1),
            "computed_km2": round(b.area_km2, 1),
            "hydrobasins_up_area_km2": round(reported, 1),
            "n_units": p.get("n_units"),
            "region_used": p.get("region"),
            "bbox_efficiency": round(b.bbox_efficiency, 3),
            "internal_err": round(abs(b.area_km2 - reported) / reported, 4) if reported else None,
            "external_err": round(abs(b.area_km2 - published) / published, 4),
        })
        row["internal_pass"] = (row["internal_err"] is not None and row["internal_err"] < 0.02)
        row["external_pass"] = row["external_err"] < tol
        row["region_pass"] = row["region_used"] == region
    except Exception as exc:
        row.update({"ok": False, "seconds": round(time.time() - t, 1),
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc()[-600:]})
    results.append(row)
    print(json.dumps(row, default=str), flush=True)

json.dump(results, open("/home/claude/verify/delineation.json", "w"), indent=2, default=str)
print("DONE", flush=True)
