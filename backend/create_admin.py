#!/usr/bin/env python3
"""
Bootstrap a super_admin account for the admin portal.

Usage:
    python create_admin.py admin@iny.health YourPassword123
    python create_admin.py admin@iny.health YourPassword123 --first "John" --last "Smith"
"""

import argparse
import sys
import os

# Add parent dir to path so we can import the app
sys.path.insert(0, os.path.dirname(__file__))

from app.admin_auth import bootstrap_super_admin


def main():
    parser = argparse.ArgumentParser(description="Create an admin portal super_admin account")
    parser.add_argument("email", help="Admin email address")
    parser.add_argument("password", help="Admin password")
    parser.add_argument("--first", default="Admin", help="First name")
    parser.add_argument("--last", default="User", help="Last name")
    args = parser.parse_args()

    user = bootstrap_super_admin(
        email=args.email,
        password=args.password,
        first_name=args.first,
        last_name=args.last,
    )
    print(f"\nAdmin account ready:")
    print(f"  Email: {user['email']}")
    print(f"  Role:  {user['role']}")
    print(f"  ID:    {user['id']}")
    print(f"\nYou can now log in at /admin/login")


if __name__ == "__main__":
    main()
