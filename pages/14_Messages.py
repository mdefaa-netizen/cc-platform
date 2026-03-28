import streamlit as st
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.database import (
    get_all_messages, mark_message_read, reply_to_message,
    get_unread_message_count, init_db, log_activity, add_notification,
    init_messages
)
from utils.styles import inject_css, page_header

st.set_page_config(page_title="Messages · CC Platform", page_icon="💬", layout="wide")
inject_css()
init_db()
init_messages()

if not st.session_state.get("authenticated"):
    st.warning("Please sign in from the main page.")
    st.stop()

_role     = st.session_state.get("user_role","coordinator")
_is_coord = (_role == "coordinator")

page_header("💬 Messages", "Messages from hosts and facilitators to the Coordinator")

if not _is_coord:
    st.info("Message inbox is available to the Coordinator only. Use the Portal to send messages.")
    st.stop()

messages = get_all_messages()
unread   = [m for m in messages if not m.get("is_read") and m.get("sender_type") != "coordinator"]

if unread:
    st.markdown(f"""
    <div style='background:#FEF9E7;border-left:4px solid #C8963E;padding:0.8rem 1rem;
    border-radius:0 8px 8px 0;margin-bottom:1rem'>
        📬 <strong>{len(unread)} unread message(s)</strong> from hosts/facilitators
    </div>
    """, unsafe_allow_html=True)

tab_inbox, tab_all = st.tabs([f"📬 Unread ({len(unread)})", "📋 All Messages"])

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

def render_message(m, show_reply=True):
    icon     = CATEGORY_ICONS.get(m.get("category","General"), "💬")
    ts       = m.get("created_at","")[:16] if m.get("created_at") else ""
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
