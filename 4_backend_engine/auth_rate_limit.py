"""
In-process sliding-window rate limits + failed-attempt lockouts for auth.

Industry-style defaults (tuned for a single Flask process; replace with Redis
in multi-instance production):

  * Per-IP cap across all sensitive auth endpoints
  * Per-email / per-user lockout after consecutive failures (login / password)

When changing thresholds, update 0_documentation/APP_MAIN.md.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after_s: int = 0
    message: str = ""


# IP-wide: all password / reset / signup traffic.
IP_WINDOW_S = 60
IP_MAX_REQUESTS = 30

# Failed logins / password verifies per email → lockout.
EMAIL_FAIL_WINDOW_S = 15 * 60
EMAIL_MAX_FAILURES = 5
EMAIL_LOCKOUT_S = 15 * 60

# Password-reset requests per email / IP.
RESET_EMAIL_WINDOW_S = 60 * 60
RESET_EMAIL_MAX = 3
RESET_IP_WINDOW_S = 60 * 60
RESET_IP_MAX = 10

# Signups per IP.
SIGNUP_IP_WINDOW_S = 60 * 60
SIGNUP_IP_MAX = 5

# Change-password / delete attempts per user id.
USER_SENSITIVE_WINDOW_S = 15 * 60
USER_SENSITIVE_MAX = 5

# Geocode proxy (Mapbox) — separate from auth so typing isn't throttled.
GEOCODE_IP_WINDOW_S = 60
GEOCODE_IP_MAX = 60

# Committed Get Route (purpose=commit) — does NOT cover background prefetch.
ROUTE_COMMIT_IP_WINDOW_S = 60
ROUTE_COMMIT_IP_MAX = 5

_lock = threading.Lock()
_ip_hits: dict[str, list[float]] = {}
_email_fails: dict[str, list[float]] = {}
_email_lockout_until: dict[str, float] = {}
_reset_email_hits: dict[str, list[float]] = {}
_reset_ip_hits: dict[str, list[float]] = {}
_signup_ip_hits: dict[str, list[float]] = {}
_user_sensitive_hits: dict[str, list[float]] = {}
_geocode_ip_hits: dict[str, list[float]] = {}
_route_commit_ip_hits: dict[str, list[float]] = {}


def _prune(timestamps: list[float], window_s: float, now: float) -> list[float]:
    cutoff = now - window_s
    return [t for t in timestamps if t >= cutoff]


def _client_ip(remote_addr: str | None, x_forwarded_for: str | None = None) -> str:
    """Prefer first X-Forwarded-For hop when behind a reverse proxy; else remote."""
    if x_forwarded_for:
        first = x_forwarded_for.split(",")[0].strip()
        if first:
            return first
    return (remote_addr or "unknown").strip() or "unknown"


def client_ip_from_request(req) -> str:
    return _client_ip(req.remote_addr, req.headers.get("X-Forwarded-For"))


def check_ip_auth_budget(ip: str) -> RateLimitResult:
    now = time.monotonic()
    with _lock:
        hits = _prune(_ip_hits.get(ip, []), IP_WINDOW_S, now)
        if len(hits) >= IP_MAX_REQUESTS:
            retry = max(1, int(IP_WINDOW_S - (now - hits[0])) + 1)
            return RateLimitResult(
                False,
                retry,
                f"Too many requests. Try again in {retry} seconds.",
            )
        hits.append(now)
        _ip_hits[ip] = hits
    return RateLimitResult(True)


def check_login_allowed(ip: str, email: str) -> RateLimitResult:
    email_l = (email or "").strip().lower()
    now = time.monotonic()
    ip_res = check_ip_auth_budget(ip)
    if not ip_res.allowed:
        return ip_res
    with _lock:
        until = _email_lockout_until.get(email_l, 0.0)
        if until > now:
            retry = max(1, int(until - now) + 1)
            return RateLimitResult(
                False,
                retry,
                f"Too many failed login attempts. Try again in {retry} seconds.",
            )
    return RateLimitResult(True)


def record_login_failure(email: str) -> RateLimitResult | None:
    """Record a failed login. Returns a lockout result if this failure trips the lock."""
    email_l = (email or "").strip().lower()
    if not email_l:
        return None
    now = time.monotonic()
    with _lock:
        fails = _prune(_email_fails.get(email_l, []), EMAIL_FAIL_WINDOW_S, now)
        fails.append(now)
        _email_fails[email_l] = fails
        if len(fails) >= EMAIL_MAX_FAILURES:
            _email_lockout_until[email_l] = now + EMAIL_LOCKOUT_S
            _email_fails[email_l] = []
            return RateLimitResult(
                False,
                EMAIL_LOCKOUT_S,
                f"Too many failed login attempts. Try again in {EMAIL_LOCKOUT_S} seconds.",
            )
    return None


def clear_login_failures(email: str) -> None:
    email_l = (email or "").strip().lower()
    with _lock:
        _email_fails.pop(email_l, None)
        _email_lockout_until.pop(email_l, None)


def check_reset_allowed(ip: str, email: str) -> RateLimitResult:
    email_l = (email or "").strip().lower()
    now = time.monotonic()
    ip_res = check_ip_auth_budget(ip)
    if not ip_res.allowed:
        return ip_res
    with _lock:
        e_hits = _prune(_reset_email_hits.get(email_l, []), RESET_EMAIL_WINDOW_S, now)
        if len(e_hits) >= RESET_EMAIL_MAX:
            retry = max(1, int(RESET_EMAIL_WINDOW_S - (now - e_hits[0])) + 1)
            return RateLimitResult(
                False,
                retry,
                f"Too many password-reset requests for this email. Try again in {retry} seconds.",
            )
        i_hits = _prune(_reset_ip_hits.get(ip, []), RESET_IP_WINDOW_S, now)
        if len(i_hits) >= RESET_IP_MAX:
            retry = max(1, int(RESET_IP_WINDOW_S - (now - i_hits[0])) + 1)
            return RateLimitResult(
                False,
                retry,
                f"Too many password-reset requests. Try again in {retry} seconds.",
            )
        e_hits.append(now)
        i_hits.append(now)
        _reset_email_hits[email_l] = e_hits
        _reset_ip_hits[ip] = i_hits
    return RateLimitResult(True)


def check_signup_allowed(ip: str) -> RateLimitResult:
    now = time.monotonic()
    ip_res = check_ip_auth_budget(ip)
    if not ip_res.allowed:
        return ip_res
    with _lock:
        hits = _prune(_signup_ip_hits.get(ip, []), SIGNUP_IP_WINDOW_S, now)
        if len(hits) >= SIGNUP_IP_MAX:
            retry = max(1, int(SIGNUP_IP_WINDOW_S - (now - hits[0])) + 1)
            return RateLimitResult(
                False,
                retry,
                f"Too many sign-up attempts. Try again in {retry} seconds.",
            )
        hits.append(now)
        _signup_ip_hits[ip] = hits
    return RateLimitResult(True)


def check_user_sensitive_allowed(user_id: str) -> RateLimitResult:
    uid = (user_id or "").strip()
    now = time.monotonic()
    with _lock:
        hits = _prune(_user_sensitive_hits.get(uid, []), USER_SENSITIVE_WINDOW_S, now)
        if len(hits) >= USER_SENSITIVE_MAX:
            retry = max(1, int(USER_SENSITIVE_WINDOW_S - (now - hits[0])) + 1)
            return RateLimitResult(
                False,
                retry,
                f"Too many account attempts. Try again in {retry} seconds.",
            )
        hits.append(now)
        _user_sensitive_hits[uid] = hits
    return RateLimitResult(True)


def check_geocode_allowed(ip: str) -> RateLimitResult:
    now = time.monotonic()
    with _lock:
        hits = _prune(_geocode_ip_hits.get(ip, []), GEOCODE_IP_WINDOW_S, now)
        if len(hits) >= GEOCODE_IP_MAX:
            retry = max(1, int(GEOCODE_IP_WINDOW_S - (now - hits[0])) + 1)
            return RateLimitResult(
                False,
                retry,
                f"Too many search requests. Try again in {retry} seconds.",
            )
        hits.append(now)
        _geocode_ip_hits[ip] = hits
    return RateLimitResult(True)


def check_route_commit_allowed(ip: str) -> RateLimitResult:
    """5 Get Route (purpose=commit) per IP per minute. Prefetch must not call this."""
    now = time.monotonic()
    with _lock:
        hits = _prune(_route_commit_ip_hits.get(ip, []), ROUTE_COMMIT_IP_WINDOW_S, now)
        if len(hits) >= ROUTE_COMMIT_IP_MAX:
            retry = max(1, int(ROUTE_COMMIT_IP_WINDOW_S - (now - hits[0])) + 1)
            return RateLimitResult(
                False,
                retry,
                f"Too many route requests. Try again in {retry} seconds.",
            )
        hits.append(now)
        _route_commit_ip_hits[ip] = hits
    return RateLimitResult(True)


def reset_for_tests() -> None:
    """Clear all buckets — unit tests only."""
    with _lock:
        _ip_hits.clear()
        _email_fails.clear()
        _email_lockout_until.clear()
        _reset_email_hits.clear()
        _reset_ip_hits.clear()
        _signup_ip_hits.clear()
        _user_sensitive_hits.clear()
        _geocode_ip_hits.clear()
        _route_commit_ip_hits.clear()
