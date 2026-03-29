import streamlit as st
import sys, os, datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.database import (
    log_activity, add_notification,
    get_all_events, get_event, add_event, update_event, delete_event,
    get_all_hosts, get_all_facilitators, get_event_facilitators,
    get_event_communications, get_event_feedback, init_db
)
from utils.styles import inject_css, page_header

st.set_page_config(page_title="Events · CC Platform", page_icon="📅", layout="wide")
inject_css()
init_db()

if not st.session_state.get("authenticated"):
    st.warning("Please sign in from the main page.")
    st.stop()

_role       = st.session_state.get("user_role", "coordinator")
_is_coord   = (_role == "coordinator")
_user_label = st.session_state.get("user_label", "Coordinator")

page_header("📅 Events Management", "Create, track, and manage all Community Conversations events")

hosts        = get_all_hosts()
facilitators = get_all_facilitators()
host_map     = {h["host_id"]: h for h in hosts}

# Read-only banner for non-coordinators
if not _is_coord:
    st.info(f"👁️ You are viewing as **{_user_label}** — read-only access.")

tabs = st.tabs(["📋 All Events", "➕ Add Event", "✏️ Edit Event", "🔍 View Details"]) if _is_coord \
      else st.tabs(["📋 All Events", "🔍 View Details"])

tab_list = tabs[0]
tab_add  = tabs[1] if _is_coord else None
tab_edit = tabs[2] if _is_coord else None
tab_view = tabs[3] if _is_coord else tabs[1]

# ── All Events ─────────────────────────────────────────────────────────────────
with tab_list:
    events = get_all_events()
    for e in events:
        facs = get_event_facilitators(e["event_id"])
        e["facilitator_names"] = ", ".join(f["name"] for f in facs) if facs else "—"

    col_f1, col_f2 = st.columns([2, 1])
    with col_f1:
        search = st.text_input("🔍 Search events", placeholder="Event name, city, host...")
    with col_f2:
        status_filter = st.selectbox("Filter by status", ["All","Scheduled","Completed","Cancelled"])

    filtered = events
    if search:
        s = search.lower()
        filtered = [e for e in filtered if s in (e.get("event_name","") + e.get("city","") + e.get("host_name","")).lower()]
    if status_filter != "All":
        filtered = [e for e in filtered if e.get("status") == status_filter]

    if not filtered:
        st.info("No events found.")
    else:
        header  = "| Event Name | Date | City | Host | Facilitators | Status | Attendance |"
        divider = "|---|---|---|---|---|---|---|"
        rows = [header, divider]
        for e in filtered:
            badge = {"Scheduled":"🔵","Completed":"🟢","Cancelled":"🔴"}.get(e.get("status",""),"⚪")
            att   = str(e.get("attendance_count") or "—")
            rows.append(f"| {e['event_name']} | {e['event_date']} | {e.get('city','')} | "
                        f"{e.get('host_name','—')} | {e.get('facilitator_names','—')} | "
                        f"{badge} {e.get('status','')} | {att} |")
        st.markdown("\n".join(rows))
        st.caption(f"Showing {len(filtered)} of {len(events)} events")

        if _is_coord:
            event_names = {e["event_id"]: f"{e['event_name']} ({e['event_date']})" for e in filtered}
            sel_id = st.selectbox("Select event to edit/view",
                                  options=["—"] + list(event_names.keys()),
                                  format_func=lambda x: "— Select —" if x=="—" else event_names[x])
            c1, c2 = st.columns(2)
            with c1:
                if st.button("✏️ Edit Selected", use_container_width=True) and sel_id != "—":
                    st.session_state["edit_event_id"] = sel_id
                    st.info("Switch to the Edit Event tab.")
            with c2:
                if st.button("🔍 View Details", use_container_width=True) and sel_id != "—":
                    st.session_state["view_event_id"] = sel_id
                    st.info("Switch to the View Details tab.")

