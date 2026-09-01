"""
Rider feedback as a routing overlay.

Reports collected by the TBT Report flag (ride_reports.py) are turned into
additive effects on the existing cost arrays. Two scopes:

- personal: a signed-in rider's own reports, applied only to their requests
- global:   reports corroborated by several distinct contributors (Phase C)

Two rules hold this together:

1. **The graph is never written.** Reports patch copies of the cost arrays, not
   `G`. OSM tags on the pickle stay exactly as the pipeline produced them, so a
   bad report can be deleted and the effect vanishes on the next rebuild.
2. **The Numba kernel never changes.** Every category maps onto an array the
   A* already reads, so `_cost_optimized` keeps its frozen signature:

   impassable -> shared.impassable = 1     (same path as a live closure)
   unlit      -> tables.unlit_base = 0.5
   surface    -> tables.bad_surf_base = 3.0
   dangerous  -> tables.risk += 1.0
   speeding   -> tables.speed_stress = max(current, 0.15)

Patching uses `dataclasses.replace` over copy-on-write arrays: only the arrays
an effect actually touches are copied, and the module-level tables are never
mutated, so concurrent requests cannot see each other's overlay.

Kill-switches: CROWD_OVERLAYS=0 disables all apply (POSTs keep working),
CROWD_GLOBAL=0 disables the global scope only.

Note: `_cost_optimized` zeroes risk and speed stress on vehicular-free edges and
surface penalties on steps. A `dangerous` or `speeding` report on a segregated
cycleway is therefore stored and reviewable but changes no cost. That is
intended — the rider is describing traffic that the cost model already knows
cannot reach them.
"""
from __future__ import annotations

import logging
import math
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import numpy as np

log = logging.getLogger("crowd_overlays")

# Deliberately far tighter than the 1000 m route snap: a report is a claim about
# one specific place, and a 300 m snap would quietly blame the wrong road.
SNAP_MAX_DISTANCE_M = 40.0

# Effect magnitudes, chosen to match what the same condition would cost if OSM
# had said it, so a crowd-sourced edge is not weighted more than a mapped one.
UNLIT_VALUE = 0.5
BAD_SURFACE_VALUE = 3.0
RISK_INCREMENT = 1.0
# The SPEED_DIFF_LOW_KMH band from app.py — "faster than comfortable", not
# "lethal". A report cannot claim more than the lowest real stress band.
SPEED_STRESS_VALUE = 0.15

# Same-way expansion: a rider reporting a pothole means this stretch of road,
# not this 30 m arc, but only for conditions that genuinely run along a way.
SAME_WAY_RADIUS_M = 40.0
DANGEROUS_JUNCTION_RADIUS_M = 12.0

_PATCH_CACHE_MAX = 8

_LOCK = threading.RLock()
_G = None
_GLOBAL: "CrowdEffects" = None  # type: ignore[assignment]
_PERSONAL: dict[str, "CrowdEffects"] = {}
# Bumped whenever effects or the base arrays change; every cached patch keys on
# it, so a rebuild silently invalidates the lot.
_VERSION = 0
_PATCH_CACHE: "OrderedDict[tuple, tuple]" = OrderedDict()
_LAST_REBUILD: dict[str, Any] = {}


