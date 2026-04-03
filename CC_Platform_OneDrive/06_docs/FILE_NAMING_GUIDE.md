# File & Folder Naming Guide — CC Platform (OneDrive)

This guide defines the consistent naming conventions used throughout the
Community Conversations Coordinator Platform stored on OneDrive.

---

## Folder Naming Rules

| Rule | Example |
|------|---------|
| Numbered prefix (`01_`, `02_`, ...) for sort order | `01_app_core`, `02_pages` |
| All lowercase with underscores (snake_case) | `03_utilities`, not `03-Utilities` |
| Short, descriptive category name | `04_scripts`, not `04_admin_and_maintenance_scripts` |
| No spaces, special characters, or accents | `05_config`, not `05 Config & Setup` |

### Folder Inventory

| Folder | Purpose |
|--------|---------|
| `01_app_core` | Main application entry point and dependency manifest |
| `02_pages` | Streamlit page modules (one per app section) |
| `03_utilities` | Shared helper modules (database, email, styles, reports) |
| `04_scripts` | One-off admin/maintenance scripts (run from terminal) |
| `05_config` | Configuration templates, launcher, and dev container setup |
| `06_docs` | Project documentation and this naming guide |

---

## File Naming Rules

| Rule | Example |
|------|---------|
| All lowercase with underscores (snake_case) | `page_events.py`, not `PageEvents.py` |
| Category prefix matching the folder purpose | `page_`, `util_`, `script_` |
| No version numbers in filenames | `util_database.py`, not `util_database_v2.py` |
| No spaces or special characters | `script_reset_data.py`, not `Reset Data.py` |
| File extensions always lowercase | `.py`, `.md`, `.toml`, `.bat`, `.json` |

### File Prefixes by Folder

| Folder | Prefix | Example |
|--------|--------|---------|
| `01_app_core` | *(none — reserved for core files)* | `app.py`, `requirements.txt` |
| `02_pages` | `page_` | `page_events.py`, `page_hosts.py` |
| `03_utilities` | `util_` | `util_database.py`, `util_email.py` |
| `04_scripts` | `script_` | `script_reset_data.py` |
| `05_config` | *(descriptive name)* | `secrets_toml_template.toml` |
| `06_docs` | *(descriptive name)* | `README.md`, `FILE_NAMING_GUIDE.md` |

---

## Complete File Map

Below is every file in the organized OneDrive folder, with its original name
and new standardized name.

### 01_app_core — Application Core

| New Name | Original Name | Description |
|----------|---------------|-------------|
| `app.py` | `app.py` | Main Streamlit entry point, dashboard, and authentication |
| `requirements.txt` | `requirements.txt` | Python package dependencies |

### 02_pages — Application Pages

| New Name | Original Name | Description |
|----------|---------------|-------------|
| `page_portal.py` | `0_Portal.py` | External portal for hosts/facilitators |
| `page_events.py` | `2_Events.py` | Event creation, editing, and management |
| `page_hosts.py` | `3_Hosts.py` | Host contact and payment management |
| `page_facilitators.py` | `4_Facilitators.py` | Facilitator pool and assignment tracking |
| `page_nhh_colleagues.py` | `5_NHH_Colleagues.py` | NH Humanities colleague management |
| `page_cdfa_colleagues.py` | `6_CDFA_Colleagues.py` | CDFA colleague management |
| `page_payments.py` | `7_Payments.py` | Payment status, checklists, and batch updates |
| `page_communications.py` | `8_Communications.py` | Email templates and communication log |
| `page_tasks.py` | `9_Tasks.py` | Task tracking with priority and deadlines |
| `page_reports.py` | `10_Reports.py` | Excel and PDF report generation |
| `page_feedback.py` | `11_Feedback.py` | Participant feedback collection |
| `page_settings.py` | `12_Settings.py` | App settings, CSV export, DB backup |
| `page_portal_access.py` | `13_Portal_Access.py` | Portal access credential management |
| `page_messages.py` | `14_Messages.py` | Internal messaging system |

### 03_utilities — Shared Utility Modules

| New Name | Original Name | Description |
|----------|---------------|-------------|
| `__init__.py` | `__init__.py` | Python package initializer |
| `util_database.py` | `database.py` | SQLite database operations and schema |
| `util_supabase_db.py` | `supabase_db.py` | PostgreSQL/Supabase database backend |
| `util_email.py` | `email_utils.py` | SMTP email sending and templates |
| `util_reports.py` | `report_utils.py` | Excel and PDF report generation logic |
| `util_styles.py` | `styles.py` | CSS injection and UI helper components |

### 04_scripts — Admin & Maintenance Scripts

| New Name | Original Name | Description |
|----------|---------------|-------------|
| `script_cleanup_supabase.py` | `cleanup_supabase.py` | Drop/recreate activity_log in Supabase |
| `script_reset_data.py` | `reset_data.py` | Clear all platform data for fresh start |
| `script_reset_password.py` | `reset_password.py` | Reset a user's password from terminal |

### 05_config — Configuration & Setup

| New Name | Original Name | Description |
|----------|---------------|-------------|
| `secrets_toml_template.toml` | `secrets.toml.template` | Template for Streamlit secrets file |
| `launch_cc_platform.bat` | `Launch_CC_Platform.bat` | Windows launcher batch file |
| `devcontainer.json` | `devcontainer.json` | VS Code dev container configuration |

### 06_docs — Documentation

| New Name | Original Name | Description |
|----------|---------------|-------------|
| `README.md` | `README.md` | Project overview, setup, and deployment guide |
| `FILE_NAMING_GUIDE.md` | *(new)* | This file — naming conventions reference |

---

## Guidelines for Adding New Files

1. **Determine the category** — Which numbered folder does it belong in?
2. **Apply the prefix** — Use the correct prefix (`page_`, `util_`, `script_`, etc.)
3. **Use snake_case** — All lowercase, words separated by underscores
4. **Be descriptive but concise** — `page_volunteer_tracker.py`, not `page_vt.py`
5. **Update this guide** — Add the new file to the relevant table above
6. **No duplicates** — Check existing files before creating a new one

---

## OneDrive Sync Notes

- The `.gitignore` file at the root excludes secrets, databases, and caches
- Never store `.streamlit/secrets.toml` or `cc_platform.db` in OneDrive
- The numbered folder prefixes ensure consistent sort order across all devices
- All filenames are compatible with Windows, macOS, and Linux (no special characters)
