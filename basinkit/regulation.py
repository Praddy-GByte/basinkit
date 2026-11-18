"""How much of this basin's water passes through something somebody operates.

A delineation is a statement about terrain. It says where water would go if
nothing had been built. Dams, diversions and inter-basin transfers break that
statement, and the validation behind basinkit's error figures never recorded
whether a gauge sat below one -- ``envelope.NOT_CHARACTERISED`` names
regulation for exactly that reason. This module measures it, so that the user
reading "median error 0.3 per cent" can find out whether that figure was ever
measured on a basin like theirs.

Nothing new is downloaded. HydroLAKES is already fetched for ``lakes()`` and
carries, per water body, whether it is a reservoir, its storage, and the
area draining to it. HydroRIVERS is already fetched for ``rivers()`` and
carries the modelled long-term flow. The arithmetic between them is the part
that was missing.

**What this will not tell you.** Not the operating rules, not the release
schedule, not how much water is behind the dam today, and not whether the
basin is short of water. Those are decisions and measurements, and nothing
here observes either. The degree of regulation is a ratio of two long-term
numbers, one of which is itself modelled.
"""
from __future__ import annotations

from typing import Any

#: HydroLAKES ``Lake_type``: 1 natural lake, 2 reservoir, 3 regulated lake.
RESERVOIR = 2
REGULATED_LAKE = 3

#: Degree of regulation, storage as a percentage of one year's flow. The bands
#: are read rather than ranked: a basin that can hold a tenth of its annual
#: flow behaves differently from one that can hold four years of it.
DOR_BANDS: tuple[tuple[float, float | None, str], ...] = (
    (0.0, 2.0, "effectively unregulated"),
    (2.0, 10.0, "lightly regulated"),
    (10.0, 50.0, "seasonally regulated"),
    (50.0, 100.0, "strongly regulated"),
    (100.0, None, "over-year storage"),
)

#: Above this, basinkit's own published error figures carry a warning: the
#: blind validation recorded no degree of regulation, so none of them is known
#: to have been measured on a basin held back like this one.
ENVELOPE_CAUTION_DOR = 10.0

SECONDS_PER_YEAR = 365.25 * 24 * 3600


def _band(dor: float) -> str:
    for lo, hi, name in DOR_BANDS:
        if dor >= lo and (hi is None or dor < hi):
            return name
    return "unknown"


def _mean_annual_flow_cms(basin, rivers) -> tuple[float | None, str]:
    """Long-term flow at the outlet, and where the number came from.

    HydroRIVERS carries a modelled long-term average per reach. The outlet
    reach is the one with the largest upstream area, not the one nearest the
    outlet coordinate: near a confluence those are different reaches, and the
    nearest one can be a tributary carrying a fraction of the flow.
    """
    if rivers is None or not len(rivers):
        return None, "no HydroRIVERS reach in this basin"
    if "DIS_AV_CMS" not in rivers.columns:
        return None, "HydroRIVERS returned no discharge column"
    if "UPLAND_SKM" in rivers.columns:
        row = rivers.loc[rivers["UPLAND_SKM"].idxmax()]
    else:
        row = rivers.loc[rivers["DIS_AV_CMS"].idxmax()]
    q = float(row["DIS_AV_CMS"])
    if q <= 0:
        return None, "the outlet reach carries no modelled flow"
    return q, "HydroRIVERS DIS_AV_CMS at the largest-upstream-area reach"


