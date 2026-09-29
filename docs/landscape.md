# Landscape form: chi, channel steepness and knickpoints

Shape indices say what a basin looks like. They do not say whether it is still
changing. This does.

```bash
basinkit landscape --lat 45.11188 --lon -110.79438 --out yellowstone
```

In ArcGIS Pro: **BasinKit -> 5 Morphometry and Drainage Network -> Landscape
Form (Chi and Channel Steepness)**. In Python:

```python
import basinkit as bk
from basinkit import landscape

basin = bk.Basin.from_point(45.11188, -110.79438)
result = landscape.analyse(basin.dem())
print(result["summary"]["ksn_median"])
```

Outputs are `chi.tif`, `ksn.tif`, `trunk_profile.csv`, a knickpoint table with
each step's height, and `landscape_form.png` — the trunk in χ–elevation space with
every knickpoint marked, the long profile, and the slope–area relation with the
fitted concavity drawn on it so the fit can be judged by eye.

### Every number arrives with what it is worth

The result carries a `confidence` block: one sentence per quantity, attached to
that quantity, stating what that value is worth — the same role a stated tolerance
plays beside an instrument reading.

```
"ksn":  "Measured on the 67% of channel cells that have a downstream gradient.
         Cross-checked cell by cell against TopoToolbox: within 6% at every
         quantile, and its median moves under 2% across a fourfold change in
         cell size. Quotable as it stands."

"fitted_concavity":
        "Fitted with R2 = 0.68, which is weak. ... theta = 0.462 is a
         measurement rather than a result; quote it with its R2 or not at all.
         k_sn is unaffected — it does not use the fitted theta."
```

So a weak θ does not contaminate k_sn, and the output says which is which
rather than leaving the reader to guess.

Separately, a run may print a **limit**: the short list of conditions under which
a value should not be used at all — a concavity fit below R² 0.5, a network more
than half flat, or fewer than 500 channel cells. **An ordinary run prints none**,
and a test enforces that. A caution raised on every run carries no information.

## Method

| quantity | definition | reference |
|---|---|---|
| χ | ∫ from the outlet to x of (A₀/A)^θ dx | Perron & Royden 2013 |
| k_sn | S · A^θref | Wobus et al. 2006 |
| θ | fitted from S = k_s A^−θ on log-area bins | Flint 1974 |

θref is fixed at 0.45 and A₀ at 1 km², so k_sn is comparable between basins and
χ carries units of length. Both are recorded with every result, because changing
either changes every number.

Two channel slopes are computed, because they answer different questions:

- **k_sn uses the raw cell-to-cell drop** along the flow path, negatives clamped
  at zero. This is the estimate that matches the reference implementation and
  published values.
- **the concavity fit uses elevation averaged over ~500 m** along the flow
  network. Cell-to-cell noise biases a fitted θ low; smoothing fixes that.

Smoothing the elevation before computing k_sn would be wrong, and the
cross-check below is what showed it: it damps genuine steep reaches and
understates the k_sn 99th percentile by about a third.

Flow routing is pyflwdir on the Copernicus DEM that basinkit already fetches.
The channel network is every cell draining more than 1 km².

## Run

| | Yellowstone above Corwin Springs | Alaknanda at Devprayag |
|---|---|---|
| setting | Rocky Mountains, long stable | Himalaya, actively uplifting |
| cell size | 113.7 m | 122.0 m |
| channel cells | 51,958 | 47,671 |
| relief | 2,138 m | 6,585 m |
| trunk length | 217.7 km | 250.9 km |
| fitted θ (smoothed, R²) | 0.431 (0.82) | 0.377 (0.92) |
| fitted θ (raw cells) | 0.264 | 0.230 |
| **k_sn median** | **59.8** | **167.2** |
| k_sn 90th percentile | 174.7 | 446.8 |
| k_sn 99th percentile | 665.6 | 1412.7 |
| **knickpoints on the trunk** | **2** | **10** |
| zero-gradient channel cells | 21.6% | 7.0% |

k_sn counts only cells with a positive channel gradient.

## Cross-check against TopoToolbox

The check that settles whether the implementation is right. TopoToolbox 0.0.12
(the Python port) and basinkit were run on the **same** DEM, reprojected to
EPSG:32612 at 80 m, with the same 1 km² channel threshold and the same
θref = 0.45. Comparison is made **cell by cell on the cells both networks
contain**, not on two separate distributions, so a difference cannot be hidden
behind a different network.

### One thing has to be settled first: what the two do with a bad cell

