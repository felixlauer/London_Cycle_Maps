"""
Supabase Auth helpers (service role + anon).

Service role:
  - email existence check, account deletion

Anon key (server-side only — never ship to the browser):
  - login / signup / password-reset email / refresh / password update

Rate limiting lives in auth_rate_limit.py and Flask routes.
"""
from __future__ import annotations

import os
from typing import Any

_service = None
_anon = None

MIN_PASSWORD_LEN = 6


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def configured() -> bool:
    return bool(_env("SUPABASE_URL") and _env("SUPABASE_SERVICE_ROLE_KEY"))


def anon_configured() -> bool:
    return bool(_env("SUPABASE_URL") and _anon_key())


def _anon_key() -> str:
    # Prefer dedicated backend env; fall back to service role never — wrong for grants.
    return _env("SUPABASE_ANON_KEY") or _env("SUPABASE_PUBLISHABLE_KEY")


def _service_client():
    global _service
    if _service is None:
        from supabase import create_client

        url = _env("SUPABASE_URL")
        key = _env("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            raise RuntimeError(
                "auth_admin requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY"
            )
        _service = create_client(url, key)
    return _service


def _anon_client():
    global _anon
    if _anon is None:
        from supabase import create_client

        url = _env("SUPABASE_URL")
        key = _anon_key()
        if not url or not key:
            raise RuntimeError(
                "auth_admin password ops require SUPABASE_URL and SUPABASE_ANON_KEY"
            )
        _anon = create_client(url, key)
    return _anon


def _user_email(user: Any) -> str | None:
    if user is None:
        return None
    if isinstance(user, dict):
        return user.get("email")
    return getattr(user, "email", None)


def _user_id(user: Any) -> str | None:
    if user is None:
        return None
    if isinstance(user, dict):
        return user.get("id")
    return getattr(user, "id", None)


def _session_dict(session: Any, user: Any = None) -> dict[str, Any] | None:
    if session is None:
        return None
    if isinstance(session, dict):
        access = session.get("access_token")
        refresh = session.get("refresh_token")
        expires_at = session.get("expires_at")
        expires_in = session.get("expires_in")
        u = session.get("user") or user
    else:
        access = getattr(session, "access_token", None)
        refresh = getattr(session, "refresh_token", None)
        expires_at = getattr(session, "expires_at", None)
        expires_in = getattr(session, "expires_in", None)
        u = getattr(session, "user", None) or user
    if not access or not refresh:
        return None
    return {
        "access_token": access,
        "refresh_token": refresh,
        "expires_at": expires_at,
        "expires_in": expires_in,
        "user": {
            "id": _user_id(u),
            "email": _user_email(u),
        },
    }


def user_exists_by_email(email: str) -> bool:
    """True if auth.users has a row for this email (case-insensitive)."""
    email = (email or "").strip()
    if not email:
        return False

    client = _service_client()

    try:
        resp = client.rpc("user_exists_by_email", {"check_email": email}).execute()
        data = resp.data
        if isinstance(data, bool):
            return data
        if isinstance(data, list) and data:
            return bool(data[0])
    except Exception:
        pass

    email_l = email.lower()
    page = 1
    while page <= 20:
        result = client.auth.admin.list_users(page=page, per_page=100)
        if isinstance(result, list):
            users = result
        elif isinstance(result, dict):
            users = result.get("users") or []
        else:
            users = getattr(result, "users", None) or []
        if not users:
            break
        for user in users:
            uemail = _user_email(user)
            if uemail and str(uemail).lower() == email_l:
                return True
        if len(users) < 100:
            break
        page += 1
    return False


def delete_user(user_id: str) -> None:
    client = _service_client()
    client.auth.admin.delete_user(user_id)


def sign_in(email: str, password: str) -> tuple[dict | None, str | None]:
    """Returns (session_dict, error_message)."""
    try:
        resp = _anon_client().auth.sign_in_with_password(
            {"email": email.strip(), "password": password}
        )
    except Exception as e:
        return None, str(e) or "Invalid email or password."
    session = getattr(resp, "session", None) or (resp.get("session") if isinstance(resp, dict) else None)
    user = getattr(resp, "user", None) or (resp.get("user") if isinstance(resp, dict) else None)
    payload = _session_dict(session, user)
    if not payload:
        return None, "Invalid email or password."
    return payload, None


def sign_up(email: str, password: str) -> tuple[dict | None, str | None, bool]:
    """Returns (session_or_none, error, needs_email_confirm)."""
    if len(password) < MIN_PASSWORD_LEN:
        return None, f"Password must be at least {MIN_PASSWORD_LEN} characters.", False
    try:
        resp = _anon_client().auth.sign_up(
            {"email": email.strip(), "password": password}
        )
    except Exception as e:
        return None, str(e), False
    session = getattr(resp, "session", None) or (resp.get("session") if isinstance(resp, dict) else None)
    user = getattr(resp, "user", None) or (resp.get("user") if isinstance(resp, dict) else None)
    error = getattr(resp, "error", None)
    if error:
        msg = getattr(error, "message", None) or str(error)
        return None, msg, False
    payload = _session_dict(session, user)
    needs_confirm = payload is None
    return payload, None, needs_confirm


def send_password_reset(email: str, redirect_to: str) -> str | None:
    """Returns error message or None on success."""
    try:
        _anon_client().auth.reset_password_for_email(
            email.strip(),
            {"redirect_to": redirect_to},
        )
    except Exception as e:
        return str(e)
    return None


def refresh_session(refresh_token: str) -> tuple[dict | None, str | None]:
    try:
        resp = _anon_client().auth.refresh_session(refresh_token)
    except Exception as e:
        return None, str(e) or "Session refresh failed."
    session = getattr(resp, "session", None) or (resp.get("session") if isinstance(resp, dict) else None)
    user = getattr(resp, "user", None) or (resp.get("user") if isinstance(resp, dict) else None)
    payload = _session_dict(session, user)
    if not payload:
        return None, "Session refresh failed."
    return payload, None


def update_password_with_access_token(access_token: str, new_password: str) -> str | None:
    """Update password for the user owning access_token. Returns error or None."""
    if len(new_password) < MIN_PASSWORD_LEN:
        return f"Password must be at least {MIN_PASSWORD_LEN} characters."
    from auth_middleware import verify_supabase_jwt

    uid = verify_supabase_jwt(access_token)
    if not uid:
        return "Invalid or expired session."
    try:
        _service_client().auth.admin.update_user_by_id(uid, {"password": new_password})
    except Exception as e:
        return str(e) or "Could not update password."
    return None


def change_password(email: str, current_password: str, new_password: str) -> str | None:
    """Verify current password then set new one. Returns error or None."""
    if len(new_password) < MIN_PASSWORD_LEN:
        return f"Password must be at least {MIN_PASSWORD_LEN} characters."
    if current_password == new_password:
        return "New password must be different from your current password."
    session, err = sign_in(email, current_password)
    if err or not session:
        return "Current password is incorrect."
    uid = (session.get("user") or {}).get("id")
    if not uid:
        return "Could not update password."
    try:
        _service_client().auth.admin.update_user_by_id(uid, {"password": new_password})
    except Exception as e:
        return str(e) or "Could not update password."
    return None
