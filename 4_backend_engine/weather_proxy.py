"""
Open-Meteo forecast proxy helpers — no API key.

Caches short-lived responses keyed by rounded lat/lon + forecast hour.

Dev: `python app.py --weather-test` rotates synthetic extreme scenarios every
minute (see EXTREME_TEST_SCENARIOS). Also: WEATHER_TEST_MODE=1.
"""
from __future__ import annotations

import json
import os
import random
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
CACHE_TTL_SEC = 12 * 60  # ~12 minutes
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}

_TEST_SLOT: int | None = None
_TEST_SCENARIO_ID: str | None = None

# Synthetic payloads for island extreme-warning QA (one picked per UTC minute).
EXTREME_TEST_SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "none",
        "weather_code": 2,
        "is_day": True,
        "wind_speed_ms": 3.0,
        "wind_dir_deg": 180,
        "temp_c": 18.0,
        "uv_index": 2.0,
    },
    {
        "id": "thunderstorm",
        "weather_code": 95,
        "is_day": True,
        "wind_speed_ms": 8.0,
        "wind_dir_deg": 225,
        "temp_c": 19.0,
        "uv_index": 1.0,
    },
    {
        "id": "thunder_hail",
        "weather_code": 96,
        "is_day": True,
        "wind_speed_ms": 9.0,
        "wind_dir_deg": 200,
        "temp_c": 17.0,
        "uv_index": 0.5,
    },
    {
        "id": "black_ice",
        "weather_code": 66,
        "is_day": False,
        "wind_speed_ms": 4.0,
        "wind_dir_deg": 90,
        "temp_c": 0.0,
        "uv_index": 0.0,
    },
    {
        "id": "heavy_snow",
        "weather_code": 75,
        "is_day": True,
        "wind_speed_ms": 6.0,
        "wind_dir_deg": 45,
        "temp_c": -2.0,
        "uv_index": 0.5,
    },
    {
        "id": "violent_rain",
        "weather_code": 82,
        "is_day": True,
        "wind_speed_ms": 7.0,
        "wind_dir_deg": 270,
        "temp_c": 14.0,
        "uv_index": 1.0,
    },
    {
        "id": "dense_fog",
        "weather_code": 45,
        "is_day": True,
        "wind_speed_ms": 2.0,
        "wind_dir_deg": 0,
        "temp_c": 12.0,
        "uv_index": 0.5,
    },
    {
        "id": "strong_wind",
        "weather_code": 2,
        "is_day": True,
        "wind_speed_ms": 12.0,
        "wind_dir_deg": 315,
        "temp_c": 16.0,
        "uv_index": 3.0,
    },
    {
        "id": "heat",
        "weather_code": 0,
        "is_day": True,
        "wind_speed_ms": 3.0,
        "wind_dir_deg": 180,
        "temp_c": 31.0,
        "uv_index": 7.0,
    },
]


def is_test_mode() -> bool:
    return os.environ.get("WEATHER_TEST_MODE", "").strip().lower() in ("1", "true", "yes")


