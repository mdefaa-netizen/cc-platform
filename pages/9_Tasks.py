import streamlit as st
import time
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.database import (
    log_activity, add_notification,
    get_all_tasks, add_task, update_task, delete_task,
    get_all_events, get_overdue_tasks, init_db)
from utils.styles import inject_css, page_header

st.set_page_config(page_title="Tasks · CC Platform", page_icon="✅", layout="wide")
inject_css()
init_db()

if not st.session_state.get("authenticated"):
    st.warning("Please sign in from the main page.")
    st.stop()

page_header("✅ Task Management", "Track coordinator tasks, deadlines, and progress")

tasks  = get_all_tasks()
events = get_all_events()
overdue = get_overdue_tasks()

# Overdue alert banner
if overdue:
    st.markdown(f"""
    <div class="alert-danger">
        ⚠️ <strong>{len(overdue)} overdue task(s)</strong> need your attention!
        {', '.join(t['task_title'] for t in overdue[:3])}{'...' if len(overdue)>3 else ''}
    </div>
    """, unsafe_allow_html=True)

# KPI summary
from datetime import date
today = date.today().isoformat()
not_started = sum(1 for t in tasks if t.get("status")=="Not Started")
in_progress = sum(1 for t in tasks if t.get("status")=="In Progress")
completed   = sum(1 for t in tasks if t.get("status")=="Completed")
blocked     = sum(1 for t in tasks if t.get("status")=="Blocked")

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(f"""<div class="kpi-card">
    <div class="kpi-label">Not Started</div><div class="kpi-value">{not_started}</div></div>""",
    unsafe_allow_html=True)
with c2:
    st.markdown(f"""<div class="kpi-card gold">
    <div class="kpi-label">In Progress</div><div class="kpi-value">{in_progress}</div></div>""",
    unsafe_allow_html=True)
with c3:
    st.markdown(f"""<div class="kpi-card green">
    <div class="kpi-label">Completed</div><div class="kpi-value">{completed}</div></div>""",
    unsafe_allow_html=True)
