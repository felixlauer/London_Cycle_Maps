"""
Park opening-hours evaluation for routing (Europe/London, DST-aware).

Pre-evaluate unique OSM opening_hours strings once per /route request;
A* only does O(1) dict lookups. Missing/unparseable hours use dawn-dusk fallback.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from opening_hours import OpeningHours

LONDON_TZ = ZoneInfo("Europe/London")
LONDON_COORDS = (51.5074, -0.1278)  # lat, lon for opening-hours-py
FALLBACK_EXPRESSION = "dawn-dusk"


def london_now() -> datetime:
    return datetime.now(LONDON_TZ)


def _opening_hours_parser(expression: str) -> OpeningHours:
    # coords + country infer Europe/London; pass London-aware at_time for DST-correct eval
    return OpeningHours(
        expression,
        coords=LONDON_COORDS,
        country="GB",
    )


def _is_park_yes(edge_data: dict) -> bool:
    return str(edge_data.get("is_park", "")).strip().lower() in ("yes", "true", "1")


def evaluate_fallback_open(at_time: datetime) -> bool:
    """Dawn-dusk fallback for park edges without valid OSM hours."""
    oh = _opening_hours_parser(FALLBACK_EXPRESSION)
    return oh.is_open(time=at_time)


def _evaluate_hours_string(expression: str, at_time: datetime, fallback_open: bool) -> bool:
    try:
        oh = _opening_hours_parser(expression)
        if oh.is_open(time=at_time):
            return True
        if oh.is_closed(time=at_time):
            return False
        return fallback_open
    except Exception:
        return fallback_open


def build_request_hours_context(
    unique_strings: list[str],
    at_time: datetime,
) -> tuple[dict[str, bool], bool]:
    """
    Pre-evaluate all unique opening_hours strings for one request.
    Returns (hours_map, fallback_open).
    """
    fallback_open = evaluate_fallback_open(at_time)
    hours_map: dict[str, bool] = {}
    for expr in unique_strings:
        s = str(expr or "").strip()
        if not s:
            continue
        hours_map[s] = _evaluate_hours_string(s, at_time, fallback_open)
    return hours_map, fallback_open


def is_park_edge_open(
    edge_data: dict,
    hours_map: dict[str, bool],
    fallback_open: bool,
) -> bool:
    """O(1) traversal check — no parsing in the A* hot loop."""
    if not _is_park_yes(edge_data):
        return True
    raw = str(edge_data.get("opening_hours", "")).strip()
    if not raw:
        return fallback_open
    parts = [p.strip() for p in raw.split(";") if p.strip()]
    if not parts:
        return fallback_open
    for part in parts:
        if part in hours_map:
            if hours_map[part]:
                return True
        else:
            return fallback_open
    return False
