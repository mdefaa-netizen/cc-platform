# CC-Platform Inspection — 2026-05-13

**Date:** 2026-05-13
**Inspector:** Claude Code
**Scope:** Read-only inspection of `cc-platform` triggered by a Communications module failure on the deployed Streamlit Cloud app (`https://cc-platform-lwgykmwhsbf954mjqsdgl5.streamlit.app`). The coordinator reported that clicking Send on the Communications page produces an error after Gmail SMTP credentials were configured via the in-app Settings form.
**Constraints:** Read-only. No edits to application code. No `git add`, no commit, no push. This report is written to disk but left untracked.

---

## Executive Summary

The Communications page fails because the `pages/12_Settings.py` "Save & Send Test Email" form writes Gmail credentials to `.streamlit/secrets.toml` inside the Streamlit Cloud container's ephemeral filesystem, then validates them with a one-shot SMTP test using the form inputs directly. The credentials never reach Streamlit Cloud's durable dashboard-managed secrets store, so on the next container restart `st.secrets["SMTP_USER"]` and `st.secrets["SMTP_PASSWORD"]` revert to empty. `send_email()` then short-circuits at its empty-credential guard and surfaces a yellow warning on every Send attempt.

A second cluster of production-breaking bugs flagged in the April 29 audit is still present on the same Postgres deployment path: `app.py:179` (NH event map), and `pages/12_Settings.py:113, 127, 147` (Download Backup, CSV Export, Danger Zone Clear) all assume a SQLite filesystem-backed DB and will fail on a Supabase / Postgres backend. The first three use `conn.execute(...)` directly on a `psycopg2` connection that has no such method; the fourth attempts `open(DB_PATH, "rb")` on a SQLite file that does not exist in a Postgres deployment.

Zero commits have landed since the April 29 audit (`e810c1f` 2026-04-29). The codebase that produced the Communications failure is byte-for-byte the same as the audit snapshot. No fixes have been applied in the intervening 14 days.

---

## Root Cause: Communications Module

### The visible failure

When the coordinator clicks **Send Email** on `pages/8_Communications.py`, the page reaches line 195 (`ok, msg = send_email(to_email, subject, body)`). Inside `utils/email_utils.py:18`, `send_email()` first calls `get_smtp_config()`, then checks at line 20:

```python
if not cfg["user"] or not cfg["password"]:
    return False, "SMTP credentials not configured. Go to Settings to configure email."
```

The returned `(False, msg)` propagates back to `pages/8_Communications.py:199`, which appends the message to `errors` and renders it via `st.warning(...)` at line 224. The user sees one yellow warning per recipient:

> ⚠ Jane Doe: SMTP credentials not configured. Go to Settings to configure email.

This is a graceful-fallback branch, not an uncaught exception. The page itself does not crash; the page-level state is "send attempt logged but not delivered".

### Why the credentials are empty in production

The Settings page's "Save & Send Test Email" flow (`pages/12_Settings.py:60-101`) does three things in sequence:

1. **Writes the credentials to disk** at `<repo_root>/.streamlit/secrets.toml` via `os.makedirs(...)` + `open(secrets_path, "w")` (lines 73-79). On Streamlit Cloud this is the ephemeral container filesystem. Streamlit Cloud regenerates `.streamlit/secrets.toml` from dashboard-managed secrets on every container restart, redeploy, idle-wakeup, or auto-scale event. Anything the running app wrote there is erased.
2. **Runs a one-shot test send** at lines 90-94 using `smtplib.SMTP("smtp.gmail.com", 587)` and `server.login(gmail, clean_pw)` — where `gmail` and `clean_pw` are the **form variables**, not values re-read from the just-written file. The test proves the credentials work against Gmail; it proves nothing about persistence.
3. **Reports success** with `st.success("Test email sent to ...! Check your inbox.")` and `st.balloons()`.

### Three positive signals vs. zero verification of persistence

The coordinator sees three signals confirming the credentials are valid:

