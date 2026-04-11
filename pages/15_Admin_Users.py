"""
Admin user management page. Coordinators only.

Create new users, deactivate existing ones, and change roles.
"""
import sys
import os

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.auth import (
    require_auth, render_sidebar_user,
    list_users, create_user, update_user_role, set_user_active,
    generate_password, ROLE_LABELS, VALID_ROLES,
)
from utils.styles import inject_css, page_header
from utils.database import log_activity

st.set_page_config(page_title="Admin · Users · CC Platform", page_icon="👥", layout="wide")
inject_css()

require_auth(allowed_roles=["coordinator"])
render_sidebar_user()

page_header("👥 User Administration", "Create, deactivate, and manage platform users")

tabs = st.tabs(["📋 All Users", "➕ Create User"])

# ── All Users ─────────────────────────────────────────────────────────────────
with tabs[0]:
    users = list_users()
    if not users:
        st.info("No users yet.")
    else:
        header = "| Email | Full Name | Role | Status | Created |"
        divider = "|---|---|---|---|---|"
        rows = [header, divider]
        for u in users:
            status = "🟢 Active" if u.get("is_active") else "🔴 Inactive"
            created = str(u.get("created_at", ""))[:10]
            rows.append(
                f"| {u['email']} | {u.get('full_name') or '—'} | "
                f"{ROLE_LABELS.get(u['role'], u['role'])} | {status} | {created} |"
            )
        st.markdown("\n".join(rows))
        st.caption(f"{len(users)} user(s)")

        st.markdown("---")
        st.markdown("### Manage User")

        user_options = {
            (u.get("id") or u.get("user_id")): f"{u['email']} ({ROLE_LABELS.get(u['role'], u['role'])})"
            for u in users
        }
        sel_id = st.selectbox(
            "Select user",
            options=[None] + list(user_options.keys()),
            format_func=lambda x: "— Select —" if x is None else user_options[x],
        )

        if sel_id is not None:
            sel_user = next(
                u for u in users if (u.get("id") or u.get("user_id")) == sel_id
            )
            current_email = sel_user["email"]
            current_active = bool(sel_user.get("is_active"))

            c1, c2 = st.columns(2)
            with c1:
                new_role = st.selectbox(
                    "Role",
                    options=list(VALID_ROLES),
                    index=list(VALID_ROLES).index(sel_user["role"])
                        if sel_user["role"] in VALID_ROLES else 0,
                    format_func=lambda r: ROLE_LABELS[r],
                    key=f"role_{sel_id}",
                )
                if st.button("💾 Update Role", use_container_width=True, key=f"update_role_{sel_id}"):
                    if new_role != sel_user["role"]:
                        update_user_role(sel_id, new_role)
                        log_activity(
                            "User Role Changed",
                            f"{current_email}: {sel_user['role']} → {new_role}",
                        )
                        st.success(f"Role updated to {ROLE_LABELS[new_role]}.")
                        st.rerun()
                    else:
                        st.info("No change.")
            with c2:
                if current_active:
                    if st.button(
                        "🚫 Deactivate User",
                        use_container_width=True,
                        key=f"deact_{sel_id}",
                        type="secondary",
                    ):
                        # Never deactivate yourself.
                        if sel_id == st.session_state.get("user_id"):
                            st.error("You cannot deactivate your own account.")
                        else:
                            set_user_active(sel_id, False)
                            log_activity("User Deactivated", current_email)
                            st.success(f"{current_email} deactivated.")
                            st.rerun()
                else:
                    if st.button(
                        "✅ Reactivate User",
                        use_container_width=True,
                        key=f"react_{sel_id}",
                    ):
                        set_user_active(sel_id, True)
                        log_activity("User Reactivated", current_email)
                        st.success(f"{current_email} reactivated.")
                        st.rerun()

# ── Create User ───────────────────────────────────────────────────────────────
with tabs[1]:
    st.markdown("### Create New User")
    with st.form("create_user_form", clear_on_submit=True):
        new_email = st.text_input("Email *", placeholder="user@example.org")
        new_full_name = st.text_input("Full Name *", placeholder="Jane Doe")
        new_role = st.selectbox(
            "Role *",
            options=list(VALID_ROLES),
            format_func=lambda r: ROLE_LABELS[r],
        )
        use_generated = st.checkbox("Generate a random temporary password", value=True)
        temp_password = st.text_input(
            "Temporary Password",
            type="password",
            disabled=use_generated,
            help="Ignored if 'Generate' is checked.",
        )

        if st.form_submit_button("➕ Create User", use_container_width=True):
            if not new_email or not new_full_name:
                st.error("Email and full name are required.")
            elif "@" not in new_email:
                st.error("Invalid email address.")
            else:
                pwd = generate_password(16) if use_generated else temp_password
                if not pwd or len(pwd) < 8:
                    st.error("Password must be at least 8 characters.")
                else:
                    try:
                        create_user(
                            email=new_email,
                            password=pwd,
                            role=new_role,
                            full_name=new_full_name,
                        )
                        log_activity(
                            "User Created",
                            f"{new_email} ({ROLE_LABELS[new_role]})",
                        )
                        st.success(f"✅ User {new_email} created.")
                        st.info(
                            f"**Temporary password:** `{pwd}`\n\n"
                            f"Share this with the user securely. They should change it on first login."
                        )
                    except Exception as e:
                        st.error(f"Failed to create user: {e}")
