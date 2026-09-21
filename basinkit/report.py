"""An eight-page report a thesis or a manuscript can use directly.

Everything basinkit computes about a basin, laid out on A4 with the numbers
carrying their symbols, units and original references, and with the suitability
grade on the cover rather than in a footnote. The point is that a reader can
see what the result rests on without being handed the code.

The pages, in order:

1. Cover: where, how big, which backend, and the suitability grade
2. Elevation, hillshade, the hypsometric curve and the elevation distribution
3. Slope and aspect, with their distributions
4. Curvature, position index, ruggedness and the slope-position classes
5. The channel network and Horton's laws
6. The morphometric parameters, with symbols and references
7. The suitability scorecard, the support map and the drainage-density curve
8. Methods: sources, licences, versions and what to cite

Pages 5 and 6 need the river network, which is a separate download. Without it
they are replaced by a page saying so rather than quietly omitted.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from .exceptions import MissingDependency

A4 = (8.27, 11.69)

#: Every morphometric parameter the report prints: section, key, the name to
#: print, symbol, unit and the paper the definition comes from. The printed
#: name is written out rather than derived from the key, because stripping
#: the units off a key mangles the words around them.
PARAMETERS: tuple[tuple[str, str, str, str, str, str], ...] = (
    ("areal", "area_km2", "area", "A", "km2", "-"),
    ("areal", "drainage_density_km_per_km2", "drainage density", "Dd", "km/km2",
     "Horton (1932)"),
    ("areal", "stream_frequency_per_km2", "stream frequency", "Fs", "1/km2",
     "Horton (1932)"),
    ("areal", "drainage_texture_per_km", "drainage texture", "Rt", "1/km", "Horton (1945)"),
    ("areal", "texture_ratio_per_km", "texture ratio", "T", "1/km", "Smith (1950)"),
    ("areal", "form_factor", "form factor", "Rf", "-", "Horton (1932)"),
    ("areal", "elongation_ratio", "elongation ratio", "Re", "-", "Schumm (1956)"),
    ("areal", "circularity_ratio", "circularity ratio", "Rc", "-", "Miller (1953)"),
    ("areal", "compactness_coefficient", "compactness coefficient", "Cc", "-",
     "Gravelius (1914)"),
    ("areal", "shape_factor", "shape factor", "Bs", "-", "Horton (1932)"),
    ("areal", "lemniscate_ratio", "lemniscate ratio", "k", "-",
     "Chorley et al. (1957)"),
    ("areal", "constant_of_channel_maintenance_km2_per_km",
     "constant of channel maintenance", "C", "km2/km", "Schumm (1956)"),
    ("areal", "infiltration_number", "infiltration number", "If", "-", "Faniran (1968)"),
    ("areal", "drainage_intensity", "drainage intensity", "Di", "-", "Faniran (1968)"),
    ("areal", "fitness_ratio", "fitness ratio", "Rfn", "-", "Melton (1957)"),
    ("areal", "wandering_ratio", "wandering ratio", "Rw", "-",
     "Smart and Surkan (1967)"),
    ("linear", "stream_orders", "stream orders", "u", "-", "Strahler (1952)"),
    ("linear", "total_streams", "total streams", "Nu", "-", "Horton (1945)"),
    ("linear", "total_stream_length_km", "total stream length", "Lu", "km", "Horton (1945)"),
    ("linear", "mean_bifurcation_ratio", "mean bifurcation ratio", "Rb", "-", "Horton (1945)"),
    ("linear", "weighted_mean_bifurcation_ratio", "weighted mean bifurcation ratio",
     "Rbwm", "-", "Strahler (1953)"),
    ("linear", "mean_stream_length_ratio", "mean stream length ratio", "Rl", "-", "Horton (1945)"),
    ("linear", "rho_coefficient", "rho coefficient", "rho", "-", "Horton (1945)"),
    ("linear", "length_of_overland_flow_km", "length of overland flow", "Lg", "km",
     "Horton (1945)"),
    ("linear", "basin_length_km", "basin length", "Lb", "km", "Schumm (1956)"),
    ("linear", "basin_perimeter_km", "basin perimeter", "P", "km", "-"),
    ("linear", "main_channel_length_km", "main channel length", "Cl", "km", "-"),
    ("linear", "main_channel_sinuosity", "main channel sinuosity", "Si", "-",
     "Mueller (1968)"),
    ("relief", "elevation_min_m", "lowest point", "Zmin", "m", "-"),
    ("relief", "elevation_max_m", "highest point", "Zmax", "m", "-"),
    ("relief", "elevation_mean_m", "mean elevation", "Zmean", "m", "-"),
    ("relief", "total_relief_m", "total relief", "H", "m", "Strahler (1952)"),
    ("relief", "channel_gradient_m_per_km", "channel gradient", "Sc", "m/km", "-"),
    ("relief", "relief_ratio", "relief ratio", "Rh", "-", "Schumm (1956)"),
    ("relief", "relative_relief", "relative relief", "Rhp", "%", "Melton (1957)"),
    ("relief", "ruggedness_number", "ruggedness number", "Rn", "-", "Strahler (1958)"),
    ("relief", "melton_ruggedness_number", "Melton ruggedness number", "MRn", "-",
     "Melton (1965)"),
    ("relief", "hypsometric_integral", "hypsometric integral", "HI", "-",
     "Strahler (1952)"),
    ("relief", "elevation_relief_ratio", "elevation-relief ratio", "E", "-",
     "Pike and Wilson (1971)"),
)

_GRADE_COLOUR = {"HIGH": "#1a7a3e", "MODERATE": "#e08214", "LIMITED": "#b2182b"}

_LANDFORM_COLOURS = ("#3b7dbf", "#8fc3e3", "#f3e6b3", "#c7b37a",
                     "#b07d4a", "#8c3b2a")


def _matplotlib():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        return matplotlib, plt
    except ImportError as exc:
        raise MissingDependency("matplotlib", "viz") from exc


def _array(layer):
    import numpy as np

    values = np.asarray(getattr(layer, "values", layer), dtype="float64")
    if values.ndim == 3 and values.shape[0] == 1:
        values = values[0]
    return values


def _extent(dem):
    bounds = dem.rio.bounds()
    return (bounds[0], bounds[2], bounds[1], bounds[3])


def _draw_raster(ax, dem, values, *, cmap, title, units, geometry=None,
                 vmin=None, vmax=None, percentiles=(2, 98), discrete=None):
    """One map panel, scaled off the percentiles so outliers do not flatten it."""
    import numpy as np

    if vmin is None or vmax is None:
        finite = values[np.isfinite(values)]
        if finite.size:
            lo, hi = np.percentile(finite, percentiles)
            vmin = lo if vmin is None else vmin
            vmax = hi if vmax is None else vmax
        if vmin == vmax:
            vmax = (vmin or 0.0) + 1.0

    image = ax.imshow(values, extent=_extent(dem), cmap=cmap, vmin=vmin,
                      vmax=vmax, interpolation="nearest", origin="upper")
    if geometry is not None:
        _outline(ax, geometry)
    ax.set_title(title, fontsize=8.5, pad=4)
    ax.set_xticks([])
    ax.set_yticks([])
    for side in ax.spines.values():
        side.set_visible(False)

    if discrete is None:
        bar = ax.figure.colorbar(image, ax=ax, fraction=0.04, pad=0.02)
        bar.ax.tick_params(labelsize=6)
        bar.set_label(units, fontsize=6.5)
    return image


def _outline(ax, geometry):
    """The basin boundary, drawn over whatever is underneath it."""
    polygons = (list(geometry.geoms) if geometry.geom_type == "MultiPolygon"
                else [geometry])
    for polygon in polygons:
        xs, ys = polygon.exterior.xy
        ax.plot(xs, ys, color="black", linewidth=0.6, zorder=5)


def _page(plt, pdf, title, subtitle=None):
    figure = plt.figure(figsize=A4)
    figure.text(0.06, 0.965, title, fontsize=13, weight="bold")
    if subtitle:
        figure.text(0.06, 0.945, subtitle, fontsize=8, color="#555555")
    figure.text(0.06, 0.022, "basinkit", fontsize=7, color="#888888")
    return figure


def _close(plt, pdf, figure, number):
    figure.text(0.94, 0.022, str(number), fontsize=7, color="#888888", ha="right")
    pdf.savefig(figure)
    plt.close(figure)


def _fmt(value, places=3):
    if value is None:
        return "not available"
    if isinstance(value, float):
        if value != value:
            return "not available"
        if abs(value) >= 1000:
            return f"{value:,.0f}"
        return f"{value:.{places}f}".rstrip("0").rstrip(".")
    return str(value)


def _ratio(value):
    """A ratio in a table column: fixed width, or a dash where there is none."""
    if value is None or value != value:
        return "-"
    return f"{float(value):.3f}"


def _text_block(figure, x, y, lines, *, size=8, leading=0.0155, mono=False):
    family = "monospace" if mono else None
    for i, line in enumerate(lines):
        figure.text(x, y - i * leading, line, fontsize=size, family=family,
                    va="top")
    return y - len(lines) * leading


# --- the pages -------------------------------------------------------------


def _cover(plt, pdf, basin, title, grade, elevation, page):
    import numpy as np

    figure = plt.figure(figsize=A4)
    figure.text(0.06, 0.93, title, fontsize=22, weight="bold", va="top")

    lat, lon = basin.centroid
    provenance = dict(getattr(basin, "provenance", {}) or {})
    figure.text(0.06, 0.885,
                f"Centroid {lat:.5f}, {lon:.5f}   |   "
                f"delineated by {provenance.get('backend', 'unknown')}   |   "
                f"{_dt.date.today().isoformat()}",
                fontsize=9, color="#555555", va="top")

    axes = figure.add_axes((0.06, 0.40, 0.60, 0.44))
    values = _array(elevation)
    _draw_raster(axes, elevation, values, cmap="terrain", title="",
                 units="elevation, m", geometry=basin.geometry)

    finite = values[np.isfinite(values)]
    headline = [
        ("Catchment area", f"{basin.area_km2:,.1f} km2"),
        ("Relief", f"{float(finite.max() - finite.min()):,.0f} m"
                   if finite.size else "not available"),
        ("Highest point", f"{float(finite.max()):,.0f} m" if finite.size else "-"),
        ("Lowest point", f"{float(finite.min()):,.0f} m" if finite.size else "-"),
        ("Elevation source", _elevation_source(elevation)),
        ("Boundary source", str(provenance.get("source_dataset", "unknown"))),
    ]
    y = 0.345
    for label, value in headline:
        figure.text(0.06, y, label, fontsize=9, color="#555555")
        figure.text(0.34, y, value, fontsize=9, weight="bold")
        y -= 0.026

    colour = _GRADE_COLOUR.get(grade["grade"], "#555555")
    badge = figure.add_axes((0.70, 0.60, 0.24, 0.24))
    badge.set_xticks([])
    badge.set_yticks([])
    for side in badge.spines.values():
        side.set_color(colour)
        side.set_linewidth(2.0)
    badge.text(0.5, 0.72, "ELEVATION DATA", fontsize=7.5, ha="center",
               color="#555555", transform=badge.transAxes)
    badge.text(0.5, 0.56, "SUITABILITY", fontsize=7.5, ha="center",
               color="#555555", transform=badge.transAxes)
    badge.text(0.5, 0.28, grade["grade"], fontsize=17, ha="center",
               weight="bold", color=colour, transform=badge.transAxes)

    failing = [t["test"] for t in grade["tests"] if t["verdict"] != "pass"]
    figure.text(0.70, 0.565,
                "every test passed" if not failing
                else "raised by: " + ", ".join(failing),
                fontsize=7.5, color="#555555")

    wrapped = _wrap(grade["statement"], 108)
    _text_block(figure, 0.06, 0.20, wrapped[:9], size=8.2)

    figure.text(0.06, 0.055,
                "Generated by basinkit. The suitability grade describes the "
                "terrain products in this report, not the basin boundary.",
                fontsize=7, color="#888888")
    _close(plt, pdf, figure, page)


def _wrap(text, width):
    import textwrap

    return textwrap.wrap(str(text), width=width)


def _elevation_page(plt, pdf, basin, elevation, page):
    import numpy as np

    from .terrain import hillshade

    figure = _page(plt, pdf, "Elevation",
                   "The surface every other page is derived from")

    values = _array(elevation)
    axes = figure.add_axes((0.06, 0.55, 0.40, 0.34))
    _draw_raster(axes, elevation, values, cmap="terrain",
                 title="Elevation", units="m", geometry=basin.geometry)

    axes = figure.add_axes((0.55, 0.55, 0.40, 0.34))
    _draw_raster(axes, elevation, _array(hillshade(elevation)), cmap="gray",
                 title="Hillshade, sun from the north-west", units="",
                 geometry=basin.geometry, vmin=0.0, vmax=1.0)

    finite = values[np.isfinite(values)]
    axes = figure.add_axes((0.10, 0.30, 0.36, 0.18))
    if finite.size:
        fraction = np.linspace(0, 1, 200)
        relative = np.percentile(finite, (1 - fraction) * 100)
        low, high = float(finite.min()), float(finite.max())
        normalised = (relative - low) / max(high - low, 1e-9)
        integral = float(np.trapezoid(normalised, fraction))
        axes.plot(fraction, normalised, color="#1f4e79", linewidth=1.4)
        axes.fill_between(fraction, normalised, color="#1f4e79", alpha=0.15)
        axes.set_title(f"Hypsometric curve, integral {integral:.3f}", fontsize=8.5)
    axes.set_xlabel("relative area", fontsize=7.5)
    axes.set_ylabel("relative elevation", fontsize=7.5)
    axes.tick_params(labelsize=6.5)
    axes.set_xlim(0, 1)
    axes.set_ylim(0, 1)

    axes = figure.add_axes((0.57, 0.30, 0.36, 0.18))
    if finite.size:
        axes.hist(finite, bins=60, color="#1f4e79", alpha=0.8)
    axes.set_title("Elevation distribution", fontsize=8.5)
    axes.set_xlabel("m", fontsize=7.5)
    axes.set_ylabel("cells", fontsize=7.5)
    axes.tick_params(labelsize=6.5)

    note = (
        "The hypsometric integral is the area under the curve. Near 0.6 and "
        "above describes a basin still being cut into; near 0.3 and below one "
        "largely worn down. Strahler's youth, maturity and old-age stages were "
        "defined for fluvially eroded basins, so in glaciated or tectonically "
        "active terrain the integral is reported and the stage label is left "
        "to the reader."
    )
    _text_block(figure, 0.06, 0.22, _wrap(note, 112), size=8)
    _close(plt, pdf, figure, page)


def _slope_page(plt, pdf, basin, elevation, page):
    import numpy as np

    from .terrain import aspect, slope

    figure = _page(plt, pdf, "Slope and aspect",
                   "Gradient and the direction it faces")

    gradient = _array(slope(elevation))
    facing = _array(aspect(elevation))

    axes = figure.add_axes((0.06, 0.55, 0.40, 0.34))
    _draw_raster(axes, elevation, gradient, cmap="YlOrRd", title="Slope",
                 units="degrees", geometry=basin.geometry)

    axes = figure.add_axes((0.55, 0.55, 0.40, 0.34))
    _draw_raster(axes, elevation, facing, cmap="twilight", title="Aspect",
                 units="degrees from north", geometry=basin.geometry,
                 vmin=0, vmax=360)

    classes = [(0, 5), (5, 10), (10, 15), (15, 25), (15, 35), (35, 90)]
    edges = [0, 5, 10, 15, 25, 35, 90]
    labels = ["0-5", "5-10", "10-15", "15-25", "25-35", "35+"]
    finite = gradient[np.isfinite(gradient)]
    counts = [float(((finite >= lo) & (finite < hi)).sum()) / max(finite.size, 1) * 100
              for lo, hi in zip(edges[:-1], edges[1:], strict=True)]
    axes = figure.add_axes((0.10, 0.30, 0.36, 0.18))
    axes.bar(labels, counts, color="#c44e52")
    axes.set_title("Slope classes", fontsize=8.5)
    axes.set_ylabel("percent of basin", fontsize=7.5)
    axes.set_xlabel("degrees", fontsize=7.5)
    axes.tick_params(labelsize=6.5)
    del classes

    axes = figure.add_axes((0.57, 0.28, 0.34, 0.22), projection="polar")
    facing_finite = facing[np.isfinite(facing)]
    if facing_finite.size:
        bins = np.linspace(0, 360, 17)
        heights, _ = np.histogram(facing_finite, bins=bins)
        centres = np.radians(bins[:-1] + 11.25)
        axes.bar(centres, heights, width=np.radians(22.5), color="#4c72b0",
                 alpha=0.85, edgecolor="white", linewidth=0.4)
    axes.set_theta_zero_location("N")
    axes.set_theta_direction(-1)
    axes.set_yticklabels([])
    axes.tick_params(labelsize=6.5)
    axes.set_title("Aspect rose", fontsize=8.5, pad=10)

    median = float(np.nanmedian(finite)) if finite.size else float("nan")
    note = (
        f"Median slope is {median:.1f} degrees. Aspect is undefined where the "
        "ground is level, so the rose is read together with the slope classes: "
        "a strong direction over a basin that is mostly under five degrees is "
        "describing the elevation model's noise, not the hillsides."
    )
    _text_block(figure, 0.06, 0.20, _wrap(note, 112), size=8)
    _close(plt, pdf, figure, page)


def _landform_page(plt, pdf, basin, elevation, page):
    import numpy as np
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from matplotlib.patches import Patch

    from .terrain import LANDFORM_CLASSES, curvature, landform, tpi, tri

    figure = _page(plt, pdf, "Shape of the ground",
                   "Curvature, slope position, ruggedness and the classes they give")

    axes = figure.add_axes((0.06, 0.55, 0.40, 0.34))
    _draw_raster(axes, elevation, _array(curvature(elevation)), cmap="RdBu_r",
                 title="Profile curvature", units="1/m",
                 geometry=basin.geometry, percentiles=(5, 95))

    axes = figure.add_axes((0.55, 0.55, 0.40, 0.34))
    _draw_raster(axes, elevation, _array(tpi(elevation)), cmap="BrBG_r",
                 title="Topographic position index, 11 cells", units="m",
                 geometry=basin.geometry, percentiles=(5, 95))

    axes = figure.add_axes((0.06, 0.20, 0.40, 0.31))
    _draw_raster(axes, elevation, _array(tri(elevation)), cmap="magma",
                 title="Terrain ruggedness index", units="m",
                 geometry=basin.geometry)

    axes = figure.add_axes((0.55, 0.20, 0.40, 0.31))
    try:
        classes = _array(landform(elevation))
        cmap = ListedColormap(_LANDFORM_COLOURS)
        norm = BoundaryNorm(np.arange(-0.5, 6.5, 1.0), cmap.N)
        axes.imshow(classes, extent=_extent(elevation), cmap=cmap, norm=norm,
                    interpolation="nearest", origin="upper")
        _outline(axes, basin.geometry)
        axes.legend(handles=[Patch(facecolor=c, label=n)
                             for c, n in zip(_LANDFORM_COLOURS,
                                             LANDFORM_CLASSES, strict=True)],
                    fontsize=6, loc="lower left", framealpha=0.85)
    except ValueError as exc:
        axes.text(0.5, 0.5, str(exc), ha="center", va="center", fontsize=7,
                  wrap=True, transform=axes.transAxes)
    axes.set_title("Slope position", fontsize=8.5, pad=4)
    axes.set_xticks([])
    axes.set_yticks([])
    for side in axes.spines.values():
        side.set_visible(False)

    note = (
        "The classes are cut at half and one standard deviation of the position "
        "index over this basin, so they describe positions within this terrain "
        "and are not comparable between basins without saying so. The "
        "ruggedness index answers to gradient as well as to variation: on a "
        "smooth uniform slope it largely restates the slope map beside it."
    )
    _text_block(figure, 0.06, 0.15, _wrap(note, 112), size=8)
    _close(plt, pdf, figure, page)


def _network_page(plt, pdf, basin, rivers, morph, page):

    figure = _page(plt, pdf, "The channel network",
                   "Strahler orders, and whether the network obeys Horton's laws")

    axes = figure.add_axes((0.06, 0.52, 0.42, 0.38))
    _outline(axes, basin.geometry)
    if rivers is not None and len(rivers):
        orders = rivers["ORD_STRA"].astype(int)
        for order in sorted(orders.unique()):
            subset = rivers[orders == order]
            for line in subset.geometry:
                geoms = (list(line.geoms) if line.geom_type == "MultiLineString"
                         else [line])
                for part in geoms:
                    xs, ys = part.xy
                    axes.plot(xs, ys, color="#1f6fb4",
                              linewidth=0.25 + 0.35 * order)
    axes.set_aspect("equal")
    axes.set_title("Stream network, width by Strahler order", fontsize=8.5)
    axes.set_xticks([])
    axes.set_yticks([])
    for side in axes.spines.values():
        side.set_visible(False)

    network = morph.get("network", []) if morph else []
    orders = [row["order"] for row in network]
    counts = [row["streams"] for row in network]
    lengths = [row["total_length_km"] for row in network]

    axes = figure.add_axes((0.57, 0.68, 0.36, 0.22))
    if counts:
        axes.semilogy(orders, counts, "o-", color="#1f4e79", linewidth=1.2,
                      markersize=4)
    axes.set_title("Law of stream numbers", fontsize=8.5)
    axes.set_xlabel("Strahler order", fontsize=7.5)
    axes.set_ylabel("streams", fontsize=7.5)
    axes.tick_params(labelsize=6.5)

    axes = figure.add_axes((0.57, 0.40, 0.36, 0.22))
    if lengths:
        axes.semilogy(orders, lengths, "s-", color="#8c3b2a", linewidth=1.2,
                      markersize=4)
    axes.set_title("Law of stream lengths", fontsize=8.5)
    axes.set_xlabel("Strahler order", fontsize=7.5)
    axes.set_ylabel("total length, km", fontsize=7.5)
    axes.tick_params(labelsize=6.5)

    header = f"{'order':>6} {'streams':>9} {'reaches':>9} {'length km':>11} {'Rb':>7} {'Rl':>7}"
    rows = [header, "-" * len(header)]
    for row in network:
        rows.append(
            f"{row['order']:>6} {row['streams']:>9} {row.get('reaches', 0):>9} "
            f"{row['total_length_km']:>11,.2f} "
            f"{_ratio(row.get('bifurcation_ratio')):>7} "
            f"{_ratio(row.get('length_ratio')):>7}"
        )
    _text_block(figure, 0.06, 0.44, rows, size=7.2, mono=True, leading=0.0135)

    warnings_found = (morph or {}).get("warnings", [])
    lines = []
    if warnings_found:
        lines.append("Consistency of the stream counts:")
        for warning in warnings_found[:4]:
            lines += _wrap(f"  [{warning['severity']}] {warning['message']}", 108)
    else:
        lines += _wrap(
            "Stream counts are internally consistent with Strahler ordering. "
            "Streams are counted as Strahler streams, not as dataset reaches, "
            "which is why the reach column differs from the stream column.", 108)
    lines += _wrap(
        "A bifurcation ratio between 3 and 5 is the usual range for a basin "
        "whose network is controlled by the ground rather than by structure; "
        "values outside it are worth explaining rather than reporting.", 108)
    _text_block(figure, 0.06, 0.20, lines, size=8)
    _close(plt, pdf, figure, page)


def _parameter_page(plt, pdf, morph, page):
    figure = _page(plt, pdf, "Morphometric parameters",
                   "Symbol, value, unit and the definition each one comes from")

    header = f"{'parameter':<44} {'sym':<6} {'value':>14} {'unit':<9} {'after':<26}"
    rows = [header, "-" * len(header)]
    for group in ("areal", "linear", "relief"):
        block = (morph or {}).get(group, {}) or {}
        printed = False
        for section, key, name, symbol, unit, source in PARAMETERS:
            if section != group or key not in block:
                continue
            if not printed:
                rows.append("")
                rows.append(group.upper())
                printed = True
            rows.append(f"{name:<44} {symbol:<6} {_fmt(block[key], 4):>14} "
                        f"{unit:<9} {source:<26}")
    _text_block(figure, 0.05, 0.90, rows, size=6.8, mono=True, leading=0.0118)

    notes = (morph or {}).get("notes", [])
    lines = ["Notes"]
    for note in notes:
        lines += _wrap("  " + note, 110)
    _text_block(figure, 0.05, 0.22, lines, size=7.6)
    _close(plt, pdf, figure, page)


def _suitability_page(plt, pdf, basin, elevation, grade, density, page):
    figure = _page(plt, pdf, "What the answer rests on",
                   "The suitability tests, cell by cell, and the threshold "
                   "drainage density depends on")

    colour = _GRADE_COLOUR.get(grade["grade"], "#555555")
    figure.text(0.06, 0.905, f"Grade: {grade['grade']}", fontsize=12,
                weight="bold", color=colour)
    figure.text(0.30, 0.907,
                f"{grade['product']}, assumed vertical error "
                f"{grade['vertical_error_m']:.1f} m, cell {grade['cell_size_m']:.0f} m",
                fontsize=8, color="#555555")

    header = (f"{'test':<11} {'verdict':<9} {'measured':>12} "
              f"{'advisory at':>13} {'unmet at':>10}  unit")
    rows = [header, "-" * (len(header) + 16)]
    for test in grade["tests"]:
        rows.append(
            f"{test['test']:<11} {test['verdict']:<9} "
            f"{_fmt(test['measured'], 3):>12} {_fmt(test['advisory_at'], 2):>13} "
            f"{_fmt(test['unmet_at'], 2):>10}  {test['unit']}"
        )
    _text_block(figure, 0.06, 0.875, rows, size=7.4, mono=True, leading=0.0135)

    axes = figure.add_axes((0.06, 0.40, 0.40, 0.30))
    support = grade.get("support")
    if support is not None:
        axes.imshow(_array(support), extent=_extent(elevation), cmap="RdYlGn",
                    vmin=0, vmax=1, interpolation="nearest", origin="upper")
        _outline(axes, basin.geometry)
        fraction = grade.get("support_fraction")
        axes.set_title(
            "Cells the model supports (green)"
            + (f": {fraction:.0%}" if fraction is not None else ""),
            fontsize=8.5, pad=4)
    axes.set_xticks([])
    axes.set_yticks([])
    for side in axes.spines.values():
        side.set_visible(False)

    axes = figure.add_axes((0.57, 0.42, 0.36, 0.26))
    if density:
        thresholds = [row["threshold_km2"] for row in density["curve"]]
        values = [row["drainage_density_km_per_km2"] for row in density["curve"]]
        axes.loglog(thresholds, values, "o-", color="#1f4e79", linewidth=1.3,
                    markersize=3.5)
        chosen = density["chosen"]
        axes.plot([chosen["threshold_km2"]],
                  [chosen["drainage_density_km_per_km2"]], "o", color="#b2182b",
                  markersize=7, zorder=5)
        axes.set_title(
            f"Drainage density, {density['range_factor']:.0f}x across the span",
            fontsize=8.5)
        axes.set_xlabel("channel initiation threshold, km2", fontsize=7.5)
        axes.set_ylabel("Dd, km/km2", fontsize=7.5)
        axes.tick_params(labelsize=6.5)
        axes.grid(True, which="both", alpha=0.25, linewidth=0.4)

    lines = _wrap(grade["statement"], 112)
    if density:
        lines.append("")
        lines += _wrap(
            f"Drainage density is {density['chosen']['drainage_density_km_per_km2']:.3f} "
            f"km/km2 at a channel initiation threshold of "
            f"{density['chosen_threshold_km2']:g} km2, chosen for "
            f"{density['chosen_because']}. Across an order of magnitude either "
            f"side of that choice the figure moves by "
            f"{density['range_factor']:.0f} times, which is why the threshold "
            "belongs beside the number wherever it is quoted.", 112)
        lines.append("")
        lines += _wrap(
            "This is not the drainage density in the parameter table. That one "
            "is measured on the mapped river network; this one on the channels "
            "routed from this elevation raster. Two different networks, so the "
            "two figures are expected to differ, often by several times. "
            "Neither is wrong. Quoting one as the other is.", 112)
    _text_block(figure, 0.06, 0.33, lines[:16], size=8)
    _close(plt, pdf, figure, page)


def _methods_page(plt, pdf, basin, grade, density, page):
    import platform

    from . import __version__
    from .catalog import DATASETS

    figure = _page(plt, pdf, "Methods and sources",
                   "Everything needed to reproduce or to cite this report")

    provenance = dict(getattr(basin, "provenance", {}) or {})
    lat, lon = basin.centroid

    lines = ["DELINEATION", ""]
    lines += _wrap(
        f"Backend: {provenance.get('backend', 'unknown')}. "
        f"Source: {provenance.get('source_dataset', 'not recorded')}. "
        f"Area {basin.area_km2:,.2f} km2, computed by reprojecting the polygon "
        f"to a Lambert azimuthal equal-area projection centred on "
        f"{lat:.4f}, {lon:.4f}, not by summing degrees.", 110)
    for key in ("snap_distance_px", "flow_accum_at_outlet_km2",
                "reported_up_area_km2", "n_units", "window_deg"):
        if key in provenance:
            lines.append(f"  {key}: {provenance[key]}")

    lines += ["", "TERRAIN", ""]
    lines += _wrap(
        "Slope, aspect, curvature and hillshade are computed on the elevation "
        "raster with cell size taken per row from that row's latitude, so a "
        "high-latitude basin is not reported as steeper than it is. Flow "
        "routing is D8 over the depression-filled surface, with ground outside "
        "the basin treated as nodata rather than filled, so accumulation counts "
        "only cells inside the polygon. Height above drainage is measured on "
        "the same filled surface the routing used.", 110)

    lines += ["", "ELEVATION DATA SUITABILITY", ""]
    lines += _wrap(
        f"Grade {grade['grade']}, from five measurements against stated "
        f"thresholds, assuming a vertical error of "
        f"{grade['vertical_error_m']:.1f} m for {grade['product']}. "
        + grade["note"], 110)

    if density:
        lines += ["", "DRAINAGE DENSITY", ""]
        lines += _wrap(density["note"], 110)

    lines += ["", "SOURCES AND LICENCES", ""]
    seen = set()
    for key in ("cop30", "hydrobasins", "hydrorivers"):
        entry = DATASETS.get(key)
        if entry is None or key in seen:
            continue
        seen.add(key)
        lines.append(f"  {entry.name} -- {entry.license}")
        if entry.citation:
            lines += _wrap(f"      {entry.citation}", 104)

    lines += ["", "SOFTWARE", ""]
    lines.append(f"  basinkit {__version__} on Python "
                 f"{platform.python_version()} ({platform.system()})")
    for module in ("numpy", "rasterio", "geopandas", "pyflwdir", "matplotlib"):
        try:
            imported = __import__(module)
            lines.append(f"  {module} {getattr(imported, '__version__', 'unknown')}")
        except ImportError:
            lines.append(f"  {module} not installed")

    lines += ["", "UNCERTAINTY", ""]
    lines += _wrap(
        "Catchment area accuracy depends almost entirely on catchment size and "
        "is published by size band rather than as a single figure; see the "
        "verification page in the basinkit documentation. The grade on the "
        "cover of this report describes the terrain products here, which is a "
        "separate question from the accuracy of the boundary.", 110)

    _text_block(figure, 0.06, 0.905, lines, size=7.3, leading=0.0128)
    _close(plt, pdf, figure, page)


def _missing_network_page(plt, pdf, reason, page):
    figure = _page(plt, pdf, "The channel network",
                   "Not included in this report")
    lines = _wrap(
        "The stream network and every parameter derived from it are missing "
        "from this report because the river layer could not be prepared: "
        f"{reason}", 108)
    lines += [""]
    lines += _wrap(
        "That affects the law of stream numbers, the law of stream lengths, "
        "the bifurcation and length ratios, drainage density computed from the "
        "mapped network, stream frequency, drainage texture and every ratio "
        "built on them. The pages that would have carried them are left out "
        "rather than filled with the parameters that happen to survive, since "
        "a partial morphometric table reads as a complete one.", 108)
    _text_block(figure, 0.06, 0.88, lines, size=8.5)
    _close(plt, pdf, figure, page)


# --- the report ------------------------------------------------------------


_DEM_NAMES = {"cop30": "Copernicus DEM GLO-30", "cop90": "Copernicus DEM GLO-90",
              "nasadem": "NASADEM", "srtm30": "SRTM 30 m"}


def _elevation_source(elevation) -> str:
    """Name the elevation product, with the cell it was read at."""
    attrs = getattr(elevation, "attrs", {}) or {}
    name = _DEM_NAMES.get(str(attrs.get("basinkit_product", "")), "Copernicus DEM")
    res = attrs.get("basinkit_output_res_m")
    return f"{name}, read at {float(res):.0f} m" if res not in (None, "") else name


def report(basin, path, *, title: str | None = None, dem=None, rivers=None,
           morphometry=None, progress: bool = True) -> str:
    """Write the eight-page report for ``basin`` to ``path``.

    Parameters
    ----------
    path
        Where to write the PDF.
    title
        Printed on the cover. Defaults to the basin's coordinates.
    dem, rivers, morphometry
        Already-computed layers, to avoid fetching or recomputing them.

    Returns
    -------
    str
        The path written.
    """
    _, plt = _matplotlib()
    from matplotlib.backends.backend_pdf import PdfPages

    from .suitability import suitability
    from .terrain import drainage_density

    elevation = basin.dem() if dem is None else dem
    lat, lon = basin.centroid
    title = title or f"Catchment at {lat:.4f}, {lon:.4f}"

    grade = suitability(basin, dem=elevation, support_map=True)

    try:
        density: dict[str, Any] | None = drainage_density(elevation)
    except (MissingDependency, ValueError):
        density = None

    network_reason = None
    if rivers is None:
        try:
            rivers = basin.rivers()
        except Exception as exc:
            network_reason = f"{type(exc).__name__}: {exc}"
            rivers = None
    if morphometry is None and rivers is not None:
        try:
            from .morphometry import morphometry as compute

            morphometry = compute(basin, dem=elevation, rivers=rivers)
        except Exception as exc:
            network_reason = f"{type(exc).__name__}: {exc}"
            morphometry = None

    with PdfPages(str(path)) as pdf:
        _cover(plt, pdf, basin, title, grade, elevation, 1)
        _elevation_page(plt, pdf, basin, elevation, 2)
        _slope_page(plt, pdf, basin, elevation, 3)
        _landform_page(plt, pdf, basin, elevation, 4)
        if morphometry is not None:
            _network_page(plt, pdf, basin, rivers, morphometry, 5)
            _parameter_page(plt, pdf, morphometry, 6)
        else:
            _missing_network_page(plt, pdf, network_reason or "not requested", 5)
            _parameter_page(plt, pdf, {}, 6)
        _suitability_page(plt, pdf, basin, elevation, grade, density, 7)
        _methods_page(plt, pdf, basin, grade, density, 8)

        info = pdf.infodict()
        info["Title"] = title
        info["Creator"] = "basinkit"
        info["Subject"] = (
            f"Catchment analysis, elevation data suitability {grade['grade']}"
        )

    del progress
    return str(path)
