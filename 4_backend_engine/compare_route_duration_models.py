#!/usr/bin/env python3
"""
Compare displayed ride-time models on the 11 test routes × Fast/Safe/Leisure.

Models (stats/display only — does not change A*):

  Phase A (live today)
    cruise_min = length / (speed_kmh/3.6) / 60
    Fast additionally uses 1.35× effective cruise speed
    (see route_time_estimate.duration_speed_multiplier_for_preset)

  Phase A cruise-only
    Same cruise without the Fast 1.35× hack

  Phase B (metric / planned — route_time_phase_b.md)
    cruise_min (no multiplier) + Σ (core_count × PENALTY_SECONDS) / 60
    Signal seconds default from route_time_estimate.PENALTY_SECONDS['signal']
    Optional override: PHASE_B_SIGNAL_S=7.5

  Straight metric delay share
    penalty_min / phase_b_total  (how much of Phase B time is stops/hills)

Doc: 0_documentation/tasks/route_time_phase_b.md
Code: 4_backend_engine/route_time_estimate.py

Run:

  cd c:\\London_Cycle_Maps
  python 4_backend_engine/compare_route_duration_models.py

Writes:
  0_documentation/testing/route_duration_models_compare.md
  0_documentation/testing/route_duration_models_compare.json
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
REPORT_MD = REPORT_DIR / "route_duration_models_compare.md"
REPORT_JSON = REPORT_DIR / "route_duration_models_compare.json"

SPEED_KMH = float(os.environ.get("DURATION_SPEED_KMH", "16"))
# Phase B signal seconds to evaluate (comma list). Default: aggressive + hybrid.
PHASE_B_SIGNAL_LIST = [
    float(x.strip())
    for x in os.environ.get("PHASE_B_SIGNAL_LIST", "5.5,7.5").split(",")
    if x.strip()
]

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


def load_presets() -> dict[str, dict]:
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


def vf_mask_for(weights: dict):
    from cost_masks import vf_allowed_masks

    return vf_allowed_masks(
        shared_path=bool(weights.get("vf_shared_path", True)),
        bus_lane=bool(weights.get("vf_bus_lane", True)),
        painted_lane=bool(weights.get("vf_painted_lane", False)),
    )[0]


def phase_b_from_stats(rte, stats: dict, signal_s: float) -> dict:
    """Cruise + metric penalties; returns breakdown."""
    length = float(stats["length_m"])
    cruise = rte.cruise_duration_min(length, SPEED_KMH, 1.0)
    parts = {
        "signal": float(stats.get("signal_count") or 0) * signal_s,
        "give_way": float(stats.get("give_way_count") or 0) * rte.PENALTY_SECONDS["give_way"],
        "stop_sign": float(stats.get("stop_sign_count") or 0) * rte.PENALTY_SECONDS["stop_sign"],
        "junction": float(stats.get("junction_count") or 0) * rte.PENALTY_SECONDS["junction"],
        "calming": float(stats.get("calming_count") or 0) * rte.PENALTY_SECONDS["calming"],
        "barrier": float(stats.get("barrier_penalty_count") or 0) * rte.PENALTY_SECONDS["barrier"],
        "climb": float(stats.get("elevation_gain") or 0) * rte.PENALTY_SECONDS["climb_per_metre"],
    }
    penalty_s = sum(parts.values())
    total = cruise + penalty_s / 60.0
    return {
        "cruise_min": round(cruise, 2),
        "penalty_s": round(penalty_s, 1),
        "penalty_min": round(penalty_s / 60.0, 2),
        "duration_min": round(total, 2),
        "penalty_share_of_total": round((penalty_s / 60.0) / total, 3) if total > 0 else 0.0,
        "penalty_parts_s": {k: round(v, 1) for k, v in parts.items()},
    }


def main() -> int:
    _mock_flask()
    os.chdir(BACKEND_DIR)
    import benchmark_array_costs as bac
    import park_opening_hours
    import tfl_live
    import app as app_mod
    import pathfinding
    import route_time_estimate as rte
    from routing_heuristic import (
        compute_optimized_cost_per_metre_lower_bound as compute_lb,
        make_heuristic,
    )

    G = app_mod.G
    if G is None:
        raise RuntimeError("Graph failed to load.")

    signal_s_list = PHASE_B_SIGNAL_LIST
    presets = load_presets()
    routes = bac.parse_test_routes()

    print(
        f"Duration models: speed={SPEED_KMH} km/h, Phase-B signal={signal_s_list}s, "
        f"Fast×={rte.FAST_PRESET_DURATION_SPEED_MULTIPLIER}\n"
    )

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

        for preset, weights in presets.items():
            scale = compute_lb(weights)
            h = make_heuristic(end.anchor_node, G, cost_per_m=scale)
            wf = app_mod.make_weight_optimized(weights, hours_map, fallback)
            t0 = time.perf_counter()
            path, _ = pathfinding.astar_unidirectional(
                G, start.anchor_node, end.anchor_node, h, wf
            )
            elapsed = time.perf_counter() - t0

            vf_mask = vf_mask_for(weights)
            stats = app_mod.calculate_path_stats(
                path,
                calming_source=weights.get("calming_source") or "both",
                speed_kmh=SPEED_KMH,
                vf_mask_allowed=vf_mask,
                duration_speed_multiplier=1.0,
            )
            length = float(stats["length_m"])
            mult = rte.duration_speed_multiplier_for_preset(preset)
            phase_a = rte.cruise_duration_min(length, SPEED_KMH, mult)
            cruise_only = rte.cruise_duration_min(length, SPEED_KMH, 1.0)
            phase_b_by_signal = {
                str(sig_s): phase_b_from_stats(rte, stats, sig_s)
                for sig_s in PHASE_B_SIGNAL_LIST
            }
            # Primary hybrid column (7.5 if present else first)
            primary_s = 7.5 if 7.5 in PHASE_B_SIGNAL_LIST else PHASE_B_SIGNAL_LIST[0]
            phase_b = phase_b_by_signal[str(primary_s)]

            row = {
                "route": route["name"],
                "preset": preset,
                "elapsed_s": round(elapsed, 3),
                "length_m": length,
                "signal_count": stats["signal_count"],
                "junction_count": stats["junction_count"],
                "calming_count": stats["calming_count"],
                "elevation_gain": stats["elevation_gain"],
                "phase_a_live_min": round(phase_a, 2),
                "phase_a_multiplier": mult,
                "cruise_only_min": round(cruise_only, 2),
                "phase_b_primary_signal_s": primary_s,
                "phase_b_min": phase_b["duration_min"],
                "phase_b_cruise_min": phase_b["cruise_min"],
                "phase_b_penalty_min": phase_b["penalty_min"],
                "phase_b_penalty_share": phase_b["penalty_share_of_total"],
                "phase_b_parts_s": phase_b["penalty_parts_s"],
                "phase_b_by_signal_s": {
                    k: {
                        "duration_min": v["duration_min"],
                        "penalty_min": v["penalty_min"],
                        "penalty_share": v["penalty_share_of_total"],
                    }
                    for k, v in phase_b_by_signal.items()
                },
                "delta_b_minus_a_live": round(phase_b["duration_min"] - phase_a, 2),
                "delta_b_minus_cruise": round(phase_b["duration_min"] - cruise_only, 2),
            }
            rows.append(row)
            b55 = phase_b_by_signal.get("5.5", {}).get("duration_min")
            b75 = phase_b_by_signal.get("7.5", {}).get("duration_min")
            print(
                f"    {preset}: A={row['phase_a_live_min']}  cruise={row['cruise_only_min']}  "
                f"B@5.5={b55}  B@7.5={b75}  (ΔB7.5−A={row['delta_b_minus_a_live']:+})"
            )

    # pivots
    def mean_for(preset, field):
        vals = [r[field] for r in rows if r["preset"] == preset]
        return round(mean(vals), 2) if vals else None

    pivot = {}
    for preset in ("fast", "safe", "leisure"):
        pivot[preset] = {
            "mean_phase_a_live_min": mean_for(preset, "phase_a_live_min"),
            "mean_cruise_only_min": mean_for(preset, "cruise_only_min"),
            "mean_phase_b_min": mean_for(preset, "phase_b_min"),
            "mean_delta_b_minus_a": mean_for(preset, "delta_b_minus_a_live"),
            "mean_penalty_share": mean_for(preset, "phase_b_penalty_share"),
            "fast_leq_safe_phase_b_count": None,
        }

    # Validation: Fast ≤ Safe under Phase B @7.5 (or primary)
    primary_s = 7.5 if 7.5 in PHASE_B_SIGNAL_LIST else PHASE_B_SIGNAL_LIST[0]
    wins = 0
    for route in {r["route"] for r in rows}:
        by = {r["preset"]: r for r in rows if r["route"] == route}
        bf = by["fast"]["phase_b_by_signal_s"][str(primary_s)]["duration_min"]
        bs = by["safe"]["phase_b_by_signal_s"][str(primary_s)]["duration_min"]
        if bf <= bs:
            wins += 1
    pivot["fast"]["fast_leq_safe_phase_b_count"] = wins
    pivot["fast"]["fast_leq_safe_at_signal_s"] = primary_s

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "speed_kmh": SPEED_KMH,
        "phase_b_signal_s_list": PHASE_B_SIGNAL_LIST,
        "phase_b_primary_signal_s": primary_s,
        "phase_a_fast_multiplier": rte.FAST_PRESET_DURATION_SPEED_MULTIPLIER,
        "penalty_seconds": dict(rte.PENALTY_SECONDS),
        "doc": "0_documentation/tasks/route_time_phase_b.md",
        "pivot": pivot,
        "rows": rows,
        "rewrite_proposal": {
            "replace": "Phase A Fast 1.35× cruise hack",
            "with": "Phase B cruise + explicit metric penalties (same counters as cost fn)",
            "signal_seconds_candidates": {
                "5.5": "11% trip-share calib (aggressive)",
                "7.5": "15% NZ delay share / hybrid (recommended trial)",
                "align_routing": "Also set app.SIGNAL_WAIT_SECONDS to the same value so A* and display agree",
            },
            "wiring": [
                "calculate_path_stats calls estimate_duration_min_phase_b when ROUTE_TIME_MODEL=penalties",
                "Drop Fast 1.35× when Phase B is default",
                "Re-sweep signal_weight after changing SIGNAL_WAIT_SECONDS so wizard anchors match",
            ],
        },
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = [
        "# Route duration models — Phase A vs Phase B (metric)",
        "",
        f"Generated: `{summary['generated_at']}`",
        "",
        "## Models",
        "",
        f"- **Phase A live**: cruise at {SPEED_KMH} km/h; Fast ×{rte.FAST_PRESET_DURATION_SPEED_MULTIPLIER}",
        "- **Cruise only**: length / speed, no Fast multiplier",
        f"- **Phase B (metric)**: cruise + penalties; signal seconds tried: **{PHASE_B_SIGNAL_LIST}**",
        f"- Primary B column / Δ uses **{primary_s}s**/signal",
        "",
        f"Spec: [`route_time_phase_b.md`](../tasks/route_time_phase_b.md)",
        "",
        "## Mean over 11 routes",
        "",
        "| Preset | Phase A (live) | Cruise only | Phase B @5.5 | Phase B @7.5 | Δ(B primary − A) |",
        "|--------|---------------:|------------:|-------------:|-------------:|-----------------:|",
    ]
    for preset in ("fast", "safe", "leisure"):
        subset = [r for r in rows if r["preset"] == preset]
        a = round(mean(r["phase_a_live_min"] for r in subset), 2)
        c = round(mean(r["cruise_only_min"] for r in subset), 2)
        has55 = "5.5" in subset[0]["phase_b_by_signal_s"]
        has75 = "7.5" in subset[0]["phase_b_by_signal_s"]
        b55 = (
            round(mean(r["phase_b_by_signal_s"]["5.5"]["duration_min"] for r in subset), 2)
            if has55
            else "—"
        )
        b75 = (
            round(mean(r["phase_b_by_signal_s"]["7.5"]["duration_min"] for r in subset), 2)
            if has75
            else "—"
        )
        d = round(
            mean(
                r["phase_b_by_signal_s"][str(primary_s)]["duration_min"] - r["phase_a_live_min"]
                for r in subset
            ),
            2,
        )
        lines.append(f"| {preset} | {a} | {c} | {b55} | {b75} | {d:+} |")

    lines += [
        "",
        f"**Phase B @{primary_s}s validation:** Fast ≤ Safe on **{wins}/11** routes (target ≥8/11).",
        "",
        "## Per route",
        "",
        "| Route | Preset | Len | Sig | A live | Cruise | B@5.5 | B@7.5 | Δ(B primary−A) |",
        "|-------|--------|----:|----:|-------:|-------:|------:|------:|---------------:|",
    ]
    for r in rows:
        b55 = r["phase_b_by_signal_s"].get("5.5", {}).get("duration_min", "—")
        b75 = r["phase_b_by_signal_s"].get("7.5", {}).get("duration_min", "—")
        primary = r["phase_b_by_signal_s"][str(primary_s)]["duration_min"]
        lines.append(
            f"| {r['route']} | {r['preset']} | {r['length_m']:.0f} | {r['signal_count']} | "
            f"{r['phase_a_live_min']} | {r['cruise_only_min']} | {b55} | {b75} | "
            f"{primary - r['phase_a_live_min']:+.2f} |"
        )

    lines += [
        "",
        "## Rewrite proposal (display time)",
        "",
        "1. Keep A* weights separate from display time.",
        "2. Replace Fast **1.35×** with **Phase B**: `cruise + Σ metric×seconds`.",
        "3. Trial **7.5 s/signal** in `PENALTY_SECONDS`; align `app.SIGNAL_WAIT_SECONDS`.",
        "4. Gate with `ROUTE_TIME_MODEL=penalties`, then flip default after this compare.",
        "5. Re-sweep `signal_weight` after changing live wait so wizard anchors stay honest.",
        "",
        f"JSON: `{REPORT_JSON}`",
        "",
    ]
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {REPORT_MD}\nWrote {REPORT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