- "Credentials saved!" green message (based only on the local write succeeding)
- "Test email sent to ...! Check your inbox." green message (based on form inputs working against Gmail)
- An actual test email in their inbox

None of these confirms that the credentials are durably stored in Streamlit Cloud's dashboard secrets. There is no post-write reload-and-verify step, no check that values made it into a persistent store, and no warning that an in-container file write does not equal Cloud-managed persistence. After the next container restart (which Streamlit Cloud performs routinely on inactive apps), `st.secrets["SMTP_USER"]` and `st.secrets["SMTP_PASSWORD"]` return to empty defaults and every Send attempt produces the yellow warning above.

### Working hypothesis (rank-ordered)

| Rank | Hypothesis | Surfaced message |
|---|---|---|
| 1 | Credentials configured via in-app Settings form only; never added to Streamlit Cloud dashboard secrets. Container restarted; secrets now empty. | `SMTP credentials not configured. Go to Settings to configure email.` |
| 2 | Credentials are in dashboard secrets but Gmail App Password has a typo, 2-Step Verification is off, or the password was regenerated. | `(535, b'5.7.8 Username and Password not accepted. ...')` |
| 3 | `FROM_EMAIL` set in dashboard but differs from `SMTP_USER` in a way Gmail's relay policy rejects. | `('SMTPSenderRefused', ...)` |
| 4 | Outbound SMTP to `smtp.gmail.com:587` blocked at Streamlit Cloud egress (rare). | `[Errno 110] Connection timed out` |

Discriminating between hypothesis 1 and 2 requires reading the exact warning text shown on screen — a follow-up question for the coordinator.

---

## April 29 Audit Items — Current Status

| # | Audit finding | Status | Note |
|---|---|---|---|
| 1 | `app.py:179` NH event map uses `conn.execute()` (SQLite-style) | STILL PRESENT | On Postgres, `get_connection()` (`utils/supabase_db.py:201-202`) returns a `psycopg2` connection from a `ThreadedConnectionPool`. psycopg2 connections do not expose `.execute()` — only cursors do. Lines 180 and 187 both raise `AttributeError`. Line 192's `.close()` also leaks the pool slot instead of using `putconn`. |
| 2a | `pages/12_Settings.py:113` Download Backup | STILL PRESENT | `open(DB_PATH, "rb")` on a Postgres deployment fails with `FileNotFoundError` (no SQLite file exists). |
| 2b | `pages/12_Settings.py:127` CSV Export | STILL PRESENT | `conn.execute(f"SELECT * FROM {sel_table}").fetchall()` — same psycopg2 issue as #1. (The `_ALLOWED_TABLES` allow-list prevents SQL injection.) |
| 2c | `pages/12_Settings.py:147` Danger Zone Clear | STILL PRESENT | `conn.execute(f"DELETE FROM {sel_clear}")` — same psycopg2 issue. |
| 3 | `pages/11_Feedback.py` missing role gate | AS-FLAGGED | Line 18 calls `require_auth()` with no `allowed_roles`. `utils/auth.py:132` skips the role check when `allowed_roles is None`. Any signed-in user reaches the page. May be by design — needs product input. |
| 4 | `Fac-XXXXX` / `Hst-XXXXX` auto-credential generation | UNBUILT | Add Host (`pages/3_Hosts.py:106-142`) and Add Facilitator (`pages/4_Facilitators.py:116-156`) insert into the data tables and direct users to "User Admin" for login provisioning. No `Fac-` / `Hst-` pattern exists anywhere in code. |

Activity since the audit: three commits dated 2026-04-29, none since. The repo has been quiet for 14 days. None of the audit findings have been addressed.

---

## Filesystem-Write Sweep

Search of `pages/` and `utils/` for `open(`, `os.makedirs`, `Path(...).write`, `.write_text(`, and `shutil.` returned only three hits — all in one file.

