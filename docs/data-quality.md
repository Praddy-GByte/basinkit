# Data quality

`Basin.dem_suitability()` grades the elevation raster, because every terrain
product is derived from it. Every other layer used to arrive with no such
statement: a land cover map, a soil raster and a rainfall series all came back
looking equally authoritative, and nothing in the output said which of them
could carry the weight a study was about to put on it.

`Basin.data_quality()` measures each layer against something produced
independently of it, and reports what it found.

```python
import basinkit as bk

basin = bk.Basin.from_point(47.8009, 13.0447)   # Salzach at Salzburg
report = basin.data_quality()

print(report["overall"])
for layer in report["layers"]:
    print(layer["layer"], layer["grade"], layer["value"])
    print("   ", layer["statement"])
```

Every entry carries the measurement, the threshold it was judged against, and a
sentence saying what was compared with what. `overall` is the worst grade among
the layers that were graded. A layer that could not be fetched is returned as an
error rather than dropped, so the absence is visible in the output.

## What each indicator compares

| layer | measured against | what the number is |
|---|---|---|
| `elevation` | the model's own stated vertical error | the suitability grade, split by terrain class |
| `landcover` | ESA WorldCover against the ESRI annual series | share of the basin where two independent maps agree |
| `soil` | SoilGrids' own published quantiles | width of the 90% interval, in the units of the property |
| `precipitation` | CHIRPS against TerraClimate | correlation of annual totals, and the difference in means |
| `surface_water` | the JRC monthly water history | permanent against seasonal water, and what was never seen cleanly |
| `delineation` | the river network, and the blind validation | the network check, and the accuracy regime for this size |

### elevation

The suitability grade, plus the same noise-floor test computed separately for
flat, hilly and mountain ground. A basin that is part plain and part mountain is
not one number: the plain is where a 30 m model's vertical error is a large share
of the relief present, and that is exactly where a slope map stops meaning
anything. The classes are cut on local relief in a 3×3 neighbourhood, at 20 m and
100 m.

Both the relief and the noise floor are quantities per cell, so the split moves
with the resolution it was measured at — a wider cell spans more ground and
reports more relief, and a coarser slope is a gentler slope. The output reports
`class_cell_size_m` and `class_noise_floor_deg` alongside the shares, so the
numbers are read against the raster they came from. The default path measures
the split on the same cells it graded.

### landcover

ESA WorldCover and the ESRI annual series are two maps of the same year made by
two teams from different inputs. They do not share a legend, so the comparison is
reduced to the eight classes both of them define — tree, grass or shrub, crop,
built, bare, snow or ice, water, wetland — and the measurement is the share of
the compared cells where they agree. Where two mapping teams disagree, the class
under a given pixel is not settled, whatever either map says on its own. The
class they agree on least is named, restricted to classes covering at least one
per cent of the compared ground so that a rounding-error class cannot be reported
as the headline.

Agreement is graded HIGH above 0.80 and LIMITED below 0.65.

### soil

SoilGrids publishes a 5th and a 95th percentile beside every mean. The width of
that interval, in the units of the property, is the model's own statement about
how well it knows this ground — and it is wide almost everywhere.

This layer is **reported but not graded**. Nobody publishes a threshold that says
a SoilGrids interval is too wide to use, so a pass or fail here would be an
invented number printed as though it were established. The output says so in
`not_graded_because`, and gives the width so that basins, depths and properties
can be compared against each other.

### precipitation

CHIRPS and TerraClimate over the same years, as annual basin totals: their
year-to-year correlation, and the difference between their long-run means. Two
products built from different inputs bound how much of a rainfall figure is the
choice of product rather than the rainfall.

Correlation is graded HIGH above 0.90 and LIMITED below 0.75. A low correlation
is not a fault in either product — it is a statement that a single rainfall
number for this basin carries a product choice inside it.

### surface_water

How much of the basin holds water more than three months in four, how much holds
it seasonally, and the reminder that water under cloud or canopy is not in the
Landsat record, so the seasonal figure is a floor.

This layer is **reported but not graded**, for the same reason as soil: the JRC
record carries no per-pixel confidence, so there is nothing here to grade
against. The permanent-to-seasonal split is reported instead, because a basin
whose water is mostly seasonal is one where a single date would have misled.

### delineation

