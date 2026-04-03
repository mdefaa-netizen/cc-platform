import streamlit as st
import time
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.database import (log_activity, add_notification, get_all_hosts, get_host,
    add_host, update_host, delete_host, get_host_events, init_db,
    init_users, create_user, username_exists)
import secrets as _secrets
import string as _string
from utils.styles import inject_css, page_header

st.set_page_config(page_title="Hosts · CC Platform", page_icon="👥", layout="wide")
inject_css()
try:
    from utils.database import init_all
    init_all()
except ImportError:
    init_db()

if not st.session_state.get("authenticated"):
    st.warning("Please log in.")
    st.stop()
role = st.session_state.get("user_role", None)
linked_id = st.session_state.get("linked_id", None)

if role is None:
    st.warning("Please log in.")
    st.stop()

if role not in ("coordinator", "host", "cdfa", "nhh"):
    st.error("You do not have access to this page.")
    st.stop()

_role = role
_is_coord = (_role == "coordinator")
_user_label = st.session_state.get("user_label", "Coordinator")

page_header("👥 Hosts Management", "Manage host venues and contacts for all events")

if _role == "host" and linked_id:
    # Host can only view/edit their own profile
    h = get_host(linked_id)
    if not h:
        st.warning("Your host profile was not found.")
        st.stop()
    st.markdown("### Your Profile")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**Name:** {h.get('name','—')}")
        st.markdown(f"**Venue:** {h.get('venue_name','—')}")
        st.markdown(f"**Contact:** {h.get('contact_person','—')}")
        st.markdown(f"**Email:** {h.get('email','—')}")
        st.markdown(f"**Phone:** {h.get('phone','—')}")
    with c2:
        addr_parts = [p for p in [h.get('address'), h.get('city'), h.get('state'), h.get('zip_code')] if p]
        st.markdown(f"**Address:** {', '.join(addr_parts) if addr_parts else '—'}")
        if h.get("notes"):
            st.caption(f"Notes: {h['notes']}")
    events = get_host_events(linked_id)
    if events:
        st.markdown("### Your Events")
        for ev in events:
            badge = {"Scheduled":"🔵","Completed":"🟢","Cancelled":"🔴"}.get(ev.get("status",""),"⚪")
            st.markdown(f"- {badge} **{ev['event_name']}** · {ev['event_date']} · {ev.get('city','')}")
    st.stop()

if _is_coord:
    tab_list, tab_add, tab_edit = st.tabs(["📋 All Hosts", "➕ Add Host", "✏️ Edit Host"])
else:
    st.info(f"👁️ You are viewing as **{_user_label}** — read-only access.")
    tab_list = st.tabs(["📋 All Hosts"])[0]
    tab_add = None
    tab_edit = None