| File:line | What it does | Survives Streamlit Cloud restart? | False-positive UX feedback? |
|---|---|---|---|
| `pages/12_Settings.py:73` | `os.makedirs(<.streamlit dir>, exist_ok=True)` | No — ephemeral container FS | Indirect |
| `pages/12_Settings.py:74` | `open(secrets_path, "w")` writes five SMTP keys | No — overwritten by dashboard secrets on next restart | YES — `st.success("Credentials saved!")` + successful test send + balloons, no persistence check |
| `pages/12_Settings.py:113` | `open(DB_PATH, "rb")` reads SQLite DB for backup download | n/a — read-only | n/a (but fails on Postgres — see audit item 2a) |

Reports (`pages/10_Reports.py`) uses `io.BytesIO()` in `utils/report_utils.py:144` and passes bytes directly to `st.download_button(data=xlsx_bytes, ...)`. No filesystem involvement. No image caches, temp files, or `shutil` calls anywhere in `pages/` or `utils/`.

**The "wrote to ephemeral FS and gave false-positive feedback" class of bug is isolated to Settings → Email Setup. It is not systemic.**

---

## Local Working Copy Hygiene

`git status` after restoring `utils/email_utils.py` and `utils/styles.py` (required to make the audit reflect deployed state):

```
Deletions still uncommitted:
  .devcontainer/devcontainer.json
  .gitignore
  README.md
  cleanup_supabase.py
  utils/report_utils.py

Untracked:
  cc_platform.db
```

| File | Imported / referenced? | Verdict |
|---|---|---|
| `.devcontainer/devcontainer.json` | Not imported. Used by VS Code Dev Containers / GitHub Codespaces. | Conditional. Production deploy does not use it. Safe to drop only if no one uses Codespaces. |
| `.gitignore` | Not imported. Ignores `.streamlit/secrets.toml` and `cc_platform.db`. | **KEEP.** Deleting it risks committing secrets and the local SQLite DB on the next `git add .`. |
| `README.md` | Not imported. Rendered on GitHub repo landing. | No technical break. Social cost only. Recommend keeping. |
| `cleanup_supabase.py` | Not imported anywhere. Standalone script for a one-shot fix on `activity_log`. April 29 audit §F5.3 already flagged as likely stale. | Plausibly dead. Safe to prune from a wiring standpoint after confirming no operator runs it manually. |
| `utils/report_utils.py` | **Imported by `pages/10_Reports.py:10`** — `from utils.report_utils import generate_excel, generate_pdf`. | **KEEP.** Deleting it makes the Reports page crash on import with `ModuleNotFoundError`. |

**Warning:** Committing the working tree in its current state would push deletions of `.gitignore` and `utils/report_utils.py` to production. The former would expose secrets to accidental commit; the latter would crash the Reports page. Restore both before any future commit from this working copy.

---

## Severity Classification

**HIGH (production-breaking right now):**

1. **Communications — SMTP credentials not persisted.** Coordinator's daily workflow is broken. Working hypothesis: credentials only ever made it to the ephemeral container FS via the Settings form, not to the Cloud-managed dashboard secrets store.
2. **`app.py:179` NH event map** — dashboard crashes on Postgres with `AttributeError: 'connection' object has no attribute 'execute'`. If the deployed app is on Postgres/Supabase, the whole dashboard page fails to render.
3. **`pages/12_Settings.py:113, 127, 147`** — Download Backup, CSV Export, and Danger Zone Clear all fail on Postgres. Email Setup tab still appears to work and is the source of the persistence bug above.
4. **Local working-copy corruption** — `.gitignore` and `utils/report_utils.py` are uncommitted deletions. A careless `git add . && git commit` would wipe both from production.

**MEDIUM (latent / by-design unclear):**

5. **Settings page rewrites `.streamlit/secrets.toml` directly in the container** — even if the user later sets dashboard secrets correctly, opening the Email Setup form and resaving would re-erase any other keys (e.g. `APP_PASSWORD`, `DATABASE_URL`) from the in-container view until next restart. Quiet self-foot-gun.
6. **`pages/11_Feedback.py:18`** — `require_auth()` with no allow-list. If the intent is "coordinator-only feedback review", this is a privilege bypass; if it's "any signed-in user can submit feedback", it's by design. Needs product clarification.