def _test_payload() -> dict[str, Any]:
    """Random extreme scenario, stable for the current UTC minute."""
    global _TEST_SLOT, _TEST_SCENARIO_ID
    slot = int(time.time() // 60)
    if slot != _TEST_SLOT:
        _TEST_SLOT = slot
        rng = random.Random(slot)
        picked = rng.choice(EXTREME_TEST_SCENARIOS)
        _TEST_SCENARIO_ID = picked["id"]
    picked = next(s for s in EXTREME_TEST_SCENARIOS if s["id"] == _TEST_SCENARIO_ID)
    return {
        "temp_c": picked["temp_c"],
        "weather_code": picked["weather_code"],
        "is_day": picked["is_day"],
        "wind_speed_ms": picked["wind_speed_ms"],
        "wind_dir_deg": picked["wind_dir_deg"],
        "uv_index": picked["uv_index"],
        "weather_test": True,
        "weather_test_scenario": picked["id"],
    }


def _cache_key(lat: float, lon: float, hour_iso: str) -> str:
    return f"v2:{round(lat, 3)}:{round(lon, 3)}:{hour_iso}"


def _parse_at(at: Optional[str]) -> Optional[datetime]:
    if not at:
        return None
    raw = at.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _nearest_hourly_index(times: list[str], target: datetime) -> int:
    best_i = 0
    best_abs = None
    for i, t in enumerate(times):
        raw = t
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            ht = datetime.fromisoformat(raw)
        except ValueError:
            continue
        if ht.tzinfo is None:
            ht = ht.replace(tzinfo=timezone.utc)
        else:
            ht = ht.astimezone(timezone.utc)
        delta = abs((ht - target).total_seconds())
        if best_abs is None or delta < best_abs:
            best_abs = delta
            best_i = i
    return best_i


def _hourly_at(hourly: dict[str, Any], key: str, index: int):
    arr = hourly.get(key) or []
    return arr[index] if 0 <= index < len(arr) else None


def _payload_from_current(current: dict[str, Any], uv_index: Any) -> dict[str, Any]:
    return {
        "temp_c": current.get("temperature_2m"),
        "weather_code": current.get("weather_code"),
        "is_day": bool(current.get("is_day", 1)),
        "wind_speed_ms": current.get("wind_speed_10m"),
        "wind_dir_deg": current.get("wind_direction_10m"),
        "uv_index": uv_index,
    }


def _payload_from_hourly(hourly: dict[str, Any], index: int) -> dict[str, Any]:
    is_day = _hourly_at(hourly, "is_day", index)
    return {
        "temp_c": _hourly_at(hourly, "temperature_2m", index),
        "weather_code": _hourly_at(hourly, "weather_code", index),
        "is_day": bool(is_day if is_day is not None else 1),
        "wind_speed_ms": _hourly_at(hourly, "wind_speed_10m", index),
        "wind_dir_deg": _hourly_at(hourly, "wind_direction_10m", index),
        "uv_index": _hourly_at(hourly, "uv_index", index),
    }


def fetch_weather(lat: float, lon: float, at: Optional[str] = None) -> dict[str, Any]:
    """
    Return { temp_c, weather_code, is_day, wind_speed_ms, wind_dir_deg, uv_index }.

    Uses Open-Meteo `current` when `at` is absent; otherwise the nearest hourly
    slot (UTC) to `at`. UV always comes from the matching hourly slot.

    In test mode (`--weather-test`), returns a synthetic extreme scenario that
    changes at the start of each UTC minute.
    """
    if is_test_mode():
        return _test_payload()

    target = _parse_at(at)
    use_current = target is None
    hour_iso = (
        "current"
        if use_current
        else target.replace(minute=0, second=0, microsecond=0).isoformat()
    )
    key = _cache_key(lat, lon, hour_iso)
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < CACHE_TTL_SEC:
        return hit[1]

    params = {
        "latitude": f"{lat:.5f}",
        "longitude": f"{lon:.5f}",
        "timezone": "UTC",
        "wind_speed_unit": "ms",
        "current": ",".join([
            "temperature_2m",
            "weather_code",
            "is_day",
            "wind_speed_10m",
            "wind_direction_10m",
        ]),
        "hourly": ",".join([
            "temperature_2m",
            "weather_code",
            "is_day",
            "wind_speed_10m",
            "wind_direction_10m",
            "uv_index",
        ]),
        "forecast_days": "8",
    }
    url = f"{OPEN_METEO_URL}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    if not times:
        raise RuntimeError("Open-Meteo returned no hourly times")

    pick_at = target or datetime.now(timezone.utc)
    idx = _nearest_hourly_index(times, pick_at)

    if use_current and data.get("current"):
        uv = _hourly_at(hourly, "uv_index", idx)
        payload = _payload_from_current(data["current"], uv)
    else:
        payload = _payload_from_hourly(hourly, idx)

    _CACHE[key] = (now, payload)
    return payload
