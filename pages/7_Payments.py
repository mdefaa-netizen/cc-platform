import streamlit as st
import sys, os, requests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.database import (
    log_activity, add_notification,
    get_all_facilitators, update_facilitator,
    get_all_events, init_db, init_mileage,
    get_mileage_reimbursements, get_mileage_total_pending,
    add_mileage_reimbursement, update_mileage_status,
    delete_mileage_reimbursement
)
from utils.styles import inject_css, page_header

st.set_page_config(page_title="Payments · CC Platform", page_icon="💰", layout="wide")
inject_css()
init_db()
init_mileage()  # Ensure mileage_reimbursements table exists

role = st.session_state.get("user_role", None)
linked_id = st.session_state.get("linked_id", None)

if role is None:
    st.warning("Please log in.")
    st.stop()

if role not in ("coordinator", "cdfa", "nhh"):
    st.error("You do not have access to this page.")
    st.stop()

_role     = role
_is_coord = (_role == "coordinator")

page_header("💰 Payment Tracking", "Track and manage payments to facilitators")

facs = get_all_facilitators()

# ── KPI row ────────────────────────────────────────────────────────────────────
total_pending   = sum(f.get("payment_amount",0) or 0 for f in facs if f.get("payment_status")=="Pending")
total_approved  = sum(f.get("payment_amount",0) or 0 for f in facs if f.get("payment_status")=="Approved")
total_paid      = sum(f.get("payment_amount",0) or 0 for f in facs if f.get("payment_status")=="Paid")
total_confirmed = sum(f.get("payment_amount",0) or 0 for f in facs if f.get("payment_status")=="Confirmed")
total_program   = total_pending + total_approved + total_paid + total_confirmed
total_outstanding = total_pending + total_approved + total_paid  # not yet confirmed

c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    st.markdown(f"""<div class="kpi-card red">
    <div class="kpi-label">Pending</div><div class="kpi-value">${total_pending:,.2f}</div>
    <div class="kpi-sub">{sum(1 for f in facs if f.get('payment_status')=='Pending')} facilitator(s)</div>
    </div>""", unsafe_allow_html=True)
with c2:
    st.markdown(f"""<div class="kpi-card gold">
    <div class="kpi-label">Approved</div><div class="kpi-value">${total_approved:,.2f}</div>
    <div class="kpi-sub">{sum(1 for f in facs if f.get('payment_status')=='Approved')} facilitator(s)</div>
    </div>""", unsafe_allow_html=True)
with c3:
    st.markdown(f"""<div class="kpi-card">
    <div class="kpi-label">Paid (Awaiting Confirmation)</div><div class="kpi-value">${total_paid:,.2f}</div>
    <div class="kpi-sub">{sum(1 for f in facs if f.get('payment_status')=='Paid')} facilitator(s)</div>
    </div>""", unsafe_allow_html=True)
with c4:
    st.markdown(f"""<div class="kpi-card green">
    <div class="kpi-label">Confirmed Received</div><div class="kpi-value">${total_confirmed:,.2f}</div>
    <div class="kpi-sub">{sum(1 for f in facs if f.get('payment_status')=='Confirmed')} facilitator(s)</div>
    </div>""", unsafe_allow_html=True)
