import streamlit as st
import sys, os, secrets, string
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.database import (
    get_all_hosts, get_all_facilitators,
    get_all_portal_access, add_portal_access, update_portal_access,
    delete_portal_access, init_db, log_activity, add_notification,
    init_portal_access
)
from utils.styles import inject_css, page_header

st.set_page_config(page_title="Portal Access · CC Platform", page_icon="🔑", layout="wide")
inject_css()
try:
    from utils.database import init_all
    init_all()
except ImportError:
    init_db()
    init_portal_access()

if not st.session_state.get("authenticated"):
    st.warning("Please log in.")
    st.stop()
role = st.session_state.get("user_role", None)

if role != "coordinator":
    st.error("This page is only accessible to the Coordinator.")
    st.stop()

page_header("🔑 Portal Access Management",
            "Grant and manage login access for hosts and facilitators")

st.markdown("""
<div class="section-box" style='margin-bottom:1.5rem'>
    <strong>How Portal Access Works:</strong><br>
    Once you confirm a host or facilitator's participation, you can grant them a portal login.
    They will be able to view their event calendar, send messages to the coordinator,
    record attendance, submit feedback, and report issues — but they cannot see
    financials, other contacts, or coordinator-only data.
</div>
""", unsafe_allow_html=True)

hosts = get_all_hosts()
facs  = get_all_facilitators()
access_list = get_all_portal_access()

tab_manage, tab_grant = st.tabs(["👥 Manage Access", "➕ Grant New Access"])

with tab_manage:
    if not access_list:
        st.info("No portal access granted yet. Use 'Grant New Access' to add users.")
    else:
        st.markdown(f"**{len(access_list)} portal user(s) configured**")
        for a in access_list:
            status_icon = "🟢 Active" if a.get("is_active") else "🔴 Pending"
            ptype_icon  = "👥" if a.get("person_type") == "host" else "🎤"

            # Get person name
            if a.get("person_type") == "host":
                person = next((h for h in hosts if h["host_id"]==a.get("person_id")), {})
            else:
                person = next((f for f in facs if f["facilitator_id"]==a.get("person_id")), {})

            with st.expander(f"{ptype_icon} {person.get('name','Unknown')} — @{a.get('username','')} — {status_icon}"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.markdown(f"**Type:** {a.get('person_type','').title()}")
                    st.markdown(f"**Username:** `{a.get('username','')}`")
                with c2:
                    st.markdown(f"**Status:** {status_icon}")
                    st.markdown(f"**Granted:** {a.get('granted_at','Not yet') or 'Not yet'}")
                with c3:
                    if a.get("notes"):
                        st.caption(f"Notes: {a['notes']}")

                col_a, col_r, col_d = st.columns(3)
                with col_a:
                    if not a.get("is_active"):
                        if st.button("✅ Approve Access", key=f"approve_{a['access_id']}",
                                     use_container_width=True):
                            update_portal_access(a["access_id"], True)
                            log_activity("Portal Access Approved",
                                         f"{person.get('name','')} (@{a.get('username','')})")
                            add_notification(
                                f"Portal access approved for {person.get('name','')}",
                                "all"
                            )
                            st.success(f"✅ Access approved for {person.get('name','')}!")
                            st.rerun()
                with col_r:
                    if a.get("is_active"):
                        if st.button("🚫 Revoke Access", key=f"revoke_{a['access_id']}",
                                     use_container_width=True):
                            update_portal_access(a["access_id"], False)
                            log_activity("Portal Access Revoked",
                                         f"{person.get('name','')} (@{a.get('username','')})")
                            st.warning(f"Access revoked for {person.get('name','')}.")
                            st.rerun()
                with col_d:
                    if st.button("🗑️ Delete", key=f"del_access_{a['access_id']}",
                                 use_container_width=True):
                        delete_portal_access(a["access_id"])
                        st.success("Deleted.")
                        st.rerun()

with tab_grant:
    st.markdown("### Grant Portal Access")

    def gen_password(length=16):
        chars = string.ascii_letters + string.digits + "!@#$%"
        return ''.join(secrets.choice(chars) for _ in range(length))

    with st.form("grant_access_form"):
        c1, c2 = st.columns(2)
        with c1:
            person_type = st.selectbox("Person Type", ["host", "facilitator"])
            if person_type == "host":
                opts = {h["host_id"]: h["name"] for h in hosts}
            else:
                opts = {f["facilitator_id"]: f["name"] for f in facs}
            person_sel = st.selectbox("Select Person *",
                                       options=[""] + list(opts.keys()),
                                       format_func=lambda x: "— Select —" if x=="" else opts[x])
        with c2:
            username   = st.text_input("Username *",
                                        placeholder="e.g., jsmith_host",
                                        help="They will use this to sign in")
            auto_pw    = gen_password()
            password   = st.text_input("Password *", value=auto_pw,
                                        help="Auto-generated — you can change it")
            activate   = st.checkbox("Approve immediately", value=False,
                                      help="Check to grant access right away, or leave unchecked to approve later")
        notes = st.text_input("Notes", placeholder="e.g., Concord event confirmed")

        if st.form_submit_button("🔑 Create Portal Access", use_container_width=True):
            if not person_sel or not username or not password:
                st.error("Person, username, and password are required.")
            else:
                # Check username not already taken
                existing = [a for a in get_all_portal_access() if a.get("username")==username]
                if existing:
                    st.error(f"Username '{username}' is already taken.")
                else:
                    add_portal_access({
                        "person_type": person_type,
                        "person_id":   person_sel,
                        "username":    username,
                        "password":    password,
                        "is_active":   1 if activate else 0,
                        "notes":       notes,
                    })
                    pname = opts.get(person_sel, "")
                    log_activity("Portal Access Created",
                                 f"{pname} (@{username}) — {'Active' if activate else 'Pending'}")
                    st.success(f"Portal access created for **{pname}**!")
                    st.warning(f"Share these credentials with {pname} (shown once only):")
                    st.code(f"Username: {username}\nPassword: {password}")
