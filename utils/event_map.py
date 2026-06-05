"""
Event map — single source of truth for the dashboard's NH event map and the
host/facilitator portal "Event Map" tab.

Lifted verbatim from the inline block that lived in app.py:148-251 so the
dashboard and the portal render the same map. Behaviour is unchanged EXCEPT
for the framing:
- folium + streamlit_folium for the rendered tiles
- geopy Nominatim, geocoding "{city}, NH" (the implicit NH constraint)
- per-session geocode cache via st.session_state plus @st.cache_resource
  on the geocoder factory so we don't re-instantiate per rerun
- CartoDB positron tiles
- same-city events nudged by +0.01° per duplicate to avoid stacking
- the per-event tooltip composition
- FRAMING: the view fits the bounding box of the ACTUAL event markers
  (southern/central NH) with modest padding, and is LOCKED to that box —
  ``max_bounds`` so panning can't leave it and ``min_zoom`` so the user can't
  zoom out past the event region.

Backend-agnostic: callers pass in already-fetched event rows and a
facilitators-by-event-id dict; this module imports no database backend.
"""
from __future__ import annotations

import math
from html import escape as _esc

import streamlit as st


TILES = "CartoDB positron"
MAX_ZOOM = 12

# Fallback frame (southern/central New Hampshire) used ONLY when no event town
# geocodes — so an empty map still opens on the event region, not the world.
# SW corner (lat, lon) → NE corner (lat, lon).
FALLBACK_SW = (42.70, -72.30)
FALLBACK_NE = (44.20, -70.80)

# Padding added around the computed event bounding box: a fraction of the span
# with a small floor in degrees, so a single town or a tight cluster isn't
# over-zoomed into a featureless tile.
PAD_FRACTION = 0.15
PAD_FLOOR_DEG = 0.12


@st.cache_resource
def _nh_geocoder():
    from geopy.geocoders import Nominatim
    return Nominatim(user_agent="cc-platform-nh-map")


def _geocode_city(city_name: str):
    """Look up '{city}, NH' via Nominatim, memoised per session.

    Catches geopy + generic exceptions so a flaky lookup degrades to a
    silent miss (the marker simply isn't plotted) rather than killing
    the page render."""
    from geopy.exc import GeocoderServiceError, GeocoderTimedOut

    if "_geo_cache" not in st.session_state:
        st.session_state._geo_cache = {}
    cache = st.session_state._geo_cache

    if not city_name:
        return None
    key = city_name.strip().lower()
    if key in cache:
        return cache[key]
    try:
        loc = _nh_geocoder().geocode(f"{city_name}, NH", timeout=5)
        coords = (loc.latitude, loc.longitude) if loc else None
    except (GeocoderServiceError, GeocoderTimedOut, Exception):
        coords = None
    cache[key] = coords
    return coords


def _bounds_zoom_level(sw, ne, *, map_px=(700, 480), max_z=MAX_ZOOM):
    """Largest integer zoom at which the (sw, ne) box still fits a ~map_px
    viewport. Used as BOTH the opening zoom and the ``min_zoom`` floor so the
    user can't zoom out past the event region. Standard Web Mercator fit math
    (the Google ``getBoundsZoomLevel`` algorithm)."""
    WORLD_DIM = 256.0

    def _lat_rad(lat):
        s = math.sin(math.radians(lat))
        x = math.log((1 + s) / (1 - s)) / 2
        return max(min(x, math.pi), -math.pi) / 2

    def _zoom(map_dim, world_dim, fraction):
        if fraction <= 0:
            return max_z
        return math.floor(math.log(map_dim / world_dim / fraction) / math.log(2))

    lat_fraction = (_lat_rad(ne[0]) - _lat_rad(sw[0])) / math.pi
    lon_diff = ne[1] - sw[1]
    lon_fraction = ((lon_diff + 360) % 360) / 360
    lat_zoom = _zoom(map_px[1], WORLD_DIM, lat_fraction)
    lon_zoom = _zoom(map_px[0], WORLD_DIM, lon_fraction)
    return int(max(0, min(lat_zoom, lon_zoom, max_z)))


