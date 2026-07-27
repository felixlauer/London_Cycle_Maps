#!/usr/bin/env python3
"""
Compare Fast + Leisure at SIGNAL_WAIT_SECONDS in {20, 5.5, 7.5} and report
core route stats (calculate_path_stats / sweep-compatible).

Safe omitted. Always includes non-optimised fastest baseline.
Does NOT change production routing.

  cd c:\\London_Cycle_Maps
  python 4_backend_engine/compare_signal_wait_seconds.py

Optional: SIGNAL_WAIT_LIST=20,5.5,7.5

Writes 0_documentation/testing/signal_wait_compare.{md,json}
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
REPORT_MD = Path(
    os.environ.get("COMPARE_SIGNAL_OUT", str(REPORT_DIR / "signal_wait_compare.md"))
)
REPORT_JSON = REPORT_MD.with_suffix(".json")

SIGNAL_WAIT_LIST = [
    float(x.strip())
    for x in os.environ.get("SIGNAL_WAIT_LIST", "20,5.5,7.5").split(",")
    if x.strip()
]

CORE_METRICS = [
    ("length_m", "Length (m)"),
    ("duration_min", "Duration (min)"),
    ("signal_count", "Signals"),
    ("junction_count", "Junctions"),
    ("calming_count", "Calming"),
    ("barrier_penalty_count", "Barrier penalties"),
    ("elevation_gain", "Elevation gain (m)"),
    ("steep_count", "Steep segments"),
    ("accidents", "Accidents"),
    ("speed_stress_pct", "Speed stress (%)"),
    ("vehicular_free_pct", "Vehicular-free (%)"),
    ("tfl_cycleway_pct", "TfL cycleway (%)"),
    ("tfl_network_pct", "TfL network (%)"),
    ("green_pct", "Green (%)"),
    ("illumination_pct", "Lit (%)"),
    ("rough_pct", "Rough (%)"),
    ("give_way_count", "Give-way"),
    ("stop_sign_count", "Stop signs"),
]

PRESET_KEYS = (("preset_fast", "fast"), ("preset_leisure", "leisure"))

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


def load_preset_weights() -> dict[str, dict]:
    with open(BACKEND_DIR / "user_profiles.json", encoding="utf-8") as f:
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
    return out


def path_core(app_mod, path, weights=None) -> dict:
    vf_mask = None
    calming = "both"
    if weights:
        from cost_masks import vf_allowed_masks

        calming = weights.get("calming_source") or "both"
        vf_mask, _ = vf_allowed_masks(
            shared_path=bool(weights.get("vf_shared_path", True)),
            bus_lane=bool(weights.get("vf_bus_lane", True)),
            painted_lane=bool(weights.get("vf_painted_lane", False)),
        )
    stats = app_mod.calculate_path_stats(
        path,
        calming_source=calming,
        speed_kmh=16.0,
        vf_mask_allowed=vf_mask,
        duration_speed_multiplier=1.0,
    )
    return {k: stats.get(k) for k, _ in CORE_METRICS}


def _fmt(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float) and abs(v - round(v)) > 1e-9:
        return f"{v:.1f}"
    return str(int(round(float(v)))) if isinstance(v, (int, float)) else str(v)


def _signed(v) -> str:
    if v is None:
        return "—"
    sign = "+" if v > 0 else ""
    if isinstance(v, float) and abs(v - round(v)) > 1e-9:
        return f"{sign}{v:.1f}"
    return f"{sign}{int(round(v))}"


def _delta(a, b) -> str:
    if a is None or b is None:
        return "—"
    return _signed(b - a)


def mean_core(rows, mode, wait) -> dict:
    subset = [r for r in rows if r["mode"] == mode and r.get("signal_wait_s") == wait]
    out = {}
    for key, _ in CORE_METRICS:
        vals = [r["core"][key] for r in subset if r["core"].get(key) is not None]
        out[key] = round(mean(vals), 2) if vals else None
    return out


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
        raise RuntimeError("Graph failed to load.")

    live_wait = float(app_mod.SIGNAL_WAIT_SECONDS)
    waits = SIGNAL_WAIT_LIST
    baseline = live_wait if live_wait in waits else waits[0]
    hybrid = 7.5 if 7.5 in waits else waits[-1]
    aggressive = 5.5 if 5.5 in waits else None
    presets = load_preset_weights()
    routes = bac.parse_test_routes()

    print(f"Comparing waits={waits}; presets={list(presets)}; n={len(routes)}\n")

    rows = []
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
        h = make_heuristic(end.anchor_node, G, cost_per_m=1.0)
        t0 = time.perf_counter()
        path, st = pathfinding.astar_unidirectional(
            G,
            start.anchor_node,
            end.anchor_node,
            h,
            app_mod.make_weight_fastest(hours_map, fallback),
        )
        core = path_core(app_mod, path)
        rows.append(
            {
                "route": route["name"],
                "mode": "fastest",
                "signal_wait_s": None,
                "elapsed_s": round(time.perf_counter() - t0, 3),
                "core": core,
            }
        )
        print(f"    fastest: signals={core['signal_count']} len={core['length_m']}")

        ctx = {
            "start": start.anchor_node,
            "end": end.anchor_node,
            "hours_map": hours_map,
            "fallback": fallback,
        }
        for preset, weights in presets.items():
            for wait in waits:
                old = app_mod.SIGNAL_WAIT_SECONDS
                app_mod.SIGNAL_WAIT_SECONDS = float(wait)
                try:
                    scale = compute_lb(weights)
                    hh = make_heuristic(ctx["end"], G, cost_per_m=scale)
                    wf = app_mod.make_weight_optimized(
                        weights, ctx["hours_map"], ctx["fallback"]
                    )
                    t0 = time.perf_counter()
                    path, st = pathfinding.astar_unidirectional(
                        G, ctx["start"], ctx["end"], hh, wf
                    )
                    elapsed = time.perf_counter() - t0
                    core = path_core(app_mod, path, weights)
                finally:
                    app_mod.SIGNAL_WAIT_SECONDS = old
                rows.append(
                    {
                        "route": route["name"],
                        "mode": preset,
                        "signal_wait_s": float(wait),
                        "elapsed_s": round(elapsed, 3),
                        "core": core,
                    }
                )
                print(
                    f"    {preset}@{wait:g}: signals={core['signal_count']} "
                    f"len={core['length_m']} ({elapsed:.1f}s)"
                )

    fastest_mean = mean_core(rows, "fastest", None)
    pivot = {"fastest": fastest_mean}
    for preset in presets:
        by_wait = {w: mean_core(rows, preset, w) for w in waits}
        deltas = {}
        deltas[f"{hybrid:g}_minus_{baseline:g}"] = {
            k: round(by_wait[hybrid][k] - by_wait[baseline][k], 2)
            if by_wait[hybrid][k] is not None and by_wait[baseline][k] is not None
            else None
            for k, _ in CORE_METRICS
        }
        if aggressive is not None:
            deltas[f"{hybrid:g}_minus_{aggressive:g}"] = {
                k: round(by_wait[hybrid][k] - by_wait[aggressive][k], 2)
                if by_wait[hybrid][k] is not None and by_wait[aggressive][k] is not None
                else None
                for k, _ in CORE_METRICS
            }
        pivot[preset] = {"by_wait": by_wait, "deltas": deltas}

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "live_signal_wait_s": live_wait,
        "waits_compared_s": waits,
        "baseline_wait_s": baseline,
        "hybrid_wait_s": hybrid,
        "aggressive_wait_s": aggressive,
        "metres_per_signal_at_w1": {
            str(w): round(w * float(app_mod.CYCLIST_SPEED_MPS), 2) for w in waits
        },
        "preset_signal_weights": {
            k: float(v.get("signal_weight", 0) or 0) for k, v in presets.items()
        },
        "justification": {
            "5.5s": "~11% trip-share calib on 50.5 min cruise / 71.09 signals.",
            "7.5s": "~15% trip-share (NZ study) → ≈7.5s; mid of 9–20% band (~7.2s).",
            "20s": "Live app.SIGNAL_WAIT_SECONDS.",
            "lit_18_19s": "Per intersection (ECF/field), not per graph node.",
        },
        "pivot_mean_core": pivot,
        "rows": rows,
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = [
        "# Signal wait comparison — Fast & Leisure (20 / 5.5 / 7.5)",
        "",
        f"Generated: `{summary['generated_at']}`",
        "",
        "## Setup",
        "",
        f"- Live: `{live_wait}` s · compared: `{waits}`",
        f"- Metres @ w=1: {summary['metres_per_signal_at_w1']}",
        f"- Weights: {summary['preset_signal_weights']}",
        "",
        "### Why 7.5s is justifiable (not forced to 5.5)",
        "",
        "- **5.5s** = aggressive (~11% of trip as signal delay).",
        "- **7.5s** = NZ study ~15% of trip as delay on same baselines; also ≈ mid of your 9–20% band.",
        "- Literature **18–19s** is per intersection, not per graph `signal_count` node.",
        "",
        "## Mean core metrics",
        "",
    ]
    for preset in presets:
        p = pivot[preset]
        dkeys = list(p["deltas"])
        header = "| Metric | Fastest |" + "".join(f" @{w:g}s |" for w in waits)
        header += "".join(f" Δ {dk} |" for dk in dkeys)
        sep = "|--------|--------:|" + "------:|" * len(waits) + "------:|" * len(dkeys)
        lines += [f"### {preset.capitalize()}", "", header, sep]
        for key, label in CORE_METRICS:
            row = f"| {label} | {_fmt(fastest_mean[key])} |"
            for w in waits:
                row += f" {_fmt(p['by_wait'][w][key])} |"
            for dk in dkeys:
                row += f" {_signed(p['deltas'][dk][key])} |"
            lines.append(row)
        lines.append("")

    lines += ["## Per route", ""]
    by_route = {}
    for r in rows:
        by_route.setdefault(r["route"], {})[(r["mode"], r.get("signal_wait_s"))] = r

    for route in routes:
        name = route["name"]
        bucket = by_route[name]
        fast0 = bucket[("fastest", None)]
        lines += [
            f"### {name}",
            "",
            f"Fastest: len={_fmt(fast0['core']['length_m'])} m, "
            f"signals={_fmt(fast0['core']['signal_count'])}",
            "",
        ]
        for preset in presets:
            lines += [f"#### {preset.capitalize()}", ""]
            header = "| Metric |" + "".join(f" @{w:g}s |" for w in waits)
            sep = "|--------|" + "------:|" * len(waits)
            if aggressive is not None:
                header += f" Δ({hybrid:g}−{aggressive:g}) | Δ({hybrid:g}−{baseline:g}) |"
                sep += "------:|------:|"
            else:
                header += f" Δ({hybrid:g}−{baseline:g}) |"
                sep += "------:|"
            lines += [header, sep]
            for key, label in CORE_METRICS:
                vals = {w: bucket[(preset, w)]["core"][key] for w in waits}
                row = f"| {label} |" + "".join(f" {_fmt(vals[w])} |" for w in waits)
                if aggressive is not None:
                    row += f" {_delta(vals[aggressive], vals[hybrid])} |"
                row += f" {_delta(vals[baseline], vals[hybrid])} |"
                lines.append(row)
            lines.append("")

    lines += [
        "## How to read",
        "",
        f"- Δ({hybrid:g}−{baseline:g}): hybrid vs live.",
        f"- Δ({hybrid:g}−{aggressive:g}): hybrid vs aggressive (if present).",
        "",
        f"JSON: `{REPORT_JSON}`",
        "",
    ]
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {REPORT_MD}\nWrote {REPORT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
