import sqlite3
import os
import hashlib
import hmac
import secrets
import string
from datetime import datetime

DB_PATH = os.environ.get("DB_PATH", "cc_platform.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

from contextlib import contextmanager

@contextmanager
def _safe_conn():
    """Context manager that guarantees connection is closed."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS hosts (
            host_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            venue_name TEXT,
            address TEXT,
            city TEXT,
            state TEXT DEFAULT 'NH',
            zip_code TEXT,
            contact_person TEXT,
            email TEXT,
            phone TEXT,
            check_payable_to TEXT,
            payment_amount REAL DEFAULT 0,
            payment_status TEXT DEFAULT 'Pending',
            payment_date DATE,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS facilitators (
            facilitator_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            address TEXT,
            city TEXT,
            state TEXT DEFAULT 'NH',
            zip_code TEXT,
            check_payable_to TEXT,
            payment_amount REAL DEFAULT 0,
            payment_status TEXT DEFAULT 'Pending',
            payment_date DATE,
            specialization TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS nhh_colleagues (
            nhh_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            title TEXT,
            email TEXT,
            phone TEXT,
            role TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS cdfa_colleagues (
            cdfa_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            title TEXT,
            email TEXT,
            phone TEXT,
            role TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_name TEXT NOT NULL,
            event_date DATE NOT NULL,
            event_time TEXT,
            host_id INTEGER REFERENCES hosts(host_id),
            venue_address TEXT,
            city TEXT,
            status TEXT DEFAULT 'Scheduled',
            attendance_count INTEGER,
            attendance_confirmed INTEGER DEFAULT 0,
            event_summary TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS event_facilitators (
            event_facilitator_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER REFERENCES events(event_id),
            facilitator_id INTEGER REFERENCES facilitators(facilitator_id)
        );
        CREATE TABLE IF NOT EXISTS communications (
            communication_id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient_type TEXT,
            recipient_id INTEGER,
            event_id INTEGER REFERENCES events(event_id),
            communication_type TEXT,
            subject TEXT,
            body TEXT,
            sent_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            sent_by TEXT DEFAULT 'Coordinator',
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS tasks (
            task_id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_title TEXT NOT NULL,
            task_description TEXT,
            related_event_id INTEGER REFERENCES events(event_id),
            due_date DATE,
            priority TEXT DEFAULT 'Medium',
            status TEXT DEFAULT 'Not Started',
            assigned_to TEXT DEFAULT 'Coordinator',
            completed_date DATE,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS feedback (
            feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER REFERENCES events(event_id),
            participant_name TEXT,
            feedback_text TEXT,
            rating INTEGER,
            submitted_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS reports (
            report_id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_type TEXT,
            report_name TEXT,
            generated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            file_path TEXT,
            notes TEXT
        );
    """)
    conn.commit()
    conn.close()

# ── Password Hashing ─────────────────────────────────────────────────────────

_PBKDF2_ITERATIONS = 600_000

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return salt.hex() + ":" + dk.hex()

def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, dk_hex = stored_hash.split(":")
        salt = bytes.fromhex(salt_hex)
        # Try current iteration count first, then legacy counts
        for iters in (_PBKDF2_ITERATIONS, 260_000, 100_000):
            dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iters)
            if hmac.compare_digest(dk.hex(), dk_hex):
                return True
        return False
    except Exception:
        return False

# ── Users ─────────────────────────────────────────────────────────────────────

def init_users():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('coordinator','facilitator','host','cdfa','nhh')),
            linked_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # Seed default users if table is empty
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count == 0:
        _chars = string.ascii_letters + string.digits
        _gen = lambda: ''.join(secrets.choice(_chars) for _ in range(16))
        defaults = [
            ("coordinator", _gen(), "coordinator"),
            ("nhh",         _gen(), "nhh"),
            ("cdfa",        _gen(), "cdfa"),
        ]
        for uname, pwd, role in defaults:
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?,?,?)",
                (uname, hash_password(pwd), role))
        import logging
        logging.warning(
            "Default users seeded with random passwords. "
            "Set passwords via the database or redeploy with pre-configured users."
        )
    conn.commit()
    conn.close()