def render_event_map(events, facs_by_event=None, *, height=500):
    """Render the NH event map, framed and locked to the event region.

    Parameters
    ----------
    events : iterable of dict-like rows
        Each row must carry at minimum: event_id, event_name, event_date,
        city, host_name (optional), venue_name (optional).
    facs_by_event : dict[int, list[str]] | None
        Optional mapping event_id -> [facilitator names] for the tooltip.
        If omitted, the facilitator line of the tooltip shows "—".
    height : int
        Rendered map height in pixels. Defaults to 500.

    The view fits the bounding box of the geocoded event markers (southern/
    central NH) with modest padding and is locked there: ``max_bounds`` stops
    panning outside the box and ``min_zoom`` stops zooming out past it. Marker
    geocoding, the +0.01° same-city nudge, styling, and tooltips are unchanged.

    Wrapped in try/except ImportError so a missing optional dep degrades to an
    st.info(...). The caller does NOT need to wrap; this never raises on a
    library import miss.
    """
    facs_by_event = facs_by_event or {}

    try:
        import folium
        from streamlit_folium import st_folium
        from datetime import datetime as _dt
    except ImportError as _map_ie:
        st.info(
            f"🗺️ Map unavailable — install dependencies: "
            f"`pip install folium streamlit-folium geopy` ({_map_ie})."
        )
        return

    try:
        # Pass 1 — geocode every event city and build the plot list, applying
        # the same per-duplicate-city +0.01° nudge so markers don't stack.
        town_idx = {}
        plot = []  # list of (lat, lon, ev)
        for ev in events:
            city = (ev.get("city") or "").strip()
            if not city:
                continue
            coords = _geocode_city(city)
            if not coords:
                continue
            key = city.lower()
            i = town_idx.get(key, 0)
            town_idx[key] = i + 1
            plot.append((coords[0] + (i * 0.01), coords[1] + (i * 0.01), ev))

        # Compute the event-region bounding box (+ padding). Fall back to a
        # southern/central NH frame when nothing geocoded.
        if plot:
            lats = [p[0] for p in plot]
            lons = [p[1] for p in plot]
            min_lat, max_lat = min(lats), max(lats)
            min_lon, max_lon = min(lons), max(lons)
            pad_lat = max((max_lat - min_lat) * PAD_FRACTION, PAD_FLOOR_DEG)
            pad_lon = max((max_lon - min_lon) * PAD_FRACTION, PAD_FLOOR_DEG)
            sw = [min_lat - pad_lat, min_lon - pad_lon]
            ne = [max_lat + pad_lat, max_lon + pad_lon]
        else:
            sw, ne = list(FALLBACK_SW), list(FALLBACK_NE)

        region_bounds = [sw, ne]
        fit_zoom = _bounds_zoom_level(sw, ne, max_z=MAX_ZOOM)
        center = [(sw[0] + ne[0]) / 2.0, (sw[1] + ne[1]) / 2.0]

        # Build the map LOCKED to the event region: max_bounds (with the box as
        # min/max lat/lon) stops panning outside it; min_zoom == the region-fit
        # zoom stops zooming out past it.
        nh_map = folium.Map(
            location=center,
            zoom_start=fit_zoom,
            tiles=TILES,
            min_zoom=fit_zoom,
            max_zoom=MAX_ZOOM,
            max_bounds=True,
            min_lat=sw[0],
            max_lat=ne[0],
            min_lon=sw[1],
            max_lon=ne[1],
        )

        # Pass 2 — add the markers (styling + tooltip unchanged).
        for lat, lon, ev in plot:
            try:
                date_fmt = _dt.fromisoformat(
                    str(ev.get("event_date", ""))[:10]
                ).strftime("%B %d, %Y")
            except Exception:
                date_fmt = str(ev.get("event_date") or "")
            host_label = ev.get("venue_name") or ev.get("host_name") or "—"
            fac_label = ", ".join(facs_by_event.get(ev.get("event_id"), [])) or "—"
            tooltip_html = (
                f"<div style='font-size:0.85rem'>"
                f"<strong>{_esc(date_fmt)}</strong><br>"
                f"🏛️ {_esc(host_label)}<br>"
                f"🎤 {_esc(fac_label)}"
                f"</div>"
            )

            folium.CircleMarker(
                location=[lat, lon],
                radius=10,
                color="#2DD4BF",
                weight=2,
                fill=True,
                fill_color="#2DD4BF",
                fill_opacity=0.85,
                tooltip=folium.Tooltip(tooltip_html, sticky=True),
            ).add_to(nh_map)

        # Frame the event region (padded bbox). fit_bounds and min_zoom agree,
        # so the opening view IS the most-zoomed-out view available.
        nh_map.fit_bounds(region_bounds)
        st_folium(nh_map, width="100%", height=height, returned_objects=[])

        plotted = len(plot)
        if plotted == 0:
            st.caption(
                "No events with locatable towns yet — add a city to an "
                "event to see it on the map."
            )
        else:
            st.caption(f"📍 {plotted} event{'s' if plotted != 1 else ''} mapped")
    except Exception as _map_err:
        st.warning(f"🗺️ Map could not be rendered: {_map_err}")
