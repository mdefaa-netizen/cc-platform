import streamlit as st
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.database import (
    log_activity, add_notification,
    get_all_events, get_all_hosts, get_all_facilitators,
    get_all_feedback, get_event_facilitators,
    log_report, get_all_reports, init_db)
from utils.report_utils import generate_excel, generate_pdf
from utils.styles import inject_css, page_header
from datetime import datetime

st.set_page_config(page_title="Reports · CC Platform", page_icon="📊", layout="wide")
inject_css()
init_db()

if not st.session_state.get("authenticated"):
    st.warning("Please sign in from the main page.")
    st.stop()

# Role awareness
_role = st.session_state.get("user_role", "coordinator")
_is_coord = (_role == "coordinator")
_user_label = st.session_state.get("user_label", "Coordinator")

page_header("📊 Reports", "Generate Excel and PDF reports for NH Humanities & CDFA")

tab_gen, tab_hist = st.tabs(["🖨️ Generate Report", "📁 Report History"])

with tab_gen:
    st.markdown("### Report Configuration")
    col_cfg, col_prev = st.columns([1, 1])

    with col_cfg:
        report_type = st.selectbox("Report Format", ["Excel (.xlsx)","PDF","Both (Excel + PDF)"])
        date_mode   = st.selectbox("Date Range", ["All Events","Custom Range","Specific Event"])

        events_all = get_all_events()

        selected_events = events_all
        date_label = "All Events"

        if date_mode == "Custom Range":
            import datetime
            c1, c2 = st.columns(2)
            with c1:
                d_from = st.date_input("From Date", value=datetime.date(2025,1,1))
            with c2:
                d_to   = st.date_input("To Date",   value=datetime.date.today())
            selected_events = [e for e in events_all
                               if e.get("event_date","") >= str(d_from)
                               and e.get("event_date","") <= str(d_to)]
            date_label = f"{d_from} to {d_to}"

        elif date_mode == "Specific Event":
            ev_opts = {e["event_id"]: f"{e['event_name']} ({e['event_date']})" for e in events_all}
            sel_ev  = st.selectbox("Select Event", options=list(ev_opts.keys()),
                                    format_func=lambda x: ev_opts[x])
            selected_events = [e for e in events_all if e["event_id"]==sel_ev]
            if selected_events:
                date_label = selected_events[0].get("event_name","")

    with col_prev:
        st.markdown("### Report Will Include")
        st.markdown(f"""
        <div class="section-box">
            <p>📅 <strong>Events:</strong> {len(selected_events)} events</p>
            <p>📋 Contents:</p>
            <ul style='margin:0;padding-left:1.2rem;font-size:0.9rem'>
                <li>Events Summary Table</li>
                <li>Attendance Data & Totals</li>
                <li>Event Narrative Summaries</li>
                <li>Payment Summary (Hosts & Facilitators)</li>
                <li>Participant Feedback</li>
                <li>Host & Facilitator Contact Directory</li>
            </ul>
            <p style='margin-top:0.8rem'><strong>Period:</strong> {date_label}</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    if st.button("🖨️ Generate Report", use_container_width=True, type="primary"):
        if not selected_events:
            st.warning("No events match the selected criteria.")
        else:
            # Enrich events with facilitator names
            for e in selected_events:
                facs_ev = get_event_facilitators(e["event_id"])
                e["facilitator_names"] = ", ".join(f["name"] for f in facs_ev)

            hosts      = get_all_hosts()
            facs       = get_all_facilitators()
            feedback   = get_all_feedback()
            # Filter feedback to selected events only
            ev_ids = {e["event_id"] for e in selected_events}
            feedback = [f for f in feedback if f.get("event_id") in ev_ids]

            timestamp  = datetime.now().strftime("%Y%m%d_%H%M")

            with st.spinner("Generating report..."):
                if "Excel" in report_type or "Both" in report_type:
                    xlsx_bytes  = generate_excel(selected_events, hosts, facs, feedback, date_label)
                    fname_xlsx  = f"NHH_CDFA_Report_{timestamp}.xlsx"
                    log_report({"report_type":"Excel","report_name":fname_xlsx,"notes":date_label})
                    st.download_button(
                        label="⬇️ Download Excel Report",
                        data=xlsx_bytes,
                        file_name=fname_xlsx,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )

                if "PDF" in report_type or "Both" in report_type:
                    pdf_bytes   = generate_pdf(selected_events, hosts, facs, feedback, date_label)
                    fname_pdf   = f"NHH_CDFA_Report_{timestamp}.pdf"
                    log_report({"report_type":"PDF","report_name":fname_pdf,"notes":date_label})
                    st.download_button(
                        label="⬇️ Download PDF Report",
                        data=pdf_bytes,
                        file_name=fname_pdf,
                        mime="application/pdf",
                        use_container_width=True,
                    )

                st.success(f"✅ Report generated for {len(selected_events)} event(s)!")

    # Quick stats preview
    st.markdown("---")
    st.markdown("### 📈 Quick Program Stats")
    all_events = get_all_events()
    total_att  = sum(e.get("attendance_count") or 0 for e in all_events)
    completed  = [e for e in all_events if e.get("status")=="Completed"]
    hosts_all  = get_all_hosts()
    facs_all   = get_all_facilitators()
    paid_h     = sum(h.get("payment_amount",0) or 0 for h in hosts_all  if h.get("payment_status")=="Paid")
    paid_f     = sum(f.get("payment_amount",0) or 0 for f in facs_all   if f.get("payment_status")=="Paid")

    qc1, qc2, qc3, qc4 = st.columns(4)
    with qc1:
        st.metric("Total Events", len(all_events))
    with qc2:
        st.metric("Completed Events", len(completed))
    with qc3:
        st.metric("Total Attendance", total_att)
    with qc4:
        st.metric("Total Paid Out", f"${paid_h+paid_f:,.2f}")

with tab_hist:
    st.markdown("### Previously Generated Reports")
    reports = get_all_reports()
    if not reports:
        st.info("No reports generated yet.")
    else:
        for r in reports:
            icon = "📊" if r.get("report_type")=="Excel" else "📄"
            date_str = r.get("generated_date","")[:16] if r.get("generated_date") else ""
            st.markdown(f"""
            <div class="feed-item">
                {icon} <strong>{r.get('report_name','')}</strong>
                <span class="feed-date"> · {date_str} · {r.get('notes','')}</span>
            </div>
            """, unsafe_allow_html=True)
