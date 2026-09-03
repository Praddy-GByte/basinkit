# Related work

Name the neighbours yourself. A reviewer who finds them before you do will
read the omission as either ignorance or concealment, and both are worse than
whatever the comparison costs.

Four packages sit close enough to matter. None of them does what basinkit does,
but each one does part of it, and two of them do that part better.

## The claim, stated so it can be tested

> No existing open-source software package provides, through a single
> installable API and without requiring any account, login or credential for
> any of its default sources, the complete chain from an arbitrary global
> outlet coordinate → a delineated upstream basin polygon → multiple Earth
> observation datasets returned as **polygon-masked gridded arrays**.

Every clause in that sentence is load-bearing, and each one excludes a real
tool. Drop any of them and the claim is false.

| clause | what it excludes |
|---|---|
| *software package* | mghydro Global Watersheds: global, account-free, multi-dataset, but a web app |
| *any global outlet coordinate* | watershed-workflow, HyRiver, StreamStats, Model My Watershed, all US-only |
| *no account for any default source* | rabpro (Earth Engine + MERIT-Hydro logins), Caravan (Earth Engine), eodag (per-provider credentials) |
| *polygon-masked gridded arrays* | delineator (geometry only), mghydro and rabpro (zonal statistics), hydromt (extent-based clipping) |

## The four to cite

### hydromt: the closest, and the real threat

