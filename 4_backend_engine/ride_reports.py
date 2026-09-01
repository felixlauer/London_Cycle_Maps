"""
Persist in-ride route feedback (TBT "Report" flag) to Supabase or a local JSON file.

One row per rider tap. These rows are the forensic source of truth; the routing
overlay (crowd_overlays.py) is derived from them and is always rebuildable, so
nothing written here is ever mutated by the cost pipeline.

Idempotency is the client's `client_event_id`: the phone queues reports offline
and may replay a batch, so inserts use upsert/ignore-duplicates and the caller
is told which ids were already present.

When changing schema or API, update 0_documentation/APP_MAIN.md and
supabase_sql/migrations/005_ride_reports.sql.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("ride_reports")

# Rider-facing categories. `general` is the 5 s picker timeout: it is stored for
# review but never drives an overlay (see crowd_overlays).
CATEGORIES = (
    "surface",
    "dangerous",
    "impassable",
    "speeding",
    "unlit",
    "general",
)

# Categories that may influence routing once snapped.
ROUTING_CATEGORIES = tuple(c for c in CATEGORIES if c != "general")

MAX_REPORTS_PER_BATCH = 25
# The snapshot is fat on purpose (a whole nav state), but still tiny vs a trace.
MAX_PAYLOAD_BYTES = 64 * 1024
MAX_SOURCE_LEN = 32
MAX_DEVICE_ID_LEN = 64

# Greater London, matching the routing service area (app.LONDON_BBOX).
LON_MIN, LAT_MIN, LON_MAX, LAT_MAX = -0.51, 51.28, 0.33, 51.69

_LOCAL_PATH = Path(__file__).resolve().parent / "ride_reports.json"
_lock = threading.Lock()
_path_override: Path | None = None


def _supabase_configured() -> bool:
    return bool(
        (os.environ.get("SUPABASE_URL") or "").strip()
        and (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    )


def _local_path() -> Path:
    return _path_override if _path_override is not None else _LOCAL_PATH


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


def _clip(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:limit]


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return False


def _finite_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out or out in (float("inf"), float("-inf")):
        return None
    return out


def normalize_report(raw: Any, *, user_id: str | None) -> tuple[dict[str, Any] | None, str | None]:
    """Validate one client report into an insertable row. Returns (row, error)."""
    if not isinstance(raw, dict):
        return None, "report must be an object"

    raw_id = raw.get("client_event_id")
    try:
        client_event_id = str(uuid.UUID(str(raw_id)))
    except (TypeError, ValueError, AttributeError):
        return None, "client_event_id must be a uuid"

    category = str(raw.get("category") or "").strip().lower()
    if category not in CATEGORIES:
        return None, f"category must be one of {', '.join(CATEGORIES)}"

    lat = _finite_float(raw.get("lat"))
    lon = _finite_float(raw.get("lon"))
    if lat is None or lon is None:
        return None, "lat and lon are required"
    if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
        return None, "lat/lon outside the supported area"

    payload = raw.get("payload")
    if not isinstance(payload, dict):
        return None, "payload must be an object"
    try:
        encoded = json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError):
        return None, "payload is not JSON-serialisable"
    if len(encoded.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        return None, f"payload must be at most {MAX_PAYLOAD_BYTES} bytes"

    return {
        "client_event_id": client_event_id,
        # Identity is the verified JWT only — never whatever the body claims.
        "user_id": user_id or None,
        "device_id": _clip(raw.get("device_id"), MAX_DEVICE_ID_LEN),
        "category": category,
        "source": _clip(raw.get("source"), MAX_SOURCE_LEN) or "tbt_island",
        "lat": lat,
        "lon": lon,
        "payload": payload,
        "simulate": _as_bool(raw.get("simulate")),
        "personal_only": _as_bool(raw.get("personal_only")),
    }, None


def submit_ride_reports(
    reports: Any,
    *,
    user_id: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """
    Insert a batch of rider reports.

    Returns ({accepted, duplicates, errors}, error). `accepted` and `duplicates`
    hold client_event_ids; a replayed batch is all duplicates and inserts nothing.
    """
    if not isinstance(reports, list):
        return None, "reports must be a list"
    if not reports:
        return None, "reports must not be empty"
    if len(reports) > MAX_REPORTS_PER_BATCH:
        return None, f"at most {MAX_REPORTS_PER_BATCH} reports per request"

    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(reports):
        row, err = normalize_report(raw, user_id=user_id)
        if err or row is None:
            errors.append({"index": index, "error": err})
            continue
        # Two copies of one id inside a single batch would break the upsert.
        if row["client_event_id"] in seen:
            errors.append({"index": index, "error": "duplicate client_event_id in batch"})
            continue
        seen.add(row["client_event_id"])
        rows.append(row)

    if not rows:
        return {"accepted": [], "duplicates": [], "errors": errors}, None

    submitted = [r["client_event_id"] for r in rows]
    if _supabase_configured():
        try:
            client = _supabase_client()
            res = (
                client.table("ride_reports")
                .upsert(rows, on_conflict="client_event_id", ignore_duplicates=True)
                .execute()
            )
            inserted = [
                str(r.get("client_event_id"))
                for r in (res.data or [])
                if isinstance(r, dict) and r.get("client_event_id")
            ]
        except Exception as exc:
            return None, f"could not save ride reports: {exc}"
    else:
        inserted, err = _insert_local(rows)
        if err:
            return None, err

    accepted = set(inserted)
    return {
        "accepted": sorted(accepted),
        "duplicates": [cid for cid in submitted if cid not in accepted],
        "errors": errors,
    }, None


def _insert_local(rows: list[dict[str, Any]]) -> tuple[list[str], str | None]:
    """Dev fallback — append to local JSON (not for production multi-instance)."""
    path = _local_path()
    try:
        with _lock:
            existing = _load_local_unlocked(path)
            known = {
                str(r.get("client_event_id"))
                for r in existing
                if isinstance(r, dict)
            }
            inserted: list[str] = []
            now = datetime.now(timezone.utc).isoformat()
            for row in rows:
                cid = row["client_event_id"]
                if cid in known:
                    continue
                known.add(cid)
                inserted.append(cid)
                existing.append({
                    "id": str(uuid.uuid4()),
                    **row,
                    "snapped_u": None,
                    "snapped_v": None,
                    "snapped_eid": None,
                    "snap_dist_m": None,
                    "osm_id": None,
                    "applied": "none",
                    "created_at": now,
                })
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(
                json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            tmp.replace(path)
            return inserted, None
    except Exception as exc:
        return [], f"could not save ride reports: {exc}"


def _load_local_unlocked(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "[]")
    except (OSError, json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [r for r in data if isinstance(r, dict)]


def list_ride_reports(
    *,
    since: datetime | None = None,
    limit: int = 20000,
) -> tuple[list[dict[str, Any]], str | None]:
    """
    Reports newest-first, optionally only those created at/after `since`.

    Used by crowd_overlays to rebuild the derived overlay from source rows.
    """
    if _supabase_configured():
        try:
            client = _supabase_client()
            query = (
                client.table("ride_reports")
                .select(
                    "id,client_event_id,user_id,device_id,category,source,lat,lon,"
                    "snapped_u,snapped_v,snapped_eid,snap_dist_m,osm_id,payload,"
                    "applied,simulate,personal_only,created_at"
                )
                .order("created_at", desc=True)
                .limit(int(limit))
            )
            if since is not None:
                query = query.gte("created_at", since.astimezone(timezone.utc).isoformat())
            res = query.execute()
            rows = res.data or []
            return (rows if isinstance(rows, list) else []), None
        except Exception as exc:
            return [], f"could not load ride reports: {exc}"

    try:
        with _lock:
            rows = _load_local_unlocked(_local_path())
        if since is not None:
            cutoff = since.astimezone(timezone.utc).isoformat()
            rows = [r for r in rows if str(r.get("created_at") or "") >= cutoff]
        rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        return rows[: int(limit)], None
    except Exception as exc:
        return [], f"could not load ride reports: {exc}"


def mark_snapped(updates: list[dict[str, Any]]) -> str | None:
    """
    Write snap results (and `applied`) back onto stored rows. Best-effort:
    a failure here costs forensics, never routing.

    Each update needs `client_event_id` plus the columns to set.
    """
    if not updates:
        return None

    if _supabase_configured():
        try:
            client = _supabase_client()
            for upd in updates:
                cid = upd.get("client_event_id")
                if not cid:
                    continue
                fields = {k: v for k, v in upd.items() if k != "client_event_id"}
                if not fields:
                    continue
                client.table("ride_reports").update(fields).eq(
                    "client_event_id", cid
                ).execute()
            return None
        except Exception as exc:
            log.warning("ride_reports.mark_snapped failed: %s", exc)
            return f"could not update ride reports: {exc}"

    try:
        path = _local_path()
        with _lock:
            existing = _load_local_unlocked(path)
            by_id = {str(r.get("client_event_id")): r for r in existing}
            for upd in updates:
                cid = str(upd.get("client_event_id") or "")
                row = by_id.get(cid)
                if row is None:
                    continue
                for key, value in upd.items():
                    if key != "client_event_id":
                        row[key] = value
            if not existing:
                return None
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(
                json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            tmp.replace(path)
        return None
    except Exception as exc:
        log.warning("ride_reports.mark_snapped local failed: %s", exc)
        return f"could not update ride reports: {exc}"
