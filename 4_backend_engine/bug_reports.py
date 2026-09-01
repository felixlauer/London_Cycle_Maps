"""
Persist user bug reports to Supabase (service role) or a local JSON file in dev.

When changing schema or API, update 0_documentation/APP_MAIN.md.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_MESSAGE_LEN = 1500
MIN_MESSAGE_LEN = 10

_LOCAL_PATH = Path(__file__).resolve().parent / "bug_reports.json"


def _supabase_configured() -> bool:
    return bool(
        (os.environ.get("SUPABASE_URL") or "").strip()
        and (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    )


def _normalize_message(raw: Any) -> tuple[str | None, str | None]:
    if not isinstance(raw, str):
        return None, "message required"
    message = " ".join(raw.strip().split())
    if len(message) < MIN_MESSAGE_LEN:
        return None, f"message must be at least {MIN_MESSAGE_LEN} characters"
    if len(message) > MAX_MESSAGE_LEN:
        return None, f"message must be at most {MAX_MESSAGE_LEN} characters"
    return message, None


def _clip(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:limit]


def _supabase_client():
    """Import the real supabase package (not a local migrations folder)."""
    import sys

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


def submit_bug_report(
    *,
    user_id: str | None,
    message: Any,
    page_url: Any = None,
    user_agent: Any = None,
    app_version: Any = None,
    theme: Any = None,
    viewport: Any = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Insert a bug report. Returns ({id, created_at}, error)."""
    cleaned, err = _normalize_message(message)
    if err:
        return None, err

    row = {
        "id": str(uuid.uuid4()),
        "user_id": user_id or None,
        "message": cleaned,
        "page_url": _clip(page_url, 500),
        "user_agent": _clip(user_agent, 400),
        "app_version": _clip(app_version, 64),
        "theme": _clip(theme, 32),
        "viewport": _clip(viewport, 64),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    if _supabase_configured():
        try:
            client = _supabase_client()
            payload = {k: v for k, v in row.items() if k != "id"}
            # Let Postgres generate uuid + created_at when inserting via API.
            payload.pop("created_at", None)
            res = client.table("bug_reports").insert(payload).execute()
            data = (res.data or [None])[0]
            if not data:
                return None, "failed to save bug report"
            return {
                "id": data.get("id"),
                "created_at": data.get("created_at"),
            }, None
        except Exception as exc:
            return None, f"could not save bug report: {exc}"

    # Dev fallback — append to local JSON (not for production multi-instance).
    try:
        existing: list[dict[str, Any]] = []
        if _LOCAL_PATH.exists():
            existing = json.loads(_LOCAL_PATH.read_text(encoding="utf-8") or "[]")
            if not isinstance(existing, list):
                existing = []
        existing.append(row)
        _LOCAL_PATH.write_text(
            json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return {"id": row["id"], "created_at": row["created_at"]}, None
    except Exception as exc:
        return None, f"could not save bug report: {exc}"


def list_bug_reports() -> tuple[list[dict[str, Any]], str | None]:
    """
    Return all bug reports newest-first, plus optional error.
    Uses Supabase when configured; otherwise local bug_reports.json.
    """
    if _supabase_configured():
        try:
            client = _supabase_client()
            res = (
                client.table("bug_reports")
                .select(
                    "id,user_id,message,page_url,user_agent,app_version,"
                    "theme,viewport,created_at"
                )
                .order("created_at", desc=True)
                .execute()
            )
            rows = res.data or []
            return rows if isinstance(rows, list) else [], None
        except Exception as exc:
            return [], f"could not load bug reports: {exc}"

    try:
        if not _LOCAL_PATH.exists():
            return [], None
        existing = json.loads(_LOCAL_PATH.read_text(encoding="utf-8") or "[]")
        if not isinstance(existing, list):
            return [], None

        def _sort_key(row: Any) -> str:
            if isinstance(row, dict):
                return str(row.get("created_at") or "")
            return ""

        rows = [r for r in existing if isinstance(r, dict)]
        rows.sort(key=_sort_key, reverse=True)
        return rows, None
    except Exception as exc:
        return [], f"could not load bug reports: {exc}"
