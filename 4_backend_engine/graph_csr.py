"""
CSR graph for routing A* (Phase A/B — pure Python).

Built once after edge `_eid` stamps. Neighbors via indptr/indices/eid;
heuristic via lat/lon (+ Phase B radian / cos_lat precompute).

Kill-switch: CSR_ASTAR=0|false|no|off → callers use NetworkX A*
(still may use CSR lat/lon for heuristics when CSR is built).
"""
from __future__ import annotations

import logging
import math
import os
import time
from dataclasses import dataclass

import numpy as np

log = logging.getLogger("graph_csr")

GRAPH_CSR = None  # GraphCSR | None


@dataclass
class GraphCSR:
    """Dense-index CSR over a directed NetworkX graph."""

    n_nodes: int
    n_edges: int
    # NetworkX node id at dense index i
    idx_to_node: list
    # node id -> dense index (hash map; build once)
    node_to_idx: dict
    indptr: np.ndarray  # int64, length n_nodes+1
    indices: np.ndarray  # int32, successor dense indices
    eid: np.ndarray  # int32, edge row into EdgeCostTables
    lon: np.ndarray  # float64, WGS84 x
    lat: np.ndarray  # float64, WGS84 y
    # Phase B: precomputed for haversine hot path
    lon_rad: np.ndarray  # float64
    lat_rad: np.ndarray  # float64
    cos_lat: np.ndarray  # float64
    build_s: float


def csr_astar_enabled() -> bool:
    raw = os.environ.get("CSR_ASTAR", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def get_csr() -> GraphCSR | None:
    return GRAPH_CSR


def set_csr(csr: GraphCSR | None) -> None:
    global GRAPH_CSR
    GRAPH_CSR = csr


def _out_degree(G, nid) -> int:
    """Out-arc count matching G.edges(data=True) / MultiDiGraph parallels."""
    if G.is_multigraph():
        return sum(len(keyed) for keyed in G.succ[nid].values())
    return len(G.succ[nid])


def _iter_out(G, nid):
    """Yield (neighbor, edge_attr) for each outgoing arc."""
    if G.is_multigraph():
        for nbr, keyed in G.succ[nid].items():
            for ed in keyed.values():
                yield nbr, ed
    else:
        for nbr, ed in G.succ[nid].items():
            yield nbr, ed


def build_csr(G) -> GraphCSR:
    """Build successor CSR + lat/lon from G. Requires d['_eid'] on every edge."""
    t0 = time.perf_counter()
    idx_to_node = list(G.nodes())
    n = len(idx_to_node)
    node_to_idx = {nid: i for i, nid in enumerate(idx_to_node)}

    lon = np.empty(n, dtype=np.float64)
    lat = np.empty(n, dtype=np.float64)
    for i, nid in enumerate(idx_to_node):
        nd = G.nodes[nid]
        if "_x" in nd and "_y" in nd:
            lon[i] = float(nd["_x"])
            lat[i] = float(nd["_y"])
        else:
            lon[i] = float(nd["x"])
            lat[i] = float(nd["y"])

    degrees = np.empty(n, dtype=np.int64)
    for i, nid in enumerate(idx_to_node):
        degrees[i] = _out_degree(G, nid)

    indptr = np.zeros(n + 1, dtype=np.int64)
    np.cumsum(degrees, out=indptr[1:])
    m = int(indptr[-1])
    indices = np.empty(m, dtype=np.int32)
    eid = np.empty(m, dtype=np.int32)

    missing_eid = 0
    for i, nid in enumerate(idx_to_node):
        base = int(indptr[i])
        k = 0
        for nbr, ed in _iter_out(G, nid):
            indices[base + k] = node_to_idx[nbr]
            e = ed.get("_eid")
            if e is None:
                missing_eid += 1
                eid[base + k] = -1
            else:
                eid[base + k] = int(e)
            k += 1

    build_s = time.perf_counter() - t0
    # Use math.radians (not np.radians) so Phase B h matches routing_heuristic.haversine_m.
    lon_rad = np.empty(n, dtype=np.float64)
    lat_rad = np.empty(n, dtype=np.float64)
    cos_lat = np.empty(n, dtype=np.float64)
    for i in range(n):
        lon_rad[i] = math.radians(float(lon[i]))
        lat_rad[i] = math.radians(float(lat[i]))
        cos_lat[i] = math.cos(lat_rad[i])
    if missing_eid:
        log.warning("graph_csr: %d edges missing _eid (will hard-block in CSR A*)", missing_eid)
    log.info(
        "graph_csr: built %d nodes, %d arcs in %.1f s",
        n,
        m,
        build_s,
    )
    return GraphCSR(
        n_nodes=n,
        n_edges=m,
        idx_to_node=idx_to_node,
        node_to_idx=node_to_idx,
        indptr=indptr,
        indices=indices,
        eid=eid,
        lon=lon,
        lat=lat,
        lon_rad=lon_rad,
        lat_rad=lat_rad,
        cos_lat=cos_lat,
        build_s=build_s,
    )


def haversine_idx_m(csr: GraphCSR, u_idx: int, goal_lon_rad: float, goal_lat_rad: float, goal_cos_lat: float) -> float:
    """Metres between dense node u and a fixed goal (precomputed radians)."""
    # Same formula as routing_heuristic.haversine_m; uses Phase B arrays.
    p1 = float(csr.lat_rad[u_idx])
    dl = float(csr.lon_rad[u_idx]) - goal_lon_rad
    dp = p1 - goal_lat_rad
    a = (
        math.sin(dp * 0.5) ** 2
        + float(csr.cos_lat[u_idx]) * goal_cos_lat * math.sin(dl * 0.5) ** 2
    )
    return 2.0 * 6371000.0 * math.asin(min(1.0, math.sqrt(a)))
