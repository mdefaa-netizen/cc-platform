import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from utils.database import (init_db, init_mileage, get_dashboard_stats, get_overdue_tasks,
                             get_upcoming_events, get_all_communications,
                             get_all_tasks, get_activity_log, init_activity_log,
                             get_notifications, get_unread_count, mark_notifications_read,
                             get_unread_message_count, init_messages, get_all_messages,
                             init_users, get_user_by_username, verify_password)
try:
    from utils.database import init_all
except ImportError:
    init_all = None
from utils.styles import inject_css, page_header

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

ROLE_LABELS = {
    "coordinator": "Coordinator",
    "nhh":         "NHH Colleague",
    "cdfa":        "CDFA Colleague",
    "facilitator": "Facilitator",
    "host":        "Host",
}

def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
        st.session_state.user_role     = None
        st.session_state.user_label    = None
        st.session_state.username      = None
        st.session_state.linked_id     = None

    if st.session_state.authenticated:
        return True

    st.markdown("""
    <div style='max-width:440px;margin:5rem auto;background:white;padding:2.5rem 2rem;
    border-radius:14px;box-shadow:0 8px 32px rgba(0,0,0,0.12);'>
    <div style='text-align:center;margin-bottom:1.5rem'>
        <div style='font-size:2.5rem'>🗺️</div>
        <h2 style='font-family:Playfair Display,serif;color:#1B2A4A;margin:0.5rem 0 0.2rem'>
            Community Conversations</h2>
        <p style='color:#7F8C8D;font-size:0.9rem;margin:0'>
            NH Humanities & CDFA Coordinator Platform</p>
    </div>
    """, unsafe_allow_html=True)

    username = st.text_input("Username", placeholder="Enter your username")
    pwd = st.text_input("Password", type="password", placeholder="Enter your password")
    if st.button("Sign In", use_container_width=True):
        if username and pwd:
            user = get_user_by_username(username.strip().lower())
            if user and verify_password(pwd, user["password_hash"]):
                st.session_state.authenticated = True
                st.session_state.user_role     = user["role"]
                st.session_state.user_label    = ROLE_LABELS.get(user["role"], user["role"].title())
                st.session_state.username      = user["username"]
                st.session_state.linked_id     = user.get("linked_id")
                st.rerun()
            else:
                st.error("Invalid username or password.")
        else:
            st.error("Please enter both username and password.")

    st.markdown("""
    <div style='margin-top:1.5rem;padding-top:1rem;border-top:1px solid #eee;font-size:0.8rem;color:#aaa;text-align:center'>
        Coordinator · NHH · CDFA · Facilitator · Host
    </div></div>
    """, unsafe_allow_html=True)
    return False

if not check_password():
    st.stop()

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

with st.sidebar:
    st.markdown(f"""
    <div style='text-align:center;padding:0.8rem 0 0.3rem'>
        <div style='font-size:1.8rem'>🗺️</div>
        <div style='font-family:Playfair Display,serif;font-size:1rem;font-weight:700;
        color:white;line-height:1.2'>Community Conversations</div>
        <div style='font-size:0.7rem;color:#aab;margin-top:0.2rem'>NH Humanities & CDFA</div>
        <div style='margin-top:0.4rem;background:#ffffff22;border-radius:6px;
        padding:3px 8px;font-size:0.72rem;color:#7dd'>
        Signed in as: <strong>{label}</strong></div>
    </div>
    <hr style='border-color:#ffffff22;margin:0.5rem 0'>
    """, unsafe_allow_html=True)

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
        st.page_link("pages/12_Settings.py",       label="⚙️  Settings",         use_container_width=True)
    elif role in ("cdfa", "nhh"):
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

    st.markdown("<hr style='border-color:#ffffff22;margin:0.5rem 0'>", unsafe_allow_html=True)
    if st.button("🔒 Sign Out", use_container_width=True):
        st.session_state.clear()
        st.rerun()


# ── Dashboard ──────────────────────────────────────────────────────────────────
page_header("🏠 Dashboard", "Program overview · Real-time activity · All collaborators")

# Role banner for NHH/CDFA
if not is_coordinator:
    st.markdown(f"""
    <div style='background:#EBF5FB;border-left:4px solid #2A7F7F;padding:0.8rem 1rem;
    border-radius:0 8px 8px 0;margin-bottom:1rem'>
        👋 Welcome, <strong>{label}</strong>. You have <strong>read-only</strong> access
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
            🔔 {n.get('message','')} <span style='color:#aaa;font-size:0.78rem'> · {ts}</span>
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

col_left, col_right = st.columns([3, 2])

with col_left:
    st.markdown("### 📅 Upcoming Events (Next 30 Days)")
    upcoming_evs = get_upcoming_events(30)
    if upcoming_evs:
        for ev in upcoming_evs:
            st.markdown(f"""
            <div class="section-box" style='margin-bottom:0.6rem;padding:0.8rem 1rem'>
                <div style='display:flex;justify-content:space-between;align-items:center'>
                    <div><strong>{ev['event_name']}</strong>
                    <span style='color:#7F8C8D;font-size:0.85rem'> · {ev.get('city','')}</span></div>
                    <div style='text-align:right;font-size:0.85rem;color:#2A7F7F'>
                        <strong>{ev['event_date']}</strong>
                        {(' · '+ev['event_time']) if ev.get('event_time') else ''}</div>
                </div>
                <div style='font-size:0.82rem;color:#7F8C8D;margin-top:0.2rem'>
                    Host: {ev.get('host_name','—')}</div>
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
                <div class='overdue-title'>{t['task_title']}</div>
                <div class='overdue-meta'>Due: {t.get('due_date','')} · {t.get('priority','')} priority</div>
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
                🔴 <strong>{m.get('sender_name','Unknown')}</strong> ({m.get('sender_type','').title()})
                · {m.get('category','')} · {m.get('subject','')[:40]}
                <span style='color:#aaa;font-size:0.8rem'> · {ts}</span>
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
                {icon} <strong>{a.get('action','')}</strong>
                <div class="feed-date">{ts} · by {user}</div>
                <div style='font-size:0.8rem;color:#555'>{a.get('details','')}</div>
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
                📧 <strong>{c.get('subject','')[:45]}</strong>
                <div class="feed-date">{date_str} · {c.get('recipient_type','')} · {c.get('communication_type','')}</div>
            </div>""", unsafe_allow_html=True)
    else:
        st.caption("No communications logged yet.")
