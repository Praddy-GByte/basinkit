"""Render a :class:`River` as one self-contained HTML page.

The page is written to be read by someone who is not going to open Python: the
river's identity at the top, the long profile as a drawing, the confluences
that actually change the flow, and the morphometry underneath for anyone who
came for that. It embeds its own styling and draws its own chart, so the file
opens from a memory stick with no network and no libraries.

Every number carries the caveat it needs beside it rather than in a footnote,
because a page like this gets screenshotted and the caveat has to travel with
the figure.
"""

from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path
from typing import Any

_CSS = """
:root{--paper:#F6F7F5;--card:#fff;--ink:#14201C;--soft:#4C5C56;--faint:#7C8C86;
--rule:#D8E0DC;--hair:#E9EEEC;--accent:#0E6B57;--accent-soft:#DCEDE7;--water:#2E7FA8}
@media(prefers-color-scheme:dark){:root:not([data-theme="light"]){
--paper:#0B1210;--card:#131C19;--ink:#E5EDEA;--soft:#98A9A3;--faint:#6F827B;
--rule:#202C28;--hair:#1A2421;--accent:#4FBF9E;--accent-soft:#102A24;--water:#5AA9D0}}
:root[data-theme="dark"]{--paper:#0B1210;--card:#131C19;--ink:#E5EDEA;--soft:#98A9A3;
--faint:#6F827B;--rule:#202C28;--hair:#1A2421;--accent:#4FBF9E;--accent-soft:#102A24;--water:#5AA9D0}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
font:400 16px/1.6 "Iowan Old Style",Palatino,Georgia,serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:880px;margin:0 auto;padding:0 22px 80px}
header{padding:48px 0 20px;border-bottom:1px solid var(--ink)}
.eyebrow{font:600 11px/1 ui-monospace,Menlo,monospace;letter-spacing:.16em;
text-transform:uppercase;color:var(--faint);margin:0 0 16px}
h1{font:700 clamp(30px,5vw,44px)/1.05 "Helvetica Neue",Arial,sans-serif;
letter-spacing:-.02em;margin:0 0 12px}
.stand{font-size:18px;color:var(--soft);margin:0;max-width:56ch}
h2{font:600 11px/1 ui-monospace,Menlo,monospace;letter-spacing:.15em;text-transform:uppercase;
color:var(--accent);margin:44px 0 10px}
h3{font:600 22px/1.25 "Helvetica Neue",Arial,sans-serif;margin:0 0 12px}
p{margin:0 0 14px;max-width:64ch}
.note{font-size:14px;color:var(--soft);max-width:64ch}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));gap:1px;
background:var(--card);border:1px solid var(--hair);border-radius:4px;margin:0 0 20px;
overflow:hidden}
.cell{background:var(--card);padding:14px 16px;outline:1px solid var(--hair)}
.k{font:600 10px/1.3 ui-monospace,Menlo,monospace;letter-spacing:.09em;text-transform:uppercase;
color:var(--faint);margin:0 0 6px}
.v{font:600 22px/1.1 "Helvetica Neue",Arial,sans-serif;margin:0;font-variant-numeric:tabular-nums}
.u{font-size:13px;color:var(--soft);font-weight:400}
.s{font-size:12.5px;color:var(--soft);margin:6px 0 0;line-height:1.45}
figure{margin:0 0 8px}
figcaption{font-size:13px;color:var(--soft);margin:8px 0 0;max-width:60ch}
svg{display:block;width:100%;height:auto}
.scroll{overflow-x:auto;border:1px solid var(--rule);border-radius:4px;margin:0 0 8px}
table{border-collapse:collapse;width:100%;min-width:540px;font-size:14px;background:var(--card)}
th{font:600 10px/1.2 ui-monospace,Menlo,monospace;letter-spacing:.09em;text-transform:uppercase;
text-align:left;color:var(--faint);padding:10px 13px;background:var(--paper);
border-bottom:1px solid var(--rule);white-space:nowrap}
td{padding:9px 13px;border-bottom:1px solid var(--hair);color:var(--soft);
font-variant-numeric:tabular-nums;white-space:nowrap}
td.nm{color:var(--ink);font-weight:600}
tr:last-child td{border-bottom:none}
.pill{display:inline-block;background:var(--accent-soft);color:var(--accent);
border-radius:3px;padding:3px 8px;font:600 11px/1 ui-monospace,monospace;letter-spacing:.04em}
footer{margin:46px 0 0;padding:18px 0 0;border-top:1px solid var(--rule);
font:400 12.5px/1.6 ui-monospace,Menlo,monospace;color:var(--faint);max-width:72ch}
@media print{body{background:#fff}.wrap{max-width:none}}
"""


