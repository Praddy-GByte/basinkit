# Why basinkit exists

## The gap

If your river is in the United States, this problem is solved.
[HyRiver](https://docs.hyriver.io) will delineate a basin from a coordinate and
pull elevation, land cover, soil and climate for it. So will
[watershed-workflow](https://github.com/environmental-modeling-workflows/watershed-workflow).
Both are excellent. Both stop at the border, because both are built on
NHDPlus and the USGS NLDI service.

Outside the US, the pieces exist but nothing joins them:

| you have | you want | what's missing |
|---|---|---|
| a coordinate | a basin polygon | global delineation that is pip-installable |
| a basin polygon | clipped data | a downloader that takes polygons, not boxes |
| both | reproducibility | provenance and licence tracking |

The delineation half exists as **scripts**:
[`mheberger/delineator`](https://github.com/mheberger/delineator) works globally
and well, but it is a clone-and-configure repository that wants tens of
gigabytes of MERIT tiles downloaded by hand first.

The data half exists as **bbox downloaders**: `eodag`, `earthaccess`,
`pystac-client`, `dem-stitcher`. Every one of them is good at what it does and
none of them has any concept of a basin.

The one prior attempt to join them,
[rabpro](https://github.com/VeinsOfTheEarth/rabpro), was yanked from PyPI in
2022, requires an Earth Engine account, and returns zonal statistics rather
than the data itself.

## The three design decisions

### Polygon, not bounding box

A river basin is a bad fit for a rectangle. Every `Basin` reports this directly:

```python
basin.bbox_efficiency
# 0.546   -> the basin occupies 55% of its own bounding box
```

For the Koshi that means a bbox download transfers nearly twice what it needs.
Worse than the waste is the contamination: a "basin mean" computed over a
bounding box averages in a neighbouring catchment's pixels. basinkit masks to
the polygon everywhere, including in the zonal statistics.

### No account, by construction

Twenty of the twenty-six catalogued datasets are reachable with no credentials
at all, and those twenty are the default stack. That is not a coincidence; it
is the selection criterion. Where a well-known route requires an account,
basinkit finds the anonymous mirror of the same data:

| the obvious route | its cost | what basinkit uses |
|---|---|---|
| OpenTopography API | 50 calls/day on a non-academic key | the same data on OpenTopography's anonymous S3 mirror |
| MERIT Hydro | Google Form, emailed Dropbox password | HydroBASINS (CC BY 4.0, direct HTTP) |
| Earth Engine | Google Cloud project; no commercial use on the free tier | STAC over Planetary Computer and Earth Search |
| Landsat via Earth Search | requester-pays bucket: 403, or a bill | Landsat via Planetary Computer |

### Licences are code, not documentation

`basinkit/catalog.py` is a machine-readable table that the fetchers, the CLI and
`Basin.license_report()` all read from. The licence you are shown is the licence
that applied, and it cannot drift from the implementation.

```python
bk.Basin.check_license("merit_hydro", commercial=True)
# LicenseError: MERIT Hydro v1.0.1 is licensed CC BY-NC 4.0 or ODbL 1.0,
# which forbids commercial use.
```

## What it does not do

It does not run a hydrological model. If you want a calibrated rainfall-runoff
or hydrodynamic model, [HydroMT](https://github.com/Deltares/hydromt) and its
plugins build those, and basinkit's outputs feed them.

It does not host data. Everything comes from the original provider on every
run, cached locally. There is no basinkit server to go down or go stale.
