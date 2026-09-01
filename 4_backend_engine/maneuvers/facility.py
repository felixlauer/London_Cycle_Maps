"""Facility classification for cyclist identity (MANEUVER_ENGINE_SPEC §2.1, §6.3)."""
from __future__ import annotations

from cycleway_clusters import (
    CLUSTER_BUS_SHARED,
    CLUSTER_CAR_SHARED,
    CLUSTER_SEGREGATED,
    classify_cycleway_edge,
)

from . import constants as C

# Higher = more mixed / less protected (for protection_delta)
PROTECTION_RANK = {
    "segregated": 0,
    "shared_path": 1,
    "bus_lane": 2,
    "painted_lane": 3,
    "carriageway": 4,
    "service": 5,
    "other": 6,
}

_SHARED_PATH_TYPES = frozenset({"path", "footway", "pedestrian"})
_CARRIAGEWAY_TYPES = frozenset({
    "primary", "secondary", "tertiary", "residential", "unclassified",
    "living_street", "trunk", "primary_link", "secondary_link", "tertiary_link",
    "trunk_link", "road",
})


def _norm_type(edge: dict) -> str:
    return str(edge.get("type") or "").strip().lower()


def facility_class(edge: dict) -> str:
    """Return facility class code for one directed edge."""
    hw = _norm_type(edge)
    cw = classify_cycleway_edge(edge)

    if hw == "cycleway" or (cw and cw["cluster"] == CLUSTER_SEGREGATED):
        return "segregated"
    if cw and cw["cluster"] == CLUSTER_BUS_SHARED:
        return "bus_lane"
    if cw and cw["cluster"] == CLUSTER_CAR_SHARED:
        return "painted_lane"
    if hw in _SHARED_PATH_TYPES:
        # Dedicated cycle infra already handled; remaining path/footway ≈ shared
        return "shared_path"
    if hw == "service":
        return "service"
    if hw in _CARRIAGEWAY_TYPES or hw:
        return "carriageway"
    return "other"


def protection_rank(cls: str) -> int:
    return PROTECTION_RANK.get(cls, PROTECTION_RANK["other"])


def smooth_facility_classes(edges: list[dict], window_m: float = C.SMOOTH_WINDOW_M) -> list[str]:
    """
    Replace isolated class flips that don't span ~window_m with neighbour class.

    Algorithm: compute raw classes; for each index, if the run of this class
    covering this edge totals < window_m and both sides (if any) share another
    class, replace the run with that neighbour class.
    """
    n = len(edges)
    if n == 0:
        return []
    raw = [facility_class(e) for e in edges]
    lengths = [float(e.get("length") or 0.0) for e in edges]
    out = list(raw)

    i = 0
    while i < n:
        j = i + 1
        while j < n and raw[j] == raw[i]:
            j += 1
        run_len = sum(lengths[k] for k in range(i, j))
        left = raw[i - 1] if i > 0 else None
        right = raw[j] if j < n else None
        if run_len < window_m and left is not None and right is not None and left == right and left != raw[i]:
            for k in range(i, j):
                out[k] = left
        i = j
    return out
