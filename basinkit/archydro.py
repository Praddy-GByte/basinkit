"""Arc Hydro schema export: basinkit's sub-catchments and rivers, renamed.

This is a reshaping, not a computation. Every value written out is one basinkit
already holds; only the field names and the identifier space change, so that
Arc Hydro's own tools can read the result without being told anything about
basinkit.

Field meanings follow the Arc Hydro data model:

    HydroID      an internal integer identifier assigned by the tools, unique
                 within the geodatabase
    HydroCode    "the permanent public identifier of the feature that was
                 assigned by the agency that created it" -- so the HydroBASINS
                 or HydroRIVERS identifier goes here, unchanged
    NextDownID   "the HydroID of the downstream feature", and -1 where there is
                 no downstream feature
    AreaSqKm     the feature's area in square kilometres

HydroID is assigned 1..N in a stable order rather than reusing HYBAS_ID,
because a 10-digit HydroBASINS identifier does not fit the Arc Hydro long
integer field, and because HydroID is defined as the tools' own identifier. The
original identifier is never lost: it is written to HydroCode.

DrainID is deliberately not written. In the Arc Hydro model it points a drainage
line at the catchment containing it, and deriving that here would mean a spatial
join -- a guess about which catchment a reach belongs to. basinkit does not hold
that link, so the field is left for Arc Hydro's own tools to populate.
"""
from __future__ import annotations

NO_DOWNSTREAM = -1


def _map_ids(ids):
    """HydroID 1..N in ascending order of the original identifier."""
    return {int(v): i + 1 for i, v in enumerate(sorted(int(x) for x in ids))}


def catchment_table(subbasins):
    """Arc Hydro Catchment attributes from Basin.subbasins().

    Returns a copy of the frame with the Arc Hydro fields added; the original
    HydroBASINS columns are kept so nothing is thrown away.
    """
    import pandas as pd

    need = {"HYBAS_ID", "NEXT_DOWN", "SUB_AREA"}
    missing = need - set(subbasins.columns)
    if missing:
        raise ValueError(
            f"the sub-catchment layer is missing {sorted(missing)}; "
            "Basin.subbasins() returns these HydroBASINS attributes")

    out = subbasins.copy()
    hid = _map_ids(out["HYBAS_ID"])
    out["HydroID"] = [hid[int(v)] for v in out["HYBAS_ID"]]
    out["HydroCode"] = [str(int(v)) for v in out["HYBAS_ID"]]
    # NEXT_DOWN is 0 in HydroBASINS where the unit drains nowhere, and points
    # outside this set for the basin's own outlet, whose downstream unit was
    # not walked. Both become -1, which is what Arc Hydro means by no
    # downstream feature.
    out["NextDownID"] = [
        hid.get(int(v), NO_DOWNSTREAM) if int(v) != 0 else NO_DOWNSTREAM
        for v in out["NEXT_DOWN"]
    ]
    out["AreaSqKm"] = pd.to_numeric(out["SUB_AREA"], errors="coerce")
    return out


def drainage_line_table(rivers):
    """Arc Hydro DrainageLine attributes from Basin.rivers()."""
    import pandas as pd

    need = {"HYRIV_ID", "NEXT_DOWN"}
    missing = need - set(rivers.columns)
    if missing:
        raise ValueError(
            f"the river layer is missing {sorted(missing)}; Basin.rivers() "
            "returns these HydroRIVERS attributes")

    out = rivers.copy()
    hid = _map_ids(out["HYRIV_ID"])
    out["HydroID"] = [hid[int(v)] for v in out["HYRIV_ID"]]
    out["HydroCode"] = [str(int(v)) for v in out["HYRIV_ID"]]
    out["NextDownID"] = [
        hid.get(int(v), NO_DOWNSTREAM) if int(v) != 0 else NO_DOWNSTREAM
        for v in out["NEXT_DOWN"]
    ]
    if "LENGTH_KM" in out.columns:
        out["LengthKm"] = pd.to_numeric(out["LENGTH_KM"], errors="coerce")
    return out


