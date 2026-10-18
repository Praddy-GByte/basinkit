"""Whether this basin is one the accuracy figures were measured on.

Every accuracy number published with basinkit is a population figure. The
blind validation drew 2,740 delineations at 2,550 gauges in 99 countries and
reported the median area error per size band, and that table is the honest
answer to "how accurate is it" -- for the population. It is not an answer
about the basin in front of you.

The difference is not academic. The headline figures, the ones worth quoting,
belong to large catchments: 0.3% above 100,000 km2, 1.3% from 10,000 to
100,000, 1.7% from 2,000 to 10,000. Below 500 km2 the same validation measured
30%, and below 100 km2 it measured 181%. A basin of 60 km2 is inside the
validated population and nowhere near the quoted accuracy, and until this
module existed nothing in the output said so. The user saw an area, a
boundary and a verdict on the outlet, and had no way to know that at this size
the measurement behind the software is four figures worse than the one on the
front page.

So this module answers a narrower question than "is it accurate". It answers:
*of the basins that were measured, which ones does this one resemble, and what
was the error there* -- and, where this basin resembles nothing that was
measured, it says that instead of quoting a number that does not apply.

Three kinds of answer come out of it:

``inside``
    This basin sits where the validation measured a median area error at or
    below :data:`INSIDE_MEDIAN_PCT`. The published figure applies to it.

``edge``
    Measured, but where the error was several times the headline figure, or
    with a descriptor out in the tail of what was validated. The number
    applies, and it is not the number most people have in mind.

``outside``
    Either the measured error here was above :data:`EDGE_MEDIAN_PCT`, or a
    descriptor falls beyond anything in the validation set. No published
    figure describes this case, and the envelope says so rather than
    interpolating one.

It is deliberately about the basin *boundary*, which is what the validation
measured. :func:`~basinkit.suitability.suitability` grades the elevation
model's support for the terrain products, which is the other half and a
different question. The two share their measurements: the four terrain axes
below are the same four numbers suitability already computes, compared
against the range they covered in the validation rather than against a
threshold, so passing a suitability result in costs nothing.

"Envelope" here is the statistical sense -- the region of descriptor
space the measurements cover -- and not the geometric one. A basin's bounding
box is :attr:`~basinkit.basin.Basin.bounds`. The function is called
:func:`validation_envelope` so that the two cannot be confused at a call site.

Not everything is characterised. Aridity, flow regulation and karst are each
known to matter and none of them was recorded in the validation set, so this
module names them as uncharacterised instead of implying coverage it does not
have. :data:`NOT_CHARACTERISED` carries the list and how to measure each one.
"""

from __future__ import annotations

from typing import Any

#: The blind validation, by size band. Taken from
#: ``verify/benchmarks/accuracy_by_size.csv``, which is what
#: ``docs/verification.md`` publishes; ``tests/test_envelope.py`` reads that
#: file and fails if this table drifts from it. ``upper`` is ``None`` for the
#: open-ended band. ``within_5_pct`` and ``within_20_pct`` are percentages of
#: the band's delineations landing inside that relative error.
ACCURACY_BY_SIZE: tuple[dict[str, Any], ...] = (
    {"band": "below 100", "lower": None, "upper": 100.0,
     "median_error_pct": 181.0, "within_20_pct": 22, "within_5_pct": 0},
    {"band": "100 to 500", "lower": 100.0, "upper": 500.0,
     "median_error_pct": 30.0, "within_20_pct": 40, "within_5_pct": 15},
    {"band": "500 to 2,000", "lower": 500.0, "upper": 2000.0,
     "median_error_pct": 8.9, "within_20_pct": 78, "within_5_pct": 35},
    {"band": "2,000 to 10,000", "lower": 2000.0, "upper": 10000.0,
     "median_error_pct": 1.7, "within_20_pct": 96, "within_5_pct": 58},
    {"band": "10,000 to 100,000", "lower": 10000.0, "upper": 100000.0,
     "median_error_pct": 1.3, "within_20_pct": 92, "within_5_pct": 86},
    {"band": "above 100,000", "lower": 100000.0, "upper": None,
     "median_error_pct": 0.3, "within_20_pct": 92, "within_5_pct": 78},
)

#: Size of the blind validation, for the sentence the envelope prints.
VALIDATION_GAUGES = 2550
VALIDATION_DELINEATIONS = 2740
VALIDATION_COUNTRIES = 99

#: A median area error at or below this counts as inside the envelope. Set at
#: 5% because that is the error the published tables report as the useful
#: case, and because it is the threshold ``within_5_pct`` is counted against,
#: so the two numbers in the output are measured against the same line.
INSIDE_MEDIAN_PCT = 5.0

