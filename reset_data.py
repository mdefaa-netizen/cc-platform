"""
Reset all platform data to a clean state.
Run this once before going live.
"""
import sqlite3, os

DB_PATH = "cc_platform.db"

def reset():
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
    print("\n✅ All data cleared. Platform is clean and ready.")

if __name__ == "__main__":
    reset()
