#!/usr/bin/env python3
"""
One-time password reset utility for CC Platform.

Usage:
    python reset_password.py <email> <new_password>

Example:
    python reset_password.py mdefaa@gmail.com MyNewSecurePassword123
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))


def _resolve_backend_for_banner():
    """Mirror utils.auth._backend() resolution.

    Returns (backend_name, target) where backend_name is 'postgres' or
    'sqlite' and target is the hostname (Postgres) or the SQLite file path.
    Runs BEFORE any DB import so the user can abort without touching
    either backend.
    """
    db_url = None
    try:
        import streamlit as _st
        db_url = _st.secrets.get("DATABASE_URL")
    except Exception:
        db_url = None
    if not db_url:
        db_url = os.environ.get("DATABASE_URL")
    if db_url:
        import urllib.parse
        host = urllib.parse.urlparse(db_url).hostname or "<unparseable>"
        return ("postgres", host)
    return ("sqlite", "./cc_platform.db")


def main():
    if len(sys.argv) != 3:
        print("Usage: python reset_password.py <email> <new_password>")
        print("Example: python reset_password.py mdefaa@gmail.com MyNewSecurePassword123")
        sys.exit(1)

    email = sys.argv[1].strip().lower()
    new_password = sys.argv[2]

    if len(new_password) < 8:
        print("Error: Password must be at least 8 characters.")
        sys.exit(1)

    backend, target = _resolve_backend_for_banner()
    if backend == "postgres":
        print(f"[BACKEND] Targeting Postgres pooler (host={target})", file=sys.stderr)
    else:
        print(
            f"[BACKEND] Targeting LOCAL SQLite ({target}) — "
            f"set DATABASE_URL to target Postgres before continuing",
            file=sys.stderr,
        )
        try:
            response = input("Type 'CONFIRM-LOCAL' to continue, anything else to abort: ")
        except EOFError:
            response = ""
        if response.strip() != "CONFIRM-LOCAL":
            print("Aborted.", file=sys.stderr)
            sys.exit(1)

    from utils.auth import get_user_by_email, reset_user_password, ROLE_LABELS

    user = get_user_by_email(email)
    if not user:
        print(f"Error: User '{email}' not found.")
        from utils.auth import list_users
        print("\nExisting users:")
        for u in list_users():
            print(f"  - {u['email']} ({ROLE_LABELS.get(u['role'], u['role'])})")
        sys.exit(1)

    reset_user_password(email, new_password)
    print(f"Password reset successfully for '{email}' ({ROLE_LABELS.get(user['role'], user['role'])}).")
    print("\nYou can now sign in with:")
    print(f"  Email:    {email}")
    print(f"  Password: {new_password}")


if __name__ == "__main__":
    main()
