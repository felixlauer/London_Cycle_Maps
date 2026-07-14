"""
Instrumented A* pathfinding for the routing backend.

Provides unidirectional (NetworkX-compatible) and bidirectional A* over a
directed graph with arbitrary (u, v, d) -> cost weight callables.

Phase A: pure-Python CSR A* (`astar_csr_unidirectional`) — neighbors via
indptr/indices/eid, heuristic via lat/lon arrays, cost via cost_by_eid(eid).
"""
from __future__ import annotations

import heapq
import math
import time
from itertools import count
from typing import Any, Callable

import networkx as nx

WeightFn = Callable[[Any, Any, dict], float]
HeuristicFn = Callable[[Any, Any], float]
CostByEidFn = Callable[[int], float]


def _empty_stats() -> dict[str, float | int]:
    return {"expansions": 0, "edge_relaxations": 0, "elapsed_s": 0.0}


def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Same formula as routing_heuristic.haversine_m (kept local to avoid cycles)."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def astar_csr_unidirectional(
    csr,
    source,
    target,
    cost_by_eid: CostByEidFn,
    cost_per_m: float = 1.0,
    *,
    heuristic_mode: str = "phase_b",
    G=None,
) -> tuple[list, dict[str, float | int]]:
    """
    Uni A* over GraphCSR. Returns NetworkX node-id path + stats.

    cost_by_eid(eid) must match make_array_cost_by_eid_* (same impassable / formula).

    heuristic_mode:
      - "phase_b" (default): precomputed lat_rad / lon_rad / cos_lat
      - "phase_a": lon/lat arrays + full haversine (Phase A style)
      - "nodes": G.nodes dict heuristic (isolates Phase B in benches; needs G)
    """
    t0 = time.perf_counter()
    stats = _empty_stats()

    node_to_idx = csr.node_to_idx
    idx_to_node = csr.idx_to_node
    indptr = csr.indptr
    indices = csr.indices
    eid_a = csr.eid
    lon = csr.lon
    lat = csr.lat

    s = node_to_idx.get(source)
    t = node_to_idx.get(target)
    if s is None or t is None:
        stats["elapsed_s"] = time.perf_counter() - t0
        raise nx.NetworkXNoPath(f"No path from {source} to {target}")

    if s == t:
        stats["elapsed_s"] = time.perf_counter() - t0
        return [source], stats

    scale = float(cost_per_m)
    mode = (heuristic_mode or "phase_b").strip().lower()

    if mode == "nodes":
        if G is None:
            raise ValueError("heuristic_mode='nodes' requires G")
        from routing_heuristic import _node_xy, haversine_m

        goal_lon, goal_lat = _node_xy(G.nodes[target])

        def h(u_idx: int) -> float:
            u_node = idx_to_node[u_idx]
            lon_u, lat_u = _node_xy(G.nodes[u_node])
            return scale * haversine_m(lon_u, lat_u, goal_lon, goal_lat)

    elif mode == "phase_a":
        goal_lon = float(lon[t])
        goal_lat = float(lat[t])

        def h(u_idx: int) -> float:
            return scale * _haversine_m(
                float(lon[u_idx]), float(lat[u_idx]), goal_lon, goal_lat
            )

    else:
        # phase_b (default)
        goal_lon_rad = float(csr.lon_rad[t])
        goal_lat_rad = float(csr.lat_rad[t])
        goal_cos = float(csr.cos_lat[t])
        lat_rad = csr.lat_rad
        lon_rad = csr.lon_rad
        cos_lat = csr.cos_lat

        def h(u_idx: int) -> float:
            p1 = float(lat_rad[u_idx])
            dl = float(lon_rad[u_idx]) - goal_lon_rad
            dp = p1 - goal_lat_rad
            a = (
                math.sin(dp * 0.5) ** 2
                + float(cos_lat[u_idx]) * goal_cos * math.sin(dl * 0.5) ** 2
            )
            return scale * (2.0 * 6371000.0 * math.asin(min(1.0, math.sqrt(a))))

    c = count()
    open_heap: list[tuple[float, int, int]] = []
    g_score: dict[int, float] = {s: 0.0}
    parents: dict[int, int] = {}
    heapq.heappush(open_heap, (h(s), next(c), s))
    closed: set[int] = set()

    while open_heap:
        _, _, current = heapq.heappop(open_heap)
        if current in closed:
            continue
        closed.add(current)
        stats["expansions"] += 1

        if current == t:
            path_idx = [t]
            while path_idx[-1] != s:
                path_idx.append(parents[path_idx[-1]])
            path_idx.reverse()
            path = [idx_to_node[i] for i in path_idx]
            stats["elapsed_s"] = time.perf_counter() - t0
            return path, stats

        start = int(indptr[current])
        end = int(indptr[current + 1])
        g_cur = g_score[current]
        for k in range(start, end):
            stats["edge_relaxations"] += 1
            neighbor = int(indices[k])
            try:
                edge_cost = float(cost_by_eid(int(eid_a[k])))
            except Exception:
                continue
            tentative = g_cur + edge_cost
            if tentative < g_score.get(neighbor, float("inf")):
                parents[neighbor] = current
                g_score[neighbor] = tentative
                f = tentative + h(neighbor)
                heapq.heappush(open_heap, (f, next(c), neighbor))

    stats["elapsed_s"] = time.perf_counter() - t0
    raise nx.NetworkXNoPath(f"No path from {source} to {target}")