TopoToolbox's channel gradient is **not clamped**. Where a DEM rises downstream —
a routing artifact, not a channel — it returns a negative gradient, and therefore
a negative k_sn. basinkit clamps those to zero and reports the fraction instead.
Neither choice is wrong, but they are different, so a median taken over *all*
channel cells is comparing a distribution containing negatives against one
containing zeros. On these two basins:

| | Yellowstone | Fall Creek |
|---|---|---|
| TopoToolbox cells with a negative gradient | 9.4% | 21.7% |
| basinkit cells clamped to zero | 13.0% | 25.3% |

**Every k_sn comparison on this page is therefore made over the cells where both
implementations return a positive value.** That is the only population on which
the two are measuring the same thing. The counts are given so the choice is
visible.

### k_sn — agrees

Yellowstone above Corwin Springs, 27,418 cells positive in both:

| statistic | TopoToolbox | basinkit | apart |
|---|---|---|---|
| median | 59.2 | 57.0 | **3.7%** |
| 75th percentile | 101.1 | 98.1 | 3.0% |
| 90th percentile | 165.5 | 162.0 | 2.1% |
| 99th percentile | 611.6 | 611.6 | **0.0%** |
| correlation, cell by cell | | | **r = 0.973** |

TopoToolbox's `StreamObject.ksn` was called with `impose=False`, which differences
raw cells as basinkit does. Against `impose=True` — TopoToolbox's own
minima-imposed setting, which is the closer analogue of clamping — the medians are
59.4 and 58.6, **1.3% apart**.

**This comparison is what corrected the k_sn method.** A first attempt ran
basinkit with 500 m smoothing still applied and its 99th percentile came out 41%
below TopoToolbox's. That was not a TopoToolbox difference — it was the smoothing,
and smoothing was removed from k_sn because of it.

### χ — agrees in the bulk, diverges on a few percent of cells

χ is a path integral from the outlet, so any difference in flow routing
propagates along the whole branch above it. That is what the comparison shows.

| | |
|---|---|
| median ratio basinkit / TopoToolbox | 1.0125 |
| regression slope against TopoToolbox | 0.986 |
| agreement in every decile of χ, including the top 1% | within 0.7–1.9% |
| shared cells within 5% | 82.7% |
| shared cells within 10% | 89.4% |
| shared cells more than 20% apart | 4.7% |

The single largest χ value differs by 19%, and that number is misleading on its
own: the cell where basinkit's χ is highest carries a TopoToolbox χ of 6,169 m
against basinkit's 17,578 m, and the cell where TopoToolbox's is highest runs
the other way. Those are cells the two routings send down different paths, not a
disagreement about the integral. Changing the quadrature rule from a rectangle
to TopoToolbox's trapezoid moved the median ratio from 1.0125 to 1.0082 — the
rule is not the cause, so it was left alone.

### Networks are not identical, and that is expected

TopoToolbox found 51,224 channel cells, basinkit 47,304, with 31,524 in common
(61.5% and 66.6%). Two independent D8 implementations with different depression
handling place channels one or two cells apart across flats, which collapses an
index-matched overlap even where the network is geometrically the same. The
quantiles above are computed on the shared cells for exactly this reason.

## Checked against published ranges

Normalised channel steepness is usually reported near 20–100 for stable ground
and 100–400 for the Himalaya. Yellowstone returns a median of 59.8 and Alaknanda
167.2. Both land inside the range published for their setting, and the uplifting
basin is 2.8 times steeper.

Fitted concavity comes out at 0.43 and 0.38, both inside the 0.3–0.6 normally
reported for bedrock rivers.

This is the discrimination the classical stage indices failed to make. The
hypsometric integral put both basins in the same band.

## Knickpoints

2 on 218 km of stable trunk; 10 on 251 km of uplifting trunk. A graded profile
against a transient one. Each is reported with its height and how far its local
gradient stands above the profile's own median, so small steps can be dismissed.

## What is reported alongside, and why

**Zero-gradient channel cells: 21.6% in Yellowstone, 7.0% in Alaknanda.** These
are the lake and the flats. They are excluded from k_sn, because a flat return is
not a bedrock channel — but the fraction is reported, because a basin where a
fifth of the channel network is flat is one where k_sn describes less of the
landscape than the number suggests. basinkit's own elevation grading already
flags the same surface: "a level surface of 334 km² at 2357 m covers 4.95% of
the basin".

## A small basin where everything is already published

The Yellowstone is 6,786 km². A reviewer is entitled to ask whether the same
thing works on a small catchment, and whether it can be checked against
something published rather than against itself.

