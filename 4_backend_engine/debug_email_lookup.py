#!/usr/bin/env python3
"""One-off diagnostic for auth email lookup. Usage: python debug_email_lookup.py [email]"""
import os
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

import auth_admin


def main() -> None:
    email = sys.argv[1] if len(sys.argv) > 1 else ""
    print("configured:", auth_admin.configured())
    client = auth_admin._service_client()

    if email:
        print("checking:", email)
        print("user_exists_by_email:", auth_admin.user_exists_by_email(email))

    print("\n--- RPC probe ---")
    try:
        r = client.rpc("user_exists_by_email", {"check_email": email or "nobody@example.com"}).execute()
        print("RPC data:", repr(r.data), type(r.data))
    except Exception as e:
        print("RPC error:", type(e).__name__, e)

    print("\n--- list_users probe ---")
    try:
        result = client.auth.admin.list_users(page=1, per_page=20)
        print("result type:", type(result))
        users = getattr(result, "users", None)
        if users is None and isinstance(result, dict):
            users = result.get("users")
        if users is None and isinstance(result, list):
            users = result
        print("user count:", len(users or []))
        for u in users or []:
            em = getattr(u, "email", None) or (u.get("email") if isinstance(u, dict) else None)
            print(" -", em)
    except Exception as e:
        print("list_users error:", type(e).__name__, e)


if __name__ == "__main__":
    main()
