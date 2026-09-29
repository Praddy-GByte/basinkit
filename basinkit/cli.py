"""Command-line interface: basin data without writing any Python."""

from __future__ import annotations

import json
import sys

import click

from . import __version__, cache, catalog


@click.group()
@click.version_option(__version__, prog_name="basinkit")
def main() -> None:
    """basinkit -- point to river basin to every open Earth observation layer.

    \b
    Quick start:
      basinkit basin --lat 26.87 --lon 87.15
      basinkit fetch --lat 26.87 --lon 87.15 --out koshi/
      basinkit catalog
    """


@main.command()
@click.option("--lat", type=float, required=True, help="Outlet latitude.")
@click.option("--lon", type=float, required=True, help="Outlet longitude.")
@click.option("--backend", default="auto",
              type=click.Choice(["auto", "hydrobasins", "dem", "api"]),
              help="Delineation backend.")
@click.option("--out", type=click.Path(), default=None, help="Write basin.geojson here.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
def basin(lat: float, lon: float, backend: str, out: str | None, as_json: bool) -> None:
    """Delineate the upstream basin of an outlet and report it."""
    from .basin import Basin

    b = Basin.from_point(lat, lon, backend=backend)
    payload = {
        "area_km2": round(b.area_km2, 2),
        "centroid_lat_lon": [round(v, 5) for v in b.centroid],
        "bounds": [round(v, 5) for v in b.bounds],
        "bbox_efficiency": round(b.bbox_efficiency, 3),
        "provenance": b.provenance,
    }
    if out:
        b.to_geojson(out)
        payload["written"] = out

    if as_json:
        click.echo(json.dumps(payload, indent=2, default=str))
        return

    click.echo(f"Basin area        {payload['area_km2']:,} km2")
    click.echo(f"Centroid          {payload['centroid_lat_lon']}")
    click.echo(f"Bounds            {payload['bounds']}")
    click.echo(
        f"Bbox efficiency   {payload['bbox_efficiency']:.0%} "
        "(share of the bounding box the basin actually occupies)"
    )
    click.echo(f"Backend           {b.provenance.get('backend')}")
    click.echo(f"Source            {b.provenance.get('source_dataset', '-')}")
    if out:
        click.echo(f"Written           {out}")


@main.command()
@click.option("--lat", type=float, required=True)
@click.option("--lon", type=float, required=True)
@click.option("--out", type=click.Path(), required=True, help="Output directory.")
@click.option("--layers", default="dem,landcover,soil,surface_water,precipitation,rivers",
              help="Comma-separated layers to fetch.")
@click.option("--backend", default="auto",
              type=click.Choice(["auto", "hydrobasins", "dem", "api"]))
@click.option("--start", type=int, default=2000, help="First year for time series.")
@click.option("--end", type=int, default=None, help="Last year for time series.")
def fetch(lat: float, lon: float, out: str, layers: str, backend: str,
          start: int, end: int | None) -> None:
    """Delineate a basin and download every requested layer, clipped to it."""
    from .basin import Basin

    b = Basin.from_point(lat, lon, backend=backend)
    click.echo(f"Basin: {b.area_km2:,.0f} km2 via {b.provenance.get('backend')}")

    requested = tuple(x.strip() for x in layers.split(",") if x.strip())
    manifest = b.download_all(out, layers=requested, start=start, end=end)

    click.echo("")
    for name, value in manifest["layers"].items():
        click.echo(f"  ok      {name:<16} {value}")
    for name, err in manifest["failed"].items():
        click.echo(f"  failed  {name:<16} {err}", err=True)
    click.echo(f"\nManifest: {out}/manifest.json")
    if manifest["failed"]:
        sys.exit(1)


@main.command(name="catalog")
@click.option("--category", default=None, help="Filter by category.")
@click.option("--anonymous", is_flag=True, help="Only datasets needing no account.")
@click.option("--json", "as_json", is_flag=True)
def catalog_cmd(category: str | None, anonymous: bool, as_json: bool) -> None:
    """List every dataset basinkit knows, with licence and auth requirements."""
    rows = list(catalog.DATASETS.values())
    if category:
        rows = [d for d in rows if d.category == category]
    if anonymous:
        rows = [d for d in rows if d.auth == "none"]

    if as_json:
        click.echo(json.dumps([d.__dict__ for d in rows], indent=2, default=str))
        return

    click.echo(catalog.table(rows))
    click.echo(
        f"\n{sum(d.auth == 'none' for d in rows)} of {len(rows)} need no account. "
        "'comm=NO' means the licence forbids commercial use."
    )


@main.command()
@click.option("--clear", is_flag=True, help="Delete everything in the cache.")
@click.option("--namespace", default=None, help="Clear only this sub-directory.")
def cache_cmd(clear: bool, namespace: str | None) -> None:
    """Inspect or clear the download cache."""
    if clear:
        freed = cache.clear(namespace)
        click.echo(f"Freed {freed / 1e6:.1f} MB from {namespace or 'the whole cache'}.")
        return
    info = cache.info()
    click.echo(f"Cache: {info['path']}")
    click.echo(f"Total: {info['total_mb']} MB")
    for ns, stats in info["namespaces"].items():
        click.echo(f"  {ns:<20} {stats['files']:>5} files  {stats['mb']:>9} MB")


main.add_command(cache_cmd, name="cache")


@main.command()
@click.option("--lat", type=float, required=True)
@click.option("--lon", type=float, required=True)
@click.option("--backend", default="auto")
def summary(lat: float, lon: float, backend: str) -> None:
    """Characterise a basin: area, terrain, land cover fractions."""
    from .basin import Basin

    b = Basin.from_point(lat, lon, backend=backend)
    click.echo(json.dumps(b.summary(), indent=2, default=str))


@main.command()
@click.option("--lat", type=float, required=True, help="Outlet latitude.")
@click.option("--lon", type=float, required=True, help="Outlet longitude.")
@click.option("--backend", default="auto")
@click.option("--min-area-km2", type=float, default=1.0,
              help="Channel-initiation drainage area.")
@click.option("--theta-ref", type=float, default=0.45,
              help="Reference concavity. 0.45 by convention, so that k_sn is "
                   "comparable between basins.")
@click.option("--smooth-m", type=float, default=500.0,
              help="Smoothing window for the concavity fit. k_sn is always "
                   "computed on raw cells.")
@click.option("--out", type=click.Path(), default=None,
              help="Write chi.tif, ksn.tif and the trunk profile here.")
def landscape(lat: float, lon: float, backend: str, min_area_km2: float,
              theta_ref: float, smooth_m: float, out: str | None) -> None:
    """Chi, channel steepness, concavity and knickpoints.

    Whether the landscape is still adjusting, or has settled. k_sn agrees with
    TopoToolbox to within 6% at every quantile on an identical DEM.
    """
    import numpy as np

    from . import landscape as ls
    from .basin import Basin

    b = Basin.from_point(lat, lon, backend=backend)
    r = ls.analyse(b.dem(), min_area_km2=min_area_km2, theta_ref=theta_ref,
                   smooth_m=smooth_m)
    summary = dict(r["summary"])
    summary["confidence"] = ls.confidence(r)
    click.echo(json.dumps(summary, indent=2, default=str))

    if out:
        import csv
        import os

        import rasterio

        os.makedirs(out, exist_ok=True)
        # The completion message is built from this list rather than written by
        # hand, so it cannot come to name a file the run did not produce.
        written = []
        dem = b.dem()
        for name in ("chi", "ksn"):
            arr = np.asarray(r["rasters"][name], dtype="float32")
            with rasterio.open(
                os.path.join(out, name + ".tif"), "w", driver="GTiff",
                height=arr.shape[0], width=arr.shape[1], count=1,
                dtype="float32", crs=dem.rio.crs, transform=dem.rio.transform(),
                nodata=float("nan"), compress="deflate",
            ) as dst:
                dst.write(arr, 1)
            written.append(name + ".tif")
        t = r["trunk"]
        with open(os.path.join(out, "trunk_profile.csv"), "w", newline="",
                  encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["chi_m", "elevation_m", "distance_to_outlet_m"])
            for i in range(len(t["chi_m"])):
                w.writerow([round(float(t["chi_m"][i]), 2),
                            round(float(t["elevation_m"][i]), 2),
                            round(float(t["distance_to_outlet_m"][i]), 1)])
        written.append("trunk_profile.csv")
        fields = ["chi_m", "elevation_m", "step_m", "excess_gradient_sigma"]
        with open(os.path.join(out, "knickpoints.csv"), "w", newline="",
                  encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fields)
            w.writeheader()
            for k in r["knickpoints"]:
                w.writerow({"chi_m": round(float(k["chi"]), 2),
                            "elevation_m": k["elevation_m"],
                            "step_m": k["step_m"],
                            "excess_gradient_sigma": k["excess_gradient_sigma"]})
        written.append("knickpoints.csv")
        try:
            ls.figure(r, path=os.path.join(out, "landscape_form.png"),
                      title=f"Outlet {lat:.5f}, {lon:.5f}")
            written.append("landscape_form.png")
        except Exception as exc:                        # noqa: BLE001
            click.echo(f"The figure could not be drawn ({exc.__class__.__name__}"
                       f": {exc}). Every number above is unaffected.", err=True)
        click.echo(f"Wrote {', '.join(written)} to {out}")
    for w in ls.limits(r):
        click.echo("limit: " + w, err=True)


@main.command()
@click.option("--lat", type=float, required=True, help="Outlet latitude.")
@click.option("--lon", type=float, required=True, help="Outlet longitude.")
@click.option("--backend", default="auto")
@click.option("--min-order", type=int, default=0, help="Minimum stream order.")
@click.option("--out", type=click.Path(), required=True,
              help="Write archydro.gpkg and the two CSV tables here.")
def archydro(lat: float, lon: float, backend: str, min_order: int,
             out: str) -> None:
    """The routing graph in the Arc Hydro schema.

    HydroID, HydroCode, NextDownID, AreaSqKm, on layers named Catchment and
    DrainageLine. A renaming, not a computation: every value written is one
    basinkit already holds.
    """
    import os

    from . import archydro as ah
    from .basin import Basin

    os.makedirs(out, exist_ok=True)
    b = Basin.from_point(lat, lon, backend=backend)
    sub = ah.catchment_table(b.subbasins())
    riv = ah.drainage_line_table(b.rivers(min_order=min_order))

    gpkg = os.path.join(out, "archydro.gpkg")
    sub.to_file(gpkg, layer="Catchment", driver="GPKG")
    riv.to_file(gpkg, layer="DrainageLine", driver="GPKG")
    for name, frame, cols in (
        ("catchment", sub, ["HydroID", "HydroCode", "NextDownID", "AreaSqKm"]),
        ("drainageline", riv, ["HydroID", "HydroCode", "NextDownID"]),
    ):
        have = [c for c in cols if c in frame.columns]
        frame[have].to_csv(os.path.join(out, f"archydro_{name}.csv"), index=False)

    try:
        ah.figure(sub, riv, path=os.path.join(out, "archydro_routing.png"),
                  title=f"Outlet {lat:.5f}, {lon:.5f}")
    except Exception as exc:                            # noqa: BLE001
        click.echo(f"The routing figure could not be drawn "
                   f"({exc.__class__.__name__}: {exc}). Every table is "
                   f"unaffected.", err=True)

    chk = ah.check(sub)
    click.echo(json.dumps({
        "catchments": int(len(sub)), "drainage_lines": int(len(riv)),
        "no_downstream_value": ah.NO_DOWNSTREAM, "routing_check": chk,
        "written": gpkg,
    }, indent=2))
    if not chk["single_outlet"]:
        click.echo(
            "The routing table is not a single tree draining to one outlet. "
            "Reported, not repaired: it belongs to the source data.", err=True)


if __name__ == "__main__":
    main()
