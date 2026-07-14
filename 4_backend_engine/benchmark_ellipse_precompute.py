#!/usr/bin/env python3
"""
Benchmark elliptical subgraph filtering + O(1) precomputed weights vs full-graph baseline.

Does NOT run in CI — operator runs manually when the graph is available.

  cd c:\\London_Cycle_Maps
  python 4_backend_engine/benchmark_ellipse_precompute.py

Writes:
  0_documentation/testing/ellipse_precompute_report.md
  0_documentation/testing/ellipse_precompute_report.json

See: 0_documentation/route_generation_performance.md
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import types
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "4_backend_engine"
TEST_ROUTES_PATH = REPO_ROOT / "6_verification" / "test_routes.txt"
REPORT_DIR = REPO_ROOT / "0_documentation" / "testing"
REPORT_MD = REPORT_DIR / "ellipse_precompute_report.md"
REPORT_JSON = REPORT_DIR / "ellipse_precompute_report.json"

DETOUR_MULTIPLIER = 1.5

sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(REPO_ROOT / "3_pipeline"))

os.environ.setdefault("FLASK_USE_RELOADER", "0")
os.environ.setdefault("SKIP_DISRUPTION_FETCH", "1")


def _mock_flask():
    flask = types.ModuleType("flask")

    class _Flask:
        def __init__(self, *args, **kwargs):
            pass

        def route(self, *args, **kwargs):
            def decorator(fn):
                return fn

            return decorator

        def before_request(self, fn):
            return fn

    flask.Flask = _Flask
    flask.request = types.SimpleNamespace(args={})
    flask.g = types.SimpleNamespace()
    flask.jsonify = lambda x: x
    sys.modules["flask"] = flask

    cors = types.ModuleType("flask_cors")
    cors.CORS = lambda *args, **kwargs: None
    sys.modules["flask_cors"] = cors


def parse_test_routes(path: Path = TEST_ROUTES_PATH) -> list[dict]:
    routes = []
    current_name = None
    coords: list[tuple[float, float]] = []

    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            m = re.match(r"route\s+\d+:\s*(.+)", line, re.IGNORECASE)
            if m:
                if current_name and len(coords) >= 2:
                    routes.append(_route_dict(current_name, coords))
                current_name = line
                coords = []
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) == 2:
                coords.append((float(parts[0]), float(parts[1])))

    if current_name and len(coords) >= 2:
        routes.append(_route_dict(current_name, coords))
    return routes


def _route_dict(name: str, coords: list[tuple[float, float]]) -> dict:
    return {
        "name": name,
        "start_lat": coords[0][0],
        "start_lon": coords[0][1],
        "end_lat": coords[1][0],
        "end_lon": coords[1][1],
    }


def load_safe_weights() -> dict:
    path = BACKEND_DIR / "user_profiles.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    w = dict(data["profiles"]["preset_safe"]["weights"])
    w["calming_source"] = "both"
    return w


def node_lon_lat(G: nx.DiGraph, node) -> tuple[float, float]:
    nd = G.nodes[node]
    return float(nd["x"]), float(nd["y"])


def nodes_in_ellipse(
    G: nx.DiGraph,
    start_node,
    end_node,
    *,
    detour_mult: float = DETOUR_MULTIPLIER,
) -> tuple[set, float, float]:
    """Return nodes inside haversine ellipse and (D, threshold)."""
    from routing_heuristic import haversine_m

    slon, slat = node_lon_lat(G, start_node)
    elon, elat = node_lon_lat(G, end_node)
    d_straight = haversine_m(slon, slat, elon, elat)
    threshold = d_straight * detour_mult

    inside: set = set()
    for n in G.nodes:
        nd = G.nodes[n]
        if "x" not in nd or "y" not in nd:
            continue
        nlon, nlat = float(nd["x"]), float(nd["y"])
        if haversine_m(slon, slat, nlon, nlat) + haversine_m(nlon, nlat, elon, elat) <= threshold:
            inside.add(n)

    return inside, d_straight, threshold


def bootstrap():
    _mock_flask()
    os.chdir(BACKEND_DIR)
    import park_opening_hours
    import tfl_live
    import app as app_mod
    import pathfinding
    from routing_heuristic import (
        compute_optimized_cost_per_metre_lower_bound,
        get_route_heuristic_epsilon,
        make_heuristic,
    )

    G = app_mod.G
    if G is None:
        raise RuntimeError("Graph failed to load.")
    return (
        G,
        app_mod,
        pathfinding,
        park_opening_hours,
        tfl_live,
        make_heuristic,
        compute_optimized_cost_per_metre_lower_bound,
        get_route_heuristic_epsilon,
    )


def run_route_benchmark(
    G,
    app_mod,
    pathfinding_mod,
    park_opening_hours,
    tfl_live,
    make_heuristic,
    compute_lb,
    route: dict,
    weights: dict,
    eps: float,
) -> dict:
    from app import BARRIER_HARD_COST

    start_snap = tfl_live.snap_to_edge(route["start_lat"], route["start_lon"])
    end_snap = tfl_live.snap_to_edge(route["end_lat"], route["end_lon"])
    if not start_snap or not end_snap:
        raise RuntimeError(f"Could not snap: {route['name']}")

    start_node = start_snap.anchor_node
    end_node = end_snap.anchor_node

    unique_hours = G.graph.get("park_opening_hours_unique") or []
    at_time = park_opening_hours.london_now()
    hours_map, fallback_open = park_opening_hours.build_request_hours_context(
        unique_hours, at_time
    )

    # --- Elliptical filter ---
    t0 = time.perf_counter()
    inside, d_straight, threshold = nodes_in_ellipse(G, start_node, end_node)
    t_filter = time.perf_counter() - t0

    local_graph = G.subgraph(inside).copy()
    global_nodes = G.number_of_nodes()
    ellipse_nodes = local_graph.number_of_nodes()
    ellipse_edges = local_graph.number_of_edges()
    reduction_pct = (
        100.0 * (1.0 - ellipse_nodes / global_nodes) if global_nodes else 0.0
    )

    weight_fn = app_mod.make_weight_optimized(weights, hours_map, fallback_open)

    # --- Precompute ---
    t0 = time.perf_counter()
    precomputed_weights: dict[tuple, float] = {}
    for u, v, d in local_graph.edges(data=True):
        precomputed_weights[(u, v)] = weight_fn(u, v, d)
    t_precompute = time.perf_counter() - t0

    def lookup_weight(u, v, _d):
        return precomputed_weights.get((u, v), BARRIER_HARD_COST)

    scale = compute_lb(weights) * (1.0 + eps)
    h_fwd = make_heuristic(end_node, G, cost_per_m=scale)

    # --- A* on local graph with O(1) lookups ---
    t0 = time.perf_counter()
    path, stats = pathfinding_mod.astar_unidirectional(
        local_graph,
        start_node,
        end_node,
        h_fwd,
        lookup_weight,
    )
    t_astar = time.perf_counter() - t0

    length_m = 0.0
    for i in range(len(path) - 1):
        u, v = path[i], path[i + 1]
        length_m += float((local_graph.get_edge_data(u, v) or {}).get("length", 0))

    return {
        "route": route["name"],
        "start_node": str(start_node),
        "end_node": str(end_node),
        "haversine_m": round(d_straight, 1),
        "ellipse_threshold_m": round(threshold, 1),
        "global_nodes": global_nodes,
        "ellipse_nodes": ellipse_nodes,
        "ellipse_edges": ellipse_edges,
        "reduction_pct": round(reduction_pct, 1),
        "filter_s": round(t_filter, 3),
        "precompute_s": round(t_precompute, 3),
        "astar_s": round(t_astar, 3),
        "total_s": round(t_filter + t_precompute + t_astar, 3),
        "expansions": stats["expansions"],
        "edge_relaxations": stats["edge_relaxations"],
        "length_m": round(length_m, 1),
        "path_found": len(path) > 1 or start_node == end_node,
    }


def format_md_table(rows: list[dict]) -> str:
    header = (
        "| Route | Global nodes | Ellipse nodes | Reduction % | "
        "Precompute (s) | A* (s) | Total (s) | Expansions | Length (m) |"
    )
    sep = "|---|---:|---:|---:|---:|---:|---:|---:|---:|"
    lines = [header, sep]
    for r in rows:
        lines.append(
            f"| {r['route']} | {r['global_nodes']:,} | {r['ellipse_nodes']:,} | "
            f"{r['reduction_pct']:.1f}% | {r['precompute_s']:.2f} | {r['astar_s']:.2f} | "
            f"{r['total_s']:.2f} | {r['expansions']:,} | {r['length_m']:.0f} |"
        )
    return "\n".join(lines)


def main() -> None:
    print("Bootstrapping engine...", flush=True)
    (
        G,
        app_mod,
        pathfinding_mod,
        park_opening_hours,
        tfl_live,
        make_heuristic,
        compute_lb,
        get_eps,
    ) = bootstrap()

    eps = get_eps()
    weights = load_safe_weights()
    routes = parse_test_routes()
    rows: list[dict] = []

    print(f"Preset: safe | epsilon: {eps} | DETOUR_MULTIPLIER: {DETOUR_MULTIPLIER}", flush=True)

    for route in routes:
        print(f"  {route['name']}...", flush=True)
        rows.append(
            run_route_benchmark(
                G,
                app_mod,
                pathfinding_mod,
                park_opening_hours,
                tfl_live,
                make_heuristic,
                compute_lb,
                route,
                weights,
                eps,
            )
        )

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "preset": "safe",
        "heuristic_epsilon": eps,
        "detour_multiplier": DETOUR_MULTIPLIER,
        "graph_nodes": G.number_of_nodes(),
        "graph_edges": G.number_of_edges(),
    }

    md_parts = [
        "# Ellipse + precompute benchmark",
        "",
        f"Generated: {meta['generated_at']}",
        f"Graph: {meta['graph_nodes']:,} nodes, {meta['graph_edges']:,} edges",
        f"Preset: **safe** | ε = {meta['heuristic_epsilon']} | "
        f"`DETOUR_MULTIPLIER` = {meta['detour_multiplier']}",
        "",
        "Pipeline per route: elliptical node filter → precompute `make_weight_optimized` "
        "on local edges → unidirectional A* with dict lookup.",
        "",
        "Spec: [`route_generation_performance.md`](../route_generation_performance.md)",
        "",
        format_md_table(rows),
        "",
        "## Notes",
        "",
        "- `filter_s` (ellipse scan) is included in `total_s` but not shown in table columns; see JSON.",
        "- Compare `total_s` to full-graph uni A* in [`routing_performance_report.md`](routing_performance_report.md).",
        "",
        "Re-run: `python 4_backend_engine/benchmark_ellipse_precompute.py`",
    ]

    REPORT_MD.write_text("\n".join(md_parts), encoding="utf-8")
    REPORT_JSON.write_text(
        json.dumps({"meta": meta, "runs": rows}, indent=2),
        encoding="utf-8",
    )

    print(f"\nReport: {REPORT_MD}")
    print(f"JSON:   {REPORT_JSON}")
    print("ELLIPSE BENCHMARK DONE", flush=True)


if __name__ == "__main__":
    main()
