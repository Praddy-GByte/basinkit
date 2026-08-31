"""Generate the drainage network that fills the bowl of the b.

Run from assets/:  python build/build_network.py net.json
then feed net.json to build/install_network.py.

The network is grown rather than drawn: a trunk descends to the single
outlet, junctions are placed along it, and at each junction the bank with
the open catchment in front of it takes the tributary. Every junction
angle is acute and opens downstream, and widths taper toward the
headwaters -- the two things that make a drawn network read as drainage.

SIMPLE=1 in the environment produces the reduced mark used below 64 px.
"""
import math, json, random, os, sys
from shapely.geometry import Polygon, Point, box
from shapely.ops import unary_union

def cub(p0,p1,p2,p3,n=60):
    o=[]
    for i in range(n+1):
        t=i/n; m=1-t
        o.append((m**3*p0[0]+3*m*m*t*p1[0]+3*m*t*t*p2[0]+t**3*p3[0],
                  m**3*p0[1]+3*m*m*t*p1[1]+3*m*t*t*p2[1]+t**3*p3[1]))
    return o

pts  = cub((62,66),(116,42),(170,70),(170,120),90)
pts += cub((170,120),(170,166),(120,172),(62,172),90)[1:]
counter = Polygon(pts)
SAFE = counter.buffer(-11.0)          # ink stays clear of the divide
rnd  = random.Random(11)
SIMPLE = os.environ.get('SIMPLE') == '1'   # reduced mark for favicon sizes

# ---------------------------------------------------------------- trunk ----
# One main stem descending to the single outlet at (62,172), the way a real
# basin drains. Everything else joins it; nothing reaches the outlet alone.
TRUNK = [((104,70),(138,86),(146,116),(134,140)),
         ((134,140),(121,152),( 98,159),(74,161))]
trunk_pts = []
for seg in TRUNK:
    trunk_pts += cub(*seg, 60)[1 if trunk_pts else 0:]

def at(t):
    """point and downstream heading (deg) at fraction t along the trunk"""
    i = max(1, min(len(trunk_pts)-1, int(t*(len(trunk_pts)-1))))
    (x0,y0),(x1,y1) = trunk_pts[i-1], trunk_pts[i]
    return (x1,y1), math.degrees(math.atan2(y1-y0, x1-x0))

def cubic(x0,y0,ang,L,bow):
    a=math.radians(ang); px,py=-math.sin(a),math.cos(a)
    e=(x0+math.cos(a)*L, y0+math.sin(a)*L)
    c1=(x0+math.cos(a)*L*.35+px*bow*.6, y0+math.sin(a)*L*.35+py*bow*.6)
    c2=(x0+math.cos(a)*L*.72+px*bow,    y0+math.sin(a)*L*.72+py*bow)
    return ("M%.1f %.1f C%.1f %.1f,%.1f %.1f,%.1f %.1f"
            %(x0,y0,c1[0],c1[1],c2[0],c2[1],e[0],e[1])), e, cub((x0,y0),c1,c2,e,14)

def fits(x0,y0,ang,L,bow,w):
    _,_,ps = cubic(x0,y0,ang,L,bow)
    g = SAFE.buffer(-w/2)
    return all(g.contains(Point(x,y)) for x,y in ps)

def reach(x, y, ang, w):
    """How far a strand can run from (x,y) before it would touch the divide."""
    a=math.radians(ang); g=SAFE.buffer(-w/2); d=0.0
    while d < 90 and g.contains(Point(x+math.cos(a)*(d+2), y+math.sin(a)*(d+2))):
        d += 2
    return d

FORKS = [(0.24,-30,0.40),(0.48,27,0.50),(0.72,-26,0.44),(1.00,9,0.56)]

def grow(out, tag, colour, x, y, ang, L, w, depth, sign=1):
    bow = L*0.12*sign
    while L > 4.5 and not fits(x,y,ang,L,bow,w):
        L *= 0.85; bow = L*0.12*sign
    if L <= 4.5: return
    d,e,_ = cubic(x,y,ang,L,bow)
    out.append((tag, colour, round(max(w,1.3),1), d))
    if depth == 0: return
    for i,(t,da,ls) in enumerate(FORKS if L > 26 else FORKS[1::2]):
        a=math.radians(ang)
        grow(out, tag+chr(97+i), colour,
             x+math.cos(a)*L*t, y+math.sin(a)*L*t,
             ang+da+rnd.uniform(-7,7), L*ls*rnd.uniform(.85,1.1),
             w*0.58, depth-1, -sign)

NET=[]
# trunk drawn in three widening pieces, thin at the head, full at the outlet
for i,(seg,w) in enumerate(zip(
        [cub(*TRUNK[0],60)[:31], cub(*TRUNK[0],60)[30:], cub(*TRUNK[1],60)],
        [4.4, 6.4, 8.0])):
    d = "M%.1f %.1f "%seg[0] + " ".join("L%.1f %.1f"%p for p in seg[1::6])
    NET.append(("trunk%d"%i, "--stem", w, d))

# tributaries, alternating banks, each an acute junction opening downstream
# Junctions spaced down the trunk; each bank is used wherever the catchment
# leaves room, which is what gives a real basin its lopsided look.
# Junctions down the trunk. The cap shrinks toward the outlet because the strip
# a lower reach drains is narrow -- the bowl's middle already belongs upstream.
# Junctions down the trunk. At each one the bank with the open catchment in
# front of it carries the main tributary; the other bank gets a short one.
BANDS=[(0.06,"--trib-4",4.0,2),(0.16,"--trib-4",3.6,2),
       (0.27,"--trib-3",5.0,3),(0.38,"--trib-3",4.4,3),
       (0.49,"--trib-2",5.6,3),(0.60,"--trib-2",4.4,3),
       (0.71,"--trib-1",5.2,3),(0.83,"--trib-1",3.8,2)]
used=[]
def pick(jx, jy, head, side, w):
    """Acute junction angle with the most catchment in front, nudged away from
    the angle the previous junction took so the tributaries fan out."""
    best=None
    for a in (24, 34, 45, 57, 68):
        ang = head + 180 + side*a
        r   = reach(jx, jy, ang, w)
        pen = max((0.0, *(18 - min(abs(ang-u) % 360, 360-abs(ang-u) % 360) for u in used[-2:])))
        score = r - pen*2.2
        if best is None or score > best[0]: best=(score, r, ang)
    used.append(best[2])
    return best[1], best[2]

for k,(t,colour,w,dep) in enumerate(BANDS):
    (jx,jy), head = at(t)
    sides = sorted((+1,-1), key=lambda s: -reach(jx, jy, head+180+s*45, w))
    for rank,side in enumerate(sides):
        r, ang = pick(jx, jy, head, side, w)
        L = min(r*0.88, 56 if rank==0 else 22)
        if L < 11: continue
        grow(NET, "t%d%s"%(k, "ab"[rank]), colour, jx, jy, ang, L,
             w if rank==0 else w*0.58,
             (1 if SIMPLE else dep) if rank==0 else (0 if SIMPLE else 2), sign=side)

json.dump(NET, open(sys.argv[1] if len(sys.argv)>1 else 'net.json','w'))
print(len(NET), "strands")
