# Contributing

## Adding a data source

Two rules, and they are what the package is for.

1. **Register it in `basinkit/catalog.py` first.** Resolution, coverage,
   licence, auth requirement, whether it can be redistributed and used
   commercially. That table is not documentation: the fetchers and the CLI
   read from it, so it cannot drift from reality.
2. **Set `implemented` honestly.** If there is no fetcher, the entry is
   `implemented=False` and asking for it raises `NotImplementedSource` with the
   access route. A catalogue that lists datasets it cannot deliver reads as a
   feature list, which is worse than a shorter catalogue.
3. **Anonymous or opt-in.** If a source needs an account or its licence
   restricts use, it does not go in `DEFAULT_STACK`. It gets `auth` set
   accurately and a `notes` string explaining what the user is walking into,
   and it announces itself before the first byte moves.

New adapters go in `basinkit/sources/` grouped by *access pattern* (STAC,
tiled COG, WCS, NetCDF-over-HTTP, vector download), not by dataset.

Every fetcher takes a geometry and clips to it. Bounding boxes are for finding
tiles, never for what comes back.

## Tests

```bash
pytest -m "not network"    # fast, runs everywhere
pytest -m network          # hits real endpoints
```

Prefer tests that check against an **independently known value** (the Koshi
basin's published area, its documented mean annual rainfall, the fact that
water occurrence is a percentage) over snapshots of whatever the code
currently produces. A snapshot test passes happily while the answer is wrong.

The network suite runs weekly in CI on purpose. Remote endpoints move without
warning: CDSE deprecated a STAC endpoint, LP DAAC retired its Data Pool,
sentinelsat's entire backend closed. The scheduled run is how we find out
before users do.

## Style

`ruff check basinkit tests` must be clean. Comments should explain *why* (the
non-obvious constraint, the failure mode being guarded against), not restate
what the line does.
