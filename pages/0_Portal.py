import streamlit as st
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.database import (
    get_all_events, get_event_facilitators, add_feedback,
    send_message, get_messages_for_person,
    get_notifications, mark_notifications_read,
    init_db, init_messages, init_portal_access,
    check_portal_login, add_notification,
    get_facilitators_for_host_event,
    create_facilitator_conversation, add_conversation_message,
    get_conversations_for_participant, get_conversation_messages,
    get_visible_participants,
    get_facilitator, update_facilitator,
    get_event, update_event,
    hide_message,
)
from utils.mileage import (
    MILEAGE_RATE, FACILITATOR_STIPEND,
    calculate_round_trip_miles, estimate_reimbursement,
)
from utils.auth import require_auth, render_sidebar_user
from utils.styles import inject_css
from html import escape as _esc
from utils.format_helpers import format_date

st.set_page_config(page_title="My Portal · Community Conversations",
                   page_icon="🗺️", layout="wide")
inject_css()
try:
    from utils.database import init_all
    init_all()
except ImportError:
    init_db()
    init_messages()
    init_portal_access()

# NOTE: We intentionally do NOT call require_auth() here. The host portal uses
# its own credentials (portal_access table, via check_portal_login) which are
# separate from the staff users table. Calling require_auth() would redirect
# unauthenticated hosts to the staff login and prevent them from ever reaching
# the portal username/password form below.
#
# Security: every code path below either (a) sets portal_user and st.rerun()s,
# (b) calls st.stop(), or (c) is the post-gate dashboard which is preceded by
# a fail-closed `if not puser: st.stop()` guard. Unauthenticated visitors see
# only the portal_login() form, never portal CONTENT.
if st.session_state.get("authenticated"):
    render_sidebar_user()

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

if not st.session_state.get("portal_user"):
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
# Fail-closed guard: portal CONTENT is reached ONLY when portal_user is set.
# Every branch of the gate block above either sets portal_user and st.rerun()s,
# or st.stop()s. This guard catches any future regression that adds a fall-
# through path.
puser = st.session_state.get("portal_user")
if not puser:
    st.stop()
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
            {_esc(person_name)}<br>{_esc(person_type_label)}
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
<h1>Welcome, {_esc(person_name)}</h1>
<span class="page-subtitle">Your event portal · {_esc(person_type_label)}</span>
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
            🔔 {_esc(n.get('message',''))} <span style='color:#aaa;font-size:0.78rem'> · {_esc(ts)}</span>
        </div>""", unsafe_allow_html=True)
    if st.button("✅ Mark all read"):
        mark_notifications_read(portal_role)
        st.rerun()
    st.markdown("---")

# Host-only tab "Contact Facilitator(s)" surfaces a two-way thread with the
# facilitator(s) of an event the host is on. The facilitator inbox lives in the
# facilitator branch further below.
# Extra address-entry tab: hosts edit their event's venue address; facilitators
# edit their own home address and see a per-event travel/reimbursement estimate.
if person_type == "host":
    tab_cal, tab_msg, tab_fac, tab_addr, tab_feedback = st.tabs(
        ["📅 My Events", "💬 Message Coordinator", "🤝 Contact Facilitator(s)",
         "🏠 Event Venue Address", "📝 Submit Feedback"]
    )
else:
    tab_cal, tab_msg, tab_fac, tab_addr, tab_feedback = st.tabs(
        ["📅 My Events", "💬 Message Coordinator", "📨 Messages from Hosts",
         "🚗 My Travel & Reimbursement", "📝 Submit Feedback"]
    )

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
                        <strong style='font-size:1.1rem'>{_esc(e['event_name'])}</strong>
                        <span style='color:{status_color};margin-left:0.5rem'>{badge} {_esc(e.get('status',''))}</span>
                    </div>
                    <div style='text-align:right;color:#2A7F7F;font-weight:600'>
                        {_esc(str(e.get('event_date','')))}
                        {(' · '+_esc(e['event_time'])) if e.get('event_time') else ''}
                    </div>
                </div>
                <div style='margin-top:0.4rem;font-size:0.9rem;color:#555'>
                    📍 {_esc(e.get('venue_address','') or e.get('city','')+', NH')}
                </div>
                {f"<div style='margin-top:0.3rem;font-size:0.85rem;color:#7F8C8D'>Attendance: {e.get('attendance_count') or 'Not yet recorded'} {'✅' if e.get('attendance_confirmed') else ''}</div>" if e.get('status')=='Completed' else ''}
            </div>
            """, unsafe_allow_html=True)

