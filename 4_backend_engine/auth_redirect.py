"""Auth redirect allowlists and related prod guards."""
from __future__ import annotations

import os
from urllib.parse import urlparse


def _env_list(name: str) -> list[str]:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def reset_redirect_allowed(redirect_to: str) -> bool:
    """True if redirect_to may be passed to Supabase password-reset.

    AUTH_RESET_REDIRECT_ALLOWLIST = comma-separated URL prefixes
    (e.g. https://app.tunedcycling.online).

    When unset: only http://localhost and http://127.0.0.1 (any port) for local dev.
    """
    url = (redirect_to or "").strip()
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    if not parsed.netloc:
        return False

    allow = _env_list("AUTH_RESET_REDIRECT_ALLOWLIST")
    if not allow:
        host = parsed.hostname or ""
        return host in ("localhost", "127.0.0.1")

    return any(url.startswith(prefix) for prefix in allow)
