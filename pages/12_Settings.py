import streamlit as st
import sys, os, io, csv, smtplib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from utils.database import log_activity, add_notification, DB_PATH, get_connection, init_db
from utils.email_utils import get_smtp_config
from utils.styles import inject_css, page_header

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

tab_email, tab_data, tab_about = st.tabs(["📧 Email Setup", "🗄️ Data Management", "ℹ️ About"])

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
