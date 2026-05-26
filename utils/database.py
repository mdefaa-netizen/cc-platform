import sqlite3
import os
import hashlib
import hmac
from datetime import datetime


# ── Legacy password hashing ──────────────────────────────────────────────────
# NOTE: This pbkdf2 pair is ONLY used by the separate portal_access system
# (hosts/facilitators signing in via pages/0_Portal.py via check_portal_login).
# The main RBAC users table uses bcrypt via utils/auth.py.

_PBKDF2_ITERATIONS = 600_000

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return salt.hex() + ":" + dk.hex()

def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, dk_hex = stored_hash.split(":")
        salt = bytes.fromhex(salt_hex)
        for iters in (_PBKDF2_ITERATIONS, 260_000, 100_000):
            dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iters)
            if hmac.compare_digest(dk.hex(), dk_hex):
                return True
        return False
    except Exception:
        return False

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
            owner_user_id INTEGER REFERENCES users(id),
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
    # Run the users-table migration on every startup so legacy username-based
    # SQLite databases get an email column and the bootstrap coordinator row
    # becomes reachable by the new email-based login flow.
    init_users()

# ── Users (RBAC) ──────────────────────────────────────────────────────────────
# Password hashing lives in utils/auth.py (bcrypt). This module only stores and
# retrieves the hash string. Schema: email-based, role-checked, activation flag.

BOOTSTRAP_COORDINATOR_EMAIL = "mdefaa@gmail.com"


def init_users():
    """Ensure the users table has the email-based schema.

    If the legacy username-based table exists, migrate it in place:
    add the missing columns (email, full_name, is_active), copy username
    into email for existing rows, and force the bootstrap coordinator row
    to email=mdefaa@gmail.com so the new login page can find it.

    Does NOT seed new users — that is done by
    utils.auth.ensure_bootstrap_coordinator().
    """
    conn = get_connection()

    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone() is not None

    if not table_exists:
        conn.executescript("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN (
                    'coordinator','facilitator','host','cdfa_staff','nhh_staff'
                )),
                full_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER NOT NULL DEFAULT 1,
                -- 1 = newly-created staff account, must set their own password
                -- on first sign-in. Default 0 so bootstrap + existing staff
                -- are not unexpectedly forced. Admin Users create flow passes
                -- 1 explicitly; the require_auth intercept reads it.
                must_change_password INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);
            CREATE INDEX IF NOT EXISTS idx_users_role  ON users (role);
        """)
    else:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]

        if "email" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
            if "username" in cols:
                conn.execute(
                    "UPDATE users SET email = username "
                    "WHERE email IS NULL OR email = ''"
                )

        if "full_name" not in cols:
            try:
                conn.execute("ALTER TABLE users ADD COLUMN full_name TEXT")
            except sqlite3.OperationalError:
                pass

        if "is_active" not in cols:
            try:
                conn.execute(
                    "ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1"
                )
            except sqlite3.OperationalError:
                pass

        if "must_change_password" not in cols:
            try:
                conn.execute(
                    "ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0"
                )
            except sqlite3.OperationalError:
                pass

        # Force the first coordinator row to the bootstrap email so the
        # new email-based login can find it.
        conn.execute(
            "UPDATE users SET email = ? "
            "WHERE rowid = (SELECT MIN(rowid) FROM users WHERE role = 'coordinator')",
            (BOOTSTRAP_COORDINATOR_EMAIL,),
        )

        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users (email)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_role  ON users (role)")
        except sqlite3.OperationalError:
            pass

    # Add owner_user_id to events if it's missing (for existing DBs created
    # before this migration). SQLite: ALTER TABLE ADD COLUMN is idempotent
    # only if we check first.
    cols = [r[1] for r in conn.execute("PRAGMA table_info(events)").fetchall()]
    if "owner_user_id" not in cols:
        try:
            conn.execute("ALTER TABLE events ADD COLUMN owner_user_id INTEGER REFERENCES users(id)")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()


def get_user_by_email(email):
    with _safe_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        return dict(row) if row else None


def create_user(email, password_hash, role, full_name="", must_change_password=0):
    """Insert a new staff user. must_change_password defaults to 0 for
    back-compat with the bootstrap path; the Admin Users grant flow in
    pages/15_Admin_Users.py passes 1 explicitly so newly-created staff are
    forced to set their own password on first sign-in (the intercept lives
    in utils.auth.require_auth)."""
    with _safe_conn() as conn:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash, role, full_name, "
            "must_change_password) VALUES (?,?,?,?,?)",
            (email, password_hash, role, full_name,
             1 if must_change_password else 0),
        )
        conn.commit()
        return cur.lastrowid


def list_users():
    with _safe_conn() as conn:
        rows = conn.execute(
            "SELECT id, email, role, full_name, created_at, is_active, "
            "must_change_password "
            "FROM users ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def update_staff_password_and_clear_flag(user_id, password_hash):
    """Replace the bcrypt hash on a staff user row and clear the
    must_change_password flag in one UPDATE. Caller hashes via
    utils.auth.hash_password (bcrypt) before passing in — do NOT call the
    PBKDF2 portal_access hash_password here. (Genuinely new helper; the
    existing reset_user_password is keyed by email and is intentionally
    not overloaded with the flag-clear because it's reachable from the
    standalone reset_password.py CLI.)"""
    with _safe_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash=?, must_change_password=0 WHERE id=?",
            (password_hash, user_id),
        )
        conn.commit()


def update_user_role(user_id, role):
    with _safe_conn() as conn:
        conn.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
        conn.commit()


def set_user_active(user_id, is_active):
    with _safe_conn() as conn:
        conn.execute(
            "UPDATE users SET is_active=? WHERE id=?",
            (1 if is_active else 0, user_id),
        )
        conn.commit()


def reset_user_password(email, new_password_hash):
    with _safe_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash=? WHERE email=?",
            (new_password_hash, email),
        )
        conn.commit()

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
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            -- 1 = account was seeded with the shared initial password and the
            -- user must set their own personal password before reaching portal
            -- content. Default 0 so existing claimed accounts created before
            -- this feature are NOT forced to change. New rows inserted via the
            -- grant flow pass 1 explicitly.
            must_change_password INTEGER DEFAULT 0
        )
    """)
    # Backfill for pre-existing local DBs whose portal_access table was created
    # before this column existed. ALTER TABLE ADD COLUMN is idempotent only via
    # the column-exists check; otherwise it raises OperationalError on re-run.
    cols = [r[1] for r in conn.execute("PRAGMA table_info(portal_access)").fetchall()]
    if "must_change_password" not in cols:
        try:
            conn.execute(
                "ALTER TABLE portal_access ADD COLUMN must_change_password INTEGER DEFAULT 0"
            )
        except sqlite3.OperationalError:
            pass
    conn.commit(); conn.close()