def astar_unidirectional(
    G: nx.DiGraph,
    source,
    target,
    heuristic: HeuristicFn,
    weight_fn: WeightFn,
) -> tuple[list, dict[str, float | int]]:
    """NetworkX-compatible A* with expansion counters."""
    t0 = time.perf_counter()
    stats = _empty_stats()

    if source == target:
        stats["elapsed_s"] = time.perf_counter() - t0
        return [source], stats

    c = count()
    open_heap: list[tuple[float, int, Any]] = []
    g_score: dict[Any, float] = {source: 0.0}
    parents: dict[Any, Any] = {}
    heapq.heappush(open_heap, (heuristic(source, target), next(c), source))
    closed: set[Any] = set()

    while open_heap:
        _, _, current = heapq.heappop(open_heap)
        if current in closed:
            continue
        closed.add(current)
        stats["expansions"] += 1

        if current == target:
            path = [target]
            while path[-1] != source:
                path.append(parents[path[-1]])
            path.reverse()
            stats["elapsed_s"] = time.perf_counter() - t0
            return path, stats

        for neighbor in G.succ[current]:
            stats["edge_relaxations"] += 1
            edge_data = G[current][neighbor]
            try:
                edge_cost = float(weight_fn(current, neighbor, edge_data))
            except Exception:
                continue
            tentative = g_score[current] + edge_cost
            if tentative < g_score.get(neighbor, float("inf")):
                parents[neighbor] = current
                g_score[neighbor] = tentative
                f = tentative + heuristic(neighbor, target)
                heapq.heappush(open_heap, (f, next(c), neighbor))

    stats["elapsed_s"] = time.perf_counter() - t0
    raise nx.NetworkXNoPath(f"No path from {source} to {target}")


