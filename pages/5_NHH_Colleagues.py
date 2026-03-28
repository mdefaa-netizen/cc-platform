import streamlit as st
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.database import log_activity, add_notification, get_all_nhh, get_nhh, add_nhh, update_nhh, delete_nhh, init_db
from utils.styles import inject_css, page_header

st.set_page_config(page_title="NHH Colleagues · CC Platform", page_icon="🏛️", layout="wide")
inject_css()
init_db()

if not st.session_state.get("authenticated"):
    st.warning("Please sign in from the main page.")
    st.stop()

# Role awareness
_role = st.session_state.get("user_role", "coordinator")
_is_coord = (_role == "coordinator")
_user_label = st.session_state.get("user_label", "Coordinator")

page_header("🏛️ NH Humanities Colleagues", "Contacts at NH Humanities (NHH)")

tab_list, tab_add, tab_edit = st.tabs(["📋 All NHH Colleagues", "➕ Add Colleague", "✏️ Edit Colleague"])

with tab_list:
    colleagues = get_all_nhh()
    search = st.text_input("🔍 Search", placeholder="Name, title, role...")
    if search:
        s = search.lower()
        colleagues = [c for c in colleagues if s in (c.get("name","") + c.get("title","") + (c.get("role") or "")).lower()]

    if not colleagues:
        st.info("No NHH colleagues added yet.")
    else:
        for c in colleagues:
            with st.expander(f"🏛️ {c['name']} — {c.get('title','') or 'NHH'}"):
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Title:** {c.get('title','—') or '—'}")
                    st.markdown(f"**Role:** {c.get('role','—') or '—'}")
                with col2:
                    st.markdown(f"**Email:** {c.get('email','—') or '—'}")
                    st.markdown(f"**Phone:** {c.get('phone','—') or '—'}")
                if c.get("notes"):
                    st.caption(f"Notes: {c['notes']}")
                if st.button("✏️ Edit", key=f"edit_nhh_{c['nhh_id']}"):
                    st.session_state["edit_nhh_id"] = c["nhh_id"]
                    st.info("Switch to Edit Colleague tab.")

with tab_add:
    st.markdown("### Add NHH Colleague")
    with st.form("add_nhh_form"):
        c1, c2 = st.columns(2)
        with c1:
            name  = st.text_input("Full Name *")
            title = st.text_input("Title", placeholder="e.g., Program Director")
            role  = st.text_input("Role", placeholder="e.g., Project Manager")
        with c2:
            email = st.text_input("Email")
            phone = st.text_input("Phone")
        notes = st.text_area("Notes", height=80)
        if st.form_submit_button("💾 Save Colleague", use_container_width=True):
            if not name:
                st.error("Name is required.")
            else:
                add_nhh({"name": name, "title": title, "email": email,
                          "phone": phone, "role": role, "notes": notes})
                st.success(f"✅ '{name}' added to NHH Colleagues!")

with tab_edit:
    colleagues2 = get_all_nhh()
    opts = {c["nhh_id"]: c["name"] for c in colleagues2}
    sel = st.selectbox("Select colleague to edit", options=[""] + list(opts.keys()),
                        format_func=lambda x: "— Select —" if x == "" else opts[x])
    if sel:
        c = get_nhh(sel)
        with st.form("edit_nhh_form"):
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
                update_nhh(sel, {"name": name, "title": title, "email": email,
                                   "phone": phone, "role": role, "notes": notes})
                st.success("✅ Colleague updated!")
            if delb:
                delete_nhh(sel)
                st.success("🗑️ Deleted.")
                st.rerun()