def _fmt(v: Any, dp: int = 1, dash: str = "not available") -> str:
    if v is None:
        return dash
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (int, float)):
        return f"{v:,.{dp}f}".rstrip("0").rstrip(".") if dp else f"{v:,.0f}"
    return html.escape(str(v))


def _cell(k: str, v: str, unit: str = "", note: str = "") -> str:
    u = f' <span class="u">{html.escape(unit)}</span>' if unit else ""
    n = f'<p class="s">{html.escape(note)}</p>' if note else ""
    return (f'<div class="cell"><p class="k">{html.escape(k)}</p>'
            f'<p class="v">{v}{u}</p>{n}</div>')


def _profile_svg(prof, river) -> str:
    """The long profile: bed elevation against distance, with confluences."""
    if prof is None or len(prof) < 2:
        return '<p class="note">No DEM was available, so the long profile could not be drawn.</p>'

    xs = prof["distance_km"].tolist()
    ys = prof["elevation_m"].tolist()
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    if x1 <= x0:
        return ""
    if y1 - y0 < 1:
        y1 = y0 + 1

    W, H = 700, 260
    L, R, T, B = 62, 16, 18, 40
    pw, ph = W - L - R, H - T - B

    def px(x): return L + (x - x0) / (x1 - x0) * pw
    def py(y): return T + (1 - (y - y0) / (y1 - y0)) * ph

    pts = " ".join(f"{px(x):.1f},{py(y):.1f}" for x, y in zip(xs, ys, strict=False))
    area = f"{L},{T + ph} {pts} {L + pw},{T + ph}"

    # y ticks at round elevations, x ticks at round distances
    def ticks(lo, hi, target=4):
        span = hi - lo
        step = 10 ** int(round(__import__("math").log10(span / target)))
        for m in (1, 2, 2.5, 5, 10):
            if span / (step * m) <= target * 1.4:
                step *= m
                break
        t, out = (int(lo / step) + 1) * step, []
        while t < hi:
            out.append(t)
            t += step
        return out

    g = []
    for t in ticks(y0, y1):
        g.append(f'<line x1="{L}" y1="{py(t):.1f}" x2="{L + pw}" y2="{py(t):.1f}" '
                 f'stroke="var(--hair)" stroke-width="1"/>')
        g.append(f'<text x="{L - 8}" y="{py(t) + 4:.1f}" text-anchor="end" '
                 f'fill="var(--faint)" font-size="11" '
                 f'font-family="ui-monospace,monospace">{t:,.0f}</text>')
    for t in ticks(x0, x1):
        g.append(f'<text x="{px(t):.1f}" y="{T + ph + 18}" text-anchor="middle" '
                 f'fill="var(--faint)" font-size="11" '
                 f'font-family="ui-monospace,monospace">{t:,.0f}</text>')

    # the confluences that carry real water
    big = sorted((c for c in river.tributaries if c.share_of_flow >= 0.15),
                 key=lambda c: -c.share_of_flow)[:6]
    for c in big:
        if not (x0 <= c.distance_from_source_km <= x1):
            continue
        x = px(c.distance_from_source_km)
        g.append(f'<line x1="{x:.1f}" y1="{T}" x2="{x:.1f}" y2="{T + ph}" '
                 f'stroke="var(--water)" stroke-width="1" stroke-dasharray="3 3" '
                 f'stroke-opacity="0.75"/>')
        g.append(f'<circle cx="{x:.1f}" cy="{T + ph:.1f}" r="3" fill="var(--water)"/>')

    return f"""<svg viewBox="0 0 {W} {H}" role="img"
 aria-label="Long profile of the river bed from source to mouth">
<polygon points="{area}" fill="var(--accent)" fill-opacity="0.10"/>
{''.join(g)}
<polyline points="{pts}" fill="none" stroke="var(--accent)" stroke-width="1.8"
 stroke-linejoin="round"/>
<text x="{L}" y="{T - 4}" fill="var(--faint)" font-size="11"
 font-family="ui-monospace,monospace">ELEVATION (m)</text>
<text x="{L + pw}" y="{H - 6}" text-anchor="end" fill="var(--faint)" font-size="11"
 font-family="ui-monospace,monospace">DISTANCE FROM SOURCE (km)</text>
</svg>"""