# ── Add Event ──────────────────────────────────────────────────────────────────
if _is_coord and tab_add:
    with tab_add:
        st.markdown("### Add New Event")
        with st.form("add_event_form"):
            c1, c2 = st.columns(2)
            with c1:
                event_name = st.text_input("Event Name *", placeholder="e.g., Portsmouth Community Conversation")
                event_date = st.date_input("Event Date *")
                event_time = st.time_input("Event Time")
                city       = st.text_input("City *", placeholder="e.g., Portsmouth")
            with c2:
                host_options = {h["host_id"]: f"{h['name']} — {h.get('venue_name','')}" for h in hosts}
                host_sel = st.selectbox("Host *", options=[""] + list(host_options.keys()),
                                        format_func=lambda x: "— Select Host —" if x=="" else host_options[x])
                fac_options = {f["facilitator_id"]: f["name"] for f in facilitators}
                fac_sel  = st.multiselect("Assign Facilitators", options=list(fac_options.keys()),
                                          format_func=lambda x: fac_options[x])
                status   = st.selectbox("Status", ["Scheduled","Completed","Cancelled"])

            venue_addr = ""
            if host_sel and host_sel in host_map:
                h = host_map[host_sel]
                venue_addr = f"{h.get('address','')} {h.get('city','')} {h.get('state','NH')} {h.get('zip_code','')}".strip()
            venue_address = st.text_input("Venue Address", value=venue_addr)

            if st.form_submit_button("💾 Save Event", use_container_width=True):
                if not event_name or not city:
                    st.error("Event name and city are required.")
                else:
                    from utils.database import get_all_events
                    existing = [e for e in get_all_events() if e["event_name"].lower()==event_name.lower() and e["event_date"]==str(event_date)]
                    if existing:
                        st.error(f"An event '{event_name}' on {event_date} already exists.")
                    else:
                        eid = add_event({
                            "event_name": event_name, "event_date": str(event_date),
                            "event_time": str(event_time), "host_id": host_sel or None,
                            "venue_address": venue_address, "city": city, "status": status,
                        }, facilitator_ids=fac_sel or [])
                        log_activity("Event Created", f"{event_name} on {event_date} in {city}")
                        add_notification(f"New event scheduled: {event_name} on {event_date} in {city}, NH", "all")
                        st.success(f"✅ Event '{event_name}' created!")
                        st.balloons()

# ── Edit Event ─────────────────────────────────────────────────────────────────
if _is_coord and tab_edit:
    with tab_edit:
        events_all   = get_all_events()
        edit_options = {e["event_id"]: f"{e['event_name']} ({e['event_date']})" for e in events_all}
        default_edit = st.session_state.get("edit_event_id", "")

        sel_edit = st.selectbox("Select event to edit",
                                options=[""] + list(edit_options.keys()),
                                format_func=lambda x: "— Select —" if x=="" else edit_options[x])

        if sel_edit:
            ev        = get_event(sel_edit)
            curr_facs = [f["facilitator_id"] for f in get_event_facilitators(sel_edit)]
            old_date   = ev.get("event_date","")
            old_city   = ev.get("city","")
            old_status = ev.get("status","")

            with st.form("edit_event_form"):
                c1, c2 = st.columns(2)
                with c1:
                    ename  = st.text_input("Event Name *", value=ev.get("event_name",""))
                    edate  = st.date_input("Event Date *",
                        value=datetime.date.fromisoformat(ev["event_date"]) if ev.get("event_date") else datetime.date.today())
                    etime  = st.text_input("Event Time", value=ev.get("event_time",""))
                    ecity  = st.text_input("City", value=ev.get("city",""))
                with c2:
                    host_options2 = {h["host_id"]: f"{h['name']} — {h.get('venue_name','')}" for h in hosts}
                    host_sel2 = st.selectbox("Host", options=[""] + list(host_options2.keys()),
                                             format_func=lambda x: "— None —" if x=="" else host_options2[x],
                                             index=0 if not ev.get("host_id") else
                                             (list(host_options2.keys()).index(ev["host_id"])+1
                                              if ev["host_id"] in host_options2 else 0))
                    fac_options2 = {f["facilitator_id"]: f["name"] for f in facilitators}
                    fac_sel2 = st.multiselect("Facilitators",
                                              options=list(fac_options2.keys()),
                                              default=[f for f in curr_facs if f in fac_options2],
                                              format_func=lambda x: fac_options2[x])
                    estatus = st.selectbox("Status", ["Scheduled","Completed","Cancelled"],
                                           index=["Scheduled","Completed","Cancelled"].index(ev.get("status","Scheduled")))

                evenue = st.text_input("Venue Address", value=ev.get("venue_address",""))
                eatt   = st.number_input("Attendance Count", value=ev.get("attendance_count") or 0, min_value=0)
                econf  = st.checkbox("Attendance Confirmed", value=bool(ev.get("attendance_confirmed")))
                esumm  = st.text_area("Event Summary / Narrative", value=ev.get("event_summary",""), height=100)

                col_save, col_del = st.columns([3,1])
                with col_save:
                    save = st.form_submit_button("💾 Save Changes", use_container_width=True)
                with col_del:
                    delete = st.form_submit_button("🗑️ Delete Event", use_container_width=True)

                if save:
                    update_event(sel_edit, {
                        "event_name": ename, "event_date": str(edate), "event_time": etime,
                        "host_id": host_sel2 or None, "venue_address": evenue, "city": ecity,
                        "status": estatus, "attendance_count": eatt,
                        "attendance_confirmed": econf, "event_summary": esumm,
                    }, facilitator_ids=fac_sel2)

                    # ── Smart change detection & targeted notifications ──────────
                    changes = []
                    if str(edate) != old_date: changes.append(f"Date changed: {old_date} → {edate}")
                    if ecity     != old_city:  changes.append(f"Location changed: {old_city} → {ecity}")
                    if estatus   != old_status: changes.append(f"Status changed: {old_status} → {estatus}")
                    if evenue    != ev.get("venue_address",""): changes.append(f"Venue updated")

                    if changes:
                        change_str = " | ".join(changes)
                        # Notify NHH and CDFA
                        add_notification(f"Event '{ename}' updated: {change_str}", "nhh")
                        add_notification(f"Event '{ename}' updated: {change_str}", "cdfa")
                        # Notify the specific host of this event
                        if host_sel2:
                            h_info = host_map.get(host_sel2, {})
                            add_notification(
                                f"Your event '{ename}' has been updated: {change_str}",
                                f"host_{host_sel2}"
                            )
                        log_activity("Event Updated", f"{ename} — {change_str}")
                        st.warning(f"⚠️ Change notifications sent to NHH, CDFA, and Host: {change_str}")
                    else:
                        log_activity("Event Updated", f"{ename} — minor update")

                    st.success("✅ Event updated successfully!")
                    st.session_state.pop("edit_event_id", None)

                if delete:
                    delete_event(sel_edit)
                    log_activity("Event Deleted", f"{ev.get('event_name','')}")
                    add_notification(f"Event cancelled: {ev.get('event_name','')}", "all")
                    st.success("🗑️ Event deleted.")
                    st.rerun()

