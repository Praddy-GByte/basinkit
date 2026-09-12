# Verification scripts

These produce the numbers in `docs/verification.md`. They hit real endpoints,
so they are slow and they will drift as upstream data changes, which is the
point.

```bash
python verify/run_delineation.py   # 12 named gauges, vs published areas
python verify/run_sources.py       # every source adapter on one small basin
python verify/run_rest.py          # cross-checks and the full pipeline to disk
python verify/run_outputs.py       # are the layers themselves right, not just the polygon
python verify/run_bad_clicks.py    # oceans, cities, lakes, deserts, swapped coordinates
```

`basins.py` holds the reference gauges. Published areas come from operating
agencies and GRDC station records, **not** from HydroBASINS, so agreement is an
external check rather than a tautology.

Those twelve are a demonstration, not the validation. They were chosen because
their areas are published, which selects for large, well-studied rivers, and
large rivers are what any method gets right. The validation that decides what
the package can claim is the blind one against 2,550 gauges in 99 countries,
written up in `docs/verification.md`, which reports accuracy by catchment size
because that is the only way the numbers mean anything.

Results are written as JSON next to the scripts.

## QGIS plugin

QGIS cannot be installed in this environment, so the plugin is checked against
stubbed bindings in `qgis_stub/`. That proves less than running it inside QGIS,
and more than nothing: the wiring script confirms the plugin loads and every
parameter constructor is called with an argument list QGIS would accept, and
the algorithm script runs the real `processAlgorithm` bodies end to end.

```bash
STUB_QGIS_VERSION=32800 python verify/run_qgis_wiring.py    # also 33000, 33800, 34400
python verify/run_qgis_algorithms.py                        # hits the network
```

The version variable exercises both branches of `compat.py`: `QgsField` took a
`QMetaType` argument from QGIS 3.38, and `Qgis.WkbType` replaced
`QgsWkbTypes.Type` in 3.30.

`run_outputs.py` validates the layers rather than the polygon. A correct
boundary carries authority, so the values inside it have to earn the same
confidence. It checks five things that can each be answered without taking the package's word for
anything: that the raster really is masked to the divide (the polygon is
rasterised independently and the two are compared), that the area agrees with a
geodesic area computed by pyproj, that the morphometric identities hold, that
rainfall and elevation land inside figures other people have published, and how
long the whole thing takes.

`run_bad_clicks.py` covers the half of reality a gauge sample cannot: every
gauge sits on a river by construction, so no number of them tests what happens
when somebody clicks a city, a lake surface, a desert, the sea, or pastes their
coordinates the other way round. Those outlets set the distance gate on the
refinement step, which no gauge sample could have done.
