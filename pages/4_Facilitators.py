import streamlit as st
import time
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.database import (
    log_activity, add_notification,
    get_all_facilitators, get_facilitator, add_facilitator,
    update_facilitator, delete_facilitator, get_facilitator_events, init_db,
    init_users, create_user, username_exists)
import secrets as _secrets
import string as _string
from utils.styles import inject_css, page_header

st.set_page_config(page_title="Facilitators · CC Platform", page_icon="🎤", layout="wide")
inject_css()
try:
    from utils.database import init_all
    init_all()
except ImportError:
    init_db()

role = st.session_state.get("user_role", None)
linked_id = st.session_state.get("linked_id", None)

if role is None:
    st.warning("Please log in.")
    st.stop()

if role not in ("coordinator", "facilitator", "cdfa", "nhh"):
    st.error("You do not have access to this page.")
    st.stop()

_role = role
_is_coord = (_role == "coordinator")
_user_label = st.session_state.get("user_label", "Coordinator")

page_header("🎤 Facilitators Management", "Manage the facilitator pool and event assignments")

if _role == "facilitator" and linked_id:
    # Facilitator can only view their own profile
    f = get_facilitator(linked_id)
    if not f:
        st.warning("Your facilitator profile was not found.")
        st.stop()
    st.markdown("### Your Profile")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**Name:** {f.get('name','—')}")
        st.markdown(f"**Email:** {f.get('email','—')}")
        st.markdown(f"**Phone:** {f.get('phone','—')}")
        st.markdown(f"**Specialization:** {f.get('specialization','—') or '—'}")
    with c2:
        addr_parts = [p for p in [f.get('address'), f.get('city'), f.get('state'), f.get('zip_code')] if p]
        st.markdown(f"**Address:** {', '.join(addr_parts) if addr_parts else '—'}")
        if f.get("notes"):
            st.caption(f"Notes: {f['notes']}")
    events = get_facilitator_events(linked_id)
    if events:
        st.markdown("### Your Events")
        for ev in events:
            badge = {"Scheduled":"🔵","Completed":"🟢","Cancelled":"🔴"}.get(ev.get("status",""),"⚪")
            st.markdown(f"- {badge} **{ev['event_name']}** · {ev['event_date']} · {ev.get('city','')}")
    st.stop()

if _is_coord:
    tab_list, tab_add, tab_edit = st.tabs(["📋 All Facilitators", "➕ Add Facilitator", "✏️ Edit Facilitator"])
else:
    st.info(f"👁️ You are viewing as **{_user_label}** — read-only access.")
    tab_list = st.tabs(["📋 All Facilitators"])[0]
    tab_add = None
    tab_edit = None

