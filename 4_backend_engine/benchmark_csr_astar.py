#!/usr/bin/env python3
"""
Phase A CSR A* benchmark: parity + wall time vs NetworkX array uni A*.

Compares, for each test_routes entry × fast/safe presets:

  nx_array  — pathfinding.astar_unidirectional + make_array_weight_fn_*
  csr       — pathfinding.astar_csr_unidirectional + make_array_cost_by_eid_*

Acceptance (Phase A):
  - exact path match
  - expansions match
  - path cost within COST_ATOL / COST_RTOL
  - report wall-time speedup (expect ~1.2–1.5× on A* wall)

This is the right gate for CSR — same search problem as production array A*,
not a different cost model. Real-app smoke is optional after this passes
(snap + dual legs + overlays unchanged).

  cd c:\\London_Cycle_Maps
  python 4_backend_engine/benchmark_csr_astar.py

Optional:
  CSR_BENCH_REPEATS=3   # median of N runs per leg (default 1)
  SKIP_DISRUPTION_FETCH=1  (defaulted here)

Writes:
  0_documentation/testing/csr_astar_phase_a_report.md
  0_documentation/testing/csr_astar_phase_a_report.json

Do not run from the agent unless asked — intended for manual runs.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "4_backend_engine"
REPORT_DIR = REPO_ROOT / "0_documentation" / "testing"
REPORT_MD = REPORT_DIR / "csr_astar_phase_a_report.md"
REPORT_JSON = REPORT_DIR / "csr_astar_phase_a_report.json"

sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("FLASK_USE_RELOADER", "0")
os.environ.setdefault("SKIP_DISRUPTION_FETCH", "1")

import benchmark_array_costs as bac
import edge_cost_arrays
import graph_csr

COST_RTOL = 1e-6
COST_ATOL = 1e-3
# Presets to exercise: fastest uses simple cost; safe uses full optimized.
PRESETS = ("fast", "safe")


def _median(xs: list[float]) -> float:
    return float(statistics.median(xs)) if xs else 0.0


def _run_nx(pathfinding_mod, G, start, end, h, weight_fn, repeats: int):
    times = []
    path = stats = None
    for _ in range(repeats):
        t0 = time.perf_counter()
        path, stats = pathfinding_mod.astar_unidirectional(G, start, end, h, weight_fn)
        times.append(time.perf_counter() - t0)
    return {
        "elapsed_s": _median(times),
        "elapsed_all_s": [round(t, 4) for t in times],
        "path": path,
        "expansions": stats["expansions"],
        "edge_relaxations": stats["edge_relaxations"],
        "length_m": bac.path_length_m(G, path),
        "path_cost": bac.path_total_cost(G, path, weight_fn),
    }


def _run_csr(pathfinding_mod, csr, start, end, cost_by_eid, cost_per_m, weight_fn, G, repeats: int):
    times = []
    path = stats = None
    for _ in range(repeats):
        t0 = time.perf_counter()
        path, stats = pathfinding_mod.astar_csr_unidirectional(
            csr, start, end, cost_by_eid, cost_per_m=cost_per_m
        )
        times.append(time.perf_counter() - t0)
    return {
        "elapsed_s": _median(times),
        "elapsed_all_s": [round(t, 4) for t in times],
        "path": path,
        "expansions": stats["expansions"],
        "edge_relaxations": stats["edge_relaxations"],
        "length_m": bac.path_length_m(G, path),
        "path_cost": bac.path_total_cost(G, path, weight_fn),
    }


def _spd(base: float, other: float) -> float:
    return round(base / other, 3) if other > 0 else 0.0


def _write_reports(payload: dict) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    rows = payload["rows"]
    ok_n = sum(1 for r in rows if r["ok"])
    lines = [
        "# CSR A* Phase A report",
        "",
        f"Generated: {payload['generated_at']}",
        f"Repeats (median): {payload['repeats']}",
        f"CSR build: {payload['csr_build_s']:.2f}s "
        f"({payload['csr_n_nodes']:,} nodes, {payload['csr_n_edges']:,} arcs)",
        f"Edge tables: {payload['tables_n_edges']:,} edges",
        f"ε optimized: {payload['eps']} | ε fastest: {payload['eps_fast']}",
        f"Parity OK: {ok_n}/{len(rows)}",
        "",
        "## Summary speedups (nx_array / csr, median wall)",
        "",
        f"- Fastest legs mean speedup: {payload['summary']['mean_speedup_fast']:.3f}×",
        f"- Optimized (safe) legs mean speedup: {payload['summary']['mean_speedup_opt']:.3f}×",
        f"- All legs mean speedup: {payload['summary']['mean_speedup_all']:.3f}×",
        "",
        "## Per-route",
        "",
        "| Preset | Route | Leg | NX s | CSR s | Speedup | Exp NX | Exp CSR | Path | Cost | OK |",
        "|--------|-------|-----|------|-------|---------|--------|---------|------|------|----|",
    ]
    for r in rows:
        lines.append(
            f"| {r['preset']} | {r['route']} | {r['leg']} | "
            f"{r['nx_s']:.3f} | {r['csr_s']:.3f} | {r['speedup']:.3f}× | "
            f"{r['nx_exp']} | {r['csr_exp']} | "
            f"{'Y' if r['path_exact'] else 'N'} | "
            f"{'Y' if r['cost_ok'] else 'N'} | "
            f"{'Y' if r['ok'] else 'N'} |"
        )
    lines.append("")
    lines.append(f"JSON: `{REPORT_JSON.relative_to(REPO_ROOT).as_posix()}`")
    lines.append("")
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {REPORT_MD}", flush=True)
    print(f"Wrote {REPORT_JSON}", flush=True)


def main() -> None:
    repeats = max(1, int(os.environ.get("CSR_BENCH_REPEATS", "1")))
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

    from routing_heuristic import get_route_fastest_heuristic_epsilon

    eps = get_eps()
    eps_fast = get_route_fastest_heuristic_epsilon()
    G = app_mod.G

    # Prefer production tables already installed at bootstrap; rebuild if missing.
    tables = edge_cost_arrays.get_tables()
    shared = edge_cost_arrays.get_shared_overlays()
    if tables is None or shared is None:
        print("Building edge cost tables (bench fallback)...", flush=True)
        tables, build_s = edge_cost_arrays.build_edge_cost_tables(
            G,
            junction_suppressed=app_mod.JUNCTION_CLUSTER_SUPPRESSED,
            bad_surfaces=app_mod.BAD_SURFACES,
            up_thresh=app_mod.UP_THRESH,
            down_thresh=app_mod.DOWN_THRESH,
            is_lit_fn=app_mod.is_lit,
            speed_stress_fn=app_mod._speed_stress_multiplier,
            is_tfl_fn=app_mod._is_tfl_network,
            has_attraction_fn=app_mod._has_attraction_edge,
            highway_mult_fn=app_mod._highway_type_multiplier,
            barrier_penalty_fn=app_mod._edge_barrier_penalty,
            give_way_fn=app_mod._edge_give_way_penalty,
            stop_sign_fn=app_mod._edge_stop_sign_penalty,
            calming_fn=app_mod._traffic_calming_additive,
            signal_fn=app_mod._node_signal_penalty,
            intersection_fn=app_mod._node_intersection_penalty,
            mini_rb_fn=app_mod._node_mini_roundabout_penalty,
            is_yes_fn=app_mod._is_yes_attr,
            parse_geometry=False,
        )
        edge_cost_arrays.install_tables(tables, G)
        shared = edge_cost_arrays.refresh_shared_overlays_from_graph()
        print(f"  tables: {tables.n_edges:,} in {build_s:.1f}s", flush=True)
    else:
        print(
            f"Using production tables: {tables.n_edges:,} edges | "
            f"impassable={int(shared.impassable.sum()):,}",
            flush=True,
        )

    csr = graph_csr.get_csr()
    if csr is None:
        print("Building CSR...", flush=True)
        csr = graph_csr.build_csr(G)
        graph_csr.set_csr(csr)
    print(
        f"CSR: {csr.n_nodes:,} nodes, {csr.n_edges:,} arcs in {csr.build_s:.1f}s",
        flush=True,
    )
    if csr.n_edges != tables.n_edges:
        print(
            f"WARNING: CSR arcs ({csr.n_edges}) != table edges ({tables.n_edges})",
            flush=True,
        )

    presets = bac.load_preset_weights()
    routes = bac.parse_test_routes()
    hard = float(app_mod.BARRIER_HARD_COST)
    m_min = float(app_mod.M_MIN)
    r_min = float(app_mod.R_MIN)

    rows: list[dict] = []
    speedups_fast: list[float] = []
    speedups_opt: list[float] = []
    speedups_all: list[float] = []

    for preset_name in PRESETS:
        if preset_name not in presets:
            print(f"Skip missing preset: {preset_name}", flush=True)
            continue
        weights = presets[preset_name]
        bike = str(weights.get("bike_type", "standard"))
        print(f"\n=== Preset: {preset_name} ===", flush=True)

        w_fast = edge_cost_arrays.make_array_weight_fn_fastest(
            tables, hard, shared, bike_type=bike
        )
        w_opt = edge_cost_arrays.make_array_weight_fn_optimized(
            tables, weights, shared, hard_cost=hard, m_min=m_min, r_min=r_min
        )
        c_fast = edge_cost_arrays.make_array_cost_by_eid_fastest(
            tables, hard, shared, bike_type=bike
        )
        c_opt = edge_cost_arrays.make_array_cost_by_eid_optimized(
            tables, weights, shared, hard_cost=hard, m_min=m_min, r_min=r_min
        )

        for route in routes:
            print(f"  {route['name']}...", flush=True)
            start_snap = tfl_live.snap_to_edge(route["start_lat"], route["start_lon"])
            end_snap = tfl_live.snap_to_edge(route["end_lat"], route["end_lon"])
            if not start_snap or not end_snap:
                raise RuntimeError(f"snap failed: {route['name']}")
            start = start_snap.anchor_node
            end = end_snap.anchor_node

            scale_fast = 1.0 * (1.0 + eps_fast)
            scale_opt = compute_lb(weights) * (1.0 + eps)
            h_fast = make_heuristic(end, G, cost_per_m=scale_fast)
            h_opt = make_heuristic(end, G, cost_per_m=scale_opt)

            # Fastest leg
            nx_f = _run_nx(pathfinding_mod, G, start, end, h_fast, w_fast, repeats)
            csr_f = _run_csr(
                pathfinding_mod, csr, start, end, c_fast, scale_fast, w_fast, G, repeats
            )
            # Optimized leg
            nx_o = _run_nx(pathfinding_mod, G, start, end, h_opt, w_opt, repeats)
            csr_o = _run_csr(
                pathfinding_mod, csr, start, end, c_opt, scale_opt, w_opt, G, repeats
            )

            for leg, nx_r, csr_r in (
                ("fastest", nx_f, csr_f),
                ("optimized", nx_o, csr_o),
            ):
                path_exact = nx_r["path"] == csr_r["path"]
                exp_match = nx_r["expansions"] == csr_r["expansions"]
                cost_ok = abs(nx_r["path_cost"] - csr_r["path_cost"]) <= (
                    COST_ATOL + COST_RTOL * abs(nx_r["path_cost"])
                )
                # Expansions must match for exact same heuristic+cost; flag if not.
                ok = path_exact and cost_ok and exp_match
                spd = _spd(nx_r["elapsed_s"], csr_r["elapsed_s"])
                speedups_all.append(spd)
                if leg == "fastest":
                    speedups_fast.append(spd)
                else:
                    speedups_opt.append(spd)
                row = {
                    "preset": preset_name,
                    "route": route["name"],
                    "leg": leg,
                    "nx_s": round(nx_r["elapsed_s"], 4),
                    "csr_s": round(csr_r["elapsed_s"], 4),
                    "speedup": spd,
                    "nx_exp": nx_r["expansions"],
                    "csr_exp": csr_r["expansions"],
                    "nx_relax": nx_r["edge_relaxations"],
                    "csr_relax": csr_r["edge_relaxations"],
                    "path_exact": path_exact,
                    "exp_match": exp_match,
                    "cost_ok": cost_ok,
                    "nx_cost": nx_r["path_cost"],
                    "csr_cost": csr_r["path_cost"],
                    "nx_len_m": round(nx_r["length_m"], 1),
                    "csr_len_m": round(csr_r["length_m"], 1),
                    "ok": ok,
                }
                rows.append(row)
                flag = "OK" if ok else "FAIL"
                print(
                    f"    {leg}: nx={nx_r['elapsed_s']:.3f}s csr={csr_r['elapsed_s']:.3f}s "
                    f"({spd:.2f}×) exp={nx_r['expansions']}/{csr_r['expansions']} [{flag}]",
                    flush=True,
                )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repeats": repeats,
        "eps": eps,
        "eps_fast": eps_fast,
        "csr_build_s": csr.build_s,
        "csr_n_nodes": csr.n_nodes,
        "csr_n_edges": csr.n_edges,
        "tables_n_edges": tables.n_edges,
        "summary": {
            "mean_speedup_fast": round(
                sum(speedups_fast) / len(speedups_fast), 3
            )
            if speedups_fast
            else 0.0,
            "mean_speedup_opt": round(sum(speedups_opt) / len(speedups_opt), 3)
            if speedups_opt
            else 0.0,
            "mean_speedup_all": round(sum(speedups_all) / len(speedups_all), 3)
            if speedups_all
            else 0.0,
            "parity_ok": all(r["ok"] for r in rows),
            "parity_ok_n": sum(1 for r in rows if r["ok"]),
            "parity_total": len(rows),
        },
        "rows": rows,
    }
    _write_reports(payload)
    if not payload["summary"]["parity_ok"]:
        print("\n*** PARITY FAILURES — see report ***", flush=True)
        sys.exit(1)
    print("\nAll parity checks passed.", flush=True)


if __name__ == "__main__":
    main()
