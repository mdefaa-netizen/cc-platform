"""
PostgreSQL backend for Supabase deployment.
Mirrors every public function in database.py but uses psycopg2.

Activated automatically when DATABASE_URL is present in st.secrets.
"""

import psycopg2
import psycopg2.extras
import streamlit as st
from datetime import datetime, date, timedelta
import hashlib, os, secrets, string

DB_PATH = "supabase"  # Sentinel so any code that prints DB_PATH still works


def get_connection():
    conn = psycopg2.connect(st.secrets["DATABASE_URL"])
    return conn


def _fetchall(conn, query, params=None):
    """Execute a SELECT and return list[dict], then close the connection."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, params or ())
        rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _fetchone(conn, query, params=None):
    """Execute a SELECT and return a single dict or None, then close."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, params or ())
        row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def _execute(conn, query, params=None):
    """Execute a write statement, commit, and close."""
    with conn.cursor() as cur:
        cur.execute(query, params or ())
    conn.commit()
    conn.close()


# ── Password Hashing ─────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260_000)
    return salt.hex() + ":" + dk.hex()


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, dk_hex = stored_hash.split(":")
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260_000)
        return dk.hex() == dk_hex
    except Exception:
        return False


# ── Schema Initialisation ─────────────────────────────────────────────────────

