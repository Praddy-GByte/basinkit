"""Visualisation. Composes with leafmap rather than competing with it."""

from __future__ import annotations

from .exceptions import MissingDependency


def explore(basin, *, dem: bool = False, rivers: bool = False, zoom: int | None = None,
            basemap: str = "OpenTopoMap", **kwargs):
    """Return an interactive leafmap/folium map of the basin.

    Deliberately returns a ``leafmap.Map`` rather than a bespoke widget, so
    anything already in that ecosystem keeps working on the result.
    """
    try:
        import leafmap
    except ImportError:
        try:
            return _folium_map(basin, rivers=rivers, zoom=zoom)
        except ImportError as exc:
            raise MissingDependency("leafmap", "viz") from exc

    import geopandas as gpd

    lat, lon = basin.centroid
    if zoom is None:
        area = basin.area_km2
        zoom = 11 if area < 100 else 9 if area < 2_000 else 7 if area < 50_000 else 5

    m = leafmap.Map(center=(lat, lon), zoom=zoom, **kwargs)
    try:
        m.add_basemap(basemap)
    except Exception:
        pass

    gdf = gpd.GeoDataFrame(
        {"area_km2": [round(basin.area_km2, 1)]},
        geometry=[basin.geometry], crs="EPSG:4326",
    )
    m.add_gdf(
        gdf, layer_name="Basin",
        style={"color": "#0b6fa4", "weight": 2.5, "fillOpacity": 0.12},
    )

    outlet = basin.provenance.get("snapped_outlet") or basin.provenance.get("outlet")
    if outlet:
        try:
            m.add_marker(location=tuple(outlet), tooltip="Outlet")
        except Exception:
            pass

    if rivers:
        try:
            net = basin.rivers(min_order=3, progress=False)
            if len(net):
                m.add_gdf(net, layer_name="Rivers",
                          style={"color": "#1e88e5", "weight": 1.2})
        except Exception:
            pass

    if dem:
        try:
            import tempfile

            fp = tempfile.NamedTemporaryFile(suffix=".tif", delete=False).name
            basin.dem(progress=False).rio.to_raster(fp)
            m.add_raster(fp, layer_name="Elevation", colormap="terrain")
        except Exception:
            pass

    return m


def _folium_map(basin, *, rivers: bool = False, zoom: int | None = None):
    import folium

    lat, lon = basin.centroid
    zoom = zoom or 8
    m = folium.Map(location=[lat, lon], zoom_start=zoom, tiles="OpenStreetMap")
    folium.GeoJson(
        basin.geometry.__geo_interface__,
        name="Basin",
        style_function=lambda _: {
            "color": "#0b6fa4", "weight": 2.5, "fillOpacity": 0.12
        },
    ).add_to(m)
    outlet = basin.provenance.get("outlet")
    if outlet:
        folium.Marker(list(outlet), tooltip="Outlet").add_to(m)
    folium.LayerControl().add_to(m)
    return m


def plot(basin, *, figsize=(12, 4.5), dem_product: str = "cop30"):
    """Static three-panel figure: elevation, boundary with rivers, hypsometry.

    The hypsometric curve is the panel worth looking at: its shape says whether
    a basin is young and steep or mature and low-relief, which is a first-order
    control on how fast it responds to rain.
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise MissingDependency("matplotlib", "viz") from exc

    import numpy as np

    fig, axes = plt.subplots(1, 3, figsize=figsize)

    elev = basin.dem(product=dem_product, progress=False)
    vals = np.asarray(elev.values, dtype="float64")

    im = axes[0].imshow(
        vals, cmap="terrain",
        extent=[float(elev.x.min()), float(elev.x.max()),
                float(elev.y.min()), float(elev.y.max())],
    )
    axes[0].set_title("Elevation (m)")
    fig.colorbar(im, ax=axes[0], shrink=0.8)

    import geopandas as gpd

    gdf = gpd.GeoDataFrame(geometry=[basin.geometry], crs="EPSG:4326")
    gdf.boundary.plot(ax=axes[1], color="#0b6fa4", linewidth=1.5)
    try:
        net = basin.rivers(min_order=3, progress=False)
        if len(net):
            net.plot(ax=axes[1], color="#1e88e5", linewidth=0.6)
    except Exception:
        pass
    outlet = basin.provenance.get("outlet")
    if outlet:
        axes[1].plot(outlet[1], outlet[0], "o", color="#c62828", markersize=6)
    axes[1].set_title(f"{basin.area_km2:,.0f} km2")
    axes[1].set_aspect("equal")

    finite = vals[np.isfinite(vals)]
    if finite.size:
        heights = np.sort(finite)[::-1]
        rel_area = np.arange(1, heights.size + 1) / heights.size
        # np.ptp(a), not a.ptp() -- the ndarray method was removed in NumPy 2.0,
        # and pyproject allows numpy>=1.24, so the method form breaks on any
        # current install.
        rel_h = (heights - heights.min()) / max(float(np.ptp(heights)), 1e-9)
        axes[2].plot(rel_area, rel_h, color="#0b6fa4")
        axes[2].fill_between(rel_area, rel_h, alpha=0.15, color="#0b6fa4")
        axes[2].set_xlabel("Relative area")
        axes[2].set_ylabel("Relative height")
        axes[2].set_title(f"Hypsometry (HI = {rel_h.mean():.2f})")

    fig.tight_layout()
    return fig
