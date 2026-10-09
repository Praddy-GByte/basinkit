"""How long a basin takes to respond to rain: concentration time and lag.

    basin = bk.Basin.from_point(-19.88038, -43.79371)
    t = basin.concentration_time()
    t["estimates"]["kirpich_min"]
    t["spread_factor"]

Time of concentration is the single most-used number in small-catchment
design, and it is not a measured quantity. Every value is an empirical formula
fitted to a particular set of catchments in a particular landscape, and on the
same basin they disagree by a factor of two or three routinely. A tool that
returns one of them as *the* answer is making a choice on the user's behalf
and hiding it.

So this returns all of them, with the catchments each was fitted to, and the
spread between them. A design that is not robust across that spread is not
robust, and that is worth knowing before the concrete is poured rather than
after.

Every input comes from ``morphometry()``: no new dataset is fetched, and the
same equal-area projection measures the area and every length, so the inputs
are consistent with each other.
"""

from __future__ import annotations

import math

#: Each formula, with what it was fitted to and where it should not be used.
METHODS = {
    "kirpich": {
        "citation": "Kirpich, Z. P. (1940). Civil Engineering 10(6), 362.",
        "fitted_to": "seven agricultural catchments in Tennessee, 0.4-45 ha, "
                     "well-defined channels, slopes 3-10 percent",
        "caution": "Fitted on very small catchments. Above a few tens of "
                   "square kilometres it is an extrapolation, and it reads "
                   "short.",
    },
    "california": {
        "citation": "California Culvert Practice (1942), after Kirpich.",
        "fitted_to": "mountain catchments in California",
        "caution": "Algebraically identical to Kirpich whenever the channel "
                   "slope is taken as relief over length, which is how "
                   "morphometry() computes it. On this package the two are "
                   "one method under two names, and the agreement between "
                   "them is arithmetic rather than evidence.",
    },
    "giandotti": {
        "citation": "Giandotti, M. (1934). Memorie e Studi Idrografici 8, 107.",
        "fitted_to": "Italian catchments, roughly 170-70,000 km2",
        "caution": "Built for large basins; on a very small one it reads long.",
    },
    "ventura": {
        "citation": "Ventura, in Italian practice; see Pasini and Ventura "
                    "formulas as collected by Grimaldi et al. (2012).",
        "fitted_to": "Italian catchments of moderate size",
        "caution": "Depends on area and slope alone, so it ignores how the "
                   "network is arranged.",
    },
    "temez": {
        "citation": "Temez, J. R. (1978). Calculo hidrometeorologico de "
                    "caudales maximos en pequenas cuencas naturales. MOPU.",
        "fitted_to": "Spanish catchments, 1-3,000 km2; widely used across "
                     "Spain and Latin America",
        "caution": "For natural catchments. An urbanised basin responds "
                   "faster than this.",
    },
    "bransby_williams": {
        "citation": "Bransby Williams, G. (1922). Engineering 121, 321.",
        "fitted_to": "catchments in India, used in Australian practice",
        "caution": "Insensitive to slope compared with the others.",
    },
}