#: Above this, no published figure is worth quoting as an accuracy. 20% is
#: where ``within_20_pct`` is counted, and a median error of a fifth of the
#: basin is a different kind of answer rather than a less precise one.
EDGE_MEDIAN_PCT = 20.0

#: The terrain study: 133 of the validation gauges for which the five
#: suitability measurements were recorded alongside the area error, in
#: ``verify/benchmarks/grade_validation.csv``. Every basin in it was between
#: 23.0 and 9,730 km2, so these ranges describe small and medium catchments
#: and nothing larger. ``axis`` keys match the ``test`` names in a
#: :func:`~basinkit.suitability.suitability` result.
TERRAIN_STUDY_GAUGES = 133
TERRAIN_STUDY_KM2 = (23.0, 9730.0)
TERRAIN_STUDY: dict[str, dict[str, Any]] = {
    "filling": {
        "unit": "percent of cells raised by depression filling",
        "p05": 1.19, "p50": 7.63, "p95": 23.6, "min": 0.33, "max": 53.34,
        # Within every size band, the basins in the top fifth for filling had
        # two to three times the median area error of the rest: 384 against
        # 239 below 100 km2, 38.3 against 13.6 from 100 to 500, 10.9 against
        # 4.4 from 500 to 2,000, 9.7 against 4.2 from 2,000 to 10,000. Median
        # filling is flat across the bands (6.3% to 8.3%), so this is not the
        # size effect in disguise. Three to ten basins per cell, so it is
        # reported as a direction and never as a coefficient.
        "tail_at": 16.13,
        "tail_multiplier": "two to three times",
    },
    "slope": {
        "unit": "percent of cells below the slope noise floor",
        "p05": 9.18, "p50": 66.87, "p95": 98.93, "min": 4.16, "max": 99.99,
    },
    "water": {
        "unit": "percent of the basin under one level surface",
        "p05": 0.0, "p50": 0.048, "p95": 2.461, "min": 0.0, "max": 5.805,
    },
    "relief": {
        "unit": "relief divided by the model's vertical error",
        "p05": 31.7, "p50": 131.2, "p95": 535.0, "min": 15.6, "max": 830.3,
        "lower_is_worse": True,
    },
    "coverage": {
        "unit": "percent of cells with no elevation",
        # Every basin in the study was fully covered. The range is therefore a
        # single point, and any basin with a void in it is outside the set --
        # which is the finding, not a gap in the table.
        "p05": 0.0, "p50": 0.0, "p95": 0.0, "min": 0.0, "max": 0.0,
    },
}

#: Conditions known to change how well surface topography defines a catchment,
#: none of which the validation set recorded. Named rather than silently
#: omitted: a user who works in one of these settings should know that no
#: error figure here was measured on it.
NOT_CHARACTERISED: tuple[dict[str, str], ...] = (
    {"axis": "aridity",
     "why": "In arid and endorheic systems the channel network is ephemeral "
            "and the topographic divide need not be the contributing area. "
            "The validation set recorded no aridity index, so none of the "
            "errors above is known to have been measured on such a basin.",
     "measure": "basinkit.sources.attributes.hydroatlas, aridity index "
                "'ari_ix_uav' (a 2.7 GB download, once)"},
    {"axis": "regulation",
     "why": "Dams, diversions and inter-basin transfers move water across the "
            "divide the terrain draws. The gauge records carried no degree of "
            "regulation, so a regulated basin's error was never separated "
            "from an unregulated one's.",
     "measure": "basinkit.sources.attributes.hydroatlas, degree of regulation "
                "'dor_pc_pva', and lakes() for upstream reservoirs"},
    {"axis": "karst",
     "why": "Where drainage is subsurface the catchment can differ from the "
            "surface basin by more than any delineation error. No "
            "lithological class was recorded in the validation.",
     "measure": "basinkit.sources.attributes.hydroatlas, karst area "
                "'kar_pc_sse'"},
)

_ORDER = {"inside": 0, "edge": 1, "outside": 2}


def _band(area_km2: float) -> dict[str, Any]:
    """The validated size band containing ``area_km2``."""
    for entry in ACCURACY_BY_SIZE:
        lower = entry["lower"]
        upper = entry["upper"]
        if (lower is None or area_km2 >= lower) and (upper is None or area_km2 < upper):
            return entry
    return ACCURACY_BY_SIZE[-1]


