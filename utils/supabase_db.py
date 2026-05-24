"""
PostgreSQL backend for Supabase deployment.
Mirrors every public function in database.py but uses psycopg2.

Activated automatically when DATABASE_URL is present in st.secrets or os.environ.
"""

import psycopg2
import psycopg2.extras
import psycopg2.pool
import streamlit as st
from datetime import datetime, date, timedelta
import os
import urllib.parse
import hashlib
import hmac


# ── Legacy password hashing ──────────────────────────────────────────────────
# Used ONLY by the separate portal_access / check_portal_login system.
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

DB_PATH = "supabase"  # Sentinel so any code that prints DB_PATH still works

_pool = None
_diagnostics_logged = False


def _debug_enabled() -> bool:
    """Return True when CC_DEBUG_DB=1 is set in either os.environ or st.secrets.

    Streamlit Cloud puts secrets.toml entries in st.secrets, NOT os.environ —
    so a flag set in the Secrets panel only fires when we look in both places.
    """
    if os.environ.get("CC_DEBUG_DB") == "1":
        return True
    try:
        return str(st.secrets.get("CC_DEBUG_DB", "")) == "1"
    except Exception:
        return False


def _log_connection_diagnostics(url: str, source: str) -> None:
    """Print non-sensitive DATABASE_URL diagnostics to stdout.

    Gated by CC_DEBUG_DB=1 (env var or st.secrets). Runs at most once per
    process. Never logs the password itself or the full URL — only derived
    facts (length, character class, source, parsed components).
    """
    global _diagnostics_logged
    if _diagnostics_logged:
        return
    if not _debug_enabled():
        return
    _diagnostics_logged = True

    print(f"[CC_DEBUG_DB] DATABASE_URL source: {source}")
    if not url:
        print("[CC_DEBUG_DB] url is empty; nothing further to inspect")
        return

    has_leading_ws = url != url.lstrip()
    has_trailing_ws = url != url.rstrip()
    has_newline = "\n" in url
    has_tab = "\t" in url
    has_surrounding_quotes = (
        (url.startswith('"') and url.endswith('"'))
        or (url.startswith("'") and url.endswith("'"))
    )
    print(f"[CC_DEBUG_DB] raw url length: {len(url)}")
    print(f"[CC_DEBUG_DB] leading whitespace: {has_leading_ws}")
    print(f"[CC_DEBUG_DB] trailing whitespace: {has_trailing_ws}")
    print(f"[CC_DEBUG_DB] embedded newline: {has_newline}")
    print(f"[CC_DEBUG_DB] embedded tab: {has_tab}")
    print(f"[CC_DEBUG_DB] surrounding quotes: {has_surrounding_quotes}")

    try:
        parsed = urllib.parse.urlparse(url)
        password = parsed.password or ""
        non_alnum = any(not c.isalnum() for c in password)
        print(f"[CC_DEBUG_DB] scheme: {parsed.scheme}")
        print(f"[CC_DEBUG_DB] hostname: {parsed.hostname}")
        print(f"[CC_DEBUG_DB] port: {parsed.port}")
        print(f"[CC_DEBUG_DB] username: {parsed.username}")
        print(f"[CC_DEBUG_DB] path: {parsed.path}")
        print(f"[CC_DEBUG_DB] password length: {len(password)}")
        print(f"[CC_DEBUG_DB] password has non-alphanumeric: {non_alnum}")
    except Exception as exc:
        print(f"[CC_DEBUG_DB] urlparse failed: {type(exc).__name__}")


def _get_database_url():
    source = "NOT FOUND"
    url = None
    try:
        url = st.secrets.get("DATABASE_URL")
        if url:
            source = "st.secrets"
    except Exception:
        pass
    if not url:
        url = os.environ.get("DATABASE_URL")
        if url:
            source = "os.environ"
    if not url:
        _log_connection_diagnostics("", source)
        raise RuntimeError(
            "DATABASE_URL not found in st.secrets or environment variables"
        )
    _log_connection_diagnostics(url, source)
    return url