The boundary is not re-measured here — it comes from the backend — so this
reports the checks that do exist: the river-network consistency check, and the
accuracy regime a basin of this size falls in, from the blind validation across
2,550 gauges in 99 countries described in [Verification](verification.md).

## Every threshold is a choice

The thresholds live in `basinkit.quality.THRESHOLDS` and are printed beside every
result they judged. They are judgements about where a measurement stops being
comfortable, not measurements themselves. The numbers beside them are what was
found in the basin.

Where no defensible threshold exists, the layer is not graded. That is the whole
reason `grade` can be `None`.

## In QGIS

**Processing Toolbox → basinkit → Data quality report.** Give it a basin layer, tick the
layers to check, and it prints the graded table to the log and writes
`data_quality.csv` next to the other outputs.

## A worked example

The Salzach at Salzburg, 4,510 km2, run in full. Overall grade **LIMITED**,
which is the worst of the graded layers, and the reason is the rainfall, not the
terrain:

| layer | grade | measurement |
|---|---|---|
| elevation | HIGH | every suitability test passed, on a 52 m cell |
| landcover | MODERATE | 0.754 agreement over 1,551,618 compared cells |
| soil | *not graded* | 24% clay, 90% interval 72 points wide (293% of the mean) |
| precipitation | LIMITED | r = 0.60, CHIRPS +17% (1,679 against 1,433 mm a year) |
| surface_water | *not graded* | 0.44% permanent, 0.16% seasonal, 1984 to 2021 |
| delineation | HIGH | network check agrees; 1.7% median error at this size |

The terrain split is where the elevation grade earns its HIGH and also where it
is qualified:

| terrain | share of basin | mean slope | below the noise floor |
|---|---:|---:|---:|
| flat | 11% | 3.7 deg | 63% |
| hilly | 75% | 23.9 deg | 0.3% |
| mountain | 14% | 43.1 deg | 0% |

Read that as one sentence: on the three quarters of this basin that is hilly, a
slope map is carrying real signal; on the tenth of it that is flat valley floor,
roughly two thirds of the slopes are below the angle a 52 m Copernicus cell can
resolve, and a slope-driven result there is reading the model's vertical error.
One grade for the basin would have hidden both halves of that.

And the rainfall is the layer to be careful with. CHIRPS and TerraClimate follow
each other only loosely from year to year here (r = 0.60) and differ by 17% in
the long-run mean. Neither is wrong; the basin is small, Alpine and steep, which
is the hardest case for a gridded product. What the indicator says is that a
rainfall total quoted for this basin carries a product choice inside it, and
that choice is worth about 250 mm a year.

## The same six checks on a different basin

The Potomac at Little Falls, 30,117 km2, run the same way. The point of the
comparison is that the grades move, and they move for reasons you can name:

| layer | Salzach, 4,510 km2 | Potomac, 30,117 km2 |
|---|---|---|
| elevation | HIGH | MODERATE -- depression filling raised 6.5% of cells, the deepest by 130 m |
| landcover | MODERATE, 0.754 | MODERATE, 0.748 |
| soil | *not graded*, interval 293% of the mean | *not graded*, interval 284% of the mean |
| precipitation | LIMITED, r = 0.60, +17% | HIGH, r = 0.95, +10% |
| surface_water | *not graded*, 0.44% permanent | *not graded*, 0.17% permanent |
| delineation | HIGH, 1.7% median error at this size | HIGH, 1.3% median error at this size |

Rainfall is the layer that separates them. On the Alpine Salzach the two
products agree at r = 0.60; on the wider, flatter Potomac they agree at r = 0.95
and differ by 10% in the mean (1,100 against 998 mm a year). Same code, same
two products, and a basin where a rainfall figure is much less of a product
choice.

The terrain split moves too, and in the other direction. Forty per cent of the
Potomac is flat ground, against 11% of the Salzach, and on that flat ground 54%
of slopes fall below the noise floor of the 109 m cell the basin was read at.
On a basin this size the elevation raster is read coarser to stay inside the
pixel budget, so the floor is lower and the cell is wider -- which is exactly
why both numbers are reported next to the shares rather than left implicit.

The two land cover figures land within half a percentage point of each other,
on two basins on different continents with little in common. Two cases are not
a pattern, and nothing here claims one -- but on both of these, the two maps
settle about three quarters of the ground and leave the rest to whichever one
you happened to download.
