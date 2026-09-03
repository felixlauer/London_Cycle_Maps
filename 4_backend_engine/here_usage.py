"""
Persistent HERE Geocoding & Search call counters (monthly UTC) with hard cuts.

Each Autosuggest or Lookup HTTP request is one HERE transaction. Caps default
to ~90% of the pay-as-you-go free tier so the HERE dashboard stays below the
paid cliff.

Free tier (confirm at here.com pricing):
  Geocoding & Search transactions: 250_000 / month

Env:
  HERE_USAGE_PATH           — JSON file path (default next to this module)
  HERE_SEARCH_CALL_LIMIT    — hard cut (default 225000 = 250k − 25k buffer)
  HERE_SEARCH_CALLS_USED    — seed when creating a new month file (default 0)
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FREE_SEARCH_CALLS = 250_000
DEFAULT_SEARCH_LIMIT = 225_000  # ~10% buffer under 250k

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
    env = (os.environ.get("HERE_USAGE_PATH") or "").strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parent / "here_usage.json"


def _month_key(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


def _limit() -> int:
    return max(0, int(os.environ.get("HERE_SEARCH_CALL_LIMIT", str(DEFAULT_SEARCH_LIMIT))))


def _seed() -> int:
    return max(0, int(os.environ.get("HERE_SEARCH_CALLS_USED", "0")))


def _empty_state(month: str) -> dict[str, Any]:
    return {
        "month": month,
        "search_calls": _seed(),
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
        return {
            "month": month,
            "search_calls": 0,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    data.setdefault("search_calls", 0)
    return data


def _save_unlocked(path: Path, data: dict[str, Any]) -> None:
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def snapshot() -> dict[str, Any]:
    """Current usage vs limit (read-only; creates/rolls file if needed)."""
    limit = _limit()
    path = _usage_path()
    with _lock:
        data = _load_unlocked(path)
        _save_unlocked(path, data)
        used = int(data["search_calls"])
        month = data["month"]
    return {
        "month": month,
        "search_calls": used,
        "search_limit": limit,
        "search_remaining": max(0, limit - used),
        "search_allowed": used < limit,
        "free_tier": {"search_calls": FREE_SEARCH_CALLS},
        "path": str(path),
    }


def check(n: int = 1) -> QuotaResult:
    """Read-only: would n more HERE transactions be allowed?"""
    n = max(1, int(n))
    limit = _limit()
    path = _usage_path()
    with _lock:
        data = _load_unlocked(path)
        used = int(data["search_calls"])
        ok = used + n <= limit
        return QuotaResult(
            allowed=ok,
            month=data["month"],
            used=used,
            limit=limit,
            remaining=max(0, limit - used),
            message=(
                "" if ok else (
                    f"HERE Search monthly limit reached ({used}/{limit}). "
                    "Try again next month."
                )
            ),
        )


def try_consume(n: int = 1) -> QuotaResult:
    """Atomically reserve n HERE transactions; deny at the hard cut."""
    n = max(1, int(n))
    limit = _limit()
    path = _usage_path()
    with _lock:
        data = _load_unlocked(path)
        used = int(data["search_calls"])
        if used + n > limit:
            return QuotaResult(
                allowed=False,
                month=data["month"],
                used=used,
                limit=limit,
                remaining=0,
                message=(
                    f"HERE Search monthly limit reached ({used}/{limit}). "
                    "Try again next month."
                ),
            )
        data["search_calls"] = used + n
        _save_unlocked(path, data)
        used = int(data["search_calls"])
        return QuotaResult(
            True,
            data["month"],
            used,
            limit,
            max(0, limit - used),
        )
