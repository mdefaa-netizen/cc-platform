import streamlit as st
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.database import (
    get_all_events, get_event_facilitators, add_feedback,
    send_message, get_messages_for_person,
    get_notifications, mark_notifications_read,
    init_db, init_messages, init_portal_access,
    check_portal_login, add_notification
)
from utils.styles import inject_css

st.set_page_config(page_title="My Portal · Community Conversations",
                   page_icon="🗺️", layout="wide")
inject_css()
init_db()
init_messages()
init_portal_access()

# ── Portal Login ───────────────────────────────────────────────────────────────
if "portal_user" not in st.session_state:
    st.session_state.portal_user = None

def portal_login():
    st.markdown("""
    <div style='max-width:420px;margin:5rem auto;background:white;padding:2.5rem 2rem;
    border-radius:14px;box-shadow:0 8px 32px rgba(0,0,0,0.12)'>
    <div style='text-align:center;margin-bottom:1.5rem'>
        <div style='font-size:2.5rem'>🗺️</div>
        <h2 style='font-family:Playfair Display,serif;color:#1B2A4A;margin:0.5rem 0 0.2rem'>
            My Event Portal</h2>
        <p style='color:#7F8C8D;font-size:0.88rem;margin:0'>
            Community Conversations · NH Humanities & CDFA</p>
    </div>
    """, unsafe_allow_html=True)

    username = st.text_input("Username", placeholder="Your username")
    password = st.text_input("Password", type="password", placeholder="Your password")

    if st.button("Sign In", use_container_width=True):
        user = check_portal_login(username, password)
        if user:
            st.session_state.portal_user = user
            st.rerun()
        else:
            st.error("Invalid credentials or access not yet approved. Contact your coordinator.")

    st.markdown("""
    <div style='margin-top:1rem;font-size:0.78rem;color:#aaa;text-align:center'>
        Access provided by your NH Humanities & CDFA Coordinator
    </div></div>
    """, unsafe_allow_html=True)

if not st.session_state.portal_user:
    # If user logged in via main login as facilitator/host, auto-set portal_user
    main_role = st.session_state.get("user_role")
    main_linked = st.session_state.get("linked_id")
    if st.session_state.get("authenticated") and main_role in ("facilitator", "host") and main_linked:
        from utils.database import get_host, get_facilitator
        if main_role == "host":
            person = get_host(main_linked)
            st.session_state.portal_user = {
                "person_type": "host", "person_id": main_linked,
                "person_name": person["name"] if person else "Host",
            }
        else:
            person = get_facilitator(main_linked)
            st.session_state.portal_user = {
                "person_type": "facilitator", "person_id": main_linked,
                "person_name": person["name"] if person else "Facilitator",
            }
        st.rerun()
    elif st.session_state.get("authenticated"):
        st.info("You are signed in as Coordinator. This page is for hosts and facilitators.")
        st.stop()
    else:
        portal_login()
        st.stop()

# ── Portal Dashboard ───────────────────────────────────────────────────────────
puser       = st.session_state.portal_user
person_type = puser.get("person_type","")
person_id   = puser.get("person_id")
person_name = puser.get("person_name","")
person_type_label = "Host" if person_type == "host" else "Facilitator"

# Sidebar
with st.sidebar:
    st.markdown(f"""
    <div style='text-align:center;padding:1rem 0 0.5rem'>
        <div style='font-size:2rem'>🗺️</div>
        <div style='font-family:Playfair Display,serif;font-size:1rem;font-weight:700;
        color:white'>My Event Portal</div>
        <div style='font-size:0.75rem;color:#aab;margin-top:0.3rem'>
            {person_name}<br>{person_type_label}
        </div>
    </div>
    <hr style='border-color:#ffffff22'>
    """, unsafe_allow_html=True)

    if st.button("🔒 Sign Out", use_container_width=True):
        st.session_state.portal_user = None
        st.rerun()

# Header
st.markdown(f"""
<span class="program-title">NH Humanities & CDFA · Community Conversations</span>
<h1>Welcome, {person_name}</h1>
<span class="page-subtitle">Your event portal · {person_type_label}</span>
""", unsafe_allow_html=True)

