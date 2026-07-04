"""
Routing cost masks: vehicular-free edges, steps double-penalty rules, service/access.

Spec: 0_documentation/tasks/cost_function_brainstorming.md

Requires graph rebuild after build_graph.py ingests access/service tags — not auto-run.
"""
from __future__ import annotations

CYCLEWAY_TAG_KEYS = ("cycleway", "cycleway_left", "cycleway_right", "cycleway_both")

SERVICE_ACCESS_DENIED = frozenset({"private", "no", "customers"})
BARRIER_ACCESS_DENIED = frozenset({"private", "no"})
# Positive bicycle=* overrides restrictive access=* (OSM access hierarchy for cyclists).
BICYCLE_POSITIVE_OVERRIDE = frozenset({"yes", "designated", "permissive"})

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


def _norm_access(val) -> str:
    return str(val or "").strip().lower()


def bicycle_overrides_restrictive_access(bicycle_val) -> bool:
    """True when bicycle=yes/designated/permissive wins over access=private/no/…"""
    return _norm_access(bicycle_val) in BICYCLE_POSITIVE_OVERRIDE


def effective_access_denied(access_val, bicycle_val, denied: frozenset) -> bool:
    """Apply OSM hierarchy: positive bicycle tag overrides restrictive access."""
    if bicycle_overrides_restrictive_access(bicycle_val):
        return False
    return _norm_access(access_val) in denied


def is_service_highway(d: dict | None) -> bool:
    if not d:
        return False
    return str(d.get("type", "")).strip().lower() == "service"


def is_service_alley(d: dict | None) -> bool:
    if not is_service_highway(d):
        return False
    return _norm_access(d.get("service")) == "alley"


def is_service_access_denied(d: dict | None) -> bool:
    if not is_service_highway(d):
        return False
    return effective_access_denied(d.get("access"), d.get("bicycle"), SERVICE_ACCESS_DENIED)


def is_barrier_access_denied(d: dict | None) -> bool:
    if not d or not str(d.get("barrier", "")).strip():
        return False
    return effective_access_denied(
        d.get("barrier_access"), d.get("barrier_bicycle"), BARRIER_ACCESS_DENIED
    )


def is_service_steps_like(d: dict | None) -> bool:
    """Non-alley service ways (after access filter) — M_highway and surface/hill like steps."""
    if not is_service_highway(d):
        return False
    if is_service_access_denied(d):
        return False
    return not is_service_alley(d)


def masks_surface_and_hill(d: dict | None) -> bool:
    return is_steps(d) or is_service_steps_like(d)


# --- Configurable vehicular-free classes (preset wizard infrastructure question) ---
# Precomputed per edge at graph load (app bootstrap sets d['_vf'] = vf_flags(d)),
# so per-request evaluation is a single int AND - no tag parsing on the hot path.
VF_MASK_CORE = 1        # physically separated (cycleway, track/separate/exclusive, kerb/bollard, superhighway)
VF_MASK_SHARED_PATH = 2  # shared with pedestrians (footway/path/pedestrian/bridleway, no physical cycle tags)
VF_MASK_BUS_LANE = 4    # share_busway only
VF_REWARD_CORE = 8      # reward-eligible core (excludes parks)
VF_REWARD_BUS_LANE = 16  # reward-eligible bus lane (excludes parks)

VF_MASK_ALL = VF_MASK_CORE | VF_MASK_SHARED_PATH | VF_MASK_BUS_LANE
VF_REWARD_ALL = VF_REWARD_CORE | VF_REWARD_BUS_LANE

_PHYSICAL_NONBUS_TAG_VALUES = frozenset({"track", "separate", "exclusive"})


def _has_physical_nonbus_cycleway_tag(d: dict) -> bool:
    for key in CYCLEWAY_TAG_KEYS:
        for tok in _tag_tokens(d.get(key)):
            if tok in _PHYSICAL_NONBUS_TAG_VALUES:
                return True
    return False


def _has_share_busway_tag(d: dict) -> bool:
    for key in CYCLEWAY_TAG_KEYS:
        for tok in _tag_tokens(d.get(key)):
            if tok == "share_busway":
                return True
    return False


def vf_flags(d: dict | None) -> int:
    """Bitmask classification of vehicular-free character for an edge.

    Mask bits (risk/speed/calming masking) and reward bits (segregated reward)
    are separate so the user's infrastructure selection can gate each. With all
    classes allowed, behaviour equals is_vehicular_free / is_segregated_cycling.
    """
    if not d:
        return 0
    flags = 0
    highway = str(d.get("type", "")).strip().lower()
    core = (
        highway == "cycleway"
        or _has_physical_nonbus_cycleway_tag(d)
        or _has_physical_cycleway_separation(d)
        or _has_tfl_superhighway(d)
    )
    shared_path = (
        not core
        and highway in ("path", "pedestrian", "footway", "bridleway")
    )
    bus_lane = not core and _has_share_busway_tag(d)

    if core:
        flags |= VF_MASK_CORE
    if shared_path:
        flags |= VF_MASK_SHARED_PATH
    if bus_lane:
        flags |= VF_MASK_BUS_LANE

    if not _is_yes_attr(d.get("is_park")):
        if core:
            flags |= VF_REWARD_CORE
        if bus_lane:
            flags |= VF_REWARD_BUS_LANE
    return flags


def vf_allowed_masks(shared_path: bool = True, bus_lane: bool = True) -> tuple[int, int]:
    """(mask_allowed, reward_allowed) bitmasks from the user's infrastructure toggles."""
    mask_allowed = VF_MASK_CORE
    reward_allowed = VF_REWARD_CORE
    if shared_path:
        mask_allowed |= VF_MASK_SHARED_PATH
    if bus_lane:
        mask_allowed |= VF_MASK_BUS_LANE
        reward_allowed |= VF_REWARD_BUS_LANE
    return mask_allowed, reward_allowed


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
