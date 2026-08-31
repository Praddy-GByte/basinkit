"""The mark is the letter b of basinkit.

Its stem is the trunk river running down to an outlet; its bowl is the basin
divide; the counter holds the tributaries. Icon and first letter of the
wordmark are the same object, so the logo is made of the name rather than
sitting beside it.
"""
import pathlib
import re

PALETTE = """  :root {
    --divide: #B79A6B; --trib-1: #159C7A; --trib-2: #2A78D6;
    --trib-3: #6B3FA0; --trib-4: #E4611F; --stem: #0B6FA4;
    --ground: #FFFFFF; --tint: #0B6FA4; --word: #12191C;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --divide: #CFB27F; --trib-1: #2ECC9A; --trib-2: #5FA3EE;
      --trib-3: #A98BE8; --trib-4: #F4834B; --stem: #58AEDC;
      --ground: #10171A; --tint: #58AEDC; --word: #E8EEEC;
    }
  }"""

STEM_X, ASC, BASE = 62.0, 34.0, 172.0
BOWL_TOP, BOWL_RIGHT = 66.0, 170.0

# The counter: the enclosed area of the b, which is also the catchment.
COUNTER = (f"M{STEM_X} {BOWL_TOP} C116 42,{BOWL_RIGHT} 70,{BOWL_RIGHT} 120 "
           f"C{BOWL_RIGHT} 166,120 {BASE},{STEM_X} {BASE} Z")

PARTS = {
    "stem": (f"M{STEM_X} {ASC} C64 78,60 126,{STEM_X} {BASE}", "--stem", 27, 1.1, 0.0),
    "bowl": (f"M{STEM_X} {BOWL_TOP} C116 42,{BOWL_RIGHT} 70,{BOWL_RIGHT} 120 "
             f"C{BOWL_RIGHT} 166,120 {BASE},{STEM_X} {BASE}", "--divide", 18, 1.3, 0.55),
    # Tributaries live inside the counter and meet the stem at four heights.
    # The orange one joins the blue rather than the stem: a second-order
    # tributary reads as a river network, four spokes read as a barcode.
    "t2": ("M144 88 C122 95,94 100,78 104", "--trib-2", 9, 0.9, 1.45),
    "t4": ("M130 68 C124 78,116 86,110 96", "--trib-4", 6.5, 0.7, 1.70),
    "t3": ("M156 124 C130 128,98 130,78 130", "--trib-3", 9, 0.9, 1.60),
    "t1": ("M138 154 C114 157,92 158,78 156", "--trib-1", 9, 0.9, 1.75),
}
ORDER = ["stem", "bowl", "t2", "t3", "t4", "t1"]
OUTLET = (STEM_X, BASE, 15)


def build(animated: bool) -> str:
    draw_cls = " draw" if animated else ""
    rules = []
    for key in ORDER:
        _, colour, width, dur, delay = PARTS[key]
        rule = f"  #{key} {{ stroke: var({colour}); stroke-width: {width};"
        if animated:
            rule += f" animation: draw {dur}s ease-out {delay}s forwards;"
        rules.append(rule + " }")

    counter_rule = (
        "  #counter { fill: var(--tint); opacity: 0;\n"
        "             animation: soak 1.2s ease-out 1.6s forwards; }"
        if animated else
        "  #counter { fill: var(--tint); opacity: .10; }")

    origin = f"{OUTLET[0]:g}px {OUTLET[1]:g}px"
    outlet_rule = (
        "  #outlet { fill: var(--stem); stroke: var(--ground); stroke-width: 5;\n"
        f"            transform-origin: {origin}; opacity: 0;\n"
        "            animation: pop .5s cubic-bezier(.34,1.56,.64,1) 2.45s forwards,\n"
        "                       beat 6s ease-in-out 2.95s infinite; }"
        if animated else
        "  #outlet { fill: var(--stem); stroke: var(--ground); stroke-width: 5; }")

    motion = """
  @keyframes draw   { to { stroke-dashoffset: 0; } }
  @keyframes soak   { to { opacity: .10; } }
  @keyframes pop    { from { opacity: 0; transform: scale(.2); }
                      to   { opacity: 1; transform: scale(1); } }
  @keyframes beat   { 0%, 88%, 100% { transform: scale(1); }
                      94%           { transform: scale(1.18); } }
  @keyframes ripple { 0% { opacity: .45; transform: scale(.5); }
                      100% { opacity: 0; transform: scale(2.4); } }
  .ripple { fill: none; stroke: var(--stem); stroke-width: 4; opacity: 0;
            transform-origin: __ORIGIN__; }
  #r1 { animation: ripple 2.8s ease-out 2.85s infinite; }
  #r2 { animation: ripple 2.8s ease-out 3.85s infinite; }

  /* Anyone who asked for less motion gets the finished letter immediately. */
  @media (prefers-reduced-motion: reduce) {
    .draw { stroke-dashoffset: 0; }
    #counter { opacity: .10; }
    #outlet { opacity: 1; }
    .ripple { display: none; }
    #stem, #bowl, #t1, #t2, #t3, #t4, #counter, #outlet { animation: none; }
  }""".replace("__ORIGIN__", origin) if animated else ""

    ripples = (f'<circle id="r1" class="ripple" cx="{OUTLET[0]}" cy="{OUTLET[1]}" r="{OUTLET[2]}"/>\n'
               f'<circle id="r2" class="ripple" cx="{OUTLET[0]}" cy="{OUTLET[1]}" r="{OUTLET[2]}"/>\n'
               if animated else "")

    body = "\n".join(
        f'<path id="{k}" class="ink{draw_cls}" pathLength="100" d="{PARTS[k][0]}"/>'
        for k in ORDER)

    dash = "  .draw { stroke-dasharray: 100; stroke-dashoffset: 100; }\n" if animated else ""

    return f'''<style>
{PALETTE}
  .ink {{ fill: none; stroke-linecap: round; stroke-linejoin: round; }}
{dash}{chr(10).join(rules)}
{counter_rule}
{outlet_rule}{motion}
</style>
<path id="counter" d="{COUNTER}"/>
{body}
{ripples}<circle id="outlet" cx="{OUTLET[0]}" cy="{OUTLET[1]}" r="{OUTLET[2]}"/>'''


for name, animated in (("logo-animated.svg", True), ("logo.svg", False)):
    pathlib.Path(name).write_text(
        f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="200" height="200"
     role="img" aria-labelledby="m-title m-desc">
<title id="m-title">basinkit</title>
<desc id="m-desc">The letter b drawn as a river basin: the stem is the trunk river, the bowl is the divide, and four coloured tributaries feed it from inside.</desc>
{build(animated)}
</svg>
''')
print("lettermark written")
