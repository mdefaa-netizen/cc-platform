"""
Authentication and RBAC for CC Platform.

Centralises everything auth-related:
- bcrypt password hashing / verification
- user CRUD (dispatches to SQLite or Postgres backend)
- require_auth() guard for every page
- render_sidebar_user() for the shared sidebar block

Roles: coordinator, facilitator, host, cdfa_staff, nhh_staff
"""
from __future__ import annotations

import os
import time
import secrets
import string
import logging
from html import escape as _esc

import bcrypt
import streamlit as st

ROLE_LABELS = {
    "coordinator": "Coordinator",
    "facilitator": "Facilitator",
    "host":        "Host",
    "cdfa_staff":  "CDFA Staff",
    "nhh_staff":   "NH Humanities Staff",
}

VALID_ROLES = tuple(ROLE_LABELS.keys())

SESSION_TIMEOUT_SECONDS = 3600
_log = logging.getLogger(__name__)


# ── Backend dispatch ─────────────────────────────────────────────────────────

def _backend():
    """Return the active DB module: supabase_db if DATABASE_URL set, else database."""
    try:
        if st.secrets.get("DATABASE_URL"):
            from utils import supabase_db as _b
            return _b
    except Exception:
        pass
    if os.environ.get("DATABASE_URL"):
        from utils import supabase_db as _b
        return _b
    from utils import database as _b
    return _b


# ── Password hashing ─────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    except Exception:
        return False


def generate_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


# ── User CRUD (dispatched) ────────────────────────────────────────────────────

def get_user_by_email(email: str):
    return _backend().get_user_by_email(email.strip().lower())


def create_user(email: str, password: str, role: str, full_name: str = "",
                must_change_password: bool = False):
    """Hash the cleartext via bcrypt and dispatch to the active backend.

    must_change_password=False is the default so the bootstrap path
    (ensure_bootstrap_coordinator) and any other legacy caller keep their
    pre-feature behaviour. The Admin Users create form (pages/15_Admin_Users.py)
    passes True so the new staff member is forced to set their own password
    on first sign-in via the require_auth intercept."""
    if role not in VALID_ROLES:
        raise ValueError(f"Invalid role: {role}")
    return _backend().create_user(
        email=email.strip().lower(),
        password_hash=hash_password(password),
        role=role,
        full_name=full_name,
        must_change_password=1 if must_change_password else 0,
    )


def update_staff_password_and_clear_flag(user_id, new_password: str):
    """Set a new bcrypt hash on a staff user row and clear
    must_change_password in one UPDATE. Reuses hash_password (bcrypt) — do
    NOT call the PBKDF2 portal_access helper. Called from the require_auth
    set-password intercept."""
    return _backend().update_staff_password_and_clear_flag(
        user_id, hash_password(new_password)
    )


def list_users():
    return _backend().list_users()


def update_user_role(user_id, role: str):
    if role not in VALID_ROLES:
        raise ValueError(f"Invalid role: {role}")
    return _backend().update_user_role(user_id, role)


def set_user_active(user_id, is_active: bool):
    return _backend().set_user_active(user_id, bool(is_active))


def reset_user_password(email: str, new_password: str):
    return _backend().reset_user_password(email.strip().lower(), hash_password(new_password))


# ── Session guard ─────────────────────────────────────────────────────────────

def require_auth(allowed_roles=None):
    """Call at the top of every page. Redirects to pages/0_Login.py if not
    authenticated, or if the user's role is not in allowed_roles.

    Portal-user exception: a host/facilitator who signed in via the portal
    (pages/0_Portal.py → check_portal_login) has st.session_state['portal_user']
    set but NOT st.session_state['authenticated'] (that flag is reserved for
    the staff users-table login). Without the branch below, clicking any
    staff page bounces them onto the staff Login screen — looks like a
    sign-out even though the session is intact. Send them back to their
    portal instead. Session is preserved (no clear), so they land where
    they started with no re-auth required.
    """
    if not st.session_state.get("authenticated"):
        if st.session_state.get("portal_user"):
            try:
                st.switch_page("pages/0_Portal.py")
            except Exception:
                st.warning("This page is for staff. Returning you to your portal.")
                st.stop()
            return None
        try:
            st.switch_page("pages/0_Login.py")
        except Exception:
            st.warning("Please sign in.")
            st.stop()

    # Session timeout
    login_at = st.session_state.get("_login_at")
    if login_at and (time.time() - login_at > SESSION_TIMEOUT_SECONDS):
        st.session_state.clear()
        try:
            st.switch_page("pages/0_Login.py")
        except Exception:
            st.warning("Session expired. Please sign in again.")
            st.stop()

    role = st.session_state.get("user_role")
    if allowed_roles and role not in allowed_roles:
        st.error(f"Access denied. Your role ({ROLE_LABELS.get(role, role)}) cannot view this page.")
        st.stop()

    # First-login intercept (staff). Mirror of the portal's set-password
    # form at pages/0_Portal.py:120-159, but here it lives inside the auth
    # guard so it fires on EVERY staff page — a user can't bypass by
    # navigating to another sidebar entry. The flag is loaded into session
    # by pages/0_Login.py on successful credential check, and the flag-clear
    # below updates BOTH the DB (via update_staff_password_and_clear_flag)
    # and the in-session mirror so the rerun falls through without another
    # round-trip. Portal users never reach this point (the portal_user
    # redirect branch earlier in this function returns first), so the staff
    # and portal intercepts stay strictly separated.
    if st.session_state.get("user_must_change_password"):
        _render_staff_set_password()
        st.stop()

    return role