with c5:
    st.markdown(f"""<div class="kpi-card gold">
    <div class="kpi-label">Outstanding Balance</div><div class="kpi-value">${total_outstanding:,.2f}</div>
    <div class="kpi-sub">Not yet confirmed received</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

tab_summary, tab_list, tab_update, tab_triggers, tab_mileage = st.tabs(
    ["📊 Payment Summary", "📋 All Payments", "✏️ Update Payment", "🔔 Payment Triggers", "🚗 Mileage"]
)

STATUS_ICONS = {
    "Pending":   "🟡",
    "Approved":  "🔵",
    "Paid":      "🟠",
    "Confirmed": "🟢",
}

# ── Tab: Payment Summary ────────────────────────────────────────────────────────
with tab_summary:
    st.markdown("### 💼 Facilitator Payment Summary")
    st.caption("Stipend + Mileage = Total to pay per facilitator")

    # Pull mileage data safely (table guaranteed by init_mileage above)
    all_mileage = get_mileage_reimbursements()
    mileage_total_pending = get_mileage_total_pending()

    # Build per-facilitator summary
    mileage_by_fac = {}
    for m in all_mileage:
        fid = m["facilitator_id"]
        if fid not in mileage_by_fac:
            mileage_by_fac[fid] = {"amount": 0.0, "miles": 0.0, "count": 0}
        mileage_by_fac[fid]["amount"] += m.get("reimbursement_amount", 0) or 0
        mileage_by_fac[fid]["miles"]  += m.get("round_trip_miles", 0) or 0
        mileage_by_fac[fid]["count"]  += 1

    if not facs:
        st.info("No facilitators found. Add facilitators to begin tracking payments.")
    else:
        import pandas as pd

        rows = []
        grand_stipend  = 0.0
        grand_mileage  = 0.0
        grand_total    = 0.0

        for f in facs:
            fid        = f["facilitator_id"]
            stipend    = f.get("payment_amount", 0) or 0
            mil_amt    = mileage_by_fac.get(fid, {"amount": 0.0})["amount"]
            total_owed = stipend + mil_amt
            status     = f.get("payment_status", "Pending")
            badge      = STATUS_ICONS.get(status, "⚪")

            grand_stipend += stipend
            grand_mileage += mil_amt
            grand_total   += total_owed

            rows.append({
                "Facilitator Name":      f["name"],
                "Stipend":               f"${stipend:,.2f}",
                "Mileage Reimbursement": f"${mil_amt:,.2f}",
                "Total to Pay":          f"${total_owed:,.2f}",
                "Payment Status":        f"{badge} {status}",
            })

        # Totals row
        rows.append({
            "Facilitator Name":      "TOTALS",
            "Stipend":               f"${grand_stipend:,.2f}",
            "Mileage Reimbursement": f"${grand_mileage:,.2f}",
            "Total to Pay":          f"${grand_total:,.2f}",
            "Payment Status":        "",
        })

        df = pd.DataFrame(rows)

        # Bold the totals row
        def _bold_last_row(row):
            is_last = row.name == len(df) - 1
            return ["font-weight: bold" if is_last else "" for _ in row]

        st.dataframe(
            df.style.apply(_bold_last_row, axis=1),
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("<br>", unsafe_allow_html=True)

        # Mileage breakdown callout
        if all_mileage:
            st.markdown("#### 🚗 Mileage Reimbursement Breakdown")
            pending_count = sum(1 for m in all_mileage if m["status"] == "Pending")
            paid_count    = sum(1 for m in all_mileage if m["status"] == "Paid")
            c1m, c2m, c3m = st.columns(3)
            with c1m:
                st.metric("Total Mileage Records", len(all_mileage))
            with c2m:
                st.metric("Pending Reimbursements", f"${mileage_total_pending:,.2f}",
                          delta=f"{pending_count} record(s)")
            with c3m:
                total_miles_all = sum(m.get("round_trip_miles", 0) or 0 for m in all_mileage)
                st.metric("Total Miles (All Records)", f"{total_miles_all:,.1f} mi")

            st.markdown("*Use the 🚗 Mileage tab above to add or manage reimbursements.*")
        else:
            st.info("💡 No mileage reimbursements recorded yet. Use the **🚗 Mileage** tab above to add travel reimbursements for facilitators.")


with tab_list:
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        status_filter = st.selectbox("Filter by status",
                                      ["All","Pending","Approved","Paid","Confirmed"])
    with col_f2:
        search = st.text_input("Search facilitator", placeholder="Name...")

    filtered = facs
    if status_filter != "All":
        filtered = [f for f in filtered if f.get("payment_status") == status_filter]
    if search:
        filtered = [f for f in filtered if search.lower() in f.get("name","").lower()]

    if not filtered:
        st.info("No facilitators found.")
    else:
        for f in filtered:
            fid = f["facilitator_id"]
            stipend = f.get("payment_amount", 0) or 0
            mil_amt = mileage_by_fac.get(fid, {"amount": 0.0})["amount"]
            check_total = stipend + mil_amt
            badge = STATUS_ICONS.get(f.get("payment_status",""), "⚪")
            with st.expander(f"🎤 {f['name']} — {badge} {f.get('payment_status','')} — Check Total: ${check_total:,.2f}"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.markdown(f"**Name:** {f.get('name','')}")
                    st.markdown(f"**Email:** {f.get('email','—')}")
                    st.markdown(f"**Phone:** {f.get('phone','—')}")
                with c2:
                    st.markdown(f"**Check Payable To:** {f.get('check_payable_to','—')}")
                    st.markdown(f"**Stipend:** ${stipend:,.2f}")
                    st.markdown(f"**Mileage Reimbursement:** ${mil_amt:,.2f}" if mil_amt > 0 else "**Mileage Reimbursement:** —")
                    st.markdown(f"**Check Total:** ${check_total:,.2f}")
                    st.markdown(f"**Status:** {badge} {f.get('payment_status','—')}")
                with c3:
                    st.markdown(f"**Date Paid:** {f.get('payment_date','—') or '—'}")
                    st.markdown(f"**Specialization:** {f.get('specialization','—') or '—'}")

                # Payment flow buttons
                if _is_coord:
                    st.markdown("---")
                    btn_cols = st.columns(4)
                    status = f.get("payment_status","Pending")

                    with btn_cols[0]:
                        if status != "Approved" and status != "Confirmed":
                            if st.button("✅ Approve", key=f"approve_{f['facilitator_id']}",
                                         use_container_width=True):
                                update_facilitator(f["facilitator_id"], {**f, "payment_status":"Approved"})
                                log_activity("Payment Approved", f"{f['name']} — ${f.get('payment_amount',0):.2f}")
                                add_notification(f"Payment approved for {f['name']}: ${f.get('payment_amount',0):.2f}", "all")
                                st.success("✅ Approved!")
                                st.rerun()

                    with btn_cols[1]:
                        if status == "Approved":
                            if st.button("💸 Mark Paid", key=f"paid_{f['facilitator_id']}",
                                         use_container_width=True):
                                import datetime
                                updated = {**f, "payment_status":"Paid",
                                           "payment_date": str(datetime.date.today())}
                                update_facilitator(f["facilitator_id"], updated)
                                log_activity("Payment Sent", f"{f['name']} — ${f.get('payment_amount',0):.2f}")
                                add_notification(f"Payment sent to {f['name']}: ${f.get('payment_amount',0):.2f} — awaiting confirmation", "all")
                                st.success("💸 Marked as Paid — awaiting facilitator confirmation!")
                                st.rerun()

                    with btn_cols[2]:
                        if status == "Paid":
                            if st.button("🟢 Confirm Received", key=f"confirm_{f['facilitator_id']}",
                                         use_container_width=True):
                                updated = {**f, "payment_status":"Confirmed"}
                                update_facilitator(f["facilitator_id"], updated)
                                log_activity("Payment Confirmed", f"{f['name']} confirmed receipt of ${f.get('payment_amount',0):.2f}")
                                add_notification(f"Payment confirmed by {f['name']}: ${f.get('payment_amount',0):.2f} — deducted from outstanding balance", "all")
                                st.success("🟢 Payment confirmed! Deducted from outstanding balance.")
                                st.rerun()

                    with btn_cols[3]:
                        if status == "Confirmed":
                            st.markdown("✅ **Complete**")

with tab_update:
    st.markdown("### Update Payment Details")
    fac_opts = {f["facilitator_id"]: f["name"] for f in facs}
    sel = st.selectbox("Select facilitator", options=[""] + list(fac_opts.keys()),
                        format_func=lambda x: "— Select —" if x=="" else fac_opts[x])
    if sel:
        f = next((x for x in facs if x["facilitator_id"]==sel), {})
        with st.form("update_payment_form"):
            c1, c2 = st.columns(2)
            with c1:
                new_status = st.selectbox("Payment Status",
                                           ["Pending","Approved","Paid","Confirmed"],
                                           index=["Pending","Approved","Paid","Confirmed"].index(
                                               f.get("payment_status","Pending")))
                new_amount = st.number_input("Payment Amount ($)",
                                              value=float(f.get("payment_amount",0)),
                                              min_value=0.0, step=50.0)
            with c2:
                import datetime
                pdate_val = None
                if f.get("payment_date"):
                    try: pdate_val = datetime.date.fromisoformat(f["payment_date"])
                    except: pass
                new_date  = st.date_input("Payment Date", value=pdate_val)
                new_payto = st.text_input("Check Payable To",
                                           value=f.get("check_payable_to",""))
            new_notes = st.text_area("Notes", value=f.get("notes","") or "")

            if st.form_submit_button("💾 Update Payment", use_container_width=True):
                updated = {**f, "payment_status": new_status,
                           "payment_amount": new_amount,
                           "payment_date":   str(new_date) if new_date else None,
                           "check_payable_to": new_payto,
                           "notes": new_notes}
                update_facilitator(sel, updated)
                log_activity("Payment Updated",
                             f"{f.get('name','')} → {new_status} — ${new_amount:.2f}")
                st.success(f"✅ Payment updated for {f.get('name','')} → {new_status}")
                st.rerun()

with tab_triggers:
    st.markdown("### 🔔 Payment Trigger Checklist")
    st.caption("Approve payment when: Event Completed ✓ + Attendance Confirmed ✓ + Invoice Submitted ✓")

    events = get_all_events()
    completed_events = [e for e in events if e.get("status") == "Completed"]

    if not completed_events:
        st.info("No completed events yet. Mark events as Completed to see payment triggers.")
    else:
        if "invoice_submitted" not in st.session_state:
            st.session_state["invoice_submitted"] = {}

        for ev in completed_events:
            eid  = ev["event_id"]
            att  = bool(ev.get("attendance_confirmed"))
            inv  = st.session_state["invoice_submitted"].get(str(eid), False)
            ready = att and inv

            with st.expander(f"{'✅' if ready else '⚠️'} {ev['event_name']} — {ev['event_date']}"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.markdown("**Event Completed:** ✅ Yes")
                with c2:
                    st.markdown(f"**Attendance Confirmed:** {'✅ Yes' if att else '❌ No'}")
                with c3:
                    inv_check = st.checkbox("Invoice Submitted", value=inv, key=f"inv_{eid}")
                    st.session_state["invoice_submitted"][str(eid)] = inv_check

                if ready:
                    st.success("🟢 All criteria met — ready to approve payment!")
                else:
                    missing = []
                    if not att: missing.append("Attendance Not Confirmed")
                    if not inv_check: missing.append("Invoice Not Submitted")
                    st.warning(f"Missing: {', '.join(missing)}")

# ── Tab: Mileage ───────────────────────────────────────────────────────────────
IRS_RATE_2026 = 0.725  # $0.725 per mile — IRS 2026 standard rate

def _get_maps_api_key():
    try:
        return st.secrets.get("GOOGLE_MAPS_API_KEY", "")
    except Exception:
        return st.session_state.get("google_maps_key", "")

def _calculate_distance_google(origin, destination, api_key):
    """Use Google Maps Distance Matrix API to get driving distance in miles."""
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": origin,
        "destinations": destination,
        "units": "imperial",
        "mode": "driving",
        "key": api_key,
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if data["status"] == "OK":
            element = data["rows"][0]["elements"][0]
            if element["status"] == "OK":
                distance_text = element["distance"]["text"]
                distance_miles = element["distance"]["value"] / 1609.344
                return distance_miles, distance_text, None
            else:
                return None, None, f"Route not found: {element['status']}"
        else:
            return None, None, f"API error: {data['status']}"
    except Exception as e:
        return None, None, str(e)

def _calculate_distance_fallback(origin, destination):
    """Fallback: use OpenStreetMap Nominatim + Haversine for approximate distance."""
    import math
    def geocode(address):
        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": address, "format": "json", "limit": 1}
        headers = {"User-Agent": "CCPlatform/1.0"}
        try:
            r = requests.get(url, params=params, headers=headers, timeout=10)
            results = r.json()
            if results:
                return float(results[0]["lat"]), float(results[0]["lon"])
        except Exception:
            pass
        return None, None

    lat1, lon1 = geocode(origin)
    lat2, lon2 = geocode(destination)

    if not all([lat1, lon1, lat2, lon2]):
        return None, None, "Could not geocode one or both addresses."

    R = 3958.8  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = R * c * 1.2  # +20% for road routing vs straight line
    return distance, f"~{distance:.1f} mi (estimated)", None

with tab_mileage:
    st.markdown("### 🚗 Mileage Reimbursement")
    st.markdown(f"""
    <div style='background:#e8f5e9;border-left:4px solid #2e7d32;padding:0.8rem 1rem;
    border-radius:6px;margin-bottom:1rem;font-size:0.9rem'>
    📋 <strong>2026 IRS Standard Mileage Rate: $0.725 per mile</strong> —
    Rate effective January 1, 2026. Round trip (×2) applied automatically.
    </div>
    """, unsafe_allow_html=True)

    # Mileage KPIs
    mil_all          = get_mileage_reimbursements()
    mil_pending_amt  = sum(m["reimbursement_amount"] for m in mil_all if m["status"] == "Pending")
    mil_approved_amt = sum(m["reimbursement_amount"] for m in mil_all if m["status"] == "Approved")
    mil_paid_amt     = sum(m["reimbursement_amount"] for m in mil_all if m["status"] == "Paid")
    mil_total_miles  = sum(m["round_trip_miles"] for m in mil_all)

    mk1, mk2, mk3, mk4 = st.columns(4)
    with mk1:
        st.markdown(f"""<div class="kpi-card red">
        <div class="kpi-label">Pending Mileage</div>
        <div class="kpi-value">${mil_pending_amt:,.2f}</div>
        <div class="kpi-sub">{sum(1 for m in mil_all if m['status']=='Pending')} reimbursement(s)</div>
        </div>""", unsafe_allow_html=True)
    with mk2:
        st.markdown(f"""<div class="kpi-card gold">
        <div class="kpi-label">Approved</div>
        <div class="kpi-value">${mil_approved_amt:,.2f}</div>
        <div class="kpi-sub">{sum(1 for m in mil_all if m['status']=='Approved')} reimbursement(s)</div>
        </div>""", unsafe_allow_html=True)
    with mk3:
        st.markdown(f"""<div class="kpi-card green">
        <div class="kpi-label">Paid</div>
        <div class="kpi-value">${mil_paid_amt:,.2f}</div>
        <div class="kpi-sub">{sum(1 for m in mil_all if m['status']=='Paid')} reimbursement(s)</div>
        </div>""", unsafe_allow_html=True)
    with mk4:
        st.markdown(f"""<div class="kpi-card">
        <div class="kpi-label">Total Miles (All)</div>
        <div class="kpi-value">{mil_total_miles:,.1f} mi</div>
        <div class="kpi-sub">Round trip across all events</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    mil_tab_calc, mil_tab_log, mil_tab_settings = st.tabs(
        ["🗺️ Calculate Mileage", "📋 Reimbursement Log", "⚙️ Settings"])

    # ── Sub-tab: Calculate Mileage ─────────────────────────────────────────────
    with mil_tab_calc:
        mil_facs   = get_all_facilitators()
        mil_events = get_all_events()

        if not mil_facs:
            st.info("No facilitators added yet. Add facilitators first.")
        else:
            st.markdown("### 🧮 Mileage Calculator")

            col_left, col_right = st.columns([1, 1])

            with col_left:
                mil_fac_opts = {f["facilitator_id"]: f["name"] for f in mil_facs}
                sel_fac = st.selectbox("Select Facilitator", options=list(mil_fac_opts.keys()),
                                       format_func=lambda x: mil_fac_opts[x],
                                       key="mil_sel_fac")
                fac = next((f for f in mil_facs if f["facilitator_id"] == sel_fac), {})

                fac_full_address = ""
                if fac.get("address"):
                    parts = [fac.get("address", ""), fac.get("city", ""),
                             fac.get("state", "NH"), fac.get("zip_code", "")]
                    fac_full_address = ", ".join(p for p in parts if p)

                fac_address = st.text_input("Facilitator Address (origin)",
                                             value=fac_full_address,
                                             placeholder="123 Main St, Concord, NH 03301",
                                             key="mil_fac_addr")
                if not fac_full_address:
                    st.caption("💡 Add address to facilitator profile to auto-fill")

            with col_right:
                ev_opts = {0: "— Manual address —"}
                ev_opts.update({e["event_id"]: f"{e['event_name']} — {e['event_date']}" for e in mil_events})
                sel_ev = st.selectbox("Select Event (auto-fills address)", options=list(ev_opts.keys()),
                                      format_func=lambda x: ev_opts[x],
                                      key="mil_sel_ev")

                ev = next((e for e in mil_events if e["event_id"] == sel_ev), {})
                ev_address_default = ""
                if ev:
                    parts = [ev.get("venue_address", ""), ev.get("city", ""), "NH"]
                    ev_address_default = ", ".join(p for p in parts if p)

                ev_address = st.text_input("Event Venue Address (destination)",
                                            value=ev_address_default,
                                            placeholder="45 Green Street, Concord, NH 03301",
                                            key="mil_ev_addr")

            st.markdown("---")
            col_r1, col_r2 = st.columns(2)
            with col_r1:
                rate = st.number_input("Rate per mile ($)", value=IRS_RATE_2026,
                                        min_value=0.01, step=0.005, format="%.3f",
                                        help="2026 IRS Standard Rate: $0.725/mile",
                                        key="mil_rate")
            with col_r2:
                mil_notes = st.text_input("Notes (optional)", placeholder="e.g. Event prep trip",
                                           key="mil_notes")

            api_key = _get_maps_api_key()

            if st.button("🗺️ Calculate Distance & Reimbursement", use_container_width=True,
                          type="primary", key="mil_calc_btn"):
                if not fac_address or not ev_address:
                    st.error("Please enter both addresses.")
                else:
                    with st.spinner("Calculating driving distance..."):
                        if api_key:
                            dist, dist_text, err = _calculate_distance_google(
                                fac_address, ev_address, api_key)
                            method = "Google Maps"
                        else:
                            dist, dist_text, err = _calculate_distance_fallback(
                                fac_address, ev_address)
                            method = "OpenStreetMap (estimated)"

                    if err:
                        st.error(f"❌ Could not calculate distance: {err}")
                    else:
                        round_trip = dist * 2
                        amount = round_trip * rate

                        st.session_state["mileage_calc"] = {
                            "facilitator_id":      sel_fac,
                            "event_id":            sel_ev if sel_ev else None,
                            "facilitator_address":  fac_address,
                            "event_address":        ev_address,
                            "distance_miles":       dist,
                            "round_trip_miles":     round_trip,
                            "rate_per_mile":        rate,
                            "reimbursement_amount": amount,
                            "notes":               mil_notes,
                            "method":              method,
                            "dist_text":           dist_text,
                        }

            if "mileage_calc" in st.session_state:
                calc = st.session_state["mileage_calc"]
                st.markdown("---")
                st.markdown("### 📊 Calculation Result")

                r1, r2, r3, r4 = st.columns(4)
                with r1:
                    st.metric("One Way", f"{calc['distance_miles']:.1f} miles")
                with r2:
                    st.metric("Round Trip", f"{calc['round_trip_miles']:.1f} miles")
                with r3:
                    st.metric("Rate", f"${calc['rate_per_mile']:.3f}/mile")
                with r4:
                    st.metric("💰 Reimbursement", f"${calc['reimbursement_amount']:.2f}")

                st.caption(f"📍 Method: {calc['method']} · Distance: {calc['dist_text']}")

                st.markdown(f"""
                <div style='background:#e3f2fd;padding:1rem;border-radius:8px;
                border-left:4px solid #1565c0;margin:0.5rem 0'>
                <strong>Calculation:</strong> {calc['distance_miles']:.1f} mi (one way)
                × 2 (round trip) = <strong>{calc['round_trip_miles']:.1f} miles</strong>
                × ${calc['rate_per_mile']:.3f}/mile =
                <strong style='color:#1565c0;font-size:1.1rem'>
                ${calc['reimbursement_amount']:.2f}</strong>
                </div>
                """, unsafe_allow_html=True)

                col_save, col_clear = st.columns(2)
                with col_save:
                    if st.button("💾 Save Reimbursement", use_container_width=True,
                                  type="primary", key="mil_save_btn"):
                        add_mileage_reimbursement(calc)
                        fac_name = mil_fac_opts.get(calc["facilitator_id"], "Facilitator")
                        log_activity("Mileage Calculated",
                                     f"{fac_name} — {calc['round_trip_miles']:.1f} mi — ${calc['reimbursement_amount']:.2f}")
                        del st.session_state["mileage_calc"]
                        st.success("✅ Mileage reimbursement saved!")
                        st.rerun()
                with col_clear:
                    if st.button("🗑️ Clear", use_container_width=True, key="mil_clear_btn"):
                        del st.session_state["mileage_calc"]
                        st.rerun()

    # ── Sub-tab: Reimbursement Log ─────────────────────────────────────────────
    with mil_tab_log:
        st.markdown("### 📋 All Mileage Reimbursements")

        facs_for_filter = [{"facilitator_id": 0, "name": "All"}] + get_all_facilitators()
        fac_filter = st.selectbox("Filter by facilitator",
                                   options=[f["facilitator_id"] for f in facs_for_filter],
                                   format_func=lambda x: next(
                                       (f["name"] for f in facs_for_filter if f["facilitator_id"] == x), ""),
                                   key="mil_fac_filter")
        mil_status_filter = st.selectbox("Filter by status", ["All", "Pending", "Approved", "Paid"],
                                          key="mil_status_filter")

        records = get_mileage_reimbursements(
            facilitator_id=fac_filter if fac_filter else None)
        if mil_status_filter != "All":
            records = [r for r in records if r["status"] == mil_status_filter]

        MIL_STATUS_ICONS = {"Pending": "🟡", "Approved": "🔵", "Paid": "🟢"}

        if not records:
            st.info("No mileage reimbursements recorded yet.")
        else:
            for r in records:
                icon = MIL_STATUS_ICONS.get(r["status"], "⚪")
                with st.expander(
                    f"🚗 {r.get('facilitator_name', '?')} — "
                    f"{r.get('event_name', 'Manual')} — "
                    f"{icon} {r['status']} — ${r['reimbursement_amount']:.2f}"):

                    mc1, mc2, mc3 = st.columns(3)
                    with mc1:
                        st.markdown(f"**From:** {r['facilitator_address']}")
                        st.markdown(f"**To:** {r['event_address']}")
                    with mc2:
                        st.markdown(f"**One Way:** {r['distance_miles']:.1f} mi")
                        st.markdown(f"**Round Trip:** {r['round_trip_miles']:.1f} mi")
                        st.markdown(f"**Rate:** ${r['rate_per_mile']:.3f}/mile")
                    with mc3:
                        st.markdown(f"**Amount:** ${r['reimbursement_amount']:.2f}")
                        st.markdown(f"**Status:** {icon} {r['status']}")
                        st.markdown(f"**Calculated:** {r['calculated_at'][:10]}")

                    if r.get("notes"):
                        st.markdown(f"**Notes:** {r['notes']}")

                    st.markdown("---")
                    btn1, btn2, btn3 = st.columns(3)
                    with btn1:
                        if r["status"] == "Pending":
                            if st.button("✅ Approve", key=f"mapprove_{r['mileage_id']}",
                                         use_container_width=True):
                                update_mileage_status(r["mileage_id"], "Approved")
                                st.success("Approved!")
                                st.rerun()
                    with btn2:
                        if r["status"] == "Approved":
                            if st.button("💸 Mark Paid", key=f"mpaid_{r['mileage_id']}",
                                         use_container_width=True):
                                update_mileage_status(r["mileage_id"], "Paid")
                                st.success("Marked as Paid!")
                                st.rerun()
                    with btn3:
                        if st.button("🗑️ Delete", key=f"mdel_{r['mileage_id']}",
                                     use_container_width=True):
                            delete_mileage_reimbursement(r["mileage_id"])
                            st.success("Deleted.")
                            st.rerun()

    # ── Sub-tab: Settings ──────────────────────────────────────────────────────
    with mil_tab_settings:
        st.markdown("### ⚙️ Google Maps API Settings")
        st.markdown("""
        For **exact driving distances**, a Google Maps API key is needed.
        Without it, the platform uses **OpenStreetMap** which gives estimated distances (~80-90% accurate).

        #### How to get a free Google Maps API key:
        1. Go to [console.cloud.google.com](https://console.cloud.google.com)
        2. Create a new project
        3. Enable **Distance Matrix API**
        4. Go to **Credentials** → Create API Key
        5. Copy the key and paste it below

        > 💡 Google gives **$200 free credit/month** — more than enough for this program.
        """)

        current_key = _get_maps_api_key()
        new_key = st.text_input("Google Maps API Key",
                                 value=current_key,
                                 type="password",
                                 placeholder="AIza...",
                                 key="mil_api_key")

        if st.button("💾 Save API Key (this session)", use_container_width=True, key="mil_save_key"):
            st.session_state["google_maps_key"] = new_key
            st.success("✅ Key saved for this session! Add to secrets.toml for permanent use.")

        st.markdown("---")
        st.markdown("### 📐 Current Mileage Rate")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"""
            | Year | Rate |
            |------|------|
            | 2024 | $0.670/mile |
            | 2025 | $0.700/mile |
            | **2026** | **$0.725/mile** ← Current |
            """)
        with col2:
            st.info("The rate is pre-set to the 2026 IRS standard rate of $0.725/mile. "
                    "You can override it per calculation in the Calculator tab.")
