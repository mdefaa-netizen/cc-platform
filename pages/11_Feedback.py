import streamlit as st
import time
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.database import log_activity, add_notification, get_all_events, get_all_feedback, add_feedback, get_event_feedback, init_db
from utils.styles import inject_css, page_header

st.set_page_config(page_title="Feedback · CC Platform", page_icon="📝", layout="wide")
inject_css()
init_db()

if not st.session_state.get("authenticated"):
    st.warning("Please sign in from the main page.")
    st.stop()

# Role awareness
_role = st.session_state.get("user_role", "coordinator")
_is_coord = (_role == "coordinator")
_user_label = st.session_state.get("user_label", "Coordinator")

page_header("📝 Participant Feedback", "Collect and review feedback from event participants")

events   = get_all_events()
feedback = get_all_feedback()

tab_add, tab_view, tab_summary = st.tabs(["➕ Add Feedback", "📋 All Feedback", "📊 Summary"])

with tab_add:
    if st.session_state.get("feedback_just_added"):
        st.session_state.pop("feedback_just_added")
    st.markdown("### Record Participant Feedback")
    ev_opts = {e["event_id"]: f"{e['event_name']} ({e['event_date']})" for e in events}
    with st.form("add_feedback_form"):
        ev_sel = st.selectbox("Event *", options=[""] + list(ev_opts.keys()),
                               format_func=lambda x: "— Select Event —" if x=="" else ev_opts[x])
        pname = st.text_input("Participant Name (optional)", placeholder="Leave blank for anonymous")
        rating = st.select_slider("Rating", options=[1,2,3,4,5], value=3,
                                   format_func=lambda x: "⭐"*x)
        text = st.text_area("Feedback *", placeholder="Enter participant feedback here...", height=140)

        if st.form_submit_button("💾 Save Feedback", use_container_width=True):
            if st.session_state.get("feedback_just_added"):
                pass
            elif not ev_sel or not text:
                st.error("Event and feedback text are required.")
            else:
                st.session_state["feedback_just_added"] = True
                add_feedback({"event_id":ev_sel,"participant_name":pname or None,
                               "feedback_text":text,"rating":rating})
                st.success("✅ Feedback recorded!")
                time.sleep(3)
                st.rerun()

with tab_view:
    st.markdown("### All Feedback")
    ev_filter = st.selectbox("Filter by event", options=["All"] + list(ev_opts.keys()),
                              format_func=lambda x: "All Events" if x=="All" else ev_opts.get(x,x))
    filtered = feedback if ev_filter=="All" else [f for f in feedback if f.get("event_id")==ev_filter]

    if not filtered:
        st.info("No feedback recorded yet.")
    else:
        for fb in filtered:
            stars = "⭐" * (fb.get("rating") or 0)
            name  = fb.get("participant_name") or "Anonymous"
            date  = str(fb.get("submitted_date",""))[:10] if fb.get("submitted_date") else "—"
            ev_name = fb.get("event_name","—")
            st.markdown(f"""
            <div class="section-box" style='margin-bottom:0.7rem;padding:0.9rem 1rem'>
                <div style='display:flex;justify-content:space-between;align-items:center'>
                    <div><strong>{name}</strong> · <span style='color:#7F8C8D;font-size:0.85rem'>{ev_name}</span></div>
                    <div>{stars} &nbsp; <span style='color:#7F8C8D;font-size:0.8rem'>{date}</span></div>
                </div>
                <div style='margin-top:0.4rem;font-size:0.9rem'>{fb.get('feedback_text','')}</div>
            </div>
            """, unsafe_allow_html=True)

with tab_summary:
    st.markdown("### Feedback Summary by Event")
    if not events:
        st.info("No events yet.")
    else:
        for e in events:
            ev_fbs = get_event_feedback(e["event_id"])
            if not ev_fbs:
                continue
            ratings = [fb.get("rating") for fb in ev_fbs if fb.get("rating")]
            avg = sum(ratings)/len(ratings) if ratings else 0
            stars = "⭐" * round(avg)
            st.markdown(f"""
            <div class="section-box" style='margin-bottom:0.8rem'>
                <div style='display:flex;justify-content:space-between'>
                    <strong>{e['event_name']}</strong>
                    <span>{stars} {avg:.1f}/5 ({len(ev_fbs)} response{'s' if len(ev_fbs)!=1 else ''})</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
