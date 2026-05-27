import streamlit as st
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.database import (
    get_all_hosts, get_all_facilitators,
    get_all_portal_access, add_portal_access, update_portal_access,
    delete_portal_access, init_db, log_activity, add_notification,
    init_portal_access
)
from utils.auth import require_auth, render_sidebar_user
from utils.styles import inject_css, page_header

# Shared initial password (the "access code") — same for every newly created
# portal account. Pulled from st.secrets if configured; otherwise falls back
# to a documented default and surfaces a caption telling the coordinator to
# set the secret. New accounts are forced to change this on first sign-in
# (see pages/0_Portal.py — must_change_password gate).
DEFAULT_PORTAL_INITIAL_PASSWORD = "ChangeMe2026!"


def _shared_initial_password():
    try:
        val = st.secrets.get("PORTAL_INITIAL_PASSWORD", "")
    except Exception:
        val = ""
    return val or DEFAULT_PORTAL_INITIAL_PASSWORD


def _initial_password_is_default() -> bool:
    return _shared_initial_password() == DEFAULT_PORTAL_INITIAL_PASSWORD

st.set_page_config(page_title="Portal Access · CC Platform", page_icon="🔑", layout="wide")
inject_css()
try:
    from utils.database import init_all
    init_all()
except ImportError:
    init_db()
    init_portal_access()

