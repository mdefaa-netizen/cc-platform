import streamlit as st
import sys, os, io, csv, smtplib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from utils.database import (log_activity, add_notification, DB_PATH, get_connection, init_db,
                            get_all_users, reset_user_password, create_user, username_exists,
                            hash_password, verify_password)
from utils.email_utils import get_smtp_config
from utils.styles import inject_css, page_header
import secrets as _secrets, string as _string

st.set_page_config(page_title="Settings · CC Platform", page_icon="⚙️", layout="wide")
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

if role != "coordinator":
    st.error("Settings is only accessible to the Coordinator.")
    st.stop()

page_header("⚙️ Settings", "Configure email, password, and manage your data")

tab_users, tab_email, tab_data, tab_about = st.tabs(["👥 User Management", "📧 Email Setup", "🗄️ Data Management", "ℹ️ About"])

with tab_users:
    st.markdown("### All User Accounts")
    users = get_all_users()
    if users:
        for u in users:
            role_icons = {"coordinator": "👑", "nhh": "🏛️", "cdfa": "🌾",
                         "facilitator": "🎤", "host": "👥"}
            icon = role_icons.get(u["role"], "👤")
            st.markdown(f"- {icon} **{u['username']}** — {u['role'].title()}"
                       f" (created: {str(u.get('created_at',''))[:10]})")
    else:
        st.info("No users found.")

    st.markdown("---")
    st.markdown("### Reset a User's Password")
    st.caption("Use this to reset any user's password, including your own.")
    with st.form("reset_pw_form"):
        user_opts = {u["username"]: f"{u['username']} ({u['role']})" for u in users}
        sel_user = st.selectbox("Select user", options=list(user_opts.keys()),
                                format_func=lambda x: user_opts[x])
        new_pw = st.text_input("New Password", type="password",
                               placeholder="Enter new password (min 8 characters)")
        confirm_pw = st.text_input("Confirm Password", type="password",
                                   placeholder="Re-enter new password")
        if st.form_submit_button("🔑 Reset Password", use_container_width=True):
            if not new_pw or not confirm_pw:
                st.error("Both password fields are required.")
            elif new_pw != confirm_pw:
                st.error("Passwords do not match.")
            elif len(new_pw) < 8:
                st.error("Password must be at least 8 characters.")
            else:
                reset_user_password(sel_user, new_pw)
                log_activity("Password Reset", f"Password reset for user: {sel_user}")
                st.success(f"Password reset for **{sel_user}**!")

    st.markdown("---")
    st.markdown("### Create New User Account")
    st.caption("Create accounts for NHH colleagues, CDFA colleagues, or additional coordinators.")
    with st.form("create_user_form"):
        c1, c2 = st.columns(2)
        with c1:
            new_username = st.text_input("Username *", placeholder="e.g., jsmith")
            new_role = st.selectbox("Role *", ["coordinator", "nhh", "cdfa"])
        with c2:
            _chars = _string.ascii_letters + _string.digits + "!@#$%"
            suggested_pw = "".join(_secrets.choice(_chars) for _ in range(16))
            new_user_pw = st.text_input("Password *", value=suggested_pw, type="password",
                                        help="Auto-generated. You can change it.")
            show_pw = st.checkbox("Show password")
        if show_pw:
            st.code(new_user_pw)
        if st.form_submit_button("➕ Create Account", use_container_width=True):
            if not new_username or not new_user_pw:
                st.error("Username and password are required.")
            elif len(new_user_pw) < 8:
                st.error("Password must be at least 8 characters.")
            elif username_exists(new_username.strip().lower()):
                st.error(f"Username '{new_username}' already exists.")
            else:
                create_user(new_username.strip().lower(), new_user_pw, new_role)
                log_activity("User Created", f"New {new_role} user: {new_username}")
                st.success(f"Account created for **{new_username}**!")
                st.warning("Share these credentials securely (shown once only):")
                st.code(f"Username: {new_username.strip().lower()}\nPassword: {new_user_pw}\nRole: {new_role}")

    st.markdown("---")
    st.markdown("""
    <div class="section-box">
        <strong>How accounts work:</strong><br>
        <strong>Coordinator / NHH / CDFA</strong> — Created here. They log in on the main sign-in page.<br>
        <strong>Facilitator / Host</strong> — Created automatically when you add a new host or facilitator
        on their respective pages. They also get a separate Portal login via Portal Access.<br>
    </div>
    """, unsafe_allow_html=True)