def enabled() -> bool:
    raw = os.environ.get("CROWD_OVERLAYS", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def global_enabled() -> bool:
    """Phase C. Off leaves personal overlays working."""
    raw = os.environ.get("CROWD_GLOBAL", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


@dataclass
class CrowdEffects:
    """Edge-id keyed effects for one scope. Empty is the common case."""

    closed: set[int] = field(default_factory=set)
    unlit: set[int] = field(default_factory=set)
    surf: set[int] = field(default_factory=set)
    risk: dict[int, float] = field(default_factory=dict)
    speed: dict[int, float] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.closed or self.unlit or self.surf or self.risk or self.speed)

    def edge_count(self) -> int:
        return len(self.closed | self.unlit | self.surf | set(self.risk) | set(self.speed))

    def merged_with(self, other: "CrowdEffects") -> "CrowdEffects":
        out = CrowdEffects(
            closed=self.closed | other.closed,
            unlit=self.unlit | other.unlit,
            surf=self.surf | other.surf,
            risk=dict(self.risk),
            speed=dict(self.speed),
        )
        for eid, value in other.risk.items():
            out.risk[eid] = out.risk.get(eid, 0.0) + value
        for eid, value in other.speed.items():
            out.speed[eid] = max(out.speed.get(eid, 0.0), value)
        return out


_EMPTY = CrowdEffects()
_GLOBAL = CrowdEffects()


def init(G) -> None:
    """Bind the graph. Snapping needs tfl_live.init(G) to have run already."""
    global _G
    _G = G


def version() -> int:
    return _VERSION


# ---------------------------------------------------------------------------
# Ingest: report rows -> edge effects
# ---------------------------------------------------------------------------

def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _eid(u, v) -> int | None:
    try:
        return int(_G[u][v]["_eid"])
    except (KeyError, TypeError, ValueError):
        return None


def _edge_data(u, v) -> dict | None:
    try:
        return _G[u][v]
    except (KeyError, TypeError):
        return None


def snap_report(lat: float, lon: float) -> dict | None:
    """
    Nearest edge within 40 m, or None. A miss is recorded on the row (so the
    report is not lost) but produces no effect.
    """
    import tfl_live

    try:
        hit = tfl_live.snap_to_edge(lat, lon, max_distance_m=SNAP_MAX_DISTANCE_M)
    except Exception as exc:
        log.warning("crowd snap failed: %s", exc)
        return None
    if hit is None:
        return None

    data = _edge_data(hit.u, hit.v) or {}
    return {
        "u": hit.u,
        "v": hit.v,
        "eid": _eid(hit.u, hit.v),
        "dist_m": float(hit.distance_m),
        "anchor_node": hit.anchor_node,
        "osm_id": str(data.get("osmid") or data.get("osm_id") or "") or None,
        # Forensics only. Never written back onto G.
        "snapshot": {
            "lit": data.get("lit"),
            "surface": data.get("surface"),
            "smoothness": data.get("smoothness"),
            "barrier": data.get("barrier"),
            "highway": data.get("highway"),
            "name": data.get("name"),
        },
    }


def _same_way_edges(u, v, osm_id: str | None) -> set[int]:
    """
    Edges of the same OSM way within 40 m of the snapped edge.

    A pothole or a fast-traffic complaint describes a stretch of road; the graph
    splits that road at every junction, so one arc would under-apply it.
    """
    eids: set[int] = set()
    base = _eid(u, v)
    if base is not None:
        eids.add(base)
    if not osm_id or _G is None:
        return eids

    try:
        ux = float(_G.nodes[u]["x"])
        uy = float(_G.nodes[u]["y"])
        vx = float(_G.nodes[v]["x"])
        vy = float(_G.nodes[v]["y"])
    except (KeyError, TypeError, ValueError):
        return eids
    cx, cy = (ux + vx) / 2.0, (uy + vy) / 2.0

    for node in (u, v):
        for nbr in list(_G.successors(node)) + list(_G.predecessors(node)):
            for a, b in ((node, nbr), (nbr, node)):
                data = _edge_data(a, b)
                if data is None:
                    continue
                other = str(data.get("osmid") or data.get("osm_id") or "")
                if other != osm_id:
                    continue
                try:
                    bx = float(_G.nodes[b]["x"])
                    by = float(_G.nodes[b]["y"])
                except (KeyError, TypeError, ValueError):
                    continue
                if _haversine_m(cx, cy, bx, by) > SAME_WAY_RADIUS_M:
                    continue
                eid = _eid(a, b)
                if eid is not None:
                    eids.add(eid)
    return eids


def _dangerous_edges(u, v, anchor_node, dist_m: float) -> set[int]:
    """
    The snapped edge, or every car-allowed arc into the junction when the report
    was made right at a junction flagged dangerous — which is where a rider
    describing a near miss is almost always standing.
    """
    base = _eid(u, v)
    eids: set[int] = set() if base is None else {base}
    if _G is None or dist_m > DANGEROUS_JUNCTION_RADIUS_M:
        return eids
    node = _G.nodes.get(anchor_node) if anchor_node in _G.nodes else None
    if not node or not node.get("is_dangerous_junction", False):
        return eids

    for nbr in list(_G.predecessors(anchor_node)) + list(_G.successors(anchor_node)):
        for a, b in ((nbr, anchor_node), (anchor_node, nbr)):
            data = _edge_data(a, b)
            if data is None:
                continue
            eid = _eid(a, b)
            if eid is not None:
                eids.add(eid)
    return eids


def _both_directions(u, v) -> set[int]:
    """A gate blocks both ways. One direction would just route the rider back."""
    out: set[int] = set()
    for a, b in ((u, v), (v, u)):
        eid = _eid(a, b)
        if eid is not None:
            out.add(eid)
    return out


def effects_from_rows(rows: Iterable[dict]) -> CrowdEffects:
    """
    Build effects from already-snapped rows. Rows without a snap are skipped:
    a report with no edge has nowhere to apply.
    """
    eff = CrowdEffects()
    for row in rows:
        category = str(row.get("category") or "")
        if category in ("", "general"):
            continue
        u, v = row.get("snapped_u"), row.get("snapped_v")
        if u is None or v is None:
            continue
        dist_m = float(row.get("snap_dist_m") or 0.0)
        osm_id = row.get("osm_id")

        if category == "impassable":
            eff.closed |= _both_directions(u, v)
        elif category == "unlit":
            base = _eid(u, v)
            if base is not None:
                eff.unlit.add(base)
        elif category == "surface":
            eff.surf |= _same_way_edges(u, v, osm_id)
        elif category == "speeding":
            for eid in _same_way_edges(u, v, osm_id):
                eff.speed[eid] = max(eff.speed.get(eid, 0.0), SPEED_STRESS_VALUE)
        elif category == "dangerous":
            for eid in _dangerous_edges(u, v, row.get("snapped_anchor") or u, dist_m):
                eff.risk[eid] = eff.risk.get(eid, 0.0) + RISK_INCREMENT
    return eff


def ingest_rows(rows: Iterable[dict]) -> tuple[list[dict], list[dict]]:
    """
    Snap unsnapped rows. Returns (snapped_rows, writeback) where `writeback` is
    the set of column updates to persist so snapping happens once, not per rebuild.
    """
    out: list[dict] = []
    writeback: list[dict] = []
    for row in rows:
        if str(row.get("category") or "") in ("", "general"):
            continue
        # Desk replay is stored for debugging but must never steer real routing.
        if row.get("simulate"):
            continue

        if row.get("snapped_u") is not None and row.get("snapped_v") is not None:
            out.append(row)
            continue

        lat, lon = row.get("lat"), row.get("lon")
        if lat is None or lon is None:
            continue
        hit = snap_report(float(lat), float(lon))
        if hit is None:
            # Recorded as a miss so the same row is not re-snapped every cycle.
            writeback.append({
                "client_event_id": row.get("client_event_id"),
                "snap_dist_m": None,
                "applied": "none",
            })
            continue

        row = dict(row)
        row["snapped_u"] = hit["u"]
        row["snapped_v"] = hit["v"]
        row["snapped_eid"] = hit["eid"]
        row["snap_dist_m"] = hit["dist_m"]
        row["osm_id"] = hit["osm_id"]
        row["snapped_anchor"] = hit["anchor_node"]
        payload = dict(row.get("payload") or {})
        payload["snapshot"] = hit["snapshot"]
        row["payload"] = payload
        out.append(row)

        writeback.append({
            "client_event_id": row.get("client_event_id"),
            "snapped_u": str(hit["u"]),
            "snapped_v": str(hit["v"]),
            "snapped_eid": hit["eid"],
            "snap_dist_m": hit["dist_m"],
            "osm_id": hit["osm_id"],
            "payload": payload,
        })
    return out, writeback


# ---------------------------------------------------------------------------
# Patching: copy-on-write onto the cost arrays
# ---------------------------------------------------------------------------

def _set_indices(arr: np.ndarray, eids: Iterable[int], value: float) -> np.ndarray:
    idx = [e for e in eids if 0 <= e < arr.shape[0]]
    if not idx:
        return arr
    out = arr.copy()
    out[idx] = value
    return out


def _add_values(arr: np.ndarray, values: dict[int, float]) -> np.ndarray:
    idx = [e for e in values if 0 <= e < arr.shape[0]]
    if not idx:
        return arr
    out = arr.copy()
    for eid in idx:
        out[eid] = out[eid] + values[eid]
    return out


def _max_values(arr: np.ndarray, values: dict[int, float]) -> np.ndarray:
    idx = [e for e in values if 0 <= e < arr.shape[0]]
    if not idx:
        return arr
    out = arr.copy()
    for eid in idx:
        out[eid] = max(float(out[eid]), values[eid])
    return out


def apply_effects(tables, shared, eff: CrowdEffects):
    """
    Patched (tables, shared). Untouched arrays are shared by reference, so a
    surface-only rider pays one array copy rather than five.
    """
    if tables is None or not eff:
        return tables, shared

    patched: dict[str, np.ndarray] = {}
    if eff.risk:
        patched["risk"] = _add_values(tables.risk, eff.risk)
    if eff.unlit:
        patched["unlit_base"] = _set_indices(tables.unlit_base, eff.unlit, UNLIT_VALUE)
    if eff.surf:
        patched["bad_surf_base"] = _set_indices(
            tables.bad_surf_base, eff.surf, BAD_SURFACE_VALUE
        )
    if eff.speed:
        patched["speed_stress"] = _max_values(tables.speed_stress, eff.speed)

    # `_set_indices` returns the input when nothing was in range, so only a real
    # change costs a dataclass copy.
    patched = {k: v for k, v in patched.items() if v is not getattr(tables, k)}
    tables_out = replace(tables, **patched) if patched else tables

    shared_out = shared
    if eff.closed and shared is not None:
        impassable = _set_indices(shared.impassable, eff.closed, 1)
        if impassable is not shared.impassable:
            shared_out = replace(shared, impassable=impassable)
    return tables_out, shared_out


def personal_effects(user_id: str | None) -> CrowdEffects:
    if not user_id:
        return _EMPTY
    with _LOCK:
        return _PERSONAL.get(str(user_id), _EMPTY)


def global_effects() -> CrowdEffects:
    if not global_enabled():
        return _EMPTY
    with _LOCK:
        return _GLOBAL


def scope_effects(user_id: str | None) -> CrowdEffects:
    """Global plus this rider's own. Personal wins by being additive on top."""
    g = global_effects()
    p = personal_effects(user_id)
    if not p:
        return g
    if not g:
        return p
    return g.merged_with(p)


def apply(tables, shared, user_id: str | None = None, avoid_eids: Iterable[int] = ()):
    """
    Patch the cost arrays for one request.

    Returns (tables, shared, info). `info` goes into `meta.crowd` for debugging.

    Results are cached per (scope, version), but only when `shared` is the live
    module-level object: the future-`depart_at` branch builds a throwaway
    `shared` whose patch must not be reused by anyone else.
    """
    info = {
        "enabled": enabled(),
        "scope": "user" if user_id else "anon",
        "personal_edges": 0,
        "global_edges": 0,
        "avoid_points": 0,
        "cached": False,
    }
    if tables is None or not enabled():
        return tables, shared, info

    avoid = {int(e) for e in avoid_eids}
    info["avoid_points"] = len(avoid)
    eff = scope_effects(user_id)
    info["personal_edges"] = personal_effects(user_id).edge_count()
    info["global_edges"] = global_effects().edge_count()

    if avoid:
        # Per-request only, and never cached: these come from the body.
        eff = eff.merged_with(CrowdEffects(closed=set(avoid)))
    if not eff:
        return tables, shared, info

    import edge_cost_arrays

    cacheable = not avoid and shared is edge_cost_arrays.get_shared_overlays()
    if cacheable:
        key = (str(user_id or ""), _VERSION)
        with _LOCK:
            hit = _PATCH_CACHE.get(key)
            if hit is not None:
                _PATCH_CACHE.move_to_end(key)
                info["cached"] = True
                return hit[0], hit[1], info

    tables_out, shared_out = apply_effects(tables, shared, eff)

    if cacheable:
        with _LOCK:
            _PATCH_CACHE[(str(user_id or ""), _VERSION)] = (tables_out, shared_out)
            while len(_PATCH_CACHE) > _PATCH_CACHE_MAX:
                _PATCH_CACHE.popitem(last=False)
    return tables_out, shared_out, info


def snap_avoid_points(points: Iterable[tuple[float, float]]) -> set[int]:
    """
    (lat, lon) pairs -> edge ids blocked in both directions for this request.

    The client has no edge ids, so an impassable replan sends the place instead.
    """
    eids: set[int] = set()
    for lat, lon in points:
        hit = snap_report(float(lat), float(lon))
        if hit is None:
            continue
        eids |= _both_directions(hit["u"], hit["v"])
    return eids


# ---------------------------------------------------------------------------
# Rebuild
# ---------------------------------------------------------------------------

def _bump_version_locked() -> None:
    global _VERSION
    _VERSION += 1
    _PATCH_CACHE.clear()


def bump_version() -> None:
    """Discard every cached patch — call after the base arrays are rebaked."""
    with _LOCK:
        _bump_version_locked()


def set_effects(
    global_eff: CrowdEffects | None = None,
    personal: dict[str, CrowdEffects] | None = None,
) -> None:
    """Install new effects and invalidate the patch cache. Tests use this too."""
    global _GLOBAL, _PERSONAL
    with _LOCK:
        if global_eff is not None:
            _GLOBAL = global_eff
        if personal is not None:
            _PERSONAL = personal
        _bump_version_locked()


def reset_for_tests() -> None:
    global _GLOBAL, _PERSONAL, _VERSION
    with _LOCK:
        _GLOBAL = CrowdEffects()
        _PERSONAL = {}
        _VERSION = 0
        _PATCH_CACHE.clear()
        _LAST_REBUILD.clear()


# ---------------------------------------------------------------------------
# Global corroboration
# ---------------------------------------------------------------------------

# One rider is an opinion; two independent riders are evidence. These numbers
# are a starting guess and should be revisited once there are real rows.
GLOBAL_WINDOW_DAYS = 90
RETENTION_WINDOW_DAYS = 180
MIN_CONTRIBUTORS = 2
# A single stationary, well-located impassable report is trusted: you stop dead
# at a locked gate, and that signature is hard to produce by accident.
SOLO_IMPASSABLE_MAX_SPEED_MPS = 0.8
SOLO_IMPASSABLE_MAX_H_ACC_M = 15.0
# How close two reports must be to be talking about the same thing.
CLUSTER_RADIUS_M = {
    "impassable": 30.0,
    "surface": 30.0,
    "speeding": 30.0,
    "unlit": 30.0,
    "dangerous": 25.0,
}

# Unlit BFS expansion limits. A rider passing a dead streetlight is describing
# the dark stretch, not the 30 m arc, but the dark stretch has to end somewhere.
UNLIT_BFS_MAX_LENGTH_M = 150.0
UNLIT_BFS_MAX_EDGES = 12
UNLIT_BFS_STOP_CAR_ROADS = 3


def _contributor_key(row: dict) -> str | None:
    """
    Who is speaking. Guests count via device_id, so a guest report can still
    corroborate — it just cannot be anyone's personal overlay.
    """
    user_id = row.get("user_id")
    if user_id:
        return str(user_id)
    device_id = row.get("device_id")
    if device_id:
        return f"dev:{device_id}"
    return None


def _parse_created_at(row: dict) -> datetime | None:
    raw = row.get("created_at")
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _is_confident_solo(row: dict) -> bool:
    fix = (row.get("payload") or {}).get("fix") or {}
    speed = fix.get("speed_mps")
    h_acc = fix.get("h_acc_m")
    if speed is None or h_acc is None:
        return False
    try:
        return (
            float(speed) < SOLO_IMPASSABLE_MAX_SPEED_MPS
            and float(h_acc) < SOLO_IMPASSABLE_MAX_H_ACC_M
        )
    except (TypeError, ValueError):
        return False


def eligible_for_global(row: dict, now: datetime | None = None) -> bool:
    """Rows that may be counted towards a global threshold."""
    if row.get("simulate"):
        return False
    # The test-build flag: steers the reporter's own routes, nobody else's.
    if row.get("personal_only"):
        return False
    if str(row.get("category") or "") in ("", "general"):
        return False
    if row.get("snapped_u") is None or row.get("snapped_v") is None:
        return False
    if _contributor_key(row) is None:
        return False
    created = _parse_created_at(row)
    if created is None:
        return False
    now = now or datetime.now(timezone.utc)
    return (now - created) <= timedelta(days=RETENTION_WINDOW_DAYS)


def cluster_rows(rows: list[dict]) -> list[list[dict]]:
    """
    Greedy single-link clustering of same-category reports by great-circle
    distance. Volumes are small (hundreds), so O(n^2) within a category is fine
    and buys us no PostGIS dependency.
    """
    clusters: list[list[dict]] = []
    for row in rows:
        radius = CLUSTER_RADIUS_M.get(str(row.get("category")), 30.0)
        lat, lon = row.get("lat"), row.get("lon")
        if lat is None or lon is None:
            continue
        placed = False
        for cluster in clusters:
            head = cluster[0]
            if str(head.get("category")) != str(row.get("category")):
                continue
            if _haversine_m(
                float(head["lon"]), float(head["lat"]), float(lon), float(lat)
            ) <= radius:
                cluster.append(row)
                placed = True
                break
        if not placed:
            clusters.append([row])
    return clusters


def _cluster_passes(cluster: list[dict], now: datetime) -> bool:
    """Enough distinct contributors inside the corroboration window."""
    cutoff = now - timedelta(days=GLOBAL_WINDOW_DAYS)
    recent = [r for r in cluster if (_parse_created_at(r) or cutoff) >= cutoff]
    if not recent:
        return False
    contributors = {_contributor_key(r) for r in recent}
    contributors.discard(None)
    if len(contributors) >= MIN_CONTRIBUTORS:
        return True
    category = str(recent[0].get("category"))
    return category == "impassable" and any(_is_confident_solo(r) for r in recent)


def expand_unlit(u, v) -> set[int]:
    """
    Grow an unlit report along the connected run of lit-mapped road.

    A rider passing one dead streetlight usually means the stretch, but the
    stretch has to end: at an already-unlit edge (someone mapped it), at a real
    junction (a different road), at 150 m, or at 12 edges.
    """
    base = _eid(u, v)
    eids: set[int] = set() if base is None else {base}
    if _G is None:
        return eids

    start = _edge_data(u, v) or {}
    # OSM already says dark here — record the report, change nothing.
    if not _is_lit(start):
        return eids

    name = start.get("name")
    osm_id = str(start.get("osmid") or start.get("osm_id") or "")
    seen_edges = {(u, v), (v, u)}
    total_m = float(start.get("length") or 0.0)
    queue = [v, u]
    visited_nodes = set()

    while queue and len(eids) < UNLIT_BFS_MAX_EDGES and total_m < UNLIT_BFS_MAX_LENGTH_M:
        node = queue.pop(0)
        if node in visited_nodes:
            continue
        visited_nodes.add(node)

        nd = _G.nodes.get(node) if node in _G.nodes else None
        if nd and int(nd.get("car_physical_road_count", 0)) >= UNLIT_BFS_STOP_CAR_ROADS:
            continue

        for nbr in list(_G.successors(node)) + list(_G.predecessors(node)):
            for a, b in ((node, nbr), (nbr, node)):
                if (a, b) in seen_edges:
                    continue
                data = _edge_data(a, b)
                if data is None:
                    continue
                same_way = (
                    str(data.get("osmid") or data.get("osm_id") or "") == osm_id
                    or (name is not None and data.get("name") == name)
                )
                if not same_way:
                    continue
                seen_edges.add((a, b))
                if not _is_lit(data):
                    # Someone already mapped this as dark; the run ends here.
                    continue
                eid = _eid(a, b)
                if eid is None or eid in eids:
                    continue
                if (
                    len(eids) >= UNLIT_BFS_MAX_EDGES
                    or total_m >= UNLIT_BFS_MAX_LENGTH_M
                ):
                    break
                eids.add(eid)
                total_m += float(data.get("length") or 0.0)
                queue.append(nbr)
    return eids


def _is_lit(data: dict) -> bool:
    return str(data.get("lit", "")).strip().lower() in ("yes", "true", "24/7", "1")


def build_global_effects(
    rows: list[dict],
    now: datetime | None = None,
) -> tuple[CrowdEffects, list[dict]]:
    """
    Corroborated effects plus the `applied` write-backs for rows that crossed a
    threshold. Global apply also gets the unlit BFS expansion, which personal
    deliberately does not: one rider's opinion should not darken a whole street.
    """
    now = now or datetime.now(timezone.utc)
    eligible = [r for r in rows if eligible_for_global(r, now)]
    eff = CrowdEffects()
    writeback: list[dict] = []

    for cluster in cluster_rows(eligible):
        if not _cluster_passes(cluster, now):
            continue
        category = str(cluster[0].get("category"))
        for row in cluster:
            u, v = row.get("snapped_u"), row.get("snapped_v")
            if u is None or v is None:
                continue
            if category == "impassable":
                eff.closed |= _both_directions(u, v)
            elif category == "unlit":
                eff.unlit |= expand_unlit(u, v)
            elif category == "surface":
                eff.surf |= _same_way_edges(u, v, row.get("osm_id"))
            elif category == "speeding":
                for eid in _same_way_edges(u, v, row.get("osm_id")):
                    eff.speed[eid] = max(eff.speed.get(eid, 0.0), SPEED_STRESS_VALUE)
            elif category == "dangerous":
                anchor = row.get("snapped_anchor") or u
                dist_m = float(row.get("snap_dist_m") or 0.0)
                for eid in _dangerous_edges(u, v, anchor, dist_m):
                    eff.risk[eid] = eff.risk.get(eid, 0.0) + RISK_INCREMENT
            if row.get("applied") != "global" and row.get("client_event_id"):
                writeback.append({
                    "client_event_id": row["client_event_id"],
                    "applied": "global",
                })
    return eff, writeback


def build_personal_effects(rows: list[dict]) -> dict[str, CrowdEffects]:
    """
    Per-user effects from that user's own reports. No corroboration needed —
    you are allowed to be wrong about your own routes.

    Guest rows have no user_id and so cannot form a personal overlay; a guest
    `personal_only` row is inert by construction, which is worth logging.
    """
    by_user: dict[str, list[dict]] = {}
    orphaned_personal = 0
    for row in rows:
        if row.get("simulate"):
            continue
        user_id = row.get("user_id")
        if not user_id:
            if row.get("personal_only"):
                orphaned_personal += 1
            continue
        by_user.setdefault(str(user_id), []).append(row)

    if orphaned_personal:
        log.info(
            "crowd_overlays: %d personal_only guest rows are inert "
            "(no user_id, excluded from global)",
            orphaned_personal,
        )
    return {uid: effects_from_rows(rs) for uid, rs in by_user.items()}


def rebuild() -> dict[str, Any]:
    """
    Pull reports, snap the new ones, and rebuild both scopes.

    Best-effort throughout: a failure here leaves the previous overlay in place
    rather than dropping riders back to an unfiltered network mid-day.
    """
    import ride_reports

    t0 = time.perf_counter()
    since = datetime.now(timezone.utc) - timedelta(days=RETENTION_WINDOW_DAYS)
    rows, err = ride_reports.list_ride_reports(since=since)
    if err:
        log.warning("crowd_overlays.rebuild: %s", err)
        return {"error": err}

    snapped, writeback = ingest_rows(rows)
    if writeback:
        ride_reports.mark_snapped(writeback)

    global_eff, applied_writeback = build_global_effects(snapped)
    personal = build_personal_effects(snapped)
    set_effects(global_eff=global_eff, personal=personal)
    if applied_writeback:
        ride_reports.mark_snapped(applied_writeback)

    summary = {
        "rows": len(rows),
        "snapped": len(snapped),
        "global_edges": global_eff.edge_count(),
        "personal_users": len(personal),
        "rebuild_ms": round((time.perf_counter() - t0) * 1000, 1),
    }
    with _LOCK:
        _LAST_REBUILD.clear()
        _LAST_REBUILD.update(summary)
    log.info("crowd_overlays: rebuilt %s", summary)
    return summary


def _refresh_loop(interval_s: int) -> None:
    import edge_cost_arrays

    while True:
        time.sleep(interval_s)
        try:
            rebuild()
            # The base `shared` is rebuilt from scratch here, so every cached
            # patch is stale — set_effects already bumped the version.
            edge_cost_arrays.refresh_shared_overlays_from_graph()
            bump_version()
        except Exception as exc:
            log.warning("crowd_overlays refresh failed: %s", exc)


def start_background_refresh(interval_s: int | None = None) -> None:
    """Rebuild now, then every CROWD_REFRESH_INTERVAL_S (default 600 s)."""
    if not enabled():
        log.info("crowd_overlays: disabled (CROWD_OVERLAYS=0)")
        return
    interval_s = int(
        interval_s or os.environ.get("CROWD_REFRESH_INTERVAL_S", "600") or 600
    )
    try:
        rebuild()
    except Exception as exc:
        log.warning("crowd_overlays: initial rebuild failed: %s", exc)
    threading.Thread(
        target=_refresh_loop, args=(interval_s,), daemon=True
    ).start()


def status() -> dict[str, Any]:
    with _LOCK:
        return {
            "enabled": enabled(),
            "global_enabled": global_enabled(),
            "version": _VERSION,
            "global_edges": _GLOBAL.edge_count(),
            "personal_users": len(_PERSONAL),
            "patch_cache": len(_PATCH_CACHE),
            **_LAST_REBUILD,
        }
