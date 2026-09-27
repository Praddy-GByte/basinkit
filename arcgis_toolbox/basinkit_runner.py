"""basinkit_runner -- runs basinkit outside ArcGIS Pro's Python environment.

The ArcGIS Pro toolbox never imports basinkit, geopandas or rasterio. It starts
this file with a different interpreter, reads the lines it prints, and adds the
files it writes. That keeps arcpy's pinned GDAL and PROJ untouched, which is the
usual way a cloned Pro environment gets broken.

Every subcommand writes its outputs into --out and prints one line per output:

    OUT<TAB><kind><TAB><path>          kind is one of: vector raster table
    INFO<TAB><text>                    progress, shown in the Pro messages pane
    RESULT<TAB><json>                  the numbers, for the tool to report

Exit code is 0 on success, 2 on a handled failure with ERROR printed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback

TAB = "\t"


def info(msg: str) -> None:
    print(f"INFO{TAB}{msg}", flush=True)


def out(kind: str, path: str) -> None:
    print(f"OUT{TAB}{kind}{TAB}{os.path.abspath(path)}", flush=True)


def result(payload) -> None:
    print(f"RESULT{TAB}{json.dumps(payload, default=str)}", flush=True)


def _basin(args):
    import basinkit as bk
    kw = {}
    if getattr(args, "backend", None) and args.backend != "auto":
        kw["backend"] = args.backend
    info(f"Delineating from {args.lat}, {args.lon}"
         + (f" using backend {kw['backend']}" if kw else ""))
    return bk.Basin.from_point(args.lat, args.lon, **kw)


def _write_vector(gdf, path):
    gdf.to_file(path, driver="GeoJSON")
    out("vector", path)


def _write_raster(da, path):
    da.rio.to_raster(path)
    out("raster", path)


def _write_table(rows, path, fieldnames=None):
    """Rows need not share keys -- the stream-order table has a bifurcation ratio
    on every order but the last, and a length ratio on every order but the first."""
    import csv
    rows = list(rows)
    if fieldnames is None:
        fieldnames = []
        for r in rows:
            for k in r:
                if k not in fieldnames:
                    fieldnames.append(k)
        fieldnames = fieldnames or ["key", "value"]
    else:
        extra = [k for r in rows for k in r if k not in fieldnames]
        for k in extra:
            if k not in fieldnames:
                fieldnames.append(k)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, restval="", extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    out("table", path)


def _flatten(d, prefix=""):
    """morphometry() and data_quality() nest; ArcGIS wants flat rows."""
    rows = []
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            rows += _flatten(v, key + ".")
        elif isinstance(v, (list, tuple)):
            rows.append({"parameter": key, "value": json.dumps(v, default=str)})
        else:
            rows.append({"parameter": key, "value": v})
    return rows


# --------------------------------------------------------------------- tools

def cmd_delineate(args):
    import geopandas as gpd
    b = _basin(args)
    gdf = gpd.GeoDataFrame(
        {"area_km2": [round(float(b.area_km2), 3)],
         "outlet_lat": [args.lat], "outlet_lon": [args.lon],
         "backend": [args.backend]},
        geometry=[b.geometry], crs="EPSG:4326")
    _write_vector(gdf, os.path.join(args.out, "basin.geojson"))
    result({"area_km2": round(float(b.area_km2), 3),
            "bounds": [round(float(v), 4) for v in b.bounds]})


def cmd_subbasins(args):
    b = _basin(args)
    sb = b.subbasins()
    info(f"{len(sb):,} sub-catchments")
    _write_vector(sb, os.path.join(args.out, "subbasins.geojson"))
    result({"n_subbasins": int(len(sb))})


def cmd_rivers(args):
    b = _basin(args)
    rv = b.rivers(min_order=args.min_order)
    _write_vector(rv, os.path.join(args.out, "rivers.geojson"))
    n_lakes = 0
    if args.lakes:
        lk = b.lakes()
        n_lakes = int(len(lk))
        if n_lakes:
            _write_vector(lk, os.path.join(args.out, "lakes.geojson"))
        else:
            info("No lakes in this basin at the requested size.")
    result({"n_reaches": int(len(rv)), "n_lakes": n_lakes})


def cmd_terrain(args):
    b = _basin(args)
    kw = {"product": args.dem_product}
    if args.max_pixels:
        kw["max_pixels"] = args.max_pixels
    info(f"Fetching {args.dem_product}")
    dem = b.dem(**kw)
    _write_raster(dem, os.path.join(args.out, "dem.tif"))
    made = ["dem"]
    for name in args.surfaces:
        info(f"Computing {name}")
        da = getattr(b, name)(dem=dem)
        _write_raster(da, os.path.join(args.out, f"{name}.tif"))
        made.append(name)
    result({"surfaces": made, "shape": list(dem.shape)})


def cmd_layers(args):
    b = _basin(args)
    kw = {"max_pixels": args.max_pixels} if args.max_pixels else {}
    written = []
    if "landcover" in args.layers:
        info("Land cover")
        _write_raster(b.landcover(source=args.landcover_source, **kw),
                      os.path.join(args.out, "landcover.tif")); written.append("landcover")
    if "soil" in args.layers:
        info(f"Soil {args.soil_property} {args.soil_depth}")
        _write_raster(b.soil(prop=args.soil_property, depth=args.soil_depth),
                      os.path.join(args.out, f"soil_{args.soil_property}_{args.soil_depth}.tif"))
        written.append("soil")
    if "surface_water" in args.layers:
        info("Surface water")
        _write_raster(b.surface_water(), os.path.join(args.out, "surface_water.tif"))
        written.append("surface_water")
    result({"layers": written})


def cmd_morphometry(args):
    b = _basin(args)
    info("Computing morphometry")
    m = b.morphometry()
    network = m.pop("network", None)
    _write_table(_flatten(m), os.path.join(args.out, "morphometry.csv"),
                 ["parameter", "value"])
    if network:
        _write_table(network, os.path.join(args.out, "network_by_order.csv"),
                     list(network[0].keys()))
    result({"n_parameters": len(_flatten(m))})


def cmd_zonal(args):
    import rioxarray
    b = _basin(args)
    values = rioxarray.open_rasterio(args.values, masked=True).squeeze("band", drop=True)
    zones = (rioxarray.open_rasterio(args.zones, masked=True).squeeze("band", drop=True)
             if args.zones else b.landcover())
    info("Summarising")
    z = b.zonal(values, zones=zones)
    path = os.path.join(args.out, "zonal.csv")
    z.to_csv(path, index=False)
    out("table", path)
    result({"n_zones": int(len(z))})


def cmd_suitability(args):
    b = _basin(args)
    info("Testing whether the elevation model can carry terrain analysis here")
    s = b.dem_suitability(support_map=args.support_map)
    support = s.pop("support", None)
    if support is not None:
        _write_raster(support, os.path.join(args.out, "dem_support.tif"))
    tests = s.pop("tests", [])
    _write_table(
        [{"test": t.get("test"), "verdict": t.get("verdict"), "measured": t.get("measured"),
          "unit": t.get("unit"), "advisory_at": t.get("advisory_at"),
          "unmet_at": t.get("unmet_at"), "statement": t.get("statement")} for t in tests],
        os.path.join(args.out, "dem_suitability.csv"),
        ["test", "verdict", "measured", "unit", "advisory_at", "unmet_at", "statement"])
    result({"grade": s.get("grade"), "unmet": s.get("unmet"),
            "support_fraction": s.get("support_fraction"),
            "statement": s.get("statement")})


def cmd_quality(args):
    b = _basin(args)
    info("Grading every layer against an independently produced source")
    q = b.data_quality()
    rows = []
    for layer in q.get("layers", []):
        rows.append({
            "layer": layer.get("layer"),
            "grade": layer.get("grade") or "not graded",
            "value": layer.get("value"),
            "indicator": layer.get("indicator"),
            "measured_against": layer.get("source"),
            "not_graded_because": layer.get("not_graded_because"),
            "statement": layer.get("statement"),
        })
    _write_table(rows, os.path.join(args.out, "data_quality.csv"),
                 ["layer", "grade", "value", "indicator", "measured_against",
                  "not_graded_because", "statement"])
    result({"overall": q.get("overall"), "basin_km2": q.get("basin_km2"),
            "grades": {r["layer"]: r["grade"] for r in rows}})


def cmd_report(args):
    b = _basin(args)
    path = os.path.join(args.out, "basin_report.pdf")
    info("Building the report")
    b.report(path, title=args.title or None)
    out("table", path)
    result({"report": path})


def cmd_everything(args):
    """One click: every analysis, plus a collage, a PDF report and a manifest."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import basinkit_everything as E

    b = _basin(args)
    skip = set()
    if args.skip_satellite:
        skip.add("Satellite")
    if args.skip:
        skip |= {s.strip() for s in args.skip.split(",") if s.strip()}

    info("Starting the full sweep. Figures go to figures/, tables to tables/.")
    records, C, csv_path = E.run_everything(
        b, args.lat, args.lon, args.out,
        max_pixels=args.max_pixels or 4_000_000,
        sat_pixels=args.sat_pixels or 1_200_000,
        stream_km2=args.stream_km2,
        clim_start=args.clim_start, clim_end=args.clim_end,
        spi_start=args.spi_start, skip=skip, emit=print)
    out("table", csv_path)

    # GIS layers, in formats ArcGIS Pro reads natively
    layers = 0
    try:
        import geopandas as gpd
        gdf = gpd.GeoDataFrame({"area_km2": [round(float(b.area_km2), 3)]},
                               geometry=[b.geometry], crs="EPSG:4326")
        _write_vector(gdf, os.path.join(args.out, "basin.geojson")); layers += 1
        for name, obj in (("subbasins", C.get("subbasins")), ("rivers", C.get("rivers")),
                          ("lakes", C.get("lakes"))):
            if obj is not None and len(obj):
                _write_vector(obj, os.path.join(args.out, name + ".geojson")); layers += 1
    except Exception as exc:                            # noqa: BLE001
        info(f"Could not write vector layers: {exc.__class__.__name__}")
    for name in ("dem", "hillshade", "landcover"):
        da = C.get(name)
        if da is not None:
            try:
                _write_raster(da, os.path.join(args.out, name + ".tif")); layers += 1
            except Exception as exc:                    # noqa: BLE001
                info(f"Could not write {name}.tif: {exc.__class__.__name__}")

    # the three extra deliverables, counted with the rest
    extras = []
    if args.download_all:
        try:
            info("Writing every layer into one folder with its licences")
            b.download_all(os.path.join(args.out, "layers"))
            extras.append("download_all")
        except Exception as exc:                        # noqa: BLE001
            info(f"download_all failed: {exc.__class__.__name__}: {exc}")
    if args.export_3d:
        try:
            p3 = os.path.join(args.out, "basin_3d.html")
            b.export_3d(p3); out("table", p3); extras.append("export_3d")
        except Exception as exc:                        # noqa: BLE001
            info(f"export_3d failed: {exc.__class__.__name__}: {exc}")

    manifest_path = os.path.join(args.out, "manifest.json")
    manifest = E.write_manifest(manifest_path, records, C,
                                extra={"gis_layers_written": layers, "extras": extras})
    out("table", manifest_path)

    ok = manifest["counts"]["ok"]
    grade = (C.get("quality") or {}).get("overall", "—")
    collage = os.path.join(args.out, "basinkit_collage.png")
    try:
        info("Building the collage")
        E.build_collage(
            records, collage,
            title=f"{ok} analyses from a single coordinate",
            subtitle=args.title or "one click",
            tiles=[(f"{float(b.area_km2):,.0f} km²", "basin delineated"),
                   (str(len(manifest.get("datasets_available", []))), "open datasets, no account"),
                   (str(ok), "analyses completed"),
                   (str(grade), "the grade the run gave itself")],
            footer=(f"{args.lat:.4f} N, {args.lon:.4f} E.  No account, no API key, "
                    f"nothing downloaded by hand.\nEvery panel came out of one run "
                    f"of basinkit {manifest['basinkit_version']}."))
        out("table", collage)
    except Exception as exc:                            # noqa: BLE001
        info(f"Collage failed: {exc.__class__.__name__}: {exc}")

    report = os.path.join(args.out, "basin_report.pdf")
    try:
        info("Building the PDF report")
        E.build_report(records, report, C, manifest)
        out("table", report)
    except Exception as exc:                            # noqa: BLE001
        info(f"Report failed: {exc.__class__.__name__}: {exc}")

    result({"analyses_completed": ok,
            "analyses_failed": manifest["counts"]["failed"],
            "analyses_skipped": manifest["counts"]["skipped"],
            "deliverables": ok + len(extras) + 3,
            "overall_grade": grade,
            "area_km2": round(float(b.area_km2), 1),
            "gis_layers": layers,
            "collage": collage, "report": report, "manifest": manifest_path})


