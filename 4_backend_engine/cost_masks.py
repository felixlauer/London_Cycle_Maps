"""
Routing cost masks: vehicular-free edges and steps double-penalty rules.

Spec: 0_documentation/tasks/cost_function_brainstorming.md
"""
from __future__ import annotations

CYCLEWAY_TAG_KEYS = ("cycleway", "cycleway_left", "cycleway_right", "cycleway_both")

VEHICULAR_FREE_HIGHWAY_TYPES = frozenset({
    "cycleway", "path", "pedestrian", "footway", "bridleway",
})

# Reward only: segregated cycling infrastructure (not footways / pedestrian / parks).
SEGREGATED_CYCLING_HIGHWAY_TYPES = frozenset({
    "cycleway",
})

# Whitelist only — excludes paint-only / shared tags (lane, shared_lane, segregated, etc.).
PHYSICAL_CYCLEWAY_TAG_VALUES = frozenset({
    "track", "separate", "share_busway", "exclusive",
})

PHYSICAL_CYCLEWAY_SEPARATION_VALUES = frozenset({
    "bollard", "kerb",
})

EMPTY_CYCLEWAY_TOKENS = frozenset({"", "no", "none"})


def _is_yes_attr(val) -> bool:
    return str(val or "").strip().lower() in ("yes", "true", "1")


def _tag_tokens(raw) -> list[str]:
    s = str(raw or "").strip().lower()
    if not s or s in EMPTY_CYCLEWAY_TOKENS:
        return []
    return [t.strip() for t in s.split(";") if t.strip() and t.strip() not in EMPTY_CYCLEWAY_TOKENS]


def _has_physical_cycleway_tag(d: dict) -> bool:
    for key in CYCLEWAY_TAG_KEYS:
        for tok in _tag_tokens(d.get(key)):
            if tok in PHYSICAL_CYCLEWAY_TAG_VALUES:
                return True
    return False


def _has_physical_cycleway_separation(d: dict) -> bool:
    sep = str(d.get("cycleway_separation", "")).strip().lower()
    if sep in PHYSICAL_CYCLEWAY_SEPARATION_VALUES:
        return True
    for key in ("cycleway_left_separation", "cycleway_right_separation"):
        for tok in _tag_tokens(d.get(key)):
            if tok in PHYSICAL_CYCLEWAY_SEPARATION_VALUES:
                return True
    return False


def _has_tfl_superhighway(d: dict) -> bool:
    prog = str(d.get("tfl_cycle_programme", "")).strip().lower()
    if not prog:
        return False
    return any(p.strip() == "superhighway" for p in prog.split(";") if p.strip())


def is_steps(d: dict | None) -> bool:
    if not d:
        return False
    return str(d.get("type", "")).strip().lower() == "steps"


def is_vehicular_free(d: dict | None) -> bool:
    """
    True when the cyclist is physically separated from general motor traffic.
    Masks risk, speed-stress, and calming penalties; affects width fallback.
    Parks are excluded — roads through parks (e.g. Hyde Park) stay penalised.
    """
    if not d:
        return False
    highway = str(d.get("type", "")).strip().lower()
    if highway in VEHICULAR_FREE_HIGHWAY_TYPES:
        return True
    if _has_physical_cycleway_tag(d):
        return True
    if _has_physical_cycleway_separation(d):
        return True
    if _has_tfl_superhighway(d):
        return True
    return False


def is_segregated_cycling(d: dict | None) -> bool:
    """
    Segregated cycling infrastructure for vehicular_free_weight reward only.
    Stricter than is_vehicular_free: no footway, pedestrian, path, bridleway, or parks.
    """
    if not d:
        return False
    if _is_yes_attr(d.get("is_park")):
        return False
    highway = str(d.get("type", "")).strip().lower()
    if highway in SEGREGATED_CYCLING_HIGHWAY_TYPES:
        return True
    if _has_physical_cycleway_tag(d):
        return True
    if _has_physical_cycleway_separation(d):
        return True
    if _has_tfl_superhighway(d):
        return True
    return False


def _parse_width_m(raw) -> float | None:
    if raw is None:
        return None
    s = str(raw).strip().lower().replace(",", ".")
    if not s:
        return None
    try:
        num = float("".join(c for c in s if c.isdigit() or c == "."))
        if "ft" in s or "foot" in s:
            num *= 0.3048
        return max(0.0, num)
    except ValueError:
        return None


def _has_nonempty_cycleway_width(d: dict) -> bool:
    return bool(str(d.get("cycleway_width", "")).strip())


def routing_width_m(d: dict | None) -> float | None:
    """
    Width used for width_weight / narrow stats.
    cycleway_width only when set; else width unless vehicular-free (then None → no penalty).
    """
    if not d:
        return None
    if _has_nonempty_cycleway_width(d):
        return _parse_width_m(d.get("cycleway_width"))
    if is_vehicular_free(d):
        return None
    return _parse_width_m(d.get("width"))
