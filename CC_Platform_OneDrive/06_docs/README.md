# 🗺️ Community Conversations Coordinator Platform

**NH Humanities & CDFA — Community Conversations Program**

A complete web-based coordination platform for managing hosts, facilitators,
events, payments, communications, tasks, and reporting.

---

## 🚀 Quick Start (Local Development)

### 1. Install Dependencies

```bash
cd cc_platform
pip install -r requirements.txt
```

### 2. Configure Secrets

```bash
mkdir -p .streamlit
cp secrets.toml.template .streamlit/secrets.toml
# Edit .streamlit/secrets.toml with your values
```

### 3. Run the App

```bash
streamlit run app.py
```

Open http://localhost:8501 in your browser.
Default password: `nhhumanities2025`

---

## ☁️ Deploy to Streamlit Community Cloud

### Step 1 — Push to GitHub
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/cc-platform.git
git push -u origin main
```

**Important:** Add `.gitignore`:
```
.streamlit/secrets.toml
cc_platform.db
__pycache__/
*.pyc
```

### Step 2 — Deploy on Streamlit Cloud
1. Go to https://share.streamlit.io
2. Click **New app**
3. Select your GitHub repo and `app.py` as the main file
4. Click **Advanced settings** → paste your secrets (from `secrets.toml.template`)
5. Click **Deploy**

### Step 3 — Database for Production
For persistent data on Streamlit Cloud, use a free PostgreSQL service:
- **Supabase** (recommended): https://supabase.com → free tier PostgreSQL
- Update `DB_PATH` in `utils/database.py` with the connection string

---

## 📧 Gmail SMTP Setup

1. Enable 2-Factor Authentication on your Gmail account
2. Go to Google Account → Security → App Passwords
3. Generate a 16-character app password
4. Use that password as `SMTP_PASSWORD` in secrets.toml

---

## 📁 Project Structure

```
cc_platform/
├── app.py                    # Main entry point + Dashboard
├── requirements.txt
├── secrets.toml.template
├── utils/
│   ├── database.py           # All database operations
│   ├── styles.py             # CSS + UI helpers
│   ├── email_utils.py        # SMTP + email templates
│   └── report_utils.py       # Excel + PDF generation
└── pages/
    ├── 2_Events.py
    ├── 3_Hosts.py
    ├── 4_Facilitators.py
    ├── 5_Payments.py
    ├── 6_Communications.py
    ├── 7_Tasks.py
    ├── 8_Reports.py
    ├── 9_Feedback.py
    └── 10_Settings.py
```

---

## 🔐 Default Login

| Field    | Value               |
|----------|---------------------|
| Password | `nhhumanities2025`  |

Change this in `.streamlit/secrets.toml` → `APP_PASSWORD`

---

## 📊 Features Summary

| Page | Feature |
|------|---------|
| 🏠 Dashboard | KPIs, upcoming events, overdue tasks, quick actions |
| 📅 Events | Add/edit/view events, assign hosts & facilitators |
| 👥 Hosts | Host contacts, payment tracking, event history |
| 🎤 Facilitators | Facilitator pool, assignments, payment tracking |
| 💰 Payments | Payment status, trigger checklist, batch updates |
| 📧 Communications | Email with templates, send via SMTP, full log |
| ✅ Tasks | Task tracking with priority, deadline alerts |
| 📊 Reports | Excel (5 sheets) and PDF reports for NHH/CDFA |
| 📝 Feedback | Participant feedback collection and summary |
| ⚙️ Settings | Email config, CSV export, database backup |