def _tributary_rows(river, limit: int = 15) -> str:
    trib = sorted(river.tributaries, key=lambda c: -c.discharge_cms)[:limit]
    if not trib:
        return ""
    rows = []
    for c in trib:
        rows.append(
            f"<tr><td class='nm'>{c.distance_from_source_km:,.1f}</td>"
            f"<td>{c.order}</td>"
            f"<td>{c.upland_km2:,.0f}</td>"
            f"<td>{c.discharge_cms:,.3f}</td>"
            f"<td>{c.share_of_flow * 100:,.0f}%</td>"
            f"<td>{c.lat:.4f}, {c.lon:.4f}</td></tr>")
    return f"""<div class="scroll"><table>
<thead><tr><th>km from source</th><th>Order</th><th>Upstream km2</th>
<th>Mean flow m3/s</th><th>Share of stem</th><th>Confluence</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>"""


def _morphometry_block(basin) -> str:
    try:
        m = basin.morphometry()
    except Exception as exc:                                  # pragma: no cover
        return f'<p class="note">Morphometry could not be computed: {html.escape(str(exc))}</p>'

    warn = ""
    for w in m.get("warnings", []):
        tone = "var(--accent)" if w["severity"] != "impossible" else "#B4472F"
        warn += (f'<p class="note" style="border-left:2px solid {tone};'
                 f'padding-left:12px"><strong>{html.escape(w["severity"])}</strong> '
                 f'{html.escape(w["message"])}</p>')

    rows = []
    for row in m.get("network", []):
        rows.append(
            f"<tr><td class='nm'>{row['order']}</td><td>{row['streams']:,}</td>"
            f"<td>{row['reaches']:,}</td><td>{row['total_length_km']:,.1f}</td>"
            f"<td>{row.get('bifurcation_ratio') or ''}</td></tr>")
    net = f"""<div class="scroll"><table>
<thead><tr><th>Strahler order</th><th>Streams</th><th>Dataset reaches</th>
<th>Total length km</th><th>Bifurcation ratio</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>"""

    lin, ar, rel = m.get("linear", {}), m.get("areal", {}), m.get("relief", {})
    cells = "".join([
        _cell("Drainage density", _fmt(ar.get("drainage_density_km_per_km2"), 3), "km/km2"),
        _cell("Stream frequency", _fmt(ar.get("stream_frequency_per_km2"), 3), "per km2"),
        _cell("Mean bifurcation ratio", _fmt(lin.get("mean_bifurcation_ratio"), 2)),
        _cell("Elongation ratio", _fmt(ar.get("elongation_ratio"), 3)),
        _cell("Circularity ratio", _fmt(ar.get("circularity_ratio"), 3)),
        _cell("Hypsometric integral", _fmt(rel.get("hypsometric_integral"), 3)),
    ])
    return (f'<div class="grid">{cells}</div>{warn}{net}'
            f'<p class="note">Streams are counted as Strahler streams, not as the '
            f'reaches the river dataset splits them into. The two columns above '
            f'are shown side by side because counting the second inflates every '
            f'order above the first.</p>')


def _landcover_block(basin) -> str:
    try:
        t = basin.terrain_stats()
    except Exception:                                          # pragma: no cover
        return ""
    cells = "".join([
        _cell("Mean elevation", _fmt(t.get("elev_mean_m"), 0), "m"),
        _cell("Basin relief", _fmt(t.get("relief_m"), 0), "m"),
        _cell("Mean slope", _fmt(t.get("slope_mean_deg"), 2), "degrees"),
        _cell("Bounding-box efficiency", _fmt(basin.bbox_efficiency * 100, 0), "%",
              "share of the basin's bounding box the basin actually fills"),
    ])
    return f'<div class="grid">{cells}</div>'