def astar_bidirectional(
    G: nx.DiGraph,
    source,
    target,
    heuristic_fwd: HeuristicFn,
    heuristic_bwd: HeuristicFn,
    weight_fn: WeightFn,
) -> tuple[list, dict[str, float | int]]:
    """Alternating bidirectional A*; edge costs always evaluated forward."""
    t0 = time.perf_counter()
    stats = _empty_stats()

    if source == target:
        stats["elapsed_s"] = time.perf_counter() - t0
        return [source], stats

    c = count()
    g_f: dict[Any, float] = {source: 0.0}
    g_b: dict[Any, float] = {target: 0.0}
    parent_f: dict[Any, Any] = {}
    parent_b: dict[Any, Any] = {}

    open_f: list[tuple[float, int, Any]] = [
        (heuristic_fwd(source, target), next(c), source)
    ]
    open_b: list[tuple[float, int, Any]] = [
        (heuristic_bwd(target, source), next(c), target)
    ]
    closed_f: set[Any] = set()
    closed_b: set[Any] = set()

    mu = float("inf")
    meeting: Any = None

    def _maybe_meet(node: Any, g_fwd: float, g_back: float) -> None:
        nonlocal mu, meeting
        total = g_fwd + g_back
        if total < mu:
            mu = total
            meeting = node

    def _expand_forward(current: Any) -> None:
        for neighbor in G.succ[current]:
            stats["edge_relaxations"] += 1
            edge_data = G[current][neighbor]
            try:
                edge_cost = float(weight_fn(current, neighbor, edge_data))
            except Exception:
                continue
            tentative = g_f[current] + edge_cost
            if tentative < g_f.get(neighbor, float("inf")):
                g_f[neighbor] = tentative
                parent_f[neighbor] = current
                f = tentative + heuristic_fwd(neighbor, target)
                heapq.heappush(open_f, (f, next(c), neighbor))
                if neighbor in g_b:
                    _maybe_meet(neighbor, tentative, g_b[neighbor])

    def _expand_backward(current: Any) -> None:
        for predecessor in G.pred[current]:
            stats["edge_relaxations"] += 1
            edge_data = G[predecessor][current]
            try:
                edge_cost = float(weight_fn(predecessor, current, edge_data))
            except Exception:
                continue
            tentative = g_b[current] + edge_cost
            if tentative < g_b.get(predecessor, float("inf")):
                g_b[predecessor] = tentative
                parent_b[predecessor] = current
                f = tentative + heuristic_bwd(predecessor, source)
                heapq.heappush(open_b, (f, next(c), predecessor))
                if predecessor in g_f:
                    _maybe_meet(predecessor, g_f[predecessor], tentative)

    def _top_f(heap: list) -> float:
        return heap[0][0] if heap else float("inf")

    while open_f or open_b:
        if mu < float("inf") and _top_f(open_f) >= mu and _top_f(open_b) >= mu:
            break

        expand_forward = True
        if not open_b:
            expand_forward = True
        elif not open_f:
            expand_forward = False
        else:
            expand_forward = _top_f(open_f) <= _top_f(open_b)

        if expand_forward:
            while open_f:
                _, _, current = heapq.heappop(open_f)
                if current in closed_f:
                    continue
                closed_f.add(current)
                stats["expansions"] += 1
                if current in g_b:
                    _maybe_meet(current, g_f[current], g_b[current])
                _expand_forward(current)
                break
        else:
            while open_b:
                _, _, current = heapq.heappop(open_b)
                if current in closed_b:
                    continue
                closed_b.add(current)
                stats["expansions"] += 1
                if current in g_f:
                    _maybe_meet(current, g_f[current], g_b[current])
                _expand_backward(current)
                break

    if meeting is None:
        stats["elapsed_s"] = time.perf_counter() - t0
        raise nx.NetworkXNoPath(f"No path from {source} to {target}")

    # Reconstruct source -> meeting via forward parents.
    fwd: list[Any] = [meeting]
    cur = meeting
    while cur != source:
        if cur not in parent_f:
            stats["elapsed_s"] = time.perf_counter() - t0
            raise nx.NetworkXNoPath(f"No forward path from {source} to meeting node")
        cur = parent_f[cur]
        fwd.append(cur)
    fwd.reverse()

    # Reconstruct meeting -> target via backward parents.
    bwd: list[Any] = []
    cur = meeting
    while cur != target:
        if cur not in parent_b:
            break
        cur = parent_b[cur]
        bwd.append(cur)

    path = fwd + bwd
    stats["elapsed_s"] = time.perf_counter() - t0
    return path, stats


def run_astar(
    G: nx.DiGraph,
    source,
    target,
    *,
    algorithm: str,
    heuristic_fwd: HeuristicFn,
    heuristic_bwd: HeuristicFn | None,
    weight_fn: WeightFn,
    csr=None,
    cost_by_eid: CostByEidFn | None = None,
    cost_per_m: float | None = None,
    numba_kwargs: dict | None = None,
) -> tuple[list, dict[str, float | int]]:
    """Dispatch to Numba / CSR py / NX uni / bi.

    Prefer Numba when numba_kwargs is set and NUMBA_ASTAR is on.
    Else CSR py when csr + cost_by_eid + cost_per_m are set.
    """
    if algorithm == "uni":
        if numba_kwargs is not None:
            import pathfinding_numba as pn

            if pn.numba_astar_enabled() and pn.is_available():
                return pn.astar_numba_unidirectional(**numba_kwargs)
        if csr is not None and cost_by_eid is not None and cost_per_m is not None:
            return astar_csr_unidirectional(
                csr, source, target, cost_by_eid, cost_per_m=cost_per_m
            )
        return astar_unidirectional(G, source, target, heuristic_fwd, weight_fn)
    if heuristic_bwd is None:
        raise ValueError("heuristic_bwd required for bidirectional search")
    return astar_bidirectional(
        G, source, target, heuristic_fwd, heuristic_bwd, weight_fn
    )
