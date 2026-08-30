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
| *software package* | mghydro Global Watersheds — global, account-free, multi-dataset, but a web app |
| *any global outlet coordinate* | watershed-workflow, HyRiver, StreamStats, Model My Watershed — all US-only |
| *no account for any default source* | rabpro (Earth Engine + MERIT-Hydro logins), Caravan (Earth Engine), eodag (per-provider credentials) |
| *polygon-masked gridded arrays* | delineator (geometry only), mghydro and rabpro (zonal statistics), hydromt (extent-based clipping) |

## The four to cite

### hydromt — the closest, and the real threat

[Deltares/hydromt](https://github.com/Deltares/hydromt). Concede all of this:
`get_basin_geometry` takes a point and returns the upstream basin, with
sub-basin and inter-basin modes. It ships a global MERIT Hydro basin index. It
auto-downloads to `~/.hydromt_data/` with no account. Its catalog entries carry
`source_license`, `source_url` and `paper_doi`.

Where it stops: **the account-free catalog is a sample.** `artifact_data` covers
the Piave basin in northern Italy and is what you get when no catalog is
supplied. The catalog with global coverage is `deltares_data`, and the
documentation states it is *"only accessible when connected to the Deltares
network."* Everyone outside Deltares assembles and hosts their own — which is
exactly the work basinkit removes.

Two smaller differences: `get_rasterdataset` clips by extent with a buffer, not
by polygon mask; and hydromt is a model-building toolchain whose purpose is
producing wflow and SFINCS inputs, not a library for getting a basin's data.

Deltares have said they intend to publish open global catalogs. That is the
thing to ship before they do.

### rabpro — same scope, two accounts

[VeinsOfTheEarth/rabpro](https://github.com/VeinsOfTheEarth/rabpro), JOSS 2022.
Global, and it does mask to the basin. But its docs require a Google Earth
Engine account and a MERIT-Hydro username and password, it asks you to upload
your basin to Earth Engine as an asset, and it returns zonal statistics rather
than the data. It was also pulled from PyPI in 2022.

### watershed-workflow — the same pipeline, one continent

[environmental-modeling-workflows/watershed-workflow](https://github.com/environmental-modeling-workflows/watershed-workflow).
Delineation plus automatic download of DEM, hydrography, land cover and soils,
colocated on the watershed, largely without accounts. This is basinkit's
pipeline, done well, and explicitly scoped to *"the conterminous US (and most of
Alaska/Hawaii/Puerto Rico)."*

It is the strongest evidence that the design is right, and the clearest proof
that nobody had done it globally.

### Global Watersheds — the conceptual wound

[mghydro.com/watersheds](https://mghydro.com/watersheds/). Click a point
anywhere, get a basin and a report drawing on population, land cover,
WorldClim, GLEAM, GRACE, irrigation and dams. Global, account-free,
multi-dataset, no install at all.

It is not a package, and it returns summary statistics and vector geometry
rather than gridded arrays — the boundaries and rivers download as GeoPackage,
not the data. But it is the honest answer to *"why does this need to be a
library?"*, and the answer is: because a report is not an input to a model.

**Disclose the dependency.** basinkit's `api` backend calls this service. It is
never the default, it is recorded in provenance, and its MERIT-Hydro lineage
makes it non-commercial — but a reviewer will find it, so say it first.

## Also worth naming

**Caravan** (Kratzert et al., *Sci. Data* 2023; GRDC-Caravan, *ESSD* 2025) —
a dataset and its derivation code, not a tool. It requires catchment boundaries
as *input*, runs on Earth Engine, and yields basin-mean forcing for a fixed set
of gauged catchments. Caravan starts where basinkit finishes.

**delineator** and **upstream-delineator** (Heberger) — global, MERIT-Hydro
based, accurate, account-free, and delineation only. No EO data at all.

**HyRiver** — the model for how this should feel as an API, and US-only.

**pysheds**, **pyflwdir**, **WhiteboxTools** — routing algorithms. You supply
the DEM.

## The attack, and the honest answer

> *"This is glue. Delineation from a point is solved. Masking is one call to
> `rioxarray.clip`. Fetching is HTTP. watershed-workflow already ships this for
> the US and hydromt already ships delineate-from-point with a licence-annotated
> catalog. You combined five existing pieces and called it novel."*

The attack is right about the components and wrong about the claim. **No
component here is new and none is claimed to be.** What is new is that the
combination has never been shipped under the account-free constraint at global
scope — and that constraint is not cosmetic. It is what rules out Earth Engine,
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