# ── View Details ───────────────────────────────────────────────────────────────
with tab_view:
    events_all2  = get_all_events()
    view_options = {e["event_id"]: f"{e['event_name']} ({e['event_date']})" for e in events_all2}
    sel_view     = st.selectbox("Select event to view",
                                options=[""] + list(view_options.keys()),
                                format_func=lambda x: "— Select —" if x=="" else view_options[x])

    if sel_view:
        ev   = get_event(sel_view)
        facs = get_event_facilitators(sel_view)
        comms = get_event_communications(sel_view)
        fbs  = get_event_feedback(sel_view)

        st.markdown(f"""
        <div class='section-box'>
            <h2 style='margin:0 0 0.5rem'>{ev['event_name']}</h2>
            <p style='color:#7F8C8D;margin:0'>{ev.get('event_date','')}
            {('· '+ev['event_time']) if ev.get('event_time') else ''} · {ev.get('city','')}, NH</p>
        </div>""", unsafe_allow_html=True)

        sc = {"Scheduled":"#2980B9","Completed":"#27AE60","Cancelled":"#C0392B"}
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f"**Status:** <span style='color:{sc.get(ev.get('status',''),'')}'>●</span> {ev.get('status','')}", unsafe_allow_html=True)
            st.markdown(f"**Host:** {ev.get('host_name','—')}")
            st.markdown(f"**Venue:** {ev.get('venue_name','—')}")
            st.markdown(f"**Address:** {ev.get('venue_address','—')}")
        with c2:
            st.markdown(f"**Attendance:** {ev.get('attendance_count') or '—'}")
            st.markdown(f"**Confirmed:** {'✅ Yes' if ev.get('attendance_confirmed') else '❌ No'}")
            if _is_coord:
                st.markdown(f"**Host Payment:** {ev.get('host_payment_status','—')} — ${ev.get('host_payment_amount',0):.2f}")
        with c3:
            st.markdown(f"**Host Contact:** {ev.get('contact_person','—')}")
            st.markdown(f"**Host Email:** {ev.get('host_email','—')}")
            st.markdown(f"**Host Phone:** {ev.get('host_phone','—')}")

        if ev.get("event_summary"):
            st.markdown("**Event Summary:**")
            st.info(ev["event_summary"])

        st.markdown("---")
        fc1, fc2 = st.columns(2)
        with fc1:
            st.markdown(f"**Facilitators ({len(facs)})**")
            for f in facs:
                st.markdown(f"- {f['name']} · {f.get('email','—')}")
            if not facs: st.caption("No facilitators assigned.")
        with fc2:
            if _is_coord:
                st.markdown(f"**Communications ({len(comms)})**")
                for c in comms[:5]:
                    date_str = str(c.get("sent_date",""))[:10] if c.get("sent_date") else ""
                    st.markdown(f"- {date_str} · {c.get('communication_type','')} · {c.get('subject','')[:40]}")
                if not comms: st.caption("No communications logged.")

        if fbs:
            st.markdown("---")
            st.markdown(f"**Participant Feedback ({len(fbs)})**")
            for fb in fbs:
                stars = "⭐" * (fb.get("rating") or 0)
                st.markdown(f"> {fb.get('feedback_text','')} {stars} — *{fb.get('participant_name','Anonymous')}*")
