"""Does the suitability grade mean anything?

The grade is built from one elevation model. If it is measuring something real,
then where it says LIMITED, a second, independently produced elevation model
should describe the same ground differently -- because the terrain is below
what either can resolve. Where it says HIGH, the two should agree.

Copernicus GLO-30 comes from TanDEM-X radar flown 2011-2015. NASADEM comes
from the Shuttle Radar Topography Mission, February 2000, separately
reprocessed. Different sensors, different decades, different processing
chains, so their disagreement is not a shared artefact.

Sample drawn by seed 20260918 from the blind validation set, before any result
was seen.
"""
import csv, json, os, sys, time, traceback, warnings
os.environ.setdefault("TQDM_DISABLE", "1")
warnings.filterwarnings("ignore")

import numpy as np
import basinkit as bk
from basinkit.suitability import suitability
from basinkit.terrain import slope

#: The blind validation set: one row per gauge with its published area and
#: the error basinkit made on it. Not shipped -- see docs/verification.md.
BLIND_SET = "bench/combined.csv"

SEED = 20260918
TARGET = 160
OUT = OUT

rows = []
for r in csv.DictReader(open(BLIND_SET)):
    try:
        area = float(r["reported_area_km2"]); err = float(r["abs_error_pct"])
    except (ValueError, TypeError):
        continue
    if not (20 <= area <= 10000):
        continue
    rows.append({"gsim_no": r["gsim_no"], "country": r["country"],
                 "lat": float(r["lat"]), "lon": float(r["lon"]),
                 "reported_area_km2": area, "size_band": r["size_band"],
                 "area_abs_error_pct": err})

rng = np.random.default_rng(SEED)
order = rng.permutation(len(rows))
sample = [rows[i] for i in order[:TARGET]]
print(f"drew {len(sample)} of {len(rows)} eligible gauges with seed {SEED}", flush=True)

fields = ["gsim_no", "country", "reported_area_km2", "size_band",
          "area_abs_error_pct", "basin_km2", "grade", "unmet", "advisory",
          "cells", "filling_pct", "slope_below_floor_pct",
          "relief_ratio", "water_pct", "coverage_pct",
          "slope_pearson_r", "slope_median_abs_diff_deg", "slope_p90_abs_diff_deg",
          "slope_median_cop30_deg", "overlap_cells", "seconds", "error"]
new = not os.path.exists(OUT)
handle = open(OUT, "a", newline="")
writer = csv.DictWriter(handle, fieldnames=fields)
if new:
    writer.writeheader(); handle.flush()

done = set()
if not new:
    for r in csv.DictReader(open(OUT)):
        done.add(r["gsim_no"])

for i, g in enumerate(sample, 1):
    if g["gsim_no"] in done:
        continue
    t0 = time.time()
    rec = {k: g[k] for k in ("gsim_no", "country", "reported_area_km2",
                             "size_band", "area_abs_error_pct")}
    try:
        b = bk.Basin.from_point(g["lat"], g["lon"], backend="hydrobasins",
                                progress=False)
        # Both models are held in memory at once and every derived array is
        # another copy of the basin, so the raster is capped rather than left
        # at native resolution. The cap applies identically to both, so the
        # comparison between them is unaffected; only the absolute cell size
        # changes, and it is recorded.
        d30 = b.dem(product="cop30", progress=False, max_pixels=6_000_000)
        dna = b.dem(product="nasadem", progress=False, max_pixels=6_000_000)

        s = suitability(b, dem=d30)
        by = {t["test"]: t for t in s["tests"]}
        rec.update(basin_km2=round(b.area_km2, 2), grade=s["grade"],
                   unmet="|".join(s["unmet"]), advisory="|".join(s["advisory"]),
                   cells=int(d30.size),
                   filling_pct=by["filling"]["measured"],
                   slope_below_floor_pct=by["slope"]["measured"],
                   relief_ratio=by["relief"]["measured"],
                   water_pct=by["water"]["measured"],
                   coverage_pct=by["coverage"]["measured"])

        s30 = slope(d30)
        a = np.asarray(s30.values, dtype="float32")
        c = np.asarray(slope(dna).rio.reproject_match(s30).values,
                       dtype="float32")
        del d30, dna, s30
        ok = np.isfinite(a) & np.isfinite(c)
        if ok.sum() > 100:
            x, y = a[ok].astype("float64"), c[ok].astype("float64")
            diff = np.abs(x - y)
            # The scale-free measure, and the one that matters. Absolute
            # disagreement in degrees is smaller on flat ground however
            # unresolvable it is, so it cannot separate "the two models agree"
            # from "neither model can see anything". Correlation can: where the
            # terrain is above what the models resolve, they describe the same
            # hillsides and the two fields track each other; where it is below,
            # both are returning their own noise and the correlation collapses.
            sx, sy = float(x.std()), float(y.std())
            r = (float(((x - x.mean()) * (y - y.mean())).mean() / (sx * sy))
                 if sx > 1e-9 and sy > 1e-9 else None)
            rec.update(slope_pearson_r=None if r is None else round(r, 4),
                       slope_median_abs_diff_deg=round(float(np.median(diff)), 4),
                       slope_p90_abs_diff_deg=round(float(np.percentile(diff, 90)), 4),
                       slope_median_cop30_deg=round(float(np.median(x)), 4),
                       overlap_cells=int(ok.sum()))
    except Exception as exc:
        rec["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
    rec["seconds"] = round(time.time() - t0, 1)
    writer.writerow(rec); handle.flush()
    print(f"[{i}/{len(sample)}] {rec['gsim_no']} {rec.get('grade', '-'):8s} "
          f"r={rec.get('slope_pearson_r', '-')} "
          f"err={rec['area_abs_error_pct']} {rec['seconds']}s "
          f"{rec.get('error', '')}", flush=True)

handle.close()
print("DONE", flush=True)
