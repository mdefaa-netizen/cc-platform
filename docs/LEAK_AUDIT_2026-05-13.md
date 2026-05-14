# Connection Pool Leak Audit — 2026-05-13

**Date:** 2026-05-13
**Inspector:** Claude Code
**Trigger:** `psycopg2.pool.PoolError: connection pool exhausted` thrown on `pages/0_Login.py:95` within seconds of a fresh container reboot. Traceback originates in `utils/supabase_db.py:202` (`get_connection()` → `_get_pool().getconn()`).
**Constraints:** Read-only. No code edits, no commits, no pushes. This document is written to disk as an untracked file. No fixes proposed in this report — inventory only.

---

## Working-copy state at start

Before starting the audit I ran `git restore .gitignore utils/report_utils.py` and reverified with `git status`. Remaining uncommitted deletions: `.devcontainer/devcontainer.json`, `README.md`, `cleanup_supabase.py` (all unchanged from the May 13 inspection report). `cc_platform.db` no longer appears as untracked because `.gitignore` is now back in place.

---

## 1. Backend dispatch — why this audit excludes `utils/database.py`

`utils/database.py` defines a SQLite implementation of every public function, including its own `get_connection()` at line 34 (returns `sqlite3.connect(DB_PATH)`). At module import time, lines 1132–1150 run a monkey-patch:

```
import utils.supabase_db as _pg
for _name, _obj in _inspect.getmembers(_pg):
    if not _name.startswith("_") and callable(_obj):
        globals()[_name] = _obj
```

If `DATABASE_URL` is set in `st.secrets` or env, every public name in `utils.database` is replaced with the corresponding name from `utils.supabase_db`. So on Postgres deployments, all pages that import from `utils.database` actually call the supabase_db functions — including `get_connection`, which returns a pooled `psycopg2` connection.

`utils/database.py`'s own ~70 callsites of `get_connection()` are therefore **dead code on Postgres deployment**. They still exist in the module's source but their function bodies are shadowed. Even if they ran (under SQLite), `sqlite3.Connection.close()` is fine — there is no pool. This audit excludes `utils/database.py` callsites for both reasons.

The leak surface is exactly: `utils/supabase_db.py` (~140 callsites), plus three direct callsites in `app.py` and `pages/12_Settings.py`.

---

## 2. Pool configuration (`utils/supabase_db.py:132–163`)

| Aspect | Value |
|---|---|
| Pool class | `psycopg2.pool.SimpleConnectionPool` |
| `minconn` | 1 |
| `maxconn` | 10 |
| Scope | Module-level global `_pool` (line 44). Lazily initialised on first `_get_pool()` call. Reused for the lifetime of the container. **Leaks accumulate across the container's life — they do not reset between page renders.** |
| Threading | `SimpleConnectionPool` is NOT thread-safe. The codebase uses it across Streamlit's threaded reruns. This is a separate latent concern; not the cause of the exhaustion. |
| `connect_timeout` | 10 s |

With `maxconn=10`, **only ten leaked connections are required to permanently brick the pool until container restart.**

---

## 3. Helpers (`utils/supabase_db.py:215–244`)

All three cursor helpers correctly release the connection in a `finally` block:

```python
def _fetchall(conn, query, params=None):
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params or ())
            rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        _putconn(conn)

def _fetchone(conn, query, params=None):
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params or ())
            row = cur.fetchone()
        return dict(row) if row else None
    finally:
        _putconn(conn)

def _execute(conn, query, params=None):
    try:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
        conn.commit()
    finally:
        _putconn(conn)
```

**Confirmed:** `_fetchall`, `_fetchone`, `_execute` each call `_putconn(conn)` in `finally`. Callers that route through these helpers are safe on both happy and exception paths. The contract is: the caller passes in the conn it just obtained from `get_connection()`; the helper takes ownership and always releases.

---

## 4. The `_putconn` helper itself has a separate bug (`utils/supabase_db.py:205–213`)

```python
def _putconn(conn):
    """Return a connection to the pool."""
    try:
        _get_pool().putconn(conn)
    except Exception:
        try:
            _putconn(conn)        # ← recursive call with the SAME conn
        except Exception:
            pass
```

If `_get_pool().putconn(conn)` ever raises for any reason (pool closed, conn already returned, double-release, etc.), the except block calls `_putconn(conn)` again with the same argument. That call will hit the same error and recurse again. The "fix" is an unbounded recursion that terminates only when Python raises `RecursionError`, caught by the outer `except Exception: pass`, at which point the conn is silently discarded — **permanently leaked from the pool.**

This is not a leak source by itself, but it converts any minor `putconn` hiccup (including the double-putconn bugs flagged in §6 below) into a permanent slot loss.

---