def cmd_selftest(args):
    """Proves this interpreter can run basinkit at all -- used by the toolbox."""
    import basinkit as bk
    mods = {}
    for name in ("geopandas", "rasterio", "rioxarray", "xarray", "pyproj", "shapely"):
        try:
            mods[name] = __import__(name).__version__
        except Exception as exc:                       # noqa: BLE001
            mods[name] = f"MISSING ({exc.__class__.__name__})"
    result({"basinkit": bk.__version__, "python": sys.version.split()[0],
            "executable": sys.executable, "dependencies": mods})


# --------------------------------------------------------------------- cli

SURFACES = ["hillshade", "slope", "aspect", "curvature", "tpi", "tri", "roughness",
            "landform", "flow_accumulation", "streams", "twi", "hand"]


def build_parser():
    p = argparse.ArgumentParser(prog="basinkit_runner")
    sub = p.add_subparsers(dest="cmd", required=True)

    def point(sp, need_out=True):
        sp.add_argument("--lat", type=float, required=True)
        sp.add_argument("--lon", type=float, required=True)
        sp.add_argument("--backend", default="auto",
                        choices=["auto", "hydrobasins", "dem", "api", "tdx"])
        if need_out:
            sp.add_argument("--out", required=True)
        return sp

    point(sub.add_parser("delineate")).set_defaults(func=cmd_delineate)
    point(sub.add_parser("subbasins")).set_defaults(func=cmd_subbasins)

    sp = point(sub.add_parser("rivers"))
    sp.add_argument("--min-order", type=int, default=0)
    sp.add_argument("--lakes", action="store_true")
    sp.set_defaults(func=cmd_rivers)

    sp = point(sub.add_parser("terrain"))
    sp.add_argument("--dem-product", default="cop30",
                    choices=["cop30", "cop90", "nasadem", "srtm30"])
    sp.add_argument("--surfaces", nargs="*", default=["hillshade", "slope", "aspect"],
                    choices=SURFACES)
    sp.add_argument("--max-pixels", type=int, default=0)
    sp.set_defaults(func=cmd_terrain)

    sp = point(sub.add_parser("layers"))
    sp.add_argument("--layers", nargs="+", default=["landcover"],
                    choices=["landcover", "soil", "surface_water"])
    sp.add_argument("--landcover-source", default="worldcover",
                    choices=["worldcover", "esri"])
    sp.add_argument("--soil-property", default="clay")
    sp.add_argument("--soil-depth", default="0-5cm")
    sp.add_argument("--max-pixels", type=int, default=0)
    sp.set_defaults(func=cmd_layers)

    point(sub.add_parser("morphometry")).set_defaults(func=cmd_morphometry)

    sp = point(sub.add_parser("zonal"))
    sp.add_argument("--values", required=True)
    sp.add_argument("--zones", default="")
    sp.set_defaults(func=cmd_zonal)

    sp = point(sub.add_parser("suitability"))
    sp.add_argument("--support-map", action="store_true")
    sp.set_defaults(func=cmd_suitability)

    point(sub.add_parser("quality")).set_defaults(func=cmd_quality)

    sp = point(sub.add_parser("report"))
    sp.add_argument("--title", default="")
    sp.set_defaults(func=cmd_report)

    sp = point(sub.add_parser("everything"))
    sp.add_argument("--title", default="")
    sp.add_argument("--max-pixels", type=int, default=0)
    sp.add_argument("--sat-pixels", type=int, default=0)
    sp.add_argument("--stream-km2", type=float, default=5.0)
    sp.add_argument("--clim-start", type=int, default=2000)
    sp.add_argument("--clim-end", type=int, default=2024)
    sp.add_argument("--spi-start", type=int, default=1985)
    sp.add_argument("--skip-satellite", action="store_true")
    sp.add_argument("--skip", default="")
    sp.add_argument("--download-all", action="store_true")
    sp.add_argument("--export-3d", action="store_true")
    sp.set_defaults(func=cmd_everything)

    sub.add_parser("selftest").set_defaults(func=cmd_selftest, out=None)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if getattr(args, "out", None):
        os.makedirs(args.out, exist_ok=True)
    try:
        args.func(args)
    except Exception as exc:                            # noqa: BLE001
        print(f"ERROR{TAB}{exc.__class__.__name__}: {exc}", flush=True)
        traceback.print_exc(file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
