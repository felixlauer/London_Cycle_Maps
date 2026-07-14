"""
Flask auth middleware: Supabase JWT verification + test-mode bypass.

Per request (init_auth registers a before_request hook):
  g.user_id       str | None — from the verified JWT `sub` claim ONLY
  g.test_mode     bool       — local Supabase bypass active
  g.profile_store ProfileStore — LocalJsonStore in test mode, else get_store()
  g.auth_mode     'test' | 'user' | 'guest' — for /route meta debugging

Test-mode failsafe: the bypass (X-Tuned-Test-Mode: 1 header) only works when
ALLOW_TEST_MODE=1 AND the request comes from localhost. A mis-set env var on a
production host can therefore never open the bypass remotely.

When changing behaviour, update 0_documentation/APP_MAIN.md.
"""
from __future__ import annotations

import os
from functools import wraps

from flask import g, jsonify, request

import profile_store

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass

TEST_MODE_HEADER = "X-Tuned-Test-Mode"
_LOCALHOST_ADDRS = ("127.0.0.1", "::1")
_jwks_client = None


def _get_jwks_client(supabase_url: str):
    global _jwks_client
    if _jwks_client is None:
        from jwt import PyJWKClient

        _jwks_client = PyJWKClient(
            f"{supabase_url}/auth/v1/.well-known/jwks.json",
            cache_keys=True,
        )
    return _jwks_client


def extract_bearer_token(req) -> str | None:
    header = req.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    token = header[len("Bearer "):].strip()
    return token or None


def verify_supabase_jwt(token: str) -> str | None:
    """Verified user id (sub claim) or None.

    New Supabase projects sign user access tokens with ES256 + JWKS
    (/.well-known/jwks.json). Legacy projects use HS256 + SUPABASE_JWT_SECRET.
    We try JWKS first, then fall back to the shared secret.
    """
    if not token:
        return None

    import jwt

    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    decode_opts = {"require": ["sub", "exp"]}

    # ES256 via JWKS (current Supabase default when JWT signing keys are enabled).
    if supabase_url:
        try:
            signing_key = _get_jwks_client(supabase_url).get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256"],
                audience="authenticated",
                issuer=f"{supabase_url}/auth/v1",
                options=decode_opts,
            )
            return claims.get("sub") or None
        except Exception:
            pass

    # Legacy HS256 shared secret (older projects).
    secret = os.environ.get("SUPABASE_JWT_SECRET", "")
    if not secret:
        return None
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience="authenticated",
            options=decode_opts,
        )
        return claims.get("sub") or None
    except Exception:
        return None


def is_test_mode_allowed(req) -> bool:
    """Bypass requires env opt-in AND the test header AND a localhost origin."""
    if os.environ.get("ALLOW_TEST_MODE", "0") != "1":
        return False
    if req.headers.get(TEST_MODE_HEADER) != "1":
        return False
    return req.remote_addr in _LOCALHOST_ADDRS


def init_auth(app) -> None:
    @app.before_request
    def _resolve_identity_and_store():
        if request.method == "OPTIONS":  # CORS preflight
            return
        if is_test_mode_allowed(request):
            g.test_mode = True
            g.user_id = None
            g.auth_mode = "test"
            g.profile_store = profile_store.get_local_store()
            return

        g.test_mode = False
        g.user_id = verify_supabase_jwt(extract_bearer_token(request))
        g.auth_mode = "user" if g.user_id else "guest"
        g.profile_store = profile_store.get_store()


def require_auth(fn):
    """401 unless authenticated — except in test mode (local JSON writes allowed)."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not g.get("test_mode") and g.get("user_id") is None:
            return jsonify({"error": "authentication required"}), 401
        return fn(*args, **kwargs)

    return wrapper


def assert_profile_access(profile: dict | None):
    """(error_response, status) or (None, None) for a fetched profile.

    Store queries already scope user rows to g.user_id, so a foreign profile id
    comes back as None — report 404 rather than leaking existence.
    """
    if profile is None:
        return jsonify({"error": "Profile not found"}), 404
    if not g.get("test_mode") and not profile.get("is_system") and g.get("user_id") is None:
        return jsonify({"error": "authentication required for custom profiles"}), 401
    return None, None