# ── Message Coordinator ────────────────────────────────────────────────────────
with tab_msg:
    st.markdown("### Send a Message to the Coordinator")
    st.caption("Use this to communicate about your event, payment, schedule, or anything else.")
    st.caption("Messages in this portal may be reviewed by your coordinator.")

    all_events2 = get_all_events()
    my_event_opts = {}
    for e in all_events2:
        if person_type == "host" and e.get("host_id") == person_id:
            my_event_opts[e["event_id"]] = f"{e['event_name']} ({format_date(e['event_date'])})"
        elif person_type == "facilitator":
            facs = get_event_facilitators(e["event_id"])
            if any(f["facilitator_id"] == person_id for f in facs):
                my_event_opts[e["event_id"]] = f"{e['event_name']} ({format_date(e['event_date'])})"

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
                # "🙈 Hide from my view" — self-only; the coordinator still
                # sees this row in their inbox. Reversible only via the DB.
                if st.button("🙈 Hide from my view",
                             key=f"hide_legacy_{m['message_id']}",
                             use_container_width=True):
                    hide_message("legacy", m["message_id"],
                                 person_type, person_id)
                    st.rerun()

# ── Contact Facilitator(s) / Messages from Hosts ─────────────────────────────
# Host branch: start a thread with the facilitator(s) of an event the host is on.
# Facilitator branch: view + reply to threads where this facilitator is a participant.
# Both branches use get_visible_participants() so the silent coordinator is never
# listed. The coordinator's read-only view of these threads lives in
# pages/14_Messages.py.
with tab_fac:
    st.caption("Messages in this portal may be reviewed by your coordinator.")

    if person_type == "host":
        st.markdown("### Start a Conversation with Your Facilitator(s)")
        st.caption("Pick one of your events, then pick which facilitator(s) to message.")

        host_event_opts = {}
        for e in get_all_events():
            if e.get("host_id") == person_id:
                host_event_opts[e["event_id"]] = f"{e['event_name']} ({format_date(e['event_date'])})"

        if not host_event_opts:
            st.info("No events assigned to you yet — once you have one, you can message its facilitator(s) here.")
        else:
            with st.form("contact_facilitator_form"):
                fc_event_id = st.selectbox(
                    "Event *",
                    options=list(host_event_opts.keys()),
                    format_func=lambda x: host_event_opts[x],
                )
                event_facs = get_facilitators_for_host_event(fc_event_id) if fc_event_id else []
                fac_opts = {f["facilitator_id"]: f["name"] for f in event_facs}

                if not fac_opts:
                    st.info("No facilitator is assigned to this event yet. Your coordinator will assign one soon.")
                    fc_fac_ids = []
                else:
                    fc_fac_ids = st.multiselect(
                        "Facilitator(s) *",
                        options=list(fac_opts.keys()),
                        format_func=lambda x: fac_opts[x],
                        default=list(fac_opts.keys()),
                    )

                fc_subject = st.text_input("Subject *", placeholder="Brief summary")
                fc_body = st.text_area("Message *", placeholder="Write your message...", height=140)

                if st.form_submit_button("📤 Send to Facilitator(s)", use_container_width=True):
                    if not fc_fac_ids:
                        st.error("Please select at least one facilitator.")
                    elif not fc_subject or not fc_body:
                        st.error("Subject and message are required.")
                    else:
                        conv_id = create_facilitator_conversation(
                            event_id=fc_event_id,
                            host_id=person_id,
                            subject=fc_subject,
                            facilitator_ids=fc_fac_ids,
                            creator_type="host",
                            creator_id=person_id,
                            creator_name=person_name,
                            first_body=fc_body,
                        )
                        # Best-effort notification to the chosen facilitator(s).
                        # add_notification keys on target_role; the portal reads
                        # notifs with role f"{person_type}_{person_id}", so we
                        # mirror that key for each recipient.
                        for fid in fc_fac_ids:
                            add_notification(
                                f"New message from host {person_name}: {fc_subject[:50]}",
                                f"facilitator_{fid}",
                            )
                        st.success(f"✅ Conversation started with {len(fc_fac_ids)} facilitator(s).")
                        st.balloons()

        st.markdown("---")
        st.markdown("### Your Facilitator Conversations")
        host_convs = get_conversations_for_participant("host", person_id)
        if not host_convs:
            st.caption("No conversations yet.")
        else:
            for c in host_convs:
                ts = str(c.get("created_at",""))[:16] if c.get("created_at") else ""
                ev = c.get("event_name","") or "—"
                with st.expander(f"🤝 {c.get('subject','')[:60]} · {ev} · {ts}"):
                    visible = get_visible_participants(c["conversation_id"])
                    fac_names = []
                    for p in visible:
                        if p.get("participant_type") == "facilitator":
                            from utils.database import get_facilitator
                            fpid = p.get("participant_id")
                            try:
                                f = get_facilitator(int(fpid)) if fpid is not None else None
                            except (TypeError, ValueError):
                                f = None
                            if f:
                                fac_names.append(f.get("name",""))
                    if fac_names:
                        st.caption(f"With: {', '.join(fac_names)}")

                    # viewer args wire in per-viewer hides; rows hidden by
                    # this host are filtered out at the read path.
                    for m in get_conversation_messages(
                            c["conversation_id"], "host", person_id):
                        m_ts = str(m.get("created_at",""))[:16] if m.get("created_at") else ""
                        is_me = (m.get("sender_type") == "host" and str(m.get("sender_id")) == str(person_id))
                        align = "right" if is_me else "left"
                        bg = "#EAF6FF" if is_me else "#F3F4F6"
                        st.markdown(
                            f"<div style='text-align:{align}'>"
                            f"<div style='display:inline-block;background:{bg};padding:0.6rem 0.9rem;"
                            f"border-radius:10px;margin:0.25rem 0;max-width:80%'>"
                            f"<div style='font-size:0.78rem;color:#666'>"
                            f"{_esc(m.get('sender_name','') or m.get('sender_type',''))} · {_esc(m_ts)}"
                            f"</div>"
                            f"<div style='white-space:pre-wrap'>{_esc(m.get('body',''))}</div>"
                            f"</div></div>",
                            unsafe_allow_html=True,
                        )
                        # Self-only hide. The facilitator and coordinator
                        # still see this row.
                        if st.button("🙈 Hide from my view",
                                     key=f"hide_fc_host_{m['id']}"):
                            hide_message("fac_conv", m["id"],
                                         "host", person_id)
                            st.rerun()

                    reply_key = f"host_reply_{c['conversation_id']}"
                    reply = st.text_area("Reply", key=reply_key, height=80,
                                          placeholder="Type your reply here...")
                    if st.button("📤 Send Reply", key=f"host_send_{c['conversation_id']}",
                                 use_container_width=True):
                        if reply.strip():
                            add_conversation_message(
                                c["conversation_id"], "host", person_id, person_name, reply.strip()
                            )
                            for p in visible:
                                if p.get("participant_type") == "facilitator":
                                    add_notification(
                                        f"New reply from host {person_name}: {c.get('subject','')[:50]}",
                                        f"facilitator_{p.get('participant_id')}",
                                    )
                            st.success("✅ Reply sent.")
                            st.rerun()

    else:
        # Facilitator branch — read-and-reply inbox of host-initiated threads.
        st.markdown("### Messages from Hosts")
        st.caption("Hosts can reach you here about an event you facilitate.")

        fac_convs = get_conversations_for_participant("facilitator", person_id)
        if not fac_convs:
            st.caption("No messages from hosts yet.")
        else:
            for c in fac_convs:
                ts = str(c.get("created_at",""))[:16] if c.get("created_at") else ""
                ev = c.get("event_name","") or "—"
                host_name = c.get("host_name","") or "Host"
                with st.expander(f"📨 {c.get('subject','')[:60]} · {host_name} · {ev} · {ts}"):
                    visible = get_visible_participants(c["conversation_id"])
                    other_fac_names = []
                    for p in visible:
                        if p.get("participant_type") == "facilitator" \
                                and str(p.get("participant_id")) != str(person_id):
                            from utils.database import get_facilitator
                            fpid = p.get("participant_id")
                            try:
                                f = get_facilitator(int(fpid)) if fpid is not None else None
                            except (TypeError, ValueError):
                                f = None
                            if f:
                                other_fac_names.append(f.get("name",""))
                    parts_caption = f"With host: {host_name}"
                    if other_fac_names:
                        parts_caption += f" · Co-facilitator(s): {', '.join(other_fac_names)}"
                    st.caption(parts_caption)

                    for m in get_conversation_messages(
                            c["conversation_id"], "facilitator", person_id):
                        m_ts = str(m.get("created_at",""))[:16] if m.get("created_at") else ""
                        is_me = (m.get("sender_type") == "facilitator"
                                 and str(m.get("sender_id")) == str(person_id))
                        align = "right" if is_me else "left"
                        bg = "#EAF6FF" if is_me else "#F3F4F6"
                        st.markdown(
                            f"<div style='text-align:{align}'>"
                            f"<div style='display:inline-block;background:{bg};padding:0.6rem 0.9rem;"
                            f"border-radius:10px;margin:0.25rem 0;max-width:80%'>"
                            f"<div style='font-size:0.78rem;color:#666'>"
                            f"{_esc(m.get('sender_name','') or m.get('sender_type',''))} · {_esc(m_ts)}"
                            f"</div>"
                            f"<div style='white-space:pre-wrap'>{_esc(m.get('body',''))}</div>"
                            f"</div></div>",
                            unsafe_allow_html=True,
                        )
                        if st.button("🙈 Hide from my view",
                                     key=f"hide_fc_fac_{m['id']}"):
                            hide_message("fac_conv", m["id"],
                                         "facilitator", person_id)
                            st.rerun()

                    reply_key = f"fac_reply_{c['conversation_id']}"
                    reply = st.text_area("Reply", key=reply_key, height=80,
                                          placeholder="Type your reply here...")
                    if st.button("📤 Send Reply", key=f"fac_send_{c['conversation_id']}",
                                 use_container_width=True):
                        if reply.strip():
                            add_conversation_message(
                                c["conversation_id"], "facilitator", person_id, person_name, reply.strip()
                            )
                            # Notify the host of the reply.
                            host_pid = None
                            for p in visible:
                                if p.get("participant_type") == "host":
                                    host_pid = p.get("participant_id")
                            if host_pid is not None:
                                add_notification(
                                    f"New reply from facilitator {person_name}: {c.get('subject','')[:50]}",
                                    f"host_{host_pid}",
                                )
                            st.success("✅ Reply sent.")
                            st.rerun()

