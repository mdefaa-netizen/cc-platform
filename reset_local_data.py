"""
Reset all LOCAL SQLite platform data to a clean state.

This script ONLY wipes the local cc_platform.db file. It does NOT touch
the Postgres / Supabase production database. To reset Postgres, use the
Supabase dashboard SQL editor or write a separate Postgres-aware script.

Usage:
    python reset_local_data.py --confirm

You will then be prompted to type 'WIPE-LOCAL' to proceed.
"""
import sqlite3
import sys
import os

DB_PATH = "cc_platform.db"


def reset():
    abs_path = os.path.abspath(DB_PATH)
    print(f"[SCOPE] Targeting LOCAL SQLite file: {abs_path}", file=sys.stderr)
    print(
        "[SCOPE] This script CANNOT touch Postgres / Supabase.",
        file=sys.stderr,
    )
    try:
        response = input("Type 'WIPE-LOCAL' to confirm, anything else to abort: ")
    except EOFError:
        response = ""
    if response.strip() != "WIPE-LOCAL":
        print("Aborted.", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    tables = [
        "event_facilitators",
        "communications",
        "feedback",
        "tasks",
        "messages",
        "notifications",
        "activity_log",
        "portal_access",
        "reports",
        "events",
        "hosts",
        "facilitators",
        "nhh_colleagues",
        "cdfa_colleagues",
    ]
    print("Clearing all data...\n")
    for t in tables:
        try:
            conn.execute(f"DELETE FROM {t}")
            conn.execute(f"DELETE FROM sqlite_sequence WHERE name='{t}'")
            print(f"  Cleared: {t}")
        except Exception as e:
            print(f"  Skipped: {t} ({e})")
    conn.commit()
    conn.close()
    print("\n✅ All LOCAL data cleared.")


def main():
    if "--confirm" not in sys.argv[1:]:
        print(
            "ERROR: This script requires the --confirm flag to run.",
            file=sys.stderr,
        )
        print(
            "Usage: python reset_local_data.py --confirm",
            file=sys.stderr,
        )
        print(
            "(Renamed from reset_data.py — only wipes local SQLite, never Postgres.)",
            file=sys.stderr,
        )
        sys.exit(1)
    reset()


if __name__ == "__main__":
    main()