def get_all_portal_access():
    conn = get_connection()
    init_portal_access()
    rows = conn.execute("SELECT * FROM portal_access ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_portal_access(data):
    """Insert a new portal account. must_change_password defaults to 0 for
    back-compat with callers that don't pass it; the grant flow in
    pages/13_Portal_Access.py passes 1 explicitly so seeded shared-code
    accounts are forced to set their own password on first sign-in."""
    init_portal_access()
    with _safe_conn() as conn:
        conn.execute("""
            INSERT INTO portal_access
                (person_type, person_id, username, password_hash,
                 is_active, notes, must_change_password)
            VALUES (?,?,?,?,?,?,?)
        """, (data['person_type'], data['person_id'], data['username'],
              hash_password(data['password']), data.get('is_active', 0),
              data.get('notes', ''),
              1 if data.get('must_change_password') else 0))
        conn.commit()


def update_portal_password(access_id, new_password):
    """Replace the stored password hash for a portal account and clear the
    must_change_password flag. Uses the existing PBKDF2 hash_password helper —
    do NOT reimplement hashing here. Called from the first-login set-password
    form in pages/0_Portal.py."""
    init_portal_access()
    with _safe_conn() as conn:
        conn.execute("""
            UPDATE portal_access
            SET password_hash = ?, must_change_password = 0
            WHERE access_id = ?
        """, (hash_password(new_password), int(access_id)))
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
    """Messages this person sent. Excludes rows the SAME person has hidden
    from their own view via message_hides('legacy', ..., sender_type,
    sender_id) — the coordinator's view (get_all_messages) still sees them."""
    conn = get_connection()
    init_messages()
    init_message_hides()
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
            LEFT JOIN message_hides h
                ON h.message_system='legacy'
                AND h.message_id   = m.message_id
                AND h.viewer_type  = ?
                AND h.viewer_id    = ?
            WHERE m.sender_type=? AND m.sender_id=?
                AND h.id IS NULL
            ORDER BY m.created_at DESC
        """, (sender_type, str(sender_id), sender_type, sender_id)).fetchall()
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


# ── Contact Facilitator(s) — host↔facilitator threads with silent coordinator ──
# Additive: a separate table set from the legacy `messages` table so the existing
# Message-Coordinator flow (init_messages / send_message / get_messages_for_person
# / reply_to_message) is untouched. The coordinator is a hidden participant
# (is_hidden=1) on every conversation — visible only in the coordinator view.

def init_facilitator_conversations():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS facilitator_conversations (
            conversation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id        INTEGER REFERENCES events(event_id),
            host_id         INTEGER REFERENCES hosts(host_id),
            subject         TEXT,
            status          TEXT DEFAULT 'open',
            created_by_type TEXT,
            created_by_id   INTEGER,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS facilitator_conversation_messages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER REFERENCES facilitator_conversations(conversation_id),
            sender_type     TEXT NOT NULL,
            sender_id       INTEGER,
            sender_name     TEXT,
            body            TEXT NOT NULL,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS facilitator_conversation_participants (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id  INTEGER REFERENCES facilitator_conversations(conversation_id),
            participant_type TEXT NOT NULL,
            -- TEXT (not INTEGER) so the same column can hold host_id /
            -- facilitator_id (integers) and coordinator users.id (UUID under
            -- Postgres). Callers must str() the value before insert.
            participant_id   TEXT,
            is_hidden        INTEGER DEFAULT 0,
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_fc_participants_lookup
            ON facilitator_conversation_participants (participant_type, participant_id);
        CREATE INDEX IF NOT EXISTS idx_fc_messages_conv
            ON facilitator_conversation_messages (conversation_id, created_at);
    """)
    conn.commit(); conn.close()


