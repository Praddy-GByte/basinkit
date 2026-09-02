"""Put the generated drainage network into every logo file."""
import json, re, pathlib
from collections import OrderedDict

A = pathlib.Path(__file__).resolve().parent.parent   # <repo>/assets
VAR = {"--stem":"s", "--trib-1":"a", "--trib-2":"b", "--trib-3":"c", "--trib-4":"d"}
DESC_OLD = ("The letter b drawn as a river basin: the stem is the trunk river, the bowl "
            "is the divide, and four coloured tributaries feed it from inside.")
DESC_NEW = ("The letter b drawn as a river basin: the bowl is the drainage divide, a "
            "dendritic stream network fills it, and every branch drains to the single "
            "outlet where the stem ends.")

def groups_for(path):
    net = json.load(open(path))
    net.sort(key=lambda r: (r[0].startswith('trunk'), r[2]))
    g = OrderedDict()
    for _tag, colour, w, d in net:
        g.setdefault((colour, w), []).append(d)
    return g

def patch(fn, netfile, animate):
    src = A.joinpath(fn).read_text()
    g = groups_for(netfile)
    widest = max(w for _c, w in g)
    rules, body = [], []
    for i, ((colour, w), ds) in enumerate(g.items()):
        cls = "r%s%d" % (VAR[colour], i)
        anim = ""
        if animate:
            # the trunk draws first, the headwaters last, the way water fills a net
            delay = 1.35 + (1 - w / widest) * 1.05
            anim = " animation: draw %.2fs ease-out %.2fs forwards;" % (0.5 + w / widest * 0.5, delay)
        rules.append("  .%s { stroke: var(%s); stroke-width: %s;%s }" % (cls, colour, w, anim))
        cls_attr = "ink draw " + cls if animate else "ink " + cls
        body.append('<g class="%s">%s</g>' % (
            cls_attr, "".join('<path pathLength="100" d="%s"/>' % d for d in ds)))

    out = re.sub(r'  #t2 \{.*?  #t1 \{[^\n]*\n', "\n".join(rules) + "\n", src, flags=re.S)
    out = re.sub(r'<path id="t\d"[^\n]*\n', '', out)
    out = out.replace('#stem, #bowl, #t1, #t2, #t3, #t4, #counter, #outlet',
                      '#stem, #bowl, .ink, #counter, #outlet')
    anchor = '<circle id="r1"' if '<circle id="r1"' in out else '<circle id="outlet"'
    out = out.replace(anchor, "\n".join(body) + "\n" + anchor)
    out = out.replace(DESC_OLD, DESC_NEW)
    A.joinpath(fn).write_text(out)
    print("%-26s %6d bytes  %3d strands  %2d rules" %
          (fn, len(out), sum(len(v) for v in g.values()), len(g)))

for fn in ("logo.svg", "logo-wordmark.svg", "logo-wordmark-light.svg",
           "logo-wordmark-dark.svg", "logo-animated.svg"):
    patch(fn, 'net.json', animate="animated" in fn or "wordmark" in fn)
