import streamlit as st
import sys, os
from html import escape as _esc
sys.path.insert(0, os.path.dirname(__file__))

from utils.database import (init_db, init_mileage, get_dashboard_stats, get_overdue_tasks,
                             get_upcoming_events, get_all_communications,
                             get_all_tasks, get_activity_log, init_activity_log,
                             get_notifications, get_unread_count, mark_notifications_read,
                             get_unread_message_count, init_messages, get_all_messages,
                             init_users, get_connection)
try:
    from utils.database import init_all
except ImportError:
    init_all = None
from utils.styles import inject_css, page_header
from utils.auth import require_auth, render_sidebar_user, ensure_bootstrap_coordinator

st.set_page_config(
    page_title="Community Conversations Coordinator",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()
if init_all:
    init_all()   # single DB connection for all tables
else:
    init_db(); init_activity_log(); init_messages(); init_mileage(); init_users()
ensure_bootstrap_coordinator()

require_auth()

role  = st.session_state.get("user_role", "coordinator")
label = st.session_state.get("user_label", "Coordinator")
is_coordinator = (role == "coordinator")

# Facilitator/Host roles redirect to the portal page
if role in ("facilitator", "host"):
    st.switch_page("pages/0_Portal.py")

# ── Sidebar ──────────────────────────────────────────────────────────────────
stats         = get_dashboard_stats()
overdue_count = stats.get("overdue_tasks", 0)
unread        = get_unread_count(role)
unread_msgs   = get_unread_message_count()

render_sidebar_user()

with st.sidebar:
    # Role-based navigation
    if role == "coordinator":
        st.page_link("app.py",                    label="🏠  Dashboard",        use_container_width=True)
        st.page_link("pages/2_Events.py",          label="📅  Events",           use_container_width=True)
        st.page_link("pages/3_Hosts.py",           label="👥  Hosts",            use_container_width=True)
        st.page_link("pages/4_Facilitators.py",    label="🎤  Facilitators",     use_container_width=True)
        st.page_link("pages/5_NHH_Colleagues.py",  label="🏛️  NHH Colleagues",  use_container_width=True)
        st.page_link("pages/6_CDFA_Colleagues.py", label="🌾  CDFA Colleagues",  use_container_width=True)
        st.page_link("pages/7_Payments.py",        label="💰  Payments",         use_container_width=True)
        st.page_link("pages/8_Communications.py",  label="📧  Communications",   use_container_width=True)
        st.page_link("pages/9_Tasks.py",           label=f"✅  Tasks {'(!)' if overdue_count else ''}",  use_container_width=True)
        st.page_link("pages/10_Reports.py",        label="📊  Reports",          use_container_width=True)
        st.page_link("pages/11_Feedback.py",       label="📝  Feedback",         use_container_width=True)
        st.page_link("pages/7_Payments.py",        label="🚗  Mileage",          use_container_width=True)
        st.page_link("pages/14_Messages.py",       label=f"💬  Messages {'(!)' if unread_msgs else ''}",   use_container_width=True)
        st.page_link("pages/13_Portal_Access.py",  label="🔑  Portal Access",    use_container_width=True)
        st.page_link("pages/15_Admin_Users.py",    label="👥  User Admin",       use_container_width=True)
        st.page_link("pages/12_Settings.py",       label="⚙️  Settings",         use_container_width=True)
    elif role in ("cdfa_staff", "nhh_staff"):
        st.page_link("app.py",                    label="🏠  Dashboard",        use_container_width=True)
        st.page_link("pages/2_Events.py",          label="📅  Events",           use_container_width=True)
        st.page_link("pages/3_Hosts.py",           label="👥  Hosts",            use_container_width=True)
        st.page_link("pages/4_Facilitators.py",    label="🎤  Facilitators",     use_container_width=True)
        st.page_link("pages/7_Payments.py",        label="💰  Payments",         use_container_width=True)
        st.page_link("pages/10_Reports.py",        label="📊  Reports",          use_container_width=True)
        st.page_link("pages/14_Messages.py",       label="💬  Messages",         use_container_width=True)
    elif role == "facilitator":
        st.page_link("pages/0_Portal.py",          label="📅  My Calendar",      use_container_width=True)
        st.page_link("pages/4_Facilitators.py",    label="🎤  My Profile",       use_container_width=True)
        st.page_link("pages/2_Events.py",          label="📅  My Events",        use_container_width=True)
        st.page_link("pages/14_Messages.py",       label="💬  Messages",         use_container_width=True)
    elif role == "host":
        st.page_link("pages/0_Portal.py",          label="📅  My Calendar",      use_container_width=True)
        st.page_link("pages/2_Events.py",          label="📅  My Events",        use_container_width=True)
        st.page_link("pages/3_Hosts.py",           label="👥  My Profile",       use_container_width=True)
        st.page_link("pages/14_Messages.py",       label="💬  Messages",         use_container_width=True)


# ── Dashboard ──────────────────────────────────────────────────────────────────
page_header("🏠 Dashboard", "Program overview · Real-time activity · All collaborators")

# Role banner for NHH/CDFA
if not is_coordinator:
    st.markdown(f"""
    <div style='background:#EBF5FB;border-left:4px solid #2A7F7F;padding:0.8rem 1rem;
    border-radius:0 8px 8px 0;margin-bottom:1rem'>
        👋 Welcome, <strong>{_esc(label)}</strong>. You have <strong>read-only</strong> access
        to the Community Conversations coordination platform.
    </div>
    """, unsafe_allow_html=True)

# Notifications panel
notifs = get_notifications(role, unread_only=True)
if notifs:
    st.markdown(f"### 🔔 Notifications ({len(notifs)} unread)")
    for n in notifs[:5]:
        ts = str(n.get("created_at",""))[:16] if n.get("created_at") else ""
        st.markdown(f"""
        <div style='background:#FEF9E7;border-left:4px solid #C8963E;padding:0.7rem 1rem;
        border-radius:0 8px 8px 0;margin-bottom:0.5rem;font-size:0.88rem'>
            🔔 {_esc(n.get('message',''))} <span style='color:#aaa;font-size:0.78rem'> · {_esc(ts)}</span>
        </div>
        """, unsafe_allow_html=True)
    if st.button("✅ Mark all as read"):
        mark_notifications_read(role)
        st.rerun()
    st.markdown("---")

# KPI Row
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(f"""<div class="kpi-card">
    <div class="kpi-label">Total Events</div><div class="kpi-value">{stats['total_events']}</div>
    <div class="kpi-sub">{stats['scheduled']} scheduled · {stats['completed']} completed</div>
    </div>""", unsafe_allow_html=True)
with c2:
    st.markdown(f"""<div class="kpi-card gold">
    <div class="kpi-label">All Contacts</div>
    <div class="kpi-value">{stats['total_hosts']+stats['total_facilitators']+stats.get('total_nhh',0)+stats.get('total_cdfa',0)}</div>
    <div class="kpi-sub">{stats['total_hosts']} hosts · {stats['total_facilitators']} facilitators · {stats.get('total_nhh',0)} NHH · {stats.get('total_cdfa',0)} CDFA</div>
    </div>""", unsafe_allow_html=True)
with c3:
    st.markdown(f"""<div class="kpi-card red">
    <div class="kpi-label">Facilitator Payments</div>
    <div class="kpi-value">${stats['pending_payment_total']:,.2f}</div>
    <div class="kpi-sub">{stats['pending_payment_count']} pending/approved/sent</div>
    </div>""", unsafe_allow_html=True)
with c4:
    st.markdown(f"""<div class="kpi-card {'red' if overdue_count else 'green'}">
    <div class="kpi-label">Overdue Tasks</div><div class="kpi-value">{overdue_count}</div>
    <div class="kpi-sub">{'Action required' if overdue_count else 'All on track'}</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Event Map ──────────────────────────────────────────────────────────────────
st.markdown("### 🗺️ Event Map — New Hampshire")

try:
    import folium
    from streamlit_folium import st_folium
    from geopy.geocoders import Nominatim
    from geopy.exc import GeocoderServiceError, GeocoderTimedOut
    from datetime import datetime as _dt

    @st.cache_resource
    def _nh_geocoder():
        return Nominatim(user_agent="cc-platform-nh-map")

    if "_geo_cache" not in st.session_state:
        st.session_state._geo_cache = {}
    _geo_cache = st.session_state._geo_cache

    def _geocode_city(city_name: str):
        if not city_name:
            return None
        key = city_name.strip().lower()
        if key in _geo_cache:
            return _geo_cache[key]
        try:
            loc = _nh_geocoder().geocode(f"{city_name}, NH", timeout=5)
            coords = (loc.latitude, loc.longitude) if loc else None
        except (GeocoderServiceError, GeocoderTimedOut, Exception):
            coords = None
        _geo_cache[key] = coords
        return coords

    _map_conn = get_connection()
    _map_rows = _map_conn.execute("""
        SELECT e.event_id, e.event_name, e.event_date, e.city,
               h.name AS host_name, h.venue_name
        FROM events e
        LEFT JOIN hosts h ON e.host_id = h.host_id
        ORDER BY e.event_date
    """).fetchall()
    _fac_rows = _map_conn.execute("""
        SELECT ef.event_id, f.name AS facilitator_name
        FROM event_facilitators ef
        JOIN facilitators f ON f.facilitator_id = ef.facilitator_id
    """).fetchall()
    _map_conn.close()

    _facs_by_event = {}
    for _fr in _fac_rows:
        _facs_by_event.setdefault(_fr["event_id"], []).append(_fr["facilitator_name"])

    nh_map = folium.Map(
        location=[43.97, -71.57],
        zoom_start=8,
        tiles="CartoDB positron",
    )
    _town_idx = {}
    _plotted = 0
    for _ev in _map_rows:
        _city = (_ev["city"] or "").strip()
        if not _city:
            continue
        _coords = _geocode_city(_city)
        if not _coords:
            continue
        _key = _city.lower()
        _i = _town_idx.get(_key, 0)
        _town_idx[_key] = _i + 1
        _lat = _coords[0] + (_i * 0.01)
        _lon = _coords[1] + (_i * 0.01)

        try:
            _date_fmt = _dt.fromisoformat(str(_ev["event_date"])[:10]).strftime("%B %d, %Y")
        except Exception:
            _date_fmt = str(_ev["event_date"] or "")
        _host_label = _ev["venue_name"] or _ev["host_name"] or "—"
        _fac_label = ", ".join(_facs_by_event.get(_ev["event_id"], [])) or "—"
        _tooltip_html = (
            f"<div style='font-size:0.85rem'>"
            f"<strong>{_esc(_date_fmt)}</strong><br>"
            f"🏛️ {_esc(_host_label)}<br>"
            f"🎤 {_esc(_fac_label)}"
            f"</div>"
        )

        folium.CircleMarker(
            location=[_lat, _lon],
            radius=10,
            color="#2DD4BF",
            weight=2,
            fill=True,
            fill_color="#2DD4BF",
            fill_opacity=0.85,
            tooltip=folium.Tooltip(_tooltip_html, sticky=True),
        ).add_to(nh_map)
        _plotted += 1

    st_folium(nh_map, width="100%", height=500, returned_objects=[])
    if _plotted == 0:
        st.caption("No events with locatable towns yet — add a city to an event to see it on the map.")
    else:
        st.caption(f"📍 {_plotted} event{'s' if _plotted != 1 else ''} mapped")
except ImportError as _map_ie:
    st.info(f"🗺️ Map unavailable — install dependencies: `pip install folium streamlit-folium geopy` ({_map_ie}).")
except Exception as _map_err:
    st.warning(f"🗺️ Map could not be rendered: {_map_err}")

st.markdown("<br>", unsafe_allow_html=True)

col_left, col_right = st.columns([3, 2])

with col_left:
    st.markdown("### 📅 Upcoming Events (Next 30 Days)")
    upcoming_evs = get_upcoming_events(30)
    if upcoming_evs:
        for ev in upcoming_evs:
            st.markdown(f"""
            <div class="section-box" style='margin-bottom:0.6rem;padding:0.8rem 1rem'>
                <div style='display:flex;justify-content:space-between;align-items:center'>
                    <div><strong>{_esc(ev['event_name'])}</strong>
                    <span style='color:#7F8C8D;font-size:0.85rem'> · {_esc(ev.get('city',''))}</span></div>
                    <div style='text-align:right;font-size:0.85rem;color:#2A7F7F'>
                        <strong>{_esc(str(ev['event_date']))}</strong>
                        {(' · '+_esc(ev['event_time'])) if ev.get('event_time') else ''}</div>
                </div>
                <div style='font-size:0.82rem;color:#7F8C8D;margin-top:0.2rem'>
                    Host: {_esc(ev.get('host_name','—'))}</div>
            </div>""", unsafe_allow_html=True)
    else:
        st.info("No events scheduled in the next 30 days.")

with col_right:
    st.markdown("### ⚠️ Overdue Tasks")
    overdue = get_overdue_tasks()
    if overdue and is_coordinator:
        for t in overdue[:5]:
            st.markdown(f"""
            <div class='overdue-card'>
                <div class='overdue-title'>{_esc(t['task_title'])}</div>
                <div class='overdue-meta'>Due: {_esc(str(t.get('due_date','')))} · {_esc(t.get('priority',''))} priority</div>
            </div>""", unsafe_allow_html=True)
    elif not is_coordinator:
        st.info("Task management is available to the Coordinator.")
    else:
        st.success("No overdue tasks!")

# Quick Actions (coordinator only)
if is_coordinator:
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### ⚡ Quick Actions")
    qa1, qa2, qa3, qa4 = st.columns(4)
    with qa1:
        if st.button("➕ Add New Event",       use_container_width=True): st.switch_page("pages/2_Events.py")
    with qa2:
        if st.button("📧 Send Communication",  use_container_width=True): st.switch_page("pages/8_Communications.py")
    with qa3:
        if st.button("💰 Update Payment",      use_container_width=True): st.switch_page("pages/7_Payments.py")
    with qa4:
        if st.button("✅ Add Task",            use_container_width=True): st.switch_page("pages/9_Tasks.py")

# Inbox Panel (coordinator only)
if is_coordinator:
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(f"### 💬 Message Inbox ({unread_msgs} unread)")
    inbox_msgs = get_all_messages(unread_only=True)[:5]
    if inbox_msgs:
        for m in inbox_msgs:
            ts = str(m.get("created_at",""))[:16] if m.get("created_at") else ""
            st.markdown(f"""
            <div class="section-box" style='margin-bottom:0.5rem;padding:0.7rem 1rem'>
                🔴 <strong>{_esc(m.get('sender_name','Unknown'))}</strong> ({_esc(m.get('sender_type','').title())})
                · {_esc(m.get('category',''))} · {_esc(m.get('subject','')[:40])}
                <span style='color:#aaa;font-size:0.8rem'> · {_esc(ts)}</span>
            </div>""", unsafe_allow_html=True)
        if st.button("📬 View All Messages", use_container_width=False):
            st.switch_page("pages/14_Messages.py")
    else:
        st.success("📭 No unread messages.")

# Real-time Activity Feed
st.markdown("<br>", unsafe_allow_html=True)
st.markdown("### 📡 Real-Time Activity Feed")
st.caption("All actions across the platform — visible to Coordinator, NHH, and CDFA")

activity = get_activity_log(20)
comms    = get_all_communications()[:5]

col_act, col_comm = st.columns(2)

with col_act:
    st.markdown("**Recent Platform Activity**")
    if activity:
        for a in activity:
            ts   = str(a.get("logged_at",""))[:16] if a.get("logged_at") else ""
            user = a.get("user","Coordinator")
            icon = {"Event":"📅","Payment":"💰","Communication":"📧","Task":"✅",
                    "Host":"👥","Facilitator":"🎤","Feedback":"📝"}.get(
                    a.get("action","").split()[0] if a.get("action") else "","🔹")
            st.markdown(f"""
            <div class="feed-item">
                {icon} <strong>{_esc(a.get('action',''))}</strong>
                <div class="feed-date">{_esc(ts)} · by {_esc(user)}</div>
                <div style='font-size:0.8rem;color:#555'>{_esc(a.get('details',''))}</div>
            </div>""", unsafe_allow_html=True)
    else:
        st.caption("No activity logged yet. Actions will appear here in real time.")

with col_comm:
    st.markdown("**Recent Communications**")
    if comms:
        for c in comms:
            date_str = str(c.get("sent_date",""))[:10] if c.get("sent_date") else ""
            st.markdown(f"""
            <div class="feed-item">
                📧 <strong>{_esc(c.get('subject','')[:45])}</strong>
                <div class="feed-date">{_esc(date_str)} · {_esc(c.get('recipient_type',''))} · {_esc(c.get('communication_type',''))}</div>
            </div>""", unsafe_allow_html=True)
    else:
        st.caption("No communications logged yet.")
