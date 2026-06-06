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

# Southern frame clamp ≈ the actual NH/MA border (southernmost NH point is
# ~42.697°N). The displayed region's south edge is never pushed below this, so
# Massachusetts tiles (Worcester 42.26, Boston 42.36, Springfield 42.10 — all
# well south of here) are cut off while every NH event town stays in frame.
NH_MA_BORDER = 42.70

# Static NH town → (lat, lon) gazetteer (town centres). Resolved FIRST so the
# common case needs NO network call — the per-render OSM Nominatim lookups were
# being blocked from Streamlit Cloud's IP (403/429/timeout), which is why prod
# showed "No events with locatable towns yet". Any town NOT here falls back to
# the Nominatim geocode. Keys are lowercased; lookups are case/whitespace
# insensitive. Covers the seacoast, Merrimack valley, Monadnock, Dartmouth–
# Sunapee, Lakes, and the North Country, plus the known event towns.
NH_TOWNS = {
    # Merrimack valley / capital area
    "concord": (43.208, -71.538), "manchester": (42.996, -71.455),
    "bow": (43.139, -71.546), "pembroke": (43.144, -71.456),
    "allenstown": (43.146, -71.397), "hooksett": (43.106, -71.465),
    "goffstown": (43.022, -71.600), "dunbarton": (43.103, -71.611),
    "weare": (43.092, -71.728), "hopkinton": (43.193, -71.679),
    "contoocook": (43.222, -71.711), "boscawen": (43.310, -71.623),
    "canterbury": (43.337, -71.555), "loudon": (43.285, -71.461),
    "chichester": (43.244, -71.398), "epsom": (43.220, -71.331),
    "pittsfield": (43.305, -71.324), "barnstead": (43.336, -71.273),
    "bedford": (42.946, -71.516), "merrimack": (42.865, -71.493),
    "litchfield": (42.844, -71.479), "hudson": (42.765, -71.439),
    "nashua": (42.766, -71.468), "amherst": (42.861, -71.628),
    "milford": (42.835, -71.649), "wilton": (42.843, -71.735),
    "lyndeborough": (42.911, -71.781), "mont vernon": (42.901, -71.674),
    "new boston": (42.973, -71.692), "hollis": (42.745, -71.591),
    "brookline": (42.732, -71.658), "pelham": (42.733, -71.325),
    "windham": (42.800, -71.305), "salem": (42.788, -71.201),
    "derry": (42.881, -71.327), "londonderry": (42.865, -71.374),
    "auburn": (42.998, -71.349), "candia": (43.078, -71.276),
    "deerfield": (43.127, -71.241), "raymond": (43.039, -71.183),
    "chester": (42.961, -71.252), "sandown": (42.928, -71.187),
    "danville": (42.911, -71.124), "hampstead": (42.879, -71.181),
    "atkinson": (42.838, -71.146), "plaistow": (42.837, -71.094),
    "newton": (42.866, -71.034), "kingston": (42.937, -71.054),
    "fremont": (42.991, -71.142), "brentwood": (42.978, -71.073),
    "epping": (43.033, -71.075), "northwood": (43.204, -71.149),
    "nottingham": (43.114, -71.099), "franklin": (43.444, -71.647),
    "tilton": (43.443, -71.589), "northfield": (43.433, -71.578),
    # Seacoast
    "portsmouth": (43.072, -70.762), "rye": (43.012, -70.773),
    "newington": (43.092, -70.823), "greenland": (43.035, -70.831),
    "stratham": (42.994, -70.901), "newfields": (43.038, -70.937),
    "newmarket": (43.082, -70.936), "exeter": (42.981, -70.948),
    "hampton": (42.937, -70.839), "hampton falls": (42.918, -70.861),
    "north hampton": (42.972, -70.829), "seabrook": (42.794, -70.871),
    "kensington": (42.926, -70.946), "east kingston": (42.928, -71.013),
    "south hampton": (42.871, -70.967), "durham": (43.134, -70.926),
    "lee": (43.123, -70.997), "madbury": (43.171, -70.926),
    "barrington": (43.219, -71.046), "dover": (43.198, -70.874),
    "somersworth": (43.262, -70.866), "rollinsford": (43.244, -70.819),
    "rochester": (43.305, -70.975), "farmington": (43.390, -71.064),
    "milton": (43.410, -70.987), "new durham": (43.438, -71.173),
    "middleton": (43.466, -71.067),
    # Monadnock region
    "keene": (42.934, -72.278), "swanzey": (42.869, -72.314),
    "marlborough": (42.904, -72.207), "troy": (42.824, -72.181),
    "fitzwilliam": (42.781, -72.142), "rindge": (42.751, -72.009),
    "jaffrey": (42.814, -72.024), "peterborough": (42.871, -71.949),
    "dublin": (42.906, -72.062), "harrisville": (42.939, -72.097),
    "hancock": (42.978, -71.990), "greenfield": (42.949, -71.873),
    "bennington": (43.001, -71.926), "antrim": (43.063, -71.939),
    "francestown": (42.989, -71.811), "deering": (43.069, -71.844),
    "hillsborough": (43.114, -71.900), "henniker": (43.180, -71.821),
    "warner": (43.278, -71.821), "bradford": (43.270, -71.959),
    "new ipswich": (42.748, -71.864), "greenville": (42.767, -71.812),
    "temple": (42.821, -71.851), "sharon": (42.789, -71.910),
    "winchester": (42.773, -72.383), "hinsdale": (42.786, -72.487),
    "chesterfield": (42.889, -72.471), "westmoreland": (42.962, -72.444),
    "walpole": (43.077, -72.428), "charlestown": (43.238, -72.425),
    "alstead": (43.149, -72.360), "stoddard": (43.073, -72.099),
    "washington": (43.176, -72.103), "nelson": (42.992, -72.131),
    # Dartmouth–Sunapee
    "new london": (43.412, -71.985), "newport": (43.366, -72.174),
    "sunapee": (43.388, -72.087), "sutton": (43.330, -71.945),
    "andover": (43.435, -71.823),
    "wilmot": (43.457, -71.911), "springfield": (43.498, -72.040),
    "grantham": (43.491, -72.139), "croydon": (43.464, -72.159),
    "cornish": (43.480, -72.302), "plainfield": (43.539, -72.270),
    "claremont": (43.377, -72.347), "lebanon": (43.642, -72.252),
    "hanover": (43.703, -72.289), "enfield": (43.642, -72.144),
    "canaan": (43.648, -72.016), "grafton": (43.567, -71.951),
    "danbury": (43.524, -71.862), "bristol": (43.592, -71.737),
    "alexandria": (43.611, -71.812), "hebron": (43.690, -71.808),
    # Lakes region
    "laconia": (43.528, -71.470), "gilford": (43.547, -71.409),
    "belmont": (43.445, -71.481), "sanbornton": (43.508, -71.591),
    "meredith": (43.658, -71.500), "center harbor": (43.713, -71.461),
    "moultonborough": (43.755, -71.395), "sandwich": (43.793, -71.409),
    "holderness": (43.732, -71.589), "ashland": (43.696, -71.631),
    "new hampton": (43.604, -71.652), "alton": (43.452, -71.216),
    "gilmanton": (43.424, -71.413), "wolfeboro": (43.585, -71.207),
    "tuftonboro": (43.683, -71.222), "ossipee": (43.685, -71.117),
    "wakefield": (43.566, -71.030), "tamworth": (43.860, -71.270),
    "plymouth": (43.757, -71.688), "campton": (43.838, -71.638),
    "rumney": (43.806, -71.813),
    # White Mountains / North Country
    "lincoln": (44.043, -71.671), "woodstock": (44.005, -71.685),
    "conway": (43.979, -71.121), "north conway": (44.053, -71.128),
    "madison": (43.901, -71.146), "bartlett": (44.085, -71.286),
    "jackson": (44.146, -71.186), "franconia": (44.224, -71.747),
    "bethlehem": (44.281, -71.690), "littleton": (44.306, -71.770),
    "lisbon": (44.218, -71.908), "bath": (44.168, -71.969),
    "haverhill": (44.036, -72.063), "lyme": (43.806, -72.157),
    "orford": (43.907, -72.140), "whitefield": (44.373, -71.612),
    "lancaster": (44.489, -71.571), "jefferson": (44.413, -71.484),
    "gorham": (44.388, -71.173), "berlin": (44.469, -71.185),
    "colebrook": (44.894, -71.496),
}


