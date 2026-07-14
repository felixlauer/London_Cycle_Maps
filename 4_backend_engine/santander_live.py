"""
Santander Cycles (TfL BikePoint) live cache + candidate picker + ORS foot walk proxy.

Not wired into edge costs / A*. Poll BikePoint in the background; serve hire-mode
candidates from in-memory state. When changing API shape, update 0_documentation/APP_MAIN.md.
"""
from __future__ import annotations

import logging
import math
import os
import threading
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

log = logging.getLogger("santander_live")
logging.basicConfig(level=logging.INFO)

BIKEPOINT_URL = "https://api.tfl.gov.uk/BikePoint"
TFL_APP_KEY = os.environ.get("TFL_APP_KEY", "")
ORS_API_KEY = os.environ.get("ORS_API_KEY", "")
ORS_DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/foot-walking/geojson"
API_TIMEOUT_S = 20
DEFAULT_POLL_INTERVAL_S = 45
DEFAULT_RADIUS_M = 1500
TARGET_SUITABLE = 3
WALK_M_PER_MIN = 80.0  # ~4.8 km/h haversine estimate

_STATIONS: list[dict] = []
_last_update: datetime | None = None
_last_error: str | None = None
_poll_started = False
_lock = threading.Lock()


def bikepoint_fetch_enabled() -> bool:
    if os.environ.get("SKIP_BIKEPOINT_FETCH", "").lower() in ("1", "true", "yes"):
        return False
    raw = os.environ.get("BIKEPOINT_FETCH", "1").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    return True


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def walk_estimate_min(distance_m: float) -> int:
    # ~4.8 km/h haversine + 20% gut-feel for street detours
    return max(1, int(round(float(distance_m) * 1.2 / WALK_M_PER_MIN)))


def _parse_bool(val) -> bool:
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ("true", "1", "yes")


def _parse_int(val, default: int = 0) -> int:
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return default


def _station_from_place(place: dict) -> dict | None:
    try:
        lat = float(place.get("lat"))
        lon = float(place.get("lon"))
    except (TypeError, ValueError):
        return None
    props = {p.get("key"): p.get("value") for p in (place.get("additionalProperties") or [])}
    if not _parse_bool(props.get("Installed", "true")):
        return None
    if _parse_bool(props.get("Locked", "false")):
        return None
    nb_bikes = _parse_int(props.get("NbBikes", 0))
    nb_empty = _parse_int(props.get("NbEmptyDocks", 0))
    nb_docks = _parse_int(props.get("NbDocks", 0))
    nb_std = _parse_int(props.get("NbStandardBikes", 0))
    nb_ebike = _parse_int(props.get("NbEBikes", 0))
    return {
        "id": place.get("id") or "",
        "name": place.get("commonName") or place.get("id") or "Station",
        "lat": lat,
        "lon": lon,
        "nb_bikes": nb_bikes,
        "nb_empty": nb_empty,
        "nb_docks": nb_docks,
        "nb_standard": nb_std,
        "nb_ebikes": nb_ebike,
        "temporary": _parse_bool(props.get("Temporary", "false")),
    }


def update_bikepoints() -> tuple[bool, str, int]:
    """Fetch all BikePoints and replace in-memory cache. Returns (ok, message, count)."""
    global _STATIONS, _last_update, _last_error
    params = {}
    if TFL_APP_KEY:
        params["app_key"] = TFL_APP_KEY
    headers = {"User-Agent": "LondonCycleMaps/santander", "Accept": "application/json"}
    try:
        resp = requests.get(BIKEPOINT_URL, params=params, headers=headers, timeout=API_TIMEOUT_S)
        resp.raise_for_status()
        raw = resp.json()
    except Exception as exc:
        _last_error = str(exc)
        log.warning("santander_live: BikePoint fetch failed: %s", exc)
        return False, f"BikePoint fetch failed: {exc}", len(_STATIONS)

    if not isinstance(raw, list):
        _last_error = "unexpected BikePoint payload"
        return False, _last_error, len(_STATIONS)

    stations = []
    for place in raw:
        st = _station_from_place(place)
        if st is not None:
            stations.append(st)

    with _lock:
        _STATIONS = stations
        _last_update = datetime.now(timezone.utc)
        _last_error = None
    msg = f"loaded {len(stations)} BikePoints"
    log.info("santander_live: %s", msg)
    return True, msg, len(stations)


def get_status() -> dict:
    with _lock:
        n = len(_STATIONS)
        last = _last_update.isoformat() if _last_update else None
        err = _last_error
    return {
        "loaded": n > 0,
        "station_count": n,
        "last_update": last,
        "last_error": err,
        "fetch_enabled": bikepoint_fetch_enabled(),
        "ors_configured": bool(ORS_API_KEY),
    }


