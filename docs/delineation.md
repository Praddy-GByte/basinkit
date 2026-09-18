# Delineation

## Four backends

```python
bk.Basin.from_point(lat, lon, backend="auto")   # default
```

| backend | mechanism | good for | floor | first-run cost |
|---|---|---|---|---|
| `hydrobasins` | walks the `NEXT_DOWN` graph over level-12 units | any size | ~130 km² | one 80 MB regional file, cached forever |
| `dem` | D8 routing with `pyflwdir` on a Copernicus DEM window | headwaters | one 30 m pixel | tiles for the window |
| `api` | Global Watersheds web service | a first look | ~90 m | nothing |
| `tdx` *(opt-in)* | walks the reach graph over TDX-Hydro unit catchments | small catchments | one reach | one regional Parquet, 37-533 MB |

## Why graph traversal is the default

HydroBASINS ships every sub-basin with a pointer to the unit it drains into.
Finding everything upstream is then a breadth-first walk over a few hundred
thousand nodes, not a fill over hundreds of millions of raster cells. The Koshi
basin (54,000 km², 423 level-12 units) delineates in about five seconds, and a
basin ten times larger takes about the same, because the cost is in the graph,
not the area.

The price is a resolution floor. A level-12 unit has a median area near 130 km²,
so a 20 km² headwater catchment cannot be resolved: you get the whole unit.
`backend="auto"` detects that case and re-runs on the DEM.

## The twelve-metre backend

`backend="tdx"` walks the same kind of graph over TDX-Hydro, which NGA derived
from TanDEM-X at 12 m and which carries one catchment polygon per stream reach
rather than one per ~130 km² unit. That is the whole of the default backend's
weakness below 500 km², so this is where it pays. On 360 gauges between 100 and
500 km², across eight GEOGLOWS regions on four continents, drawn by seed before
any result was seen:

| backend | median area error | within 20% |
|---|---:|---:|
| `hydrobasins` | 32.5% | 38% |
| `tdx` | 10.5% | 58% |

| catchment size | `hydrobasins` | `tdx` | tdx better |
|---|---:|---:|---:|
| 100-200 km² | 60.6% | 10.6% | 78% |
| 200-350 km² | 27.5% | 6.9% | 60% |
| 350-500 km² | 19.4% | 17.9% | 55% |

The gain closes as the basin grows past a level-12 unit, which is the
mechanism this backend exists for behaving exactly as claimed. Two honest
qualifications: it is better in seven of the eight regions and not in the
eighth, and while its median signed error is -1%, its lower quartile is -67%.
The default's failure is to return too much; this one's is to occasionally
snap to a tributary and return far too little. Check
`provenance["snap_km"]` when the answer looks small.

Three things to know before choosing it:

- **The licence.** TDX-Hydro is CC BY-SA 4.0. ShareAlike travels into anything
  derived from it and redistributed, and every other default in basinkit is
  CC BY 4.0 or more permissive. `auto` will never reach for this backend on
  your behalf; you have to name it.
- **The dependency.** `pip install "basinkit[tdx]"` installs the Parquet reader
  it needs. Without it, the backend raises and says so by name.
- **The coverage.** basinkit reads the GEOGLOWS v2 republication on AWS Open
  Data, because NGA's own download serves whole GeoPackages and no byte ranges.
  That republication omits twelve of NGA's sixty-two regions, Greenland and
  much of Arctic North America among them.

## Two failure modes, handled explicitly

**The outlet is not on the channel.** A coordinate read off a map, or taken from
a gauge record, is often a pixel or two from the modelled stream. Routing from a
hillslope cell returns a few hectares instead of a few hundred km², and it
returns it *silently*, which is what makes it dangerous. The DEM backend snaps
to the local maximum of upstream area, refuses to snap onto anything draining
less than `min_uparea_km2`, and reports how far it moved:

```python
basin.provenance["snap_distance_px"]           # 3
basin.provenance["flow_accum_at_outlet_km2"]   # 1752.4
```

**The basin is larger than the DEM window.** If the delineated basin touches the
window edge, part of it is off-map and the answer is wrong. The window doubles
and routing re-runs, up to `max_window_deg`, then raises rather than quietly
returning a truncated basin.

!!! note "A subtlety worth knowing"
    basinkit builds the flow network with `outlets="edge"`, not `outlets="min"`.
    With `outlets="min"`, `pyflwdir` routes the entire window toward its single
    lowest cell, which on a cropped DEM pulls the network away from the real
    channels. During development a river with 2,500 km² of upstream area came
    back with 0.2 km² of accumulation at exactly the same coordinate, purely
    because the window had been shifted. `edge` lets flow leave wherever it
    reaches the boundary, which is what a window cut out of a larger landscape
    actually does.

## Provenance

Every polygon records where it came from, and that dict is written into every
export:

```python
{'backend': 'hydrobasins',
 'source_dataset': 'HydroBASINS v1c level 12 (Central and Southeast Asia)',
 'n_units': 423,
 'outlet_hybas_id': 4120874300,
 'reported_up_area_km2': 54581.3,
 'area_km2': 54497.1,
 'license': 'CC BY 4.0'}
```

The gap between `area_km2` (computed here, by equal-area projection) and
`reported_up_area_km2` (HydroBASINS' own bookkeeping) is an **internal**
consistency check: it says the upstream traversal and the area computation
agree with the dataset about which units are in the basin. For the Koshi it is
0.15%.

**It is not an accuracy figure and must never be quoted as one.** Both numbers
come from the same polygons, so the comparison is close to circular: it can
only catch a bug in the traversal, never an error in HydroBASINS itself. The
accuracy figure is the comparison against the operating agency's published
area, which for the Koshi is 54,100 km² and 0.73%. Quoting the 0.15% instead
makes the package look roughly four times better than it is.
