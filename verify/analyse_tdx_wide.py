"""The twelve-metre backend against the default, on the wide sample."""
import csv, statistics
from collections import defaultdict

rows = []
for r in csv.DictReader(open("verify/benchmarks/tdx_wide.csv")):
    try:
        hb = float(r["hb_err_pct"]); tdx = float(r["tdx_err_pct"])
    except (ValueError, TypeError, KeyError):
        continue
    rows.append({"vpu": r["vpu"], "gsim": r["gsim_no"],
                 "area": float(r["reported_area_km2"]),
                 "hb": abs(hb), "tdx": abs(tdx),
                 "hb_signed": hb, "tdx_signed": tdx})

attempted = sum(1 for _ in csv.DictReader(open("verify/benchmarks/tdx_wide.csv")))
print(f"{attempted} gauges attempted, {len(rows)} with both backends answering\n")

def summary(sub, label):
    if not sub:
        return
    hb = [r["hb"] for r in sub]; tdx = [r["tdx"] for r in sub]
    w20_hb = sum(1 for v in hb if v <= 20) / len(hb) * 100
    w20_tdx = sum(1 for v in tdx if v <= 20) / len(tdx) * 100
    better = sum(1 for r in sub if r["tdx"] < r["hb"])
    print(f"{label:<28} {len(sub):>5} "
          f"{statistics.median(hb):>9.1f} {statistics.median(tdx):>9.1f} "
          f"{w20_hb:>8.1f} {w20_tdx:>9.1f} {better:>8} ({better/len(sub)*100:.0f}%)")

print(f"{'sample':<28} {'n':>5} {'hb med':>9} {'tdx med':>9} "
      f"{'hb<20%':>8} {'tdx<20%':>9} {'tdx better':>8}")
print("-" * 92)
summary(rows, "all")
by_vpu = defaultdict(list)
for r in rows:
    by_vpu[r["vpu"]].append(r)
for vpu in sorted(by_vpu, key=lambda v: -len(by_vpu[v])):
    summary(by_vpu[vpu], f"  region {vpu}")
print()
for lo, hi in ((100, 200), (200, 350), (350, 500)):
    summary([r for r in rows if lo <= r["area"] < hi], f"  {lo}-{hi} km2")

print("\nSigned error, to show which way each backend is wrong:")
for name in ("hb_signed", "tdx_signed"):
    vals = sorted(r[name] for r in rows)
    q = statistics.quantiles(vals, n=4)
    print(f"  {name:<12} median {statistics.median(vals):>8.1f}%  "
          f"p25 {q[0]:>8.1f}%  p75 {q[2]:>8.1f}%")

failures = []
for r in csv.DictReader(open("verify/benchmarks/tdx_wide.csv")):
    if r.get("error"):
        failures.append(r["error"][:70])
if failures:
    print(f"\n{len(failures)} rows carried an error:")
    from collections import Counter
    for kind, n in Counter(f.split(":")[0] for f in failures).most_common(8):
        print(f"  {n:>4}  {kind}")
