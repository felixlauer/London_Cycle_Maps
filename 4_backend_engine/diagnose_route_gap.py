#!/usr/bin/env python3
"""
Isolate prod vs v4-bench differences on safe route 10 (Bromley↔Ealing).

Replays the bench corridor under controlled weight/ε/array variants and prints
expansions, elapsed_s, ms/exp, scale, impassable count.

  cd c:\\London_Cycle_Maps
  python 4_backend_engine/diagnose_route_gap.py

Writes: 0_documentation/testing/route_gap_diagnosis.md
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "4_backend_engine"
REPORT_DIR = REPO_ROOT / "0_documentation" / "testing"
REPORT_MD = REPORT_DIR / "route_gap_diagnosis.md"
REPORT_JSON = REPORT_DIR / "route_gap_diagnosis.json"

# Bench report reference (safe route 10, v4 seq)
REF_OPT_EXP = 674123
REF_OPT_S = 13.401
REF_IMPASSABLE = 199189

sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("FLASK_USE_RELOADER", "0")
os.environ.setdefault("SKIP_DISRUPTION_FETCH", "1")

import benchmark_array_costs as bac


DIFFS_DOC = """
## Codified prod vs bench input diffs

| Factor | v4 bench (`benchmark_array_v4.py`) | Production `/route` |
|--------|-------------------------------------|---------------------|
| Coords | `6_verification/test_routes.txt` | Map click / geocode |
| Weights | Raw `user_profiles.json` | Profile store (+ optional Supabase) |
| Clamps | None | `translation_layer.apply_preset_clamps` |
| Light | `light_weight` kept (safe=0.6) | Daytime: forced to 0 |
| ε | Report used **0.5** | Default **0.75** |
| Arrays | `bac` tables + `make_array_weight_fn_v3` | `edge_cost_arrays` |
| Parks | Shared bake once at bench `london_now()` | Shared bake at startup / live refresh (not per request on array path) |
| Live | `SKIP_DISRUPTION_FETCH=1` | Default fetch on (`--no-live` to match) |
| A* | `astar_unidirectional` | `run_astar(..., uni)` — same core |
"""


def _ms_per_exp(elapsed_s: float, expansions: int) -> float:
    if expansions <= 0:
        return 0.0
    return (elapsed_s * 1000.0) / expansions


def _run_opt(pathfinding_mod, G, start, end, h, weight_fn) -> dict:
    t0 = time.perf_counter()
    path, stats = pathfinding_mod.astar_unidirectional(G, start, end, h, weight_fn)
    elapsed = time.perf_counter() - t0
    exp = int(stats["expansions"])
    return {
        "elapsed_s": round(elapsed, 3),
        "expansions": exp,
        "edge_relaxations": int(stats["edge_relaxations"]),
        "ms_per_exp": round(_ms_per_exp(elapsed, exp), 4),
        "path_nodes": len(path) if path else 0,
    }


def _key_weights(w: dict) -> dict:
    keys = (
        "risk_weight",
        "light_weight",
        "speed_weight",
        "junction_weight",
        "vehicular_free_weight",
        "tfl_cycleway_weight",
        "tfl_live_weight",
        "green_weight",
        "hill_weight",
        "barrier_weight",
    )
    return {k: w.get(k) for k in keys}


def main() -> None:
    print("Bootstrapping engine (SKIP_DISRUPTION_FETCH=1)...", flush=True)
    (
        app_mod,
        pathfinding_mod,
        park_opening_hours,
        tfl_live,
        make_heuristic,
        compute_lb,
        _get_eps,
    ) = bac.bootstrap()

    G = app_mod.G
    import edge_cost_arrays
    import translation_layer

    presets = bac.load_preset_weights()
    w_raw = dict(presets["safe"])
    routes = bac.parse_test_routes()
    route = next(r for r in routes if "Bromley" in r["name"] and "Ealing" in r["name"])
    print(f"Route: {route['name']}", flush=True)

    start_snap = tfl_live.snap_to_edge(route["start_lat"], route["start_lon"])
    end_snap = tfl_live.snap_to_edge(route["end_lat"], route["end_lon"])
    if not start_snap or not end_snap:
        raise RuntimeError("snap failed")
    start, end = start_snap.anchor_node, end_snap.anchor_node
    print(f"  start_node={start} end_node={end}", flush=True)

    unique_hours = G.graph.get("park_opening_hours_unique") or []
    at_time = park_opening_hours.london_now()
    hours_map, fallback_open = park_opening_hours.build_request_hours_context(
        unique_hours, at_time
    )
    print(f"  park_hours_at={at_time.isoformat()} fallback_open={fallback_open}", flush=True)

    prod_tables = edge_cost_arrays.get_tables()
    prod_shared = edge_cost_arrays.get_shared_overlays()
    if prod_tables is None or prod_shared is None:
        raise RuntimeError("production edge_cost_arrays not installed after bootstrap")
    prod_impassable = int(prod_shared.impassable.sum())
    print(
        f"  prod shared: impassable={prod_impassable:,} live={prod_shared.has_live} "
        f"(bench ref impassable={REF_IMPASSABLE:,})",
        flush=True,
    )

    print("Building bac tables for bench_like...", flush=True)
    bac_tables, bac_build_s = bac.build_edge_cost_tables(app_mod)
    print(f"  bac tables: {bac_tables.n_edges:,} edges in {bac_build_s:.1f}s", flush=True)
    bac_shared = bac.build_shared_overlays(bac_tables, hours_map, fallback_open)
    bac_impassable = int(bac_shared.impassable.sum())
    print(
        f"  bac shared: impassable={bac_impassable:,} live={bac_shared.has_live} "
        f"bake={bac_shared.bake_s*1000:.1f}ms",
        flush=True,
    )

    # Sanity: same edge indexing
    length_delta = float(np_max_abs_diff(prod_tables.length, bac_tables.length))
    print(f"  length array max|prod-bac|={length_delta:.3e}", flush=True)

    def make_h(weights: dict, eps: float):
        scale = compute_lb(weights) * (1.0 + eps)
        return make_heuristic(end, G, cost_per_m=scale), scale

    def run_variant(name: str, weights: dict, eps: float, backend: str) -> dict:
        w = dict(weights)
        h, scale = make_h(w, eps)
        if backend == "bac":
            wfn = bac.make_array_weight_fn_v3(bac_tables, app_mod, w, bac_shared)
            impassable = bac_impassable
        elif backend == "prod":
            wfn = edge_cost_arrays.make_array_weight_fn_optimized(
                prod_tables,
                w,
                prod_shared,
                hard_cost=app_mod.BARRIER_HARD_COST,
                m_min=app_mod.M_MIN,
                r_min=app_mod.R_MIN,
            )
            impassable = prod_impassable
        else:
            raise ValueError(backend)

        print(f"\n=== {name} (backend={backend}, eps={eps}) ===", flush=True)
        print(f"  weights: {_key_weights(w)}", flush=True)
        print(f"  scale={scale:.4f} impassable={impassable:,}", flush=True)
        opt = _run_opt(pathfinding_mod, G, start, end, h, wfn)
        print(
            f"  opt: {opt['elapsed_s']:.3f}s exp={opt['expansions']:,} "
            f"ms/exp={opt['ms_per_exp']:.4f} "
            f"(ref {REF_OPT_S:.3f}s / {REF_OPT_EXP:,} exp)",
            flush=True,
        )
        return {
            "name": name,
            "backend": backend,
            "eps": eps,
            "scale": round(scale, 4),
            "impassable": impassable,
            "weights": _key_weights(w),
            "opt": opt,
            "exp_vs_ref": round(opt["expansions"] / REF_OPT_EXP, 3) if REF_OPT_EXP else None,
            "time_vs_ref": round(opt["elapsed_s"] / REF_OPT_S, 3) if REF_OPT_S else None,
        }

    rows: list[dict] = []

    # 1) bench_like
    rows.append(run_variant("bench_like", w_raw, 0.5, "bac"))

    # 2) prod arrays, same inputs as bench
    rows.append(run_variant("prod_arrays_same_inputs", w_raw, 0.5, "prod"))

    # 3) eps only
    rows.append(run_variant("+eps_0.75", w_raw, 0.75, "prod"))

    # 4) light gate only (daytime)
    w_light = dict(w_raw)
    w_light["light_weight"] = 0.0
    rows.append(run_variant("+light_gate", w_light, 0.5, "prod"))

    # 5) clamps only
    w_clamped, clamp_log = translation_layer.apply_preset_clamps(dict(w_raw), "safe")
    w_clamped["calming_source"] = w_raw.get("calming_source", "both")
    w_clamped["bike_type"] = w_raw.get("bike_type", "standard")
    for k in ("vf_shared_path", "vf_bus_lane", "vf_painted_lane"):
        w_clamped[k] = w_raw.get(k)
    rows.append(run_variant("+clamps", w_clamped, 0.5, "prod"))

    # 6) full daytime prod pipeline on JSON
    w_day, _ = translation_layer.apply_preset_clamps(dict(w_raw), "safe")
    w_day["light_weight"] = 0.0
    w_day["calming_source"] = w_raw.get("calming_source", "both")
    w_day["bike_type"] = w_raw.get("bike_type", "standard")
    for k in ("vf_shared_path", "vf_bus_lane", "vf_painted_lane"):
        w_day[k] = w_raw.get(k)
    rows.append(run_variant("+clamps+light_gate", w_day, 0.75, "prod"))

    # 7) profile store (local or supabase)
    try:
        import profile_store

        store = profile_store.get_store()
        prof = store.get_profile("preset_safe", None)
        if prof is None:
            print("\n=== supabase_profile SKIP (preset_safe not found) ===", flush=True)
        else:
            w_store = dict(prof["weights"])
            w_store["calming_source"] = "both"
            w_store["bike_type"] = prof.get("bike_type", "standard")
            toggles = prof.get("toggles") or {}
            vf = toggles.get("vf_infrastructure") or {}
            w_store["vf_shared_path"] = bool(vf.get("shared_path", True))
            w_store["vf_bus_lane"] = bool(vf.get("bus_lane", True))
            w_store["vf_painted_lane"] = bool(vf.get("painted_lane", False))
            preset = prof.get("preset") or "safe"
            w_store, _ = translation_layer.apply_preset_clamps(w_store, preset)
            # Match daytime /route
            w_store["light_weight"] = 0.0
            rows.append(run_variant("profile_store_day", w_store, 0.75, "prod"))
    except Exception as exc:
        print(f"\n=== profile_store SKIP ({exc}) ===", flush=True)

    app_target_exp = 937387
    for r in rows:
        r["exp_vs_app_target"] = round(r["opt"]["expansions"] / app_target_exp, 3)

    # Which single-factor move from bench_like increased expansions most?
    baseline_exp = rows[0]["opt"]["expansions"]
    movers = []
    for r in rows[1:]:
        movers.append(
            {
                "name": r["name"],
                "delta_exp": r["opt"]["expansions"] - baseline_exp,
                "delta_s": round(r["opt"]["elapsed_s"] - rows[0]["opt"]["elapsed_s"], 3),
                "expansions": r["opt"]["expansions"],
            }
        )
    movers.sort(key=lambda m: m["delta_exp"], reverse=True)

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "route": route["name"],
        "start_node": start,
        "end_node": end,
        "park_hours_at": at_time.isoformat(),
        "park_fallback_open": fallback_open,
        "prod_impassable": prod_impassable,
        "bac_impassable": bac_impassable,
        "length_array_max_abs_diff": length_delta,
        "ref_opt_exp": REF_OPT_EXP,
        "ref_opt_s": REF_OPT_S,
        "ref_impassable": REF_IMPASSABLE,
        "app_target_exp": app_target_exp,
        "clamp_sample": clamp_log[:5] if clamp_log else [],
        "movers_vs_bench_like": movers,
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "runs": rows}, f, indent=2)

    lines = [
        "# Route gap diagnosis — prod vs v4 bench",
        "",
        f"Generated: {meta['generated_at']}",
        f"Route: **{route['name']}** (safe optimized leg)",
        f"Park hours at: `{at_time.isoformat()}` | fallback_open={fallback_open}",
        f"Impassable: prod={prod_impassable:,} bac={bac_impassable:,} "
        f"(bench ref {REF_IMPASSABLE:,})",
        f"length|prod−bac|max = {length_delta:.3e}",
        "",
        DIFFS_DOC.strip(),
        "",
        "## Results",
        "",
        "| Variant | Backend | ε | scale | exp | s | ms/exp | exp÷ref | s÷ref |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        o = r["opt"]
        lines.append(
            f"| `{r['name']}` | {r['backend']} | {r['eps']} | {r['scale']} | "
            f"{o['expansions']:,} | {o['elapsed_s']:.3f} | {o['ms_per_exp']:.4f} | "
            f"{r['exp_vs_ref']} | {r['time_vs_ref']} |"
        )

    lines.extend(
        [
            "",
            f"Bench ref: **{REF_OPT_EXP:,}** exp / **{REF_OPT_S:.3f}s** / "
            f"~{_ms_per_exp(REF_OPT_S, REF_OPT_EXP):.4f} ms/exp",
            f"App `--no-live` target: **~{app_target_exp:,}** opt expansions",
            "",
            "## Movers vs `bench_like` (by Δ expansions)",
            "",
            "| Variant | Δ exp | Δ s | expansions |",
            "|---|---:|---:|---:|",
        ]
    )
    for m in movers:
        lines.append(
            f"| `{m['name']}` | {m['delta_exp']:+,} | {m['delta_s']:+.3f} | {m['expansions']:,} |"
        )

    # Verdict
    lines.extend(["", "## Verdict", ""])
    if abs(baseline_exp - REF_OPT_EXP) / REF_OPT_EXP > 0.15:
        lines.append(
            f"- `bench_like` already at **{baseline_exp:,}** exp vs ref **{REF_OPT_EXP:,}** "
            f"({baseline_exp / REF_OPT_EXP:.2f}×). Graph/park bake or runtime changed since the "
            "v4 report — compare impassable counts and park_hours_at before blaming prod gates."
        )
    else:
        lines.append(
            f"- `bench_like` reproduces the bench search size "
            f"({baseline_exp:,} ≈ {REF_OPT_EXP:,})."
        )

    if movers:
        top = movers[0]
        lines.append(
            f"- Largest expansion increase vs `bench_like`: **`{top['name']}`** "
            f"({top['delta_exp']:+,} exp, {top['delta_s']:+.3f}s)."
        )
        # ms/exp comparison
        bench_ms = rows[0]["opt"]["ms_per_exp"]
        prod_same = next(
            (r for r in rows if r["name"] == "prod_arrays_same_inputs"), None
        )
        if prod_same:
            lines.append(
                f"- Same inputs, bac vs prod arrays: "
                f"{rows[0]['opt']['ms_per_exp']:.4f} vs "
                f"{prod_same['opt']['ms_per_exp']:.4f} ms/exp "
                f"(expansions {rows[0]['opt']['expansions']:,} vs "
                f"{prod_same['opt']['expansions']:,})."
            )

    day = next((r for r in rows if r["name"] == "+clamps+light_gate"), None)
    if day:
        lines.append(
            f"- Full daytime prod pipeline (`+clamps+light_gate`, ε=0.75): "
            f"**{day['opt']['expansions']:,}** exp / **{day['opt']['elapsed_s']:.3f}s** "
            f"({day['exp_vs_ref']}× ref exp, {day['time_vs_ref']}× ref time)."
        )

    lines.extend(
        [
            "",
            "## Confirm against `/route`",
            "",
            "With backend on `--no-live`, hit the same coords and compare "
            "`meta.search_stats.optimized_expansions`, `meta.weights.light_weight`, "
            "`meta.light_gated_off`, `meta.heuristic_epsilon` to the matching variant above.",
            "",
            "```",
            f"GET /route?start_lat={route['start_lat']}&start_lon={route['start_lon']}"
            f"&end_lat={route['end_lat']}&end_lon={route['end_lon']}&profile_id=preset_safe",
            "```",
            "",
            "Re-run: `python 4_backend_engine/diagnose_route_gap.py`",
            "",
        ]
    )

    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {REPORT_MD}", flush=True)
    print(f"Wrote {REPORT_JSON}", flush=True)
    if movers:
        print(
            f"\nTop mover vs bench_like: {movers[0]['name']} "
            f"(Δexp={movers[0]['delta_exp']:+,})",
            flush=True,
        )


def np_max_abs_diff(a, b) -> float:
    import numpy as np

    if a.shape != b.shape:
        return float("inf")
    return float(np.max(np.abs(a.astype(np.float64) - b.astype(np.float64))))


if __name__ == "__main__":
    main()
