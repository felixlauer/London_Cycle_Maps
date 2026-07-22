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
MAX_DISPLAY_NAME_LEN = 80


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def normalize_display_name(value: Any) -> tuple[str | None, str | None]:
    """
    Returns (normalized_or_None, error).
    Empty / whitespace → None (allowed; existing accounts stay nameless).
    """
    if value is None:
        return None, None
    name = str(value).strip()
    if not name:
        return None, None
    if len(name) > MAX_DISPLAY_NAME_LEN:
        return None, f"Name must be at most {MAX_DISPLAY_NAME_LEN} characters."
    return name, None


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


def _user_metadata(user: Any) -> dict:
    if user is None:
        return {}
    if isinstance(user, dict):
        meta = user.get("user_metadata") or user.get("raw_user_meta_data") or {}
    else:
        meta = getattr(user, "user_metadata", None) or getattr(user, "raw_user_meta_data", None) or {}
    return meta if isinstance(meta, dict) else {}


def _user_display_name(user: Any) -> str | None:
    meta = _user_metadata(user)
    raw = meta.get("display_name")
    if raw is None:
        return None
    name = str(raw).strip()
    return name or None


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
            "display_name": _user_display_name(u),
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


def sign_up(
    email: str,
    password: str,
    display_name: str | None = None,
) -> tuple[dict | None, str | None, bool]:
    """Returns (session_or_none, error, needs_email_confirm)."""
    if len(password) < MIN_PASSWORD_LEN:
        return None, f"Password must be at least {MIN_PASSWORD_LEN} characters.", False
    name, name_err = normalize_display_name(display_name)
    if name_err:
        return None, name_err, False
    payload_in: dict[str, Any] = {
        "email": email.strip(),
        "password": password,
    }
    if name is not None:
        payload_in["options"] = {"data": {"display_name": name}}
    try:
        resp = _anon_client().auth.sign_up(payload_in)
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


def update_display_name(user_id: str, display_name: Any) -> tuple[str | None, str | None]:
    """
    Set or clear display_name in auth user_metadata.
    Returns (normalized_display_name_or_None, error).
    """
    name, err = normalize_display_name(display_name)
    if err:
        return None, err
    uid = (user_id or "").strip()
    if not uid:
        return None, "authentication required."
    try:
        # Empty string clears the field for existing test accounts that set a name later.
        _service_client().auth.admin.update_user_by_id(
            uid,
            {"user_metadata": {"display_name": name or ""}},
        )
    except Exception as e:
        return None, str(e) or "Could not update name."
    return name, None


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
