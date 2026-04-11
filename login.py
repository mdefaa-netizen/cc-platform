"""
Login entry point for the CC Platform.

Run with:  streamlit run login.py
"""
import sys
import os
import time

import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))

from utils.auth import verify_password, get_user_by_email, ROLE_LABELS, ensure_bootstrap_coordinator
from utils.styles import inject_css

try:
    from utils.database import init_all
except ImportError:
    init_all = None
    from utils.database import init_db, init_users

_MAX_LOGIN_ATTEMPTS = 5
_LOCKOUT_SECONDS = 300

st.set_page_config(
    page_title="Sign In · Community Conversations",
    page_icon="🔒",
    layout="centered",
    initial_sidebar_state="collapsed",
)
inject_css()

# Initialise DB and seed the bootstrap coordinator if the users table is empty.
if init_all:
    init_all()
else:
    init_db()
    init_users()
ensure_bootstrap_coordinator()

# Already signed in → jump to the dashboard.
if st.session_state.get("authenticated"):
    st.switch_page("app.py")

if "_login_attempts" not in st.session_state:
    st.session_state._login_attempts = 0
    st.session_state._lockout_until = 0

st.markdown(
    """
    <div style='max-width:440px;margin:4rem auto 2rem;background:white;padding:2.5rem 2rem;
    border-radius:14px;box-shadow:0 8px 32px rgba(0,0,0,0.12);'>
    <div style='text-align:center;margin-bottom:1.5rem'>
        <div style='font-size:2.5rem'>🗺️</div>
        <h2 style='font-family:Playfair Display,serif;color:#1B2A4A;margin:0.5rem 0 0.2rem'>
            Community Conversations</h2>
        <p style='color:#7F8C8D;font-size:0.9rem;margin:0'>
            NH Humanities &amp; CDFA Coordinator Platform</p>
    </div>
    """,
    unsafe_allow_html=True,
)

locked_out = st.session_state.get("_lockout_until", 0) > time.time()
if locked_out:
    remaining = int(st.session_state._lockout_until - time.time())
    st.error(f"Too many failed attempts. Try again in {remaining} seconds.")

with st.form("login_form", clear_on_submit=False):
    email = st.text_input("Email", placeholder="you@example.org", autocomplete="email")
    pwd = st.text_input("Password", type="password", placeholder="Enter your password", autocomplete="current-password")
    submitted = st.form_submit_button("Sign In", use_container_width=True, disabled=locked_out)

if submitted and not locked_out:
    if not email or not pwd:
        st.error("Please enter both email and password.")
    else:
        user = get_user_by_email(email)
        if user and user.get("is_active") and verify_password(pwd, user["password_hash"]):
            st.session_state.authenticated = True
            st.session_state.user_id = user.get("id") or user.get("user_id")
            st.session_state.user_email = user["email"]
            st.session_state.user_role = user["role"]
            st.session_state.user_label = ROLE_LABELS.get(user["role"], user["role"].title())
            st.session_state.user_full_name = user.get("full_name") or user["email"]
            st.session_state._login_at = time.time()
            st.session_state._login_attempts = 0
            st.switch_page("app.py")
        else:
            st.session_state._login_attempts = st.session_state.get("_login_attempts", 0) + 1
            if st.session_state._login_attempts >= _MAX_LOGIN_ATTEMPTS:
                st.session_state._lockout_until = time.time() + _LOCKOUT_SECONDS
                st.error(f"Too many failed attempts. Locked out for {_LOCKOUT_SECONDS // 60} minutes.")
            elif user and not user.get("is_active"):
                st.error("This account is deactivated. Contact a Coordinator.")
            else:
                remaining = _MAX_LOGIN_ATTEMPTS - st.session_state._login_attempts
                st.error(f"Invalid email or password. {remaining} attempt(s) remaining.")

st.markdown(
    """
    <div style='margin-top:1.5rem;padding-top:1rem;border-top:1px solid #eee;font-size:0.8rem;color:#aaa;text-align:center'>
        Coordinator · NH Humanities Staff · CDFA Staff · Facilitator · Host
    </div></div>
    """,
    unsafe_allow_html=True,
)
