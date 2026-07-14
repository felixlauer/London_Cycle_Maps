#!/usr/bin/env python3
"""
v4 route-shaped benchmark: array fastest + parallel fast∥opt + shared bake.

Compares full /route-style wall time (snap excluded from A* sum; reported
separately) across:

  prod_seq  — python fastest + python optimized, sequential (today)
  v3_seq    — python fastest + array v3 optimized, sequential
  v4_seq    — array fastest + array v3 optimized, sequential
  v4_par    — array fastest ∥ array v3 optimized (ThreadPoolExecutor)

Also times SharedOverlays rebuild (item 3: bake on live/park refresh).

Note: CPython's GIL often makes v4_par ≈ v4_seq for pure-Python A*. The report
also lists theoretical_par = max(fast, opt) as the upside if search releases
the GIL (free-threaded CPython / native core).

  cd c:\\London_Cycle_Maps
  python 4_backend_engine/benchmark_array_v4.py

Writes:
  0_documentation/testing/array_costs_v4_report.md
  0_documentation/testing/array_costs_v4_report.json
"""
from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "4_backend_engine"
REPORT_DIR = REPO_ROOT / "0_documentation" / "testing"
REPORT_MD = REPORT_DIR / "array_costs_v4_report.md"
REPORT_JSON = REPORT_DIR / "array_costs_v4_report.json"

sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("FLASK_USE_RELOADER", "0")
os.environ.setdefault("SKIP_DISRUPTION_FETCH", "1")

import benchmark_array_costs as bac

COST_RTOL = 1e-6
COST_ATOL = 1e-3


def _astar(pathfinding_mod, G, start, end, h, weight_fn):
    t0 = time.perf_counter()
    path, stats = pathfinding_mod.astar_unidirectional(G, start, end, h, weight_fn)
    return {
        "elapsed_s": time.perf_counter() - t0,
        "path": path,
        "expansions": stats["expansions"],
        "edge_relaxations": stats["edge_relaxations"],
        "length_m": bac.path_length_m(G, path),
        "path_cost": bac.path_total_cost(G, path, weight_fn),
    }


def run_pair_sequential(fast_fn, opt_fn, pathfinding_mod, G, start, end, h_fast, h_opt):
    t0 = time.perf_counter()
    fast = _astar(pathfinding_mod, G, start, end, h_fast, fast_fn)
    opt = _astar(pathfinding_mod, G, start, end, h_opt, opt_fn)
    wall = time.perf_counter() - t0
    return {
        "wall_s": wall,
        "fast_s": fast["elapsed_s"],
        "opt_s": opt["elapsed_s"],
        "sum_s": fast["elapsed_s"] + opt["elapsed_s"],
        "max_s": max(fast["elapsed_s"], opt["elapsed_s"]),
        "fast": fast,
        "opt": opt,
        "mode": "sequential",
    }


def run_pair_parallel(fast_fn, opt_fn, pathfinding_mod, G, start, end, h_fast, h_opt):
    """Thread both A*s; GIL may serialize — still measures real wall clock."""

    def _fast():
        return _astar(pathfinding_mod, G, start, end, h_fast, fast_fn)

    def _opt():
        return _astar(pathfinding_mod, G, start, end, h_opt, opt_fn)

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_fast = pool.submit(_fast)
        f_opt = pool.submit(_opt)
        fast = f_fast.result()
        opt = f_opt.result()
    wall = time.perf_counter() - t0
    return {
        "wall_s": wall,
        "fast_s": fast["elapsed_s"],
        "opt_s": opt["elapsed_s"],
        "sum_s": fast["elapsed_s"] + opt["elapsed_s"],
        "max_s": max(fast["elapsed_s"], opt["elapsed_s"]),
        "fast": fast,
        "opt": opt,
        "mode": "parallel_threads",
    }