with tab_list:
    facs = get_all_facilitators()
    search = st.text_input("🔍 Search facilitators", placeholder="Name, email, specialization...")
    status_f = st.selectbox("Filter by payment status", ["All","Pending","Approved","Paid"])

    filtered = facs
    if search:
        s = search.lower()
        filtered = [f for f in filtered if s in (f.get("name","") + f.get("email","") + (f.get("specialization") or "")).lower()]
    if status_f != "All":
        filtered = [f for f in filtered if f.get("payment_status") == status_f]

    if not filtered:
        st.info("No facilitators found.")
    else:
        badge_map = {"Pending":"🟡","Approved":"🔵","Paid":"🟢"}
        for f in filtered:
            badge = badge_map.get(f.get("payment_status",""), "⚪")
            events = get_facilitator_events(f["facilitator_id"])
            with st.expander(f"{f['name']} — {f.get('specialization','') or 'General'} · {badge} {f.get('payment_status','')}"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.markdown(f"**Email:** {f.get('email','—')}")
                    st.markdown(f"**Phone:** {f.get('phone','—')}")
                    st.markdown(f"**Specialization:** {f.get('specialization','—') or '—'}")
                    addr_parts = [p for p in [f.get('address'), f.get('city'), f.get('state'), f.get('zip_code')] if p]
                    st.markdown(f"**Address:** {', '.join(addr_parts) if addr_parts else '—'}")
                with c2:
                    st.markdown(f"**Check Payable To:** {f.get('check_payable_to','—')}")
                    st.markdown(f"**Payment Amount:** ${f.get('payment_amount',0):.2f}")
                    st.markdown(f"**Payment Status:** {badge} {f.get('payment_status','—')}")
                with c3:
                    st.markdown(f"**Date Paid:** {f.get('payment_date','—') or '—'}")
                    st.markdown(f"**Events Assigned:** {len(events)}")
                if f.get("notes"):
                    st.caption(f"Notes: {f['notes']}")
                if events:
                    st.markdown("**Events:**")
                    for ev in events[:4]:
                        b2 = {"Scheduled":"🔵","Completed":"🟢","Cancelled":"🔴"}.get(ev.get("status",""),"⚪")
                        st.markdown(f"  - {b2} {ev['event_name']} · {ev['event_date']}")
                if _is_coord:
                    if st.button("✏️ Edit", key=f"edit_f_{f['facilitator_id']}"):
                        st.session_state["edit_fac_id"] = f["facilitator_id"]
                        st.info("Switch to Edit Facilitator tab.")

if tab_add:
  with tab_add:
    if st.session_state.get("facilitator_just_added"):
        st.session_state.pop("facilitator_just_added")
    st.markdown("### Add New Facilitator")
    with st.form("add_fac_form"):
        c1, c2 = st.columns(2)
        with c1:
            name   = st.text_input("Full Name *")
            email  = st.text_input("Email")
            phone  = st.text_input("Phone")
            spec   = st.text_input("Specialization", placeholder="e.g., History, Civic Engagement")
        with c2:
            address = st.text_input("Address")
            a_c1, a_c2, a_c3 = st.columns([3, 2, 2])
            with a_c1:
                city = st.text_input("City")
            with a_c2:
                state = st.text_input("State", value="NH")
            with a_c3:
                zip_code = st.text_input("Zip Code")
            payable = st.text_input("Check Payable To")
            amount  = st.number_input("Payment Amount ($)", min_value=0.0, step=50.0)
            pstatus = st.selectbox("Payment Status", ["Pending","Approved","Paid"])
        notes = st.text_area("Notes", height=80)
        if st.form_submit_button("💾 Save Facilitator", use_container_width=True):
            if st.session_state.get("facilitator_just_added"):
                pass
            elif not name:
                st.error("Name is required.")
            else:
                existing = [f for f in get_all_facilitators() if f["name"].lower()==name.lower()]
                if existing:
                    st.error(f"A facilitator named '{name}' already exists. Use Edit to update.")
                else:
                    st.session_state["facilitator_just_added"] = True
                    add_facilitator({"name":name,"email":email,"phone":phone,
                                      "address":address,"city":city,"state":state,"zip_code":zip_code,
                                      "specialization":spec,
                                      "check_payable_to":payable,"payment_amount":amount,
                                      "payment_status":pstatus,"notes":notes})
                    log_activity("Facilitator Added", f"{name} — {spec}")
                    add_notification(f"New facilitator added: {name}", "all")
                    st.success(f"Facilitator '{name}' added!")

                    # Auto-generate login credentials
                    try:
                        init_users()
                        # Find the newly added facilitator's ID
                        all_facs = get_all_facilitators()
                        new_fac = next((f for f in all_facs if f["name"].lower() == name.lower()), None)
                        if new_fac:
                            # Generate username: firstname.lastname
                            base_uname = name.strip().lower().replace(" ", ".")
                            uname = base_uname
                            counter = 2
                            while username_exists(uname):
                                uname = f"{base_uname}{counter}"
                                counter += 1
                            # Generate password: Fac- + 5 random alphanumeric
                            chars = _string.ascii_letters + _string.digits
                            pwd = "Fac-" + "".join(_secrets.choice(chars) for _ in range(5))
                            create_user(uname, pwd, "facilitator", new_fac["facilitator_id"])
                            st.success("🔑 Login credentials created!")
                            st.markdown(f"""
                            <div style='background:#D5F5E3;border-radius:8px;padding:1rem;margin:0.5rem 0'>
                                <strong>Share these credentials with {name}:</strong><br>
                                👤 Username: <code>{uname}</code><br>
                                🔑 Password: <code>{pwd}</code><br>
                                📋 Role: Facilitator
                            </div>
                            """, unsafe_allow_html=True)
                    except Exception as e:
                        st.warning(f"Facilitator saved but credential generation failed: {e}")

                    time.sleep(5)
                    st.rerun()

if tab_edit:
  with tab_edit:
    facs2 = get_all_facilitators()
    fac_opts = {f["facilitator_id"]: f["name"] for f in facs2}

    sel = st.selectbox("Select facilitator to edit", options=[""] + list(fac_opts.keys()),
                        format_func=lambda x: "— Select —" if x=="" else fac_opts[x])
    if sel:
        f = get_facilitator(sel)
        with st.form("edit_fac_form"):
            c1, c2 = st.columns(2)
            with c1:
                name   = st.text_input("Full Name *", value=f.get("name",""))
                email  = st.text_input("Email", value=f.get("email",""))
                phone  = st.text_input("Phone", value=f.get("phone",""))
                spec   = st.text_input("Specialization", value=f.get("specialization","") or "")
            with c2:
                address = st.text_input("Address", value=f.get("address","") or "")
                a_c1, a_c2, a_c3 = st.columns([3, 2, 2])
                with a_c1:
                    city = st.text_input("City", value=f.get("city","") or "")
                with a_c2:
                    state = st.text_input("State", value=f.get("state","NH") or "NH")
                with a_c3:
                    zip_code = st.text_input("Zip Code", value=f.get("zip_code","") or "")
                payable = st.text_input("Check Payable To", value=f.get("check_payable_to",""))
                amount  = st.number_input("Payment Amount ($)", value=float(f.get("payment_amount",0)), min_value=0.0, step=50.0)
                pstatus = st.selectbox("Payment Status", ["Pending","Approved","Paid"],
                                       index=["Pending","Approved","Paid"].index(f.get("payment_status","Pending")))
            import datetime
            pdate_val = None
            if f.get("payment_date"):
                try: pdate_val = datetime.date.fromisoformat(f["payment_date"])
                except: pass
            pdate = st.date_input("Payment Date", value=pdate_val)
            notes = st.text_area("Notes", value=f.get("notes","") or "", height=80)

            col_s, col_d = st.columns([3,1])
            with col_s:
                save = st.form_submit_button("💾 Save Changes", use_container_width=True)
            with col_d:
                delb = st.form_submit_button("🗑️ Delete", use_container_width=True)

            if save:
                update_facilitator(sel, {"name":name,"email":email,"phone":phone,
                                          "address":address,"city":city,"state":state,"zip_code":zip_code,
                                          "specialization":spec,
                                          "check_payable_to":payable,"payment_amount":amount,
                                          "payment_status":pstatus,
                                          "payment_date":str(pdate) if pdate else None,"notes":notes})
                log_activity("Facilitator Updated", f"{name} — payment: {pstatus}")
                st.success("✅ Facilitator updated!")
                time.sleep(3)
                st.rerun()
            if delb:
                delete_facilitator(sel)
                st.success("🗑️ Facilitator deleted.")
                time.sleep(3)
                st.rerun()
