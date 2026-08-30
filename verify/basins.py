"""Reference gauges with independently published drainage areas.

Every area here comes from the operating agency or the GRDC station record, not
from HydroBASINS -- so agreement is a real external check, not a tautology.
Rainfall figures are published long-term basin means from the literature.
"""

# name, lat, lon, published_area_km2, tolerance_frac, published_mm_yr, region
REFERENCE = [
    # --- Asia ---
    ("Sapta Koshi @ Chatara, Nepal",      26.870,  87.150,    54_100, 0.12, (900, 1800),  "as"),
    ("Godavari @ Polavaram, India",       17.240,  81.650,   307_800, 0.15, (900, 1500),  "as"),
    ("Mekong @ Pakse, Laos",              15.117, 105.800,   545_000, 0.15, (1300, 2200), "as"),
    # --- Europe ---
    ("Rhine @ Lobith, Netherlands",       51.840,   6.110,   160_800, 0.15, (700, 1200),  "eu"),
    ("Danube @ Bratislava, Slovakia",     48.140,  17.110,   131_300, 0.15, (600, 1100),  "eu"),
    # --- Africa ---
    ("Zambezi @ Victoria Falls",         -17.925,  25.857,   507_000, 0.20, (700, 1200),  "af"),
    ("Niger @ Lokoja, Nigeria",            7.800,   6.750, 2_074_000, 0.25, (600, 1400),  "af"),
    # --- South America ---
    ("Amazon @ Obidos, Brazil",           -1.947, -55.511, 4_680_000, 0.15, (1800, 2600), "sa"),
    ("Parana @ Corrientes, Argentina",   -27.470, -58.830, 1_950_000, 0.20, (900, 1600),  "sa"),
    # --- North America ---
    ("Mississippi @ Vicksburg, USA",      32.315, -90.905, 2_964_000, 0.15, (600, 1100),  "na"),
    ("Columbia @ The Dalles, USA",        45.607,-121.172,   613_800, 0.15, (400, 1000),  "na"),
    # --- Australia ---
    ("Murray @ Wentworth, Australia",    -34.108, 141.913,   950_000, 0.35, (200,  700),  "au"),
]
