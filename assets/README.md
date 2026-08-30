# Logo

**The mark is the letter.** The `b` of basinkit is drawn as a river basin: its
stem is the trunk river running down to an outlet, its bowl is the catchment
divide, and four coloured tributaries feed it from inside the counter. The two
`i` tittles become gauge points — the same object as the outlet at the foot of
the `b`. They are deliberately unequal: a small one on the first `i` and a large
one on the second, standing on a common baseline, so the pair reads left to
right the way a river actually grows — a headwater gauge upstream, a main-stem
gauge downstream.

So the logo is made *of* the name rather than sitting beside it, and the icon
and the first letter of the wordmark are the same drawing.

The colour carries the idea rather than decorating it: four tributaries, four
hues, one river. Many open data sources, one basin.

| file | use |
|---|---|
| `logo-animated.svg` | the `b`, animated. Docs, site, anywhere it has room |
| `logo.svg` | the same letter, finished, no animation |
| `logo-wordmark.svg` | the full name, follows the viewer's colour scheme |
| `logo-wordmark-light.svg` / `-dark.svg` | pinned, for GitHub's `<picture>` |
| `logo-512/256/128/64/32.png` | raster, transparent background |
| `icon.png` | 64 px, the QGIS plugin icon |

## Notes

**The animation draws the letter in order** — stem, bowl, tributaries, then the
outlet pops and ripples. Every stroke carries `pathLength="100"`, so one set of
keyframes draws paths of very different real lengths at the same apparent
speed.

**It respects `prefers-reduced-motion`.** Anyone who has asked for less motion
gets the finished letter immediately, with no animation at all.

**The lettering is glyph outlines, not text.** An SVG shown through `<img>`
cannot load a web font, so live text would render in whatever face the viewer
happens to have. The outlines come from Archivo (SIL OFL 1.1), pulled straight
from the TTF with `fontTools` — so the wordmark uses the font's own metrics
rather than eyeballed positions.

**The drawn `b` is matched to the font.** Its ink height maps to Archivo's
ascender (723 units), the bowl top to its x-height (526), and the stem weight
to the `i` stem (139 units). Getting the stem wrong by a third is instantly
visible next to real letters, and was: the first pass drew it at 88.

**Use the pinned variants on GitHub.** The theme-aware file keys off
`prefers-color-scheme`, which is the *browser's* setting — a reader running
GitHub in dark mode on a light OS would get near-black lettering on a dark
ground. GitHub's documented answer is `<picture>`:

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/logo-wordmark-dark.svg">
  <img src="assets/logo-wordmark-light.svg" alt="basinkit" width="420">
</picture>
```

## Colours

| role | light | dark |
|---|---|---|
| divide (the bowl) | `#B79A6B` | `#CFB27F` |
| tributary 1 | `#159C7A` | `#2ECC9A` |
| tributary 2 | `#2A78D6` | `#5FA3EE` |
| tributary 3 | `#6B3FA0` | `#A98BE8` |
| tributary 4 | `#E4611F` | `#F4834B` |
| trunk, outlet | `#0B6FA4` | `#58AEDC` |
| lettering | `#12191C` | `#E8EEEC` |

## Rebuilding

```bash
python build/build_mark.py       # the b, animated and static
python build/build_wordmark.py   # the full name, three colour modes
python build/build_png.py        # rasters and the QGIS icon
```
