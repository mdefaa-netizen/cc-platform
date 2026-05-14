import streamlit as st
import sys, os, io, csv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.database import (log_activity, add_notification, DB_PATH, get_connection, init_db)
from utils.auth import require_auth, render_sidebar_user
from utils.styles import inject_css, page_header
from utils.supabase_db import _fetchall, _execute

st.set_page_config(page_title="Settings · CC Platform", page_icon="⚙️", layout="wide")
inject_css()
try:
    from utils.database import init_all
    init_all()
except ImportError:
    init_db()

role = require_auth(allowed_roles=["coordinator"])
render_sidebar_user()

page_header("⚙️ Settings", "Configure email and manage your data")

tab_data, tab_about = st.tabs(["🗄️ Data Management", "ℹ️ About"])

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
        rows = _fetchall(conn, f"SELECT * FROM {sel_table}")
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
                _execute(conn, f"DELETE FROM {sel_clear}")
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