def get_user_by_username(username):
    with _safe_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        return dict(row) if row else None

def create_user(username, password, role, linked_id=None):
    with _safe_conn() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, linked_id) VALUES (?,?,?,?)",
            (username, hash_password(password), role, linked_id))
        conn.commit()

def username_exists(username):
    with _safe_conn() as conn:
        row = conn.execute("SELECT user_id FROM users WHERE username=?", (username,)).fetchone()
        return row is not None

# ── Hosts ──────────────────────────────────────────────────────────────────────

def get_all_hosts():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM hosts ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_host(host_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM hosts WHERE host_id=?", (host_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def add_host(data):
    conn = get_connection()
    conn.execute("""
        INSERT INTO hosts (name,venue_name,address,city,state,zip_code,
            contact_person,email,phone,check_payable_to,payment_amount,payment_status,notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (data["name"], data.get("venue_name"), data.get("address"), data.get("city"),
          data.get("state","NH"), data.get("zip_code"), data.get("contact_person"),
          data.get("email"), data.get("phone"), data.get("check_payable_to"),
          data.get("payment_amount",0), data.get("payment_status","Pending"), data.get("notes")))
    conn.commit(); conn.close()

def update_host(host_id, data):
    conn = get_connection()
    conn.execute("""
        UPDATE hosts SET name=?,venue_name=?,address=?,city=?,state=?,zip_code=?,
            contact_person=?,email=?,phone=?,check_payable_to=?,payment_amount=?,
            payment_status=?,payment_date=?,notes=?,updated_at=CURRENT_TIMESTAMP
        WHERE host_id=?
    """, (data["name"], data.get("venue_name"), data.get("address"), data.get("city"),
          data.get("state","NH"), data.get("zip_code"), data.get("contact_person"),
          data.get("email"), data.get("phone"), data.get("check_payable_to"),
          data.get("payment_amount",0), data.get("payment_status"), data.get("payment_date"),
          data.get("notes"), host_id))
    conn.commit(); conn.close()

def delete_host(host_id):
    conn = get_connection()
    conn.execute("DELETE FROM hosts WHERE host_id=?", (host_id,))
    conn.commit(); conn.close()

def get_host_events(host_id):
    conn = get_connection()
    rows = conn.execute("""
        SELECT e.*, h.name as host_name FROM events e
        LEFT JOIN hosts h ON e.host_id=h.host_id
        WHERE e.host_id=? ORDER BY e.event_date DESC
    """, (host_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── Facilitators ───────────────────────────────────────────────────────────────

def get_all_facilitators():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM facilitators ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_facilitator(fac_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM facilitators WHERE facilitator_id=?", (fac_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def add_facilitator(data):
    conn = get_connection()
    conn.execute("""
        INSERT INTO facilitators (name,email,phone,address,city,state,zip_code,
            check_payable_to,payment_amount,payment_status,specialization,notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (data["name"], data.get("email"), data.get("phone"),
          data.get("address"), data.get("city"), data.get("state","NH"),
          data.get("zip_code"), data.get("check_payable_to"),
          data.get("payment_amount",0), data.get("payment_status","Pending"),
          data.get("specialization"), data.get("notes")))
    conn.commit(); conn.close()

def update_facilitator(fac_id, data):
    conn = get_connection()
    conn.execute("""
        UPDATE facilitators SET name=?,email=?,phone=?,address=?,city=?,state=?,zip_code=?,
            check_payable_to=?,payment_amount=?,payment_status=?,payment_date=?,specialization=?,
            notes=?,updated_at=CURRENT_TIMESTAMP
        WHERE facilitator_id=?
    """, (data["name"], data.get("email"), data.get("phone"),
          data.get("address"), data.get("city"), data.get("state","NH"), data.get("zip_code"),
          data.get("check_payable_to"),
          data.get("payment_amount",0), data.get("payment_status"), data.get("payment_date"),
          data.get("specialization"), data.get("notes"), fac_id))
    conn.commit(); conn.close()

def delete_facilitator(fac_id):
    conn = get_connection()
    conn.execute("DELETE FROM facilitators WHERE facilitator_id=?", (fac_id,))
    conn.commit(); conn.close()

def get_facilitator_events(fac_id):
    conn = get_connection()
    rows = conn.execute("""
        SELECT e.*, h.name as host_name FROM events e
        JOIN event_facilitators ef ON e.event_id=ef.event_id
        LEFT JOIN hosts h ON e.host_id=h.host_id
        WHERE ef.facilitator_id=? ORDER BY e.event_date DESC
    """, (fac_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── NHH Colleagues ─────────────────────────────────────────────────────────────

def get_all_nhh():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM nhh_colleagues ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_nhh(nhh_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM nhh_colleagues WHERE nhh_id=?", (nhh_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def add_nhh(data):
    conn = get_connection()
    conn.execute("""
        INSERT INTO nhh_colleagues (name,title,email,phone,role,notes)
        VALUES (?,?,?,?,?,?)
    """, (data["name"], data.get("title"), data.get("email"),
          data.get("phone"), data.get("role"), data.get("notes")))
    conn.commit(); conn.close()

def update_nhh(nhh_id, data):
    conn = get_connection()
    conn.execute("""
        UPDATE nhh_colleagues SET name=?,title=?,email=?,phone=?,role=?,
            notes=?,updated_at=CURRENT_TIMESTAMP
        WHERE nhh_id=?
    """, (data["name"], data.get("title"), data.get("email"),
          data.get("phone"), data.get("role"), data.get("notes"), nhh_id))
    conn.commit(); conn.close()

def delete_nhh(nhh_id):
    conn = get_connection()
    conn.execute("DELETE FROM nhh_colleagues WHERE nhh_id=?", (nhh_id,))
    conn.commit(); conn.close()

# ── CDFA Colleagues ────────────────────────────────────────────────────────────

def get_all_cdfa():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM cdfa_colleagues ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_cdfa(cdfa_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM cdfa_colleagues WHERE cdfa_id=?", (cdfa_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def add_cdfa(data):
    conn = get_connection()
    conn.execute("""
        INSERT INTO cdfa_colleagues (name,title,email,phone,role,notes)
        VALUES (?,?,?,?,?,?)
    """, (data["name"], data.get("title"), data.get("email"),
          data.get("phone"), data.get("role"), data.get("notes")))
    conn.commit(); conn.close()

def update_cdfa(cdfa_id, data):
    conn = get_connection()
    conn.execute("""
        UPDATE cdfa_colleagues SET name=?,title=?,email=?,phone=?,role=?,
            notes=?,updated_at=CURRENT_TIMESTAMP
        WHERE cdfa_id=?
    """, (data["name"], data.get("title"), data.get("email"),
          data.get("phone"), data.get("role"), data.get("notes"), cdfa_id))
    conn.commit(); conn.close()

def delete_cdfa(cdfa_id):
    conn = get_connection()
    conn.execute("DELETE FROM cdfa_colleagues WHERE cdfa_id=?", (cdfa_id,))
    conn.commit(); conn.close()

# ── Events ─────────────────────────────────────────────────────────────────────

def get_all_events():
    conn = get_connection()
    rows = conn.execute("""
        SELECT e.*, h.name as host_name, h.venue_name
        FROM events e LEFT JOIN hosts h ON e.host_id=h.host_id
        ORDER BY e.event_date DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_event(event_id):
    conn = get_connection()
    row = conn.execute("""
        SELECT e.*, h.name as host_name, h.venue_name, h.email as host_email,
               h.phone as host_phone, h.payment_status as host_payment_status,
               h.payment_amount as host_payment_amount, h.contact_person
        FROM events e LEFT JOIN hosts h ON e.host_id=h.host_id
        WHERE e.event_id=?
    """, (event_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def add_event(data, facilitator_ids=None):
    conn = get_connection()
    cur = conn.execute("""
        INSERT INTO events (event_name,event_date,event_time,host_id,venue_address,city,status)
        VALUES (?,?,?,?,?,?,?)
    """, (data["event_name"], data["event_date"], data.get("event_time"),
          data.get("host_id"), data.get("venue_address"), data.get("city"),
          data.get("status","Scheduled")))
    event_id = cur.lastrowid
    if facilitator_ids:
        for fid in facilitator_ids:
            conn.execute("INSERT INTO event_facilitators (event_id,facilitator_id) VALUES (?,?)",
                         (event_id, fid))
    conn.commit(); conn.close()
    return event_id

def update_event(event_id, data, facilitator_ids=None):
    conn = get_connection()
    conn.execute("""
        UPDATE events SET event_name=?,event_date=?,event_time=?,host_id=?,
            venue_address=?,city=?,status=?,attendance_count=?,
            attendance_confirmed=?,event_summary=?,updated_at=CURRENT_TIMESTAMP
        WHERE event_id=?
    """, (data["event_name"], data["event_date"], data.get("event_time"),
          data.get("host_id"), data.get("venue_address"), data.get("city"),
          data.get("status"), data.get("attendance_count"),
          1 if data.get("attendance_confirmed") else 0,
          data.get("event_summary"), event_id))
    if facilitator_ids is not None:
        conn.execute("DELETE FROM event_facilitators WHERE event_id=?", (event_id,))
        for fid in facilitator_ids:
            conn.execute("INSERT INTO event_facilitators (event_id,facilitator_id) VALUES (?,?)",
                         (event_id, fid))
    conn.commit(); conn.close()

def delete_event(event_id):
    conn = get_connection()
    conn.execute("DELETE FROM event_facilitators WHERE event_id=?", (event_id,))
    conn.execute("DELETE FROM events WHERE event_id=?", (event_id,))
    conn.commit(); conn.close()

def get_event_facilitators(event_id):
    conn = get_connection()
    rows = conn.execute("""
        SELECT f.* FROM facilitators f
        JOIN event_facilitators ef ON f.facilitator_id=ef.facilitator_id
        WHERE ef.event_id=?
    """, (event_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_upcoming_events(days=30):
    from datetime import date, timedelta
    today  = date.today().isoformat()
    future = (date.today() + timedelta(days=days)).isoformat()
    conn   = get_connection()
    rows   = conn.execute("""
        SELECT e.*, h.name as host_name FROM events e
        LEFT JOIN hosts h ON e.host_id=h.host_id
        WHERE e.event_date BETWEEN ? AND ?
        AND e.status='Scheduled' ORDER BY e.event_date
    """, (today, future)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── Communications ─────────────────────────────────────────────────────────────

def get_all_communications():
    conn = get_connection()
    rows = conn.execute("""
        SELECT c.*, e.event_name FROM communications c
        LEFT JOIN events e ON c.event_id=e.event_id
        ORDER BY c.sent_date DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_event_communications(event_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM communications WHERE event_id=? ORDER BY sent_date DESC", (event_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_communication(data):
    conn = get_connection()
    conn.execute("""
        INSERT INTO communications (recipient_type,recipient_id,event_id,
            communication_type,subject,body,sent_by,notes)
        VALUES (?,?,?,?,?,?,?,?)
    """, (data.get("recipient_type"), data.get("recipient_id"), data.get("event_id"),
          data.get("communication_type"), data.get("subject"), data.get("body"),
          data.get("sent_by","Coordinator"), data.get("notes")))
    conn.commit(); conn.close()

# ── Tasks ──────────────────────────────────────────────────────────────────────

def get_all_tasks():
    conn = get_connection()
    rows = conn.execute("""
        SELECT t.*, e.event_name FROM tasks t
        LEFT JOIN events e ON t.related_event_id=e.event_id
        ORDER BY t.due_date
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_task(data):
    conn = get_connection()
    conn.execute("""
        INSERT INTO tasks (task_title,task_description,related_event_id,due_date,
            priority,status,assigned_to,notes)
        VALUES (?,?,?,?,?,?,?,?)
    """, (data["task_title"], data.get("task_description"), data.get("related_event_id"),
          data.get("due_date"), data.get("priority","Medium"),
          data.get("status","Not Started"), data.get("assigned_to","Coordinator"),
          data.get("notes")))
    conn.commit(); conn.close()

def update_task(task_id, data):
    completed_date = data.get("completed_date")
    if data.get("status") == "Completed" and not completed_date:
        completed_date = datetime.now().date().isoformat()
    conn = get_connection()
    conn.execute("""
        UPDATE tasks SET task_title=?,task_description=?,related_event_id=?,due_date=?,
            priority=?,status=?,assigned_to=?,completed_date=?,notes=?
        WHERE task_id=?
    """, (data["task_title"], data.get("task_description"), data.get("related_event_id"),
          data.get("due_date"), data.get("priority"), data.get("status"),
          data.get("assigned_to"), completed_date, data.get("notes"), task_id))
    conn.commit(); conn.close()

def delete_task(task_id):
    conn = get_connection()
    conn.execute("DELETE FROM tasks WHERE task_id=?", (task_id,))
    conn.commit(); conn.close()

def get_overdue_tasks():
    conn = get_connection()
    rows = conn.execute("""
        SELECT t.*, e.event_name FROM tasks t
        LEFT JOIN events e ON t.related_event_id=e.event_id
        WHERE t.due_date < date('now') AND t.status NOT IN ('Completed')
        ORDER BY t.due_date
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── Feedback ───────────────────────────────────────────────────────────────────

def get_event_feedback(event_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM feedback WHERE event_id=? ORDER BY submitted_date DESC", (event_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_feedback(data):
    conn = get_connection()
    conn.execute("""
        INSERT INTO feedback (event_id,participant_name,feedback_text,rating)
        VALUES (?,?,?,?)
    """, (data["event_id"], data.get("participant_name"),
          data.get("feedback_text"), data.get("rating")))
    conn.commit(); conn.close()

def get_all_feedback():
    conn = get_connection()
    rows = conn.execute("""
        SELECT f.*, e.event_name FROM feedback f
        LEFT JOIN events e ON f.event_id=e.event_id
        ORDER BY f.submitted_date DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── Reports ────────────────────────────────────────────────────────────────────

def log_report(data):
    conn = get_connection()
    conn.execute("""
        INSERT INTO reports (report_type,report_name,file_path,notes)
        VALUES (?,?,?,?)
    """, (data.get("report_type"), data.get("report_name"),
          data.get("file_path"), data.get("notes")))
    conn.commit(); conn.close()

def get_all_reports():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM reports ORDER BY generated_date DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── Dashboard Stats ────────────────────────────────────────────────────────────

def get_dashboard_stats():
    conn = get_connection()
    stats = {}
    stats["total_events"]       = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    stats["scheduled"]          = conn.execute("SELECT COUNT(*) FROM events WHERE status='Scheduled'").fetchone()[0]
    stats["completed"]          = conn.execute("SELECT COUNT(*) FROM events WHERE status='Completed'").fetchone()[0]
    stats["cancelled"]          = conn.execute("SELECT COUNT(*) FROM events WHERE status='Cancelled'").fetchone()[0]
    stats["total_hosts"]        = conn.execute("SELECT COUNT(*) FROM hosts").fetchone()[0]
    stats["total_facilitators"] = conn.execute("SELECT COUNT(*) FROM facilitators").fetchone()[0]
    stats["total_nhh"]          = conn.execute("SELECT COUNT(*) FROM nhh_colleagues").fetchone()[0]
    stats["total_cdfa"]         = conn.execute("SELECT COUNT(*) FROM cdfa_colleagues").fetchone()[0]
    # Only facilitators are paid — hosts are not in payment tracking
    pf = conn.execute("SELECT COUNT(*), COALESCE(SUM(payment_amount),0) FROM facilitators WHERE payment_status IN ('Pending','Approved','Paid')").fetchone()
    stats["pending_payment_count"] = pf[0]
    stats["pending_payment_total"] = pf[1]
    stats["overdue_tasks"] = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE due_date < date('now') AND status NOT IN ('Completed')"
    ).fetchone()[0]
    conn.close()
    return stats

# ── Activity Log ───────────────────────────────────────────────────────────────

def log_activity(action: str, details: str, user: str = "Coordinator"):
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            details TEXT,
            user TEXT DEFAULT 'Coordinator',
            logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute(
        "INSERT INTO activity_log (action, details, user) VALUES (?,?,?)",
        (action, details, user)
    )
    conn.commit(); conn.close()

def get_activity_log(limit=50):
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT * FROM activity_log ORDER BY logged_at DESC LIMIT ?
        """, (limit,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        conn.close()
        return []

def init_activity_log():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            details TEXT,
            user TEXT DEFAULT 'Coordinator',
            logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit(); conn.close()

# ── Notifications ──────────────────────────────────────────────────────────────

def add_notification(message: str, target_role: str = "all", event_id=None):
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            notif_id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT NOT NULL,
            target_role TEXT DEFAULT 'all',
            event_id INTEGER,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute(
        "INSERT INTO notifications (message, target_role, event_id) VALUES (?,?,?)",
        (message, target_role, event_id)
    )
    conn.commit(); conn.close()

def get_notifications(role="all", unread_only=False):
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                notif_id INTEGER PRIMARY KEY AUTOINCREMENT,
                message TEXT NOT NULL,
                target_role TEXT DEFAULT 'all',
                event_id INTEGER,
                is_read INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        q = "SELECT * FROM notifications WHERE (target_role=? OR target_role='all')"
        params = [role]
        if unread_only:
            q += " AND is_read=0"
        q += " ORDER BY created_at DESC LIMIT 30"
        rows = conn.execute(q, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        conn.close()
        return []

def mark_notifications_read(role="all"):
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE notifications SET is_read=1 WHERE target_role=? OR target_role='all'",
            (role,)
        )
        conn.commit()
    except Exception:
        pass
    conn.close()

def get_unread_count(role="all"):
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                notif_id INTEGER PRIMARY KEY AUTOINCREMENT,
                message TEXT NOT NULL,
                target_role TEXT DEFAULT 'all',
                event_id INTEGER,
                is_read INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        count = conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE (target_role=? OR target_role='all') AND is_read=0",
            (role,)
        ).fetchone()[0]
        conn.close()
        return count
    except Exception:
        conn.close()
        return 0

# ── Portal Access Control ──────────────────────────────────────────────────────

def init_mileage():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mileage_reimbursements (
            mileage_id INTEGER PRIMARY KEY AUTOINCREMENT,
            facilitator_id INTEGER,
            event_id INTEGER,
            facilitator_address TEXT,
            event_address TEXT,
            distance_miles REAL,
            round_trip_miles REAL,
            rate_per_mile REAL DEFAULT 0.725,
            reimbursement_amount REAL,
            status TEXT DEFAULT 'Pending',
            notes TEXT,
            calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (facilitator_id) REFERENCES facilitators(facilitator_id),
            FOREIGN KEY (event_id) REFERENCES events(event_id)
        )
    """)
    conn.commit()
    conn.close()


def init_portal_access():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS portal_access (
            access_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            person_type TEXT NOT NULL,  -- 'host' or 'facilitator'
            person_id   INTEGER NOT NULL,
            username    TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_active   INTEGER DEFAULT 0,  -- 0=pending, 1=approved
            granted_by  TEXT DEFAULT 'Coordinator',
            granted_at  TIMESTAMP,
            notes       TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit(); conn.close()

def get_all_portal_access():
    conn = get_connection()
    init_portal_access()
    rows = conn.execute("SELECT * FROM portal_access ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_portal_access(data):
    init_portal_access()
    with _safe_conn() as conn:
        conn.execute("""
            INSERT INTO portal_access (person_type,person_id,username,password_hash,is_active,notes)
            VALUES (?,?,?,?,?,?)
        """, (data['person_type'], data['person_id'], data['username'],
              hash_password(data['password']), data.get('is_active', 0), data.get('notes','')))
        conn.commit()

def update_portal_access(access_id, is_active):
    conn = get_connection()
    from datetime import datetime
    init_portal_access()
    conn.execute("""
        UPDATE portal_access SET is_active=?, granted_at=CURRENT_TIMESTAMP
        WHERE access_id=?
    """, (1 if is_active else 0, access_id))
    conn.commit(); conn.close()

def delete_portal_access(access_id):
    conn = get_connection()
    init_portal_access()
    conn.execute("DELETE FROM portal_access WHERE access_id=?", (access_id,))
    conn.commit(); conn.close()

def check_portal_login(username, password):
    """Returns portal user info if credentials match and access is active."""
    init_portal_access()
    with _safe_conn() as conn:
        row = conn.execute("""
            SELECT pa.*,
                   CASE WHEN pa.person_type='host' THEN h.name ELSE f.name END as person_name,
                   CASE WHEN pa.person_type='host' THEN h.email ELSE f.email END as person_email
            FROM portal_access pa
            LEFT JOIN hosts h ON pa.person_type='host' AND pa.person_id=h.host_id
            LEFT JOIN facilitators f ON pa.person_type='facilitator' AND pa.person_id=f.facilitator_id
            WHERE pa.username=? AND pa.is_active=1
        """, (username,)).fetchone()
        if row and verify_password(password, dict(row).get("password_hash", "")):
            return dict(row)
        return None

# ── Messages (Host/Facilitator → Coordinator) ──────────────────────────────────

def init_messages():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            message_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_type  TEXT NOT NULL,  -- 'host','facilitator','coordinator'
            sender_id    INTEGER,
            sender_name  TEXT,
            event_id     INTEGER REFERENCES events(event_id),
            category     TEXT,  -- 'General','Attendance','Payment','Delay','Problem','Information','Feedback'
            subject      TEXT,
            body         TEXT NOT NULL,
            is_read      INTEGER DEFAULT 0,
            replied_at   TIMESTAMP,
            reply_body   TEXT,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit(); conn.close()

def send_message(data):
    conn = get_connection()
    init_messages()
    conn.execute("""
        INSERT INTO messages (sender_type,sender_id,sender_name,event_id,category,subject,body)
        VALUES (?,?,?,?,?,?,?)
    """, (data.get('sender_type'), data.get('sender_id'), data.get('sender_name'),
          data.get('event_id'), data.get('category','General'),
          data.get('subject',''), data.get('body','')))
    conn.commit(); conn.close()

def get_all_messages(unread_only=False):
    conn = get_connection()
    init_messages()
    q = """
        SELECT m.*, e.event_name FROM messages m
        LEFT JOIN events e ON m.event_id=e.event_id
        ORDER BY m.created_at DESC
    """
    rows = conn.execute(q).fetchall()
    conn.close()
    result = [dict(r) for r in rows]
    if unread_only:
        result = [r for r in result if not r.get('is_read')]
    return result

def mark_message_read(message_id):
    conn = get_connection()
    init_messages()
    conn.execute("UPDATE messages SET is_read=1 WHERE message_id=?", (message_id,))
    conn.commit(); conn.close()

def reply_to_message(message_id, reply_body):
    conn = get_connection()
    init_messages()
    conn.execute("""
        UPDATE messages SET reply_body=?, replied_at=CURRENT_TIMESTAMP, is_read=1
        WHERE message_id=?
    """, (reply_body, message_id))
    conn.commit(); conn.close()

def get_messages_for_person(sender_type, sender_id):
    conn = get_connection()
    init_messages()
    if sender_id is None:
        rows = conn.execute("""
            SELECT m.*, e.event_name FROM messages m
            LEFT JOIN events e ON m.event_id=e.event_id
            WHERE m.sender_type=? AND m.sender_id IS NULL
            ORDER BY m.created_at DESC
        """, (sender_type,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT m.*, e.event_name FROM messages m
            LEFT JOIN events e ON m.event_id=e.event_id
            WHERE m.sender_type=? AND m.sender_id=?
            ORDER BY m.created_at DESC
        """, (sender_type, sender_id)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_unread_message_count():
    conn = get_connection()
    init_messages()
    count = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE is_read=0 AND sender_type != 'coordinator'"
    ).fetchone()[0]
    conn.close()
    return count


def add_mileage_reimbursement(data):
    conn = get_connection()
    conn.execute("""
        INSERT INTO mileage_reimbursements
        (facilitator_id, event_id, facilitator_address, event_address,
         distance_miles, round_trip_miles, rate_per_mile, reimbursement_amount, status, notes)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (data["facilitator_id"], data.get("event_id"),
          data["facilitator_address"], data["event_address"],
          data["distance_miles"], data["round_trip_miles"],
          data.get("rate_per_mile", 0.725), data["reimbursement_amount"],
          data.get("status", "Pending"), data.get("notes", "")))
    conn.commit()
    conn.close()


def get_mileage_reimbursements(facilitator_id=None, event_id=None):
    conn = get_connection()
    query = """
        SELECT m.*, f.name as facilitator_name, e.event_name
        FROM mileage_reimbursements m
        LEFT JOIN facilitators f ON m.facilitator_id = f.facilitator_id
        LEFT JOIN events e ON m.event_id = e.event_id
        WHERE 1=1
    """
    params = []
    if facilitator_id:
        query += " AND m.facilitator_id = ?"
        params.append(facilitator_id)
    if event_id:
        query += " AND m.event_id = ?"
        params.append(event_id)
    query += " ORDER BY m.calculated_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_mileage_status(mileage_id, status):
    conn = get_connection()
    conn.execute("UPDATE mileage_reimbursements SET status=? WHERE mileage_id=?",
                 (status, mileage_id))
    conn.commit()
    conn.close()


def delete_mileage_reimbursement(mileage_id):
    conn = get_connection()
    conn.execute("DELETE FROM mileage_reimbursements WHERE mileage_id=?", (mileage_id,))
    conn.commit()
    conn.close()


def get_mileage_total_pending():
    conn = get_connection()
    row = conn.execute("""
        SELECT COALESCE(SUM(reimbursement_amount),0)
        FROM mileage_reimbursements WHERE status='Pending'
    """).fetchone()
    conn.close()
    return row[0]


# ── PostgreSQL override ───────────────────────────────────────────────────────
# When DATABASE_URL is configured (Supabase / Streamlit Cloud), swap every
# function above with its psycopg2 equivalent.  Local dev keeps SQLite.
try:
    import streamlit as _st
    if _st.secrets.get("DATABASE_URL"):
        import utils.supabase_db as _pg
        import inspect as _inspect
        for _name, _obj in _inspect.getmembers(_pg):
            if not _name.startswith("_") and callable(_obj):
                globals()[_name] = _obj
except Exception as _e:
    import logging as _logging
    _logging.warning("Supabase override failed, falling back to SQLite: %s", _e)
