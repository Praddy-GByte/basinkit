# Handing the basin to a model

A distributed hydrological model does not want a polygon. It wants
sub-catchments and the links between them. basinkit already holds that graph, so
this is a renaming rather than a computation — **every value written out is one
basinkit already has**, and nothing is inferred from geometry.

```bash
basinkit archydro --lat 45.11188 --lon -110.79438 --out yellowstone
```

In ArcGIS Pro: **BasinKit → 8 Model Coupling → Export for Arc Hydro**.

## What you get

`archydro.gpkg` with two layers named as Arc Hydro names them, plus the same two
tables as CSV:

| layer | one row per | fields added |
|---|---|---|
| `Catchment` | sub-catchment | `HydroID`, `HydroCode`, `NextDownID`, `AreaSqKm` |
| `DrainageLine` | river reach | `HydroID`, `HydroCode`, `NextDownID`, `LengthKm` |

Every original HydroBASINS and HydroRIVERS column is kept alongside, so nothing
is lost in translation. `archydro_routing.png` draws the table: each catchment
filled, a line from each centroid to the centroid of the catchment its
`NextDownID` names, and the terminal unit marked. A table that is a single tree
draining to one outlet looks like one, and a table with two outlets, a cycle or
a pointer into nothing does not.

## What the fields mean, and why they hold what they hold

| field | Arc Hydro's definition | what basinkit puts there |
|---|---|---|
| `HydroID` | "an internal Arc Hydro identifier that is assigned by the Arc Hydro tools and is used for relating Arc Hydro features to one another" | 1…N, in ascending order of the source identifier |
| `HydroCode` | "the permanent public identifier of the feature that was assigned by the agency that created it" | the HydroBASINS `HYBAS_ID` or HydroRIVERS `HYRIV_ID`, unchanged |
| `NextDownID` | "the HydroID of the downstream feature" | exactly that, and **−1** where there is none |
| `AreaSqKm` | the feature's area | HydroBASINS' own `SUB_AREA`, not recomputed |

`HydroID` is assigned rather than reused because a ten-digit `HYBAS_ID` does not
fit the Arc Hydro long-integer field, and because `HydroID` is *defined* as the
tools' own identifier. The original is never lost — it goes to `HydroCode`, which
is the field Arc Hydro reserves for it.

**`DrainID` is deliberately not written.** In the Arc Hydro model it points a
drainage line at the catchment containing it. basinkit does not hold that link,
and deriving it here would mean a spatial join — a guess about which catchment a
reach belongs to. The field is left for Arc Hydro's own tools to populate.

## The routing table is checked, not assumed

Every export reports whether the graph is a single tree draining to one outlet:
how many terminal units it has, how many `NextDownID` values point at units that
are not in the table, and how many units sit in a cycle. A table that fails the
check is still written, with the failure reported. It belongs to the source data,
and repairing it silently would be worse than naming it.

On the Yellowstone above Corwin Springs: 54 catchments, one terminal unit, no
dangling pointers, no cycles.

## Areas: a pass-through, and what that costs

The 54 sub-catchment areas sum to **6,771.10 km²**, against basinkit's own
geodesic polygon area of **6,785.76 km²** — a difference of 0.216%. That gap is
not an error to fix. `AreaSqKm` is HydroBASINS' published `SUB_AREA`, computed by
HydroBASINS at its own resolution; basinkit's basin area is measured on the
dissolved polygon. Recomputing the sub-catchment areas would make the two agree
and would also mean writing a number the source did not publish. The pass-through
is the honest choice, and the 0.2% is the price of it.

## Arc Hydro users

If you already work in Arc Hydro, nothing about your workflow changes. Import the
GeoPackage into your geodatabase as `Catchment` and `DrainageLine` and Arc Hydro's
tools read them, because the field names are the ones they look for. What basinkit
adds is where the data came from: one coordinate instead of a DEM you had to
source, clip and mosaic yourself, with the licence and version of every input
recorded per run.
