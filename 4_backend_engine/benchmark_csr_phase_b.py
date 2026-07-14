#!/usr/bin/env python3
"""
Phase B CSR heuristic benchmark.

Isolates the Phase B lat/lon work on top of Phase A CSR neighbor/cost walk:

  nodes    — CSR search + G.nodes dict heuristic (Phase A without B)
  phase_a  — CSR search + lon/lat float arrays + full haversine
  phase_b  — CSR search + precomputed lat_rad/lon_rad/cos_lat (production)

Also reports NX array A* with G.nodes heuristic vs NX + CSR-array heuristic
(for CSR_ASTAR=0 / bi paths).

Acceptance:
  - path / expansions / cost parity across nodes / phase_a / phase_b
  - report wall speedups (expect modest phase_a→phase_b; larger nodes→phase_b)

  cd c:\\London_Cycle_Maps
  python 4_backend_engine/benchmark_csr_phase_b.py

Optional: CSR_BENCH_REPEATS=3

Writes:
  0_documentation/testing/csr_astar_phase_b_report.md
  0_documentation/testing/csr_astar_phase_b_report.json

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
REPORT_MD = REPORT_DIR / "csr_astar_phase_b_report.md"
REPORT_JSON = REPORT_DIR / "csr_astar_phase_b_report.json"

sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("FLASK_USE_RELOADER", "0")
os.environ.setdefault("SKIP_DISRUPTION_FETCH", "1")

import benchmark_array_costs as bac
import edge_cost_arrays
import graph_csr

COST_RTOL = 1e-6
COST_ATOL = 1e-3
PRESETS = ("fast", "safe")
CSR_MODES = ("nodes", "phase_a", "phase_b")


def _median(xs: list[float]) -> float:
    return float(statistics.median(xs)) if xs else 0.0


def _spd(base: float, other: float) -> float:
    return round(base / other, 3) if other > 0 else 0.0


def _run_csr(
    pathfinding_mod,
    csr,
    G,
    start,
    end,
    cost_by_eid,
    cost_per_m,
    weight_fn,
    mode: str,
    repeats: int,
):
    times = []
    path = stats = None
    for _ in range(repeats):
        t0 = time.perf_counter()
        path, stats = pathfinding_mod.astar_csr_unidirectional(
            csr,
            start,
            end,
            cost_by_eid,
            cost_per_m=cost_per_m,
            heuristic_mode=mode,
            G=G if mode == "nodes" else None,
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


def _run_nx(pathfinding_mod, G, start, end, h, weight_fn, repeats: int):
    times = []
    path = stats = None
    for _ in range(repeats):
        t0 = time.perf_counter()
        path, stats = pathfinding_mod.astar_unidirectional(G, start, end, h, weight_fn)
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
    s = payload["summary"]
    lines = [
        "# CSR A* Phase B report",
        "",
        f"Generated: {payload['generated_at']}",
        f"Repeats (median): {payload['repeats']}",
        f"CSR build: {payload['csr_build_s']:.2f}s "
        f"({payload['csr_n_nodes']:,} nodes, {payload['csr_n_edges']:,} arcs)",
        f"ε optimized: {payload['eps']} | ε fastest: {payload['eps_fast']}",
        f"Parity OK: {ok_n}/{len(rows)}",
        "",
        "## Summary (CSR modes)",
        "",
        f"- Mean nodes → phase_b: **{s['mean_nodes_to_b']:.3f}×**",
        f"- Mean phase_a → phase_b: **{s['mean_a_to_b']:.3f}×**",
        f"- Mean NX nodes_h → NX csr_h: **{s['mean_nx_nodes_to_csr_h']:.3f}×**",
        "",
        "## Per-route CSR heuristic modes",
        "",
        "| Preset | Route | Leg | nodes s | A s | B s | nodes→B | A→B | Exp | Path | OK |",
        "|--------|-------|-----|---------|-----|-----|---------|-----|-----|------|----|",
    ]
    for r in rows:
        if r["kind"] != "csr_modes":
            continue
        lines.append(
            f"| {r['preset']} | {r['route']} | {r['leg']} | "
            f"{r['nodes_s']:.3f} | {r['phase_a_s']:.3f} | {r['phase_b_s']:.3f} | "
            f"{r['spd_nodes_to_b']:.3f}× | {r['spd_a_to_b']:.3f}× | "
            f"{r['expansions']} | {'Y' if r['path_exact'] else 'N'} | "
            f"{'Y' if r['ok'] else 'N'} |"
        )
    lines.extend(
        [
            "",
            "## NX heuristic: G.nodes vs CSR arrays",
            "",
            "| Preset | Route | Leg | NX nodes_h s | NX csr_h s | Speedup | Exp | Path | OK |",
            "|--------|-------|-----|--------------|------------|---------|-----|------|----|",
        ]
    )
    for r in rows:
        if r["kind"] != "nx_heuristic":
            continue
        lines.append(
            f"| {r['preset']} | {r['route']} | {r['leg']} | "
            f"{r['nx_nodes_s']:.3f} | {r['nx_csr_s']:.3f} | {r['speedup']:.3f}× | "
            f"{r['expansions']} | {'Y' if r['path_exact'] else 'N'} | "
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

    tables = edge_cost_arrays.get_tables()
    shared = edge_cost_arrays.get_shared_overlays()
    if tables is None or shared is None:
        raise RuntimeError("Production edge tables/overlays missing after bootstrap")
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
    if not hasattr(csr, "cos_lat") or csr.cos_lat is None:
        raise RuntimeError("CSR missing Phase B radian arrays — rebuild graph_csr")
    print(
        f"CSR: {csr.n_nodes:,} nodes, {csr.n_edges:,} arcs in {csr.build_s:.1f}s",
        flush=True,
    )

    presets = bac.load_preset_weights()
    routes = bac.parse_test_routes()
    hard = float(app_mod.BARRIER_HARD_COST)
    m_min = float(app_mod.M_MIN)
    r_min = float(app_mod.R_MIN)

    rows: list[dict] = []
    spd_nodes_b: list[float] = []
    spd_a_b: list[float] = []
    spd_nx: list[float] = []

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

            for leg, scale, cost_eid, weight_fn in (
                ("fastest", scale_fast, c_fast, w_fast),
                ("optimized", scale_opt, c_opt, w_opt),
            ):
                results = {}
                for mode in CSR_MODES:
                    results[mode] = _run_csr(
                        pathfinding_mod,
                        csr,
                        G,
                        start,
                        end,
                        cost_eid,
                        scale,
                        weight_fn,
                        mode,
                        repeats,
                    )

                path_exact = (
                    results["nodes"]["path"]
                    == results["phase_a"]["path"]
                    == results["phase_b"]["path"]
                )
                exp_match = (
                    results["nodes"]["expansions"]
                    == results["phase_a"]["expansions"]
                    == results["phase_b"]["expansions"]
                )
                cost_ok = all(
                    abs(results["nodes"]["path_cost"] - results[m]["path_cost"])
                    <= (COST_ATOL + COST_RTOL * abs(results["nodes"]["path_cost"]))
                    for m in ("phase_a", "phase_b")
                )
                ok = path_exact and exp_match and cost_ok
                snb = _spd(results["nodes"]["elapsed_s"], results["phase_b"]["elapsed_s"])
                sab = _spd(
                    results["phase_a"]["elapsed_s"], results["phase_b"]["elapsed_s"]
                )
                spd_nodes_b.append(snb)
                spd_a_b.append(sab)
                rows.append(
                    {
                        "kind": "csr_modes",
                        "preset": preset_name,
                        "route": route["name"],
                        "leg": leg,
                        "nodes_s": round(results["nodes"]["elapsed_s"], 4),
                        "phase_a_s": round(results["phase_a"]["elapsed_s"], 4),
                        "phase_b_s": round(results["phase_b"]["elapsed_s"], 4),
                        "spd_nodes_to_b": snb,
                        "spd_a_to_b": sab,
                        "expansions": results["phase_b"]["expansions"],
                        "path_exact": path_exact,
                        "exp_match": exp_match,
                        "cost_ok": cost_ok,
                        "ok": ok,
                    }
                )
                flag = "OK" if ok else "FAIL"
                print(
                    f"    csr {leg}: nodes={results['nodes']['elapsed_s']:.3f}s "
                    f"A={results['phase_a']['elapsed_s']:.3f}s "
                    f"B={results['phase_b']['elapsed_s']:.3f}s "
                    f"(nodes→B {snb:.2f}× A→B {sab:.2f}×) [{flag}]",
                    flush=True,
                )

                # NX: G.nodes heuristic vs CSR-array heuristic (same weight fn)
                h_nodes = make_heuristic(end, G, cost_per_m=scale, csr=None)
                h_csr = make_heuristic(end, G, cost_per_m=scale, csr=csr)
                nx_n = _run_nx(
                    pathfinding_mod, G, start, end, h_nodes, weight_fn, repeats
                )
                nx_c = _run_nx(
                    pathfinding_mod, G, start, end, h_csr, weight_fn, repeats
                )
                nx_path_ok = nx_n["path"] == nx_c["path"]
                nx_exp_ok = nx_n["expansions"] == nx_c["expansions"]
                nx_cost_ok = abs(nx_n["path_cost"] - nx_c["path_cost"]) <= (
                    COST_ATOL + COST_RTOL * abs(nx_n["path_cost"])
                )
                nx_ok = nx_path_ok and nx_exp_ok and nx_cost_ok
                nx_spd = _spd(nx_n["elapsed_s"], nx_c["elapsed_s"])
                spd_nx.append(nx_spd)
                rows.append(
                    {
                        "kind": "nx_heuristic",
                        "preset": preset_name,
                        "route": route["name"],
                        "leg": leg,
                        "nx_nodes_s": round(nx_n["elapsed_s"], 4),
                        "nx_csr_s": round(nx_c["elapsed_s"], 4),
                        "speedup": nx_spd,
                        "expansions": nx_c["expansions"],
                        "path_exact": nx_path_ok,
                        "ok": nx_ok,
                    }
                )
                print(
                    f"    nx  {leg}: nodes_h={nx_n['elapsed_s']:.3f}s "
                    f"csr_h={nx_c['elapsed_s']:.3f}s ({nx_spd:.2f}×) "
                    f"[{'OK' if nx_ok else 'FAIL'}]",
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
        "summary": {
            "mean_nodes_to_b": round(sum(spd_nodes_b) / len(spd_nodes_b), 3)
            if spd_nodes_b
            else 0.0,
            "mean_a_to_b": round(sum(spd_a_b) / len(spd_a_b), 3) if spd_a_b else 0.0,
            "mean_nx_nodes_to_csr_h": round(sum(spd_nx) / len(spd_nx), 3)
            if spd_nx
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