**Fall Creek near Ithaca, New York.** 326 km². USGS gauge 04234000 at
42.4533333, −76.47277778. It was chosen because three independent things about it
are already on the record: its drainage area is published by the USGS, its lower
gorge is a textbook hanging valley, and the waterfall at the end of that gorge has
a published height.

### 1. The basin area, against the USGS

USGS NWIS publishes the drainage area at this gauge as **126 square miles =
326.34 km²**. Three of basinkit's delineation backends were run on the gauge
coordinate:

| backend | source | area | against USGS |
|---|---|---|---|
| `api` | MERIT-Hydro (~90 m) | 324.56 km² | **−0.54%** |
| `hydrobasins` (default) | HydroBASINS v1c level 12 | 343.94 km² | +5.39% |
| `dem` | Copernicus 30 m, D8 routing | 352.08 km² | +7.89% |

**The +5.39% is not an error, and this is worth being precise about.** The
HydroBASINS unit's outlet is not the gauge: the lowest cell of that basin sits at
**120.6 m**, which is 1.95 km downstream of the gauge and 4.2 m above Cayuga
Lake's published surface elevation of 116.4 m. The gauge cell itself is at
**239.0 m**. Two different outlets measure two different basins, and the published
126 mi² is measured at the gauge. On a basin this small, level-12 units cannot be
cut at an arbitrary point, and `api` is the backend that can.

So the apples-to-apples answer is **−0.54% on a 326 km² basin**, and the lesson
for a small catchment is to choose the backend rather than take the default.

### 2. A knickpoint the tool was not told about

Ithaca Falls is **150 feet (46 m)** high, and Wikipedia describes it as "the last
of a series of waterfalls along the hanging valley formed where Fall Creek
intersects the glacial trough of Cayuga Lake". A hanging valley is exactly the
configuration that leaves a knickpoint: the trunk glacier overdeepened the Cayuga
trough, the tributary was left perched, and the gorge has been cutting back from
the lake ever since.

That gorge is **below** the gauge. So the same analysis was run twice, on two
basins that differ only in whether the gorge is inside them:

| basin | outlet | gorge included? | knickpoints found |
|---|---|---|---|
| `hydrobasins` | Cayuga Lake, 120.6 m | yes | **1** |
| `api` | the gauge, 240.2 m | no | **0** |

The one it found sits at **131.0 m elevation, 0.3 km above the outlet** — inside
the gorge — with a **65.8 m step** and a local gradient **14.7σ** above that
profile's own median. Its 65.8 m spans Ithaca Falls' 46 m plus the cascades
immediately above it, which is what a 30 m DEM differenced over a 500 m window
should return; it is not a measurement of the waterfall's height.

**The point is the pair, not either number.** The tool found the documented
feature where the documented feature is, and found nothing where there is
nothing. Neither run was tuned, and neither was told that a waterfall existed.

### 3. The channel numbers, against TopoToolbox on the identical grid

Same 30 m grid reprojected to EPSG:32618, same 1 km² threshold, same θ = 0.45,
compared cell by cell on the 2,844 cells where both return a positive value:

| | TopoToolbox | basinkit | apart |
|---|---|---|---|
| k_sn median | 21.6 | 20.3 | **6.1%** |
| k_sn 75th percentile | 42.0 | 40.6 | 3.4% |
| k_sn 90th percentile | 87.3 | 83.5 | 4.3% |
| k_sn 99th percentile | 372.3 | 365.0 | 2.0% |
| correlation, cell by cell | | | **r = 0.987** |
| χ, regression slope | | | 1.070, **r = 0.997** |
| χ cells more than 20% apart | | | **1.97%** |

Against TopoToolbox's `impose=True` setting the medians are 19.1 and 19.6 —
**2.8% apart**.

The median's 6.1% is looser than the Yellowstone's 3.7%, and it is worth saying
why rather than leaving it. **Per cell, the median disagreement is 0.35 k_sn
units.** On a basin whose median k_sn is around 21, a third of one unit is a large
percentage and a small quantity. The correlation of 0.987 — higher than the
Yellowstone's 0.973 — is the evidence that the cells themselves agree.

That is the honest shape of the result on low relief: the **absolute** agreement is
tighter than on the Yellowstone, and the **percentage** agreement is looser,
because the numbers being compared are small. A reviewer should hold percentage
claims about k_sn to the relief of the basin they were measured on.

## Something to compare your number against

k_sn is a **comparative** index. There is no published cut-off at θref = 0.45
that separates "active" from "stable" independently of lithology and rainfall, so
this page does not print one. What it can give you is five basins measured by
this exact code, with these exact settings, spanning depositional plain to active
orogen:

