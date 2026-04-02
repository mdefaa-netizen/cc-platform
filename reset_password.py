#!/usr/bin/env python3
"""
One-time password reset utility for CC Platform.

Run this script to reset a user's password when you cannot log in to the app.

Usage:
    python reset_password.py <username> <new_password>

Examples:
    python reset_password.py coordinator MyNewSecurePassword123
    python reset_password.py nhh NewNHHPassword456
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

def main():
    if len(sys.argv) != 3:
        print("Usage: python reset_password.py <username> <new_password>")
        print("Example: python reset_password.py coordinator MyNewSecurePassword123")
        sys.exit(1)

    username = sys.argv[1].strip().lower()
    new_password = sys.argv[2]

    if len(new_password) < 8:
        print("Error: Password must be at least 8 characters.")
        sys.exit(1)

    from utils.database import get_user_by_username, hash_password, get_connection

    user = get_user_by_username(username)
    if not user:
        print(f"Error: User '{username}' not found.")
        print("\nExisting users:")
        conn = get_connection()
        rows = conn.execute("SELECT username, role FROM users").fetchall()
        conn.close()
        for r in rows:
            print(f"  - {r['username']} ({r['role']})")
        sys.exit(1)

    conn = get_connection()
    conn.execute("UPDATE users SET password_hash=? WHERE username=?",
                 (hash_password(new_password), username))
    conn.commit()
    conn.close()

    print(f"Password reset successfully for '{username}' ({user['role']}).")
    print(f"\nYou can now sign in with:")
    print(f"  Username: {username}")
    print(f"  Password: {new_password}")

if __name__ == "__main__":
    main()
