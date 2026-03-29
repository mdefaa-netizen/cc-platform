"""
Cleanup script for Supabase PostgreSQL database.
Drops and recreates the activity_log table cleanly.

Usage:
    pip install psycopg2-binary
    python cleanup_supabase.py
"""

import sys

try:
    import psycopg2
except ImportError:
    print("psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)

# Read DATABASE_URL from .streamlit/secrets.toml
def get_database_url():
    import tomllib
    with open(".streamlit/secrets.toml", "rb") as f:
        secrets = tomllib.load(f)
    url = secrets.get("DATABASE_URL", "")
    if not url:
        print("ERROR: DATABASE_URL not found in .streamlit/secrets.toml")
        sys.exit(1)
    return url


def main():
    db_url = get_database_url()
    print(f"Connecting to Supabase: {db_url[:40]}...")

    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cur = conn.cursor()

    # Check if activity_log exists and show row count
    cur.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'activity_log'
        )
    """)
    exists = cur.fetchone()[0]

    if exists:
        cur.execute("SELECT COUNT(*) FROM activity_log")
        count = cur.fetchone()[0]
        print(f"activity_log exists with {count} row(s).")
    else:
        print("activity_log does not exist yet.")

    # Drop and recreate
    print("Dropping activity_log...")
    cur.execute("DROP TABLE IF EXISTS activity_log")

    print("Recreating activity_log...")
    cur.execute("""
        CREATE TABLE activity_log (
            log_id SERIAL PRIMARY KEY,
            action TEXT NOT NULL,
            details TEXT,
            "user" TEXT DEFAULT 'Coordinator',
            logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    print("Done. activity_log is now clean and empty.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
