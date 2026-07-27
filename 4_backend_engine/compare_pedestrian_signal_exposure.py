#!/usr/bin/env python3
"""
Baseline / after compare: pedestrian-penalty exposure + signal entry/exit balance
on the 11 verification routes (Fast / Safe / Leisure / fastest).

Ped penalty = edges where bikes are not on dedicated infra and we apply
PEDESTRIAN_HIGHWAY_M (footway / pedestrian / path without cycleway* tags).
Service alleys (also M=4) are reported separately.

Signal entry/exit: after Phase 1 (signal clusters), edges carry signal_entry /
signal_exit. Before Phase 1 those counts are 0 and balance is skipped.

  cd c:\\London_Cycle_Maps
  python 4_backend_engine/compare_pedestrian_signal_exposure.py

Writes:
  0_documentation/testing/pedestrian_signal_exposure_baseline.{md,json}

After Phase 1:
  set COMPARE_PED_OUT=0_documentation\\testing\\pedestrian_signal_exposure_after.md
"""
from __future__ import annotations

import json
import os
import sys
import time
import types
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "4_backend_engine"
REPORT_DIR = REPO_ROOT / "0_documentation" / "testing"
_raw_out = os.environ.get(
    "COMPARE_PED_OUT",
    str(REPORT_DIR / "pedestrian_signal_exposure_baseline.md"),
)
REPORT_MD = Path(_raw_out)
if not REPORT_MD.is_absolute():
    REPORT_MD = (REPO_ROOT / REPORT_MD).resolve()
REPORT_JSON = REPORT_MD.with_suffix(".json")

PRESET_KEYS = (
    ("preset_fast", "fast"),
    ("preset_safe", "safe"),
    ("preset_leisure", "leisure"),
)

sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("FLASK_USE_RELOADER", "0")
os.environ.setdefault("SKIP_DISRUPTION_FETCH", "1")


def _mock_flask() -> None:
    if "flask" in sys.modules and hasattr(sys.modules["flask"], "g"):
        return
    flask = types.ModuleType("flask")

    class _Flask:
        def __init__(self, *a, **k):
            pass

        def route(self, *a, **k):
            return lambda fn: fn

        def before_request(self, fn):
            return fn

        def after_request(self, fn):
            return fn

        def errorhandler(self, *a, **k):
            return lambda fn: fn

    flask.Flask = _Flask
    flask.request = types.SimpleNamespace(args={}, headers={}, get_json=lambda *a, **k: {})
    flask.jsonify = lambda x: x
    flask.g = types.SimpleNamespace()
    sys.modules["flask"] = flask
    cors = types.ModuleType("flask_cors")
    cors.CORS = lambda *a, **k: None
    sys.modules["flask_cors"] = cors


def load_presets() -> tuple[dict[str, dict], str]:
    profiles_path = BACKEND_DIR / "user_profiles.json"
    if profiles_path.is_file():
        with open(profiles_path, encoding="utf-8") as f:
            data = json.load(f)
        out = {}
        for key, label in PRESET_KEYS:
            w = dict(data["profiles"][key]["weights"])
            w["calming_source"] = "both"
            w["bike_type"] = data["profiles"][key].get("bike_type", "standard")
            vf = (data["profiles"][key].get("toggles") or {}).get("vf_infrastructure") or {}
            w["vf_shared_path"] = bool(vf.get("shared_path", True))
            w["vf_bus_lane"] = bool(vf.get("bus_lane", True))
            w["vf_painted_lane"] = bool(vf.get("painted_lane", False))
            out[label] = w
        return out, "user_profiles.json"

    with open(BACKEND_DIR / "preset_config.json", encoding="utf-8") as f:
        data = json.load(f)
    out = {}
    for label in ("fast", "safe", "leisure"):
        block = data["presets"][label]
        w = dict(block["weights"])
        w["calming_source"] = "both"
        w["bike_type"] = "standard"
        vf = (block.get("toggles") or {}).get("vf_infrastructure") or {}
        w["vf_shared_path"] = bool(vf.get("shared_path", True))
        w["vf_bus_lane"] = bool(vf.get("bus_lane", True))
        w["vf_painted_lane"] = bool(vf.get("painted_lane", False))
        out[label] = w
    return out, "preset_config.json"


