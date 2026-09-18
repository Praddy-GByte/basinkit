"""Does the suitability grade predict anything measurable?

The grade is computed from one elevation model. If it measures something real
about whether the terrain is resolvable, then a second, independently produced
model should describe the same ground differently where the grade says
LIMITED, and similarly where it says HIGH.

The measure is the correlation between the two slope fields, not their
difference in degrees. Absolute disagreement is smaller on flat ground however
unresolvable it is, so it cannot tell "the models agree" from "neither model
can see anything". Correlation can.
"""
import csv, math, statistics
from collections import Counter

rows = []
for r in csv.DictReader(open("verify/benchmarks/grade_validation.csv")):
    if r.get("error") or not r.get("grade"):
        continue
    try:
        rows.append({
            "gsim": r["gsim_no"], "grade": r["grade"],
            "r": float(r["slope_pearson_r"]),
            "absdiff": float(r["slope_median_abs_diff_deg"]),
            "slope": float(r["slope_median_cop30_deg"]),
            "err": float(r["area_abs_error_pct"]),
            "area": float(r["basin_km2"]),
            "unmet": r["unmet"], "band": r["size_band"],
        })
    except (ValueError, TypeError, KeyError):
        continue

print(f"n = {len(rows)} gauges with a grade and both elevation models")
print("grades:", dict(Counter(r["grade"] for r in rows)), "\n")


def block(label, key, fmt="{:.3f}"):
    print(f"--- {label} ---")
    print(f"{'grade':<10} {'n':>4} {'median':>10} {'p25':>10} {'p75':>10}")
    for g in ("HIGH", "MODERATE", "LIMITED"):
        vals = sorted(r[key] for r in rows if r["grade"] == g)
        if len(vals) < 2:
            print(f"{g:<10} {len(vals):>4}")
            continue
        q = statistics.quantiles(vals, n=4) if len(vals) > 3 else [vals[0], vals[0], vals[-1]]
        print(f"{g:<10} {len(vals):>4} {fmt.format(statistics.median(vals)):>10} "
              f"{fmt.format(q[0]):>10} {fmt.format(q[2]):>10}")
    print()


block("Agreement between Copernicus GLO-30 and NASADEM slope (Pearson r)", "r")
block("Median slope of the basin, degrees", "slope", "{:.2f}")
block("Absolute slope disagreement, degrees (the confounded measure)", "absdiff", "{:.2f}")
block("Catchment area error against the published figure, percent", "err", "{:.1f}")
block("Catchment area, km2", "area", "{:.0f}")


def mann_whitney(a, b):
    """Two-sided rank test, normal approximation, no scipy."""
    merged = sorted([(v, 0) for v in a] + [(v, 1) for v in b])
    values = [m[0] for m in merged]
    ranks, i = {}, 0
    while i < len(values):
        j = i
        while j + 1 < len(values) and values[j + 1] == values[i]:
            j += 1
        rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[k] = rank
        i = j + 1
    r1 = sum(ranks[k] for k, m in enumerate(merged) if m[1] == 0)
    n1, n2 = len(a), len(b)
    u1 = r1 - n1 * (n1 + 1) / 2
    u = min(u1, n1 * n2 - u1)
    sd = (n1 * n2 * (n1 + n2 + 1) / 12) ** 0.5
    z = (u - n1 * n2 / 2) / sd if sd else 0.0
    return u, z, math.erfc(abs(z) / math.sqrt(2))


print("--- rank tests, HIGH against LIMITED ---")
for key, label in (("r", "slope agreement (Pearson r)"),
                   ("err", "catchment area error")):
    high = [r[key] for r in rows if r["grade"] == "HIGH"]
    low = [r[key] for r in rows if r["grade"] == "LIMITED"]
    if len(high) > 3 and len(low) > 3:
        u, z, p = mann_whitney(high, low)
        print(f"{label:<32} U={u:>7.0f}  z={z:>6.2f}  p={p:.2e}  "
              f"(n={len(high)} vs {len(low)})")

print("\n--- which test fired, and what it cost ---")
fired = Counter()
for r in rows:
    for t in (r["unmet"] or "").split("|"):
        if t:
            fired[t] += 1
for test, n in fired.most_common():
    sub = [r for r in rows if test in (r["unmet"] or "")]
    rest = [r for r in rows if test not in (r["unmet"] or "")]
    print(f"{test:<10} unmet in {n:>4}  median r {statistics.median([x['r'] for x in sub]):.3f}"
          f"   (rest {statistics.median([x['r'] for x in rest]):.3f})")
