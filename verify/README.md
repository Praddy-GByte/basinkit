# Verification scripts

These produce the numbers in `docs/verification.md`. They hit real endpoints,
so they are slow and they will drift as upstream data changes — which is the
point.

```bash
python verify/run_delineation.py   # 12 gauges, six continents, vs published areas
python verify/run_sources.py       # every source adapter on one small basin
python verify/run_rest.py          # cross-checks and the full pipeline to disk
```

`basins.py` holds the reference gauges. Published areas come from operating
agencies and GRDC station records, **not** from HydroBASINS, so agreement is an
external check rather than a tautology.

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