def _render_staff_set_password():
    """Inline 'Set Your Password' card for staff users whose
    must_change_password flag is set. Form-side validation matches the
    portal form: both non-empty, must match, min 8 chars."""
    st.markdown(
        """
        <div style='max-width:480px;margin:3rem auto 1rem;background:white;
        padding:2rem 2rem;border-radius:14px;box-shadow:0 8px 32px rgba(0,0,0,0.1)'>
        <div style='text-align:center;margin-bottom:1.2rem'>
            <div style='font-size:2.2rem'>🔑</div>
            <h3 style='font-family:Playfair Display,serif;color:#1B2A4A;margin:0.4rem 0 0.2rem'>
                Set Your Password</h3>
            <p style='color:#7F8C8D;font-size:0.88rem;margin:0'>
                Choose a personal password before continuing.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.form("staff_set_password_form"):
        new_pw = st.text_input("New password", type="password",
                                placeholder="At least 8 characters")
        confirm_pw = st.text_input("Confirm new password", type="password",
                                    placeholder="Type it again")
        if st.form_submit_button("Save password", use_container_width=True):
            uid = st.session_state.get("user_id")
            if not uid:
                st.error("Session expired. Please sign in again.")
            elif not new_pw or not confirm_pw:
                st.error("Both fields are required.")
            elif new_pw != confirm_pw:
                st.error("The two passwords don't match.")
            elif len(new_pw) < 8:
                st.error("Password must be at least 8 characters.")
            else:
                update_staff_password_and_clear_flag(uid, new_pw)
                st.session_state["user_must_change_password"] = 0
                st.success("✅ Password set. Continuing…")
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def render_sidebar_user():
    """Render the Signed-in-as block and sign-out button in the sidebar.
    Safe to call on every page.
    """
    full_name = st.session_state.get("user_full_name") or st.session_state.get("user_email", "")
    role = st.session_state.get("user_role", "")
    label = ROLE_LABELS.get(role, role.title() if role else "")

    with st.sidebar:
        st.markdown(
            f"""
            <div style='text-align:center;padding:0.6rem 0 0.3rem'>
                <div style='font-family:Playfair Display,serif;font-size:0.95rem;font-weight:700;
                color:white;line-height:1.2'>{_esc(full_name)}</div>
                <div style='margin-top:0.3rem;background:#ffffff22;border-radius:6px;
                padding:3px 8px;font-size:0.72rem;color:#7dd'>
                    {_esc(label)}
                </div>
            </div>
            <hr style='border-color:#ffffff22;margin:0.5rem 0'>
            """,
            unsafe_allow_html=True,
        )
        if st.button("🔒 Sign Out", use_container_width=True, key=f"_signout_{st.session_state.get('_sidebar_nonce', 0)}"):
            st.session_state.clear()
            try:
                st.switch_page("pages/0_Login.py")
            except Exception:
                st.rerun()


# ── Bootstrap coordinator ─────────────────────────────────────────────────────

BOOTSTRAP_EMAIL = "mdefaa@gmail.com"


def ensure_bootstrap_coordinator():
    """Create the initial Coordinator if no users exist.
    Password is read from st.secrets['BOOTSTRAP_PASSWORD'] or generated and
    printed once to stdout.
    """
    b = _backend()
    try:
        users = b.list_users()
    except Exception as e:
        _log.warning("list_users failed during bootstrap: %s", e)
        return
    if users:
        return

    try:
        pwd = st.secrets.get("BOOTSTRAP_PASSWORD")
    except Exception:
        pwd = None
    if not pwd:
        pwd = generate_password(16)
        print("=" * 60)
        print("BOOTSTRAP COORDINATOR CREATED")
        print(f"  Email:    {BOOTSTRAP_EMAIL}")
        print(f"  Password: {pwd}")
        print("  Change this password immediately after first login.")
        print("=" * 60)

    b.create_user(
        email=BOOTSTRAP_EMAIL,
        password_hash=hash_password(pwd),
        role="coordinator",
        full_name="Bootstrap Coordinator",
    )