def concentration_time(morphometry: dict) -> dict:
    """Concentration time by several formulas, with the spread between them.

    Parameters
    ----------
    morphometry
        The dict ``Basin.morphometry()`` returns. Area, channel length, basin
        length and the channel gradient are read from it.

    Returns
    -------
    dict
        ``estimates`` in minutes per method, ``lag_time_min`` from the SCS
        relation on the median estimate, ``spread_factor`` (longest over
        shortest) and ``inputs``, so the numbers can be checked by hand.
    """
    areal = morphometry.get("areal", {})
    linear = morphometry.get("linear", {})
    relief = morphometry.get("relief", {})

    area_km2 = areal.get("area_km2")
    channel_km = linear.get("main_channel_length_km")
    basin_km = linear.get("basin_length_km")
    gradient = relief.get("channel_gradient_m_per_km")
    mean_m = relief.get("elevation_mean_m")
    min_m = relief.get("elevation_min_m")
    channel_relief_m = relief.get("main_channel_relief_m")

    missing = [n for n, v in (("area_km2", area_km2),
                              ("main_channel_length_km", channel_km),
                              ("basin_length_km", basin_km)) if not v]
    if missing:
        raise ValueError(
            "Concentration time needs " + ", ".join(missing) + " from "
            "morphometry(), and this basin has no value for them. That "
            "happens when the channel network could not be built, which "
            "morphometry() reports in its own output."
        )

    out: dict[str, float] = {}
    channel_m = channel_km * 1000.0

    # Channel slope as a fraction. The gradient comes in metres per kilometre.
    slope = (gradient / 1000.0) if gradient else None

    if slope and slope > 0:
        # Kirpich, in the metric form: minutes from metres and m/m.
        out["kirpich_min"] = 0.0195 * channel_m ** 0.77 * slope ** -0.385
        # Ventura: area and slope only.
        out["ventura_min"] = 60 * 0.1272 * math.sqrt(area_km2 / slope)
        # Temez, the Spanish standard form, hours -> minutes.
        out["temez_min"] = 60 * 0.3 * (channel_km / slope ** 0.25) ** 0.76

    if channel_relief_m and channel_relief_m > 0:
        # California Culvert Practice, hours -> minutes.
        out["california_min"] = 60 * (
            0.871 * channel_km ** 3 / channel_relief_m) ** 0.385

    if mean_m is not None and min_m is not None and mean_m > min_m:
        # Giandotti, hours -> minutes.
        out["giandotti_min"] = 60 * (
            (4 * math.sqrt(area_km2) + 1.5 * channel_km)
            / (0.8 * math.sqrt(mean_m - min_m)))

    if slope and slope > 0:
        # Bransby Williams, minutes. Slope as a percentage.
        out["bransby_williams_min"] = (
            0.605 * channel_km / (area_km2 ** 0.1 * (slope * 100) ** 0.2) * 60)

    if not out:
        raise ValueError(
            "No formula could be evaluated: the basin has no usable channel "
            "slope and no channel relief. Both come from the long profile, "
            "which morphometry() builds from the river network."
        )

    # Kirpich and California coincide here (see METHODS), so counting both
    # would make the estimates look more independent than they are. They are
    # not bit-identical: the channel gradient reaches this function already
    # rounded by morphometry(), so the two forms of the same equation differ
    # in the fifth significant figure. Counted at the precision the estimates
    # are reported at -- two values that print the same are one value.
    distinct = {round(v, 1) for v in out.values()}
    values = sorted(out.values())
    median = (values[len(values) // 2] if len(values) % 2
              else 0.5 * (values[len(values) // 2 - 1] + values[len(values) // 2]))
    # Round once, then derive the lag from the rounded value. Taking the lag
    # from the full-precision median and rounding separately leaves two
    # printed numbers that do not agree with each other.
    median = round(median, 1)

    return {
        "estimates": {k: round(v, 1) for k, v in sorted(out.items())},
        "median_min": median,
        "shortest_min": round(values[0], 1),
        "longest_min": round(values[-1], 1),
        "spread_factor": round(values[-1] / values[0], 2),
        "n_formulas": len(out),
        "n_distinct_values": len(distinct),
        # Mockus's relation, used throughout SCS/NRCS practice.
        "lag_time_min": round(0.6 * median, 1),
        "inputs": {
            "area_km2": area_km2,
            "main_channel_length_km": channel_km,
            "basin_length_km": basin_km,
            "channel_slope_m_per_m": round(slope, 6) if slope else None,
            "main_channel_relief_m": channel_relief_m,
        },
        "methods": METHODS,
        "note": (
            "These are empirical formulas, not a measurement. They were fitted "
            "to different catchments in different landscapes and disagree by "
            f"a factor of {round(values[-1] / values[0], 2)} on this basin. "
            "Pick the one whose fitted range this basin falls in, or carry the "
            "spread through the design. Kirpich and California Culvert "
            "Practice are the same equation once the channel slope is relief "
            "over length, so they agree by construction, not by corroboration."
        ),
    }