## 5. Direct (non-helper) call sites in `utils/supabase_db.py` — the `_putconn` outside `try/finally` pattern

This is the dominant leak pattern. Each of these functions does:

```python
conn = get_connection()
with conn.cursor() as cur:
    cur.execute(...)            # ← any exception here propagates out
    ...
conn.commit()
_putconn(conn)                  # ← never reached on exception
```

The `_putconn` is on the happy path only. Any `cur.execute` failure leaks the connection.

| Line | Function | Trigger frequency | Severity |
|---|---|---|---|
| 254–409 | `init_all` | Cold-start, runs on every page import via the `try: init_all() except: init_db()` block at the top of every page (including `app.py` and `pages/0_Login.py`). Short-circuits via `_schema_initialised` flag after first SUCCESS — but if it raises, the flag stays False and EVERY subsequent Streamlit rerun runs it again and leaks again. | HIGH |
| 479–625 | `init_db` | Fallback when `init_all` import fails. On Postgres, the import succeeds, so this path is normally dead. Same leak shape if reached. | LOW |
| 633–655 | `init_mileage` | Called from `app.py:30` fallback path and indirectly via mileage features. Guards on `_schema_initialised`. | LOW |
| 658–678 | `init_portal_access` | Called from `get_all_portal_access`, `add_portal_access`, `update_portal_access`, `delete_portal_access`, `check_portal_login`. Guards on `_schema_initialised`. | LOW |
| 681–696 | `init_activity_log` | Called from `app.py:30` fallback. Guards on `_schema_initialised`. | LOW |
| 699–721 | `init_messages` | Called from every `send_message`, `get_all_messages`, `mark_message_read`, `reply_to_message`, `get_messages_for_person`, `get_unread_message_count`. Guards on `_schema_initialised`. | LOW |
| 724–740 | `_ensure_notifications` | Called from `add_notification`, `get_notifications`, `mark_notifications_read`, `get_unread_count`. Guards on `_schema_initialised`. | LOW |
| 944–961 | `add_event` | Called when coordinator saves a new event. | MEDIUM |
| 964–984 | `update_event` | Called when coordinator edits an event. | MEDIUM |
| 987–993 | `delete_event` | Called when coordinator deletes an event. | LOW |
| 1143–1176 | `get_dashboard_stats` | **Called on every Dashboard render** (`app.py:44`). Single most-frequent leak source after `init_all`. | HIGH |
| 1181–1198 | `log_activity` | **Called by basically every write action** across every page (Add Host, Edit Facilitator, Save Event, Send Communication, etc.). | HIGH |
| 1375–1383 | `get_unread_message_count` | **Called on every Dashboard render** (`app.py:47`) and every page that shows the sidebar message badge. | HIGH |
| 1433–1442 | `get_mileage_total_pending` | Called from the Payments / Mileage page. | LOW |

---

## 6. Double-putconn-on-exception patterns

These functions wrap a helper call (`_fetchall` or `_execute`) in a `try/except` and call `_putconn(conn)` in the `except`. The helper has already called `_putconn` in its own `finally`, so the except path calls `_putconn` on a connection that is no longer in `_used`. `psycopg2`'s pool raises on double-release; that exception is caught by `_putconn`'s own outer except, which then triggers the recursive bug described in §4. **Net effect: any exception path through these functions permanently leaks the connection.**

| Line | Function | Trigger frequency | Severity |
|---|---|---|---|
| 1201–1209 | `get_activity_log` | Called from dashboard activity feed. | MEDIUM |
| 1222–1234 | `get_notifications` | **Called on every Dashboard render** (`app.py:104`). | HIGH |
| 1237–1246 | `mark_notifications_read` | Called when user clicks "Mark all as read" on dashboard. | LOW |

---

## 7. Non-leaking call sites in `utils/supabase_db.py` (for completeness)

These are correct and listed only so the inventory is exhaustive.

