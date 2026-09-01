"""Trial cheap GPX matcher + 20 km/h clock on fixture 1 only.

Writes:
  0_documentation/testing/google_compare/r01_imperial_kings_cross/debug_match.html
  0_documentation/testing/google_compare/r01_imperial_kings_cross/debug_speed20.html

  cd C:\\London_Cycle_Maps
  python 4_backend_engine/trial_gpx_match_r01.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("FLASK_USE_RELOADER", "0")
os.environ.setdefault("SKIP_DISRUPTION_FETCH", "1")

from google_gpx_overlay import write_debug_html  # noqa: E402
from gpx_graph_match import (  # noqa: E402
    count_reversals,
    snap_track,
    stitch_edge_follow,
)
from score_google_gpx import (  # noqa: E402
    COMPARE_DIR,
    SAMPLE_SPACING_M,
    SNAP_MAX_M,
    _follow_weight,
    _mock_flask,
    parse_gpx,
    parse_notes,
    notes_float,
    path_to_latlon,
    stitch_anchors,
    subsample,
)


def time_path(app_mod, rte, path, speed_kmh: float) -> dict:
    stats = app_mod.calculate_path_stats(
        path,
        calming_source="both",
        speed_kmh=speed_kmh,
        vf_mask_allowed=None,
        duration_speed_multiplier=1.0,
    )
    vf = {
        "core": float(stats.get("vf_length_core_m") or 0),
        "shared_path": float(stats.get("vf_length_shared_path_m") or 0),
        "bus_lane": float(stats.get("vf_length_bus_lane_m") or 0),
        "painted_lane": float(stats.get("vf_length_painted_lane_m") or 0),
    }
    cruise = rte.cruise_duration_min_with_vf(
        float(stats["length_m"]), speed_kmh, vf
    )
    b = rte.estimate_duration_min_phase_b(
        float(stats["length_m"]),
        speed_kmh,
        signal_count=int(stats.get("signal_count") or 0),
        give_way_count=int(stats.get("give_way_count") or 0),
        stop_sign_count=int(stats.get("stop_sign_count") or 0),
        junction_count=int(stats.get("junction_count") or 0),
        calming_count=int(stats.get("calming_count") or 0),
        barrier_penalty_count=int(stats.get("barrier_penalty_count") or 0),
        elevation_gain=float(stats.get("elevation_gain") or 0),
        vf_lengths_m=vf,
    )
    length_m = float(stats["length_m"])
    implied = (length_m / 1000.0) / (b / 60.0) if b else None
    cruise_needed_16 = (length_m / 1000.0) / 16.0 * 60.0
    moving_for_d2d_16 = None
    penalty_min = b - cruise
    if cruise > 0 and cruise_needed_16 > penalty_min:
        # scale current moving speed so total time hits 16 km/h door-to-door
        # total = cruise * (v_old/v_new) + penalty = length/16*60
        # cruise_new = cruise_needed_16 - penalty
        cruise_new = cruise_needed_16 - penalty_min
        if cruise_new > 0:
            moving_for_d2d_16 = speed_kmh * (cruise / cruise_new)
    return {
        "length_m": round(length_m, 1),
        "signals": int(stats.get("signal_count") or 0),
        "junctions": int(stats.get("junction_count") or 0),
        "barriers": int(stats.get("barrier_penalty_count") or 0),
        "elev_m": float(stats.get("elevation_gain") or 0),
        "cruise_min": round(cruise, 2),
        "penalty_min": round(penalty_min, 2),
        "phase_b_min": round(b, 2),
        "implied_kmh": round(implied, 2) if implied else None,
        "moving_kmh_for_d2d_16": round(moving_for_d2d_16, 1)
        if moving_for_d2d_16
        else None,
        "speed_kmh": speed_kmh,
    }


def fmt_row(label: str, row: dict) -> str:
    return (
        f"{label}: {row['length_m']:.0f} m  cruise {row['cruise_min']:.2f}  "
        f"pen {row['penalty_min']:.2f}  B {row['phase_b_min']:.2f} min  "
        f"d2d {row['implied_kmh']} km/h"
    )


def main() -> int:
    folder = COMPARE_DIR / "r01_imperial_kings_cross"
    gpx_path = folder / "google.gpx"
    if not gpx_path.is_file():
        raise SystemExit(f"Missing {gpx_path}")

    _mock_flask()
    os.chdir(BACKEND_DIR)
    import tfl_live
    import app as app_mod
    import pathfinding
    import route_time_estimate as rte
    import park_opening_hours
    import benchmark_array_costs as bac
    from routing_heuristic import (
        compute_optimized_cost_per_metre_lower_bound as compute_lb,
        make_heuristic,
    )
    from compare_presets_aligned_time import load_presets

    if app_mod.G is None:
        raise RuntimeError("Graph failed to load.")

    gpx = parse_gpx(gpx_path)
    notes = parse_notes(folder / "notes.txt")
    maps_min = notes_float(notes, "google_duration_min") or gpx["advertised_min"]
    maps_km = notes_float(notes, "google_distance_km") or gpx["advertised_km"]
    maps_v = (maps_km / (maps_min / 60.0)) if maps_min and maps_km else None

    sampled = subsample(gpx["points"], SAMPLE_SPACING_M)
    snaps, skipped = snap_track(tfl_live, sampled, SNAP_MAX_M, endpoints_wide=True)
    print(
        f"GPX {gpx['n_trkpt']} pts  geodesic {gpx['geodesic_m']:.0f} m  "
        f"samples {len(sampled)}  snaps {len(snaps)}  skipped {skipped}"
    )

    weight_fn = _follow_weight(app_mod)
    anchors = []
    for s in snaps:
        if not anchors or anchors[-1]["anchor"] != s["anchor"]:
            anchors.append(s)

    old_path, old_legs, old_skip = stitch_anchors(
        app_mod.G, pathfinding, make_heuristic, weight_fn, list(anchors)
    )
    new_path, new_meta = stitch_edge_follow(
        app_mod.G, pathfinding, make_heuristic, weight_fn, snaps
    )
    old_rev = count_reversals(old_path)
    print(
        f"OLD node-A*: nodes {len(old_path)}  len {sum(1 for _ in old_path)}  "
        f"reversals {old_rev}  jump_legs {sum(1 for x in old_legs if x['jump'])}  "
        f"skipped_anchors {old_skip}"
    )
    print(
        f"NEW edge-follow: nodes {new_meta['n_nodes']}  len {new_meta['length_m']} m  "
        f"reversals {new_meta['n_reversals']}  local {new_meta['n_local_legs']}  "
        f"astar {new_meta['n_astar_legs']}  skipped {new_meta['n_skipped']}  "
        f"jumps {new_meta['n_jump_legs']}"
    )

    from gpx_graph_match import path_length_m as glength

    print(f"OLD length {glength(app_mod.G, old_path):.0f} m")

    gpx_ll = [[float(a), float(b)] for a, b in gpx["points"]]
    old_ll = path_to_latlon(app_mod, old_path)
    new_ll = path_to_latlon(app_mod, new_path)

    fixtures = bac.parse_test_routes()
    preset_weights, _ = load_presets()
    print("routing Fast for r01 ...", flush=True)
    start = tfl_live.snap_to_edge(
        fixtures[0]["start_lat"],
        fixtures[0]["start_lon"],
        max_distance_m=tfl_live.SNAP_MAX_DISTANCE_M_ROUTE,
    )
    end = tfl_live.snap_to_edge(
        fixtures[0]["end_lat"],
        fixtures[0]["end_lon"],
        max_distance_m=tfl_live.SNAP_MAX_DISTANCE_M_ROUTE,
    )
    hours_map, fallback = park_opening_hours.build_request_hours_context(
        app_mod.G.graph.get("park_opening_hours_unique") or [],
        park_opening_hours.london_now(),
    )
    wf = app_mod.make_weight_optimized(
        preset_weights["fast"], hours_map, fallback, apply_live=False
    )
    scale = compute_lb(preset_weights["fast"])
    h = make_heuristic(end.anchor_node, app_mod.G, cost_per_m=scale)
    fast_path, _ = pathfinding.astar_unidirectional(
        app_mod.G, start.anchor_node, end.anchor_node, h, wf
    )
    fast_ll = path_to_latlon(app_mod, fast_path)

    google20 = time_path(app_mod, rte, new_path, 20.0)
    google16 = time_path(app_mod, rte, new_path, 16.0)
    fast20 = time_path(app_mod, rte, fast_path, 20.0)
    fast16 = time_path(app_mod, rte, fast_path, 16.0)
    old20 = time_path(app_mod, rte, old_path, 20.0)

    print("Maps UI:", maps_km, "km /", maps_min, "min  implied", round(maps_v, 2) if maps_v else None)
    print(fmt_row("Fast @16", fast16))
    print(fmt_row("Fast @20", fast20))
    print(fmt_row("Google NEW @16", google16))
    print(fmt_row("Google NEW @20", google20))
    print(fmt_row("Google OLD @20", old20))
    print("Fast moving speed that would make d2d = 16 km/h:", fast20["moving_kmh_for_d2d_16"])
    print("Google NEW moving speed that would make d2d = 16 km/h:", google20["moving_kmh_for_d2d_16"])

    write_debug_html(
        folder / "debug_match.html",
        title="r01 matcher trial — GPX vs edge-follow",
        note="Magenta = Maps GPX. Blue = cheap edge-follow match. Grey dashed = old node-A* (off by default).",
        stats=[
            f"GPX geodesic {gpx['geodesic_m']:.0f} m  samples {len(sampled)}  snaps {len(snaps)}",
            f"OLD node-A*: {glength(app_mod.G, old_path):.0f} m  reversals {old_rev}  jumps {sum(1 for x in old_legs if x['jump'])}",
            f"NEW edge-follow: {new_meta['length_m']:.0f} m  reversals {new_meta['n_reversals']}  local {new_meta['n_local_legs']} A* {new_meta['n_astar_legs']} skip {new_meta['n_skipped']}",
        ],
        layers=[
            {
                "name": "Google GPX",
                "color": "#ff0061",
                "weight": 5,
                "pts": gpx_ll,
                "on": True,
            },
            {
                "name": "Matched (edge-follow)",
                "color": "#2563eb",
                "weight": 5,
                "pts": new_ll,
                "on": True,
            },
            {
                "name": "Old node-A* (artefacts)",
                "color": "#6b7280",
                "weight": 4,
                "dash": "7 7",
                "pts": old_ll,
                "on": False,
            },
        ],
    )

    stats_speed = [
        f"Maps UI  {maps_km} km / {maps_min} min  →  {maps_v:.2f} km/h door-to-door" if maps_v else "Maps UI missing",
        fmt_row("Fast  moving 16", fast16),
        fmt_row("Fast  moving 20", fast20),
        fmt_row("Google match  moving 16", google16),
        fmt_row("Google match  moving 20", google20),
        f"To hit 16 km/h door-to-door with this stop table, Fast would need moving {fast20['moving_kmh_for_d2d_16']} km/h.",
        f"Same for matched Google: moving {google20['moving_kmh_for_d2d_16']} km/h.",
        "d2d = length / Phase B. Phase B = Jafari cruise at the moving speed + the usual stop/climb table.",
    ]
    write_debug_html(
        folder / "debug_speed20.html",
        title="r01 clock trial — Fast vs matched Google at 20 km/h",
        note="Orange = Fast. Blue = edge-follow Google. Magenta = Maps GPX. Times in the panel.",
        stats=stats_speed,
        layers=[
            {
                "name": "Google GPX",
                "color": "#ff0061",
                "weight": 5,
                "pts": gpx_ll,
                "on": True,
            },
            {
                "name": "Google matched (edge-follow)",
                "color": "#2563eb",
                "weight": 5,
                "pts": new_ll,
                "on": True,
            },
            {
                "name": "Fast",
                "color": "#f59e0b",
                "weight": 5,
                "pts": fast_ll,
                "on": True,
            },
        ],
    )

    summary = {
        "maps_km": maps_km,
        "maps_min": maps_min,
        "maps_implied_kmh": round(maps_v, 2) if maps_v else None,
        "old_reversals": old_rev,
        "new": new_meta,
        "fast16": fast16,
        "fast20": fast20,
        "google16": google16,
        "google20": google20,
        "old20": old20,
    }
    (folder / "debug_trial.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    print("wrote", folder / "debug_match.html")
    print("wrote", folder / "debug_speed20.html")
    print("wrote", folder / "debug_trial.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
