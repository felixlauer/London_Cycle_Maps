"""
Barrier routing clusters (OSM barrier=* on snapped edges).

Five groups: free flow (0), permeable (+15m), stop/push (+35m), hostile (+90m), impassable (1e9).
Single source of truth for app.py routing and app_debug overlay colours.

TODO (future): scale penalties by bike type (cargo / longtail / standard) and a user
preference for how willing they are to dismount or lift (barrier tolerance slider).
cycle_barrier is group 3 and motorcycle_barrier is group 2 by current policy — revisit then.
"""
from __future__ import annotations

BARRIER_HARD_COST = 1e9

# Additive penalties (virtual metres), scaled by barrier_confidence on edge.
PENALTY_FREE_FLOW = 0.0
PENALTY_PERMEABLE = 15.0
PENALTY_STOP_PUSH = 35.0
PENALTY_HOSTILE = 90.0

CLUSTER_FREE_FLOW = 1
CLUSTER_PERMEABLE = 2
CLUSTER_STOP_PUSH = 3
CLUSTER_HOSTILE = 4
CLUSTER_IMPASSABLE = 5

CLUSTER_LABELS = {
    CLUSTER_FREE_FLOW: "free_flow",
    CLUSTER_PERMEABLE: "permeable_slow",
    CLUSTER_STOP_PUSH: "stop_push",
    CLUSTER_HOSTILE: "lift_squeeze",
    CLUSTER_IMPASSABLE: "impassable",
}

# Debug map overlay (one colour per cluster).
CLUSTER_COLORS = {
    CLUSTER_FREE_FLOW: "#2E7D32",
    CLUSTER_PERMEABLE: "#1976D2",
    CLUSTER_STOP_PUSH: "#F57C00",
    CLUSTER_HOSTILE: "#C62828",
    CLUSTER_IMPASSABLE: "#212121",
}

CLUSTER_PENALTY = {
    CLUSTER_FREE_FLOW: PENALTY_FREE_FLOW,
    CLUSTER_PERMEABLE: PENALTY_PERMEABLE,
    CLUSTER_STOP_PUSH: PENALTY_STOP_PUSH,
    CLUSTER_HOSTILE: PENALTY_HOSTILE,
    CLUSTER_IMPASSABLE: BARRIER_HARD_COST,
}

# Unknown tags in London extract → moderate stop/push (group 3).
DEFAULT_CLUSTER = CLUSTER_STOP_PUSH

_GROUP1 = frozenset({
    "height_restrictor", "lift_gate", "width_restrictor", "automatic lifting gate",
    "toll_booth", "sump_buster", "gap",
})

_GROUP2 = frozenset({
    "bollard", "kerb", "block", "planter", "cattle_grid", "wedge", "checkpoint", "bump",
    "pinch point", "rock", "stone", "artwork", "bench", "choker", "post",
    "motorcycle_barrier",  # policy: permeable slow-down (may move to hostile for cargo bikes)
})

_GROUP3 = frozenset({
    "cycle_barrier",  # policy: stop/push (user override from original group 2)
    "gate", "entrance", "swing_gate", "sliding_gate", "wicket_gate", "hampshire_gate", "door",
    "gate;entrance", "slide_gate", "bump_gate", "swing_gate;bollard", "swing_gate;entrance",
    "lych_gate", "sally_port", "ticket_barrier", "border_control", "security_control",
    "metal_detector", "ticket", "tickets", "rope", "pedestrian only", "yes", "barrier",
    "obstacle", "chain",  # chain: not in user list; mapped to stop/push
})

_GROUP4 = frozenset({
    "step", "log", "horse_stile", "spikes", "rising_kerb", "debris", "tree", "rocks",
})

_GROUP5 = frozenset({
    "stile", "turnstile", "full-height_turnstile", "full_height_turnstile", "kissing_gate",
    "fence", "wall", "jersey_barrier", "barricade", "embankment", "hoarding", "log;kissing_gate",
})

BARRIER_TO_CLUSTER: dict[str, int] = {}
for _tag in _GROUP1:
    BARRIER_TO_CLUSTER[_tag] = CLUSTER_FREE_FLOW
for _tag in _GROUP2:
    BARRIER_TO_CLUSTER[_tag] = CLUSTER_PERMEABLE
for _tag in _GROUP3:
    BARRIER_TO_CLUSTER[_tag] = CLUSTER_STOP_PUSH
for _tag in _GROUP4:
    BARRIER_TO_CLUSTER[_tag] = CLUSTER_HOSTILE
for _tag in _GROUP5:
    BARRIER_TO_CLUSTER[_tag] = CLUSTER_IMPASSABLE


def normalize_barrier_tag(raw) -> str:
    return str(raw or "").strip().lower()


def barrier_cluster_for_tag(tag: str) -> int:
    tag = normalize_barrier_tag(tag)
    if not tag:
        return CLUSTER_FREE_FLOW
    return BARRIER_TO_CLUSTER.get(tag, DEFAULT_CLUSTER)


def barrier_confidence(edge_data: dict) -> float:
    try:
        return max(0.0, min(1.0, float(edge_data.get("barrier_confidence", 1.0))))
    except (TypeError, ValueError):
        return 1.0


def barrier_is_hard_block(edge_data: dict | None) -> bool:
    if not edge_data:
        return False
    tag = normalize_barrier_tag(edge_data.get("barrier"))
    if not tag:
        return False
    return barrier_cluster_for_tag(tag) == CLUSTER_IMPASSABLE


def barrier_additive_penalty(edge_data: dict | None) -> float:
    """Virtual-metre additive A_barrier (groups 2–4). Group 1 → 0. Hard blocks → 0 here (use is_hard_block)."""
    if not edge_data:
        return 0.0
    tag = normalize_barrier_tag(edge_data.get("barrier"))
    if not tag:
        return 0.0
    cluster = barrier_cluster_for_tag(tag)
    if cluster in (CLUSTER_FREE_FLOW, CLUSTER_IMPASSABLE):
        return 0.0
    base = CLUSTER_PENALTY[cluster]
    return base * barrier_confidence(edge_data)


def barrier_cluster_meta(edge_data: dict | None) -> dict | None:
    if not edge_data:
        return None
    tag = normalize_barrier_tag(edge_data.get("barrier"))
    if not tag:
        return None
    cluster = barrier_cluster_for_tag(tag)
    return {
        "barrier": tag,
        "barrier_cluster": cluster,
        "barrier_cluster_label": CLUSTER_LABELS[cluster],
        "barrier_cluster_color": CLUSTER_COLORS[cluster],
    }


def cluster_legend() -> list[dict]:
    return [
        {
            "cluster": c,
            "label": CLUSTER_LABELS[c],
            "color": CLUSTER_COLORS[c],
            "penalty_m": None if c == CLUSTER_IMPASSABLE else CLUSTER_PENALTY[c],
            "hard_block": c == CLUSTER_IMPASSABLE,
        }
        for c in sorted(CLUSTER_LABELS)
    ]