def _edge_attrs(G, u, v) -> dict:
    raw = G.get_edge_data(u, v)
    if not raw:
        return {}
    if "length" in raw:
        return raw
    # MultiDiGraph: {key: attr_dict}
    if all(isinstance(k, int) for k in raw.keys()):
        return next(iter(raw.values()))
    return raw


def _truthy(val) -> bool:
    return val in (True, 1, "1", "yes", "true")


def _is_ped_penalty_edge(app_mod, d: dict) -> bool:
    highway = str(d.get("type", "")).strip().lower()
    if highway not in app_mod.PEDESTRIAN_HIGHWAY_TYPES:
        return False
    if app_mod._has_dedicated_cycle_infrastructure(d):
        return False
    return True


def _is_service_alley_penalty(d: dict) -> bool:
    from cost_masks import is_service_access_denied, is_service_alley

    highway = str(d.get("type", "")).strip().lower()
    if highway != "service":
        return False
    if is_service_access_denied(d):
        return False
    return bool(is_service_alley(d))


def path_exposure(app_mod, path_nodes: list) -> dict:
    G = app_mod.G
    ped_m = 0.0
    ped_edges = 0
    ped_runs = 0
    in_ped_run = False
    alley_m = 0.0
    alley_edges = 0
    total_m = 0.0
    signal_node_count = 0
    signal_entry_count = 0
    signal_exit_count = 0
    entry_clusters: list[int] = []
    exit_clusters: list[int] = []

    start_in_cluster = False
    end_in_cluster = False
    if path_nodes:
        nd0 = G.nodes[path_nodes[0]] if path_nodes[0] in G.nodes else {}
        start_in_cluster = int(nd0.get("signal_cluster_id") or 0) > 0
        nd_n = G.nodes[path_nodes[-1]] if path_nodes[-1] in G.nodes else {}
        end_in_cluster = int(nd_n.get("signal_cluster_id") or 0) > 0

    for i in range(len(path_nodes) - 1):
        u, v = path_nodes[i], path_nodes[i + 1]
        d = _edge_attrs(G, u, v)
        length = float(d.get("length", 0.0) or 0.0)
        total_m += length

        if _is_ped_penalty_edge(app_mod, d):
            ped_m += length
            ped_edges += 1
            if not in_ped_run:
                ped_runs += 1
                in_ped_run = True
        else:
            in_ped_run = False

        if _is_service_alley_penalty(d):
            alley_m += length
            alley_edges += 1

        node_v = G.nodes[v] if v in G.nodes else {}
        if app_mod._node_signal_penalty(node_v) > 0:
            signal_node_count += 1

        if _truthy(d.get("signal_entry")):
            signal_entry_count += 1
            cid = int(d.get("signal_cluster_id") or node_v.get("signal_cluster_id") or 0)
            if cid:
                entry_clusters.append(cid)
        if _truthy(d.get("signal_exit")):
            signal_exit_count += 1
            cid = int(d.get("signal_cluster_id") or 0)
            if not cid:
                node_u = G.nodes[u] if u in G.nodes else {}
                cid = int(node_u.get("signal_cluster_id") or 0)
            if cid:
                exit_clusters.append(cid)

    delta = signal_entry_count - signal_exit_count
    has_flags = signal_entry_count > 0 or signal_exit_count > 0
    if not has_flags:
        balance_ok = None
        balance_note = "phase1_not_shipped (no signal_entry/exit on path)"
        expected_delta = None
    else:
        if start_in_cluster and not end_in_cluster:
            expected_delta = -1
        elif end_in_cluster and not start_in_cluster:
            expected_delta = 1
        else:
            expected_delta = 0
        balance_ok = (delta == expected_delta) or (abs(delta) <= 1)
        balance_note = (
            f"delta={delta} expected={expected_delta} "
            f"start_in={start_in_cluster} end_in={end_in_cluster}"
        )

    return {
        "length_m": round(total_m, 1),
        "ped_penalty_edges": ped_edges,
        "ped_penalty_m": round(ped_m, 1),
        "ped_penalty_pct": round(100.0 * ped_m / total_m, 2) if total_m > 0 else 0.0,
        "ped_penalty_runs": ped_runs,
        "service_alley_edges": alley_edges,
        "service_alley_m": round(alley_m, 1),
        "signal_node_count": signal_node_count,
        "signal_entry_count": signal_entry_count,
        "signal_exit_count": signal_exit_count,
        "signal_entry_exit_delta": delta,
        "signal_balance_ok": balance_ok,
        "signal_balance_note": balance_note,
        "start_in_signal_cluster": start_in_cluster,
        "end_in_signal_cluster": end_in_cluster,
        "entry_cluster_ids": entry_clusters,
        "exit_cluster_ids": exit_clusters,
    }