def get_facilitators_for_host_event(event_id):
    """Facilitators assigned to a specific event. Returns list of dicts with
    facilitator_id + name + email. Wraps the existing event_facilitators join."""
    with _safe_conn() as conn:
        rows = conn.execute("""
            SELECT f.facilitator_id, f.name, f.email
            FROM facilitators f
            JOIN event_facilitators ef ON f.facilitator_id = ef.facilitator_id
            WHERE ef.event_id = ?
            ORDER BY f.name
        """, (event_id,)).fetchall()
        return [dict(r) for r in rows]


def resolve_main_coordinator():
    """Return the users.id of the main coordinator (silent-copy recipient).
    Preference order: bootstrap email mdefaa@gmail.com if active, else the
    earliest-created active coordinator. Returns None if no coordinator exists
    (caller must decide whether to skip the hidden CC in that case)."""
    with _safe_conn() as conn:
        row = conn.execute("""
            SELECT id FROM users
            WHERE role='coordinator' AND is_active=1 AND email=?
            LIMIT 1
        """, (BOOTSTRAP_COORDINATOR_EMAIL,)).fetchone()
        if row:
            return row["id"]
        row = conn.execute("""
            SELECT id FROM users
            WHERE role='coordinator' AND is_active=1
            ORDER BY created_at ASC, id ASC
            LIMIT 1
        """).fetchone()
        return row["id"] if row else None


def create_facilitator_conversation(event_id, host_id, subject, facilitator_ids,
                                    creator_type, creator_id, creator_name, first_body):
    """Insert the conversation + first message + participants (host + chosen
    facilitators + silent coordinator). Returns the new conversation_id."""
    init_facilitator_conversations()
    coord_user_id = resolve_main_coordinator()
    with _safe_conn() as conn:
        cur = conn.execute("""
            INSERT INTO facilitator_conversations
                (event_id, host_id, subject, status, created_by_type, created_by_id)
            VALUES (?,?,?,?,?,?)
        """, (event_id, host_id, subject, 'open', creator_type, creator_id))
        conv_id = cur.lastrowid

        conn.execute("""
            INSERT INTO facilitator_conversation_messages
                (conversation_id, sender_type, sender_id, sender_name, body)
            VALUES (?,?,?,?,?)
        """, (conv_id, creator_type, creator_id, creator_name, first_body))

        conn.execute("""
            INSERT INTO facilitator_conversation_participants
                (conversation_id, participant_type, participant_id, is_hidden)
            VALUES (?,?,?,?)
        """, (conv_id, 'host', str(host_id), 0))

        for fid in (facilitator_ids or []):
            conn.execute("""
                INSERT INTO facilitator_conversation_participants
                    (conversation_id, participant_type, participant_id, is_hidden)
                VALUES (?,?,?,?)
            """, (conv_id, 'facilitator', str(fid), 0))

        if coord_user_id is not None:
            conn.execute("""
                INSERT INTO facilitator_conversation_participants
                    (conversation_id, participant_type, participant_id, is_hidden)
                VALUES (?,?,?,?)
            """, (conv_id, 'coordinator', str(coord_user_id), 1))

        conn.commit()
        return conv_id


