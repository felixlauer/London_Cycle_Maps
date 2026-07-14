#!/usr/bin/env python3
"""
One-shot /route-style substep profile for a medium test route.

Breaks wall time into: snap, park hours, weight build, A* (weight vs search
overhead), geometry, stats, overlays. Compares python vs array v3 weight fns.

  cd c:\\London_Cycle_Maps
  python 4_backend_engine/profile_route_substeps.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "4_backend_engine"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(REPO_ROOT / "3_pipeline"))

os.environ.setdefault("FLASK_USE_RELOADER", "0")
os.environ.setdefault("SKIP_DISRUPTION_FETCH", "1")

# Medium hop: Imperial → Greenwich (~15 km, ~9s python / ~3.5s v3 in array bench).
ROUTE = {
    "name": "route 2: Imperial to Greenwich",
    "start_lat": 51.497761018020995,
    "start_lon": -0.1740317840508432,
    "end_lat": 51.481448473034185,
    "end_lon": -0.010092364105364706,
}


def main() -> None:
    import benchmark_array_costs as bac

    print("Bootstrapping...", flush=True)
    (
        app_mod,
        pathfinding_mod,
        park_opening_hours,
        tfl_live,
        make_heuristic,
        compute_lb,
        get_eps,
    ) = bac.bootstrap()

    presets = bac.load_preset_weights()
    w = presets["safe"]
    eps = get_eps()
    G = app_mod.G

    print("Building edge tables + shared overlays...", flush=True)
    tables, build_s = bac.build_edge_cost_tables(app_mod)
    unique_hours = G.graph.get("park_opening_hours_unique") or []
    at_time = park_opening_hours.london_now()
    hours_map, fallback_open = park_opening_hours.build_request_hours_context(
        unique_hours, at_time
    )
    shared = bac.build_shared_overlays(tables, hours_map, fallback_open)
    print(
        f"  tables {build_s:.1f}s | shared bake {shared.bake_s:.3f}s | eps={eps}",
        flush=True,
    )

    # --- request-shaped timing ---
    t0 = time.perf_counter()
    start_snap = tfl_live.snap_to_edge(ROUTE["start_lat"], ROUTE["start_lon"])
    end_snap = tfl_live.snap_to_edge(ROUTE["end_lat"], ROUTE["end_lon"])
    t_snap = time.perf_counter() - t0
    start_node = start_snap.anchor_node
    end_node = end_snap.anchor_node

    t0 = time.perf_counter()
    hours_map2, fallback2 = park_opening_hours.build_request_hours_context(
        unique_hours, park_opening_hours.london_now()
    )
    t_park = time.perf_counter() - t0

    t0 = time.perf_counter()
    weight_py = app_mod.make_weight_optimized(w, hours_map2, fallback2)
    t_w_py = time.perf_counter() - t0

    t0 = time.perf_counter()
    weight_v3 = bac.make_array_weight_fn_v3(tables, app_mod, w, shared)
    t_w_v3 = time.perf_counter() - t0

    scale = compute_lb(w) * (1.0 + eps)
    h = make_heuristic(end_node, G, cost_per_m=scale)

    def _run_instrumented(weight_fn, label: str) -> dict:
        """A* with weight_fn wall-time accumulator."""
        weight_s = [0.0]
        calls = [0]
        relax = [0]

        def wrapped(u, v, d):
            calls[0] += 1
            tw = time.perf_counter()
            c = weight_fn(u, v, d)
            weight_s[0] += time.perf_counter() - tw
            return c

        t0 = time.perf_counter()
        path, stats = pathfinding_mod.astar_unidirectional(
            G, start_node, end_node, h, wrapped
        )
        total = time.perf_counter() - t0
        relax[0] = stats["edge_relaxations"]
        overhead = total - weight_s[0]
        return {
            "label": label,
            "astar_s": total,
            "weight_s": weight_s[0],
            "overhead_s": overhead,
            "weight_pct": 100.0 * weight_s[0] / total if total else 0.0,
            "overhead_pct": 100.0 * overhead / total if total else 0.0,
            "expansions": stats["expansions"],
            "relaxations": stats["edge_relaxations"],
            "weight_calls": calls[0],
            "us_per_call": 1e6 * weight_s[0] / calls[0] if calls[0] else 0.0,
            "path_nodes": path,
            "length_m": bac.path_length_m(G, path),
        }

    print(f"\nProfiling {ROUTE['name']} (safe, eps={eps})...", flush=True)
    py = _run_instrumented(weight_py, "python")
    v3 = _run_instrumented(weight_v3, "array_v3")

    # Post-A* work (production /route does this once on optimized path).
    path = py["path_nodes"]
    t0 = time.perf_counter()
    coords = app_mod.reconstruct_path_geometry(path)
    coords = app_mod.apply_endpoint_stubs(coords, start_snap, end_snap)
    t_geom = time.perf_counter() - t0

    t0 = time.perf_counter()
    _ = app_mod.calculate_path_stats(path, calming_source="both")
    t_stats = time.perf_counter() - t0

    t0 = time.perf_counter()
    _ = app_mod.get_lit_sections(path)
    _ = app_mod.get_steep_sections(path)
    _ = app_mod.get_tfl_cycleway_sections(path)
    _ = app_mod.get_green_sections(path)
    from cost_masks import vf_allowed_masks

    vf_mask, _ = vf_allowed_masks(
        shared_path=bool(w.get("vf_shared_path", True)),
        bus_lane=bool(w.get("vf_bus_lane", True)),
        painted_lane=bool(w.get("vf_painted_lane", False)),
    )
    _ = app_mod.get_vehicular_free_sections(path, vf_mask)
    _ = app_mod.get_disruption_sections(path)
    _ = app_mod.get_node_highlights(path, w, overlay_mode=True)
    t_overlays = time.perf_counter() - t0

    # Fastest leg estimate (length-only weight) for full /route picture.
    t0 = time.perf_counter()
    w_fast = app_mod.make_weight_fastest(hours_map2, fallback2)
    h_fast = make_heuristic(end_node, G, cost_per_m=1.0)
    path_f, stats_f = pathfinding_mod.astar_unidirectional(
        G, start_node, end_node, h_fast, w_fast
    )
    t_fast = time.perf_counter() - t0

    print("\n=== Pre-search (once per /route) ===")
    print(f"  snap (2×):           {t_snap*1000:7.1f} ms")
    print(f"  park hours context:  {t_park*1000:7.1f} ms")
    print(f"  make_weight python:  {t_w_py*1000:7.1f} ms")
    print(f"  make_weight v3:      {t_w_v3*1000:7.1f} ms")

    print("\n=== Optimized A* (safe) ===")
    for r in (py, v3):
        print(
            f"  {r['label']:10s}  total={r['astar_s']:.3f}s  "
            f"weight={r['weight_s']:.3f}s ({r['weight_pct']:.0f}%)  "
            f"overhead={r['overhead_s']:.3f}s ({r['overhead_pct']:.0f}%)  "
            f"exp={r['expansions']:,}  relax={r['relaxations']:,}  "
            f"{r['us_per_call']:.1f} µs/weight"
        )

    print("\n=== Fastest A* (python length weight) ===")
    print(
        f"  total={t_fast:.3f}s  exp={stats_f['expansions']:,}  "
        f"len={bac.path_length_m(G, path_f):.0f}m"
    )

    print("\n=== Post-search (optimized path only) ===")
    print(f"  geometry+stubs:      {t_geom*1000:7.1f} ms  ({len(coords)} pts)")
    print(f"  path stats:          {t_stats*1000:7.1f} ms")
    print(f"  overlay chunks:      {t_overlays*1000:7.1f} ms")

    post = t_geom + t_stats + t_overlays
    full_py = t_snap + t_park + t_w_py + t_fast + py["astar_s"] + post
    full_v3 = t_snap + t_park + t_w_v3 + t_fast + v3["astar_s"] + post
    print("\n=== Full /route-shaped total (est.) ===")
    print(f"  with python opt:     {full_py:.3f}s")
    print(f"  with v3 opt:         {full_v3:.3f}s")
    print(
        f"  (fastest still python; opt weight share of full: "
        f"py {100*py['astar_s']/full_py:.0f}% / v3 {100*v3['astar_s']/full_v3:.0f}%)"
    )
    print(
        f"\n  A* overhead alone (v3): {v3['overhead_s']:.3f}s — "
        f"heap+NetworkX+heuristic; not fixed by more array thinning."
    )
    print("PROFILE DONE", flush=True)


if __name__ == "__main__":
    main()