def _size_position(median_error_pct: float) -> str:
    if median_error_pct <= INSIDE_MEDIAN_PCT:
        return "inside"
    if median_error_pct <= EDGE_MEDIAN_PCT:
        return "edge"
    return "outside"


def _terrain_position(measured: float, ref: dict[str, Any]) -> str:
    """Where ``measured`` sits against the range the study covered."""
    if measured < ref["min"] or measured > ref["max"]:
        return "outside"
    if measured < ref["p05"] or measured > ref["p95"]:
        return "edge"
    return "inside"


def _terrain_statement(axis: str, measured: float, ref: dict[str, Any],
                       position: str, comparable: bool) -> str:
    """How this descriptor compares with the range the terrain study covered.

    Two ranges matter and conflating them would mislead: the middle 90 per
    cent, which is where the study actually has basins, and the full span,
    which includes its one or two extremes. A value at the 99th percentile was
    measured, but by almost nothing, and the wording says so rather than
    calling it covered.
    """
    bulk = f"{ref['p05']:g} to {ref['p95']:g}"
    full = f"{ref['min']:g} to {ref['max']:g}"
    flat = ref["p05"] == ref["p95"]

    if position == "inside":
        where = (
            f"every basin in the terrain study measured {ref['p05']:g}, and so "
            f"does this one"
            if flat else
            f"{measured:g} sits in the {bulk} that held the middle 90 per cent "
            f"of the terrain study's basins"
        )
    elif position == "edge":
        where = (
            f"{measured:g} is outside the {bulk} that held the middle 90 per "
            f"cent of the terrain study's basins, though inside the {full} it "
            f"covered in full: measured, but by very few basins"
        )
    elif flat:
        where = (
            f"every basin in the terrain study measured {ref['p05']:g}; this "
            f"one measures {measured:g}"
        )
    else:
        where = (
            f"{measured:g} is beyond the {full} the terrain study covered. No "
            f"basin in it looked like this on this axis"
        )
    text = f"{ref['unit'].capitalize()}: {where}."

    if axis == "filling" and measured > ref.get("tail_at", float("inf")):
        text += (f" Within every size band, the fifth of basins filled this "
                 f"heavily carried {ref['tail_multiplier']} the median area "
                 f"error of the rest -- three to ten basins per band, so read "
                 f"it as a direction and not as a factor to apply.")
    if axis == "coverage" and measured > 0:
        text += (" Every basin in the study was fully covered, so a basin "
                 "with missing elevation is outside the set by definition.")
    if not comparable:
        text += (f" The study's basins were {TERRAIN_STUDY_KM2[0]:g} to "
                 f"{TERRAIN_STUDY_KM2[1]:,.0f} km2; this one is not, so the "
                 f"range is context rather than a comparison.")
    return text