def init_db():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS hosts (
                host_id SERIAL PRIMARY KEY,
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
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS facilitators (
                facilitator_id SERIAL PRIMARY KEY,
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
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS nhh_colleagues (
                nhh_id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                title TEXT,
                email TEXT,
                phone TEXT,
                role TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cdfa_colleagues (
                cdfa_id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                title TEXT,
                email TEXT,
                phone TEXT,
                role TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS events (
                event_id SERIAL PRIMARY KEY,
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
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS event_facilitators (
                event_facilitator_id SERIAL PRIMARY KEY,
                event_id INTEGER REFERENCES events(event_id),
                facilitator_id INTEGER REFERENCES facilitators(facilitator_id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS communications (
                communication_id SERIAL PRIMARY KEY,
                recipient_type TEXT,
                recipient_id INTEGER,
                event_id INTEGER REFERENCES events(event_id),
                communication_type TEXT,
                subject TEXT,
                body TEXT,
                sent_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sent_by TEXT DEFAULT 'Coordinator',
                notes TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id SERIAL PRIMARY KEY,
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
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                feedback_id SERIAL PRIMARY KEY,
                event_id INTEGER REFERENCES events(event_id),
                participant_name TEXT,
                feedback_text TEXT,
                rating INTEGER,
                submitted_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                report_id SERIAL PRIMARY KEY,
                report_type TEXT,
                report_name TEXT,
                generated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                file_path TEXT,
                notes TEXT
            )
        """)
    conn.commit()
    conn.close()


def init_users():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('coordinator','facilitator','host','cdfa','nhh')),
                linked_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Seed default users if table is empty
        cur.execute("SELECT COUNT(*) FROM users")
        if cur.fetchone()[0] == 0:
            defaults = [
                ("coordinator", "nhhumanities2025", "coordinator"),
                ("nhh",         "nhh2025",          "nhh"),
                ("cdfa",        "cdfa2025",         "cdfa"),
            ]
            for uname, pwd, role in defaults:
                cur.execute(
                    "INSERT INTO users (username, password_hash, role) VALUES (%s,%s,%s)",
                    (uname, hash_password(pwd), role))
    conn.commit()
    conn.close()


def get_user_by_username(username):
    conn = get_connection()
    return _fetchone(conn, "SELECT * FROM users WHERE username=%s", (username,))


def create_user(username, password, role, linked_id=None):
    conn = get_connection()
    _execute(conn, """
        INSERT INTO users (username, password_hash, role, linked_id)
        VALUES (%s,%s,%s,%s)
    """, (username, hash_password(password), role, linked_id))


def username_exists(username):
    conn = get_connection()
    row = _fetchone(conn, "SELECT user_id FROM users WHERE username=%s", (username,))
    return row is not None


def init_mileage():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS mileage_reimbursements (
                mileage_id SERIAL PRIMARY KEY,
                facilitator_id INTEGER REFERENCES facilitators(facilitator_id),
                event_id INTEGER REFERENCES events(event_id),
                facilitator_address TEXT,
                event_address TEXT,
                distance_miles REAL,
                round_trip_miles REAL,
                rate_per_mile REAL DEFAULT 0.725,
                reimbursement_amount REAL,
                status TEXT DEFAULT 'Pending',
                notes TEXT,
                calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    conn.commit()
    conn.close()


def init_portal_access():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS portal_access (
                access_id   SERIAL PRIMARY KEY,
                person_type TEXT NOT NULL,
                person_id   INTEGER NOT NULL,
                username    TEXT UNIQUE NOT NULL,
                password    TEXT NOT NULL,
                is_active   INTEGER DEFAULT 0,
                granted_by  TEXT DEFAULT 'Coordinator',
                granted_at  TIMESTAMP,
                notes       TEXT,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    conn.commit()
    conn.close()


def init_activity_log():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                log_id SERIAL PRIMARY KEY,
                action TEXT NOT NULL,
                details TEXT,
                "user" TEXT DEFAULT 'Coordinator',
                logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    conn.commit()
    conn.close()


def init_messages():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                message_id   SERIAL PRIMARY KEY,
                sender_type  TEXT NOT NULL,
                sender_id    INTEGER,
                sender_name  TEXT,
                event_id     INTEGER REFERENCES events(event_id),
                category     TEXT,
                subject      TEXT,
                body         TEXT NOT NULL,
                is_read      INTEGER DEFAULT 0,
                replied_at   TIMESTAMP,
                reply_body   TEXT,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    conn.commit()
    conn.close()


def _ensure_notifications():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                notif_id SERIAL PRIMARY KEY,
                message TEXT NOT NULL,
                target_role TEXT DEFAULT 'all',
                event_id INTEGER,
                is_read INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    conn.commit()
    conn.close()


# ── Hosts ─────────────────────────────────────────────────────────────────────

def get_all_hosts():
    conn = get_connection()
    return _fetchall(conn, "SELECT * FROM hosts ORDER BY name")


def get_host(host_id):
    conn = get_connection()
    return _fetchone(conn, "SELECT * FROM hosts WHERE host_id=%s", (host_id,))


def add_host(data):
    conn = get_connection()
    _execute(conn, """
        INSERT INTO hosts (name,venue_name,address,city,state,zip_code,
            contact_person,email,phone,check_payable_to,payment_amount,payment_status,notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (data["name"], data.get("venue_name"), data.get("address"), data.get("city"),
          data.get("state", "NH"), data.get("zip_code"), data.get("contact_person"),
          data.get("email"), data.get("phone"), data.get("check_payable_to"),
          data.get("payment_amount", 0), data.get("payment_status", "Pending"),
          data.get("notes")))


def update_host(host_id, data):
    conn = get_connection()
    _execute(conn, """
        UPDATE hosts SET name=%s,venue_name=%s,address=%s,city=%s,state=%s,zip_code=%s,
            contact_person=%s,email=%s,phone=%s,check_payable_to=%s,payment_amount=%s,
            payment_status=%s,payment_date=%s,notes=%s,updated_at=CURRENT_TIMESTAMP
        WHERE host_id=%s
    """, (data["name"], data.get("venue_name"), data.get("address"), data.get("city"),
          data.get("state", "NH"), data.get("zip_code"), data.get("contact_person"),
          data.get("email"), data.get("phone"), data.get("check_payable_to"),
          data.get("payment_amount", 0), data.get("payment_status"),
          data.get("payment_date"), data.get("notes"), host_id))


def delete_host(host_id):
    conn = get_connection()
    _execute(conn, "DELETE FROM hosts WHERE host_id=%s", (host_id,))


def get_host_events(host_id):
    conn = get_connection()
    return _fetchall(conn, """
        SELECT e.*, h.name as host_name FROM events e
        LEFT JOIN hosts h ON e.host_id=h.host_id
        WHERE e.host_id=%s ORDER BY e.event_date DESC
    """, (host_id,))


# ── Facilitators ──────────────────────────────────────────────────────────────

def get_all_facilitators():
    conn = get_connection()
    return _fetchall(conn, "SELECT * FROM facilitators ORDER BY name")


def get_facilitator(fac_id):
    conn = get_connection()
    return _fetchone(conn, "SELECT * FROM facilitators WHERE facilitator_id=%s", (fac_id,))


def add_facilitator(data):
    conn = get_connection()
    _execute(conn, """
        INSERT INTO facilitators (name,email,phone,address,city,state,zip_code,
            check_payable_to,payment_amount,payment_status,specialization,notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (data["name"], data.get("email"), data.get("phone"),
          data.get("address"), data.get("city"), data.get("state", "NH"),
          data.get("zip_code"), data.get("check_payable_to"),
          data.get("payment_amount", 0), data.get("payment_status", "Pending"),
          data.get("specialization"), data.get("notes")))


def update_facilitator(fac_id, data):
    conn = get_connection()
    _execute(conn, """
        UPDATE facilitators SET name=%s,email=%s,phone=%s,address=%s,city=%s,state=%s,zip_code=%s,
            check_payable_to=%s,payment_amount=%s,payment_status=%s,payment_date=%s,specialization=%s,
            notes=%s,updated_at=CURRENT_TIMESTAMP
        WHERE facilitator_id=%s
    """, (data["name"], data.get("email"), data.get("phone"),
          data.get("address"), data.get("city"), data.get("state", "NH"), data.get("zip_code"),
          data.get("check_payable_to"), data.get("payment_amount", 0),
          data.get("payment_status"), data.get("payment_date"),
          data.get("specialization"), data.get("notes"), fac_id))


def delete_facilitator(fac_id):
    conn = get_connection()
    _execute(conn, "DELETE FROM facilitators WHERE facilitator_id=%s", (fac_id,))


def get_facilitator_events(fac_id):
    conn = get_connection()
    return _fetchall(conn, """
        SELECT e.*, h.name as host_name FROM events e
        JOIN event_facilitators ef ON e.event_id=ef.event_id
        LEFT JOIN hosts h ON e.host_id=h.host_id
        WHERE ef.facilitator_id=%s ORDER BY e.event_date DESC
    """, (fac_id,))


# ── NHH Colleagues ────────────────────────────────────────────────────────────

def get_all_nhh():
    conn = get_connection()
    return _fetchall(conn, "SELECT * FROM nhh_colleagues ORDER BY name")


def get_nhh(nhh_id):
    conn = get_connection()
    return _fetchone(conn, "SELECT * FROM nhh_colleagues WHERE nhh_id=%s", (nhh_id,))


def add_nhh(data):
    conn = get_connection()
    _execute(conn, """
        INSERT INTO nhh_colleagues (name,title,email,phone,role,notes)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, (data["name"], data.get("title"), data.get("email"),
          data.get("phone"), data.get("role"), data.get("notes")))


def update_nhh(nhh_id, data):
    conn = get_connection()
    _execute(conn, """
        UPDATE nhh_colleagues SET name=%s,title=%s,email=%s,phone=%s,role=%s,
            notes=%s,updated_at=CURRENT_TIMESTAMP
        WHERE nhh_id=%s
    """, (data["name"], data.get("title"), data.get("email"),
          data.get("phone"), data.get("role"), data.get("notes"), nhh_id))


def delete_nhh(nhh_id):
    conn = get_connection()
    _execute(conn, "DELETE FROM nhh_colleagues WHERE nhh_id=%s", (nhh_id,))


# ── CDFA Colleagues ───────────────────────────────────────────────────────────

def get_all_cdfa():
    conn = get_connection()
    return _fetchall(conn, "SELECT * FROM cdfa_colleagues ORDER BY name")


def get_cdfa(cdfa_id):
    conn = get_connection()
    return _fetchone(conn, "SELECT * FROM cdfa_colleagues WHERE cdfa_id=%s", (cdfa_id,))


def add_cdfa(data):
    conn = get_connection()
    _execute(conn, """
        INSERT INTO cdfa_colleagues (name,title,email,phone,role,notes)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, (data["name"], data.get("title"), data.get("email"),
          data.get("phone"), data.get("role"), data.get("notes")))


def update_cdfa(cdfa_id, data):
    conn = get_connection()
    _execute(conn, """
        UPDATE cdfa_colleagues SET name=%s,title=%s,email=%s,phone=%s,role=%s,
            notes=%s,updated_at=CURRENT_TIMESTAMP
        WHERE cdfa_id=%s
    """, (data["name"], data.get("title"), data.get("email"),
          data.get("phone"), data.get("role"), data.get("notes"), cdfa_id))


def delete_cdfa(cdfa_id):
    conn = get_connection()
    _execute(conn, "DELETE FROM cdfa_colleagues WHERE cdfa_id=%s", (cdfa_id,))


# ── Events ────────────────────────────────────────────────────────────────────

def get_all_events():
    conn = get_connection()
    return _fetchall(conn, """
        SELECT e.*, h.name as host_name, h.venue_name
        FROM events e LEFT JOIN hosts h ON e.host_id=h.host_id
        ORDER BY e.event_date DESC
    """)


def get_event(event_id):
    conn = get_connection()
    return _fetchone(conn, """
        SELECT e.*, h.name as host_name, h.venue_name, h.email as host_email,
               h.phone as host_phone, h.payment_status as host_payment_status,
               h.payment_amount as host_payment_amount, h.contact_person
        FROM events e LEFT JOIN hosts h ON e.host_id=h.host_id
        WHERE e.event_id=%s
    """, (event_id,))


def add_event(data, facilitator_ids=None):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO events (event_name,event_date,event_time,host_id,venue_address,city,status)
            VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING event_id
        """, (data["event_name"], data["event_date"], data.get("event_time"),
              data.get("host_id"), data.get("venue_address"), data.get("city"),
              data.get("status", "Scheduled")))
        event_id = cur.fetchone()[0]
        if facilitator_ids:
            for fid in facilitator_ids:
                cur.execute(
                    "INSERT INTO event_facilitators (event_id,facilitator_id) VALUES (%s,%s)",
                    (event_id, fid))
    conn.commit()
    conn.close()
    return event_id


def update_event(event_id, data, facilitator_ids=None):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE events SET event_name=%s,event_date=%s,event_time=%s,host_id=%s,
                venue_address=%s,city=%s,status=%s,attendance_count=%s,
                attendance_confirmed=%s,event_summary=%s,updated_at=CURRENT_TIMESTAMP
            WHERE event_id=%s
        """, (data["event_name"], data["event_date"], data.get("event_time"),
              data.get("host_id"), data.get("venue_address"), data.get("city"),
              data.get("status"), data.get("attendance_count"),
              1 if data.get("attendance_confirmed") else 0,
              data.get("event_summary"), event_id))
        if facilitator_ids is not None:
            cur.execute("DELETE FROM event_facilitators WHERE event_id=%s", (event_id,))
            for fid in facilitator_ids:
                cur.execute(
                    "INSERT INTO event_facilitators (event_id,facilitator_id) VALUES (%s,%s)",
                    (event_id, fid))
    conn.commit()
    conn.close()


def delete_event(event_id):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM event_facilitators WHERE event_id=%s", (event_id,))
        cur.execute("DELETE FROM events WHERE event_id=%s", (event_id,))
    conn.commit()
    conn.close()


def get_event_facilitators(event_id):
    conn = get_connection()
    return _fetchall(conn, """
        SELECT f.* FROM facilitators f
        JOIN event_facilitators ef ON f.facilitator_id=ef.facilitator_id
        WHERE ef.event_id=%s
    """, (event_id,))


def get_upcoming_events(days=30):
    today = date.today().isoformat()
    future = (date.today() + timedelta(days=days)).isoformat()
    conn = get_connection()
    return _fetchall(conn, """
        SELECT e.*, h.name as host_name FROM events e
        LEFT JOIN hosts h ON e.host_id=h.host_id
        WHERE e.event_date BETWEEN %s AND %s
        AND e.status='Scheduled' ORDER BY e.event_date
    """, (today, future))


# ── Communications ────────────────────────────────────────────────────────────

def get_all_communications():
    conn = get_connection()
    return _fetchall(conn, """
        SELECT c.*, e.event_name FROM communications c
        LEFT JOIN events e ON c.event_id=e.event_id
        ORDER BY c.sent_date DESC
    """)


def get_event_communications(event_id):
    conn = get_connection()
    return _fetchall(conn, """
        SELECT * FROM communications WHERE event_id=%s ORDER BY sent_date DESC
    """, (event_id,))


def add_communication(data):
    conn = get_connection()
    _execute(conn, """
        INSERT INTO communications (recipient_type,recipient_id,event_id,
            communication_type,subject,body,sent_by,notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """, (data.get("recipient_type"), data.get("recipient_id"), data.get("event_id"),
          data.get("communication_type"), data.get("subject"), data.get("body"),
          data.get("sent_by", "Coordinator"), data.get("notes")))


# ── Tasks ─────────────────────────────────────────────────────────────────────

def get_all_tasks():
    conn = get_connection()
    return _fetchall(conn, """
        SELECT t.*, e.event_name FROM tasks t
        LEFT JOIN events e ON t.related_event_id=e.event_id
        ORDER BY t.due_date
    """)


def add_task(data):
    conn = get_connection()
    _execute(conn, """
        INSERT INTO tasks (task_title,task_description,related_event_id,due_date,
            priority,status,assigned_to,notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """, (data["task_title"], data.get("task_description"), data.get("related_event_id"),
          data.get("due_date"), data.get("priority", "Medium"),
          data.get("status", "Not Started"), data.get("assigned_to", "Coordinator"),
          data.get("notes")))


def update_task(task_id, data):
    completed_date = data.get("completed_date")
    if data.get("status") == "Completed" and not completed_date:
        completed_date = datetime.now().date().isoformat()
    conn = get_connection()
    _execute(conn, """
        UPDATE tasks SET task_title=%s,task_description=%s,related_event_id=%s,due_date=%s,
            priority=%s,status=%s,assigned_to=%s,completed_date=%s,notes=%s
        WHERE task_id=%s
    """, (data["task_title"], data.get("task_description"), data.get("related_event_id"),
          data.get("due_date"), data.get("priority"), data.get("status"),
          data.get("assigned_to"), completed_date, data.get("notes"), task_id))


def delete_task(task_id):
    conn = get_connection()
    _execute(conn, "DELETE FROM tasks WHERE task_id=%s", (task_id,))


def get_overdue_tasks():
    conn = get_connection()
    return _fetchall(conn, """
        SELECT t.*, e.event_name FROM tasks t
        LEFT JOIN events e ON t.related_event_id=e.event_id
        WHERE t.due_date < CURRENT_DATE AND t.status NOT IN ('Completed')
        ORDER BY t.due_date
    """)


# ── Feedback ──────────────────────────────────────────────────────────────────

def get_event_feedback(event_id):
    conn = get_connection()
    return _fetchall(conn, """
        SELECT * FROM feedback WHERE event_id=%s ORDER BY submitted_date DESC
    """, (event_id,))


def add_feedback(data):
    conn = get_connection()
    _execute(conn, """
        INSERT INTO feedback (event_id,participant_name,feedback_text,rating)
        VALUES (%s,%s,%s,%s)
    """, (data["event_id"], data.get("participant_name"),
          data.get("feedback_text"), data.get("rating")))


def get_all_feedback():
    conn = get_connection()
    return _fetchall(conn, """
        SELECT f.*, e.event_name FROM feedback f
        LEFT JOIN events e ON f.event_id=e.event_id
        ORDER BY f.submitted_date DESC
    """)


# ── Reports ───────────────────────────────────────────────────────────────────

def log_report(data):
    conn = get_connection()
    _execute(conn, """
        INSERT INTO reports (report_type,report_name,file_path,notes)
        VALUES (%s,%s,%s,%s)
    """, (data.get("report_type"), data.get("report_name"),
          data.get("file_path"), data.get("notes")))


def get_all_reports():
    conn = get_connection()
    return _fetchall(conn, "SELECT * FROM reports ORDER BY generated_date DESC")


# ── Dashboard Stats ───────────────────────────────────────────────────────────

def get_dashboard_stats():
    conn = get_connection()
    stats = {}
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM events")
        stats["total_events"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM events WHERE status='Scheduled'")
        stats["scheduled"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM events WHERE status='Completed'")
        stats["completed"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM events WHERE status='Cancelled'")
        stats["cancelled"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM hosts")
        stats["total_hosts"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM facilitators")
        stats["total_facilitators"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM nhh_colleagues")
        stats["total_nhh"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM cdfa_colleagues")
        stats["total_cdfa"] = cur.fetchone()[0]
        cur.execute("""
            SELECT COUNT(*), COALESCE(SUM(payment_amount),0)
            FROM facilitators WHERE payment_status IN ('Pending','Approved','Paid')
        """)
        pf = cur.fetchone()
        stats["pending_payment_count"] = pf[0]
        stats["pending_payment_total"] = pf[1]
        cur.execute("""
            SELECT COUNT(*) FROM tasks
            WHERE due_date < CURRENT_DATE AND status NOT IN ('Completed')
        """)
        stats["overdue_tasks"] = cur.fetchone()[0]
    conn.close()
    return stats


# ── Activity Log ──────────────────────────────────────────────────────────────

def log_activity(action: str, details: str, user: str = "Coordinator"):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                log_id SERIAL PRIMARY KEY,
                action TEXT NOT NULL,
                details TEXT,
                "user" TEXT DEFAULT 'Coordinator',
                logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute(
            'INSERT INTO activity_log (action, details, "user") VALUES (%s,%s,%s)',
            (action, details, user))
    conn.commit()
    conn.close()


def get_activity_log(limit=50):
    conn = get_connection()
    try:
        return _fetchall(conn, """
            SELECT * FROM activity_log ORDER BY logged_at DESC LIMIT %s
        """, (limit,))
    except Exception:
        conn.close()
        return []


# ── Notifications ─────────────────────────────────────────────────────────────

def add_notification(message: str, target_role: str = "all", event_id=None):
    _ensure_notifications()
    conn = get_connection()
    _execute(conn, """
        INSERT INTO notifications (message, target_role, event_id) VALUES (%s,%s,%s)
    """, (message, target_role, event_id))


def get_notifications(role="all", unread_only=False):
    _ensure_notifications()
    conn = get_connection()
    try:
        q = "SELECT * FROM notifications WHERE (target_role=%s OR target_role='all')"
        params = [role]
        if unread_only:
            q += " AND is_read=0"
        q += " ORDER BY created_at DESC LIMIT 30"
        return _fetchall(conn, q, params)
    except Exception:
        conn.close()
        return []


def mark_notifications_read(role="all"):
    _ensure_notifications()
    conn = get_connection()
    try:
        _execute(conn, """
            UPDATE notifications SET is_read=1
            WHERE target_role=%s OR target_role='all'
        """, (role,))
    except Exception:
        conn.close()


def get_unread_count(role="all"):
    _ensure_notifications()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM notifications
                WHERE (target_role=%s OR target_role='all') AND is_read=0
            """, (role,))
            count = cur.fetchone()[0]
        conn.close()
        return count
    except Exception:
        conn.close()
        return 0


# ── Portal Access Control ─────────────────────────────────────────────────────

def get_all_portal_access():
    init_portal_access()
    conn = get_connection()
    return _fetchall(conn, "SELECT * FROM portal_access ORDER BY created_at DESC")


def add_portal_access(data):
    init_portal_access()
    conn = get_connection()
    _execute(conn, """
        INSERT INTO portal_access (person_type,person_id,username,password,is_active,notes)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, (data['person_type'], data['person_id'], data['username'],
          data['password'], data.get('is_active', 0), data.get('notes', '')))


def update_portal_access(access_id, is_active):
    init_portal_access()
    conn = get_connection()
    _execute(conn, """
        UPDATE portal_access SET is_active=%s, granted_at=CURRENT_TIMESTAMP
        WHERE access_id=%s
    """, (1 if is_active else 0, access_id))


def delete_portal_access(access_id):
    init_portal_access()
    conn = get_connection()
    _execute(conn, "DELETE FROM portal_access WHERE access_id=%s", (access_id,))


def check_portal_login(username, password):
    init_portal_access()
    conn = get_connection()
    return _fetchone(conn, """
        SELECT pa.*,
               CASE WHEN pa.person_type='host' THEN h.name ELSE f.name END as person_name,
               CASE WHEN pa.person_type='host' THEN h.email ELSE f.email END as person_email
        FROM portal_access pa
        LEFT JOIN hosts h ON pa.person_type='host' AND pa.person_id=h.host_id
        LEFT JOIN facilitators f ON pa.person_type='facilitator' AND pa.person_id=f.facilitator_id
        WHERE pa.username=%s AND pa.password=%s AND pa.is_active=1
    """, (username, password))


# ── Messages ──────────────────────────────────────────────────────────────────

def send_message(data):
    init_messages()
    conn = get_connection()
    _execute(conn, """
        INSERT INTO messages (sender_type,sender_id,sender_name,event_id,category,subject,body)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
    """, (data.get('sender_type'), data.get('sender_id'), data.get('sender_name'),
          data.get('event_id'), data.get('category', 'General'),
          data.get('subject', ''), data.get('body', '')))


def get_all_messages(unread_only=False):
    init_messages()
    conn = get_connection()
    rows = _fetchall(conn, """
        SELECT m.*, e.event_name FROM messages m
        LEFT JOIN events e ON m.event_id=e.event_id
        ORDER BY m.created_at DESC
    """)
    if unread_only:
        rows = [r for r in rows if not r.get('is_read')]
    return rows


def mark_message_read(message_id):
    init_messages()
    conn = get_connection()
    _execute(conn, "UPDATE messages SET is_read=1 WHERE message_id=%s", (message_id,))


def reply_to_message(message_id, reply_body):
    init_messages()
    conn = get_connection()
    _execute(conn, """
        UPDATE messages SET reply_body=%s, replied_at=CURRENT_TIMESTAMP, is_read=1
        WHERE message_id=%s
    """, (reply_body, message_id))


def get_messages_for_person(sender_type, sender_id):
    init_messages()
    conn = get_connection()
    if sender_id is None:
        return _fetchall(conn, """
            SELECT m.*, e.event_name FROM messages m
            LEFT JOIN events e ON m.event_id=e.event_id
            WHERE m.sender_type=%s AND m.sender_id IS NULL
            ORDER BY m.created_at DESC
        """, (sender_type,))
    return _fetchall(conn, """
        SELECT m.*, e.event_name FROM messages m
        LEFT JOIN events e ON m.event_id=e.event_id
        WHERE m.sender_type=%s AND m.sender_id=%s
        ORDER BY m.created_at DESC
    """, (sender_type, sender_id))


def get_unread_message_count():
    init_messages()
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM messages WHERE is_read=0 AND sender_type != 'coordinator'")
        count = cur.fetchone()[0]
    conn.close()
    return count


# ── Mileage ───────────────────────────────────────────────────────────────────

def add_mileage_reimbursement(data):
    conn = get_connection()
    _execute(conn, """
        INSERT INTO mileage_reimbursements
        (facilitator_id, event_id, facilitator_address, event_address,
         distance_miles, round_trip_miles, rate_per_mile, reimbursement_amount, status, notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (data["facilitator_id"], data.get("event_id"),
          data["facilitator_address"], data["event_address"],
          data["distance_miles"], data["round_trip_miles"],
          data.get("rate_per_mile", 0.725), data["reimbursement_amount"],
          data.get("status", "Pending"), data.get("notes", "")))


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
        query += " AND m.facilitator_id = %s"
        params.append(facilitator_id)
    if event_id:
        query += " AND m.event_id = %s"
        params.append(event_id)
    query += " ORDER BY m.calculated_at DESC"
    return _fetchall(conn, query, params)


def update_mileage_status(mileage_id, status):
    conn = get_connection()
    _execute(conn, "UPDATE mileage_reimbursements SET status=%s WHERE mileage_id=%s",
             (status, mileage_id))


def delete_mileage_reimbursement(mileage_id):
    conn = get_connection()
    _execute(conn, "DELETE FROM mileage_reimbursements WHERE mileage_id=%s", (mileage_id,))


def get_mileage_total_pending():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COALESCE(SUM(reimbursement_amount),0)
            FROM mileage_reimbursements WHERE status='Pending'
        """)
        val = cur.fetchone()[0]
    conn.close()
    return val
