"""Export a basin as a self-contained, interactive 3D web page.

The page draws the catchment as a terrain mesh built from the DEM, drapes a
satellite composite over it, and animates the river network downhill. It is one
HTML file with everything embedded -- imagery, heights, geometry and the
renderer -- so it opens from a memory stick on a laptop with no network, which
is the situation a lot of the people this package is for actually work in.

    basin = bk.Basin.from_point(28.276, 85.378)
    basin.export_3d("rasuwagadhi.html")

Nothing here is a scientific claim. It is a way of looking at the data the rest
of the package fetched, and its one substantive choice -- mapping colour to the
rank of an elevation rather than its value -- exists because a linear ramp
collapses to a single flat tone on any basin whose relief sits mostly in the
upper part of its own range, which is most mountain basins.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import numpy as np

from . import cache

# Pinned. The renderer is embedded in every page this writes, so it must not
# change under a user whose export worked last week.
THREE_JS_URL = "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"

_TEMPLATE = r"""<title>__TITLE__</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Inter+Tight:wght@400;500;600;700&display=swap">
<style>
  :root{
    --ink:#F2F4F5; --ink-2:#A6B2B8; --ink-3:#72808A;
    --panel:rgba(14,20,24,.82); --edge:rgba(255,255,255,.14);
    --accent:#4FC3E8; --warm:#F08A4B;
  }
  *{box-sizing:border-box}
  html,body{height:100%}
  body{margin:0;background:#080C0F;color:var(--ink);
    font-family:"Inter Tight",-apple-system,"Segoe UI",sans-serif;overflow:hidden;}
  #app{position:fixed;inset:0}
  canvas{display:block;width:100%;height:100%}

  .hud{position:fixed;pointer-events:none}
  #title{top:26px;left:0;right:0;text-align:center;}
  #title h1{margin:0;font-size:clamp(20px,3.2vw,30px);font-weight:600;letter-spacing:-.02em;
    text-shadow:0 2px 18px rgba(0,0,0,.8);}
  #title p{margin:7px auto 0;max-width:62ch;font-size:13.5px;line-height:1.5;color:var(--ink-2);
    text-shadow:0 1px 12px rgba(0,0,0,.9);padding:0 20px;}

  #panel{bottom:22px;left:22px;pointer-events:auto;background:var(--panel);
    border:1px solid var(--edge);border-radius:12px;padding:15px 17px;
    backdrop-filter:blur(14px);min-width:236px;}
  .lab{font-family:"IBM Plex Mono",monospace;font-size:10px;letter-spacing:.14em;
    text-transform:uppercase;color:var(--ink-3);margin:0 0 9px;}
  .row{display:flex;gap:7px;margin:0 0 12px;flex-wrap:wrap}
  .row:last-child{margin-bottom:0}
  button.t{font-family:"Inter Tight",sans-serif;font-size:12.5px;color:var(--ink-2);
    background:rgba(255,255,255,.05);border:1px solid var(--edge);border-radius:7px;
    padding:6px 11px;cursor:pointer;transition:all .15s}
  button.t:hover{color:var(--ink);border-color:rgba(255,255,255,.3)}
  button.t[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:#06222C;font-weight:500}
  button.t:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
  input[type=range]{width:100%;accent-color:var(--accent);cursor:pointer}
  .val{font-family:"IBM Plex Mono",monospace;font-size:11px;color:var(--ink-2);
    float:right;font-variant-numeric:tabular-nums}

  #facts{bottom:22px;right:22px;background:var(--panel);border:1px solid var(--edge);
    border-radius:12px;padding:15px 17px;backdrop-filter:blur(14px);text-align:right;}
  #facts dl{margin:0;display:grid;grid-template-columns:auto auto;gap:5px 18px;align-items:baseline}
  #facts dt{font-size:12px;color:var(--ink-3);text-align:left}
  #facts dd{margin:0;font-family:"IBM Plex Mono",monospace;font-size:13px;
    font-variant-numeric:tabular-nums;color:var(--ink)}
  #facts .hi{color:var(--warm)}

  #hint{top:50%;left:0;right:0;text-align:center;font-size:12.5px;color:var(--ink-3);
    transition:opacity .6s;text-shadow:0 1px 10px #000}
  #credit{bottom:6px;left:0;right:0;text-align:center;font-family:"IBM Plex Mono",monospace;
    font-size:10px;color:var(--ink-3);}
  #loading{position:fixed;inset:0;display:grid;place-items:center;background:#080C0F;z-index:50;
    font-family:"IBM Plex Mono",monospace;font-size:12px;color:var(--ink-3);letter-spacing:.1em;
    transition:opacity .5s}
  @media (max-width:720px){
    #panel,#facts{position:fixed;left:12px;right:12px;min-width:0}
    #panel{bottom:auto;top:auto;bottom:150px}
    #facts{bottom:12px;text-align:left}
    #facts dl{justify-content:start}
  }
  @media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style>

