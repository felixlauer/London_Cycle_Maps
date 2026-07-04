"""
Compare A* path costs with h=0 vs admissible haversine heuristics.
Costs must match exactly (optimality preserved).

Run from repo root:
  python 4_backend_engine/route_benchmark.py
"""
import os
import sys
import time
import types

os.environ.setdefault("FLASK_USE_RELOADER", "0")

import networkx as nx

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "3_pipeline"))


def _mock_flask():
    flask = types.ModuleType("flask")

    class _Flask:
        def __init__(self, *args, **kwargs):
            pass

        def route(self, *args, **kwargs):
            def decorator(fn):
                return fn
            return decorator

    flask.Flask = _Flask
    flask.request = types.SimpleNamespace(args={})
    flask.jsonify = lambda x: x
    sys.modules["flask"] = flask

    cors = types.ModuleType("flask_cors")
    cors.CORS = lambda *args, **kwargs: None
    sys.modules["flask_cors"] = cors


_mock_flask()

import tfl_live
import park_opening_hours
from app import G, make_weight_fastest, make_weight_optimized
from routing_heuristic import compute_optimized_cost_per_metre_lower_bound, make_heuristic

ZERO_HEURISTIC = lambda u, v: 0.0


def _benchmark_weight_fns():
    at_time = park_opening_hours.london_now()
    unique_hours = G.graph.get("park_opening_hours_unique") or []
    hours_map, fallback_open = park_opening_hours.build_request_hours_context(unique_hours, at_time)
    return hours_map, fallback_open


def _build_fixtures():
    """Pick geographically spread pairs from the largest weakly connected component."""
    wccs = list(nx.weakly_connected_components(G))
    main = max(wccs, key=len)
    nodes = [n for n in main if "x" in G.nodes[n] and "y" in G.nodes[n]]
    nodes.sort(key=lambda n: (float(G.nodes[n]["y"]), float(G.nodes[n]["x"])))

    def _coord(n):
        d = G.nodes[n]
        return float(d["y"]), float(d["x"])

    n = len(nodes)
    picks = [
        ("inner short", nodes[n // 4], nodes[n // 3]),
        ("inner medium", nodes[n // 6], nodes[n // 2]),
        ("cross-London", nodes[0], nodes[-1]),
    ]
    fixtures = []
    for label, a, b in picks:
        slat, slon = _coord(a)
        elat, elon = _coord(b)
        fixtures.append((label, slat, slon, elat, elon))
    return fixtures

WEIGHT_COMBOS = [
    ("no rewards", {}),
    ("green only", {"green_weight": 1.0}),
    ("all scenery", {"tfl_cycleway_weight": 1.0, "green_weight": 1.0, "vehicular_free_weight": 3.0}),
    ("safety+live", {"risk_weight": 2.0, "signal_weight": 2.0, "junction_weight": 3.0, "tfl_live_weight": 1.0}),
    ("preset safe", {
        "risk_weight": 1.2, "speed_weight": 2.0, "junction_weight": 2.0,
        "vehicular_free_weight": 2.5, "tfl_cycleway_weight": 0.5, "green_weight": 0.15,
        "hill_weight": 0.3, "barrier_weight": 0.3, "tfl_live_weight": 0.4,
    }),
]


def _base_weights():
    return {
        "risk_weight": 1.0,
        "light_weight": 0.0,
        "surface_weight": 0.0,
        "hill_weight": 0.0,
        "tfl_cycleway_weight": 0.0,
        "vehicular_free_weight": 0.0,
        "speed_weight": 0.0,
        "green_weight": 0.0,
        "barrier_weight": 0.0,
        "calming_weight": 0.0,
        "calming_source": "way",
        "junction_weight": 0.0,
        "signal_weight": 0.0,
        "tfl_live_weight": 0.0,
    }


def path_cost(path, weight_fn):
    total = 0.0
    for u, v in zip(path[:-1], path[1:]):
        d = G[u][v]
        total += weight_fn(u, v, d)
    return total


def run_pair(label, start_lat, start_lon, end_lat, end_lon, w, combo_name):
    start_snap = tfl_live.snap_to_edge(start_lat, start_lon)
    end_snap = tfl_live.snap_to_edge(end_lat, end_lon)
    if not start_snap or not end_snap:
        return False, f"{label}/{combo_name}: snap failed"
    start_node = start_snap.anchor_node
    end_node = end_snap.anchor_node

    scale = compute_optimized_cost_per_metre_lower_bound(w)
    hours_map, fallback_open = _benchmark_weight_fns()
    weight_fastest = make_weight_fastest(hours_map, fallback_open)
    h_fast = make_heuristic(end_node, G, cost_per_m=1.0)
    h_opt = make_heuristic(end_node, G, cost_per_m=scale)
    weight_optimized = make_weight_optimized(w, hours_map, fallback_open)

    t0 = time.perf_counter()
    path_fast_h0 = nx.astar_path(G, start_node, end_node, heuristic=ZERO_HEURISTIC, weight=weight_fastest)
    path_opt_h0 = nx.astar_path(G, start_node, end_node, heuristic=ZERO_HEURISTIC, weight=weight_optimized)
    t_h0 = time.perf_counter() - t0

    t0 = time.perf_counter()
    path_fast_h = nx.astar_path(G, start_node, end_node, heuristic=h_fast, weight=weight_fastest)
    path_opt_h = nx.astar_path(G, start_node, end_node, heuristic=h_opt, weight=weight_optimized)
    t_h = time.perf_counter() - t0

    cost_fast_h0 = path_cost(path_fast_h0, weight_fastest)
    cost_fast_h = path_cost(path_fast_h, weight_fastest)
    cost_opt_h0 = path_cost(path_opt_h0, weight_optimized)
    cost_opt_h = path_cost(path_opt_h, weight_optimized)

    tol = 1e-3
    ok = True
    msgs = []
    if abs(cost_fast_h0 - cost_fast_h) > tol:
        ok = False
        msgs.append(f"fastest cost mismatch {cost_fast_h0:.3f} vs {cost_fast_h:.3f}")
    if abs(cost_opt_h0 - cost_opt_h) > tol:
        ok = False
        msgs.append(f"optimized cost mismatch {cost_opt_h0:.3f} vs {cost_opt_h:.3f}")
    if path_fast_h0 != path_fast_h:
        msgs.append("fastest path nodes differ (same cost OK)")
    if path_opt_h0 != path_opt_h:
        msgs.append("optimized path nodes differ (same cost OK)")

    status = "PASS" if ok else "FAIL"
    detail = "; ".join(msgs) if msgs else "costs match"
    line = (
        f"[{status}] {label} / {combo_name}: "
        f"fast={cost_fast_h:.0f}m opt={cost_opt_h:.0f} "
        f"h0={t_h0*1000:.0f}ms h={t_h*1000:.0f}ms — {detail}"
    )
    print(line)
    return ok, line


def main():
    quick = "--quick" in sys.argv

    if G is None:
        print("Graph not loaded.")
        sys.exit(1)

    print(f"Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    fixtures = _build_fixtures()
    if quick:
        fixtures = fixtures[:1]
        combos = WEIGHT_COMBOS[:2]
        print("Quick mode: first fixture, first two weight combos")
    else:
        combos = WEIGHT_COMBOS

    all_ok = True
    for label, slat, slon, elat, elon in fixtures:
        for combo_name, overrides in combos:
            w = _base_weights()
            w.update(overrides)
            ok, _ = run_pair(label, slat, slon, elat, elon, w, combo_name)
            all_ok = all_ok and ok

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
