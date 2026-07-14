"""
Lazy edge polyline store: lat/lon coords keyed by ``_eid``, not NetworkX edge dicts.

Request-path geometry must not mutate ``G`` (thread-safety under threaded WSGI).
Resolution: geom store → read-only ``d['_coords']`` if present → WKT parse (no writeback).
"""
from __future__ import annotations

import functools
import logging
import math
import os
from dataclasses import dataclass
from typing import Any

import numpy as np

log = logging.getLogger("edge_geom_store")

# Spatial tolerance for cache alignment (degrees ≈ 1.1 m).
ALIGN_ABS_TOL_DEG = 1e-5

_GEOM_STORE: "EdgeGeomStore | None" = None


@dataclass
class EdgeGeomStore:
    """Process-global polyline arrays (typically mmap'd .npy)."""

    offsets: np.ndarray  # int64, length n_edges+1
    flat: np.ndarray  # float32 (n_pts, 2) lat, lon
    n_edges: int

    def coords_for_eid(self, eid: int) -> list[list[float]]:
        if eid < 0 or eid >= self.n_edges:
            raise IndexError(f"eid {eid} out of range [0, {self.n_edges})")
        a = int(self.offsets[eid])
        b = int(self.offsets[eid + 1])
        # Copy out of mmap for JSON / callers that may retain the list
        return self.flat[a:b].tolist()


def install_geom_store(offsets: np.ndarray, flat: np.ndarray) -> EdgeGeomStore:
    global _GEOM_STORE
    offsets = np.asarray(offsets, dtype=np.int64)
    flat = np.asarray(flat, dtype=np.float32)
    if flat.ndim != 2 or flat.shape[1] != 2:
        raise ValueError(f"geom flat must be (n,2), got {flat.shape}")
    if offsets.ndim != 1 or len(offsets) < 1:
        raise ValueError("geom offsets must be 1-D")
    n_edges = int(len(offsets) - 1)
    if int(offsets[-1]) != flat.shape[0]:
        raise ValueError(
            f"offsets[-1]={offsets[-1]} != flat rows {flat.shape[0]}"
        )
    store = EdgeGeomStore(offsets=offsets, flat=flat, n_edges=n_edges)
    _GEOM_STORE = store
    log.info("edge_geom_store: installed %d edges, %d points", n_edges, flat.shape[0])
    return store


def get_geom_store() -> EdgeGeomStore | None:
    return _GEOM_STORE


def clear_geom_store() -> None:
    global _GEOM_STORE
    _GEOM_STORE = None


def load_geom_npy(
    offsets_path,
    flat_path,
    *,
    mmap_mode: str | None = "r",
) -> EdgeGeomStore:
    """Load standalone .npy geom arrays (mmap_mode='r' by default)."""
    offsets = np.load(offsets_path, mmap_mode=mmap_mode)
    flat = np.load(flat_path, mmap_mode=mmap_mode)
    return install_geom_store(offsets, flat)


@functools.lru_cache(maxsize=65536)
def _parse_wkt_oriented_cached(
    wkt: str,
    u_x: float,
    u_y: float,
) -> tuple[tuple[float, float], ...]:
    """Pure WKT→lat/lon tuples; cached; does not touch NetworkX."""
    from shapely.wkt import loads as load_wkt

    line = load_wkt(wkt)
    segment_coords = list(line.coords)
    start_dist = (segment_coords[0][0] - u_x) ** 2 + (segment_coords[0][1] - u_y) ** 2
    end_dist = (segment_coords[-1][0] - u_x) ** 2 + (segment_coords[-1][1] - u_y) ** 2
    if end_dist < start_dist:
        segment_coords.reverse()
    return tuple((float(y), float(x)) for x, y in segment_coords)


def parse_edge_coords_no_write(G, u, v, d: dict) -> list[list[float]]:
    """
    [[lat, lon], ...] oriented u→v. Never mutates ``d`` or ``G``.
    """
    wkt = d.get("geometry")
    if wkt:
        try:
            u_x = float(G.nodes[u].get("_x", G.nodes[u]["x"]))
            u_y = float(G.nodes[u].get("_y", G.nodes[u]["y"]))
            return [list(p) for p in _parse_wkt_oriented_cached(str(wkt), u_x, u_y)]
        except Exception:
            pass
    nu, nv = G.nodes[u], G.nodes[v]
    return [
        [float(nu.get("_y", nu["y"])), float(nu.get("_x", nu["x"]))],
        [float(nv.get("_y", nv["y"])), float(nv.get("_x", nv["x"]))],
    ]


