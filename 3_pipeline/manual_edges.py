"""
Inject persistent manual graph connections at build time (no extra pipeline step).

Reads: 3_pipeline/manual_graph_edges.json
Called from build_graph.py after OSM edges are loaded, before island cleanup.
"""
from __future__ import annotations

import json
import math
import os
from typing import Any

import networkx as nx

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_EDGES_PATH = os.path.join(SCRIPT_DIR, "manual_graph_edges.json")

# Match build_graph.py node rounding and point snap tolerance.
NODE_ROUND = 6
SNAP_THRESHOLD_DEG = 0.0002

# Edge attribute keys copied from a reference OSM segment (same set as build_graph attrs).
_TEMPLATE_ATTR_KEYS = (
    "name",
    "risk",
    "type",
    "surface",
    "lit",
    "maxspeed",
    "width",
    "bridge",
    "tunnel",
    "junction",
    "smoothness",
    "cycleway",
    "cycleway_left",
    "cycleway_right",
    "cycleway_both",
    "segregated",
    "cycleway_separation",
    "cycleway_left_separation",
    "cycleway_right_separation",
    "cycleway_buffer",
    "cycleway_width",
    "cycleway_surface",
    "cycleway_smoothness",
    "lcn_ref",
    "rcn_ref",
    "ncn_ref",
    "cycle_network",
    "hgv",
    "traffic_calming",
)


def load_manual_connections(path: str | None = None) -> list[dict]:
    path = path or DEFAULT_EDGES_PATH
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return list(data.get("connections") or [])


def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _node_lon_lat(G: nx.DiGraph, node: tuple) -> tuple[float, float]:
    data = G.nodes[node]
    if "x" in data and "y" in data:
        return float(data["x"]), float(data["y"])
    return float(node[0]), float(node[1])


def _dist_deg(lon: float, lat: float, node: tuple, G: nx.DiGraph) -> float:
    nx_lon, nx_lat = _node_lon_lat(G, node)
    return math.hypot(lon - nx_lon, lat - nx_lat)


def _resolve_endpoint(G: nx.DiGraph, spec: dict) -> tuple | None:
    osm_id = str(spec.get("osm_id", "")).strip()
    lon = float(spec["lon"])
    lat = float(spec["lat"])
    rounded = (round(lon, NODE_ROUND), round(lat, NODE_ROUND))

    candidates: list[tuple] = []
    if G.has_node(rounded):
        candidates.append(rounded)

    if osm_id:
        for u, v, data in G.edges(data=True):
            if str(data.get("osm_id", "")).strip() != osm_id:
                continue
            for node in (u, v):
                if node not in candidates:
                    candidates.append(node)

    if not candidates:
        best_node = None
        best_dist = float("inf")
        for node in G.nodes:
            d = _dist_deg(lon, lat, node, G)
            if d < best_dist:
                best_dist = d
                best_node = node
        if best_node is not None and best_dist <= SNAP_THRESHOLD_DEG:
            return best_node
        return None

    return min(candidates, key=lambda n: _dist_deg(lon, lat, n, G))


def _template_attrs(G: nx.DiGraph, osm_id: str) -> dict[str, Any]:
    for _u, _v, data in G.edges(data=True):
        if str(data.get("osm_id", "")).strip() == osm_id:
            return {k: data.get(k, "") for k in _TEMPLATE_ATTR_KEYS}
    return {k: "" for k in _TEMPLATE_ATTR_KEYS}


def _wkt_line(lon1: float, lat1: float, lon2: float, lat2: float) -> str:
    return f"LINESTRING({lon1} {lat1}, {lon2} {lat2})"


def _ensure_node_coords(G: nx.DiGraph, node: tuple) -> None:
    G.nodes[node]["x"], G.nodes[node]["y"] = float(node[0]), float(node[1])


def apply_manual_edges(G: nx.DiGraph, path: str | None = None) -> int:
    """
    Add bidirectional manual connections from JSON. Returns number of directed edges added.
    Skips connections whose endpoints cannot be resolved or edge already exists.
    """
    connections = load_manual_connections(path)
    if not connections:
        return 0

    added = 0
    for conn in connections:
        conn_id = str(conn.get("id") or "manual").strip()
        from_node = _resolve_endpoint(G, conn.get("from") or {})
        to_node = _resolve_endpoint(G, conn.get("to") or {})
        if from_node is None or to_node is None:
            print(
                f"   [!] Manual connection '{conn_id}': could not resolve endpoints "
                f"(from={from_node is not None}, to={to_node is not None})"
            )
            continue
        if from_node == to_node:
            print(f"   [!] Manual connection '{conn_id}': endpoints coincide; skipped.")
            continue

        copy_from = str(conn.get("copy_tags_from_osm_id") or "").strip()
        attrs = _template_attrs(G, copy_from) if copy_from else {k: "" for k in _TEMPLATE_ATTR_KEYS}
        highway = str(conn.get("highway") or attrs.get("type") or "cycleway").strip().lower()
        attrs["type"] = highway

        lon1, lat1 = _node_lon_lat(G, from_node)
        lon2, lat2 = _node_lon_lat(G, to_node)
        length_m = _haversine_m(lon1, lat1, lon2, lat2)
        geometry = _wkt_line(lon1, lat1, lon2, lat2)
        manual_osm_id = f"manual:{conn_id}"

        base = {
            **attrs,
            "osm_id": manual_osm_id,
            "length": length_m,
            "geometry": geometry,
        }

        for u, v in ((from_node, to_node), (to_node, from_node)):
            _ensure_node_coords(G, u)
            _ensure_node_coords(G, v)
            if G.has_edge(u, v):
                continue
            G.add_edge(u, v, **base)
            added += 1

        if added:
            print(
                f"   -> Manual '{conn_id}': {from_node} <-> {to_node} "
                f"({length_m:.1f} m, osm_id={manual_osm_id})"
            )

    return added