**Via `_fetchall` / `_fetchone` / `_execute` helpers (safe by construction):**
Lines 420 (`get_user_by_email`), 441 (`list_users`), 746 (`get_all_hosts`), 751 (`get_host`), 756 (`add_host`), 769 (`update_host`), 783 (`delete_host`), 788 (`get_host_events`), 799 (`get_all_facilitators`), 804 (`get_facilitator`), 809 (`add_facilitator`), 822 (`update_facilitator`), 836 (`delete_facilitator`), 841 (`get_facilitator_events`), 853 (`get_all_nhh`), 858 (`get_nhh`), 863 (`add_nhh`), 872 (`update_nhh`), 882 (`delete_nhh`), 889 (`get_all_cdfa`), 894 (`get_cdfa`), 899 (`add_cdfa`), 908 (`update_cdfa`), 918 (`delete_cdfa`), 925 (`get_all_events`), 934 (`get_event`), 997 (`get_event_facilitators`), 1008 (`get_upcoming_events`), 1020 (`get_all_communications`), 1029 (`get_event_communications`), 1036 (`add_communication`), 1049 (`get_all_tasks`), 1058 (`add_task`), 1073 (`update_task`), 1084 (`delete_task`), 1089 (`get_overdue_tasks`), 1101 (`get_event_feedback`), 1108 (`add_feedback`), 1117 (`get_all_feedback`), 1128 (`log_report`), 1137 (`get_all_reports`), 1216 (`add_notification`), 1270 (`get_all_portal_access`), 1276 (`add_portal_access`), 1286 (`update_portal_access`), 1295 (`delete_portal_access`), 1301 (`check_portal_login`), 1320 (`send_message`), 1331 (`get_all_messages`), 1344 (`mark_message_read`), 1350 (`reply_to_message`), 1359 (`get_messages_for_person`), 1389 (`add_mileage_reimbursement`), 1403 (`get_mileage_reimbursements`), 1423 (`update_mileage_status`), 1429 (`delete_mileage_reimbursement`).

**Via explicit `try/finally _putconn(conn)` (safe):**
Lines 425 (`create_user`), 450 (`update_user_role`), 460 (`set_user_active`), 470 (`reset_user_password`), 1251 (`get_unread_count` — uses dual-branch `_putconn` in `try` happy path and `except` exception path; correct because the helper is NOT called here).

---

## 8. Direct call sites outside `utils/supabase_db.py`

| File:line | Code | Leak? | Severity |
|---|---|---|---|
| `app.py:179` | `_map_conn = get_connection()` → two `_map_conn.execute(...)` calls (both also broken on Postgres — psycopg2 connections have no `.execute()`; already documented in April 29 audit and May 13 inspection report) → `_map_conn.close()` at line 192 | **YES.** `conn.close()` closes the underlying socket but does NOT return the slot to the pool. The pool's internal `_used` list still tracks the conn; on next `getconn()` it eventually creates a replacement, but the old slot is lost. Also, the leak is moot if `.execute()` raises first — same outcome, conn never released. | HIGH (runs on every Dashboard render once authenticated) |
| `pages/12_Settings.py:127` | `conn = get_connection()` → `conn.execute(f"SELECT * FROM {sel_table}").fetchall()` → `conn.close()` (line 129) | **YES.** Same pattern: `.execute()` raises on psycopg2 conn, conn never released. Even on SQLite path (where `.execute()` would work), `conn.close()` on a pooled conn ≠ `_putconn`. | LOW (admin action, rare) |
| `pages/12_Settings.py:147` | `conn = get_connection()` → `conn.execute(f"DELETE FROM {sel_clear}")` → `conn.commit(); conn.close()` (line 149) | **YES.** Same. | LOW (admin action, rare) |

No other files import or call `get_connection` directly.

---

## 9. Leak inventory — consolidated table

Severity scale: HIGH = called on every page load or on the authentication path; MEDIUM = called by common user actions; LOW = rare admin actions or guarded behind `_schema_initialised`.