def md_table(rows: list[dict], preset: str) -> list[str]:
    subset = [r for r in rows if r["preset"] == preset]
    lines = [
        f"### {preset}",
        "",
        "| Route | Len m | Ped edges | Ped m | Ped % | Ped runs | Alley m | Sig nodes | Entry | Exit | Δ | Balance |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|",
    ]
    for r in subset:
        x = r["exposure"]
        bal = x["signal_balance_ok"]
        bal_s = "—" if bal is None else ("ok" if bal else "FAIL")
        lines.append(
            f"| {r['route']} | {x['length_m']:.0f} | {x['ped_penalty_edges']} | "
            f"{x['ped_penalty_m']:.0f} | {x['ped_penalty_pct']:.1f} | {x['ped_penalty_runs']} | "
            f"{x['service_alley_m']:.0f} | {x['signal_node_count']} | "
            f"{x['signal_entry_count']} | {x['signal_exit_count']} | "
            f"{x['signal_entry_exit_delta']} | {bal_s} |"
        )
    if subset:
        lines.append(
            f"| **mean** | {mean(r['exposure']['length_m'] for r in subset):.0f} | "
            f"{mean(r['exposure']['ped_penalty_edges'] for r in subset):.1f} | "
            f"{mean(r['exposure']['ped_penalty_m'] for r in subset):.0f} | "
            f"{mean(r['exposure']['ped_penalty_pct'] for r in subset):.1f} | "
            f"{mean(r['exposure']['ped_penalty_runs'] for r in subset):.1f} | "
            f"{mean(r['exposure']['service_alley_m'] for r in subset):.0f} | "
            f"{mean(r['exposure']['signal_node_count'] for r in subset):.1f} | "
            f"{mean(r['exposure']['signal_entry_count'] for r in subset):.1f} | "
            f"{mean(r['exposure']['signal_exit_count'] for r in subset):.1f} | "
            f" | |"
        )
    lines.append("")
    return lines