def _get_pool():
    global _pool
    if _pool is None:
        url = _get_database_url()
        parsed = urllib.parse.urlparse(url)
        # urlparse() returns username/password percent-decoded on Python 3.6+
        username = parsed.username or ''
        password = parsed.password or ''
        hostname = parsed.hostname or ''
        port = parsed.port or 5432
        dbname = (parsed.path or '/postgres').lstrip('/')
        if _debug_enabled():
            print(
                f"[CC_DEBUG_DB] connecting with "
                f"user={username!r} host={hostname!r} port={port} "
                f"dbname={dbname!r} pwlen={len(password)}",
                flush=True,
            )
        try:
            _pool = psycopg2.pool.SimpleConnectionPool(
                minconn=1, maxconn=10,
                host=hostname,
                port=port,
                user=username,
                password=password,
                dbname=dbname,
                sslmode='require',
                connect_timeout=10,
            )
        except psycopg2.OperationalError as exc:
            _handle_pool_error(exc)
    return _pool


def _handle_pool_error(exc: psycopg2.OperationalError) -> None:
    """Translate a psycopg2 connection error into a clean Streamlit page halt.

    Logs the full error to stdout (psycopg2 connection errors do not contain
    the password — only host/port/error code), then renders a user-friendly
    message via st.error() and stops the page render with st.stop().
    Never lets the raw traceback reach the user.
    """
    err_text = str(exc)
    print(f"[CC_DB_ERROR] psycopg2.OperationalError: {err_text}")

    if "ECIRCUITBREAKER" in err_text:
        message = (
            "The database is temporarily blocking connections after repeated "
            "failed authentication attempts. Please wait 15 to 30 minutes, "
            "then refresh this page."
        )
    elif "ENOTFOUND" in err_text:
        message = "Database project not found. Please contact the coordinator."
    elif "password authentication failed" in err_text:
        message = "Database authentication failed. Please contact the coordinator."
    else:
        message = "Database connection unavailable. Please try again in a few minutes."

    try:
        st.error(message)
        if _debug_enabled():
            with st.expander("Show technical details (CC_DEBUG_DB enabled)"):
                st.code(err_text, language="text")
    except Exception:
        # Outside a Streamlit script context (e.g., reset_password.py CLI).
        # Re-raise the original psycopg2 error so the CLI sees the real cause.
        raise exc
    st.stop()

def get_connection():
    return _get_pool().getconn()


def _putconn(conn):
    """Return a connection to the pool. Swallow errors — never recurse."""
    if conn is None:
        return
    try:
        _get_pool().putconn(conn)
    except Exception:
        # Pool may have been closed, or conn may already be returned.
        # Do not retry — retrying caused infinite recursion in the previous
        # implementation. Silently drop on the floor; the next getconn() will
        # create a replacement if needed.
        pass

def _fetchall(conn, query, params=None):
    """Execute a SELECT and return list[dict], then return conn to pool."""
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params or ())
            rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        _putconn(conn)


def _fetchone(conn, query, params=None):
    """Execute a SELECT and return a single dict or None, then return conn."""
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params or ())
            row = cur.fetchone()
        return dict(row) if row else None
    finally:
        _putconn(conn)


def _execute(conn, query, params=None):
    """Execute a write statement, commit, and return conn to pool."""
    try:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
        conn.commit()
    finally:
        _putconn(conn)


# Password hashing lives in utils/auth.py (bcrypt).


# ── Schema Initialisation ─────────────────────────────────────────────────────

_schema_initialised = False

