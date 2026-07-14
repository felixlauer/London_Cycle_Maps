#!/usr/bin/env python3
"""
Compare unidirectional vs bidirectional A* on all 11 test routes x fast/safe presets.

Does NOT run automatically in CI — operator runs manually after graph is available.

  cd c:\\London_Cycle_Maps
  python 4_backend_engine/benchmark_routing.py

Writes:
  0_documentation/testing/routing_performance_report.md
  0_documentation/testing/routing_performance_report.json
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
REPORT_MD = REPORT_DIR / "routing_performance_report.md"
REPORT_JSON = REPORT_DIR / "routing_performance_report.json"

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


def load_preset_weights() -> dict[str, dict]:
    """Resolved fast/safe vectors from seeded user_profiles.json."""
    path = BACKEND_DIR / "user_profiles.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    profiles = data["profiles"]
    out = {}
    for key, label in (("preset_fast", "fast"), ("preset_safe", "safe")):
        w = dict(profiles[key]["weights"])
        w["calming_source"] = "both"
        out[label] = w
    return out


def path_length_m(G: nx.DiGraph, path: list) -> float:
    total = 0.0
    for i in range(len(path) - 1):
        u, v = path[i], path[i + 1]
        total += float((G.get_edge_data(u, v) or {}).get("length", 0))
    return total


def path_match(ref_nodes: list, cur_nodes: list) -> dict:
    same = ref_nodes == cur_nodes
    ref_edges = set(zip(ref_nodes, ref_nodes[1:])) if len(ref_nodes) > 1 else set()
    cur_edges = set(zip(cur_nodes, cur_nodes[1:])) if len(cur_nodes) > 1 else set()
    shared = len(ref_edges & cur_edges)
    union = len(ref_edges | cur_edges) or 1
    return {
        "exact_match": same,
        "jaccard_edges": round(shared / union, 3),
    }


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
        make_backward_heuristic,
        make_heuristic,
    )

    G = app_mod.G
    if G is None:
        raise RuntimeError("Graph failed to load.")
    return G, app_mod, pathfinding, park_opening_hours, tfl_live, make_heuristic, make_backward_heuristic, compute_optimized_cost_per_metre_lower_bound, get_route_heuristic_epsilon


def run_one(
    G,
    app_mod,
    pathfinding_mod,
    park_opening_hours,
    tfl_live,
    make_heuristic,
    make_backward_heuristic,
    compute_lb,
    route: dict,
    weights: dict,
    algorithm: str,
    eps: float,
) -> dict:
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

    scale = compute_lb(weights) * (1.0 + eps)
    h_fwd = make_heuristic(end_node, G, cost_per_m=scale)
    h_bwd = make_backward_heuristic(start_node, G, cost_per_m=scale)
    weight_fn = app_mod.make_weight_optimized(weights, hours_map, fallback_open)

    t0 = time.perf_counter()
    path, stats = pathfinding_mod.run_astar(
        G,
        start_node,
        end_node,
        algorithm=algorithm,
        heuristic_fwd=h_fwd,
        heuristic_bwd=h_bwd,
        weight_fn=weight_fn,
    )
    elapsed = time.perf_counter() - t0

    return {
        "algorithm": algorithm,
        "elapsed_s": round(elapsed, 3),
        "expansions": stats["expansions"],
        "edge_relaxations": stats["edge_relaxations"],
        "length_m": round(path_length_m(G, path), 1),
        "path_nodes": path,
    }


def format_md_table(rows: list[dict]) -> str:
    header = (
        "| Route | Uni (s) | Bi (s) | Speedup | Uni expansions | "
        "Bi expansions | Length delta (m) | Path match |"
    )
    sep = "|---|---:|---:|---:|---:|---:|---:|---|"
    lines = [header, sep]
    for r in rows:
        match = "exact" if r["exact_match"] else f"jaccard {r['jaccard']:.2f}"
        lines.append(
            f"| {r['route']} | {r['uni_s']:.2f} | {r['bi_s']:.2f} | "
            f"{r['speedup']:.2f}x | {r['uni_exp']} | {r['bi_exp']} | "
            f"{r['length_delta']:+.0f} | {match} |"
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
        make_backward_heuristic,
        compute_lb,
        get_eps,
    ) = bootstrap()

    eps = get_eps()
    routes = parse_test_routes()
    presets = load_preset_weights()

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "graph_nodes": G.number_of_nodes(),
        "graph_edges": G.number_of_edges(),
        "heuristic_epsilon": eps,
        "route_count": len(routes),
        "presets": list(presets.keys()),
    }
    all_runs: list[dict] = []
    summary_by_preset: dict[str, list[dict]] = {k: [] for k in presets}

    for preset_name, weights in presets.items():
        print(f"\n=== Preset: {preset_name} ===", flush=True)
        for route in routes:
            label = route["name"]
            print(f"  {label}...", flush=True)
            uni = run_one(
                G, app_mod, pathfinding_mod, park_opening_hours, tfl_live,
                make_heuristic, make_backward_heuristic, compute_lb,
                route, weights, "uni", eps,
            )
            bi = run_one(
                G, app_mod, pathfinding_mod, park_opening_hours, tfl_live,
                make_heuristic, make_backward_heuristic, compute_lb,
                route, weights, "bi", eps,
            )
            pm = path_match(uni["path_nodes"], bi["path_nodes"])
            speedup = uni["elapsed_s"] / bi["elapsed_s"] if bi["elapsed_s"] > 0 else 0.0
            row = {
                "preset": preset_name,
                "route": label,
                "uni_s": uni["elapsed_s"],
                "bi_s": bi["elapsed_s"],
                "speedup": round(speedup, 2),
                "uni_exp": uni["expansions"],
                "bi_exp": bi["expansions"],
                "uni_relax": uni["edge_relaxations"],
                "bi_relax": bi["edge_relaxations"],
                "uni_length_m": uni["length_m"],
                "bi_length_m": bi["length_m"],
                "length_delta": round(bi["length_m"] - uni["length_m"], 1),
                "exact_match": pm["exact_match"],
                "jaccard": pm["jaccard_edges"],
            }
            summary_by_preset[preset_name].append(row)
            all_runs.append({
                **row,
                "uni": {k: uni[k] for k in uni if k != "path_nodes"},
                "bi": {k: bi[k] for k in bi if k != "path_nodes"},
            })

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    md_parts = [
        "# Routing performance report",
        "",
        f"Generated: {meta['generated_at']}",
        f"Graph: {meta['graph_nodes']:,} nodes, {meta['graph_edges']:,} edges",
        f"Heuristic epsilon: {meta['heuristic_epsilon']}",
        "",
        "Optimized A* only (single search per run). Compares unidirectional "
        "(production default) vs bidirectional (experimental).",
        "",
    ]

    for preset_name, rows in summary_by_preset.items():
        md_parts.append(f"## Preset: {preset_name}")
        md_parts.append("")
        md_parts.append(format_md_table(rows))
        md_parts.append("")

    avg_speedup = {}
    for preset_name, rows in summary_by_preset.items():
        if rows:
            avg_speedup[preset_name] = round(
                sum(r["speedup"] for r in rows) / len(rows), 2
            )
    md_parts.append("## Summary")
    md_parts.append("")
    for preset_name, avg in avg_speedup.items():
        md_parts.append(f"- **{preset_name}** mean speedup (uni/bi): **{avg}x**")
    md_parts.append("")
    md_parts.append(
        "Re-run: `python 4_backend_engine/benchmark_routing.py`"
    )

    md_text = "\n".join(md_parts)
    REPORT_MD.write_text(md_text, encoding="utf-8")

    json_payload = {"meta": meta, "runs": all_runs, "summary": summary_by_preset}
    REPORT_JSON.write_text(json.dumps(json_payload, indent=2), encoding="utf-8")

    print(f"\nReport: {REPORT_MD}")
    print(f"JSON:   {REPORT_JSON}")
    print("BENCHMARK DONE", flush=True)


if __name__ == "__main__":
    main()
