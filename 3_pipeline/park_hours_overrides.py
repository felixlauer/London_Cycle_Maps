"""
Manual park opening_hours overrides (by polygon / park name).

Loaded from park_hours_overrides.json and applied when tagging each OSM park
polygon in tag_attractions_osm.py. Conflict resolution uses spatial overlap
in attraction_spatial._set_park_hours_on_edge (park_hours_overlap), not name heuristics.
"""
from __future__ import annotations

import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OVERRIDES_PATH = os.path.join(SCRIPT_DIR, "park_hours_overrides.json")


def _norm_name(name: str) -> str:
    s = str(name or "").strip()
    if s.lower() in ("", "nan", "none"):
        return ""
    return s


def load_park_hours_overrides(path: str | None = None) -> list[dict]:
    path = path or DEFAULT_OVERRIDES_PATH
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return list(data.get("overrides") or [])


def resolve_polygon_opening_hours(
    polygon_name: str,
    osm_hours: str,
    overrides: list[dict],
) -> str:
    """Return override hours when polygon name matches; else OSM hours."""
    name = _norm_name(polygon_name)
    if not name:
        return str(osm_hours or "").strip()
    for entry in overrides:
        for match in entry.get("match_names") or []:
            if _norm_name(match) == name:
                return str(entry.get("opening_hours") or "").strip()
    return str(osm_hours or "").strip()