| basin | setting | k_sn median | k_sn p90 | knickpoints | flat channel cells |
|---|---|---|---|---|---|
| Gangetic plain near Patna | alluvial, depositional | **2.3** | 14.1 | 0 | 50.7% |
| Godavari headwaters at Nashik | Deccan plateau basalt | **11.9** | 52.7 | 0 | 36.4% |
| New River, Virginia | Appalachians, long eroded | **31.4** | 104.6 | 0 | 26.5% |
| Yellowstone above Corwin Springs | Rocky Mountains, stable | **59.8** | 174.7 | 2 | 21.6% |
| Alaknanda at Devprayag | Himalaya, actively uplifting | **167.2** | 446.8 | 10 | 7.0% |

The ordering is monotonic across all five, and it is the ordering you would
predict from the tectonics. That is the evidence that the index is measuring what
it claims to.

**Read this as a ladder, not as thresholds.** Lithology and rainfall move k_sn
independently of uplift: a resistant quartzite reach in a quiet setting can
out-steepen a shale reach in an active one. Two of these basins are small (239
and 459 km²) because the outlet snapped to a tributary, while the Yellowstone is
6,786 km². k_sn is normalised by drainage area, so size is not the confound —
rock strength and precipitation are.

## What this does not tell you

Three things are deliberately absent, and each was tested before being left out.

**A stage or an age.** The classical erosional-stage indices were run first and
cannot place a single basin: the hypsometric integral spread only 0.21–0.25
across sub-catchments of one system, and the elongation and bifurcation ratios
changed sign between settings. Nothing here prints "youthful" or "mature".

**An uplift or erosion rate.** χ, k_sn and knickpoint counts describe form and
transience. Converting them to rates needs independent calibration — cosmogenic
nuclides, dated terraces — which basinkit does not have and does not pretend to.

**A steady-state score from the χ-plot's straightness.** Perron & Royden's result
is that a river in equilibrium plots linear in χ–elevation, so the R² of a
straight-line fit looks like an obvious transience metric. It was implemented and
it failed: the stable Yellowstone returned R² = 0.77 while the uplifting
Alaknanda returned 0.94 — backwards. The Yellowstone's lake and flats create a
large concave departure, while the Alaknanda's 6,585 m of relief dominates the
variance and keeps R² high in spite of a 1,795 m departure from the line. The
metric is not shipped.

## Limits

Two basins, one cross-check implementation. k_sn is verified to within 6% at
every quantile and within 4% on the larger basin; χ is verified in the bulk but 4.7% of cells sit more than 20%
from the reference, and the cause is flow routing rather than the χ integral.

Neither number is an uplift rate. χ, k_sn and knickpoint counts describe form and
transience. Turning them into rates needs independent calibration.

## Does the answer survive a change of resolution?

The same basin, the same code, the same 1 km² threshold, at four cell sizes
(area-averaged from the native grid, so the terrain is the same terrain):

| cell size | channel cells | fitted θ | k_sn median | k_sn p90 | trunk length | knickpoints | flat channel cells |
|---|---|---|---|---|---|---|---|
| 93 m | 51,958 | 0.431 | **59.8** | 174.7 | 217.7 km | 2 | 21.6% |
| 186 m | 26,648 | 0.417 | **60.3** | 176.6 | 208.3 km | 2 | 27.2% |
| 278 m | 17,590 | 0.349 | **59.5** | 173.4 | 202.6 km | 3 | 28.6% |
| 371 m | 12,675 | 0.360 | **59.2** | 173.3 | 203.3 km | 1 | 27.6% |

**k_sn is the robust number.** Its median moves 1.9% and its 90th percentile
1.9% across a fourfold change in cell size, while the number of channel cells
falls by three quarters. A separate run at a finer pixel budget returned 61.1,
inside the same band. That is the quantity to compare between basins.

**Two numbers are not robust, and are reported as such:**

- **The knickpoint count is unstable**: 2, 2, 3, 1. It is a count of discrete
  features found by a threshold on a profile, and a coarser profile both loses
  small steps and merges neighbouring ones. The contrast between a graded and a
  transient trunk (2 against 10) survives; the absolute count should not be
  quoted without its cell size.
- **The fitted concavity degrades on a coarse grid**: 0.431 at 93 m against
  0.360 at 371 m. The concavity fit smooths elevation over 500 m, which is five
  cells at 93 m and barely one at 371 m, so the noise the smoothing exists to
  remove comes back. θ is worth quoting when the cell size is well under the
  smoothing window, and not otherwise.

Trunk length shortens by 7% as the grid coarsens, which is the usual effect of
measuring a path on a coarser grid.