def add_conversation_message(conversation_id, sender_type, sender_id, sender_name, body):
    init_facilitator_conversations()
    with _safe_conn() as conn:
        conn.execute("""
            INSERT INTO facilitator_conversation_messages
                (conversation_id, sender_type, sender_id, sender_name, body)
            VALUES (?,?,?,?,?)
        """, (conversation_id, sender_type, sender_id, sender_name, body))
        conn.commit()


def get_conversations_for_participant(participant_type, participant_id):
    """Conversations where this person is a participant (regardless of is_hidden,
    but in practice host/facilitator are never hidden). Each row carries event_name
    and host_name for display."""
    init_facilitator_conversations()
    with _safe_conn() as conn:
        rows = conn.execute("""
            SELECT c.*, e.event_name, h.name AS host_name
            FROM facilitator_conversations c
            JOIN facilitator_conversation_participants p
                ON p.conversation_id = c.conversation_id
            LEFT JOIN events e ON c.event_id = e.event_id
            LEFT JOIN hosts  h ON c.host_id  = h.host_id
            WHERE p.participant_type = ? AND p.participant_id = ?
            ORDER BY c.created_at DESC
        """, (participant_type, str(participant_id))).fetchall()
        return [dict(r) for r in rows]


def get_conversation_messages(conversation_id, viewer_type=None, viewer_id=None):
    """Ordered turns in a Contact-Facilitator conversation. When viewer_type
    + viewer_id are supplied (host or facilitator views), rows that viewer
    has hidden via message_hides('fac_conv', id, viewer_type, viewer_id) are
    excluded. When omitted (coordinator's read-only oversight view), every
    row is returned regardless of hides — and hard-deleted rows are simply
    no longer there."""
    init_facilitator_conversations()
    if viewer_type and viewer_id is not None:
        init_message_hides()
        with _safe_conn() as conn:
            rows = conn.execute("""
                SELECT m.* FROM facilitator_conversation_messages m
                LEFT JOIN message_hides h
                    ON h.message_system='fac_conv'
                    AND h.message_id   = m.id
                    AND h.viewer_type  = ?
                    AND h.viewer_id    = ?
                WHERE m.conversation_id = ? AND h.id IS NULL
                ORDER BY m.created_at ASC, m.id ASC
            """, (viewer_type, str(viewer_id), conversation_id)).fetchall()
            return [dict(r) for r in rows]
    with _safe_conn() as conn:
        rows = conn.execute("""
            SELECT * FROM facilitator_conversation_messages
            WHERE conversation_id = ?
            ORDER BY created_at ASC, id ASC
        """, (conversation_id,)).fetchall()
        return [dict(r) for r in rows]


def get_visible_participants(conversation_id):
    """Participants with is_hidden=0 only. Host/facilitator views must call this
    so the silent coordinator is never disclosed."""
    init_facilitator_conversations()
    with _safe_conn() as conn:
        rows = conn.execute("""
            SELECT * FROM facilitator_conversation_participants
            WHERE conversation_id = ? AND is_hidden = 0
            ORDER BY id ASC
        """, (conversation_id,)).fetchall()
        return [dict(r) for r in rows]


def get_all_facilitator_conversations():
    """Coordinator view: every conversation, newest first. Coordinator sees all
    threads regardless of participation."""
    init_facilitator_conversations()
    with _safe_conn() as conn:
        rows = conn.execute("""
            SELECT c.*, e.event_name, h.name AS host_name
            FROM facilitator_conversations c
            LEFT JOIN events e ON c.event_id = e.event_id
            LEFT JOIN hosts  h ON c.host_id  = h.host_id
            ORDER BY c.created_at DESC
        """).fetchall()
        return [dict(r) for r in rows]


# ── Message hides — per-viewer hide-from-my-view across BOTH message systems ──
# Single table for both the legacy `messages` rows and the new
# `facilitator_conversation_messages` rows, discriminated by `message_system`.
# Code-enforced (no FK) because one column would otherwise need to FK two tables.
# Coordinator hard-delete removes the underlying row from its own table and
# then cleans up any hides pointing at it; per-viewer hide just INSERT-OR-IGNOREs.

