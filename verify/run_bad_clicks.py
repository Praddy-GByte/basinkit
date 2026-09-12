"""What happens when the click is wrong, which is most clicks.

    python verify/run_bad_clicks.py

Everything validated so far assumed a coordinate on a river. Real users click
in the sea, click the city rather than the gauge, paste coordinates the wrong
way round, and work in places with no rivers at all. Each of those either
produces a clear refusal or an absurd answer delivered with confidence, and
which one it is decides whether the tool embarrasses its author.
"""
from __future__ import annotations

import time
import warnings

warnings.filterwarnings("ignore")
import basinkit as bk  # noqa: E402

CASES = [
    ("open ocean, mid-Atlantic", 30.0, -40.0,
     "should refuse: there is no basin here"),
    ("lat and lon swapped (Koshi)", 87.15, 26.87,
     "87 N, 27 E is the Arctic Ocean; should refuse or be obviously wrong"),
    ("a city, not a gauge (Delhi)", 28.6139, 77.2090,
     "a user clicks the place name they know"),
    ("Sahara, no mapped rivers", 23.0, 12.0,
     "endorheic desert, no drainage network"),
    ("Dead Sea, endorheic", 31.5, 35.47,
     "closed basin with no outlet to the sea"),
    ("coastline, just offshore", 19.0, 72.75,
     "Mumbai coast, a few hundred metres out to sea"),
    ("Antarctica", -75.0, 0.0,
     "outside HydroSHEDS entirely"),
    ("high Arctic, Svalbard", 78.2, 15.6,
     "above 60 N, thin coverage"),
    ("a lake surface (Victoria)", -1.0, 33.0,
     "clicking open water inside a basin"),
]

print(f"{'case':<32}{'result':>16}  what came back")
print("-" * 100)
for name, lat, lon, note in CASES:
    t = time.time()
    try:
        b = bk.Basin.from_point(lat, lon, backend="auto", verify="download",
                                progress=False)
        p = b.provenance or {}
        snap = p.get("snap_distance_km")
        detail = (f"{b.area_km2:>13,.0f} km2  units={p.get('n_units')}"
                  + (f" snapped {snap} km" if snap else ""))
        verdict = "ANSWERED"
    except Exception as exc:
        detail = f"{type(exc).__name__}: {str(exc).splitlines()[0][:78]}"
        verdict = "refused"
    print(f"{name:<32}{verdict:>16}  {detail}   ({time.time()-t:.1f}s)", flush=True)
    print(f"{'':<32}{'':<16}  expected: {note}")
