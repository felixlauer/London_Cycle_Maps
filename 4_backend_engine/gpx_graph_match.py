"""Cheap GPX → graph stitch: follow the snapped edge in GPX heading.

A* runs only when consecutive snaps are not on the same edge or adjacent
nodes. Immediate A-B-A reversals are dropped after concatenate.

This is a trial matcher, not the live scorer.
"""
from __future__ import annotations

import math

import networkx as nx

JUMP_RATIO = 2.5
JUMP_EXTRA_M = 250.0


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def bearing_rad(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return math.atan2(y, x)


def node_latlon(G, n) -> tuple[float, float]:
    d = G.nodes[n]
    return float(d["y"]), float(d["x"])


def edge_length_m(G, u, v) -> float:
    data = G.get_edge_data(u, v)
    if not data:
        return 0.0
    if isinstance(next(iter(data.values()), None), dict):
        data = next(iter(data.values()))
    return float(data.get("length", 0) or 0)


def path_length_m(G, path: list) -> float:
    return sum(edge_length_m(G, u, v) for u, v in zip(path, path[1:]))


def count_reversals(path: list) -> int:
    return sum(1 for i in range(len(path) - 2) if path[i] == path[i + 2])


def collapse_2cycles(path: list) -> list:
    out = []
    for n in path:
        if len(out) >= 2 and out[-2] == n:
            out.pop()
            continue
        if out and out[-1] == n:
            continue
        out.append(n)
    return out


def snap_track(tfl_live, pts, snap_max_m: float, *, endpoints_wide: bool = True):
    snaps = []
    skipped = 0
    n = len(pts)
    wide = float(tfl_live.SNAP_MAX_DISTANCE_M_ROUTE)
    for i, (lat, lon) in enumerate(pts):
        cap = wide if endpoints_wide and i in (0, n - 1) else snap_max_m
        hit = tfl_live.snap_to_edge(lat, lon, max_distance_m=cap)
        if hit is None and cap < wide:
            hit = tfl_live.snap_to_edge(lat, lon, max_distance_m=wide)
        if hit is None:
            skipped += 1
            continue
        snaps.append(
            {
                "i": i,
                "lat": lat,
                "lon": lon,
                "u": hit.u,
                "v": hit.v,
                "frac": float(hit.edge_fraction),
                "snap_lat": float(hit.snap_lat),
                "snap_lon": float(hit.snap_lon),
                "anchor": hit.anchor_node,
                "snap_m": round(float(hit.distance_m), 1),
            }
        )
    return snaps, skipped


def _heading(snaps: list[dict], i: int) -> float | None:
    if i + 1 < len(snaps):
        a, b = snaps[i], snaps[i + 1]
        if haversine_m(a["lat"], a["lon"], b["lat"], b["lon"]) > 1.0:
            return bearing_rad(a["lat"], a["lon"], b["lat"], b["lon"])
    if i > 0:
        a, b = snaps[i - 1], snaps[i]
        if haversine_m(a["lat"], a["lon"], b["lat"], b["lon"]) > 1.0:
            return bearing_rad(a["lat"], a["lon"], b["lat"], b["lon"])
    return None


def _forward_node(G, snap: dict, heading: float | None):
    u, v = snap["u"], snap["v"]
    if heading is None:
        return snap["anchor"]
    uy, ux = node_latlon(G, u)
    vy, vx = node_latlon(G, v)
    edge_h = bearing_rad(uy, ux, vy, vx)
    return v if math.cos(heading - edge_h) >= 0.0 else u


def _back_node(snap: dict, forward):
    return snap["v"] if forward == snap["u"] else snap["u"]


def _connect(G, src, dst, pathfinding, make_heuristic, weight_fn):
    if src == dst:
        return [src], 0.0, False
    if G.has_edge(src, dst):
        return [src, dst], edge_length_m(G, src, dst), False
    h = make_heuristic(dst, G, cost_per_m=1.0)
    path, _stats = pathfinding.astar_unidirectional(G, src, dst, h, weight_fn)
    return path, path_length_m(G, path), True


def stitch_edge_follow(G, pathfinding, make_heuristic, weight_fn, snaps: list[dict]):
    """Walk each snapped edge in GPX heading; A* only for non-neighbours."""
    if len(snaps) < 2:
        raise RuntimeError(f"Need >=2 snaps (got {len(snaps)})")

    h0 = _heading(snaps, 0)
    curr = _back_node(snaps[0], _forward_node(G, snaps[0], h0))
    nodes = [curr]
    legs = []
    skipped = 0
    n_local = 0
    n_astar = 0
    last_lat, last_lon = snaps[0]["lat"], snaps[0]["lon"]

    for i, snap in enumerate(snaps):
        heading = _heading(snaps, i)
        target = _forward_node(G, snap, heading)
        if target == curr:
            last_lat, last_lon = snap["lat"], snap["lon"]
            continue
        try:
            path, graph_m, used_astar = _connect(
                G, curr, target, pathfinding, make_heuristic, weight_fn
            )
        except nx.NetworkXNoPath:
            skipped += 1
            continue

        hav = haversine_m(last_lat, last_lon, snap["lat"], snap["lon"])
        jump = used_astar and graph_m > max(JUMP_RATIO * max(hav, 1.0), hav + JUMP_EXTRA_M)
        if jump:
            other = snap["u"] if target == snap["v"] else snap["v"]
            if other != curr:
                try:
                    path2, m2, astar2 = _connect(
                        G, curr, other, pathfinding, make_heuristic, weight_fn
                    )
                    if m2 + 1.0 < graph_m:
                        path, graph_m, used_astar, target = path2, m2, astar2, other
                        jump = used_astar and graph_m > max(
                            JUMP_RATIO * max(hav, 1.0), hav + JUMP_EXTRA_M
                        )
                except nx.NetworkXNoPath:
                    pass
            if jump:
                skipped += 1
                continue

        if used_astar:
            n_astar += 1
        else:
            n_local += 1
        nodes.extend(path[1:])
        curr = path[-1]
        last_lat, last_lon = snap["lat"], snap["lon"]
        legs.append(
            {
                "from_i": snap["i"],
                "graph_m": round(graph_m, 1),
                "haversine_m": round(hav, 1),
                "jump": bool(jump),
                "astar": used_astar,
            }
        )

    nodes = collapse_2cycles(nodes)
    if len(nodes) < 2:
        raise RuntimeError("Edge-follow stitch collapsed to a single node.")
    return nodes, {
        "n_snaps": len(snaps),
        "n_legs": len(legs),
        "n_local_legs": n_local,
        "n_astar_legs": n_astar,
        "n_skipped": skipped,
        "n_jump_legs": sum(1 for leg in legs if leg["jump"]),
        "n_reversals": count_reversals(nodes),
        "n_nodes": len(nodes),
        "length_m": round(path_length_m(G, nodes), 1),
        "legs": legs,
    }