def get_candidates(
    lat: float,
    lon: float,
    *,
    need: str = "bikes",
    radius_m: float = DEFAULT_RADIUS_M,
    target_suitable: int = TARGET_SUITABLE,
) -> dict:
    """
    Soft-fail 1B algorithm: stations within radius sorted by haversine; include each
    until target_suitable suitable stations collected (or range exhausted).
    need=bikes -> suitable if nb_bikes > 0; need=docks -> suitable if nb_empty > 0.
    """
    need = (need or "bikes").strip().lower()
    if need not in ("bikes", "docks"):
        raise ValueError("need must be 'bikes' or 'docks'")
    radius_m = float(radius_m)
    target_suitable = int(target_suitable)

    with _lock:
        stations = list(_STATIONS)

    in_radius = []
    for st in stations:
        d = _haversine_m(lat, lon, st["lat"], st["lon"])
        if d <= radius_m:
            in_radius.append((d, st))
    in_radius.sort(key=lambda t: t[0])

    shown = []
    suitable_count = 0
    for d, st in in_radius:
        suitable = (st["nb_bikes"] > 0) if need == "bikes" else (st["nb_empty"] > 0)
        item = {
            **st,
            "distance_m": round(d, 1),
            "walk_estimate_min": walk_estimate_min(d),
            "suitable": suitable,
            "has_bikes": st["nb_bikes"] > 0,
        }
        shown.append(item)
        if suitable:
            suitable_count += 1
            if suitable_count >= target_suitable:
                break

    return {
        "shown": shown,
        "suitable_count": suitable_count,
        "total_in_radius": len(in_radius),
        "need": need,
        "radius_m": radius_m,
        "origin": {"lat": lat, "lon": lon},
        "last_update": _last_update.isoformat() if _last_update else None,
    }


def walk_route(from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> dict:
    """
    OpenRouteService foot-walking directions.
    Returns {path: [[lat,lon],...], duration_s, distance_m}.
    """
    if not ORS_API_KEY:
        raise RuntimeError("ORS_API_KEY not configured")

    headers = {
        "Authorization": ORS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json, application/geo+json",
    }
    body = {
        "coordinates": [[float(from_lon), float(from_lat)], [float(to_lon), float(to_lat)]],
    }
    resp = requests.post(ORS_DIRECTIONS_URL, json=body, headers=headers, timeout=API_TIMEOUT_S)
    if resp.status_code >= 400:
        raise RuntimeError(f"ORS error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    features = data.get("features") or []
    if not features:
        raise RuntimeError("ORS returned no features")
    feat = features[0]
    geom = feat.get("geometry") or {}
    coords = geom.get("coordinates") or []
    # GeoJSON is [lon, lat] → Leaflet [lat, lon]
    path = [[float(c[1]), float(c[0])] for c in coords if len(c) >= 2]
    props = feat.get("properties") or {}
    summary = props.get("summary") or {}
    # Some ORS versions nest summary under segments
    if not summary and props.get("segments"):
        segs = props["segments"]
        summary = {
            "duration": sum(float(s.get("duration", 0)) for s in segs),
            "distance": sum(float(s.get("distance", 0)) for s in segs),
        }
    duration_s = float(summary.get("duration", 0) or 0)
    distance_m = float(summary.get("distance", 0) or 0)
    if not path:
        raise RuntimeError("ORS returned empty geometry")
    return {
        "path": path,
        "duration_s": duration_s,
        "distance_m": distance_m,
        "duration_min": max(1, int(round(duration_s / 60.0))) if duration_s else walk_estimate_min(
            _haversine_m(from_lat, from_lon, to_lat, to_lon)
        ),
    }


def _poll_loop(interval_s: int) -> None:
    while True:
        time.sleep(interval_s)
        try:
            ok, msg, count = update_bikepoints()
            log.info("santander_live: poll ok=%s stations=%d (%s)", ok, count, msg)
        except Exception:
            log.exception("santander_live: poll failed")


def start_background_refresh(interval_s: int | None = None) -> None:
    """Fetch BikePoints now, then refresh on an interval (default 45s)."""
    global _poll_started
    if not bikepoint_fetch_enabled():
        log.info("santander_live: fetch disabled (SKIP_BIKEPOINT_FETCH / BIKEPOINT_FETCH=0)")
        return
    if _poll_started:
        return
    _poll_started = True
    interval_s = int(
        interval_s
        if interval_s is not None
        else os.environ.get("BIKEPOINT_POLL_INTERVAL_S", DEFAULT_POLL_INTERVAL_S)
    )
    ok, msg, count = update_bikepoints()
    log.info("santander_live: initial fetch ok=%s stations=%d (%s)", ok, count, msg)
    t = threading.Thread(
        target=_poll_loop,
        args=(interval_s,),
        name="bikepoint-poll",
        daemon=True,
    )
    t.start()
