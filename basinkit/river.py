"""The river above a point: its course, its tributaries, and its profile.

``Basin`` answers "what drains into here". ``River`` answers "what is the river
that arrives here" -- which is a different question and the one people usually
ask first. Where does it rise, how far has it come, how much water is in it,
what joined it on the way, and how steeply does its bed fall.

    river = bk.River.from_point(23.18, 75.78)
    print(river)
    river.report("shipra.html")

Everything comes from the same HydroRIVERS network the basin already uses, so
one download serves both and no new source is introduced. The course is traced
from the outlet upstream, taking the larger contributing area at every junction
-- the standard definition of a main stem -- so the river reported is the river
that arrives at the point you clicked, not the longest line on the map.

Three things are worth stating before anyone reads a number off this.

**The river ends where you clicked.** A profile of the Ganga taken at Kanpur is
the Ganga above Kanpur. ``distance_to_sea_km`` records how much river is left
below the point, so the part being described is never mistaken for the whole.

**Discharge is modelled, not gauged.** ``DIS_AV_CMS`` is HydroRIVERS' long-term
natural average, computed from a global runoff model. It is not a measurement
and it does not know about dams, abstraction or irrigation, which on a regulated
river is the difference between the number and the water.

**The network sets the resolution.** HydroRIVERS carries reaches down to about
10 km2 of catchment, so headwater tributaries below that threshold are absent
and the source sits at the top of the mapped network rather than at the spring.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


def _laea(lat: float, lon: float) -> str:
    return (f"+proj=laea +lat_0={lat} +lon_0={lon} "
            "+x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs")


@dataclass
class Confluence:
    """A tributary meeting the main stem."""

    distance_from_source_km: float
    order: int
    length_km: float
    upland_km2: float
    discharge_cms: float
    lat: float
    lon: float
    share_of_flow: float = 0.0     # of the main stem below the junction


@dataclass
class River:
    """A river traced from an outlet up to its source.

    Attributes are plain numbers so the object prints and serialises without
    ceremony; the geometry stays in :attr:`main_stem` for anyone who needs it.
    """

    basin: Any
    main_stem: Any                          # GeoDataFrame, source -> outlet
    length_km: float = 0.0
    straight_km: float = 0.0
    order: int = 0
    source_lat: float = 0.0
    source_lon: float = 0.0
    mouth_lat: float = 0.0
    mouth_lon: float = 0.0
    discharge_cms: float = 0.0
    upland_km2: float = 0.0
    distance_to_sea_km: float | None = None
    endorheic: bool = False
    source_elev_m: float | None = None
    mouth_elev_m: float | None = None
    tributaries: list[Confluence] = field(default_factory=list)
    _profile: Any = None

    # -- construction ----------------------------------------------------

    @classmethod
    def from_point(cls, lat: float, lon: float, *, dem=None, **kwargs) -> River:
        """Trace the river arriving at a coordinate.

        ``kwargs`` are passed to :meth:`Basin.from_point`, so the delineation
        backend and its options are the same ones the basin accepts.
        """
        from .basin import Basin

        basin = Basin.from_point(lat, lon, **kwargs)
        return cls.from_basin(basin, dem=dem)

    @classmethod
    def from_basin(cls, basin, *, rivers=None, dem=None) -> River:
        """Trace the main stem of an existing basin."""
        riv = rivers if rivers is not None else basin.rivers()
        needed = {"HYRIV_ID", "NEXT_DOWN", "UPLAND_SKM"}
        missing = needed - set(riv.columns)
        if missing:
            raise ValueError(
                f"the river layer is missing {sorted(missing)}; River needs the "
                "HydroRIVERS attributes that Basin.rivers() returns")

        path = _trace(riv)
        stem = riv.iloc[path].copy()

        r = cls(basin=basin, main_stem=stem)
        _measure(r, stem)
        _find_tributaries(r, riv, stem)
        if dem is not None or True:
            _read_ends(r, stem, dem, basin)
        return r

    # -- derived ---------------------------------------------------------

    @property
    def sinuosity(self) -> float | None:
        """Course length over the straight line from source to mouth."""
        return round(self.length_km / self.straight_km, 3) if self.straight_km else None

    @property
    def relief_m(self) -> float | None:
        if self.source_elev_m is None or self.mouth_elev_m is None:
            return None
        return round(self.source_elev_m - self.mouth_elev_m, 1)

    @property
    def gradient_m_per_km(self) -> float | None:
        rel = self.relief_m
        if rel is None or not self.length_km:
            return None
        return round(rel / self.length_km, 3)

    @property
    def reaches_the_sea(self) -> bool:
        return not self.endorheic

    def profile(self, n: int = 300):
        """Distance, elevation, upstream area and discharge along the stem.

        Returns a DataFrame indexed by distance from the source. Elevation is
        sampled from the DEM and conditioned to fall downstream, because a
        centreline and a DEM never agree pixel for pixel and a single sample
        can land on a bank.
        """
        if self._profile is None:
            self._profile = _build_profile(self, n)
        return self._profile

    def facts(self) -> dict[str, Any]:
        """Everything scalar, as one flat dictionary."""
        return {
            "length_km": round(self.length_km, 2),
            "straight_line_km": round(self.straight_km, 2),
            "sinuosity": self.sinuosity,
            "strahler_order": self.order,
            "basin_area_km2": round(self.basin.area_km2, 1),
            "upland_area_km2": round(self.upland_km2, 1),
            "mean_discharge_cms": round(self.discharge_cms, 3),
            "source_lat_lon": [round(self.source_lat, 5), round(self.source_lon, 5)],
            "mouth_lat_lon": [round(self.mouth_lat, 5), round(self.mouth_lon, 5)],
            "source_elevation_m": self.source_elev_m,
            "mouth_elevation_m": self.mouth_elev_m,
            "relief_m": self.relief_m,
            "gradient_m_per_km": self.gradient_m_per_km,
            "distance_to_sea_km": self.distance_to_sea_km,
            "endorheic": self.endorheic,
            "tributaries_counted": len(self.tributaries),
        }

    def report(self, path: str | Path, *, title: str | None = None,
               morphometry: bool = True, landcover: bool = True) -> str:
        """Write the whole profile as one self-contained HTML page."""
        from .riverreport import write_report

        return write_report(self, path, title=title,
                            morphometry=morphometry, landcover=landcover)

    def __repr__(self) -> str:
        q = f"{self.discharge_cms:,.1f} m3/s" if self.discharge_cms else "no discharge"
        return (f"<River length={self.length_km:,.0f} km order={self.order} "
                f"{q} basin={self.basin.area_km2:,.0f} km2>")


# ------------------------------------------------------------------ tracing


def _trace(riv) -> list[int]:
    """Row positions of the main stem, ordered source -> outlet.

    Starts at the reach draining the most land (the outlet) and walks upstream,
    taking the larger contributing area at every junction.
    """
    ids = riv["HYRIV_ID"].astype("int64").to_numpy()
    dn = riv["NEXT_DOWN"].astype("int64").to_numpy()
    up = riv["UPLAND_SKM"].astype("float64").to_numpy()
    by_id = {int(i): k for k, i in enumerate(ids)}

    upstream: dict[int, list[int]] = {}
    for k, d in enumerate(dn):
        d = int(d)
        if d in by_id:
            upstream.setdefault(d, []).append(k)

    cur = int(np.argmax(up))
    path = [cur]
    seen = {cur}
    while True:
        kids = upstream.get(int(ids[cur]), [])
        kids = [k for k in kids if k not in seen]
        if not kids:
            break
        cur = max(kids, key=lambda k: up[k])
        seen.add(cur)
        path.append(cur)
    path.reverse()                       # source first
    return path


def _measure(r: River, stem) -> None:
    lat, lon = r.basin.centroid
    m = stem.to_crs(_laea(lat, lon))
    r.length_km = float(m.geometry.length.sum()) / 1000.0

    first, last = stem.geometry.iloc[0], stem.geometry.iloc[-1]
    src = _first_point(first)
    mouth = _last_point(last)
    r.source_lat, r.source_lon = src[1], src[0]
    r.mouth_lat, r.mouth_lon = mouth[1], mouth[0]

    a = m.geometry.iloc[0]
    b = m.geometry.iloc[-1]
    r.straight_km = math.dist(_first_point(a), _last_point(b)) / 1000.0

    out = stem.iloc[-1]
    r.order = int(out["ORD_STRA"]) if "ORD_STRA" in stem.columns else 0
    r.upland_km2 = float(out.get("UPLAND_SKM", 0.0))
    r.discharge_cms = float(out.get("DIS_AV_CMS", 0.0) or 0.0)
    if "DIST_DN_KM" in stem.columns:
        r.distance_to_sea_km = round(float(out["DIST_DN_KM"]), 1)
    if "ENDORHEIC" in stem.columns:
        r.endorheic = bool(int(out["ENDORHEIC"]))


def _first_point(geom):
    g = getattr(geom, "geoms", [geom])[0]
    return tuple(g.coords[0][:2])


def _last_point(geom):
    parts = list(getattr(geom, "geoms", [geom]))
    return tuple(parts[-1].coords[-1][:2])


def _find_tributaries(r: River, riv, stem) -> None:
    """Every reach that drains directly into the main stem.

    Reported with the distance downstream at which it arrives and the share of
    the main stem's flow it carries, so the confluences that matter stand out
    from the ones that do not.
    """
    ids = riv["HYRIV_ID"].astype("int64").to_numpy()
    dn = riv["NEXT_DOWN"].astype("int64").to_numpy()
    stem_ids = set(stem["HYRIV_ID"].astype("int64").tolist())
    stem_pos = {int(v): i for i, v in enumerate(stem["HYRIV_ID"].astype("int64"))}

    lat, lon = r.basin.centroid
    seg_km = (stem.to_crs(_laea(lat, lon)).geometry.length / 1000.0).to_numpy()
    cum = np.concatenate([[0.0], np.cumsum(seg_km)])   # distance to each reach's end

    stem_q = {int(v): float(q or 0.0)
              for v, q in zip(stem["HYRIV_ID"].astype("int64"),
                              stem.get("DIS_AV_CMS", [0] * len(stem)), strict=False)}

    out: list[Confluence] = []
    for k, (rid, d) in enumerate(zip(ids, dn, strict=False)):
        rid, d = int(rid), int(d)
        if rid in stem_ids or d not in stem_ids:
            continue
        row = riv.iloc[k]
        pos = stem_pos[d]
        q = float(row.get("DIS_AV_CMS", 0.0) or 0.0)
        main_q = stem_q.get(d, 0.0)
        geom = row.geometry
        p = _last_point(geom)
        out.append(Confluence(
            distance_from_source_km=round(float(cum[pos + 1]), 2),
            order=int(row.get("ORD_STRA", 0)),
            length_km=round(float(row.get("LENGTH_KM", 0.0)), 2),
            upland_km2=round(float(row.get("UPLAND_SKM", 0.0)), 1),
            discharge_cms=round(q, 3),
            lat=round(p[1], 5), lon=round(p[0], 5),
            share_of_flow=round(q / main_q, 3) if main_q > 0 else 0.0,
        ))
    out.sort(key=lambda c: c.distance_from_source_km)
    r.tributaries = out


def _read_ends(r: River, stem, dem, basin) -> None:
    """Elevation at the source and the mouth, from the DEM."""
    prof = _build_profile(r, 200, dem=dem, stem=stem, basin=basin)
    if prof is None or len(prof) < 2:
        return
    r.source_elev_m = round(float(prof["elevation_m"].iloc[0]), 1)
    r.mouth_elev_m = round(float(prof["elevation_m"].iloc[-1]), 1)
    r._profile = prof


def _build_profile(r: River, n: int, dem=None, stem=None, basin=None):
    """Sample the stem at n points and read the DEM along it."""
    try:
        import geopandas as gpd
        import pandas as pd
        import xarray as xr
        from shapely.geometry import LineString, Point
    except ImportError:                                  # pragma: no cover
        return None

    stem = r.main_stem if stem is None else stem
    basin = r.basin if basin is None else basin
    lat, lon = basin.centroid
    crs = _laea(lat, lon)
    m = stem.to_crs(crs)

    coords: list[tuple[float, float]] = []
    for g in m.geometry:
        for part in getattr(g, "geoms", [g]):
            for xy in part.coords:
                if not coords or coords[-1] != xy[:2]:
                    coords.append(xy[:2])
    if len(coords) < 2:
        return None
    line = LineString(coords)

    dists = [line.length * i / (n - 1) for i in range(n)]
    pts = [line.interpolate(d) for d in dists]
    gs = gpd.GeoSeries([Point(p.x, p.y) for p in pts], crs=crs)

    elev = dem if dem is not None else basin.dem()
    dem_crs = getattr(getattr(elev, "rio", None), "crs", None) or "EPSG:4326"
    ll = gs.to_crs(dem_crs)
    xname = "x" if "x" in elev.coords else "longitude"
    yname = "y" if "y" in elev.coords else "latitude"
    z = elev.sel({xname: xr.DataArray([p.x for p in ll], dims="s"),
                  yname: xr.DataArray([p.y for p in ll], dims="s")},
                 method="nearest").values
    z = np.asarray(z, dtype="float64").ravel()

    ok = np.isfinite(z)
    if ok.sum() < 2:
        return None
    z = np.where(ok, z, np.nan)
    z = pd.Series(z).ffill().bfill().to_numpy()
    z = np.minimum.accumulate(z)                 # condition to fall downstream

    km = np.asarray(dists) / 1000.0
    seg = (m.geometry.length / 1000.0).to_numpy()
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    upland = np.asarray(stem.get("UPLAND_SKM", [np.nan] * len(stem)), dtype="float64")
    disch = np.asarray(stem.get("DIS_AV_CMS", [np.nan] * len(stem)), dtype="float64")
    idx = np.clip(np.searchsorted(cum, km, side="right") - 1, 0, len(stem) - 1)

    ll4326 = gs.to_crs("EPSG:4326")
    return pd.DataFrame({
        "distance_km": np.round(km, 4),
        "elevation_m": np.round(z, 2),
        "upland_km2": np.round(upland[idx], 2),
        "discharge_cms": np.round(disch[idx], 4),
        "lat": np.round([p.y for p in ll4326], 5),
        "lon": np.round([p.x for p in ll4326], 5),
    })
