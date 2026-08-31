"""Compose the wordmark: the drawn b, then a-s-i-n-k-i-t as glyph outlines.

Glyph outlines rather than live text, because an SVG shown through <img>
cannot load a web font -- live text would render in whatever face the viewer
happens to have. Outlines come straight from the Archivo TTF (SIL OFL 1.1) via
fontTools, so the metrics are the font's own rather than eyeballed.

The two i tittles are recoloured as gauge points, which is the same object as
the outlet at the foot of the b.
"""
import pathlib
import re

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

FONT = TTFont("/tmp/archivo.ttf")
GLYPHS = FONT.getGlyphSet()
CMAP = FONT.getBestCmap()
HMTX = FONT["hmtx"]
UPM = FONT["head"].unitsPerEm            # 1000
ASCENDER_INK = 723                       # ink top of 'b' above the baseline
X_HEIGHT = FONT["OS/2"].sxHeight         # 526

# --- the drawn b, in its own 200-unit space -------------------------------
MARK = pathlib.Path("logo-animated.svg").read_text()
MARK_STEM_X, MARK_BASE = 62.0, 172.0
MARK_INK_LEFT = MARK_STEM_X - 13.5          # half the stem's stroke width
MARK_INK_TOP = 34.0 - 13.5                  # ascender top, less the round cap
MARK_INK_RIGHT = 170.0 + 9             # bowl right, plus half its stroke

K = ASCENDER_INK / (MARK_BASE - MARK_INK_TOP)      # mark units -> font units
LSB = 64                                            # match the font's own b
mark_ink_w = (MARK_INK_RIGHT - MARK_INK_LEFT) * K
B_ADVANCE = LSB + mark_ink_w + 38                   # 38 = the font b's rsb


def glyph_path(char: str) -> tuple[str, int]:
    name = CMAP[ord(char)]
    pen = SVGPathPen(GLYPHS)
    GLYPHS[name].draw(pen)
    return pen.getCommands(), HMTX[name][0]


def contours(char: str):
    """Yield (path_d, bounds) per contour.

    Splitting the path string on "M" and assuming numbers alternate x,y is
    wrong: SVGPathPen emits H and V commands, which carry a single coordinate.
    Replaying recorded contours through real pens avoids parsing entirely.
    """
    name = CMAP[ord(char)]
    recorder = RecordingPen()
    GLYPHS[name].draw(recorder)

    groups, current = [], []
    for op, args in recorder.value:
        if op == "moveTo" and current:
            groups.append(current)
            current = []
        current.append((op, args))
    if current:
        groups.append(current)

    for group in groups:
        svg, bounds = SVGPathPen(GLYPHS), BoundsPen(GLYPHS)
        for op, args in group:
            getattr(svg, op)(*args)
            getattr(bounds, op)(*args)
        yield svg.getCommands(), bounds.bounds


def build(palette_css: str) -> str:
    body = MARK[MARK.index("</style>") + 8: MARK.rindex("</svg>")].strip()
    style = re.search(r"<style>(.*?)</style>", MARK, re.S).group(1)
    style = re.sub(r"\s*:root \{[^}]*\}", "", style, count=1)
    style = re.sub(r"\s*@media \(prefers-color-scheme: dark\) \{.*?\n  \}", "",
                   style, count=1, flags=re.S)

    letters, tittles = [], []
    x = B_ADVANCE
    tittle_colours = ["--trib-2", "--trib-4"]
    for char in "asinkit":
        d, advance = glyph_path(char)
        if char == "i":
            for sub_d, bounds in contours(char):
                is_tittle = bounds is not None and bounds[1] > X_HEIGHT + 30
                if is_tittle:
                    tittles.append((sub_d, x, tittle_colours[len(tittles)], bounds))
                else:
                    letters.append((sub_d, x, None, bounds))
        else:
            letters.append((d, x, None, None))
        x += advance
    total_advance = x

    def emit(items, cls):
        out = []
        for d, tx, colour, bounds in items:
            style = ' style="fill: var(%s)"' % colour if colour else ""
            if cls == "tittle" and bounds:
                # Archivo's tittle is a rectangle. Rounding it turns the two i
                # dots into gauge points -- the same object as the outlet at
                # the foot of the b.
                x0, y0, x1, y1 = bounds
                cx, cy = (x0 + x1) / 2 + tx, (y0 + y1) / 2
                r = min(x1 - x0, y1 - y0) / 2
                out.append(f'<circle class="{cls}"{style} cx="{cx:.0f}" '
                           f'cy="{cy:.0f}" r="{r:.0f}"/>')
            else:
                out.append(f'<path class="{cls}"{style} '
                           f'transform="translate({tx:.0f} 0)" d="{d}"/>')
        return "\n".join(out)

    # font units -> SVG: y flips, baseline sits at BASELINE
    BASELINE, PAD = 760, 40
    height = 1000
    width = total_advance + PAD * 2

    mark_scale = K
    mark_tx = PAD + LSB - MARK_INK_LEFT * mark_scale
    mark_ty = BASELINE - MARK_BASE * mark_scale

    return f'''<svg xmlns="http://www.w3.org/2000/svg"
     viewBox="0 0 {width:.0f} {height}" width="{width:.0f}" height="{height}"
     role="img" aria-labelledby="wm-title wm-desc">
<title id="wm-title">basinkit</title>
<desc id="wm-desc">The basinkit wordmark. The b is drawn as a river basin: its stem is the trunk river, its bowl is the divide, four coloured tributaries feed it from inside, and the two i tittles are gauge points.</desc>
<style>
{palette_css}
{style}
  .glyph {{ fill: var(--word); }}
  .tittle {{ fill: var(--word); }}
</style>
<g transform="translate({mark_tx:.1f} {mark_ty:.1f}) scale({mark_scale:.4f})">
{body}
</g>
<g transform="translate({PAD} {BASELINE}) scale(1 -1)">
{emit(letters, "glyph")}
{emit(tittles, "tittle")}
</g>
</svg>
'''


LIGHT = ("  :root { --divide: #B79A6B; --trib-1: #159C7A; --trib-2: #2A78D6; "
         "--trib-3: #6B3FA0; --trib-4: #E4611F; --stem: #0B6FA4; "
         "--ground: #FFFFFF; --tint: #0B6FA4; --word: #12191C; }")
DARK = ("  :root { --divide: #CFB27F; --trib-1: #2ECC9A; --trib-2: #5FA3EE; "
        "--trib-3: #A98BE8; --trib-4: #F4834B; --stem: #58AEDC; "
        "--ground: #10171A; --tint: #58AEDC; --word: #E8EEEC; }")
AUTO = LIGHT + "\n  @media (prefers-color-scheme: dark) {\n  " + DARK + "\n  }"

pathlib.Path("logo-wordmark.svg").write_text(build(AUTO))
pathlib.Path("logo-wordmark-light.svg").write_text(build(LIGHT))
pathlib.Path("logo-wordmark-dark.svg").write_text(build(DARK))
print(f"wordmark written  |  b advance {B_ADVANCE:.0f} vs font's 608  |  scale {K:.3f}")
