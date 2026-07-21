"""
Persistent Mapbox usage counters (monthly UTC) with hard cutoffs.

Tracks:
  * Search Box sessions — unique session_token values that hit Flask /geocode/*
    (matches Mapbox Search Box session billing: one UUID focus session).
  * Web map loads — client reports when the planning Map mounts (matches
    Mapbox GL JS "map load" when our app actually initializes Map).

Persists to a JSON file (survives restarts / 24/7 hosting). Caps default to
~90% of Mapbox free tiers so Mapbox dashboard stays below the paid cliff.

Free tiers (confirm at mapbox.com/pricing):
  Search Box sessions (intro): 500 / month
  Mapbox GL JS map loads:      50_000 / month

Env:
  MAPBOX_USAGE_PATH              — JSON file path (default next to this module)
  MAPBOX_SEARCH_SESSION_LIMIT    — hard cut (default 450 = 500 − 50 buffer)
  MAPBOX_MAP_LOAD_LIMIT          — hard cut (default 45000 = 50k − 5k buffer)
  MAPBOX_SEARCH_SESSIONS_USED    — seed when creating a new month file (align to
                                   Mapbox dashboard; default 0)
  MAPBOX_MAP_LOADS_USED          — same for map loads seed (default 0)
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Mapbox published free tiers (safety buffer applied via LIMIT defaults).
FREE_SEARCH_SESSIONS = 500
FREE_MAP_LOADS = 50_000

DEFAULT_SEARCH_LIMIT = 450   # ~10% buffer under 500
DEFAULT_MAP_LIMIT = 45_000   # ~10% buffer under 50_000

_lock = threading.Lock()
_path_override: Path | None = None


@dataclass(frozen=True)
class QuotaResult:
    allowed: bool
    month: str
    used: int
    limit: int
    remaining: int
    message: str = ""


def _usage_path() -> Path:
    if _path_override is not None:
        return _path_override
    env = (os.environ.get("MAPBOX_USAGE_PATH") or "").strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parent / "mapbox_usage.json"


def _month_key(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


def _limits() -> tuple[int, int]:
    search = int(os.environ.get("MAPBOX_SEARCH_SESSION_LIMIT", str(DEFAULT_SEARCH_LIMIT)))
    maps = int(os.environ.get("MAPBOX_MAP_LOAD_LIMIT", str(DEFAULT_MAP_LIMIT)))
    return max(0, search), max(0, maps)


def _seed_counts() -> tuple[int, int]:
    s = int(os.environ.get("MAPBOX_SEARCH_SESSIONS_USED", "0"))
    m = int(os.environ.get("MAPBOX_MAP_LOADS_USED", "0"))
    return max(0, s), max(0, m)


def _empty_state(month: str) -> dict[str, Any]:
    search_seed, map_seed = _seed_counts()
    return {
        "month": month,
        "search_sessions": search_seed,
        "map_loads": map_seed,
        "session_ids": [],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _load_unlocked(path: Path) -> dict[str, Any]:
    month = _month_key()
    if not path.exists():
        return _empty_state(month)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return _empty_state(month)
    if not isinstance(data, dict) or data.get("month") != month:
        # New calendar month (UTC) — reset counters; seeds only for brand-new files.
        return {
            "month": month,
            "search_sessions": 0,
            "map_loads": 0,
            "session_ids": [],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    data.setdefault("search_sessions", 0)
    data.setdefault("map_loads", 0)
    data.setdefault("session_ids", [])
    if not isinstance(data["session_ids"], list):
        data["session_ids"] = []
    return data


def _save_unlocked(path: Path, data: dict[str, Any]) -> None:
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def snapshot() -> dict[str, Any]:
    """Current usage vs limits (read-only; creates/rolls file if needed)."""
    search_limit, map_limit = _limits()
    path = _usage_path()
    with _lock:
        data = _load_unlocked(path)
        _save_unlocked(path, data)
        search_used = int(data["search_sessions"])
        map_used = int(data["map_loads"])
        month = data["month"]
    return {
        "month": month,
        "search_sessions": search_used,
        "search_limit": search_limit,
        "search_remaining": max(0, search_limit - search_used),
        "search_allowed": search_used < search_limit,
        "map_loads": map_used,
        "map_limit": map_limit,
        "map_remaining": max(0, map_limit - map_used),
        "map_allowed": map_used < map_limit,
        "free_tier": {
            "search_sessions": FREE_SEARCH_SESSIONS,
            "map_loads": FREE_MAP_LOADS,
        },
        "path": str(path),
    }


def check_search_session(session_token: str) -> QuotaResult:
    """
    Allow continuing an already-counted session_token even at the limit.
    Block brand-new session_tokens once at hard cut (before calling Mapbox).
    """
    token = (session_token or "").strip()
    search_limit, _ = _limits()
    path = _usage_path()
    with _lock:
        data = _load_unlocked(path)
        used = int(data["search_sessions"])
        ids: list[str] = list(data.get("session_ids") or [])
        if token and token in ids:
            return QuotaResult(
                allowed=True,
                month=data["month"],
                used=used,
                limit=search_limit,
                remaining=max(0, search_limit - used),
            )
        if used >= search_limit:
            return QuotaResult(
                allowed=False,
                month=data["month"],
                used=used,
                limit=search_limit,
                remaining=0,
                message=(
                    f"Mapbox Search monthly limit reached ({used}/{search_limit}). "
                    "Try again next month."
                ),
            )
        return QuotaResult(
            allowed=True,
            month=data["month"],
            used=used,
            limit=search_limit,
            remaining=max(0, search_limit - used),
        )


def record_search_session(session_token: str) -> QuotaResult:
    """Count session_token once (after a successful Mapbox suggest/retrieve)."""
    token = (session_token or "").strip()
    if not token:
        return check_search_session("")
    search_limit, _ = _limits()
    path = _usage_path()
    with _lock:
        data = _load_unlocked(path)
        ids: list[str] = list(data.get("session_ids") or [])
        used = int(data["search_sessions"])
        if token in ids:
            return QuotaResult(
                True, data["month"], used, search_limit, max(0, search_limit - used)
            )
        if used >= search_limit:
            return QuotaResult(
                False,
                data["month"],
                used,
                search_limit,
                0,
                message=(
                    f"Mapbox Search monthly limit reached ({used}/{search_limit}). "
                    "Try again next month."
                ),
            )
        ids.append(token)
        # Cap stored ids to limit size (enough to remember counted sessions).
        if len(ids) > max(search_limit * 2, 1000):
            ids = ids[-search_limit:]
        data["session_ids"] = ids
        data["search_sessions"] = used + 1
        _save_unlocked(path, data)
        used = int(data["search_sessions"])
        return QuotaResult(
            True, data["month"], used, search_limit, max(0, search_limit - used)
        )


def try_consume_map_load() -> QuotaResult:
    """Atomically reserve one map load; deny at hard cut."""
    _, map_limit = _limits()
    path = _usage_path()
    with _lock:
        data = _load_unlocked(path)
        used = int(data["map_loads"])
        if used >= map_limit:
            return QuotaResult(
                allowed=False,
                month=data["month"],
                used=used,
                limit=map_limit,
                remaining=0,
                message=(
                    f"Mapbox map-load monthly limit reached ({used}/{map_limit}). "
                    "Try again next month."
                ),
            )
        data["map_loads"] = used + 1
        _save_unlocked(path, data)
        used = int(data["map_loads"])
        return QuotaResult(
            True, data["month"], used, map_limit, max(0, map_limit - used)
        )


def check_map_load() -> QuotaResult:
    """Read-only map quota (no increment)."""
    _, map_limit = _limits()
    path = _usage_path()
    with _lock:
        data = _load_unlocked(path)
        used = int(data["map_loads"])
        ok = used < map_limit
        return QuotaResult(
            allowed=ok,
            month=data["month"],
            used=used,
            limit=map_limit,
            remaining=max(0, map_limit - used),
            message=(
                "" if ok else (
                    f"Mapbox map-load monthly limit reached ({used}/{map_limit}). "
                    "Try again next month."
                )
            ),
        )
