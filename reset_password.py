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