def check(catchments):
    """Is the routing table a single tree that drains to one outlet?

    Reported rather than fixed. A table that fails this is still written out,
    because the failure belongs to the source data and hiding it would be worse.
    """
    hid = catchments["HydroID"].astype(int).tolist()
    nxt = catchments["NextDownID"].astype(int).tolist()
    known = set(hid)
    terminal = [h for h, n in zip(hid, nxt, strict=True) if n == NO_DOWNSTREAM]
    dangling = [n for n in nxt if n != NO_DOWNSTREAM and n not in known]
    # walk downstream from every unit; a cycle shows up as a walk that does not
    # end within the number of units
    nx = dict(zip(hid, nxt, strict=True))
    cycles = 0
    for h in hid:
        seen, cur, steps = set(), h, 0
        while cur != NO_DOWNSTREAM and cur in nx and steps <= len(hid):
            if cur in seen:
                cycles += 1
                break
            seen.add(cur)
            cur = nx[cur]
            steps += 1
    return {"units": len(hid), "terminal_units": len(terminal),
            "dangling_next_down": len(dangling), "units_in_a_cycle": cycles,
            "single_outlet": len(terminal) == 1 and not dangling and not cycles}


def figure(catchments, drainage_lines=None, *, path=None, title="",
           figsize=(7.2, 6.4), dpi=150):
    """The routing table drawn, so that it can be checked by eye.

    Each catchment is filled, and a line runs from its centroid to the centroid
    of the catchment its ``NextDownID`` names. A routing table that is a single
    tree draining to one outlet looks like one; a table with two outlets, a
    cycle or a pointer into nothing does not, and that is visible here before
    anything downstream consumes it.

    Returns the figure. Saves it if ``path`` is given.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    need = {"HydroID", "NextDownID"}
    missing = need - set(catchments.columns)
    if missing:
        raise ValueError("catchment_table() must be run first; "
                         f"{sorted(missing)} missing")

    fig, ax = plt.subplots(figsize=figsize)
    catchments.plot(ax=ax, facecolor="#dce7f0", edgecolor="#7f9db9", linewidth=0.6)
    if drainage_lines is not None and len(drainage_lines):
        drainage_lines.plot(ax=ax, color="#1f4e79", linewidth=0.8)

    pts = catchments.geometry.representative_point()
    by_id = {int(h): (p.x, p.y)
             for h, p in zip(catchments["HydroID"], pts, strict=True)}
    outlets = 0
    for hid, nxt in zip(catchments["HydroID"], catchments["NextDownID"],
                        strict=True):
        a = by_id.get(int(hid))
        b = by_id.get(int(nxt))
        if a is None:
            continue
        if b is None:
            outlets += 1
            ax.plot([a[0]], [a[1]], marker="s", ms=9, mfc="#c0392b",
                    mec="white", mew=1.2, zorder=5)
            continue
        ax.annotate("", xy=b, xytext=a, zorder=4,
                    arrowprops=dict(arrowstyle="-|>", color="#444444",
                                    lw=1.0, shrinkA=2, shrinkB=2))
        ax.plot([a[0]], [a[1]], marker="o", ms=3.2, color="#444444", zorder=5)

    chk = check(catchments)
    plural = "" if chk["terminal_units"] == 1 else "s"
    ax.set_title((title + "\n" if title else "")
                 + f"Catchment routing: {chk['units']} units, "
                   f"{chk['terminal_units']} outlet{plural}",
                 fontsize=10, loc="left")
    ax.set_xlabel("longitude" if (catchments.crs and catchments.crs.is_geographic)
                  else "easting")
    ax.set_ylabel("latitude" if (catchments.crs and catchments.crs.is_geographic)
                  else "northing")
    ax.set_aspect("equal", adjustable="datalim")
    verdict = ("single tree, no cycles, no dangling pointers"
               if chk["single_outlet"] else
               f"{chk['dangling_next_down']} dangling pointers, "
               f"{chk['units_in_a_cycle']} units in a cycle")
    foot = ("HydroID, HydroCode, NextDownID, AreaSqKm  •  "
            f"no downstream feature = {NO_DOWNSTREAM}  •  " + verdict)
    fig.text(0.01, 0.005, foot, fontsize=7.5, color="#444444")
    fig.tight_layout()
    if path:
        fig.savefig(path, dpi=dpi, bbox_inches="tight")
    return fig