def coords_for_edge(d: dict | None, G, u, v) -> list[list[float]]:
    """
    Resolve polyline for edge (u,v):
      1) EdgeGeomStore by d['_eid']
      2) read-only d['_coords'] if already present (bootstrap legacy)
      3) WKT parse without writeback
    """
    if d is None:
        nu, nv = G.nodes[u], G.nodes[v]
        return [
            [float(nu.get("_y", nu["y"])), float(nu.get("_x", nu["x"]))],
            [float(nv.get("_y", nv["y"])), float(nv.get("_x", nv["x"]))],
        ]

    store = _GEOM_STORE
    eid = d.get("_eid")
    if store is not None and eid is not None:
        try:
            return store.coords_for_eid(int(eid))
        except (IndexError, TypeError, ValueError):
            pass

    cached = d.get("_coords")
    if cached is not None:
        return list(cached)

    return parse_edge_coords_no_write(G, u, v, d)


def _xy_close(a: float, b: float, abs_tol: float = ALIGN_ABS_TOL_DEG) -> bool:
    return math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=abs_tol)


def _node_latlon(G, nid) -> tuple[float, float]:
    nd = G.nodes[nid]
    return float(nd.get("_y", nd["y"])), float(nd.get("_x", nd["x"]))


def assert_cache_edge_alignment(
    G,
    *,
    edge_u: np.ndarray,
    edge_v: np.ndarray,
    geom_offsets: np.ndarray,
    geom_flat: np.ndarray,
    n_table_edges: int,
    sample_n: int = 256,
    abs_tol: float = ALIGN_ABS_TOL_DEG,
) -> None:
    """
    Fail-closed structural + spatial check that cache rows match G.
    Raises ValueError on mismatch.
    """
    if getattr(G, "is_multigraph", lambda: False)():
        raise ValueError(
            "routing cache does not support MultiDiGraph "
            "(need edge keys in sidecar); refuse cache"
        )

    n = int(edge_u.shape[0])
    n_graph = int(G.number_of_edges())
    if n != n_graph:
        raise ValueError(f"edge count cache={n} != graph={n_graph}")
    if n != int(n_table_edges):
        raise ValueError(f"edge count cache={n} != tables={n_table_edges}")
    if int(len(geom_offsets) - 1) != n:
        raise ValueError(
            f"geom_offsets length {len(geom_offsets)} != n_edges+1 ({n + 1})"
        )
    if int(geom_offsets[-1]) != int(geom_flat.shape[0]):
        raise ValueError("geom_offsets[-1] != geom_flat rows")

    full = os.environ.get("ROUTING_CACHE_ALIGN", "").strip().lower() in (
        "full",
        "1",
        "true",
        "yes",
        "all",
    )
    if full:
        eids = range(n)
    else:
        sample_n = max(3, min(int(sample_n), n))
        stride = max(1, n // sample_n)
        eids = sorted(
            set([0, n // 2, n - 1] + list(range(0, n, stride)))
        )[: max(sample_n, 3)]

    def _xy_to_node(xy) -> tuple[float, float]:
        return (float(xy[0]), float(xy[1]))

    for i in eids:
        u = _xy_to_node(edge_u[i])
        v = _xy_to_node(edge_v[i])
        if not G.has_edge(u, v):
            # float drift on node id tuples: try tolerance match via nearby
            raise ValueError(
                f"alignment: eid={i} endpoints {u!r}->{v!r} not in G"
            )
        # Node coords vs stored endpoints
        u_lat, u_lon = _node_latlon(G, u)
        v_lat, v_lon = _node_latlon(G, v)
        # edge_u/v store (lon, lat) = (x, y) as node ids
        if not (
            _xy_close(u[0], u_lon, abs_tol)
            and _xy_close(u[1], u_lat, abs_tol)
            and _xy_close(v[0], v_lon, abs_tol)
            and _xy_close(v[1], v_lat, abs_tol)
        ):
            raise ValueError(
                f"alignment: eid={i} endpoint xy drift beyond {abs_tol}"
            )

        a = int(geom_offsets[i])
        b = int(geom_offsets[i + 1])
        if b - a < 2:
            raise ValueError(f"alignment: eid={i} geom has <2 points")
        first = geom_flat[a]
        last = geom_flat[b - 1]
        # flat is lat, lon
        if not (
            _xy_close(first[0], u_lat, abs_tol)
            and _xy_close(first[1], u_lon, abs_tol)
            and _xy_close(last[0], v_lat, abs_tol)
            and _xy_close(last[1], v_lon, abs_tol)
        ):
            raise ValueError(
                f"alignment: eid={i} geom endpoints != u/v "
                f"(first={first.tolist()} u=[{u_lat},{u_lon}] "
                f"last={last.tolist()} v=[{v_lat},{v_lon}])"
            )

    checked = list(eids) if not isinstance(eids, range) else list(eids)
    log.info(
        "edge_geom_store: alignment OK (%d edges checked, tol=%g deg)",
        len(checked) if not full else n,
        abs_tol,
    )