def init_all():
    """Initialise every table in a single DB connection. Cached by caller."""
    global _schema_initialised
    if _schema_initialised:
        return
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # hosts
            cur.execute("""CREATE TABLE IF NOT EXISTS hosts (
                host_id SERIAL PRIMARY KEY, name TEXT NOT NULL, venue_name TEXT,
                address TEXT, city TEXT, state TEXT DEFAULT 'NH', zip_code TEXT,
                contact_person TEXT, email TEXT, phone TEXT, check_payable_to TEXT,
                payment_amount REAL DEFAULT 0, payment_status TEXT DEFAULT 'Pending',
                payment_date DATE, notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            # facilitators
            cur.execute("""CREATE TABLE IF NOT EXISTS facilitators (
                facilitator_id SERIAL PRIMARY KEY, name TEXT NOT NULL, email TEXT,
                phone TEXT, address TEXT, city TEXT, state TEXT DEFAULT 'NH',
                zip_code TEXT, check_payable_to TEXT,
                payment_amount REAL DEFAULT 0, payment_status TEXT DEFAULT 'Pending',
                payment_date DATE, specialization TEXT, notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            # nhh_colleagues
            cur.execute("""CREATE TABLE IF NOT EXISTS nhh_colleagues (
                nhh_id SERIAL PRIMARY KEY, name TEXT NOT NULL, title TEXT,
                email TEXT, phone TEXT, role TEXT, notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            # cdfa_colleagues
            cur.execute("""CREATE TABLE IF NOT EXISTS cdfa_colleagues (
                cdfa_id SERIAL PRIMARY KEY, name TEXT NOT NULL, title TEXT,
                email TEXT, phone TEXT, role TEXT, notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            # events
            cur.execute("""CREATE TABLE IF NOT EXISTS events (
                event_id SERIAL PRIMARY KEY, event_name TEXT NOT NULL,
                event_date DATE NOT NULL, event_time TEXT,
                host_id INTEGER REFERENCES hosts(host_id),
                venue_address TEXT, city TEXT, status TEXT DEFAULT 'Scheduled',
                attendance_count INTEGER, attendance_confirmed INTEGER DEFAULT 0,
                event_summary TEXT,
                owner_user_id UUID,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            # Migration for pre-existing events tables missing owner_user_id.
            cur.execute("""ALTER TABLE events
                ADD COLUMN IF NOT EXISTS owner_user_id UUID""")
            # event_facilitators
            cur.execute("""CREATE TABLE IF NOT EXISTS event_facilitators (
                event_facilitator_id SERIAL PRIMARY KEY,
                event_id INTEGER REFERENCES events(event_id),
                facilitator_id INTEGER REFERENCES facilitators(facilitator_id))""")
            # communications
            cur.execute("""CREATE TABLE IF NOT EXISTS communications (
                communication_id SERIAL PRIMARY KEY, recipient_type TEXT,
                recipient_id INTEGER, event_id INTEGER REFERENCES events(event_id),
                communication_type TEXT, subject TEXT, body TEXT,
                sent_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sent_by TEXT DEFAULT 'Coordinator', notes TEXT)""")
            # tasks
            cur.execute("""CREATE TABLE IF NOT EXISTS tasks (
                task_id SERIAL PRIMARY KEY, task_title TEXT NOT NULL,
                task_description TEXT,
                related_event_id INTEGER REFERENCES events(event_id),
                due_date DATE, priority TEXT DEFAULT 'Medium',
                status TEXT DEFAULT 'Not Started',
                assigned_to TEXT DEFAULT 'Coordinator',
                completed_date DATE, notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            # feedback
            cur.execute("""CREATE TABLE IF NOT EXISTS feedback (
                feedback_id SERIAL PRIMARY KEY,
                event_id INTEGER REFERENCES events(event_id),
                participant_name TEXT, feedback_text TEXT, rating INTEGER,
                submitted_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            # reports
            cur.execute("""CREATE TABLE IF NOT EXISTS reports (
                report_id SERIAL PRIMARY KEY, report_type TEXT, report_name TEXT,
                generated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                file_path TEXT, notes TEXT)""")
            # mileage_reimbursements
            cur.execute("""CREATE TABLE IF NOT EXISTS mileage_reimbursements (
                mileage_id SERIAL PRIMARY KEY,
                facilitator_id INTEGER REFERENCES facilitators(facilitator_id),
                event_id INTEGER REFERENCES events(event_id),
                facilitator_address TEXT, event_address TEXT,
                distance_miles REAL, round_trip_miles REAL,
                rate_per_mile REAL DEFAULT 0.725, reimbursement_amount REAL,
                status TEXT DEFAULT 'Pending', notes TEXT,
                calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            # portal_access
            cur.execute("""CREATE TABLE IF NOT EXISTS portal_access (
                access_id SERIAL PRIMARY KEY, person_type TEXT NOT NULL,
                person_id INTEGER NOT NULL, username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL, is_active INTEGER DEFAULT 0,
                granted_by TEXT DEFAULT 'Coordinator', granted_at TIMESTAMP,
                notes TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            # activity_log
            cur.execute("""CREATE TABLE IF NOT EXISTS activity_log (
                log_id SERIAL PRIMARY KEY, action TEXT NOT NULL, details TEXT,
                "user" TEXT DEFAULT 'Coordinator',
                logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            # messages
            cur.execute("""CREATE TABLE IF NOT EXISTS messages (
                message_id SERIAL PRIMARY KEY, sender_type TEXT NOT NULL,
                sender_id INTEGER, sender_name TEXT,
                event_id INTEGER REFERENCES events(event_id),
                category TEXT, subject TEXT, body TEXT NOT NULL,
                is_read INTEGER DEFAULT 0, replied_at TIMESTAMP,
                reply_body TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            # notifications
            cur.execute("""CREATE TABLE IF NOT EXISTS notifications (
                notif_id SERIAL PRIMARY KEY, message TEXT NOT NULL,
                target_role TEXT DEFAULT 'all', event_id INTEGER,
                is_read INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            # users (RBAC — email-based)
            # Drop the legacy username-based table if it exists so the wipe/reseed
            # migration completes cleanly on first run.
            cur.execute("""SELECT column_name FROM information_schema.columns
                            WHERE table_name='users' AND column_name='username'""")
            if cur.fetchone():
                cur.execute("DROP TABLE IF EXISTS users CASCADE")
            cur.execute("""CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN (
                    'coordinator','facilitator','host','cdfa_staff','nhh_staff'
                )),
                full_name TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                is_active BOOLEAN NOT NULL DEFAULT TRUE)""")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users (email)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_users_role  ON users (role)")
            # Wire up the FK from events.owner_user_id now that users exists.
            cur.execute("""DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.table_constraints
                        WHERE constraint_name = 'events_owner_user_id_fkey'
                    ) THEN
                        ALTER TABLE events
                        ADD CONSTRAINT events_owner_user_id_fkey
                        FOREIGN KEY (owner_user_id) REFERENCES users(id)
                        ON DELETE SET NULL;
                    END IF;
                END $$""")
            # facilitator_conversations (Contact Facilitator(s) feature).
            # Additive: independent of the legacy `messages` table. Coordinator
            # is recorded as a hidden participant (is_hidden=1).
            cur.execute("""CREATE TABLE IF NOT EXISTS facilitator_conversations (
                conversation_id SERIAL PRIMARY KEY,
                event_id        INTEGER REFERENCES events(event_id),
                host_id         INTEGER REFERENCES hosts(host_id),
                subject         TEXT,
                status          TEXT DEFAULT 'open',
                created_by_type TEXT,
                created_by_id   INTEGER,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS facilitator_conversation_messages (
                id              SERIAL PRIMARY KEY,
                conversation_id INTEGER REFERENCES facilitator_conversations(conversation_id),
                sender_type     TEXT NOT NULL,
                sender_id       INTEGER,
                sender_name     TEXT,
                body            TEXT NOT NULL,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            # participant_id is TEXT so the same column can hold host/facilitator
            # integer ids AND the coordinator users.id UUID. Callers str() the value.
            cur.execute("""CREATE TABLE IF NOT EXISTS facilitator_conversation_participants (
                id               SERIAL PRIMARY KEY,
                conversation_id  INTEGER REFERENCES facilitator_conversations(conversation_id),
                participant_type TEXT NOT NULL,
                participant_id   TEXT,
                is_hidden        INTEGER DEFAULT 0,
                created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            cur.execute("""CREATE INDEX IF NOT EXISTS idx_fc_participants_lookup
                ON facilitator_conversation_participants (participant_type, participant_id)""")
            cur.execute("""CREATE INDEX IF NOT EXISTS idx_fc_messages_conv
                ON facilitator_conversation_messages (conversation_id, created_at)""")
        conn.commit()
        _schema_initialised = True
    finally:
        _putconn(conn)


# ── Users (RBAC) ──────────────────────────────────────────────────────────────

def init_users():
    """Idempotent alias — init_all() already creates the users table."""
    init_all()


def get_user_by_email(email):
    conn = get_connection()
    return (_fetchall(conn, "SELECT * FROM users WHERE email=%s", (email,)) or [None])[0]


def create_user(email, password_hash, role, full_name=""):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (email, password_hash, role, full_name) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (email, password_hash, role, full_name),
            )
            new_id = cur.fetchone()[0]
        conn.commit()
        return new_id
    finally:
        _putconn(conn)
    return True



def list_users():
    conn = get_connection()
    return _fetchall(
        conn,
        "SELECT id, email, role, full_name, created_at, is_active "
        "FROM users ORDER BY created_at DESC",
    )


def update_user_role(user_id, role):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET role=%s WHERE id=%s", (role, user_id))
        conn.commit()
    finally:
        _putconn(conn)
    return True



def set_user_active(user_id, is_active):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET is_active=%s WHERE id=%s", (bool(is_active), user_id))
        conn.commit()
    finally:
        _putconn(conn)
    return True



def reset_user_password(email, new_password_hash):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET password_hash=%s WHERE email=%s", (new_password_hash, email))
        conn.commit()
    finally:
        _putconn(conn)
    return True



def init_db():
    if _schema_initialised:
        return
    conn = get_connection()
    try:
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
    finally:
        _putconn(conn)


# Legacy username-based user helpers removed — see the RBAC section above
# (init_users, get_user_by_email, create_user, list_users, update_user_role,
# set_user_active, reset_user_password) which use the new email schema.


def init_mileage():
    if _schema_initialised:
        return
    conn = get_connection()
    try:
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
    finally:
        _putconn(conn)


def init_portal_access():
    if _schema_initialised:
        return
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS portal_access (
                    access_id   SERIAL PRIMARY KEY,
                    person_type TEXT NOT NULL,
                    person_id   INTEGER NOT NULL,
                    username    TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    is_active   INTEGER DEFAULT 0,
                    granted_by  TEXT DEFAULT 'Coordinator',
                    granted_at  TIMESTAMP,
                    notes       TEXT,
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        conn.commit()
    finally:
        _putconn(conn)


def init_activity_log():
    if _schema_initialised:
        return
    conn = get_connection()
    try:
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
    finally:
        _putconn(conn)


def init_messages():
    if _schema_initialised:
        return
    conn = get_connection()
    try:
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
    finally:
        _putconn(conn)


def _ensure_notifications():
    if _schema_initialised:
        return
    conn = get_connection()
    try:
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
    finally:
        _putconn(conn)


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
    return True



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
    return True



def delete_host(host_id):
    conn = get_connection()
    _execute(conn, "DELETE FROM hosts WHERE host_id=%s", (host_id,))
    return True



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
    return True



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
    return True



def delete_facilitator(fac_id):
    conn = get_connection()
    _execute(conn, "DELETE FROM facilitators WHERE facilitator_id=%s", (fac_id,))
    return True



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
    return True



def update_nhh(nhh_id, data):
    conn = get_connection()
    _execute(conn, """
        UPDATE nhh_colleagues SET name=%s,title=%s,email=%s,phone=%s,role=%s,
            notes=%s,updated_at=CURRENT_TIMESTAMP
        WHERE nhh_id=%s
    """, (data["name"], data.get("title"), data.get("email"),
          data.get("phone"), data.get("role"), data.get("notes"), nhh_id))
    return True



def delete_nhh(nhh_id):
    conn = get_connection()
    _execute(conn, "DELETE FROM nhh_colleagues WHERE nhh_id=%s", (nhh_id,))
    return True


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
    return True



def update_cdfa(cdfa_id, data):
    conn = get_connection()
    _execute(conn, """
        UPDATE cdfa_colleagues SET name=%s,title=%s,email=%s,phone=%s,role=%s,
            notes=%s,updated_at=CURRENT_TIMESTAMP
        WHERE cdfa_id=%s
    """, (data["name"], data.get("title"), data.get("email"),
          data.get("phone"), data.get("role"), data.get("notes"), cdfa_id))
    return True



def delete_cdfa(cdfa_id):
    conn = get_connection()
    _execute(conn, "DELETE FROM cdfa_colleagues WHERE cdfa_id=%s", (cdfa_id,))
    return True


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
    try:
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
        return event_id
    finally:
        _putconn(conn)
    return True



def update_event(event_id, data, facilitator_ids=None):
    conn = get_connection()
    try:
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
    finally:
        _putconn(conn)
    return True



def delete_event(event_id):
    """
    Delete an event and all rows in child tables that reference it.
    All deletes run inside one transaction — if any DELETE fails,
    nothing is committed.

    Child tables cleared (in FK-safe order):
      1. event_facilitators   (event_id)
      2. communications       (event_id)
      3. feedback             (event_id)
      4. mileage_reimbursements (event_id)
      5. messages             (event_id)
      6. tasks                (related_event_id)
      7. events               (event_id)  — the parent row
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM event_facilitators WHERE event_id=%s", (event_id,))
            cur.execute("DELETE FROM communications WHERE event_id=%s", (event_id,))
            cur.execute("DELETE FROM feedback WHERE event_id=%s", (event_id,))
            cur.execute("DELETE FROM mileage_reimbursements WHERE event_id=%s", (event_id,))
            cur.execute("DELETE FROM messages WHERE event_id=%s", (event_id,))
            cur.execute("DELETE FROM tasks WHERE related_event_id=%s", (event_id,))
            cur.execute("DELETE FROM events WHERE event_id=%s", (event_id,))
        conn.commit()
    finally:
        _putconn(conn)
    return True



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
    return True


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
    return True



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
    return True



def delete_task(task_id):
    conn = get_connection()
    _execute(conn, "DELETE FROM tasks WHERE task_id=%s", (task_id,))
    return True



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
    return True



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
    return True



def get_all_reports():
    conn = get_connection()
    return _fetchall(conn, "SELECT * FROM reports ORDER BY generated_date DESC")


# ── Dashboard Stats ───────────────────────────────────────────────────────────

def get_dashboard_stats():
    conn = get_connection()
    try:
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
        return stats
    finally:
        _putconn(conn)


# ── Activity Log ──────────────────────────────────────────────────────────────

def log_activity(action: str, details: str, user: str = "Coordinator"):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if not _schema_initialised:
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
    finally:
        _putconn(conn)
    return True



def get_activity_log(limit=50):
    conn = get_connection()
    return _fetchall(conn, """
        SELECT * FROM activity_log ORDER BY logged_at DESC LIMIT %s
    """, (limit,))


# ── Notifications ─────────────────────────────────────────────────────────────

def add_notification(message: str, target_role: str = "all", event_id=None):
    _ensure_notifications()
    conn = get_connection()
    _execute(conn, """
        INSERT INTO notifications (message, target_role, event_id) VALUES (%s,%s,%s)
    """, (message, target_role, event_id))
    return True



def get_notifications(role="all", unread_only=False):
    _ensure_notifications()
    conn = get_connection()
    q = "SELECT * FROM notifications WHERE (target_role=%s OR target_role='all')"
    params = [role]
    if unread_only:
        q += " AND is_read=0"
    q += " ORDER BY created_at DESC LIMIT 30"
    return _fetchall(conn, q, params)


def mark_notifications_read(role="all"):
    _ensure_notifications()
    conn = get_connection()
    _execute(conn, """
        UPDATE notifications SET is_read=1
        WHERE target_role=%s OR target_role='all'
    """, (role,))
    return True



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
        _putconn(conn)
        return count
    except Exception:
        _putconn(conn)
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
        INSERT INTO portal_access (person_type,person_id,username,password_hash,is_active,notes)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, (data['person_type'], data['person_id'], data['username'],
          hash_password(data['password']), data.get('is_active', 0), data.get('notes', '')))
    return True



def update_portal_access(access_id, is_active):
    init_portal_access()
    conn = get_connection()
    _execute(conn, """
        UPDATE portal_access SET is_active=%s, granted_at=CURRENT_TIMESTAMP
        WHERE access_id=%s
    """, (1 if is_active else 0, access_id))
    return True



def delete_portal_access(access_id):
    init_portal_access()
    conn = get_connection()
    _execute(conn, "DELETE FROM portal_access WHERE access_id=%s", (access_id,))
    return True



def check_portal_login(username, password):
    init_portal_access()
    conn = get_connection()
    row = _fetchone(conn, """
        SELECT pa.*,
               CASE WHEN pa.person_type='host' THEN h.name ELSE f.name END as person_name,
               CASE WHEN pa.person_type='host' THEN h.email ELSE f.email END as person_email
        FROM portal_access pa
        LEFT JOIN hosts h ON pa.person_type='host' AND pa.person_id=h.host_id
        LEFT JOIN facilitators f ON pa.person_type='facilitator' AND pa.person_id=f.facilitator_id
        WHERE pa.username=%s AND pa.is_active=1
    """, (username,))
    if row and verify_password(password, row.get("password_hash", "")):
        return row
    return None


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
    return True



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
    return True



def reply_to_message(message_id, reply_body):
    init_messages()
    conn = get_connection()
    _execute(conn, """
        UPDATE messages SET reply_body=%s, replied_at=CURRENT_TIMESTAMP, is_read=1
        WHERE message_id=%s
    """, (reply_body, message_id))
    return True



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
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM messages WHERE is_read=0 AND sender_type != 'coordinator'")
            count = cur.fetchone()[0]
        return count
    finally:
        _putconn(conn)


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
    return True



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
    return True



def delete_mileage_reimbursement(mileage_id):
    conn = get_connection()
    _execute(conn, "DELETE FROM mileage_reimbursements WHERE mileage_id=%s", (mileage_id,))
    return True



def get_mileage_total_pending():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COALESCE(SUM(reimbursement_amount),0)
                FROM mileage_reimbursements WHERE status='Pending'
            """)
            val = cur.fetchone()[0]
        return val
    finally:
        _putconn(conn)


# ── Contact Facilitator(s) — host↔facilitator threads with silent coordinator ──
# Parity mirror of utils.database. The three tables (facilitator_conversations,
# facilitator_conversation_messages, facilitator_conversation_participants) are
# created inside init_all() above; init_facilitator_conversations() is exposed
# as an idempotent standalone so callers that pre-date init_all() still work.

BOOTSTRAP_COORDINATOR_EMAIL_FC = "mdefaa@gmail.com"


def init_facilitator_conversations():
    if _schema_initialised:
        return
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS facilitator_conversations (
                conversation_id SERIAL PRIMARY KEY,
                event_id        INTEGER REFERENCES events(event_id),
                host_id         INTEGER REFERENCES hosts(host_id),
                subject         TEXT,
                status          TEXT DEFAULT 'open',
                created_by_type TEXT,
                created_by_id   INTEGER,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS facilitator_conversation_messages (
                id              SERIAL PRIMARY KEY,
                conversation_id INTEGER REFERENCES facilitator_conversations(conversation_id),
                sender_type     TEXT NOT NULL,
                sender_id       INTEGER,
                sender_name     TEXT,
                body            TEXT NOT NULL,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS facilitator_conversation_participants (
                id               SERIAL PRIMARY KEY,
                conversation_id  INTEGER REFERENCES facilitator_conversations(conversation_id),
                participant_type TEXT NOT NULL,
                participant_id   TEXT,
                is_hidden        INTEGER DEFAULT 0,
                created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            cur.execute("""CREATE INDEX IF NOT EXISTS idx_fc_participants_lookup
                ON facilitator_conversation_participants (participant_type, participant_id)""")
            cur.execute("""CREATE INDEX IF NOT EXISTS idx_fc_messages_conv
                ON facilitator_conversation_messages (conversation_id, created_at)""")
        conn.commit()
    finally:
        _putconn(conn)


def get_facilitators_for_host_event(event_id):
    conn = get_connection()
    return _fetchall(conn, """
        SELECT f.facilitator_id, f.name, f.email
        FROM facilitators f
        JOIN event_facilitators ef ON f.facilitator_id = ef.facilitator_id
        WHERE ef.event_id = %s
        ORDER BY f.name
    """, (event_id,))


def resolve_main_coordinator():
    """Return users.id (UUID) of the main coordinator, or None.
    Preference: bootstrap email mdefaa@gmail.com if active, else earliest-created
    active coordinator. Note Postgres uses is_active BOOLEAN (TRUE/FALSE), not 0/1."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id FROM users
                WHERE role='coordinator' AND is_active=TRUE AND email=%s
                LIMIT 1
            """, (BOOTSTRAP_COORDINATOR_EMAIL_FC,))
            row = cur.fetchone()
            if row:
                return row["id"]
            cur.execute("""
                SELECT id FROM users
                WHERE role='coordinator' AND is_active=TRUE
                ORDER BY created_at ASC, id ASC
                LIMIT 1
            """)
            row = cur.fetchone()
            return row["id"] if row else None
    finally:
        _putconn(conn)


def create_facilitator_conversation(event_id, host_id, subject, facilitator_ids,
                                    creator_type, creator_id, creator_name, first_body):
    init_facilitator_conversations()
    coord_user_id = resolve_main_coordinator()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO facilitator_conversations
                    (event_id, host_id, subject, status, created_by_type, created_by_id)
                VALUES (%s,%s,%s,%s,%s,%s)
                RETURNING conversation_id
            """, (event_id, host_id, subject, 'open', creator_type, creator_id))
            conv_id = cur.fetchone()[0]

            cur.execute("""
                INSERT INTO facilitator_conversation_messages
                    (conversation_id, sender_type, sender_id, sender_name, body)
                VALUES (%s,%s,%s,%s,%s)
            """, (conv_id, creator_type, creator_id, creator_name, first_body))

            cur.execute("""
                INSERT INTO facilitator_conversation_participants
                    (conversation_id, participant_type, participant_id, is_hidden)
                VALUES (%s,%s,%s,%s)
            """, (conv_id, 'host', str(host_id), 0))

            for fid in (facilitator_ids or []):
                cur.execute("""
                    INSERT INTO facilitator_conversation_participants
                        (conversation_id, participant_type, participant_id, is_hidden)
                    VALUES (%s,%s,%s,%s)
                """, (conv_id, 'facilitator', str(fid), 0))

            if coord_user_id is not None:
                cur.execute("""
                    INSERT INTO facilitator_conversation_participants
                        (conversation_id, participant_type, participant_id, is_hidden)
                    VALUES (%s,%s,%s,%s)
                """, (conv_id, 'coordinator', str(coord_user_id), 1))

        conn.commit()
        return conv_id
    finally:
        _putconn(conn)


def add_conversation_message(conversation_id, sender_type, sender_id, sender_name, body):
    init_facilitator_conversations()
    conn = get_connection()
    _execute(conn, """
        INSERT INTO facilitator_conversation_messages
            (conversation_id, sender_type, sender_id, sender_name, body)
        VALUES (%s,%s,%s,%s,%s)
    """, (conversation_id, sender_type, sender_id, sender_name, body))


def get_conversations_for_participant(participant_type, participant_id):
    init_facilitator_conversations()
    conn = get_connection()
    return _fetchall(conn, """
        SELECT c.*, e.event_name, h.name AS host_name
        FROM facilitator_conversations c
        JOIN facilitator_conversation_participants p
            ON p.conversation_id = c.conversation_id
        LEFT JOIN events e ON c.event_id = e.event_id
        LEFT JOIN hosts  h ON c.host_id  = h.host_id
        WHERE p.participant_type = %s AND p.participant_id = %s
        ORDER BY c.created_at DESC
    """, (participant_type, str(participant_id)))


def get_conversation_messages(conversation_id):
    init_facilitator_conversations()
    conn = get_connection()
    return _fetchall(conn, """
        SELECT * FROM facilitator_conversation_messages
        WHERE conversation_id = %s
        ORDER BY created_at ASC, id ASC
    """, (conversation_id,))


def get_visible_participants(conversation_id):
    init_facilitator_conversations()
    conn = get_connection()
    return _fetchall(conn, """
        SELECT * FROM facilitator_conversation_participants
        WHERE conversation_id = %s AND is_hidden = 0
        ORDER BY id ASC
    """, (conversation_id,))


def get_all_facilitator_conversations():
    init_facilitator_conversations()
    conn = get_connection()
    return _fetchall(conn, """
        SELECT c.*, e.event_name, h.name AS host_name
        FROM facilitator_conversations c
        LEFT JOIN events e ON c.event_id = e.event_id
        LEFT JOIN hosts  h ON c.host_id  = h.host_id
        ORDER BY c.created_at DESC
    """)