# Notifications for this host/facilitator
portal_role = f"{person_type}_{person_id}"
notifs      = get_notifications(portal_role, unread_only=True)
if notifs:
    st.markdown(f"### 🔔 Updates for You ({len(notifs)})")
    for n in notifs:
        ts = str(n.get("created_at",""))[:16] if n.get("created_at") else ""
        st.markdown(f"""
        <div style='background:#FEF9E7;border-left:4px solid #C8963E;padding:0.7rem 1rem;
        border-radius:0 8px 8px 0;margin-bottom:0.5rem;font-size:0.9rem'>
            🔔 {n.get('message','')} <span style='color:#aaa;font-size:0.78rem'> · {ts}</span>
        </div>""", unsafe_allow_html=True)
    if st.button("✅ Mark all read"):
        mark_notifications_read(portal_role)
        st.rerun()
    st.markdown("---")

tab_cal, tab_msg, tab_feedback = st.tabs(["📅 My Events", "💬 Message Coordinator", "📝 Submit Feedback"])

# ── Calendar / My Events ───────────────────────────────────────────────────────
with tab_cal:
    st.markdown("### Your Upcoming Events")
    all_events = get_all_events()

    # Filter events relevant to this person
    my_events = []
    for e in all_events:
        if person_type == "host" and e.get("host_id") == person_id:
            my_events.append(e)
        elif person_type == "facilitator":
            facs = get_event_facilitators(e["event_id"])
            if any(f["facilitator_id"] == person_id for f in facs):
                my_events.append(e)

    if not my_events:
        st.info("No events assigned to you yet. Your coordinator will update this soon.")
    else:
        for e in my_events:
            status_color = {"Scheduled":"#2980B9","Completed":"#27AE60","Cancelled":"#C0392B"}.get(
                e.get("status",""),"#7F8C8D")
            badge = {"Scheduled":"🔵","Completed":"🟢","Cancelled":"🔴"}.get(e.get("status",""),"⚪")
            st.markdown(f"""
            <div class="section-box" style='margin-bottom:0.8rem'>
                <div style='display:flex;justify-content:space-between;align-items:flex-start'>
                    <div>
                        <strong style='font-size:1.1rem'>{e['event_name']}</strong>
                        <span style='color:{status_color};margin-left:0.5rem'>{badge} {e.get('status','')}</span>
                    </div>
                    <div style='text-align:right;color:#2A7F7F;font-weight:600'>
                        {e.get('event_date','')}
                        {(' · '+e['event_time']) if e.get('event_time') else ''}
                    </div>
                </div>
                <div style='margin-top:0.4rem;font-size:0.9rem;color:#555'>
                    📍 {e.get('venue_address','') or e.get('city','')+', NH'}
                </div>
                {f"<div style='margin-top:0.3rem;font-size:0.85rem;color:#7F8C8D'>Attendance: {e.get('attendance_count') or 'Not yet recorded'} {'✅' if e.get('attendance_confirmed') else ''}</div>" if e.get('status')=='Completed' else ''}
            </div>
            """, unsafe_allow_html=True)

