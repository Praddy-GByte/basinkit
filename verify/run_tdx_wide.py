"""The twelve-metre backend, on a sample wide enough to carry a claim.

The first benchmark was 60 gauges in two GEOGLOWS regions. This one draws a
global sample by seed from GSIM in the 100-500 km2 band, before any result is
seen, then works through the regions holding the most of them until at least
320 gauges have been attempted. Grouping by region is a cost decision, not a
selection one: a region's catchment file is hundreds of megabytes and is read
once.
"""
import csv, os, sys, time, warnings
os.environ.setdefault("TQDM_DISABLE", "1")
warnings.filterwarnings("ignore")

import numpy as np
from collections import Counter, defaultdict

from basinkit.clip import basin_area_km2
from basinkit.delineate.tdx import _nearest_reach, delineate_tdx
from basinkit.delineate.hydrobasins import delineate_hydrobasins

#: GSIM catchment characteristics. Use area.meta, which is in square
#: kilometres; the area column in GSIM_metadata.csv is in square miles for
#: 2,395 USGS stations.
GSIM = "GSIM_catchment_characteristics.csv"

SEED = 20260918
BAND = (100.0, 500.0)
TARGET = 320
PER_VPU = 45
OUT = OUT

gauges = []
with open(GSIM) as fh:
    for r in csv.DictReader(fh):
        try:
            area = float(r["area.meta"]); lat = float(r["lat.org"]); lon = float(r["long.org"])
        except (ValueError, TypeError, KeyError):
            continue
        if BAND[0] <= area <= BAND[1] and -60 <= lat <= 72:
            gauges.append({"gsim_no": r["gsim.no"], "lat": lat, "lon": lon,
                           "reported_area_km2": area})

rng = np.random.default_rng(SEED)
order = rng.permutation(len(gauges))
pool = [gauges[i] for i in order]
print(f"{len(pool)} gauges in the {BAND[0]:.0f}-{BAND[1]:.0f} km2 band, "
      f"shuffled with seed {SEED}", flush=True)

# Which region each one falls in, from the index alone -- no downloads yet.
located = []
for g in pool[:4000]:
    try:
        link, vpu, km = _nearest_reach(g["lat"], g["lon"], 2.0, False)
    except Exception:
        continue
    g = dict(g, link=link, vpu=vpu, snap_km=round(km, 3))
    located.append(g)
print(f"{len(located)} of the first 4000 snapped to a reach within 2 km", flush=True)

by_vpu = defaultdict(list)
for g in located:
    by_vpu[g["vpu"]].append(g)
ranked = [v for v, _ in Counter({k: len(v) for k, v in by_vpu.items()}).most_common()]

plan, total = [], 0
for vpu in ranked:
    take = by_vpu[vpu][:PER_VPU]
    plan.extend(take)
    total += len(take)
    if total >= TARGET:
        break
print(f"plan: {total} gauges across {len({g['vpu'] for g in plan})} regions "
      f"-> {sorted({g['vpu'] for g in plan})}", flush=True)

fields = ["gsim_no", "vpu", "lat", "lon", "reported_area_km2", "snap_km",
          "hydrobasins_km2", "hb_err_pct", "tdx_km2", "tdx_err_pct",
          "tdx_reaches", "seconds", "error"]
new = not os.path.exists(OUT)
handle = open(OUT, "a", newline="")
writer = csv.DictWriter(handle, fieldnames=fields)
if new:
    writer.writeheader(); handle.flush()
done = set()
if not new:
    for r in csv.DictReader(open(OUT)):
        done.add(r["gsim_no"])

for i, g in enumerate(plan, 1):
    if g["gsim_no"] in done:
        continue
    t0 = time.time()
    rec = {k: g[k] for k in ("gsim_no", "vpu", "lat", "lon",
                             "reported_area_km2", "snap_km")}
    published = g["reported_area_km2"]
    try:
        geom, prov = delineate_hydrobasins(g["lat"], g["lon"], progress=False)
        area = basin_area_km2(geom)
        rec.update(hydrobasins_km2=round(area, 3),
                   hb_err_pct=round(100 * (area - published) / published, 2))
    except Exception as exc:
        rec["error"] = f"hb {type(exc).__name__}"
    try:
        geom, prov = delineate_tdx(g["lat"], g["lon"], progress=False)
        area = basin_area_km2(geom)
        rec.update(tdx_km2=round(area, 3),
                   tdx_err_pct=round(100 * (area - published) / published, 2),
                   tdx_reaches=prov.get("n_reaches"))
    except Exception as exc:
        rec["error"] = f"{rec.get('error', '')} tdx {type(exc).__name__}: {str(exc)[:90]}"
    rec["seconds"] = round(time.time() - t0, 1)
    writer.writerow(rec); handle.flush()
    print(f"[{i}/{len(plan)}] vpu{g['vpu']} {g['gsim_no']} "
          f"hb={rec.get('hb_err_pct','-')}% tdx={rec.get('tdx_err_pct','-')}% "
          f"{rec['seconds']}s {rec.get('error','')}", flush=True)

handle.close()
print("DONE", flush=True)