def write_report(river, path: str | Path, *, title: str | None = None,
                 morphometry: bool = True, landcover: bool = True) -> str:
    """Write the river's profile to ``path`` and return the path written."""
    p = Path(path)
    f = river.facts()
    name = title or f"The river above {f['mouth_lat_lon'][0]:.4f}, {f['mouth_lat_lon'][1]:.4f}"

    sea = (f'{f["distance_to_sea_km"]:,.0f} km still to run to the sea'
           if f["distance_to_sea_km"] else "endorheic: it does not reach the sea")
    if f["endorheic"]:
        sea = "endorheic: this river system does not reach the sea"

    top = "".join([
        _cell("Course length", _fmt(f["length_km"], 1), "km",
              "traced from the outlet upstream, taking the larger catchment at "
              "each junction"),
        _cell("Strahler order", _fmt(f["strahler_order"], 0)),
        _cell("Mean discharge", _fmt(f["mean_discharge_cms"], 2), "m3/s",
              "long-term natural average from a global model, not a gauge, and "
              "it does not know about dams"),
        _cell("Basin area", _fmt(f["basin_area_km2"], 0), "km2"),
        _cell("Fall of the bed", _fmt(f["relief_m"], 0), "m",
              "source elevation minus mouth elevation, read along the channel"),
        _cell("Gradient", _fmt(f["gradient_m_per_km"], 3), "m/km",
              "the bed's own slope, not basin relief divided by length"),
        _cell("Sinuosity", _fmt(f["sinuosity"], 3),
              note="course length over the straight line from source to mouth"),
        _cell("Tributaries", _fmt(f["tributaries_counted"], 0),
              note="reaches joining the main stem directly"),
    ])

    src = f'{f["source_lat_lon"][0]:.4f}, {f["source_lat_lon"][1]:.4f}'
    mth = f'{f["mouth_lat_lon"][0]:.4f}, {f["mouth_lat_lon"][1]:.4f}'
    ends = "".join([
        _cell("Rises at", src, note=f'{_fmt(f["source_elevation_m"], 0)} m, at the '
                                   f'top of the mapped network'),
        _cell("Arrives at", mth, note=f'{_fmt(f["mouth_elevation_m"], 0)} m, the '
                                      f'point this profile was taken for'),
        _cell("Downstream", sea, ""),
    ])

    prof = river.profile()
    chart = _profile_svg(prof, river)
    trib = _tributary_rows(river)
    morph = _morphometry_block(river.basin) if morphometry else ""
    land = _landcover_block(river.basin) if landcover else ""
    prov = json.dumps(getattr(river.basin, "provenance", {}) or {}, default=str)

    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(name)}</title>
<style>{_CSS}</style></head><body><div class="wrap">

<header>
<p class="eyebrow">River profile &middot; basinkit &middot; {date.today().isoformat()}</p>
<h1>{html.escape(name)}</h1>
<p class="stand">Traced from the outlet upstream through the HydroRIVERS network,
with the bed read from the DEM along the channel. Everything below describes the
river <em>above</em> this point.</p>
</header>

<h2>The river</h2>
<div class="grid">{top}</div>

<h2>Where it runs</h2>
<div class="grid">{ends}</div>

<h2>Long profile</h2>
<figure>{chart}
<figcaption>The bed from source to mouth. The profile is sampled along the
channel and made monotonic downstream, so a centreline crossing a bank cannot
invent a fall. Dashed lines mark confluences bringing at least 15 per cent of
the main stem's flow.</figcaption></figure>

<h2>What joins it</h2>
{trib or '<p class="note">No tributaries were found in the mapped network.</p>'}
<p class="note">Ordered by mean flow. HydroRIVERS maps reaches down to about
10 km2 of catchment, so smaller headwater tributaries are not in this list.</p>

{'<h2>The basin</h2>' + land if land else ''}

{'<h2>Morphometry</h2>' + morph if morph else ''}

<footer>
Delineation and network: HydroSHEDS HydroRIVERS and HydroBASINS (CC BY 4.0).
Elevation: Copernicus DEM. Discharge is HydroRIVERS' modelled long-term natural
average and is not a gauge reading.<br>
Provenance: {html.escape(prov)}
</footer>

</div></body></html>"""

    p.write_text(doc, encoding="utf8")
    return str(p)