def main() -> int:
    _mock_flask()
    os.chdir(BACKEND_DIR)
    import benchmark_array_costs as bac
    import park_opening_hours
    import tfl_live
    import app as app_mod
    import pathfinding
    from routing_heuristic import (
        compute_optimized_cost_per_metre_lower_bound as compute_lb,
        make_heuristic,
    )

    G = app_mod.G
    if G is None:
        print("ERROR: graph not loaded", flush=True)
        return 1

    presets, preset_src = load_presets()
    routes = bac.parse_test_routes()
    modes = [("fastest", None)] + list(presets.items())

    print(
        f"Pedestrian / signal exposure on {len(routes)} routes × {len(modes)} modes\n"
        f"  presets={preset_src}; PEDESTRIAN_HIGHWAY_M={app_mod.PEDESTRIAN_HIGHWAY_M}\n"
        f"  out={REPORT_MD}",
        flush=True,
    )

    rows: list[dict] = []
    t0 = time.perf_counter()

    for i, route in enumerate(routes, 1):
        print(f"[{i}/{len(routes)}] {route['name']} …", flush=True)
        start = tfl_live.snap_to_edge(route["start_lat"], route["start_lon"])
        end = tfl_live.snap_to_edge(route["end_lat"], route["end_lon"])
        if not start or not end:
            raise RuntimeError(f"snap failed: {route['name']}")
        hours_map, fallback = park_opening_hours.build_request_hours_context(
            G.graph.get("park_opening_hours_unique") or [],
            park_opening_hours.london_now(),
        )

        for preset, weights in modes:
            t1 = time.perf_counter()
            if weights is None:
                h = make_heuristic(end.anchor_node, G, cost_per_m=1.0)
                wf = app_mod.make_weight_fastest(hours_map, fallback)
            else:
                h = make_heuristic(end.anchor_node, G, cost_per_m=compute_lb(weights))
                wf = app_mod.make_weight_optimized(weights, hours_map, fallback)
            path, _ = pathfinding.astar_unidirectional(
                G, start.anchor_node, end.anchor_node, h, wf
            )
            exp = path_exposure(app_mod, path)
            elapsed = time.perf_counter() - t1
            rows.append(
                {
                    "route": route["name"],
                    "preset": preset,
                    "elapsed_s": round(elapsed, 3),
                    "exposure": exp,
                    "path_nodes": len(path),
                }
            )
            print(
                f"    {preset}: ped_m={exp['ped_penalty_m']:.0f} "
                f"runs={exp['ped_penalty_runs']} "
                f"sig_nodes={exp['signal_node_count']} "
                f"entry/exit={exp['signal_entry_count']}/{exp['signal_exit_count']} "
                f"({elapsed:.1f}s)",
                flush=True,
            )

    pivot = {}
    for preset, _ in modes:
        sub = [r for r in rows if r["preset"] == preset]
        pivot[preset] = {
            "mean_ped_penalty_m": round(mean(r["exposure"]["ped_penalty_m"] for r in sub), 1),
            "mean_ped_penalty_pct": round(mean(r["exposure"]["ped_penalty_pct"] for r in sub), 2),
            "mean_ped_penalty_runs": round(mean(r["exposure"]["ped_penalty_runs"] for r in sub), 2),
            "mean_ped_penalty_edges": round(mean(r["exposure"]["ped_penalty_edges"] for r in sub), 2),
            "mean_service_alley_m": round(mean(r["exposure"]["service_alley_m"] for r in sub), 1),
            "mean_signal_node_count": round(mean(r["exposure"]["signal_node_count"] for r in sub), 2),
            "mean_signal_entry_count": round(mean(r["exposure"]["signal_entry_count"] for r in sub), 2),
            "mean_signal_exit_count": round(mean(r["exposure"]["signal_exit_count"] for r in sub), 2),
            "balance_fail_routes": [
                r["route"]
                for r in sub
                if r["exposure"]["signal_balance_ok"] is False
            ],
        }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_s": round(time.perf_counter() - t0, 1),
        "report": str(REPORT_MD),
        "definition": {
            "ped_penalty": (
                "highway in {footway,pedestrian,path} AND NOT dedicated cycle infra "
                f"→ length multiplier PEDESTRIAN_HIGHWAY_M={app_mod.PEDESTRIAN_HIGHWAY_M}"
            ),
            "service_alley": "highway=service alley → same M (reported separately)",
            "signal_node_count": "legacy: arrivals at traffic_signals=yes nodes",
            "signal_entry_exit": "Phase 1 edge flags; 0 until signal clusters ship",
            "balance_rule": (
                "After Phase 1: entry≈exit; |Δ|≤1 allowed if start/end inside cluster"
            ),
        },
        "pivot": pivot,
        "rows": rows,
        "spec": "0_documentation/tasks/signal_cluster_remodel.md",
    }

    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "# Pedestrian + signal entry/exit exposure",
        "",
        f"Generated: `{payload['generated_at']}` · wall `{payload['elapsed_s']}s`",
        "",
        "## Definition",
        "",
        f"- **Ped penalty:** {payload['definition']['ped_penalty']}",
        f"- **Service alley:** {payload['definition']['service_alley']}",
        f"- **Signal nodes:** {payload['definition']['signal_node_count']}",
        f"- **Entry/exit:** {payload['definition']['signal_entry_exit']}",
        f"- **Balance:** {payload['definition']['balance_rule']}",
        "",
        "Spec: [`../tasks/signal_cluster_remodel.md`](../tasks/signal_cluster_remodel.md)",
        "",
        "## Pivot (means over 11 routes)",
        "",
        "| Preset | Ped m | Ped % | Ped runs | Ped edges | Alley m | Sig nodes | Entry | Exit | Balance fails |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for preset, _ in modes:
        p = pivot[preset]
        fails = ", ".join(p["balance_fail_routes"]) or "—"
        lines.append(
            f"| {preset} | {p['mean_ped_penalty_m']} | {p['mean_ped_penalty_pct']} | "
            f"{p['mean_ped_penalty_runs']} | {p['mean_ped_penalty_edges']} | "
            f"{p['mean_service_alley_m']} | {p['mean_signal_node_count']} | "
            f"{p['mean_signal_entry_count']} | {p['mean_signal_exit_count']} | {fails} |"
        )
    lines.extend(["", "## Per route", ""])
    for preset, _ in modes:
        lines.extend(md_table(rows, preset))

    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {REPORT_MD}\nWrote {REPORT_JSON}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
