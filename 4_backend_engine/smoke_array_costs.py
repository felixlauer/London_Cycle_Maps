#!/usr/bin/env python3
"""
Smoke: array costs vs python weights on one medium route (safe preset).

  cd c:\\London_Cycle_Maps
  python 4_backend_engine/smoke_array_costs.py
"""
from __future__ import annotations

import os
import sys
import time
import types
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(REPO / "3_pipeline"))

os.environ.setdefault("FLASK_USE_RELOADER", "0")
os.environ.setdefault("SKIP_DISRUPTION_FETCH", "1")
os.environ.setdefault("ARRAY_COSTS", "1")


def _mock_flask():
    flask = types.ModuleType("flask")

    class _Flask:
        def __init__(self, *a, **k):
            pass

        def route(self, *a, **k):
            def d(fn):
                return fn

            return d

        def before_request(self, fn):
            return fn

    flask.Flask = _Flask
    flask.request = types.SimpleNamespace(args={})
    flask.g = types.SimpleNamespace()
    flask.jsonify = lambda x: x
    sys.modules["flask"] = flask
    cors = types.ModuleType("flask_cors")
    cors.CORS = lambda *a, **k: None
    sys.modules["flask_cors"] = cors


def main() -> None:
    _mock_flask()
    os.chdir(BACKEND)
    print("Loading app (array costs on)...", flush=True)
    import app as app_mod
    import edge_cost_arrays
    import pathfinding
    from routing_heuristic import (
        compute_optimized_cost_per_metre_lower_bound,
        get_route_heuristic_epsilon,
        make_heuristic,
    )
    import park_opening_hours
    import tfl_live
    import json

    assert edge_cost_arrays.get_tables() is not None, "EDGE_TABLES missing"
    assert edge_cost_arrays.get_shared_overlays() is not None, "SHARED_OVERLAYS missing"

    profiles = json.loads((BACKEND / "user_profiles.json").read_text(encoding="utf-8"))
    # Prefer system safe preset (schema v2 keys)
    key = "preset_safe" if "preset_safe" in profiles["profiles"] else "safe"
    pdata = profiles["profiles"][key]
    w = dict(pdata["weights"])
    w["calming_source"] = "both"
    w["bike_type"] = pdata.get("bike_type", "standard")
    vf = pdata.get("toggles", {}).get("vf_infrastructure", {})
    w["vf_shared_path"] = bool(vf.get("shared_path", True))
    w["vf_bus_lane"] = bool(vf.get("bus_lane", True))
    w["vf_painted_lane"] = bool(vf.get("painted_lane", False))

    # Imperial → Greenwich
    start = tfl_live.snap_to_edge(51.497761018020995, -0.1740317840508432)
    end = tfl_live.snap_to_edge(51.481448473034185, -0.010092364105364706)
    assert start and end
    s, e = start.anchor_node, end.anchor_node
    G = app_mod.G
    eps = get_route_heuristic_epsilon()
    scale = compute_optimized_cost_per_metre_lower_bound(w) * (1.0 + eps)
    h = make_heuristic(e, G, cost_per_m=scale)
    h_fast = make_heuristic(e, G, cost_per_m=1.0)

    unique = G.graph.get("park_opening_hours_unique") or []
    hours_map, fallback = park_opening_hours.build_request_hours_context(
        unique, park_opening_hours.london_now()
    )
    tables = edge_cost_arrays.get_tables()
    shared = edge_cost_arrays.get_shared_overlays()

    w_fast_py = app_mod.make_weight_fastest(hours_map, fallback)
    w_opt_py = app_mod.make_weight_optimized(w, hours_map, fallback)
    w_fast_arr = edge_cost_arrays.make_array_weight_fn_fastest(
        tables, app_mod.BARRIER_HARD_COST, shared, bike_type=w["bike_type"]
    )
    w_opt_arr = edge_cost_arrays.make_array_weight_fn_optimized(
        tables,
        w,
        shared,
        hard_cost=app_mod.BARRIER_HARD_COST,
        m_min=app_mod.M_MIN,
        r_min=app_mod.R_MIN,
    )

    def run(label, hfn, wfn):
        t0 = time.perf_counter()
        path, stats = pathfinding.astar_unidirectional(G, s, e, hfn, wfn)
        dt = time.perf_counter() - t0
        length = sum(
            float((G.get_edge_data(path[i], path[i + 1]) or {}).get("length", 0))
            for i in range(len(path) - 1)
        )
        return path, stats, dt, length

    print("Running fastest python vs array...", flush=True)
    pf_py, sf_py, tf_py, lf_py = run("fast_py", h_fast, w_fast_py)
    pf_ar, sf_ar, tf_ar, lf_ar = run("fast_arr", h_fast, w_fast_arr)
    print(
        f"  fastest  py={tf_py:.2f}s len={lf_py:.0f}m exp={sf_py['expansions']} | "
        f"arr={tf_ar:.2f}s len={lf_ar:.0f}m exp={sf_ar['expansions']} | "
        f"path_match={pf_py == pf_ar}",
        flush=True,
    )

    print("Running optimized python vs array...", flush=True)
    po_py, so_py, to_py, lo_py = run("opt_py", h, w_opt_py)
    po_ar, so_ar, to_ar, lo_ar = run("opt_arr", h, w_opt_arr)
    print(
        f"  optimized py={to_py:.2f}s len={lo_py:.0f}m exp={so_py['expansions']} | "
        f"arr={to_ar:.2f}s len={lo_ar:.0f}m exp={so_ar['expansions']} | "
        f"path_match={po_py == po_ar}",
        flush=True,
    )

    # Geometry uses _coords
    t0 = time.perf_counter()
    coords = app_mod.reconstruct_path_geometry(po_ar)
    print(f"  geometry: {len(coords)} pts in {(time.perf_counter()-t0)*1000:.1f} ms")

    ok = pf_py == pf_ar and po_py == po_ar
    print("SMOKE PASS" if ok else "SMOKE FAIL (path mismatch)", flush=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
