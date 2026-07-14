#!/usr/bin/env python3
"""
Phase C Numba CSR A* benchmark: parity + wall vs pure-Python CSR (Phase B).

Compares, for each test_routes × fast/safe × fastest/optimized:

  csr_py  — pathfinding.astar_csr_unidirectional (phase_b heuristic)
  numba   — pathfinding_numba.astar_numba_unidirectional

Acceptance:
  - exact path match (or document float-tie diffs)
  - expansions match (preferred)
  - path cost within COST_ATOL / COST_RTOL
  - report wall speedup (expect multi-× on long hops)

  cd c:\\London_Cycle_Maps
  pip install numba   # if needed
  python 4_backend_engine/benchmark_csr_numba.py

Optional: CSR_BENCH_REPEATS=3

Writes:
  0_documentation/testing/csr_astar_phase_c_report.md
  0_documentation/testing/csr_astar_phase_c_report.json

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
REPORT_MD = REPORT_DIR / "csr_astar_phase_c_report.md"
REPORT_JSON = REPORT_DIR / "csr_astar_phase_c_report.json"

sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("FLASK_USE_RELOADER", "0")
os.environ.setdefault("SKIP_DISRUPTION_FETCH", "1")

import benchmark_array_costs as bac
import edge_cost_arrays
import graph_csr
import pathfinding_numba

COST_RTOL = 1e-6
COST_ATOL = 1e-3
PRESETS = ("fast", "safe")


def _median(xs: list[float]) -> float:
    return float(statistics.median(xs)) if xs else 0.0


def _spd(base: float, other: float) -> float:
    return round(base / other, 3) if other > 0 else 0.0


def _run_py(pathfinding_mod, csr, start, end, cost_by_eid, cost_per_m, weight_fn, G, repeats):
    times = []
    path = stats = None
    for _ in range(repeats):
        t0 = time.perf_counter()
        path, stats = pathfinding_mod.astar_csr_unidirectional(
            csr, start, end, cost_by_eid, cost_per_m=cost_per_m, heuristic_mode="phase_b"
        )
        times.append(time.perf_counter() - t0)
    return {
        "elapsed_s": _median(times),
        "path": path,
        "expansions": stats["expansions"],
        "edge_relaxations": stats["edge_relaxations"],
        "length_m": bac.path_length_m(G, path),
        "path_cost": bac.path_total_cost(G, path, weight_fn),
    }


def _run_numba(
    csr,
    start,
    end,
    tables,
    shared,
    mode,
    cost_per_m,
    hard_cost,
    bike_type,
    opt_scalars,
    weight_fn,
    G,
    repeats,
):
    times = []
    path = stats = None
    for _ in range(repeats):
        t0 = time.perf_counter()
        path, stats = pathfinding_numba.astar_numba_unidirectional(
            csr,
            start,
            end,
            tables,
            shared,
            mode=mode,
            cost_per_m=cost_per_m,
            hard_cost=hard_cost,
            bike_type=bike_type,
            opt_scalars=opt_scalars,
        )
        times.append(time.perf_counter() - t0)
    return {
        "elapsed_s": _median(times),
        "path": path,
        "expansions": stats["expansions"],
        "edge_relaxations": stats["edge_relaxations"],
        "length_m": bac.path_length_m(G, path),
        "path_cost": bac.path_total_cost(G, path, weight_fn),
    }


def _write_reports(payload: dict) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    rows = payload["rows"]
    ok_n = sum(1 for r in rows if r["ok"])
    lines = [
        "# CSR A* Phase C (Numba) report",
        "",
        f"Generated: {payload['generated_at']}",
        f"Repeats (median): {payload['repeats']}",
        f"Numba available: {payload['numba_available']}",
        f"Warmup: {payload['warmup_s']:.2f}s",
        f"CSR build: {payload['csr_build_s']:.2f}s "
        f"({payload['csr_n_nodes']:,} nodes, {payload['csr_n_edges']:,} arcs)",
        f"ε optimized: {payload['eps']} | ε fastest: {payload['eps_fast']}",
        f"Parity OK: {ok_n}/{len(rows)}",
        "",
        "## Summary speedups (csr_py / numba)",
        "",
        f"- Fastest legs mean: **{payload['summary']['mean_speedup_fast']:.3f}×**",
        f"- Optimized legs mean: **{payload['summary']['mean_speedup_opt']:.3f}×**",
        f"- All legs mean: **{payload['summary']['mean_speedup_all']:.3f}×**",
        "",
        "## Per-route",
        "",
        "| Preset | Route | Leg | CSR-py s | Numba s | Speedup | Exp py | Exp nb | Path | Cost | OK |",
        "|--------|-------|-----|----------|---------|---------|--------|--------|------|------|----|",
    ]
    for r in rows:
        lines.append(
            f"| {r['preset']} | {r['route']} | {r['leg']} | "
            f"{r['py_s']:.3f} | {r['numba_s']:.3f} | {r['speedup']:.3f}× | "
            f"{r['py_exp']} | {r['numba_exp']} | "
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
    if not pathfinding_numba.is_available():
        print("ERROR: numba is not installed. pip install numba", flush=True)
        sys.exit(2)

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
    tables = edge_cost_arrays.get_tables()
    shared = edge_cost_arrays.get_shared_overlays()
    if tables is None or shared is None:
        raise RuntimeError("Production edge tables/overlays missing after bootstrap")

    csr = graph_csr.get_csr()
    if csr is None:
        csr = graph_csr.build_csr(G)
        graph_csr.set_csr(csr)

    print("Warming Numba kernels...", flush=True)
    warm_s = pathfinding_numba.warmup(
        csr, tables, shared, hard_cost=float(app_mod.BARRIER_HARD_COST)
    )
    print(f"  warmup {warm_s:.2f}s", flush=True)

    presets = bac.load_preset_weights()
    routes = bac.parse_test_routes()
    hard = float(app_mod.BARRIER_HARD_COST)
    m_min = float(app_mod.M_MIN)
    r_min = float(app_mod.R_MIN)

    rows: list[dict] = []
    spd_fast: list[float] = []
    spd_opt: list[float] = []
    spd_all: list[float] = []

    for preset_name in PRESETS:
        if preset_name not in presets:
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
        opt_scalars = pathfinding_numba.pack_optimized_scalars(
            weights, shared, hard, m_min, r_min
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

            for leg, mode, scale, cost_eid, weight_fn, sc in (
                ("fastest", "fastest", scale_fast, c_fast, w_fast, None),
                ("optimized", "optimized", scale_opt, c_opt, w_opt, opt_scalars),
            ):
                py = _run_py(
                    pathfinding_mod, csr, start, end, cost_eid, scale, weight_fn, G, repeats
                )
                nb = _run_numba(
                    csr,
                    start,
                    end,
                    tables,
                    shared,
                    mode,
                    scale,
                    hard,
                    bike,
                    sc,
                    weight_fn,
                    G,
                    repeats,
                )
                path_exact = py["path"] == nb["path"]
                exp_match = py["expansions"] == nb["expansions"]
                cost_ok = abs(py["path_cost"] - nb["path_cost"]) <= (
                    COST_ATOL + COST_RTOL * abs(py["path_cost"])
                )
                # Prefer strict parity; still OK if path+cost match with exp noise.
                ok = path_exact and cost_ok and exp_match
                spd = _spd(py["elapsed_s"], nb["elapsed_s"])
                spd_all.append(spd)
                if leg == "fastest":
                    spd_fast.append(spd)
                else:
                    spd_opt.append(spd)
                rows.append(
                    {
                        "preset": preset_name,
                        "route": route["name"],
                        "leg": leg,
                        "py_s": round(py["elapsed_s"], 4),
                        "numba_s": round(nb["elapsed_s"], 4),
                        "speedup": spd,
                        "py_exp": py["expansions"],
                        "numba_exp": nb["expansions"],
                        "path_exact": path_exact,
                        "exp_match": exp_match,
                        "cost_ok": cost_ok,
                        "py_cost": py["path_cost"],
                        "numba_cost": nb["path_cost"],
                        "ok": ok,
                    }
                )
                print(
                    f"    {leg}: py={py['elapsed_s']:.3f}s numba={nb['elapsed_s']:.3f}s "
                    f"({spd:.2f}×) exp={py['expansions']}/{nb['expansions']} "
                    f"[{'OK' if ok else 'FAIL'}]",
                    flush=True,
                )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repeats": repeats,
        "numba_available": True,
        "warmup_s": warm_s,
        "eps": eps,
        "eps_fast": eps_fast,
        "csr_build_s": csr.build_s,
        "csr_n_nodes": csr.n_nodes,
        "csr_n_edges": csr.n_edges,
        "summary": {
            "mean_speedup_fast": round(sum(spd_fast) / len(spd_fast), 3)
            if spd_fast
            else 0.0,
            "mean_speedup_opt": round(sum(spd_opt) / len(spd_opt), 3) if spd_opt else 0.0,
            "mean_speedup_all": round(sum(spd_all) / len(spd_all), 3) if spd_all else 0.0,
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