with c4:
    color = "red" if blocked else "teal"
    st.markdown(f"""<div class="kpi-card {color}">
    <div class="kpi-label">Blocked</div><div class="kpi-value">{blocked}</div></div>""",
    unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

tab_list, tab_add, tab_edit = st.tabs(["📋 Task List", "➕ Add Task", "✏️ Edit Task"])

PRIORITY_ORDER = {"Urgent":0,"High":1,"Medium":2,"Low":3}
STATUS_ORDER   = {"Blocked":0,"In Progress":1,"Not Started":2,"Completed":3}

with tab_list:
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        status_f   = st.selectbox("Filter by status", ["All","Not Started","In Progress","Completed","Blocked"])
    with col_f2:
        priority_f = st.selectbox("Filter by priority", ["All","Urgent","High","Medium","Low"])
    with col_f3:
        ev_opts  = {e["event_id"]: e["event_name"] for e in events}
        ev_f     = st.selectbox("Filter by event", ["All"] + list(ev_opts.keys()),
                                 format_func=lambda x: "All Events" if x=="All" else ev_opts.get(x,x))

    filtered = tasks
    if status_f   != "All": filtered = [t for t in filtered if t.get("status")==status_f]
    if priority_f != "All": filtered = [t for t in filtered if t.get("priority")==priority_f]
    if ev_f       != "All": filtered = [t for t in filtered if t.get("related_event_id")==ev_f]

    # Sort by priority then status
    filtered = sorted(filtered, key=lambda t: (
        t.get("due_date","9999") if t.get("due_date") else "9999",
        PRIORITY_ORDER.get(t.get("priority","Medium"),2),
    ))

    if not filtered:
        st.info("No tasks found.")
    else:
        priority_icons = {"Urgent":"🔴","High":"🟠","Medium":"🔵","Low":"🟢"}
        status_icons   = {"Not Started":"⬜","In Progress":"🔄","Completed":"✅","Blocked":"🚫"}

        for t in filtered:
            is_overdue = t.get("due_date","9999") < today and t.get("status") != "Completed"
            p_icon = priority_icons.get(t.get("priority","Medium"),"🔵")
            s_icon = status_icons.get(t.get("status","Not Started"),"⬜")
            overdue_flag = " 🚨 OVERDUE" if is_overdue else ""
            due_str = t.get("due_date","—") or "—"

            with st.expander(f"{s_icon} {p_icon} {t['task_title']}{overdue_flag} — Due: {due_str}"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.markdown(f"**Priority:** {p_icon} {t.get('priority','')}")
                    st.markdown(f"**Status:** {s_icon} {t.get('status','')}")
                with c2:
                    st.markdown(f"**Due Date:** {t.get('due_date','—') or '—'}")
                    st.markdown(f"**Related Event:** {t.get('event_name','—') or '—'}")
                with c3:
                    st.markdown(f"**Completed:** {t.get('completed_date','—') or '—'}")
                if t.get("task_description"):
                    st.caption(t["task_description"])
                if t.get("notes"):
                    st.caption(f"Notes: {t['notes']}")

                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    if t.get("status") != "Completed":
                        if st.button("✅ Mark Complete", key=f"done_{t['task_id']}"):
                            update_task(t["task_id"], {**t, "status":"Completed"})
                            st.rerun()
                with col_b:
                    if st.button("✏️ Edit", key=f"edit_{t['task_id']}"):
                        st.session_state["edit_task_id"] = t["task_id"]
                        st.info("Switch to Edit Task tab.")
                with col_c:
                    if st.button("🗑️ Delete", key=f"del_{t['task_id']}"):
                        delete_task(t["task_id"])
                        st.rerun()

with tab_add:
    st.markdown("### Add New Task")
    event_options = {e["event_id"]: e["event_name"] for e in events}
    with st.form("add_task_form"):
        c1, c2 = st.columns(2)
        with c1:
            title = st.text_input("Task Title *", placeholder="e.g., Send confirmation to Concord host")
            desc  = st.text_area("Description", height=80)
            rel_ev = st.selectbox("Related Event (optional)", options=[""] + list(event_options.keys()),
                                   format_func=lambda x: "— None —" if x=="" else event_options[x])
        with c2:
            import datetime
            due   = st.date_input("Due Date", value=datetime.date.today())
            prio  = st.selectbox("Priority", ["Medium","Low","High","Urgent"])
            stat  = st.selectbox("Status", ["Not Started","In Progress","Completed","Blocked"])
        notes = st.text_input("Notes")

        if st.form_submit_button("💾 Save Task", use_container_width=True):
            if not title:
                st.error("Task title is required.")
            else:
                add_task({"task_title":title,"task_description":desc,
                           "related_event_id": rel_ev or None,
                           "due_date":str(due),"priority":prio,"status":stat,"notes":notes})
                st.success(f"✅ Task '{title}' created!")
                time.sleep(3)
                st.rerun()

with tab_edit:
    task_opts = {t["task_id"]: f"{t['task_title']} (Due: {t.get('due_date','—')})" for t in tasks}
    default_t = st.session_state.get("edit_task_id","")

    sel = st.selectbox("Select task to edit", options=[""] + list(task_opts.keys()),
                        format_func=lambda x: "— Select —" if x=="" else task_opts[x])
    if sel:
        t = next((tk for tk in tasks if tk["task_id"]==sel), None)
        if t:
            with st.form("edit_task_form"):
                c1, c2 = st.columns(2)
                with c1:
                    title = st.text_input("Task Title *", value=t.get("task_title",""))
                    desc  = st.text_area("Description", value=t.get("task_description","") or "", height=80)
                    event_opts2 = {e["event_id"]: e["event_name"] for e in events}
                    rel_ev = st.selectbox("Related Event", options=[""] + list(event_opts2.keys()),
                                           format_func=lambda x: "— None —" if x=="" else event_opts2[x],
                                           index=0 if not t.get("related_event_id") else
                                           (list(event_opts2.keys()).index(t["related_event_id"])+1
                                            if t["related_event_id"] in event_opts2 else 0))
                with c2:
                    import datetime
                    due_val = None
                    if t.get("due_date"):
                        try: due_val = datetime.date.fromisoformat(t["due_date"])
                        except: pass
                    due   = st.date_input("Due Date", value=due_val or datetime.date.today())
                    prio  = st.selectbox("Priority", ["Medium","Low","High","Urgent"],
                                          index=["Medium","Low","High","Urgent"].index(t.get("priority","Medium")))
                    stat  = st.selectbox("Status", ["Not Started","In Progress","Completed","Blocked"],
                                          index=["Not Started","In Progress","Completed","Blocked"].index(t.get("status","Not Started")))
                notes = st.text_input("Notes", value=t.get("notes","") or "")

                col_s, col_d = st.columns([3,1])
                with col_s:
                    save = st.form_submit_button("💾 Save Changes", use_container_width=True)
                with col_d:
                    delb = st.form_submit_button("🗑️ Delete", use_container_width=True)

                if save:
                    update_task(sel, {"task_title":title,"task_description":desc,
                                       "related_event_id": rel_ev or None,
                                       "due_date":str(due),"priority":prio,"status":stat,"notes":notes})
                    st.session_state.pop("edit_task_id",None)
                    st.success("✅ Task updated!")
                    time.sleep(3)
                    st.rerun()
                if delb:
                    delete_task(sel)
                    st.success("🗑️ Task deleted.")
                    time.sleep(3)
                    st.rerun()
