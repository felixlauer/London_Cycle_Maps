"""
Aggregate product metrics: website sessions, routes computed, optimised
distance, and distinct clients that committed a route.

Persists to Supabase (service role) when configured; otherwise a local JSON file
for single-process dev. Failures never raise — callers should treat metrics as
best-effort so routing stays up if Supabase is down.

Writes are fire-and-forget (daemon thread) so /mapbox/map_load and /route never
block on Supabase latency.

Client uniqueness is HMAC-SHA256(ip, salt) truncated to 16 bytes. Raw IPs are
never stored. snapshot() and print_app_metrics expose only the integer count.

When changing schema, update supabase_sql/migrations/004_app_metrics.sql
and 006_app_metrics_unique_clients.sql.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("app_metrics")

_LOCAL_PATH = Path(__file__).resolve().parent / "app_metrics.json"
_lock = threading.Lock()
_path_override: Path | None = None

# 16 bytes / 32 hex chars. Not a user id — only a membership key for the count.
_CLIENT_HASH_HEX_LEN = 32
_DEFAULT_CLIENT_SALT = "tuned-app-metrics-client-v1"
_SKIP_IPS = frozenset({"", "unknown"})


def _supabase_configured() -> bool:
    return bool(
        (os.environ.get("SUPABASE_URL") or "").strip()
        and (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    )


def _local_path() -> Path:
    return _path_override if _path_override is not None else _LOCAL_PATH


def _client_salt() -> bytes:
    return (
        os.environ.get("APP_METRICS_CLIENT_SALT") or _DEFAULT_CLIENT_SALT
    ).encode("utf-8")


def client_hash_hex(ip: str | None) -> str | None:
    """Hex digest for a client IP, or None when the address is unusable."""
    raw = (ip or "").strip().lower()
    if raw in _SKIP_IPS:
        return None
    digest = hmac.new(_client_salt(), raw.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:_CLIENT_HASH_HEX_LEN]


def _empty_state() -> dict[str, Any]:
    return {
        "sessions": 0,
        "routes_computed": 0,
        "optimized_distance_m": 0.0,
        "unique_route_clients": 0,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _public_state(data: dict[str, Any]) -> dict[str, Any]:
    """Counts only — never hashes, IPs, or other membership keys."""
    return {
        "sessions": max(0, int(data.get("sessions") or 0)),
        "routes_computed": max(0, int(data.get("routes_computed") or 0)),
        "optimized_distance_m": max(0.0, float(data.get("optimized_distance_m") or 0)),
        "unique_route_clients": max(0, int(data.get("unique_route_clients") or 0)),
        "updated_at": str(data.get("updated_at") or datetime.now(timezone.utc).isoformat()),
    }


def _load_local_unlocked(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError, TypeError):
        return _empty_state()
    if not isinstance(data, dict):
        return _empty_state()
    out = _empty_state()
    out["sessions"] = max(0, int(data.get("sessions") or 0))
    out["routes_computed"] = max(0, int(data.get("routes_computed") or 0))
    out["optimized_distance_m"] = max(0.0, float(data.get("optimized_distance_m") or 0))
    hashes: list[str] = []
    raw_hashes = data.get("client_hashes")
    if isinstance(raw_hashes, list):
        seen: set[str] = set()
        for item in raw_hashes:
            if not isinstance(item, str):
                continue
            h = item.strip().lower()
            if len(h) != _CLIENT_HASH_HEX_LEN or h in seen:
                continue
            seen.add(h)
            hashes.append(h)
    out["client_hashes"] = hashes
    stored_unique = max(0, int(data.get("unique_route_clients") or 0))
    out["unique_route_clients"] = max(stored_unique, len(hashes))
    if data.get("updated_at"):
        out["updated_at"] = str(data["updated_at"])
    return out


def _save_local_unlocked(path: Path, data: dict[str, Any]) -> None:
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    hashes = data.get("client_hashes") or []
    if not isinstance(hashes, list):
        hashes = []
    payload = {
        "sessions": max(0, int(data.get("sessions") or 0)),
        "routes_computed": max(0, int(data.get("routes_computed") or 0)),
        "optimized_distance_m": max(0.0, float(data.get("optimized_distance_m") or 0)),
        "unique_route_clients": max(0, int(data.get("unique_route_clients") or 0)),
        "client_hashes": hashes,
        "updated_at": data["updated_at"],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _supabase_client():
    """Import the real supabase package (not a local migrations folder)."""
    import sys

    # A local ./supabase directory (migrations) can shadow the installed package.
    here = str(Path(__file__).resolve().parent)
    removed: list[tuple[int, str]] = []
    for i, p in list(enumerate(sys.path)):
        try:
            if p in ("", ".") or os.path.abspath(p or ".") == here:
                removed.append((i, p))
        except OSError:
            continue
    for i, _ in reversed(removed):
        sys.path.pop(i)
    try:
        from supabase import create_client
    finally:
        for i, p in removed:
            sys.path.insert(i, p)

    return create_client(
        os.environ["SUPABASE_URL"].rstrip("/"),
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )


def _spawn(fn, *args, **kwargs) -> None:
    threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True).start()


def _record_session_sync() -> None:
    try:
        if _supabase_configured():
            _supabase_client().rpc("app_metrics_record_session").execute()
            return
        path = _local_path()
        with _lock:
            data = _load_local_unlocked(path)
            data["sessions"] = int(data["sessions"]) + 1
            _save_local_unlocked(path, data)
    except Exception as exc:
        log.warning("app_metrics.record_session failed: %s", exc)


def _record_route_sync(
    *,
    optimized_distance_m: float,
    client_ip: str | None = None,
) -> None:
    try:
        dist = max(0.0, float(optimized_distance_m or 0.0))
    except (TypeError, ValueError):
        dist = 0.0
    digest = client_hash_hex(client_ip)
    try:
        if _supabase_configured():
            params: dict[str, Any] = {"p_distance_m": dist}
            if digest:
                params["p_client_hash"] = digest
            _supabase_client().rpc("app_metrics_record_route", params).execute()
            return
        path = _local_path()
        with _lock:
            data = _load_local_unlocked(path)
            data["routes_computed"] = int(data["routes_computed"]) + 1
            data["optimized_distance_m"] = float(data["optimized_distance_m"]) + dist
            if digest:
                hashes = data.setdefault("client_hashes", [])
                if digest not in hashes:
                    hashes.append(digest)
                    data["unique_route_clients"] = len(hashes)
            _save_local_unlocked(path, data)
    except Exception as exc:
        log.warning("app_metrics.record_route failed: %s", exc)


def record_session() -> None:
    """+1 website session (wired to successful map load / site open). Non-blocking."""
    _spawn(_record_session_sync)


def record_route(
    *,
    optimized_distance_m: float,
    client_ip: str | None = None,
) -> None:
    """+1 route + optimised path length (metres). Non-blocking.

    client_ip is hashed immediately and discarded; the same address is counted
    at most once toward unique_route_clients.
    """
    _spawn(
        _record_route_sync,
        optimized_distance_m=optimized_distance_m,
        client_ip=client_ip,
    )


def snapshot() -> dict[str, Any]:
    """Read current totals (creates local file if needed)."""
    try:
        if _supabase_configured():
            res = (
                _supabase_client()
                .table("app_metrics")
                .select(
                    "sessions,routes_computed,optimized_distance_m,"
                    "unique_route_clients,updated_at"
                )
                .eq("id", 1)
                .limit(1)
                .execute()
            )
            row = (res.data or [None])[0]
            if not row:
                return _empty_state()
            return {
                **_public_state(row),
                "backend": "supabase",
            }
        path = _local_path()
        with _lock:
            data = _load_local_unlocked(path)
            _save_local_unlocked(path, data)
            return {**_public_state(data), "backend": "local", "path": str(path)}
    except Exception as exc:
        log.warning("app_metrics.snapshot failed: %s", exc)
        return {**_empty_state(), "error": str(exc)}