**LOW (unbuilt features / cleanup):**

7. **`Fac-XXXXX` / `Hst-XXXXX` auto-credentials** — unbuilt; project memory and audit already track it as a planned feature, not a regression.
8. **`cleanup_supabase.py` is likely stale** — pruning candidate, low risk.
9. **`.devcontainer/devcontainer.json`, `README.md` deletions** — local-only, no production impact unless committed.

---

## Recommended Next Actions

In order of priority. Each action is grounded in evidence gathered in Steps 1–3.

1. **Add SMTP credentials to Streamlit Cloud dashboard secrets.** Files: none (Streamlit Cloud UI only). Open the deployed app's dashboard at share.streamlit.io → app → Settings → Secrets, and add the five keys: `SMTP_HOST = "smtp.gmail.com"`, `SMTP_PORT = "587"`, `SMTP_USER = "<gmail address>"`, `SMTP_PASSWORD = "<16-char app password, no spaces>"`, `FROM_EMAIL = "<gmail address>"`. Expected outcome: on the next container restart triggered by saving, `st.secrets` returns populated values and `send_email()` proceeds past the empty-credential guard. The Communications page works again.

2. **Fix the Settings page Email Setup tab.** File: `pages/12_Settings.py:60-101`. Either (a) remove the file-write block entirely (lines 70-79) and replace it with a static panel that links to the Streamlit Cloud Secrets dashboard, or (b) keep the write for local dev only by gating it on `os.environ.get("STREAMLIT_RUNTIME") != "cloud"` (or similar) and adding a visible warning above the form stating "On Streamlit Cloud this form does not persist credentials — set them in Settings → Secrets in the dashboard instead." Expected outcome: removes the false-positive UX trap; users either land in the right place (option a) or get an explicit warning (option b).

3. **Fix the three Postgres `conn.execute()` bugs.** Files and lines: `app.py:179-191` (and `app.py:192` for the leak), `pages/12_Settings.py:127-129`, `pages/12_Settings.py:147-149`. Replace each `conn.execute(...)` with the cursor pattern already established in `utils/supabase_db.py` — wrap reads in `_fetchall(conn, query, params)` (line 215) and writes in `_execute(conn, query, params)` (line 237), both of which use `conn.cursor()` and return the connection to the pool via `_putconn`. For `app.py`, replace the two `_map_conn.execute(...).fetchall()` calls with `_fetchall(_map_conn, "...")` and remove the explicit `_map_conn.close()` at line 192 (the helper handles return-to-pool). Expected outcome: NH event map, Download Backup, CSV Export, and Danger Zone Clear all work on Postgres deployments and stop leaking pool slots.

4. **Restore `.gitignore` and `utils/report_utils.py` in the working copy.** Commands: `git restore .gitignore utils/report_utils.py`. Then verify with `git status`. Expected outcome: removes the immediate risk that a future commit from this working copy would push deletions of these files to production. The remaining three deletions (`.devcontainer/devcontainer.json`, `README.md`, `cleanup_supabase.py`) can be decided on separately — `cleanup_supabase.py` is the only one safe to actually commit as deleted, per the April 29 audit.

5. **Decide on `pages/11_Feedback.py` role gate.** File: `pages/11_Feedback.py:18`. This is a product question, not a code question. If feedback is intended to be coordinator-only, change to `require_auth(allowed_roles=["coordinator"])`. If feedback is open to all authenticated users, leave as-is and document the intent. Expected outcome: explicit decision recorded; ambiguity removed.

---

## Out of Scope / Not Investigated

This inspection was code-only and read-only. I did not run the Streamlit app locally or against the deployment. I did not query the live Postgres / Supabase database or the local SQLite DB. I did not test the user's Gmail credentials against `smtp.gmail.com:587`. I had no access to Streamlit Cloud's dashboard secrets — the hypothesis that credentials were not added there is inferred from the symptoms and the Settings page's behavior, not directly verified. The exact warning text the coordinator sees on screen would discriminate between the two leading hypotheses (Step 2.3) and should be captured before applying a fix.