def main() -> None:
    print("Bootstrapping engine...", flush=True)
    (
        app_mod,
        pathfinding_mod,
        park_opening_hours,
        tfl_live,
        make_heuristic,
        compute_lb,
        get_eps,
    ) = bac.bootstrap()

    eps = get_eps()
    print("Building edge cost tables...", flush=True)
    tables, build_s = bac.build_edge_cost_tables(app_mod)
    print(f"  tables: {tables.n_edges:,} edges in {build_s:.1f}s", flush=True)

    G = app_mod.G
    presets = bac.load_preset_weights()
    routes = bac.parse_test_routes()

    unique_hours = G.graph.get("park_opening_hours_unique") or []
    at_time = park_opening_hours.london_now()
    hours_map, fallback_open = park_opening_hours.build_request_hours_context(
        unique_hours, at_time
    )

    # Item 3: time shared overlay rebuild (simulates post-live-fetch bake).
    print("Timing shared overlay bake (3×)...", flush=True)
    bake_times = []
    shared = None
    for i in range(3):
        shared = bac.build_shared_overlays(tables, hours_map, fallback_open)
        bake_times.append(shared.bake_s)
        print(f"  bake {i+1}: {shared.bake_s*1000:.1f} ms", flush=True)
    bake_mean = sum(bake_times) / len(bake_times)
    print(
        f"  mean bake {bake_mean*1000:.1f} ms | live={shared.has_live} | "
        f"impassable={int(shared.impassable.sum()):,}",
        flush=True,
    )

    all_rows: list[dict] = []

    for preset_name, weights in presets.items():
        print(f"\n=== Preset: {preset_name} ===", flush=True)
        bike = str(weights.get("bike_type", "standard"))

        w_fast_py = app_mod.make_weight_fastest(hours_map, fallback_open)
        w_opt_py = app_mod.make_weight_optimized(weights, hours_map, fallback_open)
        w_fast_arr = bac.make_array_weight_fn_fastest(tables, app_mod, shared, bike)
        w_opt_v3 = bac.make_array_weight_fn_v3(tables, app_mod, weights, shared)

        for route in routes:
            print(f"  {route['name']}...", flush=True)
            start_snap = tfl_live.snap_to_edge(route["start_lat"], route["start_lon"])
            end_snap = tfl_live.snap_to_edge(route["end_lat"], route["end_lon"])
            if not start_snap or not end_snap:
                raise RuntimeError(f"snap failed: {route['name']}")
            start = start_snap.anchor_node
            end = end_snap.anchor_node

            h_fast = make_heuristic(end, G, cost_per_m=1.0)
            scale = compute_lb(weights) * (1.0 + eps)
            h_opt = make_heuristic(end, G, cost_per_m=scale)

            prod = run_pair_sequential(
                w_fast_py, w_opt_py, pathfinding_mod, G, start, end, h_fast, h_opt
            )
            v3 = run_pair_sequential(
                w_fast_py, w_opt_v3, pathfinding_mod, G, start, end, h_fast, h_opt
            )
            v4s = run_pair_sequential(
                w_fast_arr, w_opt_v3, pathfinding_mod, G, start, end, h_fast, h_opt
            )
            v4p = run_pair_parallel(
                w_fast_arr, w_opt_v3, pathfinding_mod, G, start, end, h_fast, h_opt
            )

            # Parity: optimized path/cost vs python; fastest length vs python.
            opt_exact = prod["opt"]["path"] == v4s["opt"]["path"]
            fast_exact = prod["fast"]["path"] == v4s["fast"]["path"]
            cost_py = prod["opt"]["path_cost"]
            cost_v4 = bac.path_total_cost(G, prod["opt"]["path"], w_opt_v3)
            cost_ok = abs(cost_py - cost_v4) <= (COST_ATOL + COST_RTOL * abs(cost_py))

            def _spd(base, other):
                return round(base / other, 2) if other > 0 else 0.0

            row = {
                "preset": preset_name,
                "route": route["name"],
                "prod_wall_s": round(prod["wall_s"], 3),
                "prod_fast_s": round(prod["fast_s"], 3),
                "prod_opt_s": round(prod["opt_s"], 3),
                "v3_wall_s": round(v3["wall_s"], 3),
                "v3_fast_s": round(v3["fast_s"], 3),
                "v3_opt_s": round(v3["opt_s"], 3),
                "v4_seq_wall_s": round(v4s["wall_s"], 3),
                "v4_seq_fast_s": round(v4s["fast_s"], 3),
                "v4_seq_opt_s": round(v4s["opt_s"], 3),
                "v4_par_wall_s": round(v4p["wall_s"], 3),
                "v4_par_fast_s": round(v4p["fast_s"], 3),
                "v4_par_opt_s": round(v4p["opt_s"], 3),
                "v4_theoretical_par_s": round(v4s["max_s"], 3),
                "speedup_v3_vs_prod": _spd(prod["wall_s"], v3["wall_s"]),
                "speedup_v4_seq_vs_prod": _spd(prod["wall_s"], v4s["wall_s"]),
                "speedup_v4_par_vs_prod": _spd(prod["wall_s"], v4p["wall_s"]),
                "speedup_v4_theo_vs_prod": _spd(prod["wall_s"], v4s["max_s"]),
                "par_vs_seq": _spd(v4s["wall_s"], v4p["wall_s"]),
                "fast_array_vs_py": _spd(prod["fast_s"], v4s["fast_s"]),
                "opt_exact": opt_exact,
                "fast_exact": fast_exact,
                "cost_parity_ok": cost_ok,
                "prod_opt_exp": prod["opt"]["expansions"],
                "v4_opt_exp": v4s["opt"]["expansions"],
                "prod_fast_len_m": round(prod["fast"]["length_m"], 1),
                "v4_fast_len_m": round(v4s["fast"]["length_m"], 1),
                "prod_opt_len_m": round(prod["opt"]["length_m"], 1),
                "v4_opt_len_m": round(v4s["opt"]["length_m"], 1),
            }
            all_rows.append(row)
            print(
                f"    prod={prod['wall_s']:.2f}s "
                f"(f={prod['fast_s']:.2f}+o={prod['opt_s']:.2f}) | "
                f"v3={v3['wall_s']:.2f}s | "
                f"v4seq={v4s['wall_s']:.2f}s "
                f"(f={v4s['fast_s']:.2f}+o={v4s['opt_s']:.2f}, "
                f"{row['speedup_v4_seq_vs_prod']}x) | "
                f"v4par={v4p['wall_s']:.2f}s ({row['speedup_v4_par_vs_prod']}x) | "
                f"theo={v4s['max_s']:.2f}s ({row['speedup_v4_theo_vs_prod']}x) | "
                f"opt={'exact' if opt_exact else 'DIFF'} "
                f"fast={'exact' if fast_exact else 'DIFF'} "
                f"cost_ok={cost_ok}",
                flush=True,
            )

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "graph_nodes": G.number_of_nodes(),
        "graph_edges": G.number_of_edges(),
        "table_build_s": round(build_s, 2),
        "shared_bake_s_mean": round(bake_mean, 4),
        "shared_bake_s_runs": [round(t, 4) for t in bake_times],
        "live_overlay_active": shared.has_live,
        "impassable_edges": int(shared.impassable.sum()),
        "heuristic_epsilon": eps,
        "v4": {
            "array_fastest": True,
            "parallel_threads": True,
            "shared_bake_on_refresh": True,
            "gil_note": "v4_par may ≈ v4_seq under CPython GIL; theo=max(fast,opt)",
        },
    }

    def table_for(preset: str) -> str:
        rows = [r for r in all_rows if r["preset"] == preset]
        header = (
            "| Route | Prod (s) | v3 (s) | v4 seq (s) | v4 par (s) | "
            "v4 theo (s) | v4seq× | v4par× | theo× | Opt | Fast | Cost |"
        )
        sep = "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|"
        lines = [header, sep]
        for r in rows:
            lines.append(
                f"| {r['route']} | {r['prod_wall_s']:.2f} | {r['v3_wall_s']:.2f} | "
                f"{r['v4_seq_wall_s']:.2f} | {r['v4_par_wall_s']:.2f} | "
                f"{r['v4_theoretical_par_s']:.2f} | {r['speedup_v4_seq_vs_prod']:.2f}x | "
                f"{r['speedup_v4_par_vs_prod']:.2f}x | {r['speedup_v4_theo_vs_prod']:.2f}x | "
                f"{'exact' if r['opt_exact'] else 'DIFF'} | "
                f"{'exact' if r['fast_exact'] else 'DIFF'} | "
                f"{'ok' if r['cost_parity_ok'] else 'FAIL'} |"
            )
        return "\n".join(lines)

    def breakdown_for(preset: str) -> str:
        rows = [r for r in all_rows if r["preset"] == preset]
        header = (
            "| Route | Prod fast | Prod opt | v4 fast | v4 opt | "
            "fast array× | par/seq |"
        )
        sep = "|---|---:|---:|---:|---:|---:|---:|"
        lines = [header, sep]
        for r in rows:
            lines.append(
                f"| {r['route']} | {r['prod_fast_s']:.2f} | {r['prod_opt_s']:.2f} | "
                f"{r['v4_seq_fast_s']:.2f} | {r['v4_seq_opt_s']:.2f} | "
                f"{r['fast_array_vs_py']:.2f}x | {r['par_vs_seq']:.2f}x |"
            )
        return "\n".join(lines)

    # Summary stats
    def _med(vals):
        s = sorted(vals)
        return s[len(s) // 2]

    md = [
        "# Array costs v4 — fastest + parallel + shared bake",
        "",
        f"Generated: {meta['generated_at']}",
        f"Graph: {meta['graph_nodes']:,} nodes, {meta['graph_edges']:,} edges",
        f"Table build: **{meta['table_build_s']} s** | "
        f"Shared bake mean: **{meta['shared_bake_s_mean']*1000:.1f} ms** "
        f"(live={meta['live_overlay_active']})",
        f"Heuristic epsilon: {meta['heuristic_epsilon']}",
        "",
        "Full /route-shaped A* pair (fastest + optimized). Snap excluded from wall.",
        "",
        "| Mode | Meaning |",
        "|------|---------|",
        "| **prod** | python fastest + python optimized, sequential |",
        "| **v3** | python fastest + array v3 optimized, sequential |",
        "| **v4 seq** | array fastest + array v3 optimized, sequential |",
        "| **v4 par** | same weights, ThreadPoolExecutor (2 workers) |",
        "| **v4 theo** | `max(fast, opt)` — ideal if both run truly concurrent |",
        "",
        "## Shared overlay bake (item 3)",
        "",
        f"Rebuild `SharedOverlays` (parks + live coeffs + impassable): "
        f"**{meta['shared_bake_s_mean']*1000:.1f} ms** mean "
        f"({', '.join(f'{t*1000:.1f}' for t in bake_times)} ms).",
        "Cheap enough to run after every live disruption refresh (~5–10 min).",
        "",
        "## Preset: fast — wall clock",
        "",
        table_for("fast"),
        "",
        "## Preset: safe — wall clock",
        "",
        table_for("safe"),
        "",
        "## Preset: fast — leg breakdown",
        "",
        breakdown_for("fast"),
        "",
        "## Preset: safe — leg breakdown",
        "",
        breakdown_for("safe"),
        "",
        "## How to read",
        "",
        "- **v4seq× / v4par× / theo×** = speedup vs prod wall.",
        "- **par/seq** ≈ 1.0 under CPython GIL for pure-Python A*; theo shows "
        "headroom if search is GIL-free later.",
        "- **Opt / Fast / Cost** = path match and v3 cost on python opt path.",
        "",
        "Re-run: `python 4_backend_engine/benchmark_array_v4.py`",
        "",
        "## Analysis",
        "",
        "_Fill after run: median v4seq×, whether v4par beats v4seq, fast array×, "
        "bake ms, path fidelity._",
        "",
    ]
    REPORT_MD.write_text("\n".join(md), encoding="utf-8")
    REPORT_JSON.write_text(
        json.dumps({"meta": meta, "runs": all_rows}, indent=2),
        encoding="utf-8",
    )

    # Console summary
    for preset in ("fast", "safe"):
        rows = [r for r in all_rows if r["preset"] == preset]
        print(f"\n--- {preset} medians vs prod ---", flush=True)
        print(
            f"  v3:     {_med([r['speedup_v3_vs_prod'] for r in rows]):.2f}x | "
            f"v4seq: {_med([r['speedup_v4_seq_vs_prod'] for r in rows]):.2f}x | "
            f"v4par: {_med([r['speedup_v4_par_vs_prod'] for r in rows]):.2f}x | "
            f"theo:  {_med([r['speedup_v4_theo_vs_prod'] for r in rows]):.2f}x | "
            f"fast×: {_med([r['fast_array_vs_py'] for r in rows]):.2f}x",
            flush=True,
        )

    print(f"\nReport: {REPORT_MD}")
    print(f"JSON:   {REPORT_JSON}")
    print("ARRAY V4 BENCHMARK DONE", flush=True)


if __name__ == "__main__":
    main()
