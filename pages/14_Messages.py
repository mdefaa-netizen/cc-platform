import streamlit as st
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.database import (
    get_all_messages, mark_message_read, reply_to_message,
    get_unread_message_count, init_db, log_activity, add_notification,
    init_messages, send_message, get_messages_for_person
)
from utils.styles import inject_css, page_header

st.set_page_config(page_title="Messages · CC Platform", page_icon="💬", layout="wide")
inject_css()
try:
    from utils.database import init_all
    init_all()
except ImportError:
    init_db()
    init_messages()

role = st.session_state.get("user_role", None)
linked_id = st.session_state.get("linked_id", None)
username = st.session_state.get("username", "")

if role is None:
    st.warning("Please log in.")
    st.stop()

if role not in ("coordinator", "cdfa", "nhh", "facilitator", "host"):
    st.error("You do not have access to this page.")
    st.stop()

# Facilitators and hosts are redirected to the portal for messaging
if role in ("facilitator", "host"):
    st.info("Please use the Portal to send messages to the Coordinator.")
    st.switch_page("pages/0_Portal.py")

_is_coord = (role == "coordinator")

page_header("💬 Messages", "Messages from hosts and facilitators to the Coordinator")

CATEGORY_ICONS = {
    "General":     "💬",
    "Attendance":  "📊",
    "Payment":     "💰",
    "Delay":       "⏰",
    "Problem":     "🚨",
    "Information": "ℹ️",
    "Feedback":    "📝",
    "Cancellation":"❌",
}

# ── Coordinator: full inbox ───────────────────────────────────────────────────
if _is_coord:
    messages = get_all_messages()
    unread   = [m for m in messages if not m.get("is_read") and m.get("sender_type") != "coordinator"]

    if unread:
        st.markdown(f"""
        <div style='background:#FEF9E7;border-left:4px solid #C8963E;padding:0.8rem 1rem;
        border-radius:0 8px 8px 0;margin-bottom:1rem'>
            📬 <strong>{len(unread)} unread message(s)</strong> from hosts/facilitators/colleagues
        </div>
        """, unsafe_allow_html=True)

    tab_inbox, tab_all = st.tabs([f"📬 Unread ({len(unread)})", "📋 All Messages"])

    def render_message(m, show_reply=True):
        icon     = CATEGORY_ICONS.get(m.get("category","General"), "💬")
        ts       = str(m.get("created_at",""))[:16] if m.get("created_at") else ""
        unread_b = "🔴 " if not m.get("is_read") else ""
        ev_name  = m.get("event_name","") or "—"

        with st.expander(f"{unread_b}{icon} {m.get('sender_name','Unknown')} · {m.get('category','')} · {m.get('subject','')[:40]} · {ts}"):
            c1, c2 = st.columns([2,1])
            with c1:
                st.markdown(f"**From:** {m.get('sender_name','')} ({m.get('sender_type','').title()})")
                st.markdown(f"**Category:** {icon} {m.get('category','')}")
                st.markdown(f"**Related Event:** {ev_name}")
                st.markdown(f"**Subject:** {m.get('subject','')}")
                st.markdown("**Message:**")
                st.info(m.get("body",""))
            with c2:
                if not m.get("is_read"):
                    if st.button("✅ Mark Read", key=f"read_{m['message_id']}",
                                 use_container_width=True):
                        mark_message_read(m["message_id"])
                        st.rerun()

            if m.get("reply_body"):
                st.markdown("---")
                st.markdown("**Your Reply:**")
                st.success(m["reply_body"])
                st.caption(f"Replied: {m.get('replied_at','')[:16] if m.get('replied_at') else ''}")

            if show_reply and not m.get("reply_body"):
                st.markdown("---")
                reply = st.text_area("Reply to this message", key=f"reply_txt_{m['message_id']}",
                                      placeholder="Type your reply here...", height=80)
                if st.button("📤 Send Reply", key=f"send_reply_{m['message_id']}",
                             use_container_width=True):
                    if reply.strip():
                        reply_to_message(m["message_id"], reply.strip())
                        log_activity("Message Replied",
                                     f"To {m.get('sender_name','')} re: {m.get('subject','')[:40]}")
                        st.success("✅ Reply sent!")
                        st.rerun()

    with tab_inbox:
        if not unread:
            st.success("📭 No unread messages. All caught up!")
        else:
            for m in unread:
                render_message(m)

    with tab_all:
        cat_filter = st.selectbox("Filter by category",
                                   ["All"] + list(CATEGORY_ICONS.keys()))
        filtered = messages if cat_filter == "All" else \
                   [m for m in messages if m.get("category") == cat_filter]

        if not filtered:
            st.info("No messages yet.")
        else:
            st.caption(f"{len(filtered)} message(s)")
            for m in filtered:
                render_message(m)

# ── CDFA / NHH: Send message to coordinator ──────────────────────────────────
else:
    role_label = "NHH Colleague" if role == "nhh" else "CDFA Colleague"
    sender_name = st.session_state.get("user_label", role_label)

    tab_send, tab_history = st.tabs(["📤 Send Message", "📋 My Messages"])

    with tab_send:
        st.markdown("### Send a Message to the Coordinator")
        st.caption("Use this to communicate questions, updates, or requests.")

        with st.form("send_msg_form"):
            category = st.selectbox("Message Type", [
                "General",
                "Payment — Invoice, check, or payment question",
                "Information — Request information",
                "Problem — Report an issue or problem",
                "Feedback — Share feedback",
            ])
            cat_clean = category.split(" —")[0]
            subject = st.text_input("Subject *", placeholder="Brief summary of your message")
            body    = st.text_area("Message *",
                                    placeholder="Describe your question or request in detail...",
                                    height=160)

            if st.form_submit_button("📤 Send Message", use_container_width=True):
                if not subject or not body:
                    st.error("Subject and message are required.")
                else:
                    send_message({
                        "sender_type":  role,
                        "sender_id":    None,
                        "sender_name":  sender_name,
                        "event_id":     None,
                        "category":     cat_clean,
                        "subject":      subject,
                        "body":         body,
                    })
                    add_notification(
                        f"New message from {sender_name} ({role.upper()}): {subject[:50]}",
                        "coordinator"
                    )
                    st.success("✅ Message sent to the Coordinator!")

    with tab_history:
        st.markdown("### Your Message History")
        my_msgs = get_messages_for_person(role, None)
        # Filter to messages from this role (sender_type matches)
        if not my_msgs:
            st.caption("No messages yet.")
        else:
            for m in my_msgs:
                ts   = str(m.get("created_at",""))[:16] if m.get("created_at") else ""
                icon = CATEGORY_ICONS.get(m.get("category","General"), "💬")
                with st.expander(f"{icon} {m.get('subject','')[:50]} · {ts}"):
                    st.markdown(f"**{m.get('body','')}**")
                    if m.get("reply_body"):
                        st.markdown("---")
                        st.markdown("**Coordinator's Reply:**")
                        st.success(m["reply_body"])
                        st.caption(f"Replied: {m.get('replied_at','')[:16] if m.get('replied_at') else ''}")
                    else:
                        st.caption("⏳ Awaiting reply from Coordinator")