# ── Message Coordinator ────────────────────────────────────────────────────────
with tab_msg:
    st.markdown("### Send a Message to the Coordinator")
    st.caption("Use this to communicate about your event, payment, schedule, or anything else.")

    all_events2 = get_all_events()
    my_event_opts = {}
    for e in all_events2:
        if person_type == "host" and e.get("host_id") == person_id:
            my_event_opts[e["event_id"]] = f"{e['event_name']} ({e['event_date']})"
        elif person_type == "facilitator":
            facs = get_event_facilitators(e["event_id"])
            if any(f["facilitator_id"] == person_id for f in facs):
                my_event_opts[e["event_id"]] = f"{e['event_name']} ({e['event_date']})"

    with st.form("send_message_form"):
        category = st.selectbox("Message Type", [
            "General",
            "Attendance — Record or update attendance",
            "Payment — Invoice, check, or payment question",
            "Delay — Request a delay or reschedule",
            "Problem — Report an issue or problem",
            "Information — Request information",
            "Feedback — Share feedback about the event",
            "Cancellation — Cancel or withdraw",
        ])
        cat_clean = category.split(" —")[0]

        rel_ev = st.selectbox("Related Event (optional)",
                               options=[""] + list(my_event_opts.keys()),
                               format_func=lambda x: "— None —" if x=="" else my_event_opts[x])
        subject = st.text_input("Subject *", placeholder="Brief summary of your message")
        body    = st.text_area("Message *", placeholder="Describe your question, issue, or request in detail...",
                                height=160)

        if st.form_submit_button("📤 Send Message", use_container_width=True):
            if not subject or not body:
                st.error("Subject and message are required.")
            else:
                send_message({
                    "sender_type":  person_type,
                    "sender_id":    person_id,
                    "sender_name":  person_name,
                    "event_id":     rel_ev or None,
                    "category":     cat_clean,
                    "subject":      subject,
                    "body":         body,
                })
                add_notification(
                    f"New message from {person_name} ({person_type_label}): {subject[:50]}",
                    "coordinator"
                )
                st.success("✅ Message sent to the Coordinator!")
                st.balloons()

    # Show message history
    st.markdown("---")
    st.markdown("### Your Message History")
    my_msgs = get_messages_for_person(person_type, person_id)
    if not my_msgs:
        st.caption("No messages yet.")
    else:
        for m in my_msgs:
            ts   = str(m.get("created_at",""))[:16] if m.get("created_at") else ""
            icon = {"General":"💬","Attendance":"📊","Payment":"💰","Delay":"⏰",
                    "Problem":"🚨","Information":"ℹ️","Feedback":"📝","Cancellation":"❌"}.get(
                    m.get("category","General"),"💬")
            with st.expander(f"{icon} {m.get('subject','')[:50]} · {ts}"):
                st.markdown(f"**{m.get('body','')}**")
                if m.get("reply_body"):
                    st.markdown("---")
                    st.markdown("**Coordinator's Reply:**")
                    st.success(m["reply_body"])
                    st.caption(f"Replied: {m.get('replied_at','')[:16] if m.get('replied_at') else ''}")
                else:
                    st.caption("⏳ Awaiting reply from Coordinator")

# ── Submit Feedback ────────────────────────────────────────────────────────────
with tab_feedback:
    st.markdown("### Submit Event Feedback")
    st.caption("Share your experience and observations from the event.")

    all_events3 = get_all_events()
    completed_my = {}
    for e in all_events3:
        if e.get("status") == "Completed":
            if person_type == "host" and e.get("host_id") == person_id:
                completed_my[e["event_id"]] = f"{e['event_name']} ({e['event_date']})"
            elif person_type == "facilitator":
                facs = get_event_facilitators(e["event_id"])
                if any(f["facilitator_id"] == person_id for f in facs):
                    completed_my[e["event_id"]] = f"{e['event_name']} ({e['event_date']})"

    if not completed_my:
        st.info("No completed events yet. Feedback can be submitted after your event is marked complete.")
    else:
        with st.form("feedback_form"):
            ev_sel  = st.selectbox("Select Event *",
                                    options=[""] + list(completed_my.keys()),
                                    format_func=lambda x: "— Select —" if x=="" else completed_my[x])
            rating  = st.select_slider("Overall Rating", options=[1,2,3,4,5], value=4,
                                        format_func=lambda x: "⭐"*x)
            fb_text = st.text_area("Your Feedback *",
                                    placeholder="Share your observations, what worked well, what could improve...",
                                    height=140)
            att_count = st.number_input("Attendance Count (if you tracked it)",
                                         min_value=0, value=0)

            if st.form_submit_button("📝 Submit Feedback", use_container_width=True):
                if not ev_sel or not fb_text:
                    st.error("Event and feedback are required.")
                else:
                    add_feedback({
                        "event_id":         ev_sel,
                        "participant_name":  person_name,
                        "feedback_text":     fb_text,
                        "rating":            rating,
                    })
                    # Also send as a message for coordinator visibility
                    send_message({
                        "sender_type":  person_type,
                        "sender_id":    person_id,
                        "sender_name":  person_name,
                        "event_id":     ev_sel,
                        "category":     "Feedback",
                        "subject":      f"Event Feedback — Rating: {'⭐'*rating}",
                        "body":         fb_text + (f"\n\nAttendance Count: {att_count}" if att_count else ""),
                    })
                    add_notification(
                        f"Feedback submitted by {person_name} for {completed_my.get(ev_sel,'')}",
                        "coordinator"
                    )
                    st.success("✅ Thank you! Your feedback has been submitted.")
                    st.balloons()