role = require_auth(allowed_roles=["coordinator"])
render_sidebar_user()

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
            # 🔓 badge: account still holds the shared initial password — the
            # user has not yet signed in and chosen their own. Lets the
            # coordinator see at a glance who's claimed their account.
            claim_icon = " 🔓 not yet claimed" if a.get("must_change_password") else ""

            # Get person name
            if a.get("person_type") == "host":
                person = next((h for h in hosts if h["host_id"]==a.get("person_id")), {})
            else:
                person = next((f for f in facs if f["facilitator_id"]==a.get("person_id")), {})

            with st.expander(f"{ptype_icon} {person.get('name','Unknown')} — @{a.get('username','')} — {status_icon}{claim_icon}"):
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

    _shared_pw = _shared_initial_password()
    st.caption(
        "Every new portal account is created with the same **shared access "
        "code** below. The user will be required to set their own password "
        "the first time they sign in."
    )
    if _initial_password_is_default():
        st.warning(
            "Using the default fallback access code "
            "(`PORTAL_INITIAL_PASSWORD` is not set in Streamlit secrets). "
            "Set it in **Settings → Secrets** on Streamlit Cloud to rotate "
            "the shared code. Rotating affects only NEW accounts; accounts "
            "already issued keep their seeded code."
        )

    st.code(f"Shared access code: {_shared_pw}")

    # Person Type and Select Person live OUTSIDE the form so that changing
    # Person Type immediately re-runs the page and refreshes the dependent
    # dropdown. If these widgets were inside the st.form() below, Streamlit
    # would defer all widget updates until form submission, leaving the
    # Select Person list stuck on whatever person_type was at first render
    # (causing the "facilitator dropdown still shows hosts" bug).
    c1_out, c2_out = st.columns(2)
    with c1_out:
        person_type = st.selectbox("Person Type", ["host", "facilitator"],
                                    key="grant_person_type")
        if person_type == "host":
            # Host rows store the organization/venue in `name` and the
            # human contact in `contact_person`. Show both so the
            # coordinator can pick the right venue when assigning a
            # username to a contact person.
            def _host_label(h):
                cp = (h.get("contact_person") or "").strip()
                org = h.get("name") or ""
                return f"{org} — {cp}" if cp else org
            opts = {h["host_id"]: _host_label(h) for h in hosts}
        else:
            opts = {f["facilitator_id"]: f["name"] for f in facs}
        person_sel = st.selectbox(
            "Select Person *",
            options=[""] + list(opts.keys()),
            format_func=lambda x: "— Select —" if x == "" else opts[x],
            key="grant_person_sel",
        )

    with st.form("grant_access_form"):
        c1, c2 = st.columns(2)
        with c1:
            # Echo the currently selected person inside the form so the
            # coordinator can see what will be submitted alongside the
            # username field. Read-only display; the actual selection
            # state lives in the widgets above.
            if person_sel:
                st.caption(f"Granting access to: **{opts.get(person_sel, '')}** "
                           f"({person_type})")
            else:
                st.caption("— Select a person above before submitting —")
        with c2:
            username   = st.text_input("Username *",
                                        placeholder="e.g., tsmith",
                                        help="They will use this to sign in")
            activate   = st.checkbox("Approve immediately", value=True,
                                      help="Check to grant access right away (default), or uncheck to create a pending account you'll approve later under 'Manage Access'")
        notes = st.text_input("Notes", placeholder="e.g., Concord event confirmed")

        if st.form_submit_button("🔑 Create Portal Access", use_container_width=True):
            if not person_sel or not username:
                st.error("Person and username are required.")
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
                        # Seed with the shared access code; the user is forced
                        # to change it on first sign-in (must_change_password=1
                        # below, intercept in pages/0_Portal.py).
                        "password":    _shared_pw,
                        "is_active":   1 if activate else 0,
                        "notes":       notes,
                        "must_change_password": 1,
                    })
                    pname = opts.get(person_sel, "")
                    log_activity("Portal Access Created",
                                 f"{pname} (@{username}) — {'Active' if activate else 'Pending'}")
                    if activate:
                        st.success(f"Portal access created and approved for **{pname}**!")
                        st.warning(f"Share these credentials with {pname}:")
                        st.code(
                            f"Username: {username}\n"
                            f"Access code (one-time): {_shared_pw}"
                        )
                        st.info(
                            f"Tell {pname} to sign in on the **My Portal** page with their "
                            f"**Username**. They'll be asked to set their own password the "
                            f"first time they sign in."
                        )
                    else:
                        st.success(f"Portal access created for **{pname}** (pending approval).")
                        st.error(
                            f"⚠️ **DO NOT SHARE YET** — these credentials will NOT work until you "
                            f"approve {pname} under the **Manage Access** tab. "
                            f"Share them only after approval."
                        )
                        st.code(
                            f"Username: {username}\n"
                            f"Access code (one-time): {_shared_pw}\n"
                            f"# Status: PENDING APPROVAL — login will fail until approved"
                        )

    # ── Bulk Grant ────────────────────────────────────────────────────────────
    # Onboard a whole cohort in one click. Each line of the textarea is parsed
    # as `type,full_name,username`. Matching is case- and whitespace-tolerant.
    # For hosts, the full_name field is checked against BOTH the venue name
    # (`hosts.name`) AND the contact person (`hosts.contact_person`), so the
    # coordinator can paste either form. Each row is created with the shared
    # access code and must_change_password=1 — identical to the manual flow.
    # Duplicate usernames are skipped, not errored, so re-running with extra
    # lines added is safe.
    st.markdown("---")
    with st.expander("📦 Bulk Grant — create many accounts at once", expanded=False):
        st.caption(
            "Paste one row per line in the format "
            "**`type | full_name | username`** (fields separated by the pipe "
            "character `|`). Use `host` or `facilitator` for type. The pipe is "
            "used instead of comma because some stored names contain commas "
            "(e.g., `Marshall, Courtney`). For hosts you can write either the "
            "venue name (e.g., `Bradford`) or the contact person (e.g., "
            "`Devin Pendleton`). All new rows are created with the shared "
            "access code shown above, approved immediately, and require the "
            "user to set their own password on first sign-in. Existing "
            "usernames are skipped, not overwritten."
        )

        bulk_text = st.text_area(
            "Bulk roster",
            value="",
            placeholder=(
                "facilitator | Alice B Fogel | afogel\n"
                "facilitator | Marshall, Courtney | cmarshall\n"
                "host | Anne Deely | adeely\n"
                "host | Devin Pendleton | dpendleton"
            ),
            height=220,
            key="bulk_roster_text",
        )

        if st.button("🚀 Create all rows", use_container_width=True,
                     key="bulk_grant_submit"):
            # Build lookup tables once. Match keys are lowercase + stripped so
            # "alice b fogel" matches "Alice B Fogel" without manual cleanup.
            def _norm(s: str) -> str:
                return (s or "").strip().lower()

            existing_usernames = {
                _norm(a.get("username", "")): a.get("username", "")
                for a in get_all_portal_access()
            }
            facs_by_name = {_norm(f.get("name", "")): f for f in facs}
            hosts_by_name = {_norm(h.get("name", "")): h for h in hosts}
            hosts_by_contact = {
                _norm(h.get("contact_person", "")): h
                for h in hosts
                if _norm(h.get("contact_person", ""))
            }

            results = []  # list of (status, original_line, message)
            lines = [ln for ln in bulk_text.splitlines() if ln.strip()]
            if not lines:
                st.warning("Paste at least one row before clicking Create.")
                st.stop()

            for ln in lines:
                parts = [p.strip() for p in ln.split("|")]
                if len(parts) != 3:
                    results.append(("error", ln,
                                    "needs exactly 3 pipe-separated fields"))
                    continue
                ptype_raw, pname_raw, puser_raw = parts
                ptype = ptype_raw.lower()
                puser = puser_raw  # keep username as typed (case-sensitive)
                pname_key = _norm(pname_raw)

                if ptype not in ("host", "facilitator"):
                    results.append(("error", ln,
                                    f"unknown type '{ptype_raw}' — must be host or facilitator"))
                    continue
                if not puser:
                    results.append(("error", ln, "username is empty"))
                    continue
                if _norm(puser) in existing_usernames:
                    results.append(("skip", ln,
                                    f"username '{puser}' already exists"))
                    continue

                if ptype == "facilitator":
                    target = facs_by_name.get(pname_key)
                    if not target:
                        results.append(("error", ln,
                                        f"no facilitator named '{pname_raw}'"))
                        continue
                    pid = target["facilitator_id"]
                else:
                    target = (hosts_by_name.get(pname_key)
                              or hosts_by_contact.get(pname_key))
                    if not target:
                        results.append(("error", ln,
                                        f"no host venue or contact_person matches '{pname_raw}'"))
                        continue
                    pid = target["host_id"]

                add_portal_access({
                    "person_type": ptype,
                    "person_id":   pid,
                    "username":    puser,
                    "password":    _shared_pw,
                    "is_active":   1,
                    "notes":       "Bulk created",
                    "must_change_password": 1,
                })
                existing_usernames[_norm(puser)] = puser
                log_activity("Portal Access Created (bulk)",
                             f"{pname_raw} (@{puser}) — Active")
                results.append(("ok", ln, "created and approved"))

            ok_count   = sum(1 for r in results if r[0] == "ok")
            skip_count = sum(1 for r in results if r[0] == "skip")
            err_count  = sum(1 for r in results if r[0] == "error")

            if ok_count:
                st.success(f"✅ Created {ok_count} new portal account(s).")
            if skip_count:
                st.info(f"⏭️ Skipped {skip_count} row(s) — username already existed.")
            if err_count:
                st.error(f"❌ {err_count} row(s) failed — see details below.")

            with st.container():
                for status, ln, msg in results:
                    icon = {"ok": "✅", "skip": "⏭️", "error": "❌"}[status]
                    st.text(f"{icon} {ln}  — {msg}")