<div id="loading">BUILDING TERRAIN</div>
<div id="app"></div>

<div class="hud" id="title">
  <h1>__TITLE__</h1>
  <p>__SUBTITLE__</p>
</div>

<div class="hud" id="hint">drag to orbit</div>

<div class="hud" id="panel">
  <p class="lab">Surface</p>
  <div class="row">
    <button class="t" id="bSat" aria-pressed="true">Satellite</button>
    <button class="t" id="bElev" aria-pressed="false">Elevation</button>
    <button class="t" id="bRiv" aria-pressed="true">Rivers</button>
  </div>
  <p class="lab">Vertical exaggeration <span class="val" id="vx">__EX__×</span></p>
  <div class="row"><input type="range" id="ex" min="0.5" max="4" step="0.1" value="__EX__"></div>
</div>

<div class="hud" id="facts">
__FACTS__
</div>

<div class="hud" id="credit">
  __CREDIT__
</div>

<script>__THREE__</script>
<script id="payload" type="application/json">__PAYLOAD__</script>
<script>
(function(){
  var P = JSON.parse(document.getElementById("payload").textContent);
  var M = P.m, W = M.w, H = M.h;

  // ---- decode the 16-bit height grid ----
  var raw = atob(P.h), n = raw.length / 2;
  var hv = new Uint16Array(n);
  for (var i = 0; i < n; i++) hv[i] = raw.charCodeAt(i*2) | (raw.charCodeAt(i*2+1) << 8);

  // ---- real-world scale, in kilometres ----
  var b = M.bounds, latMid = (b[1] + b[3]) / 2;
  var kmPerLon = 111.32 * Math.cos(latMid * Math.PI / 180);
  var spanX = (b[2] - b[0]) * kmPerLon;
  var spanZ = (b[3] - b[1]) * 110.57;
  var relief = (M.zmax - M.zmin) / 1000;

  function heightAt(col, row){           // km above the basin minimum, or null
    var v = hv[row * W + col];
    return v === 0 ? null : (v - 1) / 65534 * relief;
  }

  var scene = new THREE.Scene();
  scene.background = new THREE.Color(0x080C0F);
  // Fog has to scale with the basin. Fixed distances looked right on a 70 km
  // catchment and swallowed a 500 km one whole, leaving a black screen.
  var SPAN = Math.max(spanX, spanZ);
  scene.fog = new THREE.Fog(0x080C0F, SPAN * 1.0, SPAN * 2.8);

  var camera = new THREE.PerspectiveCamera(42, innerWidth/innerHeight, 0.5, 900);
  var renderer = new THREE.WebGLRenderer({antialias:true});
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.setSize(innerWidth, innerHeight);
  document.getElementById("app").appendChild(renderer.domElement);

  scene.add(new THREE.AmbientLight(0xC6D6E0, 0.98));
  var sun = new THREE.DirectionalLight(0xFFF6EA, 0.92);
  sun.position.set(-60, 90, 55); scene.add(sun);
  var rim = new THREE.DirectionalLight(0x6E8EA2, 0.38);
  rim.position.set(70, 30, -60); scene.add(rim);

  // ---- terrain mesh, with holes outside the basin ----
  var EX = __EX__;
  var pos = [], uv = [], idx = [], map = new Int32Array(W*H).fill(-1), k = 0;
  for (var r = 0; r < H; r++){
    for (var c = 0; c < W; c++){
      var h = heightAt(c, r);
      if (h === null) continue;
      map[r*W + c] = k++;
      pos.push((c/(W-1) - 0.5) * spanX, h, (r/(H-1) - 0.5) * spanZ);
      uv.push(c/(W-1), 1 - r/(H-1));
    }
  }
  for (var r2 = 0; r2 < H-1; r2++){
    for (var c2 = 0; c2 < W-1; c2++){
      var a = map[r2*W+c2], bb = map[r2*W+c2+1],
          cc = map[(r2+1)*W+c2], d = map[(r2+1)*W+c2+1];
      if (a<0||bb<0||cc<0||d<0) continue;      // any missing corner: no quad
      idx.push(a, cc, bb, bb, cc, d);
    }
  }
  var geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute("uv", new THREE.Float32BufferAttribute(uv, 2));
  geo.setIndex(idx);
  geo.computeVertexNormals();

  var basePos = new Float32Array(geo.attributes.position.array);

  var tex = new THREE.Texture();
  var im = new Image();
  im.onload = function(){ tex.image = im; tex.needsUpdate = true; };
  im.src = "data:image/jpeg;base64," + P.t;
  tex.colorSpace = THREE.sRGBEncoding;
  tex.encoding = THREE.sRGBEncoding;

  var HAS_TEXTURE = __HASTEX__;
  var matSat = new THREE.MeshLambertMaterial({map: tex, side: THREE.DoubleSide});

  // Elevation view. Most of this basin sits in the upper part of its own range,
  // so a linear ramp collapses to one pale tone. Mapping colour to each
  // vertex's RANK instead spreads the ramp across the terrain that is actually
  // there, which is what makes the relief legible.
  var nv = pos.length / 3;
  var HB = 512, hist = new Float64Array(HB);
  for (var v0 = 0; v0 < nv; v0++){
    var tt = Math.min(0.999999, Math.max(0, pos[v0*3+1] / relief));
    hist[(tt * HB) | 0]++;
  }
  var cdf = new Float64Array(HB), run = 0;
  for (var i0 = 0; i0 < HB; i0++){ run += hist[i0]; cdf[i0] = run / nv; }

  // Hypsometric tint: valley green through rock tan to snow. A conventional
  // terrain ramp, ordered light-to-dark in luminance, not a rainbow.
  var stops = [[0.11,0.28,0.24],[0.24,0.42,0.30],[0.45,0.50,0.32],
               [0.66,0.60,0.42],[0.82,0.78,0.70],[1.00,1.00,1.00]];
  var col = new Float32Array(nv * 3);
  for (var v2 = 0; v2 < nv; v2++){
    var t0 = Math.min(0.999999, Math.max(0, pos[v2*3+1] / relief));
    var t = cdf[(t0 * HB) | 0];
    var s2 = t * (stops.length - 1), lo = Math.min(stops.length - 2, Math.floor(s2)), f = s2 - lo;
    var A = stops[lo], B = stops[lo+1];
    col[v2*3]   = A[0] + (B[0]-A[0])*f;
    col[v2*3+1] = A[1] + (B[1]-A[1])*f;
    col[v2*3+2] = A[2] + (B[2]-A[2])*f;
  }
  geo.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
  var matElev = new THREE.MeshLambertMaterial({vertexColors:true, side:THREE.DoubleSide});

  var terrain = new THREE.Mesh(geo, matSat);
  scene.add(terrain);

  // ---- rivers, flowing downhill ----
  var riverGroup = new THREE.Group(); scene.add(riverGroup);
  var riverMats = [];
  function sampleH(u, v){
    var c = Math.round(u * (W-1)), r = Math.round((1-v) * (H-1));
    c = Math.min(W-1, Math.max(0, c)); r = Math.min(H-1, Math.max(0, r));
    for (var rad = 0; rad < 6; rad++){
      for (var dr = -rad; dr <= rad; dr++){
        for (var dc = -rad; dc <= rad; dc++){
          var rr = r+dr, ccc = c+dc;
          if (rr < 0 || rr >= H || ccc < 0 || ccc >= W) continue;
          var h = heightAt(ccc, rr);
          if (h !== null) return h;
        }
      }
    }
    return 0;
  }
  P.r.forEach(function(line){
    var pts = line.p.map(function(q){
      var h = sampleH(q[0], q[1]);
      return new THREE.Vector3((q[0]-0.5)*spanX, h, (0.5-q[1])*spanZ);
    });
    if (pts.length < 2) return;
    // Run every reach downhill, so the animation reads as flow, not decoration.
    if (pts[0].y < pts[pts.length-1].y) pts.reverse();
    var g = new THREE.BufferGeometry().setFromPoints(pts);
    var big = line.u > 400;
    var mat = new THREE.LineDashedMaterial({
      color: big ? 0x7FE3FF : 0x4FC3E8,
      dashSize: big ? 0.9 : 0.6, gapSize: big ? 1.5 : 1.1,
      transparent:true, opacity: big ? 0.95 : 0.62,
      linewidth: 1
    });
    var l = new THREE.Line(g, mat);
    l.computeLineDistances();
    l.userData.speed = big ? 3.4 : 2.2;
    riverGroup.add(l); riverMats.push(l);
  });

  function applyExaggeration(e){
    var a = geo.attributes.position.array;
    for (var i2 = 1; i2 < a.length; i2 += 3) a[i2] = basePos[i2] * e;
    geo.attributes.position.needsUpdate = true;
    geo.computeVertexNormals();
    riverGroup.children.forEach(function(l){ l.scale.y = e; });
    riverGroup.position.y = 0.06 * e;
  }
  applyExaggeration(EX);

  // ---- minimal orbit controls ----
  var tgt = new THREE.Vector3(0, relief * EX * 0.28, 0);
  var azim = -0.55, polar = 0.98, dist = Math.max(spanX, spanZ) * 1.32;
  var drag = null;
  function place(){
    var sp = Math.sin(polar);
    camera.position.set(tgt.x + dist*sp*Math.sin(azim),
                        tgt.y + dist*Math.cos(polar),
                        tgt.z + dist*sp*Math.cos(azim));
    camera.lookAt(tgt);
  }
  place();
  var cv = renderer.domElement;
  cv.style.touchAction = "none";
  cv.addEventListener("pointerdown", function(e){
    drag = {x:e.clientX, y:e.clientY, pan:e.button === 2 || e.shiftKey};
    cv.setPointerCapture(e.pointerId); hideHint();
  });
  cv.addEventListener("pointermove", function(e){
    if (!drag) return;
    var dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    drag.x = e.clientX; drag.y = e.clientY;
    if (drag.pan){
      var s = dist * 0.0012;
      tgt.x -= (dx*Math.cos(azim) - dy*Math.sin(azim)) * s;
      tgt.z += (dx*Math.sin(azim) + dy*Math.cos(azim)) * s;
    } else {
      azim -= dx * 0.005;
      polar = Math.min(1.52, Math.max(0.12, polar - dy * 0.005));
    }
    place();
  });
  ["pointerup","pointercancel","pointerleave"].forEach(function(ev){
    cv.addEventListener(ev, function(){ drag = null; });
  });
  cv.addEventListener("contextmenu", function(e){ e.preventDefault(); });
  cv.addEventListener("wheel", function(e){
    e.preventDefault();
    dist = Math.min(400, Math.max(12, dist * (1 + Math.sign(e.deltaY) * 0.09)));
    place(); hideHint();
  }, {passive:false});

  var hint = document.getElementById("hint"), hidden = false;
  function hideHint(){ if (!hidden){ hidden = true; hint.style.opacity = 0; } }
  setTimeout(hideHint, 6000);

  // ---- controls ----
  var bSat = document.getElementById("bSat"), bElev = document.getElementById("bElev"),
      bRiv = document.getElementById("bRiv");
  function surface(sat){
    terrain.material = sat ? matSat : matElev;
    bSat.setAttribute("aria-pressed", sat);
    bElev.setAttribute("aria-pressed", !sat);
  }
  bSat.onclick = function(){ if (HAS_TEXTURE) surface(true); };
  bElev.onclick = function(){ surface(false); };
  // With no imagery there is nothing for the satellite material to draw, and
  // a page that opens on a black mesh reads as broken rather than as empty.
  if (!HAS_TEXTURE){
    surface(false);
    bSat.disabled = true;
    bSat.style.opacity = 0.35;
    bSat.style.cursor = "not-allowed";
    bSat.title = "This page was exported without imagery (texture=None).";
  }
  bRiv.onclick = function(){
    var on = bRiv.getAttribute("aria-pressed") !== "true";
    riverGroup.visible = on; bRiv.setAttribute("aria-pressed", on);
  };
  var ex = document.getElementById("ex"), vx = document.getElementById("vx");
  ex.oninput = function(){
    EX = parseFloat(ex.value); vx.textContent = EX.toFixed(1) + "×";
    tgt.y = relief * EX * 0.28; applyExaggeration(EX); place();
  };

  addEventListener("resize", function(){
    camera.aspect = innerWidth/innerHeight; camera.updateProjectionMatrix();
    renderer.setSize(innerWidth, innerHeight);
  });

  var reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  var t0 = performance.now();
  (function loop(now){
    requestAnimationFrame(loop);
    if (!reduce){
      var t = (now - t0) / 1000;
      for (var i3 = 0; i3 < riverMats.length; i3++){
        riverMats[i3].material.dashOffset = -t * riverMats[i3].userData.speed;
      }
    }
    renderer.render(scene, camera);
  })(t0);

  var ld = document.getElementById("loading");
  ld.style.opacity = 0;
  setTimeout(function(){ ld.remove(); }, 500);
})();
</script>
"""


def _three_js() -> str:
    """The renderer source, cached on first use and reused offline after that."""
    path = cache.download(THREE_JS_URL, namespace="viz3d", progress=False,
                          expected_min_bytes=100_000)
    return path.read_text(encoding="utf-8")


def _heights(dem, mesh_width: int) -> tuple[str, dict]:
    """Pack the DEM into a 16-bit grid, with 0 reserved for 'outside the basin'."""
    z = np.asarray(dem.values, dtype="float32")
    if z.ndim != 2:
        raise ValueError(f"expected a 2-D elevation grid, got shape {z.shape}")
    step = max(1, z.shape[1] // int(mesh_width))
    zs = z[::step, ::step]
    mask = np.isfinite(zs)
    if not mask.any():
        raise ValueError("the elevation grid is empty inside the basin")

    zmin, zmax = float(np.nanmin(zs)), float(np.nanmax(zs))
    span = max(zmax - zmin, 1e-6)
    norm = np.where(mask, (zs - zmin) / span, 0.0)
    packed = np.where(mask, np.clip(norm, 0, 1) * 65534 + 1, 0).astype("<u2")
    meta = {"h": int(zs.shape[0]), "w": int(zs.shape[1]),
            "zmin": zmin, "zmax": zmax}
    return base64.b64encode(packed.tobytes()).decode("ascii"), meta


def _texture(rgb, mask, width: int, high: float, gamma: float, lift: float) -> str:
    """Stretch a reflectance composite into an 8-bit JPEG, as a base64 string."""
    from io import BytesIO

    try:
        from PIL import Image
    except ImportError as exc:                       # pragma: no cover
        raise ImportError(
            "Draping imagery needs Pillow: pip install 'basinkit[viz]'. "
            "For a terrain-only page that needs nothing extra, pass "
            "texture=None."
        ) from exc

    out = np.zeros_like(rgb)
    for i in range(3):
        band = rgb[..., i]
        lo = float(np.nanpercentile(band[mask], 2)) if mask.any() else 0.0
        out[..., i] = np.clip((band - lo) / max(high - lo, 1e-6), 0, 1)
    out = np.where(np.isfinite(out), out, 0.0)

    # Deep valleys in a low-sun scene are genuinely dark; left raw they read as
    # holes punched in the terrain, so the shadows are lifted for display.
    img = lift + (1.0 - lift) * out ** gamma
    img = np.where(mask[..., None], np.clip(img, 0, 1), 0.45)

    buf = BytesIO()
    Image.fromarray((img * 255).astype("uint8"), "RGB").save(
        buf, format="JPEG", quality=87, optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _rivers(gdf, bounds) -> list[dict]:
    """River reaches as polylines in 0-1 basin coordinates."""
    x0, y0, x1, y1 = bounds
    dx, dy = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)
    lines: list[dict] = []
    upland = "UPLAND_SKM" if "UPLAND_SKM" in gdf.columns else None
    for row in gdf.itertuples():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        parts = [geom] if geom.geom_type == "LineString" else list(getattr(geom, "geoms", []))
        for part in parts:
            pts = [[round((px - x0) / dx, 5), round((py - y0) / dy, 5)]
                   for px, py in part.coords]
            if len(pts) > 1:
                lines.append({"p": pts,
                              "u": round(float(getattr(row, upland, 0.0) or 0.0), 1)
                              if upland else 0.0})
    return lines


def _facts_html(facts: dict[str, str] | None) -> str:
    if not facts:
        return ""
    rows = "".join(
        f"    <dt>{k}</dt><dd>{v}</dd>\n" for k, v in facts.items())
    return f"  <dl>\n{rows}  </dl>"


def export_3d(
    basin,
    path: str | Path,
    *,
    texture: str | None = "sentinel2",
    start: str = "2024-10-15",
    end: str = "2024-12-15",
    cloud_cover: float = 15,
    mesh_width: int = 384,
    texture_width: int = 1100,
    rivers: bool = True,
    min_order: int = 2,
    exaggeration: float = 1.6,
    title: str | None = None,
    subtitle: str | None = None,
    facts: dict[str, str] | None = None,
    high: float = 0.62,
    gamma: float = 0.58,
    lift: float = 0.07,
) -> Path:
    """Write ``basin`` to a self-contained interactive 3D page.

    Parameters
    ----------
    texture
        ``'sentinel2'`` drapes a cloud-filtered median composite over the
        terrain; ``None`` ships the elevation tint only, which needs no imagery
        and makes a much smaller file.
    start, end, cloud_cover
        The imagery window. A dry-season window gives the cleanest composite;
        the default is post-monsoon.
    mesh_width
        Columns in the terrain mesh. 384 is about 200k vertices and turns
        smoothly on a laptop; raise it for stills, lower it for large basins.
    high, gamma, lift
        Display stretch for the imagery: white point in reflectance, gamma, and
        how far the shadows are lifted. Only affects how it looks.

    Returns
    -------
    Path
        The file written.
    """
    path = Path(path)
    dem = basin.dem()
    heights, meta = _heights(dem, mesh_width)

    tex = ""
    if texture == "sentinel2":
        s2 = basin.sentinel2(start, end, cloud_cover=cloud_cover,
                             bands=["red", "green", "blue"], composite="median")
        matched = s2.rio.reproject_match(dem)
        step = max(1, dem.rio.shape[1] // int(texture_width))
        stack = np.stack(
            [np.asarray(matched[c].values, dtype="float32")[::step, ::step]
             for c in ("red", "green", "blue")], axis=-1)
        valid = np.isfinite(stack).all(axis=-1)
        tex = _texture(stack, valid, texture_width, high, gamma, lift)
    elif texture is not None:
        raise ValueError(
            f"texture must be 'sentinel2' or None, not {texture!r}")

    lines = _rivers(basin.rivers(min_order=min_order), basin.bounds) if rivers else []

    meta.update({"bounds": list(basin.bounds), "area": round(basin.area_km2, 1)})
    payload: dict[str, Any] = {"h": heights, "t": tex, "r": lines, "m": meta}

    lat, lon = basin.centroid
    default_facts = {
        "Basin area": f"{basin.area_km2:,.0f} km²",
        "Elevation": f"{meta['zmin']:,.0f} - {meta['zmax']:,.0f} m",
        "Relief": f"{meta['zmax'] - meta['zmin']:,.0f} m",
    }
    credit = ("Built with basinkit. Elevation: Copernicus DEM. "
              + ("Imagery: Sentinel-2 L2A median, "
                 f"{start} to {end}. " if tex else "")
              + ("Rivers: HydroRIVERS. " if lines else "")
              + "Run Basin.license_report() for the full attribution.")

    html = (_TEMPLATE
            .replace("__TITLE__", title or f"Basin at {lat:.3f}, {lon:.3f}")
            .replace("__SUBTITLE__", subtitle or
                     f"{basin.area_km2:,.0f} km² draining to "
                     f"{basin.provenance.get('outlet', ['?', '?'])[0]:.4g}, "
                     f"{basin.provenance.get('outlet', ['?', '?'])[1]:.4g}. "
                     "Drag to orbit, scroll to zoom.")
            .replace("__FACTS__", _facts_html(facts if facts is not None else default_facts))
            .replace("__CREDIT__", credit)
            .replace("__EX__", f"{float(exaggeration):g}")
            .replace("__HASTEX__", "true" if tex else "false")
            .replace("__PAYLOAD__", json.dumps(payload).replace("</", "<\\/"))
            # Last, because three.js contains "__THREE__" in its own devtools
            # hook -- and a later release could contain one of our other tokens.
            .replace("__THREE__", _three_js()))

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path
