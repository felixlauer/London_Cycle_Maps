#!/usr/bin/env python3
"""
Canonical Fast / Safe / Leisure compare under *aligned* signal seconds.

Routes with live app.SIGNAL_WAIT_SECONDS, then times with live Phase B:
  Miotti climb + Jafari VF cruise + stop penalties (same as calculate_path_stats).

  cd c:\\London_Cycle_Maps
  python 4_backend_engine/compare_presets_aligned_time.py

Writes (default — dated run folder, same-day re-runs overwrite that day only):
  0_documentation/testing/runs/YYYY-MM-DD/presets_aligned_time_compare_phase_b_live.{md,json}

Previous baseline to diff against (fixed historical file):
  0_documentation/testing/presets_aligned_time_compare.{md,json}

Override output:
  set COMPARE_ALIGNED_OUT=path\\to\\out.md
  set COMPARE_ALIGNED_RUN=YYYY-MM-DD   # pick the run folder date (default: today)
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import types
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "4_backend_engine"
TEST_DIR = REPO_ROOT / "0_documentation" / "testing"
RUNS_DIR = TEST_DIR / "runs"
PRESET_REPORT_STEM = "presets_aligned_time_compare_phase_b_live"
PREV_JSON = TEST_DIR / "presets_aligned_time_compare.json"
WIZARD_JS = REPO_ROOT / "5_frontend" / "src" / "wizard" / "fastSavings.js"

SPEED_KMH = float(os.environ.get("DURATION_SPEED_KMH", "20"))


def resolve_output_paths() -> tuple[Path, Path, Path]:
    """Return (run_dir, report_md, report_json)."""
    override = os.environ.get("COMPARE_ALIGNED_OUT")
    if override:
        md = Path(override)
        if not md.is_absolute():
            md = (REPO_ROOT / md).resolve()
        return md.parent, md, md.with_suffix(".json")
    stamp = os.environ.get("COMPARE_ALIGNED_RUN") or datetime.now().strftime("%Y-%m-%d")
    run_dir = RUNS_DIR / stamp
    md = run_dir / f"{PRESET_REPORT_STEM}.md"
    return run_dir, md, md.with_suffix(".json")

CORE_KEYS = [
    ("length_m", "Length (m)"),
    ("signal_count", "Signals"),
    ("junction_count", "Junctions"),
    ("calming_count", "Calming"),
    ("barrier_penalty_count", "Barriers"),
    ("elevation_gain", "Elev gain (m)"),
    ("steep_count", "Steep segs"),
    ("accidents", "Accidents"),
    ("speed_stress_pct", "Speed stress %"),
    ("vehicular_free_pct", "VF %"),
    ("tfl_cycleway_pct", "TfL cw %"),
    ("tfl_network_pct", "TfL net %"),
    ("green_pct", "Green %"),
    ("illumination_pct", "Lit %"),
    ("give_way_count", "Give-way"),
    ("stop_sign_count", "Stop signs"),
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
    """Prefer user_profiles.json; fall back to preset_config.json."""
    profiles_path = BACKEND_DIR / "user_profiles.json"
    if profiles_path.is_file():
        with open(profiles_path, encoding="utf-8") as f:
            data = json.load(f)
        src = "user_profiles.json"
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
        return out, src

    with open(BACKEND_DIR / "preset_config.json", encoding="utf-8") as f:
        data = json.load(f)
    src = "preset_config.json"
    out = {}
    for label in ("fast", "safe", "leisure"):
        block = data["presets"][label]
        w = dict(block["weights"])
        w["calming_source"] = "both"
        w["bike_type"] = "standard"
        toggles = block.get("toggles") or {}
        vf = toggles.get("vf_infrastructure") or {}
        w["vf_shared_path"] = bool(vf.get("shared_path", True))
        w["vf_bus_lane"] = bool(vf.get("bus_lane", True))
        w["vf_painted_lane"] = bool(vf.get("painted_lane", False))
        out[label] = w
    return out, src


def wizard_signal_seconds() -> float | None:
    if not WIZARD_JS.is_file():
        return None
    text = WIZARD_JS.read_text(encoding="utf-8")
    # Prefer FAST_SECONDS_PER_UNIT block (not FAST_BASELINES.signal_count).
    m = re.search(
        r"FAST_SECONDS_PER_UNIT\s*=\s*\{[^}]*signal_count:\s*([0-9.]+)",
        text,
        re.DOTALL,
    )
    return float(m.group(1)) if m else None


def vf_mask_for(weights: dict):
    from cost_masks import vf_allowed_masks

    return vf_allowed_masks(
        shared_path=bool(weights.get("vf_shared_path", True)),
        bus_lane=bool(weights.get("vf_bus_lane", True)),
        painted_lane=bool(weights.get("vf_painted_lane", False)),
    )[0]


def phase_b_manual(rte, stats: dict) -> dict:
    """Rebuild live Phase B (Miotti climb + Jafari VF) — must match estimate_duration_min_phase_b."""
    length = float(stats["length_m"])
    vf_lengths = {
        "core": float(stats.get("vf_length_core_m") or 0),
        "shared_path": float(stats.get("vf_length_shared_path_m") or 0),
        "bus_lane": float(stats.get("vf_length_bus_lane_m") or 0),
        "painted_lane": float(stats.get("vf_length_painted_lane_m") or 0),
    }
    cruise = rte.cruise_duration_min_with_vf(length, SPEED_KMH, vf_lengths)
    cruise_flat = rte.cruise_duration_min(length, SPEED_KMH, 1.0)
    ps = rte.PENALTY_SECONDS
    climb_rate = float(ps["climb_per_metre"])
    parts = {
        "signal": float(stats.get("signal_count") or 0) * ps["signal"],
        "give_way": float(stats.get("give_way_count") or 0) * ps["give_way"],
        "stop_sign": float(stats.get("stop_sign_count") or 0) * ps["stop_sign"],
        "junction": float(stats.get("junction_count") or 0) * ps["junction"],
        "calming": float(stats.get("calming_count") or 0) * ps["calming"],
        "barrier": float(stats.get("barrier_penalty_count") or 0) * ps["barrier"],
        "climb": float(stats.get("elevation_gain") or 0) * climb_rate,
    }
    penalty_s = sum(parts.values())
    total = cruise + penalty_s / 60.0
    return {
        "cruise_min": round(cruise, 4),
        "cruise_flat_min": round(cruise_flat, 4),
        "vf_save_min": round(cruise_flat - cruise, 4),
        "penalty_s": round(penalty_s, 2),
        "penalty_min": round(penalty_s / 60.0, 4),
        "duration_min": round(total, 4),
        "parts_s": {k: round(v, 2) for k, v in parts.items()},
        "vf_lengths_m": vf_lengths,
    }


def core_from_stats(stats: dict) -> dict:
    return {k: stats.get(k) for k, _ in CORE_KEYS}


def main() -> int:
    run_dir, report_md, report_json = resolve_output_paths()
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

    print(f"Output run folder: {run_dir}", flush=True)

    wait_s = float(app_mod.SIGNAL_WAIT_SECONDS)
    penalty_signal_s = float(rte.PENALTY_SECONDS["signal"])
    wizard_s = wizard_signal_seconds()
    intersection_m = float(app_mod.INTERSECTION_PENALTY_METRES)
    signal_m = wait_s * float(app_mod.CYCLIST_SPEED_MPS)

    alignment = {
        "SIGNAL_WAIT_SECONDS": wait_s,
        "PENALTY_SECONDS.signal": penalty_signal_s,
        "wizard_FAST_SECONDS_PER_UNIT.signal_count": wizard_s,
        "signal_penalty_metres_at_w1": round(signal_m, 4),
        "INTERSECTION_PENALTY_METRES": round(intersection_m, 4),
        "match_wait_eq_penalty": abs(wait_s - penalty_signal_s) < 1e-9,
        "match_wait_eq_wizard": wizard_s is not None and abs(wait_s - wizard_s) < 1e-9,
    }
    if not alignment["match_wait_eq_penalty"]:
        raise SystemExit(
            f"MISALIGNED: SIGNAL_WAIT_SECONDS={wait_s} != "
            f"PENALTY_SECONDS['signal']={penalty_signal_s}"
        )
    if wizard_s is not None and not alignment["match_wait_eq_wizard"]:
        raise SystemExit(
            f"MISALIGNED: SIGNAL_WAIT_SECONDS={wait_s} != wizard signal_count={wizard_s}"
        )

    presets, preset_src = load_presets()
    signal_weights = {k: float(v.get("signal_weight", 0) or 0) for k, v in presets.items()}
    routes = bac.parse_test_routes()

    print(
        f"Aligned time compare @ wait={wait_s}s (= Phase B signal = wizard)\n"
        f"  presets from {preset_src}; signal_weight={signal_weights}\n"
        f"  signal metres@w1={signal_m:.2f}; intersection metres={intersection_m:.2f}\n"
    )

    rows = []
    crosscheck_failures = []

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

        # Fastest baseline (length-only)
        h_fastest = make_heuristic(end.anchor_node, G, cost_per_m=1.0)
        wf_fastest = app_mod.make_weight_fastest(hours_map, fallback)
        path_f, _ = pathfinding.astar_unidirectional(
            G, start.anchor_node, end.anchor_node, h_fastest, wf_fastest
        )
        stats_f = app_mod.calculate_path_stats(
            path_f, calming_source="both", speed_kmh=SPEED_KMH, duration_speed_multiplier=1.0
        )
        manual_f = phase_b_manual(rte, stats_f)
        api_f = rte.estimate_duration_min_phase_b(
            float(stats_f["length_m"]),
            SPEED_KMH,
            signal_count=int(stats_f.get("signal_count") or 0),
            give_way_count=int(stats_f.get("give_way_count") or 0),
            stop_sign_count=int(stats_f.get("stop_sign_count") or 0),
            junction_count=int(stats_f.get("junction_count") or 0),
            calming_count=int(stats_f.get("calming_count") or 0),
            barrier_penalty_count=int(stats_f.get("barrier_penalty_count") or 0),
            elevation_gain=float(stats_f.get("elevation_gain") or 0),
            vf_lengths_m=manual_f["vf_lengths_m"],
        )
        live_f = float(stats_f.get("duration_min") or 0)
        if abs(api_f - manual_f["duration_min"]) > 0.05:
            crosscheck_failures.append(
                ("fastest", route["name"], api_f, manual_f["duration_min"])
            )
        if abs(live_f - manual_f["duration_min"]) > 0.15:
            crosscheck_failures.append(
                ("fastest-live", route["name"], live_f, manual_f["duration_min"])
            )

        by_preset = {
            "fastest": {
                "route": route["name"],
                "preset": "fastest",
                "signal_weight": 0.0,
                "elapsed_s": None,
                "core": core_from_stats(stats_f),
                "cruise_min": round(manual_f["cruise_min"], 2),
                "cruise_flat_min": round(manual_f["cruise_flat_min"], 2),
                "vf_save_min": round(manual_f["vf_save_min"], 2),
                "phase_a_live_min": round(
                    rte.cruise_duration_min(
                        float(stats_f["length_m"]),
                        SPEED_KMH,
                        rte.duration_speed_multiplier_for_preset("fastest"),
                    ),
                    2,
                ),
                "phase_b_min": round(api_f, 2),
                "phase_b_penalty_min": round(manual_f["penalty_min"], 2),
                "phase_b_parts_s": manual_f["parts_s"],
                "vf_lengths_m": manual_f["vf_lengths_m"],
                "stats_duration_min": live_f,
                "phase_b_api_min": round(api_f, 4),
                "phase_b_manual_min": manual_f["duration_min"],
                "phase_b_match": abs(api_f - manual_f["duration_min"]) <= 0.05,
            }
        }

        for preset, weights in presets.items():
            scale = compute_lb(weights)
            h = make_heuristic(end.anchor_node, G, cost_per_m=scale)
            wf = app_mod.make_weight_optimized(weights, hours_map, fallback)
            t0 = time.perf_counter()
            path, _ = pathfinding.astar_unidirectional(
                G, start.anchor_node, end.anchor_node, h, wf
            )
            elapsed = time.perf_counter() - t0
            stats = app_mod.calculate_path_stats(
                path,
                calming_source=weights.get("calming_source") or "both",
                speed_kmh=SPEED_KMH,
                vf_mask_allowed=vf_mask_for(weights),
                duration_speed_multiplier=1.0,
            )
            manual = phase_b_manual(rte, stats)
            api = rte.estimate_duration_min_phase_b(
                float(stats["length_m"]),
                SPEED_KMH,
                signal_count=int(stats.get("signal_count") or 0),
                give_way_count=int(stats.get("give_way_count") or 0),
                stop_sign_count=int(stats.get("stop_sign_count") or 0),
                junction_count=int(stats.get("junction_count") or 0),
                calming_count=int(stats.get("calming_count") or 0),
                barrier_penalty_count=int(stats.get("barrier_penalty_count") or 0),
                elevation_gain=float(stats.get("elevation_gain") or 0),
                vf_lengths_m=manual["vf_lengths_m"],
            )
            live = float(stats.get("duration_min") or 0)
            if abs(api - manual["duration_min"]) > 0.05:
                crosscheck_failures.append((preset, route["name"], api, manual["duration_min"]))
            if abs(live - manual["duration_min"]) > 0.15:
                crosscheck_failures.append((f"{preset}-live", route["name"], live, manual["duration_min"]))

            mult = rte.duration_speed_multiplier_for_preset(preset)
            phase_a = rte.cruise_duration_min(float(stats["length_m"]), SPEED_KMH, mult)
            row = {
                "route": route["name"],
                "preset": preset,
                "signal_weight": float(weights.get("signal_weight") or 0),
                "elapsed_s": round(elapsed, 3),
                "core": core_from_stats(stats),
                "cruise_min": round(manual["cruise_min"], 2),
                "cruise_flat_min": round(manual["cruise_flat_min"], 2),
                "vf_save_min": round(manual["vf_save_min"], 2),
                "phase_a_live_min": round(phase_a, 2),
                "phase_b_min": round(api, 2),
                "phase_b_penalty_min": round(manual["penalty_min"], 2),
                "implied_kmh": round(
                    (float(stats["length_m"]) / 1000.0) / (api / 60.0), 2
                )
                if api
                else None,
                "phase_b_parts_s": manual["parts_s"],
                "vf_lengths_m": manual["vf_lengths_m"],
                "stats_duration_min": live,
                "phase_b_api_min": round(api, 4),
                "phase_b_manual_min": manual["duration_min"],
                "phase_b_match": abs(api - manual["duration_min"]) <= 0.05,
            }
            by_preset[preset] = row
            print(
                f"    {preset}: len={stats['length_m']:.0f} sig={stats['signal_count']} "
                f"elev={stats.get('elevation_gain')}  cruise={row['cruise_min']}  "
                f"B={row['phase_b_min']}  A(live*)={row['phase_a_live_min']}"
            )

        # Head-to-head Fast vs Safe (and vs Leisure)
        f, s, L = by_preset["fast"], by_preset["safe"], by_preset["leisure"]
        h2h = {
            "fast_leq_safe_phase_b": f["phase_b_min"] <= s["phase_b_min"],
            "fast_leq_safe_cruise": f["cruise_min"] <= s["cruise_min"],
            "fast_leq_leisure_phase_b": f["phase_b_min"] <= L["phase_b_min"],
            "delta_phase_b_fast_minus_safe": round(f["phase_b_min"] - s["phase_b_min"], 2),
            "delta_cruise_fast_minus_safe": round(f["cruise_min"] - s["cruise_min"], 2),
            "delta_len_fast_minus_safe": round(
                float(f["core"]["length_m"]) - float(s["core"]["length_m"]), 1
            ),
            "delta_sig_fast_minus_safe": int(f["core"]["signal_count"] or 0)
            - int(s["core"]["signal_count"] or 0),
            "delta_elev_fast_minus_safe": round(
                float(f["core"].get("elevation_gain") or 0)
                - float(s["core"].get("elevation_gain") or 0),
                1,
            ),
            "delta_vf_fast_minus_safe": round(
                float(f["core"].get("vehicular_free_pct") or 0)
                - float(s["core"].get("vehicular_free_pct") or 0),
                1,
            ),
            "why_fast_slower_if_any": None,
        }
        if not h2h["fast_leq_safe_phase_b"]:
            reasons = []
            if h2h["delta_len_fast_minus_safe"] > 50:
                reasons.append(
                    f"longer path (+{h2h['delta_len_fast_minus_safe']:.0f} m → "
                    f"+{h2h['delta_cruise_fast_minus_safe']:.1f} min cruise)"
                )
            # Signal saving vs cruise cost
            sig_save_min = (-h2h["delta_sig_fast_minus_safe"]) * wait_s / 60.0
            if h2h["delta_sig_fast_minus_safe"] < 0:
                reasons.append(
                    f"fewer signals ({h2h['delta_sig_fast_minus_safe']:+d} → "
                    f"~{sig_save_min:.1f} min saved @ {wait_s}s) but not enough "
                    f"to offset other costs"
                )
            climb_delta_min = h2h["delta_elev_fast_minus_safe"] * rte.PENALTY_SECONDS[
                "climb_per_metre"
            ] / 60.0
            if abs(climb_delta_min) > 0.2:
                reasons.append(f"climb Δ → {climb_delta_min:+.1f} min")
            # Penalty part deltas
            for key in ("junction", "calming", "barrier", "give_way", "stop_sign"):
                df = f["phase_b_parts_s"].get(key, 0) - s["phase_b_parts_s"].get(key, 0)
                if abs(df) > 30:
                    reasons.append(f"{key} penalty Δ {df:+.0f}s")
            if not reasons:
                reasons.append("Phase B sum of penalties outweighs Fast’s signal win")
            h2h["why_fast_slower_if_any"] = "; ".join(reasons)

        for preset in ("fastest", "fast", "safe", "leisure"):
            row = dict(by_preset[preset])
            if preset != "fastest":
                row["h2h_fast_vs_safe"] = h2h
            rows.append(row)

        tag = "OK" if h2h["fast_leq_safe_phase_b"] else "FAIL"
        print(
            f"    Fast<=Safe B? {tag}  dB={h2h['delta_phase_b_fast_minus_safe']:+}  "
            f"dlen={h2h['delta_len_fast_minus_safe']:+.0f}  "
            f"dsig={h2h['delta_sig_fast_minus_safe']:+d}  "
            f"delev={h2h['delta_elev_fast_minus_safe']:+.0f}"
        )
        if h2h["why_fast_slower_if_any"]:
            print(f"      why: {h2h['why_fast_slower_if_any']}")

    if crosscheck_failures:
        raise SystemExit(f"Phase B API≠manual on {crosscheck_failures}")

    # Means + win counts
    def mean_core(preset: str, key: str):
        vals = [
            float(r["core"][key])
            for r in rows
            if r["preset"] == preset and r["core"].get(key) is not None
        ]
        return round(mean(vals), 2) if vals else None

    def mean_field(preset: str, field: str):
        vals = [float(r[field]) for r in rows if r["preset"] == preset and r.get(field) is not None]
        return round(mean(vals), 2) if vals else None

    pivot = {}
    for preset in ("fastest", "fast", "safe", "leisure"):
        pivot[preset] = {
            "signal_weight": signal_weights.get(preset, 0.0),
            "mean_length_m": mean_core(preset, "length_m"),
            "mean_signals": mean_core(preset, "signal_count"),
            "mean_elev_m": mean_core(preset, "elevation_gain"),
            "mean_vf_pct": mean_core(preset, "vehicular_free_pct"),
            "mean_accidents": mean_core(preset, "accidents"),
            "mean_cruise_min": mean_field(preset, "cruise_min"),
            "mean_phase_a_live_min": mean_field(preset, "phase_a_live_min"),
            "mean_phase_b_min": mean_field(preset, "phase_b_min"),
            "mean_phase_b_penalty_min": mean_field(preset, "phase_b_penalty_min"),
        }

    route_names = sorted({r["route"] for r in rows})
    wins_b = 0
    wins_cruise = 0
    fail_details = []
    for route in route_names:
        by = {r["preset"]: r for r in rows if r["route"] == route}
        if by["fast"]["phase_b_min"] <= by["safe"]["phase_b_min"]:
            wins_b += 1
        else:
            fail_details.append(
                {
                    "route": route,
                    **by["fast"]["h2h_fast_vs_safe"],
                    "fast_core": by["fast"]["core"],
                    "safe_core": by["safe"]["core"],
                    "fast_phase_b": by["fast"]["phase_b_min"],
                    "safe_phase_b": by["safe"]["phase_b_min"],
                    "fast_parts_s": by["fast"]["phase_b_parts_s"],
                    "safe_parts_s": by["safe"]["phase_b_parts_s"],
                }
            )
        if by["fast"]["cruise_min"] <= by["safe"]["cruise_min"]:
            wins_cruise += 1

    pivot["fast"]["fast_leq_safe_phase_b"] = f"{wins_b}/{len(route_names)}"
    pivot["fast"]["fast_leq_safe_cruise"] = f"{wins_cruise}/{len(route_names)}"
    pivot["fast"]["target_phase_b"] = "≥8/11"

    vs_previous = None
    if PREV_JSON.is_file():
        prev = json.loads(PREV_JSON.read_text(encoding="utf-8"))
        prev_pivot = prev.get("pivot") or {}
        vs_previous = {
            "previous_file": str(PREV_JSON),
            "previous_generated_at": prev.get("generated_at"),
            "mean_phase_b_delta": {},
            "fast_leq_safe_previous": (prev_pivot.get("fast") or {}).get(
                "fast_leq_safe_phase_b"
            ),
            "fast_leq_safe_now": pivot["fast"]["fast_leq_safe_phase_b"],
            "note": (
                "Previous run used climb 1.0 s/m and flat cruise (no Jafari VF). "
                "This run uses Miotti climb + Jafari VF (live Phase B)."
            ),
        }
        for preset in ("fastest", "fast", "safe", "leisure"):
            old = (prev_pivot.get(preset) or {}).get("mean_phase_b_min")
            new = (pivot.get(preset) or {}).get("mean_phase_b_min")
            if old is not None and new is not None:
                vs_previous["mean_phase_b_delta"][preset] = {
                    "previous": old,
                    "now": new,
                    "delta": round(new - old, 2),
                }

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "speed_kmh": SPEED_KMH,
        "preset_source": preset_src,
        "alignment": alignment,
        "phase_b": {
            "climb_s_per_m": rte.PENALTY_SECONDS["climb_per_metre"],
            "jafari_vf": True,
            "route_time_model": rte.route_time_model(),
        },
        "note": (
            "Paths routed at live SIGNAL_WAIT_SECONDS; ETA = live Phase B "
            "(Miotti climb + Jafari VF cruise + stop penalties)."
        ),
        "vs_previous": vs_previous,
        "pivot": pivot,
        "fast_vs_safe_fails": fail_details,
        "rows": rows,
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # Markdown
    lines = [
        "# Presets aligned time compare — live Phase B (Miotti + Jafari VF)",
        "",
        f"Generated: `{summary['generated_at']}`",
        "",
        f"Run folder: `{run_dir}`",
        "",
        f"Climb: **{rte.PENALTY_SECONDS['climb_per_metre']} s/m** · "
        f"`ROUTE_TIME_MODEL={rte.route_time_model()}` · Jafari VF cruise **on**",
        "",
        f"Baseline to diff: `{PREV_JSON.name}` (climb 1.0, no VF uplift)",
        "",
    ]
    if vs_previous:
        lines += [
            "## vs previous baseline (mean Phase B)",
            "",
            "| Preset | Previous B | Now B | Δ |",
            "|--------|----------:|------:|--:|",
        ]
        for preset, d in vs_previous["mean_phase_b_delta"].items():
            lines.append(
                f"| {preset} | {d['previous']} | {d['now']} | {d['delta']:+} |"
            )
        lines += [
            "",
            f"Fast<=Safe: was **{vs_previous['fast_leq_safe_previous']}** -> "
            f"now **{vs_previous['fast_leq_safe_now']}**",
            "",
            vs_previous["note"],
            "",
        ]
    lines += [
        "## Alignment cross-check",
        "",
        "| Constant | Value |",
        "|----------|------:|",
        f"| `SIGNAL_WAIT_SECONDS` | {wait_s} |",
        f"| `PENALTY_SECONDS['signal']` | {penalty_signal_s} |",
        f"| wizard `signal_count` seconds | {wizard_s} |",
        f"| Signal metres @ weight=1 | {signal_m:.2f} |",
        f"| `INTERSECTION_PENALTY_METRES` (1/2 signal) | {intersection_m:.2f} |",
        f"| Wait == Penalty == Wizard | "
        f"{'YES' if alignment['match_wait_eq_penalty'] and alignment['match_wait_eq_wizard'] else 'NO'} |",
        "",
        f"Preset source: `{preset_src}` · signal_weight Fast/Safe/Leisure = "
        f"{signal_weights['fast']} / {signal_weights['safe']} / {signal_weights['leisure']}",
        "",
        "> Safe `signal_weight` ~ 0 → changing wait barely moves Safe *via signals*, "
        "but `INTERSECTION_PENALTY_METRES` still scales with wait and Safe's "
        "`junction_weight` is high.",
        "",
        "## Mean metrics + times",
        "",
        "| Preset | Len (m) | Sig | Elev | VF% | Acc | Cruise | Phase A* | Phase B |",
        "|--------|--------:|----:|-----:|----:|----:|-------:|---------:|--------:|",
    ]
    for preset in ("fastest", "fast", "safe", "leisure"):
        p = pivot[preset]
        lines.append(
            f"| {preset} | {p['mean_length_m']} | {p['mean_signals']} | {p['mean_elev_m']} | "
            f"{p['mean_vf_pct']} | {p['mean_accidents']} | {p['mean_cruise_min']} | "
            f"{p['mean_phase_a_live_min']} | **{p['mean_phase_b_min']}** |"
        )
    lines += [
        "",
        f"**Fast ≤ Safe (Phase B):** {wins_b}/{len(route_names)} "
        f"(target ≥8/11) · **Fast ≤ Safe (cruise only):** {wins_cruise}/{len(route_names)}",
        "",
        "## Per route — Fast vs Safe",
        "",
        "| Route | Fast len/sig/elev | Safe len/sig/elev | Fast B | Safe B | ΔB | Δlen | Δsig | Winner |",
        "|-------|------------------:|------------------:|-------:|-------:|---:|-----:|-----:|--------|",
    ]
    for route in route_names:
        by = {r["preset"]: r for r in rows if r["route"] == route}
        f, s = by["fast"], by["safe"]
        h2h = f["h2h_fast_vs_safe"]
        winner = "Fast" if h2h["fast_leq_safe_phase_b"] else "Safe"
        lines.append(
            f"| {route} | {f['core']['length_m']:.0f}/{f['core']['signal_count']}/"
            f"{f['core'].get('elevation_gain')} | "
            f"{s['core']['length_m']:.0f}/{s['core']['signal_count']}/"
            f"{s['core'].get('elevation_gain')} | "
            f"{f['phase_b_min']} | {s['phase_b_min']} | "
            f"{h2h['delta_phase_b_fast_minus_safe']:+} | "
            f"{h2h['delta_len_fast_minus_safe']:+.0f} | "
            f"{h2h['delta_sig_fast_minus_safe']:+d} | {winner} |"
        )

    if fail_details:
        lines += ["", "## Why Fast loses (Phase B)", ""]
        for fd in fail_details:
            lines.append(f"### {fd['route']}")
            lines.append("")
            lines.append(f"- {fd['why_fast_slower_if_any']}")
            lines.append(
                f"- Fast B={fd['fast_phase_b']} vs Safe B={fd['safe_phase_b']} "
                f"(Δ {fd['delta_phase_b_fast_minus_safe']:+} min)"
            )
            lines.append(
                f"- Cruise Δ {fd['delta_cruise_fast_minus_safe']:+} · "
                f"len Δ {fd['delta_len_fast_minus_safe']:+.0f} m · "
                f"sig Δ {fd['delta_sig_fast_minus_safe']:+d} · "
                f"elev Δ {fd['delta_elev_fast_minus_safe']:+.0f} m · "
                f"VF Δ {fd['delta_vf_fast_minus_safe']:+.1f} pp"
            )
            lines.append("")

    lines += [
        "## How to read",
        "",
        "- **Cruise** = length / 20 km/h (no Fast 1.35×).",
        "- **Phase A×** = live display (Fast still ×1.35) — shown only for contrast.",
        "- **Phase B** = cruise + metric×`PENALTY_SECONDS` (canonical ETA under alignment).",
        "- Fast is *not* length-shortest; it trades distance for fewer signals/calming/climb. "
        "If the detour costs more cruise minutes than the signal seconds save, Fast loses on B.",
        "",
        f"JSON: `{report_json}`",
        "",
    ]
    report_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {report_md}")
    print(f"Wrote {report_json}")
    print(
        f"Fast<=Safe Phase B: {wins_b}/{len(route_names)}  "
        f"cruise: {wins_cruise}/{len(route_names)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
