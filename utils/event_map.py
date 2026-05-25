"""
Event map — single source of truth for the dashboard's NH event map and the
host/facilitator portal "Event Map" tab.

Lifted verbatim from the inline block that lived in app.py:148-251 so the
dashboard and the portal render the same map. Behaviour is unchanged:
- folium + streamlit_folium for the rendered tiles
- geopy Nominatim, geocoding "{city}, NH" (the implicit NH constraint)
- per-session geocode cache via st.session_state plus @st.cache_resource
  on the geocoder factory so we don't re-instantiate per rerun
- fixed center (43.97, -71.57) zoom 8 with the CartoDB positron tiles
- same-city events nudged by +0.01° per duplicate to avoid stacking
- the per-event tooltip composition

Backend-agnostic: callers pass in already-fetched event rows and a
facilitators-by-event-id dict; this module imports no database backend.
"""
from __future__ import annotations

from html import escape as _esc

import streamlit as st


CENTER = (43.97, -71.57)
ZOOM = 8
TILES = "CartoDB positron"

# New Hampshire state bounding box — used by fit_bounds as the PRIMARY framing
# so the entire state (north and south together) is visible on open, and by
# max_bounds so panning stays around the state. SW corner (lat, lon) → NE
# corner (lat, lon).
#
# Earlier iterations framed on the event markers instead; events cluster in
# central/southern NH, so the opening view excluded northern towns and the
# previously raised MIN_ZOOM=8 floor made the whole state unreachable. Frame
# the whole state and lower MIN_ZOOM to 6 so the full-state fit can actually
# land (whole-state fits land around zoom 7 in this panel). MAX_ZOOM still
# caps zoom-in.
NH_BOUNDS = [[42.70, -72.56], [45.31, -70.61]]
MIN_ZOOM = 6
MAX_ZOOM = 12
FIT_PADDING = (40, 40)


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


def render_event_map(events, facs_by_event=None, *, height=500):
    """Render the NH event map. Identical to the original dashboard block.

    Parameters
    ----------
    events : iterable of dict-like rows
        Each row must carry at minimum: event_id, event_name, event_date,
        city, host_name (optional), venue_name (optional).
    facs_by_event : dict[int, list[str]] | None
        Optional mapping event_id -> [facilitator names] for the tooltip.
        If omitted, the facilitator line of the tooltip shows "—".
    height : int
        Rendered map height in pixels. Defaults to 500 (same as the
        dashboard's historical value).

    Notes
    -----
    Wrapped in try/except ImportError so a missing optional dep degrades
    to an st.info(...) just like the original inline block did. The
    caller does NOT need to wrap; this function never raises on a
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
        nh_map = folium.Map(
            location=list(CENTER),
            zoom_start=ZOOM,
            tiles=TILES,
            min_zoom=MIN_ZOOM,
            max_zoom=MAX_ZOOM,
            max_bounds=True,
        )
        town_idx = {}
        points = []
        plotted = 0
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
            lat = coords[0] + (i * 0.01)
            lon = coords[1] + (i * 0.01)

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
            points.append([lat, lon])
            plotted += 1

        # Primary framing: fit the WHOLE state of NH (north + south together).
        # Events live inside the state, so the whole-state view already
        # includes them — fitting to event markers instead would clip out the
        # north on the typical wide/short map panel.
        nh_map.fit_bounds(NH_BOUNDS)
        st_folium(nh_map, width="100%", height=height, returned_objects=[])
        if plotted == 0:
            st.caption(
                "No events with locatable towns yet — add a city to an "
                "event to see it on the map."
            )
        else:
            st.caption(f"📍 {plotted} event{'s' if plotted != 1 else ''} mapped")
    except Exception as _map_err:
        st.warning(f"🗺️ Map could not be rendered: {_map_err}")