def validation_envelope(basin=None, *, area_km2: float | None = None,
             suitability: dict[str, Any] | None = None) -> dict[str, Any]:
    """Say which part of the validation set this basin belongs to.

    Parameters
    ----------
    basin
        A :class:`~basinkit.basin.Basin`. Only its area is read, so this
        downloads nothing and costs nothing.
    area_km2
        The basin area, when there is no ``Basin`` to hand. Given alongside
        ``basin`` it wins, which is what lets a caller ask about a size it has
        not delineated yet.
    suitability
        A :func:`~basinkit.suitability.suitability` result. Its five
        measurements are compared against the range they covered in the
        terrain study, adding those axes to the answer. Without it the
        envelope rests on size alone, which is the axis the full validation
        measured.

    Returns
    -------
    dict
        ``position`` (``inside``, ``edge`` or ``outside``), ``basin_km2``,
        ``size`` with the band and the error measured in it, ``axes`` with one
        entry per descriptor compared, ``not_characterised``,
        ``statement`` and ``source``.

    Examples
    --------
    >>> validation_envelope(area_km2=61.0)["position"]
    'outside'
    >>> validation_envelope(area_km2=61.0)["size"]["median_error_pct"]
    181.0
    """
    if area_km2 is None:
        if basin is None:
            raise TypeError("validation_envelope() needs a basin or an area_km2.")
        area_km2 = float(basin.area_km2)
    area_km2 = float(area_km2)

    band = _band(area_km2)
    size_position = _size_position(band["median_error_pct"])
    axes: list[dict[str, Any]] = [{
        "axis": "size",
        "measured": round(area_km2, 3),
        "unit": "km2",
        "position": size_position,
        "validated_from": (
            f"{VALIDATION_DELINEATIONS:,} delineations at "
            f"{VALIDATION_GAUGES:,} gauges in {VALIDATION_COUNTRIES} countries"
        ),
        "validated_range": band["band"] + " km2",
        "statement": (
            f"At {area_km2:,.1f} km2 this basin falls in the {band['band']} km2 "
            f"band, where the blind validation measured a median area error of "
            f"{band['median_error_pct']:g}%, with {band['within_5_pct']}% of "
            f"delineations within 5% and {band['within_20_pct']}% within 20%."
        ),
    }]

    comparable = TERRAIN_STUDY_KM2[0] <= area_km2 <= TERRAIN_STUDY_KM2[1]
    if suitability:
        for test in suitability.get("tests", ()):
            ref = TERRAIN_STUDY.get(test.get("test"))
            measured = test.get("measured")
            if ref is None or measured is None or not test.get("evaluated", True):
                continue
            measured = float(measured)
            position = _terrain_position(measured, ref)
            axes.append({
                "axis": test["test"],
                "measured": measured,
                "unit": ref["unit"],
                "position": position,
                "validated_from": (
                    f"{TERRAIN_STUDY_GAUGES} of those gauges, with the "
                    f"suitability measurements recorded"
                ),
                "validated_range": f"{ref['min']:g} to {ref['max']:g}",
                "statement": _terrain_statement(test["test"], measured, ref,
                                                position, comparable),
            })

    position = max((a["position"] for a in axes), key=lambda p: _ORDER[p])
    out = {
        "position": position,
        "basin_km2": round(area_km2, 3),
        "size": {
            "band": band["band"] + " km2",
            "median_error_pct": band["median_error_pct"],
            "within_5_pct": band["within_5_pct"],
            "within_20_pct": band["within_20_pct"],
        },
        "axes": axes,
        "outside": [a["axis"] for a in axes if a["position"] == "outside"],
        "edge": [a["axis"] for a in axes if a["position"] == "edge"],
        "not_characterised": [dict(entry) for entry in NOT_CHARACTERISED],
        "statement": _statement(position, axes, suitability is not None),
        "source": "docs/verification.md, from "
                  "verify/benchmarks/accuracy_by_size.csv and "
                  "verify/benchmarks/grade_validation.csv",
        "note": "Where this basin sits in the set the accuracy figures were "
                "measured on. It says nothing about whether this particular "
                "boundary is right: check_outlet tests that against the river "
                "network, and suitability grades the terrain products.",
    }
    return out


def _statement(position: str, axes: list[dict[str, Any]],
               had_suitability: bool) -> str:
    """The plain-language verdict, built from the axes that left the range.

    Two different things both come out as ``outside`` and they must not be
    worded the same way. A 135 km2 basin *was* measured -- 34 of the terrain
    study's gauges were that size -- and what was measured there is 30%, not
    the 1.3% on the front page. A basin with a void in it was measured by
    nothing at all. Saying "not measured on basins like this one" about the
    first would be false, so the head sentence is chosen by cause.
    """
    size = axes[0]
    reasons = " ".join(a["statement"] for a in axes
                       if a["position"] in ("edge", "outside"))

    if position == "inside":
        head = (
            "This basin is one the published accuracy applies to. "
            f"{size['statement']} "
        )
        if not had_suitability:
            head += (
                "Size is the axis the full validation measured; pass a "
                "suitability result to compare the terrain descriptors as "
                "well. "
            )
        return head + _uncharacterised_tail()

    if position == "edge":
        return (
            "This basin was measured, but at the edge of what the published "
            "figures describe, so quote the number below rather than the "
            "headline one. " + reasons + " " + _uncharacterised_tail()
        )

    heads = []
    if size["position"] == "outside":
        heads.append(
            "The validation did measure basins of this size, and what it "
            "measured there is not the figure basinkit is usually quoted "
            "for. Read this boundary as a first approximation and check it: "
            "check_outlet tests it against the mapped river network, and a "
            "finer elevation source or survey sheets settle it."
        )
    unmatched = [a["axis"] for a in axes[1:] if a["position"] == "outside"]
    if unmatched:
        heads.append(
            "On " + ", ".join(unmatched) + ", no basin in the terrain study "
            "resembled this one, so no measured error covers it at all."
        )
    return " ".join(heads) + " " + reasons + " " + _uncharacterised_tail()


def _uncharacterised_tail() -> str:
    names = ", ".join(entry["axis"] for entry in NOT_CHARACTERISED)
    return (
        f"Three conditions were never recorded in the validation and so carry "
        f"no measured error at all: {names}. Where one of them applies to this "
        f"basin, nothing above describes it."
    )