with tab_list:
    hosts = get_all_hosts()
    search = st.text_input("🔍 Search hosts", placeholder="Name, venue, city...")
    status_f = st.selectbox("Filter by payment status", ["All","Pending","Approved","Paid"])

    filtered = hosts
    if search:
        s = search.lower()
        filtered = [h for h in filtered if s in (h.get("name","") + h.get("venue_name","") + h.get("city","")).lower()]
    if status_f != "All":
        filtered = [h for h in filtered if h.get("payment_status") == status_f]

    if not filtered:
        st.info("No hosts found.")
    else:
        badge_map = {"Pending":"🟡","Approved":"🔵","Paid":"🟢"}
        for h in filtered:
            badge = badge_map.get(h.get("payment_status",""), "⚪")
            with st.expander(f"{h['name']} — {h.get('venue_name','')} · {h.get('city','')}"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.markdown(f"**Contact:** {h.get('contact_person','—')}")
                    st.markdown(f"**Email:** {h.get('email','—')}")
                    st.markdown(f"**Phone:** {h.get('phone','—')}")
                with c2:
                    st.markdown(f"**Address:** {h.get('address','—')}, {h.get('city','')}, {h.get('state','NH')} {h.get('zip_code','')}")
                    st.markdown(f"**Check Payable To:** {h.get('check_payable_to','—')}")
                with c3:
                    st.markdown(f"**Payment:** {badge} {h.get('payment_status','—')} — **${h.get('payment_amount',0):.2f}**")
                    st.markdown(f"**Date Paid:** {h.get('payment_date','—') or '—'}")
                if h.get("notes"):
                    st.caption(f"Notes: {h['notes']}")
                if _is_coord:
                    if st.button("✏️ Edit This Host", key=f"edit_h_{h['host_id']}"):
                        st.session_state["edit_host_id"] = h["host_id"]
                        st.info("Switch to Edit Host tab.")

if tab_add:
  with tab_add:
    if st.session_state.get("host_just_added"):
        st.session_state.pop("host_just_added")
    st.markdown("### Add New Host")
    with st.form("add_host_form"):
        c1, c2 = st.columns(2)
        with c1:
            name    = st.text_input("Organization / Host Name *")
            venue   = st.text_input("Venue Name")
            address = st.text_input("Street Address")
            city    = st.text_input("City")
            state   = st.text_input("State", value="NH")
            zipcode = st.text_input("Zip Code")
        with c2:
            contact = st.text_input("Contact Person")
            email   = st.text_input("Email")
            phone   = st.text_input("Phone")
            payable = st.text_input("Check Payable To")
            amount  = st.number_input("Payment Amount ($)", min_value=0.0, step=50.0)
            pstatus = st.selectbox("Payment Status", ["Pending","Approved","Paid"])
        notes = st.text_area("Notes", height=80)
        if st.form_submit_button("💾 Save Host", use_container_width=True):
            if st.session_state.get("host_just_added"):
                pass
            elif not name:
                st.error("Host name is required.")
            else:
                existing = [h for h in get_all_hosts() if h["name"].lower()==name.lower()]
                if existing:
                    st.error(f"A host named '{name}' already exists. Use Edit Host to update it.")
                else:
                    st.session_state["host_just_added"] = True
                    add_host({"name":name,"venue_name":venue,"address":address,"city":city,
                               "state":state,"zip_code":zipcode,"contact_person":contact,
                               "email":email,"phone":phone,"check_payable_to":payable,
                               "payment_amount":amount,"payment_status":pstatus,"notes":notes})
                    log_activity("Host Added", f"{name} — {venue}, {city}")
                    add_notification(f"New host added: {name}", "all")
                    st.success(f"✅ Host '{name}' added!")

                    # Auto-generate login credentials
                    try:
                        init_users()
                        all_hosts = get_all_hosts()
                        new_host = next((h for h in all_hosts if h["name"].lower() == name.lower()), None)
                        if new_host:
                            # Generate username from venue name (slugified, max 20 chars)
                            venue_str = (venue or name).strip().lower().replace(" ", ".")
                            base_uname = venue_str[:20]
                            uname = base_uname
                            counter = 2
                            while username_exists(uname):
                                uname = f"{base_uname}{counter}"[:20]
                                counter += 1
                            chars = _string.ascii_letters + _string.digits + "!@#$%"
                            pwd = "".join(_secrets.choice(chars) for _ in range(16))
                            create_user(uname, pwd, "host", new_host["host_id"])
                            st.success("Login credentials created!")
                            st.warning(f"Share these credentials with {name} (shown once only):")
                            st.code(f"Username: {uname}\nPassword: {pwd}\nRole: Host")
                    except Exception as e:
                        st.warning(f"Host saved but credential generation failed: {e}")

                    st.rerun()

if tab_edit:
  with tab_edit:
    hosts2 = get_all_hosts()
    host_opts = {h["host_id"]: h["name"] for h in hosts2}
    default_id = st.session_state.get("edit_host_id", "")

    sel = st.selectbox("Select host to edit", options=[""] + list(host_opts.keys()),
                        format_func=lambda x: "— Select —" if x=="" else host_opts[x])
    if sel:
        h = get_host(sel)
        with st.form("edit_host_form"):
            c1, c2 = st.columns(2)
            with c1:
                name    = st.text_input("Organization / Host Name *", value=h.get("name",""))
                venue   = st.text_input("Venue Name", value=h.get("venue_name",""))
                address = st.text_input("Street Address", value=h.get("address",""))
                city    = st.text_input("City", value=h.get("city",""))
                state   = st.text_input("State", value=h.get("state","NH"))
                zipcode = st.text_input("Zip Code", value=h.get("zip_code",""))
            with c2:
                contact = st.text_input("Contact Person", value=h.get("contact_person",""))
                email   = st.text_input("Email", value=h.get("email",""))
                phone   = st.text_input("Phone", value=h.get("phone",""))
                payable = st.text_input("Check Payable To", value=h.get("check_payable_to",""))
                amount  = st.number_input("Payment Amount ($)", value=float(h.get("payment_amount",0)), min_value=0.0, step=50.0)
                pstatus = st.selectbox("Payment Status", ["Pending","Approved","Paid"],
                                       index=["Pending","Approved","Paid"].index(h.get("payment_status","Pending")))
            import datetime
            pdate_val = None
            if h.get("payment_date"):
                try: pdate_val = datetime.date.fromisoformat(h["payment_date"])
                except (ValueError, TypeError): pass
            pdate = st.date_input("Payment Date", value=pdate_val)
            notes = st.text_area("Notes", value=h.get("notes",""), height=80)

            col_s, col_d = st.columns([3,1])
            with col_s:
                save = st.form_submit_button("💾 Save Changes", use_container_width=True)
            with col_d:
                delb = st.form_submit_button("🗑️ Delete", use_container_width=True)

            if save:
                update_host(sel, {"name":name,"venue_name":venue,"address":address,"city":city,
                                   "state":state,"zip_code":zipcode,"contact_person":contact,
                                   "email":email,"phone":phone,"check_payable_to":payable,
                                   "payment_amount":amount,"payment_status":pstatus,
                                   "payment_date":str(pdate) if pdate else None,"notes":notes})
                log_activity("Host Updated", f"{name} — payment status: {pstatus}")
                st.session_state.pop("edit_host_id", None)
                st.success("Host updated!")
                st.rerun()
            if delb:
                st.session_state["_confirm_delete_host"] = sel

        if st.session_state.get("_confirm_delete_host") == sel:
            st.warning(f"Are you sure you want to delete this host? This cannot be undone.")
            c_yes, c_no = st.columns(2)
            with c_yes:
                if st.button("Yes, delete", key="confirm_del_host"):
                    delete_host(sel)
                    st.session_state.pop("_confirm_delete_host", None)
                    st.success("Host deleted.")
                    st.rerun()
            with c_no:
                if st.button("Cancel", key="cancel_del_host"):
                    st.session_state.pop("_confirm_delete_host", None)
                    st.rerun()

        # Host's events
        hevents = get_host_events(sel)
        if hevents:
            st.markdown(f"**Events for {h['name']}:**")
            for ev in hevents:
                badge = {"Scheduled":"🔵","Completed":"🟢","Cancelled":"🔴"}.get(ev.get("status",""),"⚪")
                st.markdown(f"- {badge} {ev['event_name']} · {ev['event_date']} · {ev.get('city','')}")
