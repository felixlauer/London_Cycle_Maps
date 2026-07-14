#!/usr/bin/env python3
"""
Phase D geometry preparse benchmark.

Measures path-geometry wall time with cold WKT parse vs warm `_coords` cache
on the same A* paths (fastest + optimized) for test_routes × fast/safe.

Also times a one-shot full-graph preparse (all edges → `_coords`).

  cd c:\\London_Cycle_Maps
  python 4_backend_engine/benchmark_geom_preparse.py

Optional:
  GEOM_BENCH_REPEATS=3
  SKIP_DISRUPTION_FETCH=1  (defaulted)

Writes:
  0_documentation/testing/geom_preparse_phase_d_report.md
  0_documentation/testing/geom_preparse_phase_d_report.json

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
REPORT_MD = REPORT_DIR / "geom_preparse_phase_d_report.md"
REPORT_JSON = REPORT_DIR / "geom_preparse_phase_d_report.json"

sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("FLASK_USE_RELOADER", "0")
os.environ.setdefault("SKIP_DISRUPTION_FETCH", "1")
# Bench controls its own preparse; don't background-race during bootstrap.
os.environ["GEOM_PREPARSE"] = "off"

import benchmark_array_costs as bac
import edge_cost_arrays
import graph_csr
import pathfinding_numba

PRESETS = ("fast", "safe")


def _median(xs: list[float]) -> float:
    return float(statistics.median(xs)) if xs else 0.0


def _spd(base: float, other: float) -> float:
    return round(base / other, 3) if other > 0 else 0.0


def _clear_path_coords(G, path: list) -> int:
    n = 0
    for i in range(len(path) - 1):
        ed = G.get_edge_data(path[i], path[i + 1])
        if not ed:
            continue
        if G.is_multigraph():
            for d in ed.values():
                if "_coords" in d:
                    del d["_coords"]
                    n += 1
        elif "_coords" in ed:
            del ed["_coords"]
            n += 1
    return n


def _time_reconstruct(app_mod, path: list, repeats: int) -> float:
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        _ = app_mod.reconstruct_path_geometry(path)
        times.append(time.perf_counter() - t0)
    return _median(times)


def _run_astar_paths(
    app_mod,
    pathfinding_mod,
    tables,
    shared,
    csr,
    start,
    end,
    weights,
    bike,
    hard,
    m_min,
    r_min,
    scale_fast,
    scale_opt,
):
    """Return (path_fast, path_opt) using Numba if available else CSR-py."""
    use_numba = pathfinding_numba.is_available() and pathfinding_numba.numba_astar_enabled()
    if use_numba:
        pf, _ = pathfinding_numba.astar_numba_unidirectional(
            csr,
            start,
            end,
            tables,
            shared,
            mode="fastest",
            cost_per_m=scale_fast,
            hard_cost=hard,
            bike_type=bike,
        )
        sc = pathfinding_numba.pack_optimized_scalars(
            weights, shared, hard, m_min, r_min
        )
        po, _ = pathfinding_numba.astar_numba_unidirectional(
            csr,
            start,
            end,
            tables,
            shared,
            mode="optimized",
            cost_per_m=scale_opt,
            hard_cost=hard,
            bike_type=bike,
            opt_scalars=sc,
        )
        return pf, po

    c_fast = edge_cost_arrays.make_array_cost_by_eid_fastest(
        tables, hard, shared, bike_type=bike
    )
    c_opt = edge_cost_arrays.make_array_cost_by_eid_optimized(
        tables, weights, shared, hard_cost=hard, m_min=m_min, r_min=r_min
    )
    pf, _ = pathfinding_mod.astar_csr_unidirectional(
        csr, start, end, c_fast, cost_per_m=scale_fast
    )
    po, _ = pathfinding_mod.astar_csr_unidirectional(
        csr, start, end, c_opt, cost_per_m=scale_opt
    )
    return pf, po


def _write_reports(payload: dict) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    s = payload["summary"]
    rows = payload["rows"]
    lines = [
        "# Geometry preparse Phase D report",
        "",
        f"Generated: {payload['generated_at']}",
        f"Repeats (median): {payload['repeats']}",
        f"Full-graph preparse: **{payload['full_preparse']['elapsed_s']:.1f} s** "
        f"({payload['full_preparse']['n_parsed']:,} edges, "
        f"{payload['full_preparse']['edges_per_s']:,.0f} edges/s)",
        "",
        "## Summary (path reconstruct wall)",
        "",
        f"- Mean cold (WKT) fastest+opt sum: **{s['mean_cold_sum_s']:.3f} s**",
        f"- Mean warm (`_coords`) fastest+opt sum: **{s['mean_warm_sum_s']:.3f} s**",
        f"- Mean speedup (cold/warm): **{s['mean_speedup']:.2f}×**",
        "",
        "## Per-route",
        "",
        "| Preset | Route | Cold sum s | Warm sum s | Speedup | Cold fast | Warm fast | Cold opt | Warm opt | Path edges |",
        "|--------|-------|------------|------------|---------|-----------|-----------|----------|----------|------------|",
    ]
    for r in rows:
        lines.append(
            f"| {r['preset']} | {r['route']} | "
            f"{r['cold_sum_s']:.3f} | {r['warm_sum_s']:.3f} | {r['speedup']:.2f}× | "
            f"{r['cold_fast_s']:.3f} | {r['warm_fast_s']:.3f} | "
            f"{r['cold_opt_s']:.3f} | {r['warm_opt_s']:.3f} | "
            f"{r['n_edges_fast']}+{r['n_edges_opt']} |"
        )
    lines.append("")
    lines.append(f"JSON: `{REPORT_JSON.relative_to(REPO_ROOT).as_posix()}`")
    lines.append("")
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {REPORT_MD}", flush=True)
    print(f"Wrote {REPORT_JSON}", flush=True)


def main() -> None:
    repeats = max(1, int(os.environ.get("GEOM_BENCH_REPEATS", "1")))
    print("Bootstrapping engine (GEOM_PREPARSE=off for controlled bench)...", flush=True)
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
        raise RuntimeError("tables/overlays missing after bootstrap")
    csr = graph_csr.get_csr()
    if csr is None:
        csr = graph_csr.build_csr(G)
        graph_csr.set_csr(csr)

    if pathfinding_numba.is_available():
        print("Warming Numba...", flush=True)
        pathfinding_numba.warmup(csr, tables, shared, hard_cost=float(app_mod.BARRIER_HARD_COST))

    print("Full-graph geometry preparse...", flush=True)
    # Clear any lazy caches from warmup/bootstrap helpers
    cleared = 0
    for _u, _v, d in G.edges(data=True):
        if "_coords" in d:
            del d["_coords"]
            cleared += 1
    print(f"  cleared {cleared:,} cached _coords", flush=True)
    full = edge_cost_arrays.preparse_edge_geometries(G)
    print(
        f"  parsed {full['n_parsed']:,} in {full['elapsed_s']:.1f}s "
        f"({full['edges_per_s']:,.0f}/s)",
        flush=True,
    )

    presets = bac.load_preset_weights()
    routes = bac.parse_test_routes()
    hard = float(app_mod.BARRIER_HARD_COST)
    m_min = float(app_mod.M_MIN)
    r_min = float(app_mod.R_MIN)

    rows: list[dict] = []
    cold_sums: list[float] = []
    warm_sums: list[float] = []
    speedups: list[float] = []

    for preset_name in PRESETS:
        if preset_name not in presets:
            continue
        weights = presets[preset_name]
        bike = str(weights.get("bike_type", "standard"))
        print(f"\n=== Preset: {preset_name} ===", flush=True)
        scale_fast = 1.0 * (1.0 + eps_fast)
        scale_opt = compute_lb(weights) * (1.0 + eps)

        for route in routes:
            print(f"  {route['name']}...", flush=True)
            start_snap = tfl_live.snap_to_edge(route["start_lat"], route["start_lon"])
            end_snap = tfl_live.snap_to_edge(route["end_lat"], route["end_lon"])
            if not start_snap or not end_snap:
                raise RuntimeError(f"snap failed: {route['name']}")
            start = start_snap.anchor_node
            end = end_snap.anchor_node

            path_f, path_o = _run_astar_paths(
                app_mod,
                pathfinding_mod,
                tables,
                shared,
                csr,
                start,
                end,
                weights,
                bike,
                hard,
                m_min,
                r_min,
                scale_fast,
                scale_opt,
            )

            # Cold: strip path _coords then reconstruct (forces WKT parse)
            _clear_path_coords(G, path_f)
            cold_f = _time_reconstruct(app_mod, path_f, repeats)
            _clear_path_coords(G, path_o)
            cold_o = _time_reconstruct(app_mod, path_o, repeats)

            # Warm: path edges now cached from cold run; time cache hits
            warm_f = _time_reconstruct(app_mod, path_f, repeats)
            warm_o = _time_reconstruct(app_mod, path_o, repeats)

            cold_sum = cold_f + cold_o
            warm_sum = warm_f + warm_o
            spd = _spd(cold_sum, warm_sum)
            cold_sums.append(cold_sum)
            warm_sums.append(warm_sum)
            speedups.append(spd)
            row = {
                "preset": preset_name,
                "route": route["name"],
                "cold_fast_s": round(cold_f, 4),
                "warm_fast_s": round(warm_f, 4),
                "cold_opt_s": round(cold_o, 4),
                "warm_opt_s": round(warm_o, 4),
                "cold_sum_s": round(cold_sum, 4),
                "warm_sum_s": round(warm_sum, 4),
                "speedup": spd,
                "n_edges_fast": max(0, len(path_f) - 1),
                "n_edges_opt": max(0, len(path_o) - 1),
            }
            rows.append(row)
            print(
                f"    cold={cold_sum:.3f}s warm={warm_sum:.3f}s ({spd:.1f}×) "
                f"edges={row['n_edges_fast']}+{row['n_edges_opt']}",
                flush=True,
            )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repeats": repeats,
        "eps": eps,
        "eps_fast": eps_fast,
        "full_preparse": full,
        "summary": {
            "mean_cold_sum_s": round(sum(cold_sums) / len(cold_sums), 4) if cold_sums else 0.0,
            "mean_warm_sum_s": round(sum(warm_sums) / len(warm_sums), 4) if warm_sums else 0.0,
            "mean_speedup": round(sum(speedups) / len(speedups), 3) if speedups else 0.0,
        },
        "rows": rows,
    }
    _write_reports(payload)
    print("\nDone.", flush=True)


if __name__ == "__main__":
    main()