[Deltares/hydromt](https://github.com/Deltares/hydromt). Concede all of this:
`get_basin_geometry` takes a point and returns the upstream basin, with
sub-basin and inter-basin modes. It ships a global MERIT Hydro basin index. It
auto-downloads to `~/.hydromt_data/` with no account. Its catalog entries carry
`source_license`, `source_url` and `paper_doi`.

Where it stops: **the account-free catalog is a sample.** `artifact_data` covers
the Piave basin in northern Italy and is what you get when no catalog is
supplied. The catalog with global coverage is `deltares_data`, and the
documentation states it is *"only accessible when connected to the Deltares
network."* Everyone outside Deltares assembles and hosts their own, which is
exactly the work basinkit removes.

Two smaller differences: `get_rasterdataset` clips by extent with a buffer, not
by polygon mask; and hydromt is a model-building toolchain whose purpose is
producing wflow and SFINCS inputs, not a library for getting a basin's data.

hydromt has moved on since this page was first written: at 1.4.1 it ships more
predefined catalogs than `artifact_data` and `deltares_data` -- `aws_data`,
`gcs_cmip6_data` and `earthdatahub_data`. Those widen the climate and cloud-
hosted coverage rather than replacing the internal global catalog, and Earth
Data Hub is credentialed, so the account-free gap still stands. It is the
neighbour to keep re-checking, because it is the one that could close it.

### rabpro: same scope, two accounts

[VeinsOfTheEarth/rabpro](https://github.com/VeinsOfTheEarth/rabpro), JOSS 2022.
Global, and it does mask to the basin. But its docs require a Google Earth
Engine account and a MERIT-Hydro username and password, it asks you to upload
your basin to Earth Engine as an asset, and it returns zonal statistics rather
than the data. (Checked again in August 2026: rabpro is on PyPI at 0.2.2. An
earlier draft of this page said it had been pulled, which is no longer true.)

### watershed-workflow: the same pipeline, one continent

[environmental-modeling-workflows/watershed-workflow](https://github.com/environmental-modeling-workflows/watershed-workflow).
Delineation plus automatic download of DEM, hydrography, land cover and soils,
colocated on the watershed, largely without accounts. This is basinkit's
pipeline, done well, and explicitly scoped to *"the conterminous US (and most of
Alaska/Hawaii/Puerto Rico)."*

It is the strongest evidence that the design is right, and the clearest proof
that nobody had done it globally.

### Global Watersheds: the conceptual wound

[mghydro.com/watersheds](https://mghydro.com/watersheds/). Click a point
anywhere, get a basin and a report drawing on population, land cover,
WorldClim, GLEAM, GRACE, irrigation and dams. Global, account-free,
multi-dataset, no install at all.

It is not a package, and it returns summary statistics and vector geometry
rather than gridded arrays: the boundaries and rivers download as GeoPackage,
not the data. But it is the honest answer to *"why does this need to be a
library?"*, and the answer is: because a report is not an input to a model.

**Disclose the dependency.** basinkit's `api` backend calls this service. It is
never the default, it is recorded in provenance, and its MERIT-Hydro lineage
makes it non-commercial, but a reviewer will find it, so say it first.

## Also worth naming

**Caravan** (Kratzert et al., *Sci. Data* 2023; GRDC-Caravan, *ESSD* 2025) is
a dataset and its derivation code, not a tool. It requires catchment boundaries
as *input*, runs on Earth Engine, and yields basin-mean forcing for a fixed set
of gauged catchments. Caravan starts where basinkit finishes.

**delineator** and **upstream-delineator** (Heberger): global, MERIT-Hydro
based, accurate, account-free, and delineation only. No EO data at all.

**HyRiver**: the model for how this should feel as an API, and US-only.

**pysheds**, **pyflwdir**, **WhiteboxTools**: routing algorithms. You supply
the DEM.

**AquaFetch** (JOSS 2025) and **HARBOR** (Copernicus preprint, 2026): the
same *idea*, unified retrieval of basin data, published under other names.
AquaFetch harmonises around seventy datasets but for pre-defined gauged
catchments, not an arbitrary coordinate; HARBOR collates river-basin
attributes into one repository with a toolkit. Neither returns polygon-masked
rasters for a point you choose. They are the closest published statements of
the concept and belong in any introduction that claims it is unaddressed.

**Sen Hydro - Watershed Delineation** (QGIS plugin 5713): the neighbour of
basinkit's *plugin*, not of the library. It delineates from a clicked point
using the same mghydro Global Watersheds API that backs basinkit's `api`
backend, and adds river styling and a Senegal boundary layer. Anyone comparing
the two QGIS plugins will see the delineation overlap immediately, so the
plugin description has to lead with what Sen Hydro does not do: no EO layers,
no morphometry, no offline backend.

## Morphometry has its own neighbourhood, and it is older

The claim above is about the data chain. `morphometry()` is a separate feature
and it has separate incumbents, older and better established than the ones
listed so far. Saying morphometry is unpackaged would be false.

**GRASS GIS `r.stream.stats`** (Jasiewicz & Metz, *Computers & Geosciences*
2011) is the real incumbent. It has computed the Horton set (stream counts
and lengths by order, bifurcation and length ratios, drainage density) since
2011, and it counts Strahler streams rather than dataset reaches, which is the
part most re-implementations get wrong. It is a raster tool: you give it a
flow-direction raster and a stream network, not a coordinate.

**QGIS** ships two in its official repository. **ArcGeek Calculator** includes
watershed morphometric analysis with Strahler ordering. **Drainage Basin
Geomorphology** (plugin 4004, at 2.1.0 in August 2026) covers forty-odd
parameters. A separate **Hypsometric Curve** plugin (3659) computes the curve
and the integral from a DEM and a basin polygon.

**ArcGIS** has RivEX, and several published toolboxes besides.

So the honest statement is narrower than "nobody does this":

> Morphometry is well served in the desktop-GIS and raster-tool world and has
> been for over a decade. What has no implementation is a **Python library**
> that returns the parameters from a coordinate, with the network and the
> basin fetched for you.

That is worth having, and it is not a scientific contribution; it is a
packaging one. Claim it as such.

### The one part that is not packaging

Strahler ordering constrains the counts it produces, and the constraints are
checkable. An order-*u+1* stream exists only where two order-*u* streams meet,
so N(u) ≥ 2·N(u+1), and therefore Rb ≥ 2: always, for every basin, with no
exceptions and no tuning. A single-outlet basin has exactly one stream of its
highest order for the same reason.

Neither GRASS, nor the QGIS plugins, nor any Python code found so far reports
these as checks. They compute Rb and hand it over. basinkit computes Rb and
then tells you when the number it just produced cannot be true.

This matters because the error is in print. A PLOS One paper from September
2025 reports a mean bifurcation ratio of 1.85, individual sub-watershed values
of 1.0 and 1.5, and five third-order streams in a third-order basin. All of
those are impossible, all of them are consistent with counting reaches, and
all of them would have been caught by a two-line check.

One caution to state before anyone else does. Kirchner (1993, *Geology*)
showed that Horton's laws hold for essentially any branching network, random
ones included, so bifurcation ratios carry far less geomorphic information
than the literature built on them assumes. That weakens the case for
*interpreting* Rb. It strengthens the case for *screening* it: if the ratio is
near-inevitable, a value below the floor is not an unusual basin, it is a
broken calculation.

## The attack, and the honest answer

> *"This is glue. Delineation from a point is solved. Masking is one call to
> `rioxarray.clip`. Fetching is HTTP. watershed-workflow already ships this for
> the US and hydromt already ships delineate-from-point with a licence-annotated
> catalog. You combined five existing pieces and called it novel."*

The attack is right about the components and wrong about the claim. **No
component here is new and none is claimed to be.** What is new is that the
combination has never been shipped under the account-free constraint at global
scope, and that constraint is not cosmetic. It is what rules out Earth Engine,
Earthdata Login and the Climate Data Store, and therefore forces a different
dataset selection and a different fetcher design than every prior tool. The
nineteen sources basinkit can reach are nineteen because of it.

Claim integration and the removal of access barriers. Do not claim an
algorithm.

## One claim to narrow, not drop

Machine-readable licence metadata is **prior art**: hydromt's catalog carries
`source_license`, and STAC mandates a `license` field on every collection.
"basinkit tracks licences" is not defensible.

What is defensible is that the metadata *gates behaviour* rather than
documenting it:

```python
>>> bk.Basin.check_license("merit_hydro", commercial=True)
LicenseError: MERIT Hydro v1.0.1 is licensed CC BY-NC 4.0 or ODbL 1.0,
which forbids commercial use.

>>> basinkit.catalog.require("glofas")
NotImplementedSource: GloFAS v4 (CEMS-Floods) is catalogued but basinkit
cannot fetch it yet.
    Access : CEMS Early Warning Data Store (ewds.climate.copernicus.eu/api)
    Licence: CEMS-Floods licence
```

A test asserts that every layer in the default stack is anonymous,
commercially usable, redistributable **and** implemented. That is the
defensible sentence: the licence table is executable, and it fails the build
rather than the user.
