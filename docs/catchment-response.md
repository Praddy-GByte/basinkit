# Catchment response

Two numbers every small-catchment design runs through, from inputs this
package already has: how long the basin takes to respond to rain, and how much
of that rain runs off. Nothing new is downloaded for either.

## Time of concentration

```python
import basinkit as bk

basin = bk.Basin.from_point(37.79180, -79.75949)   # Cowpasture River, Virginia
t = basin.concentration_time()

t["estimates"]["kirpich_min"]
t["median_min"]
t["lag_time_min"]
t["spread_factor"]
```

Time of concentration is not a measured quantity. Every value is an empirical
formula fitted to a particular set of catchments in a particular landscape,
and on one basin they disagree routinely by a factor of two or three. A tool
that returns one of them as the answer has made a choice on your behalf and
hidden it.

So all six are returned, with the catchments each was fitted to and the
caution that goes with it:

| Method | Fitted to |
|---|---|
| Kirpich (1940) | seven agricultural catchments in Tennessee, 0.4–45 ha |
| California Culvert Practice (1942) | mountain catchments in California |
| Giandotti (1934) | Italian catchments, roughly 170–70,000 km² |
| Ventura | Italian catchments of moderate size |
| Témez (1978) | Spanish catchments, 1–3,000 km²; widely used across Latin America |
| Bransby Williams (1922) | catchments in India; used in Australian practice |

`spread_factor` is the longest estimate over the shortest. A design that is
not robust across that spread is not robust, and that is better known before
the concrete is poured.

**Kirpich and California Culvert Practice are the same equation.** California
uses the relief of the longest watercourse where Kirpich uses its slope, and
`morphometry()` computes that slope as relief over length. They therefore
agree by construction rather than by corroboration, and `n_distinct_values`
counts them once.

`lag_time_min` is Mockus's relation, 0.6 × the median, as used throughout
SCS/NRCS practice.

## Curve number

```python
cn = basin.curve_number()

cn["composite_cn"]          # antecedent moisture II, the average condition
cn["cn_amc_iii_wet"]        # the one a design storm runs
cn["potential_retention_mm"]
cn["by_cover"]
cn["hydrologic_soil_group_pct"]
```

The curve number is composed cell by cell from the land cover and the soil,
area-weighted over every cell that has both. Two judgements go into it, and
both are returned in `assumptions` rather than buried:

**The hydrologic soil group comes from texture, not from a soil survey.**
Where a national survey exists it assigns A to D directly and should be
preferred. Without one, the standard fallback is the USDA texture class from
the sand and clay fractions, which SoilGrids provides globally. It is a weaker
instrument: texture cannot see depth to a restrictive layer or to the water
table, and either can move a soil two groups. Tropical Oxisols are the case
worth knowing — clay-rich by texture, freely drained in the field — and a
texture-only rule will put them in group D.

**The cover types are matched from ESA WorldCover, which was not written for
TR-55.** Eleven classes are mapped to the nearest tabulated cover type, and
the mapping used is returned in `cover_mapping`. Pass `cn_table=` to replace
it with the condition you actually have.

Initial abstraction is `Ia = 0.2S`, the TR-55 default. Published work since has
argued for `0.05S`, which raises computed runoff.
