import streamlit as st
import time
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.database import log_activity, add_notification, get_all_cdfa, get_cdfa, add_cdfa, update_cdfa, delete_cdfa, init_db
from utils.styles import inject_css, page_header

st.set_page_config(page_title="CDFA Colleagues · CC Platform", page_icon="🌾", layout="wide")
inject_css()
try:
    from utils.database import init_all
    init_all()
except ImportError:
    init_db()

role = st.session_state.get("user_role", None)

if role is None:
    st.warning("Please log in.")
    st.stop()

if role != "coordinator":
    st.error("This page is only accessible to the Coordinator.")
    st.stop()

_role = role
_is_coord = True
_user_label = st.session_state.get("user_label", "Coordinator")

page_header("🌾 CDFA Colleagues", "Contacts at the Community Development Finance Authority (CDFA)")

tab_list, tab_add, tab_edit = st.tabs(["📋 All CDFA Colleagues", "➕ Add Colleague", "✏️ Edit Colleague"])

with tab_list:
    colleagues = get_all_cdfa()
    search = st.text_input("🔍 Search", placeholder="Name, title, role...")
    if search:
        s = search.lower()
        colleagues = [c for c in colleagues if s in (c.get("name","") + c.get("title","") + (c.get("role") or "")).lower()]

    if not colleagues:
        st.info("No CDFA colleagues added yet.")
    else:
        for c in colleagues:
            with st.expander(f"🌾 {c['name']} — {c.get('title','') or 'CDFA'}"):
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Title:** {c.get('title','—') or '—'}")
                    st.markdown(f"**Role:** {c.get('role','—') or '—'}")
                with col2:
                    st.markdown(f"**Email:** {c.get('email','—') or '—'}")
                    st.markdown(f"**Phone:** {c.get('phone','—') or '—'}")
                if c.get("notes"):
                    st.caption(f"Notes: {c['notes']}")
                if st.button("✏️ Edit", key=f"edit_cdfa_{c['cdfa_id']}"):
                    st.session_state["edit_cdfa_id"] = c["cdfa_id"]
                    st.info("Switch to Edit Colleague tab.")

with tab_add:
    if st.session_state.get("cdfa_just_added"):
        st.session_state.pop("cdfa_just_added")
    st.markdown("### Add CDFA Colleague")
    with st.form("add_cdfa_form"):
        c1, c2 = st.columns(2)
        with c1:
            name  = st.text_input("Full Name *")
            title = st.text_input("Title", placeholder="e.g., Program Officer")
            role  = st.text_input("Role", placeholder="e.g., Grants Manager")
        with c2:
            email = st.text_input("Email")
            phone = st.text_input("Phone")
        notes = st.text_area("Notes", height=80)
        if st.form_submit_button("💾 Save Colleague", use_container_width=True):
            if st.session_state.get("cdfa_just_added"):
                pass
            elif not name:
                st.error("Name is required.")
            else:
                st.session_state["cdfa_just_added"] = True
                add_cdfa({"name": name, "title": title, "email": email,
                           "phone": phone, "role": role, "notes": notes})
                st.success(f"✅ '{name}' added to CDFA Colleagues!")
                time.sleep(3)
                st.rerun()

with tab_edit:
    colleagues2 = get_all_cdfa()
    opts = {c["cdfa_id"]: c["name"] for c in colleagues2}
    sel = st.selectbox("Select colleague to edit", options=[""] + list(opts.keys()),
                        format_func=lambda x: "— Select —" if x == "" else opts[x])
    if sel:
        c = get_cdfa(sel)
        with st.form("edit_cdfa_form"):
            col1, col2 = st.columns(2)
            with col1:
                name  = st.text_input("Full Name *", value=c.get("name",""))
                title = st.text_input("Title", value=c.get("title","") or "")
                role  = st.text_input("Role", value=c.get("role","") or "")
            with col2:
                email = st.text_input("Email", value=c.get("email","") or "")
                phone = st.text_input("Phone", value=c.get("phone","") or "")
            notes = st.text_area("Notes", value=c.get("notes","") or "", height=80)

            cs, cd = st.columns([3, 1])
            with cs:
                save = st.form_submit_button("💾 Save Changes", use_container_width=True)
            with cd:
                delb = st.form_submit_button("🗑️ Delete", use_container_width=True)

            if save:
                update_cdfa(sel, {"name": name, "title": title, "email": email,
                                   "phone": phone, "role": role, "notes": notes})
                st.success("✅ Colleague updated!")
                time.sleep(3)
                st.rerun()
            if delb:
                delete_cdfa(sel)
                st.success("🗑️ Deleted.")
                time.sleep(3)
                st.rerun()
