"""
HERE Geocoding & Search v7 — Autosuggest + Lookup.

Flask /geocode/* maps these onto the existing Mapbox-shaped JSON so web and
mobile keep using mapbox_id / name / place_formatted.

Positions returned on Autosuggest are cached briefly so Retrieve can skip a
second billed Lookup when the user picks a row we already have coordinates for.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

AUTOSUGGEST_URL = "https://autosuggest.search.hereapi.com/v1/autosuggest"
LOOKUP_URL = "https://lookup.search.hereapi.com/v1/lookup"

# Greater London centre. HERE forbids combining `at` with in=bbox / in=circle.
# Bias with `at` and hard-filter to Great Britain via in=countryCode:GBR.
LONDON_AT = "51.5074,-0.1278"

_SKIP_RESULT_TYPES = frozenset({"categoryQuery", "chainQuery"})
_CACHE_TTL_S = 15 * 60
_CACHE_MAX = 2000

_cache_lock = threading.Lock()
_position_cache: dict[str, tuple[float, dict[str, Any]]] = {}


class HereGeocodeError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def api_key() -> str:
    return (os.environ.get("HERE_API_KEY") or "").strip()


def configured() -> bool:
    return bool(api_key())


def _cache_put(here_id: str, payload: dict[str, Any]) -> None:
    if not here_id:
        return
    now = time.monotonic()
    with _cache_lock:
        _position_cache[here_id] = (now, payload)
        if len(_position_cache) > _CACHE_MAX:
            oldest = sorted(_position_cache.items(), key=lambda kv: kv[1][0])
            for key, _ in oldest[: len(_position_cache) - _CACHE_MAX]:
                _position_cache.pop(key, None)


def cache_get(here_id: str) -> dict[str, Any] | None:
    now = time.monotonic()
    with _cache_lock:
        hit = _position_cache.get(here_id)
        if not hit:
            return None
        ts, payload = hit
        if now - ts > _CACHE_TTL_S:
            _position_cache.pop(here_id, None)
            return None
        return payload


def reset_cache_for_tests() -> None:
    with _cache_lock:
        _position_cache.clear()


def _http_get(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            pass
        raise HereGeocodeError(
            f"HERE search failed ({e.code}){': ' + detail if detail else ''}",
            status=502 if e.code >= 500 else e.code,
        ) from e
    except Exception as e:
        raise HereGeocodeError(str(e) or "HERE search failed", status=502) from e


def _address_label(item: dict[str, Any]) -> str:
    addr = item.get("address") or {}
    if isinstance(addr, dict):
        label = (addr.get("label") or "").strip()
        if label:
            return label
    return (item.get("title") or "").strip()


def _place_formatted(item: dict[str, Any], name: str, full_address: str) -> str:
    addr = item.get("address") if isinstance(item.get("address"), dict) else {}
    parts = [
        (addr or {}).get("district") or (addr or {}).get("county"),
        (addr or {}).get("city"),
        (addr or {}).get("postalCode"),
    ]
    joined = ", ".join(p for p in parts if p)
    if joined:
        return joined
    if full_address and name and full_address.lower().startswith(name.lower()):
        rest = full_address[len(name):].lstrip(" ,")
        if rest:
            return rest
    return full_address


def _coords(item: dict[str, Any]) -> tuple[float, float] | None:
    pos = item.get("position")
    if not isinstance(pos, dict):
        access = item.get("access")
        if isinstance(access, list) and access and isinstance(access[0], dict):
            pos = access[0]
    if not isinstance(pos, dict):
        return None
    try:
        lat = float(pos.get("lat"))
        lon = float(pos.get("lng") if pos.get("lng") is not None else pos.get("lon"))
    except (TypeError, ValueError):
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return lat, lon


def map_suggestion(item: dict[str, Any]) -> dict[str, Any] | None:
    """Map a HERE Autosuggest entity onto the Mapbox-shaped dropdown row."""
    if not isinstance(item, dict):
        return None
    if item.get("resultType") in _SKIP_RESULT_TYPES:
        return None
    here_id = (item.get("id") or "").strip()
    if not here_id:
        return None
    name = (item.get("title") or "").strip()
    full_address = _address_label(item)
    if not name and not full_address:
        return None
    row = {
        "mapbox_id": here_id,
        "name": name or full_address,
        "full_address": full_address or name,
        "place_formatted": _place_formatted(item, name, full_address),
    }
    coords = _coords(item)
    if coords:
        lat, lon = coords
        _cache_put(here_id, {
            "lat": lat,
            "lon": lon,
            "label": full_address or name,
        })
    return row


def autosuggest(query: str, limit: int = 5) -> list[dict[str, Any]]:
    key = api_key()
    if not key:
        raise HereGeocodeError("geocoding not configured", status=503)
    q = (query or "").strip()
    if not q:
        return []
    params = urllib.parse.urlencode({
        "q": q,
        "at": LONDON_AT,
        "in": "countryCode:GBR",
        "limit": str(max(1, min(int(limit), 20))),
        "lang": "en",
        "apiKey": key,
    })
    data = _http_get(f"{AUTOSUGGEST_URL}?{params}")
    rows: list[dict[str, Any]] = []
    for item in data.get("items") or []:
        mapped = map_suggestion(item)
        if mapped:
            rows.append(mapped)
    return rows


def lookup(here_id: str) -> dict[str, Any]:
    key = api_key()
    if not key:
        raise HereGeocodeError("geocoding not configured", status=503)
    hid = (here_id or "").strip()
    if not hid:
        raise HereGeocodeError("id required", status=400)
    cached = cache_get(hid)
    if cached:
        return cached
    params = urllib.parse.urlencode({
        "id": hid,
        "lang": "en",
        "apiKey": key,
    })
    data = _http_get(f"{LOOKUP_URL}?{params}")
    coords = _coords(data)
    if not coords:
        raise HereGeocodeError("No coordinates in retrieve response", status=404)
    lat, lon = coords
    label = _address_label(data) or (data.get("title") or f"{lat:.4f}, {lon:.4f}")
    payload = {"lat": lat, "lon": lon, "label": label}
    _cache_put(hid, payload)
    return payload