def _normalize_city(name: str) -> str:
    # Lowercase and drop a trailing state suffix ("nh" preceded by a comma
    # and/or whitespace), so "Concord", "Concord NH", "Concord, NH", and
    # "Concord,NH" all match the gazetteer key "concord". Commas become spaces
    # and internal whitespace collapses, so multi-word keys still match.
    key = (name or "").strip().lower().replace(",", " ")
    parts = key.split()
    if len(parts) >= 2 and parts[-1] == "nh":
        parts = parts[:-1]
    return " ".join(parts)


def _resolve_city(city_name: str):
    """Resolve a town to (lat, lon): the static NH gazetteer FIRST (no network),
    falling back to the Nominatim geocode only for towns not in the table. The
    Nominatim result is cached per session by ``_geocode_city`` so an unknown
    town is looked up at most once."""
    key = _normalize_city(city_name)
    if not key:
        return None
    if key in NH_TOWNS:
        return NH_TOWNS[key]
    return _geocode_city(city_name)


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
            coords = _resolve_city(city)
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

        # Clamp the SOUTHERN edge to the NH/MA border so Massachusetts never
        # shows. Never rises above the southernmost marker (markers sit at
        # min_lat ≥ ~42.7, above this floor), so no event dot is cut off.
        sw[0] = max(sw[0], NH_MA_BORDER)

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