def regulation(basin, *, lakes=None, rivers=None, min_storage_mcm: float = 0.0
               ) -> dict[str, Any]:
    """Reservoirs in this basin, what they hold, and what that means.

    Parameters
    ----------
    lakes, rivers
        Already-fetched layers, to avoid refetching. Both default to the
        basin's own.
    min_storage_mcm
        Ignore reservoirs below this storage, in million cubic metres. The
        default keeps every one, because a small reservoir on the main stem
        can matter more than a large one on a tributary and nothing here
        knows which is which.
    """
    lk = basin.lakes() if lakes is None else lakes
    area_km2 = float(basin.area_km2)

    out: dict[str, Any] = {
        "basin_km2": round(area_km2, 3),
        "source": "HydroLAKES v1.0 (Lake_type, Vol_total, Wshd_area)",
    }

    if lk is None or not len(lk) or "Lake_type" not in lk.columns:
        out.update(reservoirs=0, storage_mcm=0.0, degree_of_regulation_pct=0.0,
                   band="effectively unregulated",
                   statement=("No water body in HydroLAKES falls inside this "
                              "basin. That is an absence in a global "
                              "inventory of lakes above 10 hectares, not a "
                              "survey: a small weir or a run-of-river intake "
                              "is below what the inventory records."))
        return out

    res = lk[lk["Lake_type"].isin((RESERVOIR, REGULATED_LAKE))].copy()
    if "Vol_total" in res.columns:
        res = res[res["Vol_total"].fillna(0.0) >= min_storage_mcm]

    if not len(res):
        natural = int((lk["Lake_type"] == 1).sum())
        out.update(reservoirs=0, natural_lakes=natural, storage_mcm=0.0,
                   degree_of_regulation_pct=0.0,
                   band="effectively unregulated",
                   statement=(
                       f"{natural} natural lake(s) and no reservoir inside "
                       "this basin. Run-of-river works, which hold no stored "
                       "volume, are not reservoirs and would not appear here "
                       "even where they exist."))
        return out

    storage = float(res["Vol_total"].fillna(0.0).sum())
    man_made = float(res["Vol_res"].fillna(0.0).sum()) if "Vol_res" in res else 0.0

    rv = basin.rivers() if rivers is None else rivers
    q_cms, q_from = _mean_annual_flow_cms(basin, rv)

    dor = None
    if q_cms:
        annual_mcm = q_cms * SECONDS_PER_YEAR / 1e6
        dor = storage / annual_mcm * 100.0

    # Area draining to reservoirs. Two numbers, because one of them is a lie
    # told by addition: reservoirs in series each count the whole catchment
    # above them, so the sum of their watershed areas can exceed the basin.
    largest_ws = None
    sum_ws = None
    if "Wshd_area" in res.columns:
        ws = res["Wshd_area"].fillna(0.0)
        largest_ws = float(ws.max())
        sum_ws = float(ws.sum())

    rows = []
    for _, r in res.sort_values("Vol_total", ascending=False).head(25).iterrows():
        rows.append({
            "name": (r.get("Lake_name") if isinstance(r.get("Lake_name"), str)
                     else None),
            "type": "reservoir" if r["Lake_type"] == RESERVOIR else "regulated lake",
            "grand_id": int(r["Grand_id"]) if r.get("Grand_id", 0) else None,
            "storage_mcm": round(float(r.get("Vol_total") or 0.0), 1),
            "upstream_km2": round(float(r.get("Wshd_area") or 0.0), 1),
            "lake_area_km2": round(float(r.get("Lake_area") or 0.0), 2),
        })

    out.update(
        reservoirs=len(res),
        natural_lakes=int((lk["Lake_type"] == 1).sum()),
        storage_mcm=round(storage, 1),
        man_made_storage_mcm=round(man_made, 1),
        mean_annual_flow_cms=round(q_cms, 2) if q_cms else None,
        mean_annual_flow_source=q_from,
        degree_of_regulation_pct=round(dor, 1) if dor is not None else None,
        band=_band(dor) if dor is not None else None,
        largest_reservoir_upstream_km2=(round(largest_ws, 1)
                                        if largest_ws is not None else None),
        largest_reservoir_upstream_pct=(round(largest_ws / area_km2 * 100, 1)
                                        if largest_ws else None),
        summed_upstream_km2=round(sum_ws, 1) if sum_ws is not None else None,
        summed_upstream_exceeds_basin=(bool(sum_ws > area_km2)
                                       if sum_ws is not None else None),
        biggest=rows,
    )
    out["statement"] = _statement(out)
    out["envelope_note"] = _envelope_note(dor)
    out["not_measured"] = (
        "Operating rules, release schedules, current storage, and whether any "
        "of this water is actually available are not measured here and cannot "
        "be read off a reservoir inventory. The degree of regulation is "
        "storage divided by a modelled long-term flow, not an observed one."
    )
    return out


def _statement(o: dict[str, Any]) -> str:
    bits = [
        (f"{o['reservoirs']} reservoir(s) inside this basin hold "
         f"{o['storage_mcm']:,.0f} million cubic metres."),
    ]
    if o.get("degree_of_regulation_pct") is not None:
        bits.append(
            f"Against a modelled long-term flow of "
            f"{o['mean_annual_flow_cms']:,.1f} m3/s, that is "
            f"{o['degree_of_regulation_pct']:,.1f} per cent of one year's "
            f"water: {o['band']}."
        )
    if o.get("largest_reservoir_upstream_pct"):
        bits.append(
            f"The largest single reservoir sits below "
            f"{o['largest_reservoir_upstream_pct']:.1f} per cent of the basin."
        )
    if o.get("summed_upstream_exceeds_basin"):
        bits.append(
            f"Adding every reservoir's own upstream area gives "
            f"{o['summed_upstream_km2']:,.0f} km2, more than the basin itself, "
            "because reservoirs in series each count the whole catchment above "
            "them. That sum is an upper bound and not an area."
        )
    return " ".join(bits)


def _envelope_note(dor: float | None) -> str:
    """Whether basinkit's own accuracy figures were measured on a basin like this.

    This is the part a tool does not usually say about itself. The blind
    validation recorded no degree of regulation, so above the caution
    threshold the honest statement is not a smaller error bar but no error
    bar at all.
    """
    if dor is None:
        return ("Flow could not be read for this basin, so the degree of "
                "regulation is unknown rather than zero.")
    if dor < ENVELOPE_CAUTION_DOR:
        return (f"At {dor:.1f} per cent, regulation is below the point where "
                "basinkit flags its own error figures. They were measured on "
                "gauges whose regulation was never recorded, so this is a "
                "weak reassurance rather than a strong one.")
    return (
        f"At {dor:.1f} per cent of annual flow in storage, this basin is held "
        "back. basinkit's published error figures come from a blind validation "
        "that recorded no degree of regulation for any of its 2,550 gauges, so "
        "none of those figures is known to have been measured on a basin like "
        "this one. Treat the delineation as a statement about terrain, which "
        "is all it ever was, and not about where the water goes."
    )
