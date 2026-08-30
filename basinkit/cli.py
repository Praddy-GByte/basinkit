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


if __name__ == "__main__":
    main()
