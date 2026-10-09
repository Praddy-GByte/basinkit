# Forcing a known channel

```python
basin = bk.Basin.from_point(lat, lon, backend="dem",
                            streams="city_drainage.gpkg")
```

In QGIS: **Delineate river basin** → *Known channels to force the flow along*.
A line drawn on the canvas is enough.

## Why it is needed

A global elevation model knows what the ground surface looks like. It does not
know what is under it. Where a stream has been culverted beneath a city there
is nothing on the surface to see, so flow routing sends the water over the
buildings and the catchment it returns is not the catchment that drains there.
No elevation-derived hydrography — HydroSHEDS, MERIT, TDX-Hydro — can resolve a
buried channel, because none of them is looking at anything but the surface.

The same happens where a road embankment dams a valley in the model, and where
a canal crosses a divide the terrain says it should not.

## What it does

Each line is walked from its lower end, and every cell on it is forced to at
least a small drop below the one before. The result is a continuous channel
with a monotonic fall, which the router has to follow.

Lowering every cell on the line by a fixed depth is the obvious approach and it
does not work. The trench keeps the terrain's own rises, so a line crossing a
divide still climbs over it, and the router treats the two halves as separate
hollows and fills them. Measured on a validated basin, a constant-depth burn
moved the area by 0.00 km² at every depth up to 150 m.

## What it does not do

**Burning does not make the channel true. It makes the model obey you.** A line
in the wrong place produces a confident wrong basin, and nothing downstream
will question it. If you are guessing where the culvert runs, the result is a
guess with a sharper edge.

The provenance records that the path was forced, how deep, and over how many
cells, so a basin that was told where to go can be told apart from one that was
found:

```python
basin.provenance["conditioning"]
# {"burned": True, "method": "carved to a monotonic descent",
#  "burn_depth_m": 20.0, "carved_cells": 13713, "n_lines": 64, ...}
```

## Measured behaviour

Cowpasture River near Clifton Forge, Virginia (USGS 02016000, published
drainage area 1,194.0 km²):

| | Area | Change |
|---|---|---|
| No conditioning | 1,194.81 km² | — |
| The 64 mapped channels carved in | 1,194.99 km² | +0.18 km² |
| One line carved across the divide | 1,903.26 km² | +708 km² |

Telling the model what it already knows changes almost nothing. Telling it
something it cannot see changes everything. Both are the intended behaviour.