# ── Address entry: host venue / facilitator home + reimbursement estimate ────
# Self-only edits. The fetch-then-merge pattern (get_*, dict-update with the
# new field, full update_*) keeps every unrelated column intact and matches
# how pages/3_Hosts.py and pages/4_Facilitators.py call update_*.
with tab_addr:
    if person_type == "host":
        st.markdown("### Event Venue Address")
        st.caption(
            "This address is the venue for your event. It's used to calculate "
            "your facilitator's travel reimbursement."
        )

        host_events_for_addr = [
            e for e in get_all_events() if e.get("host_id") == person_id
        ]
        if not host_events_for_addr:
            st.info("No events assigned to you yet — once you have one, you can set its venue here.")
        else:
            for e in host_events_for_addr:
                ev_label = f"{e['event_name']} · {format_date(e['event_date'])}"
                with st.expander(f"🏠 {ev_label}", expanded=False):
                    with st.form(f"venue_form_{e['event_id']}"):
                        v_addr = st.text_input(
                            "Venue address (street)",
                            value=e.get("venue_address","") or "",
                            placeholder="45 Green Street",
                            key=f"venue_addr_{e['event_id']}",
                        )
                        v_city = st.text_input(
                            "City",
                            value=e.get("city","") or "",
                            placeholder="Concord",
                            key=f"venue_city_{e['event_id']}",
                        )
                        if st.form_submit_button("💾 Save venue address",
                                                 use_container_width=True):
                            # Re-fetch so we don't clobber any field that changed
                            # since the page loaded. Guard: only this host's event.
                            fresh = get_event(e["event_id"])
                            if not fresh or fresh.get("host_id") != person_id:
                                st.error("You can only edit venues for events you host.")
                            else:
                                merged = {**fresh,
                                          "venue_address": v_addr,
                                          "city": v_city}
                                update_event(e["event_id"], merged)
                                st.success("✅ Venue address saved.")
                                st.rerun()

    else:
        # Facilitator branch: edit own home address + see per-event estimates.
        st.markdown("### My Home Address")
        st.caption(
            "Used to estimate driving distance from your home to each event "
            "venue. The coordinator's Payments page is the official record; "
            "the numbers below are an estimate."
        )

        me = get_facilitator(person_id) or {}
        with st.form("fac_addr_form"):
            col_a, col_b = st.columns(2)
            with col_a:
                f_addr = st.text_input("Street address",
                                        value=me.get("address","") or "",
                                        placeholder="123 Main St")
                f_city = st.text_input("City",
                                        value=me.get("city","") or "",
                                        placeholder="Concord")
            with col_b:
                f_state = st.text_input("State",
                                         value=me.get("state","NH") or "NH")
                f_zip = st.text_input("ZIP code",
                                       value=me.get("zip_code","") or "",
                                       placeholder="03301")

            if st.form_submit_button("💾 Save home address",
                                     use_container_width=True):
                # Re-fetch and guard: only this facilitator's own row.
                fresh = get_facilitator(person_id)
                if not fresh or fresh.get("facilitator_id") != person_id:
                    st.error("You can only edit your own profile.")
                else:
                    merged = {**fresh,
                              "address": f_addr,
                              "city": f_city,
                              "state": f_state or "NH",
                              "zip_code": f_zip}
                    update_facilitator(person_id, merged)
                    st.success("✅ Home address saved.")
                    st.rerun()

        st.markdown("---")
        st.markdown("### Estimated Reimbursement per Event")
        st.caption(
            f"Formula: round-trip miles × ${MILEAGE_RATE:.3f}/mi + "
            f"${FACILITATOR_STIPEND:,.2f} program stipend. "
            "These are **estimates** — the coordinator's Payments page is the official record."
        )

        my_facilitator_events = []
        for e in get_all_events():
            facs = get_event_facilitators(e["event_id"])
            if any(f["facilitator_id"] == person_id for f in facs):
                my_facilitator_events.append(e)

        if not my_facilitator_events:
            st.info("You aren't on any events yet — once you are, estimates will appear here.")
        else:
            # Build home origin from the just-saved (or pre-existing) profile.
            home_parts = [me.get("address",""), me.get("city",""),
                          me.get("state","NH"), me.get("zip_code","")]
            home_addr = ", ".join(p for p in home_parts if p)

            for e in my_facilitator_events:
                ev_label = f"{e['event_name']} · {format_date(e['event_date'])}"
                with st.expander(f"🚗 {ev_label}", expanded=False):
                    venue_parts = [e.get("venue_address",""), e.get("city",""), "NH"]
                    venue_addr = ", ".join(p for p in venue_parts if p)

                    if not home_addr:
                        st.warning("Add your home address above to see an estimate.")
                        continue
                    if not e.get("venue_address") and not e.get("city"):
                        st.info("Awaiting venue address from your host.")
                        continue

                    calc_key = f"fac_estimate_{e['event_id']}"
                    if st.button("🗺️ Calculate estimate",
                                 key=f"fac_calc_{e['event_id']}",
                                 use_container_width=True):
                        with st.spinner("Calculating driving distance..."):
                            rt, text, err = calculate_round_trip_miles(home_addr, venue_addr)
                        if err or rt is None:
                            st.session_state[calc_key] = {"error": err or "Distance unavailable."}
                        else:
                            est = estimate_reimbursement(rt)
                            st.session_state[calc_key] = {
                                "round_trip_miles": rt,
                                "text": text,
                                **est,
                            }

                    cached = st.session_state.get(calc_key)
                    if cached:
                        if "error" in cached:
                            st.error(f"❌ {cached['error']}")
                        else:
                            r1, r2, r3, r4 = st.columns(4)
                            with r1:
                                st.metric("Round trip", f"{cached['round_trip_miles']:.1f} mi")
                            with r2:
                                st.metric("Mileage", f"${cached['mileage']:,.2f}")
                            with r3:
                                st.metric("Stipend", f"${cached['stipend']:,.2f}")
                            with r4:
                                st.metric("Estimated total", f"${cached['total']:,.2f}")
                            st.caption(
                                f"From: {home_addr} → To: {venue_addr} · "
                                f"Method: {cached.get('text','')}"
                            )

# ── Submit Feedback ────────────────────────────────────────────────────────────
with tab_feedback:
    st.markdown("### Submit Event Feedback")
    st.caption("Share your experience and observations from the event.")

    all_events3 = get_all_events()
    completed_my = {}
    for e in all_events3:
        if e.get("status") == "Completed":
            if person_type == "host" and e.get("host_id") == person_id:
                completed_my[e["event_id"]] = f"{e['event_name']} ({format_date(e['event_date'])})"
            elif person_type == "facilitator":
                facs = get_event_facilitators(e["event_id"])
                if any(f["facilitator_id"] == person_id for f in facs):
                    completed_my[e["event_id"]] = f"{e['event_name']} ({format_date(e['event_date'])})"

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