def init_message_hides():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS message_hides (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            message_system  TEXT NOT NULL,   -- 'legacy' | 'fac_conv'
            message_id      INTEGER NOT NULL,
            viewer_type     TEXT NOT NULL,   -- 'host' | 'facilitator'
            viewer_id       TEXT NOT NULL,   -- str(host_id) / str(facilitator_id)
            hidden_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(message_system, message_id, viewer_type, viewer_id)
        );
        CREATE INDEX IF NOT EXISTS idx_message_hides_lookup
            ON message_hides (message_system, viewer_type, viewer_id);
    """)
    conn.commit(); conn.close()


def hide_message(message_system, message_id, viewer_type, viewer_id):
    """Mark a message as hidden for this viewer only. INSERT OR IGNORE so
    repeat clicks are no-ops. The coordinator and other participants still
    see the row — this is per-viewer, not a global delete."""
    init_message_hides()
    with _safe_conn() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO message_hides
                (message_system, message_id, viewer_type, viewer_id)
            VALUES (?,?,?,?)
        """, (message_system, int(message_id), viewer_type, str(viewer_id)))
        conn.commit()


def _is_message_hidden_for(message_system, message_id, viewer_type, viewer_id):
    """Predicate used by tests and by render code that decides whether to
    show an individual row outside the LEFT-JOIN read path."""
    init_message_hides()
    with _safe_conn() as conn:
        row = conn.execute("""
            SELECT 1 FROM message_hides
            WHERE message_system=? AND message_id=? AND viewer_type=? AND viewer_id=?
            LIMIT 1
        """, (message_system, int(message_id), viewer_type, str(viewer_id))).fetchone()
        return row is not None


def delete_message(message_id, deleted_by=""):
    """Coordinator-only hard delete from the legacy `messages` table. Writes
    an audit entry to `activity_log` and removes any per-viewer hides that
    pointed at the now-gone row."""
    init_messages()
    init_message_hides()
    with _safe_conn() as conn:
        conn.execute("DELETE FROM messages WHERE message_id=?", (int(message_id),))
        conn.execute("""
            DELETE FROM message_hides
            WHERE message_system='legacy' AND message_id=?
        """, (int(message_id),))
        conn.commit()
    log_activity(
        "Message Deleted",
        f"message_system=legacy message_id={int(message_id)}",
        user=deleted_by or "Coordinator",
    )


def delete_conversation_message(message_id, deleted_by=""):
    """Coordinator-only hard delete from the Contact-Facilitator thread
    table. No 'deleted by' tombstone is written into the thread — the
    coordinator stays a silent participant. The audit trail is in
    `activity_log`."""
    init_facilitator_conversations()
    init_message_hides()
    with _safe_conn() as conn:
        conn.execute(
            "DELETE FROM facilitator_conversation_messages WHERE id=?",
            (int(message_id),),
        )
        conn.execute("""
            DELETE FROM message_hides
            WHERE message_system='fac_conv' AND message_id=?
        """, (int(message_id),))
        conn.commit()
    log_activity(
        "Message Deleted",
        f"message_system=fac_conv message_id={int(message_id)}",
        user=deleted_by or "Coordinator",
    )


def init_all():
    """Initialise the full SQLite schema for local dev — mirrors
    supabase_db.init_all(). All eight helpers are idempotent. init_db()
    also calls init_users() internally; the explicit call here is a
    harmless idempotent repeat that keeps this aggregator self-documenting.
    Dependency order matters: init_db() must create `events` before
    init_users() runs its events.owner_user_id migration."""
    init_db()             # hosts, facilitators, nhh/cdfa_colleagues, events,
                          # event_facilitators, communications, tasks,
                          # feedback, reports (+ init_users internally)
    init_users()          # users (+ indexes, events.owner_user_id migration)
    init_activity_log()   # activity_log
    init_mileage()        # mileage_reimbursements
    init_portal_access()  # portal_access
    init_messages()       # messages
    init_facilitator_conversations()  # facilitator_conversations + messages + participants
    init_message_hides()  # message_hides (legacy + fac_conv per-viewer hide table)


# ── PostgreSQL override ───────────────────────────────────────────────────────
# When DATABASE_URL is configured (Supabase / Streamlit Cloud), swap every
# function above with its psycopg2 equivalent.  Local dev keeps SQLite.
try:
    import os as _os
    _db_url = None
    try:
        import streamlit as _st
        _db_url = _st.secrets.get("DATABASE_URL")
    except Exception:
        _db_url = None
    if not _db_url:
        _db_url = _os.environ.get("DATABASE_URL")
    if _db_url:
        import utils.supabase_db as _pg
        import inspect as _inspect
        for _name, _obj in _inspect.getmembers(_pg):
            if not _name.startswith("_") and callable(_obj):
                globals()[_name] = _obj
except Exception as _e:
    import logging as _logging
    _logging.warning("Supabase override failed, falling back to SQLite: %s", _e)