with tab_email:
    st.markdown("### Gmail Setup — Step by Step")
    st.markdown("""
    <div class="section-box">
        <strong>Why does email fail with my regular password?</strong><br>
        Gmail blocks regular passwords for third-party apps.
        You need a special <strong>App Password</strong> — a 16-character code Gmail
        generates just for this app.
    </div>
    """, unsafe_allow_html=True)

    with st.expander("📋 How to get your Gmail App Password", expanded=True):
        st.markdown("""
**Step 1** — Open: https://myaccount.google.com

**Step 2** — Click **Security** in the left menu

**Step 3** — Make sure **2-Step Verification is ON**
(App Passwords only work when 2-Step Verification is enabled)

**Step 4** — In the Google Account search bar, type **App Passwords** and click it

**Step 5** — Type **Community Conversations** as the app name, click **Create**

**Step 6** — Google shows a 16-character password like: `abcd efgh ijkl mnop`
Copy it — you only see it once!

**Step 7** — Paste it in the form below (spaces are OK, they will be removed automatically)
        """)

    st.markdown("---")
    st.markdown("### Enter Your Credentials")
    cfg = get_smtp_config()

    with st.form("email_form"):
        gmail  = st.text_input("Your Gmail Address", value=cfg.get("user",""), placeholder="yourname@gmail.com")
        app_pw = st.text_input("Gmail App Password", placeholder="abcd efgh ijkl mnop", type="password")
        submit = st.form_submit_button("💾 Save & Send Test Email", use_container_width=True)

        if submit:
            if not gmail or not app_pw:
                st.error("Both fields are required.")
            else:
                clean_pw = app_pw.replace(" ","")
                secrets_path = os.path.abspath(
                    os.path.join(os.path.dirname(__file__), "..", ".streamlit", "secrets.toml"))
                try:
                    os.makedirs(os.path.dirname(secrets_path), exist_ok=True)
                    with open(secrets_path, "w") as f:
                        f.write(f'SMTP_HOST     = "smtp.gmail.com"\n')
                        f.write(f'SMTP_PORT     = "587"\n')
                        f.write(f'SMTP_USER     = "{gmail}"\n')
                        f.write(f'SMTP_PASSWORD = "{clean_pw}"\n')
                        f.write(f'FROM_EMAIL    = "{gmail}"\n')
                    st.success("Credentials saved! Sending test email...")
                    try:
                        msg = MIMEMultipart()
                        msg["Subject"] = "Test - CC Platform Email Working!"
                        msg["From"]    = gmail
                        msg["To"]      = gmail
                        msg.attach(MIMEText(
                            "Your Community Conversations email is working correctly!\n\n"
                            "You can now send confirmation emails, reminders, and post-event summaries.",
                            "plain"))
                        with smtplib.SMTP("smtp.gmail.com", 587) as server:
                            server.ehlo()
                            server.starttls()
                            server.login(gmail, clean_pw)
                            server.sendmail(gmail, gmail, msg.as_string())
                        st.success(f"Test email sent to {gmail}! Check your inbox.")
                        st.balloons()
                    except Exception as e:
                        st.error(f"Email failed: {e}")
                        st.warning("Check your App Password and make sure 2-Step Verification is ON.")
                except Exception as e:
                    st.error(f"Could not save credentials: {e}")

    st.markdown("---")
    cfg2 = get_smtp_config()
    if cfg2.get("user"):
        st.success(f"Currently configured for: **{cfg2['user']}**")
    else:
        st.warning("Email not configured yet.")

with tab_data:
    st.markdown("### Database Backup")
    if st.button("⬇️ Download Backup"):
        with open(DB_PATH, "rb") as f:
            st.download_button("📦 Download cc_platform.db", f.read(),
                               "cc_platform_backup.db", "application/octet-stream")

    st.markdown("---")
    st.markdown("### Export to CSV")
    _ALLOWED_TABLES = {"hosts","facilitators","nhh_colleagues","cdfa_colleagues",
                        "events","tasks","communications","feedback","reports"}
    tables = sorted(_ALLOWED_TABLES)
    sel_table = st.selectbox("Select table", tables)
    if st.button("⬇️ Export CSV"):
        if sel_table not in _ALLOWED_TABLES:
            st.error("Invalid table selection.")
            st.stop()
        conn = get_connection()
        rows = conn.execute(f"SELECT * FROM {sel_table}").fetchall()
        conn.close()
        if rows:
            buf = io.StringIO()
            csv.writer(buf).writerows([rows[0].keys()] + list(rows))
            st.download_button(f"📄 {sel_table}.csv", buf.getvalue().encode(),
                               f"{sel_table}.csv", "text/csv")
        else:
            st.info("No data in that table.")

    st.markdown("---")
    with st.expander("⚠️ Danger Zone — Clear Table"):
        sel_clear = st.selectbox("Table to clear", tables, key="clear_sel")
        confirm   = st.text_input("Type CONFIRM")
        if st.button("🗑️ Clear"):
            if confirm == "CONFIRM":
                if sel_clear not in _ALLOWED_TABLES:
                    st.error("Invalid table selection.")
                    st.stop()
                conn = get_connection()
                conn.execute(f"DELETE FROM {sel_clear}")
                conn.commit(); conn.close()
                st.success(f"Table '{sel_clear}' cleared.")
            else:
                st.error("Type CONFIRM to proceed.")

with tab_about:
    st.markdown("""
    <div class="section-box">
        <h3 style='margin-top:0'>🗺️ Community Conversations Coordinator Platform v1.1</h3>
        <p>NH Humanities & CDFA · Community Conversations Program</p>
        <hr>
        <b>Pages:</b> Dashboard · Events · Hosts · Facilitators ·
        NHH Colleagues · CDFA Colleagues · Payments · Communications ·
        Tasks · Reports · Feedback · Settings
    </div>
    """, unsafe_allow_html=True)