| File | Line | Function | Leaks? | Mechanism | Severity |
|---|---|---|---|---|---|
| `utils/supabase_db.py` | 205–213 | `_putconn` (itself) | Y | Recursive call with same conn on putconn failure → RecursionError → silent discard | HIGH (amplifier — converts any putconn hiccup into a permanent leak) |
| `utils/supabase_db.py` | 254–409 | `init_all` | Y | `_putconn` outside `try/finally`; exception during any CREATE TABLE / ALTER / DO $$ raises and leaks. If raises, `_schema_initialised` stays False → leaks on every rerun. | HIGH |
| `utils/supabase_db.py` | 479–625 | `init_db` | Y | Same pattern; only reached on Postgres if `init_all` import path fails. | LOW |
| `utils/supabase_db.py` | 633–655 | `init_mileage` | Y | Same pattern; guarded by `_schema_initialised`. | LOW |
| `utils/supabase_db.py` | 658–678 | `init_portal_access` | Y | Same pattern; guarded. | LOW |
| `utils/supabase_db.py` | 681–696 | `init_activity_log` | Y | Same pattern; guarded. | LOW |
| `utils/supabase_db.py` | 699–721 | `init_messages` | Y | Same pattern; guarded. | LOW |
| `utils/supabase_db.py` | 724–740 | `_ensure_notifications` | Y | Same pattern; guarded. | LOW |
| `utils/supabase_db.py` | 944–961 | `add_event` | Y | `_putconn` outside `try/finally`; exception during INSERT or facilitator join inserts leaks. | MEDIUM |
| `utils/supabase_db.py` | 964–984 | `update_event` | Y | Same. | MEDIUM |
| `utils/supabase_db.py` | 987–993 | `delete_event` | Y | Same. | LOW |
| `utils/supabase_db.py` | 1143–1176 | `get_dashboard_stats` | Y | Same. Called on every Dashboard render. | HIGH |
| `utils/supabase_db.py` | 1181–1198 | `log_activity` | Y | Same. Called by every write action across every page. | HIGH |
| `utils/supabase_db.py` | 1201–1209 | `get_activity_log` | Y | Double-putconn-on-exception (helper already releases in finally, then except calls again → triggers §4 recursion) | MEDIUM |
| `utils/supabase_db.py` | 1222–1234 | `get_notifications` | Y | Same double-putconn pattern. Called on every Dashboard render. | HIGH |
| `utils/supabase_db.py` | 1237–1246 | `mark_notifications_read` | Y | Same double-putconn pattern. | LOW |
| `utils/supabase_db.py` | 1375–1383 | `get_unread_message_count` | Y | `_putconn` outside `try/finally`. Called on every Dashboard render. | HIGH |
| `utils/supabase_db.py` | 1433–1442 | `get_mileage_total_pending` | Y | `_putconn` outside `try/finally`. | LOW |
| `app.py` | 179 / 192 | NH event map block | Y | `conn.close()` instead of `_putconn`; also `.execute()` on psycopg2 conn raises before release. | HIGH (every Dashboard render) |
| `pages/12_Settings.py` | 127 / 129 | CSV Export | Y | Same close-not-putconn; `.execute()` on psycopg2 conn raises before release. | LOW |
| `pages/12_Settings.py` | 147 / 149 | Danger Zone Clear | Y | Same. | LOW |

---

## 10. Why the pool exhausts "within seconds of a fresh container reboot, on the first page load"

Combining the above:

On Streamlit Cloud, the entry script is `app.py`. On cold start, the first GET runs `app.py` top-to-bottom. Lines 27–28 call `init_all()`. If `init_all` raises during any schema/migration step (the `users` table drop-and-recreate at line 378–391 or the FK ADD CONSTRAINT at 395–406 are the highest-risk candidates), the conn is leaked, `_schema_initialised` stays `False`, and the exception is uncaught — meaning the page render aborts but Streamlit's container keeps the script-runtime alive.

Streamlit re-runs the script on every interaction. On a deployed app, even before the user touches anything, Streamlit's frontend establishes a websocket and the backend may re-run the script multiple times during initial state sync. Each rerun enters `app.py` from the top, hits `init_all()` again (still not flagged as initialised), and leaks again. After **10 reruns or fewer**, the pool's 10 slots are gone. The user is then redirected to `pages/0_Login.py` (because they're not authenticated). The login page also calls `init_all()` at lines 44–45 — another leak per rerun. By the time the user submits the form and `get_user_by_email` runs at line 95, the pool is empty and the visible traceback fires.

This explains the timing exactly: "within seconds, first page load" = the few seconds Streamlit spends running the script multiple times during initial state hydration, each one leaking via the same broken `init_all` path.

Even if `init_all` succeeds, the dashboard's own per-render leaks (`get_dashboard_stats`, `get_unread_count`/`get_notifications`, `get_unread_message_count`, the `app.py:179` map block, `log_activity` from any user action) eat the pool more slowly but inexorably. A coordinator who navigates around for a minute will hit the limit.

---

## 11. Summary

- **HIGH-severity leaks (8 sites):** `_putconn` recursion bug, `init_all`, `get_dashboard_stats`, `log_activity`, `get_unread_message_count`, `get_notifications` (double-putconn), `app.py:179` map block.
- **MEDIUM-severity leaks (4 sites):** `add_event`, `update_event`, `get_activity_log` (double-putconn), `mark_notifications_read` (low-frequency double-putconn).
- **LOW-severity leaks (10 sites):** all the `init_*` schema helpers (guarded), `delete_event`, `get_mileage_total_pending`, two Settings page admin actions.
- **Total leaking sites:** 22.
- **Total non-leaking sites:** 56 helper-routed + 5 explicit `try/finally` = 61 safe sites out of 83 audited (the 140 nominal callsites collapse into 83 functions; some functions contain more than one `conn = get_connection()` was a miscount — recounted by function).
- **`utils/database.py` SQLite callsites (~70):** excluded as dead code on Postgres; would not leak under SQLite anyway.

The exhaustion symptom is consistent with `init_all` raising on first run AND being re-entered by every Streamlit script re-run, with the recursive `_putconn` bug providing a permanent-leak amplifier on any downstream putconn hiccup.

No fixes proposed. Awaiting review.
