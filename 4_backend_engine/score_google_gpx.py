#!/usr/bin/env python3
"""
Score a Google Maps cycling GPX on the local graph and compare to the live
preset scoreboard (Phase B: Miotti climb + Jafari VF + stop table).

Drop files under 0_documentation/testing/google_compare/rNN_*/ (not the thesis
repo). Each folder: google.gpx, optional maps_ui.png, notes.txt.

  cd C:\\London_Cycle_Maps
  python 4_backend_engine/score_google_gpx.py --init
  python 4_backend_engine/score_google_gpx.py              # every folder with a GPX
  python 4_backend_engine/score_google_gpx.py --route 1
  python 4_backend_engine/score_google_gpx.py --gpx path\\to\\r1.gpx --route 1

Writes (default — dated run folder, same-day re-runs overwrite that day only):
  0_documentation/testing/runs/YYYY-MM-DD/google_gpx_score.{md,json}
  0_documentation/testing/runs/YYYY-MM-DD/overlays/rNN_*.html

Preset metrics are loaded from (in order):
  PRESET_JSON / GOOGLE_PRESET_JSON env, else same-day run folder, else newest
  dated run that has presets_aligned_time_compare_phase_b_live.json, else the
  legacy testing/ root file.

Override:
  set GOOGLE_SCORE_OUT=path\\to\\out.md
  set GOOGLE_SCORE_RUN=YYYY-MM-DD
  set PRESET_JSON=path\\to\\presets_....json

Snaps subsampled track points, stitches with length-only A* (parks open, live
closures off), then calculate_path_stats + live Phase B. Fast/Safe/Leisure are
re-routed only to draw overlay.html.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import types
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from google_gpx_overlay import write_overlay_html

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "4_backend_engine"
TEST_DIR = REPO_ROOT / "0_documentation" / "testing"
RUNS_DIR = TEST_DIR / "runs"
COMPARE_DIR = TEST_DIR / "google_compare"
PRESET_REPORT_STEM = "presets_aligned_time_compare_phase_b_live"
GOOGLE_SCORE_STEM = "google_gpx_score"

SPEED_KMH = float(os.environ.get("DURATION_SPEED_KMH", "20"))
SAMPLE_SPACING_M = float(os.environ.get("GOOGLE_SAMPLE_SPACING_M", "60"))
SNAP_MAX_M = float(os.environ.get("GOOGLE_SNAP_MAX_M", "80"))
JUMP_RATIO = float(os.environ.get("GOOGLE_JUMP_RATIO", "2.5"))
JUMP_EXTRA_M = float(os.environ.get("GOOGLE_JUMP_EXTRA_M", "250"))


def _abs_under_repo(path: Path | str) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = (REPO_ROOT / p).resolve()
    return p


def resolve_run_dir() -> Path:
    stamp = os.environ.get("GOOGLE_SCORE_RUN") or datetime.now().strftime("%Y-%m-%d")
    return RUNS_DIR / stamp


def resolve_output_paths(run_dir: Path | None = None) -> tuple[Path, Path, Path]:
    """Return (run_dir, report_md, report_json)."""
    override = os.environ.get("GOOGLE_SCORE_OUT")
    if override:
        md = _abs_under_repo(override)
        return md.parent, md, md.with_suffix(".json")
    run_dir = run_dir or resolve_run_dir()
    md = run_dir / f"{GOOGLE_SCORE_STEM}.md"
    return run_dir, md, md.with_suffix(".json")


def find_preset_json(preferred_run_dir: Path) -> Path:
    """Locate the Fast/Safe/Leisure scoreboard JSON for this Google run."""
    env = os.environ.get("PRESET_JSON") or os.environ.get("GOOGLE_PRESET_JSON")
    if env:
        return _abs_under_repo(env)

    same_day = preferred_run_dir / f"{PRESET_REPORT_STEM}.json"
    if same_day.is_file():
        return same_day

    if RUNS_DIR.is_dir():
        dated = sorted(
            RUNS_DIR.glob(f"*/{PRESET_REPORT_STEM}.json"),
            key=lambda p: p.parent.name,
            reverse=True,
        )
        if dated:
            return dated[0]

    return TEST_DIR / f"{PRESET_REPORT_STEM}.json"

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

# Numbered folders next to test_routes.txt. Paste google.gpx + maps_ui.png in each.
ROUTE_FOLDERS: list[tuple[int, str, str]] = [
    (1, "r01_imperial_kings_cross", "Imperial to Kings Cross"),
    (2, "r02_imperial_greenwich", "Imperial to Greenwich"),
    (3, "r03_imperial_spitalfields", "Imperial to New Spitalfields Market"),
    (4, "r04_twickenham_st_pauls", "Twickenham Stadium to St. Pauls"),
    (5, "r05_wembley_kch", "Wembley Stadium to Kings College Hospital"),
    (6, "r06_battersea_temple", "Battersea Park to Temple"),
    (7, "r07_putney_notting_hill", "Putney bridge to Notting Hill"),
    (8, "r08_tottenham_hampstead", "Tottenham Stadium to Hampstead"),
    (9, "r09_earls_court_piccadilly", "Earls court to Piccadilly"),
    (10, "r10_bromley_ealing", "Bromley to Ealing"),
    (11, "r11_elmers_end_streatham", "Hill route, Elmers End to Streatham"),
]

NOTES_TEMPLATE = """# Google Maps cycling UI capture
# Drop google.gpx and maps_ui.png in this folder, then fill advertised stats
# if the GPX description does not already contain Distance / Duration.

google_duration_min:
google_distance_km:
logged_in: unknown
captured_utc:
via:
source: Google Maps cycling UI via GPX2Maps
notes:
"""

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


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def geodesic_length_m(pts: list[tuple[float, float]]) -> float:
    return sum(
        haversine_m(a[0], a[1], b[0], b[1]) for a, b in zip(pts, pts[1:])
    )


def subsample(pts: list[tuple[float, float]], spacing_m: float) -> list[tuple[float, float]]:
    if not pts:
        return []
    out = [pts[0]]
    acc = 0.0
    for a, b in zip(pts, pts[1:]):
        acc += haversine_m(a[0], a[1], b[0], b[1])
        if acc >= spacing_m:
            out.append(b)
            acc = 0.0
    if out[-1] != pts[-1]:
        out.append(pts[-1])
    return out


def _local_tag(el: ET.Element) -> str:
    return el.tag.rsplit("}", 1)[-1]


def parse_gpx(path: Path) -> dict:
    tree = ET.parse(path)
    root = tree.getroot()
    pts: list[tuple[float, float]] = []
    desc = ""
    name = path.stem
    captured = None
    for el in root.iter():
        tag = _local_tag(el)
        if tag == "trkpt":
            pts.append((float(el.attrib["lat"]), float(el.attrib["lon"])))
        elif tag == "desc" and el.text and not desc:
            desc = el.text.strip()
        elif tag == "name" and el.text and name == path.stem:
            name = el.text.strip()
        elif tag == "time" and el.text and captured is None:
            captured = el.text.strip()
    if not pts:
        raise ValueError(f"No <trkpt> in {path}")
    advertised_km = None
    advertised_min = None
    via = None
    m_km = re.search(r"Distance:\s*([0-9.]+)\s*km", desc, re.I)
    m_min = re.search(r"Duration:\s*([0-9.]+)\s*min", desc, re.I)
    m_via = re.search(r"Via:\s*(.+)", desc, re.I)
    if m_km:
        advertised_km = float(m_km.group(1))
    if m_min:
        advertised_min = float(m_min.group(1))
    if m_via:
        via = m_via.group(1).strip()
    return {
        "path": str(path),
        "name": name,
        "desc": desc,
        "captured_utc": captured,
        "points": pts,
        "n_trkpt": len(pts),
        "geodesic_m": round(geodesic_length_m(pts), 1),
        "advertised_km": advertised_km,
        "advertised_min": advertised_min,
        "via": via,
    }


def parse_notes(path: Path) -> dict:
    out: dict = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip()
        val = val.strip()
        if not val:
            continue
        out[key] = val
    return out


def notes_float(notes: dict, key: str) -> float | None:
    raw = notes.get(key)
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def find_gpx(folder: Path) -> Path | None:
    preferred = folder / "google.gpx"
    if preferred.is_file():
        return preferred
    gpxs = sorted(folder.glob("*.gpx"))
    return gpxs[0] if gpxs else None


def find_screenshot(folder: Path) -> Path | None:
    for name in ("maps_ui.png", "screenshot.png", "maps.png"):
        p = folder / name
        if p.is_file():
            return p
    imgs = sorted(
        [*folder.glob("*.png"), *folder.glob("*.jpg"), *folder.glob("*.jpeg")]
    )
    return imgs[0] if imgs else None


def folder_for_route(n: int) -> tuple[str, str]:
    for num, slug, title in ROUTE_FOLDERS:
        if num == n:
            return slug, title
    raise SystemExit(f"Unknown route number {n} (want 1–11)")


def parse_route_number(route_name: str) -> int | None:
    m = re.match(r"route\s+(\d+):", route_name, re.I)
    return int(m.group(1)) if m else None


def load_preset_rows(path: Path) -> dict[int, dict[str, dict]]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    by: dict[int, dict[str, dict]] = {}
    for row in data.get("rows") or []:
        n = parse_route_number(str(row.get("route") or ""))
        if n is None:
            continue
        by.setdefault(n, {})[row["preset"]] = row
    return by


def core_from_stats(stats: dict) -> dict:
    return {k: stats.get(k) for k, _ in CORE_KEYS}


def phase_b_manual(rte, stats: dict) -> dict:
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
    parts = {
        "signal": float(stats.get("signal_count") or 0) * ps["signal"],
        "give_way": float(stats.get("give_way_count") or 0) * ps["give_way"],
        "stop_sign": float(stats.get("stop_sign_count") or 0) * ps["stop_sign"],
        "junction": float(stats.get("junction_count") or 0) * ps["junction"],
        "calming": float(stats.get("calming_count") or 0) * ps["calming"],
        "barrier": float(stats.get("barrier_penalty_count") or 0) * ps["barrier"],
        "climb": float(stats.get("elevation_gain") or 0) * float(ps["climb_per_metre"]),
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


def path_length_m(G, path: list) -> float:
    total = 0.0
    for u, v in zip(path, path[1:]):
        d = G.get_edge_data(u, v) or {}
        total += float(d.get("length", 0) or 0)
    return total


def write_init(force_notes: bool = False) -> None:
    COMPARE_DIR.mkdir(parents=True, exist_ok=True)
    readme = COMPARE_DIR / "README.md"
    if not readme.is_file():
        readme.write_text(_README, encoding="utf-8")
    for n, slug, title in ROUTE_FOLDERS:
        folder = COMPARE_DIR / slug
        folder.mkdir(parents=True, exist_ok=True)
        notes = folder / "notes.txt"
        if force_notes or not notes.is_file():
            body = NOTES_TEMPLATE.replace(
                "notes:\n",
                f"notes: Fixture {n} — {title}\n",
            )
            notes.write_text(body, encoding="utf-8")
        keep = folder / ".keep"
        if not find_gpx(folder) and not keep.is_file():
            keep.write_text("", encoding="utf-8")
    print(f"Drop folders ready under {COMPARE_DIR}")
    for n, slug, _title in ROUTE_FOLDERS:
        gpx = find_gpx(COMPARE_DIR / slug)
        shot = find_screenshot(COMPARE_DIR / slug)
        print(
            f"  r{n:02d}  {slug:32}  "
            f"gpx={'yes' if gpx else '-':3}  "
            f"png={'yes' if shot else '-'}"
        )


_README = """# Google Maps cycling compare (local drop box)

Not in the thesis repo. Paste one capture per fixture, then run
`python 4_backend_engine/score_google_gpx.py` from `C:\\London_Cycle_Maps`.

## Per route folder

| File | Required | What it is |
|------|----------|------------|
| `google.gpx` | yes | Maps cycling track (mapstogpx.com Track Points) |
| `maps_ui.png` | recommended | Screenshot of Maps distance + duration |
| `notes.txt` | fill advertised numbers if missing from GPX | `google_duration_min` / `google_distance_km` |

Do not pick among Maps alternatives. Export the route the UI shows first.
Log `logged_in:` in notes (`yes` / `no` / `unknown`).

## Folders

| Folder | Fixture |
|--------|---------|
| `r01_imperial_kings_cross` | Imperial → King's Cross |
| `r02_imperial_greenwich` | Imperial → Greenwich |
| `r03_imperial_spitalfields` | Imperial → New Spitalfields Market |
| `r04_twickenham_st_pauls` | Twickenham Stadium → St Paul's |
| `r05_wembley_kch` | Wembley Stadium → King's College Hospital |
| `r06_battersea_temple` | Battersea Park → Temple |
| `r07_putney_notting_hill` | Putney Bridge → Notting Hill |
| `r08_tottenham_hampstead` | Tottenham Stadium → Hampstead |
| `r09_earls_court_piccadilly` | Earl's Court → Piccadilly |
| `r10_bromley_ealing` | Bromley → Ealing |
| `r11_elmers_end_streatham` | Elmers End → Streatham (hill) |

## What the script does

1. Reads `<trkpt>` from `google.gpx`, subsamples ~60 m.
2. Snaps each point onto the OSM cycling graph (80 m cap; endpoints may go wider).
3. Stitches consecutive anchors with **length-only** A* (parks treated as open, live closures off) so the scored path follows Google instead of a Fast/Safe cost.
4. Runs `calculate_path_stats` + live Phase B (same clock as `presets_aligned_time_compare_phase_b_live.json`).
5. Writes `runs/YYYY-MM-DD/google_gpx_score.md` / `.json` and `runs/YYYY-MM-DD/overlays/*.html`.

Maps UI minutes are Google's clock. Phase B is this planner's clock. Both are reported; they are not the same model.

Export tool: https://mapstogpx.com/ — Track Points (exact route), GPX output, start/end waypoints.
Copy the Maps **address-bar** URL after the bike route is drawn, not the `api=1` link.
"""


def _follow_weight(app_mod):
    hard = app_mod.BARRIER_HARD_COST

    def weight_fn(u, v, d):
        if app_mod.is_service_access_denied(d):
            return hard
        if app_mod.barrier_is_hard_block(d):
            return hard
        return float(d.get("length", 1.0) or 1.0)

    return weight_fn


def snap_points(tfl_live, pts: list[tuple[float, float]], *, endpoints_wide: bool):
    snaps = []
    skipped = 0
    n = len(pts)
    wide = float(tfl_live.SNAP_MAX_DISTANCE_M_ROUTE)
    for i, (lat, lon) in enumerate(pts):
        cap = wide if endpoints_wide and i in (0, n - 1) else SNAP_MAX_M
        hit = tfl_live.snap_to_edge(lat, lon, max_distance_m=cap)
        if hit is None and cap < wide:
            hit = tfl_live.snap_to_edge(lat, lon, max_distance_m=wide)
        if hit is None:
            skipped += 1
            continue
        snaps.append(
            {
                "i": i,
                "lat": lat,
                "lon": lon,
                "anchor": hit.anchor_node,
                "snap_m": round(float(hit.distance_m), 1),
                "wide": cap > SNAP_MAX_M + 1e-6,
            }
        )
    anchors = []
    for s in snaps:
        if not anchors or anchors[-1]["anchor"] != s["anchor"]:
            anchors.append(s)
    return snaps, anchors, skipped


def stitch_anchors(G, pathfinding, make_heuristic, weight_fn, anchors: list[dict]):
    import networkx as nx
    from maneuvers.path_edges import concatenate_node_paths

    legs = []
    paths = []
    i = 0
    skipped_anchors = 0
    while i < len(anchors) - 1:
        a, b = anchors[i], anchors[i + 1]
        h = make_heuristic(b["anchor"], G, cost_per_m=1.0)
        try:
            path, astar_stats = pathfinding.astar_unidirectional(
                G, a["anchor"], b["anchor"], h, weight_fn
            )
        except nx.NetworkXNoPath:
            skipped_anchors += 1
            if i + 2 < len(anchors):
                anchors.pop(i + 1)
                continue
            raise RuntimeError(
                f"No graph path between consecutive Google snaps "
                f"(anchor {i} → last). Google likely used an OSM-missing link."
            )
        graph_m = path_length_m(G, path)
        hav_m = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
        jump = graph_m > max(JUMP_RATIO * max(hav_m, 1.0), hav_m + JUMP_EXTRA_M)
        legs.append(
            {
                "from_i": a["i"],
                "to_i": b["i"],
                "graph_m": round(graph_m, 1),
                "haversine_m": round(hav_m, 1),
                "jump": jump,
                "elapsed_s": round(float(astar_stats.get("elapsed_s") or 0), 3),
            }
        )
        paths.append(path)
        i += 1
    if not paths:
        raise RuntimeError("No stitch legs (track snapped to a single node).")
    return concatenate_node_paths(paths), legs, skipped_anchors


def path_to_latlon(app_mod, path_nodes: list) -> list[list[float]]:
    raw = app_mod.reconstruct_path_geometry(path_nodes) or []
    out: list[list[float]] = []
    for pt in raw:
        lat, lon = float(pt[0]), float(pt[1])
        if out and abs(out[-1][0] - lat) < 1e-8 and abs(out[-1][1] - lon) < 1e-8:
            continue
        out.append([lat, lon])
    return out


def route_preset_geoms(app_mod, tfl_live, pathfinding, make_heuristic, compute_lb, park_hours, route: dict, presets: dict) -> dict[str, list]:
    start = tfl_live.snap_to_edge(
        route["start_lat"], route["start_lon"], max_distance_m=tfl_live.SNAP_MAX_DISTANCE_M_ROUTE
    )
    end = tfl_live.snap_to_edge(
        route["end_lat"], route["end_lon"], max_distance_m=tfl_live.SNAP_MAX_DISTANCE_M_ROUTE
    )
    if not start or not end:
        raise RuntimeError(f"preset snap failed: {route['name']}")
    hours_map, fallback = park_hours.build_request_hours_context(
        app_mod.G.graph.get("park_opening_hours_unique") or [],
        park_hours.london_now(),
    )
    out = {}
    for name, weights in presets.items():
        scale = compute_lb(weights)
        h = make_heuristic(end.anchor_node, app_mod.G, cost_per_m=scale)
        wf = app_mod.make_weight_optimized(weights, hours_map, fallback, apply_live=False)
        path, _ = pathfinding.astar_unidirectional(
            app_mod.G, start.anchor_node, end.anchor_node, h, wf
        )
        out[name] = path_to_latlon(app_mod, path)
        print(f"    overlay {name}: {len(out[name])} pts", flush=True)
    return out


def score_track(app_mod, tfl_live, pathfinding, rte, make_heuristic, gpx: dict) -> dict:
    sampled = subsample(gpx["points"], SAMPLE_SPACING_M)
    snaps, anchors, skipped = snap_points(tfl_live, sampled, endpoints_wide=True)
    if len(anchors) < 2:
        raise RuntimeError(
            f"Need >=2 distinct snap anchors (got {len(anchors)}; "
            f"skipped {skipped} of {len(sampled)} samples)."
        )
    weight_fn = _follow_weight(app_mod)
    path, legs, skipped_anchors = stitch_anchors(
        app_mod.G, pathfinding, make_heuristic, weight_fn, anchors
    )
    stats = app_mod.calculate_path_stats(
        path,
        calming_source="both",
        speed_kmh=SPEED_KMH,
        vf_mask_allowed=None,
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
    snapped_m = float(stats["length_m"])
    gpx_m = float(gpx["geodesic_m"])
    ratio = snapped_m / gpx_m if gpx_m else None
    jumps = [leg for leg in legs if leg["jump"]]
    return {
        "n_sampled": len(sampled),
        "n_snapped": len(snaps),
        "n_anchors": len(anchors),
        "n_skipped_samples": skipped,
        "n_skipped_anchors": skipped_anchors,
        "mean_snap_m": round(
            sum(s["snap_m"] for s in snaps) / max(len(snaps), 1), 2
        ),
        "max_snap_m": max((s["snap_m"] for s in snaps), default=None),
        "n_jump_legs": len(jumps),
        "jump_legs": jumps,
        "snapped_length_m": round(snapped_m, 1),
        "gpx_geodesic_m": gpx_m,
        "length_ratio_snapped_over_gpx": round(ratio, 3) if ratio else None,
        "core": core_from_stats(stats),
        "cruise_min": round(manual["cruise_min"], 2),
        "phase_b_min": round(api, 2),
        "phase_b_penalty_min": round(manual["penalty_min"], 2),
        "phase_b_parts_s": manual["parts_s"],
        "vf_lengths_m": manual["vf_lengths_m"],
        "stats_duration_min": float(stats.get("duration_min") or 0),
        "phase_b_api_min": round(api, 4),
        "phase_b_manual_min": manual["duration_min"],
        "phase_b_match": abs(api - manual["duration_min"]) <= 0.05,
        "implied_kmh": implied_kmh(snapped_m, api),
        "legs": legs,
        "_path_nodes": path,
    }


def implied_kmh(length_m, duration_min):
    if duration_min is None or float(duration_min) <= 0:
        return None
    return round((float(length_m) / 1000.0) / (float(duration_min) / 60.0), 2)


def _rescale_preset_clock(row: dict, from_kmh: float, to_kmh: float) -> dict:
    """Cruise scales 1/speed; stop/climb seconds stay. Paths do not change."""
    if not row or abs(from_kmh - to_kmh) < 1e-9:
        return row
    out = dict(row)
    cruise = float(row.get("cruise_min") or 0.0) * (from_kmh / to_kmh)
    penalty = float(row.get("phase_b_penalty_min") or 0.0)
    out["cruise_min"] = round(cruise, 2)
    out["phase_b_min"] = round(cruise + penalty, 2)
    length_m = (row.get("core") or {}).get("length_m")
    if length_m is not None:
        out["implied_kmh"] = implied_kmh(length_m, out["phase_b_min"])
    return out


def _fmt(v, nd=0):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{nd}f}" if nd else f"{v:.0f}"
    return str(v)


def compare_block(score: dict, presets: dict | None, advertised_min, advertised_km) -> dict:
    out = {
        "maps_ui_min": advertised_min,
        "maps_ui_km": advertised_km,
        "maps_implied_kmh": implied_kmh(
            (advertised_km or 0) * 1000.0, advertised_min
        )
        if advertised_km and advertised_min
        else None,
        "phase_b_minus_maps_ui_min": None,
        "vs": {},
    }
    if advertised_min is not None:
        out["phase_b_minus_maps_ui_min"] = round(
            float(score["phase_b_min"]) - float(advertised_min), 2
        )
    if not presets:
        return out
    g_b = float(score["phase_b_min"])
    g_len = float(score["core"]["length_m"])
    for preset in ("fastest", "fast", "safe", "leisure"):
        row = presets.get(preset)
        if not row:
            continue
        b = float(row["phase_b_min"])
        ln = float(row["core"]["length_m"])
        out["vs"][preset] = {
            "phase_b_min": b,
            "length_m": ln,
            "implied_kmh": implied_kmh(ln, b),
            "delta_phase_b_google_minus_preset": round(g_b - b, 2),
            "delta_len_google_minus_preset": round(g_len - ln, 1),
            "google_faster_on_phase_b": g_b < b,
        }
    return out


def write_report(
    jobs: list[dict],
    preset_meta: dict,
    *,
    report_md: Path,
    report_json: Path,
    preset_json: Path,
) -> None:
    report_md.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "speed_kmh": SPEED_KMH,
        "sample_spacing_m": SAMPLE_SPACING_M,
        "snap_max_m": SNAP_MAX_M,
        "preset_json": str(preset_json) if preset_json.is_file() else None,
        "preset_generated_at": preset_meta.get("generated_at"),
        "preset_fast_leq_safe": (preset_meta.get("pivot") or {})
        .get("fast", {})
        .get("fast_leq_safe_phase_b"),
        "jobs": jobs,
    }
    report_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "# Google GPX scored on the local graph (Phase B)",
        "",
        f"Generated: `{payload['generated_at']}`",
        "",
        f"Run folder: `{report_md.parent}`",
        "",
        f"Snap cap **{SNAP_MAX_M:.0f} m** (endpoints may use the /route cap) · "
        f"sample **{SAMPLE_SPACING_M:.0f} m** · cruise **{SPEED_KMH:.0f} km/h** · "
        "length-only stitch, parks open, live closures off.",
        "",
    ]
    if payload["preset_json"]:
        lines += [
            f"Preset scoreboard: `{preset_json}`"
            + (
                f" ({payload['preset_generated_at']})"
                if payload["preset_generated_at"]
                else ""
            )
            + (
                f" · Fast≤Safe Phase B **{payload['preset_fast_leq_safe']}**"
                if payload["preset_fast_leq_safe"]
                else ""
            ),
            "",
        ]
    else:
        lines += [
            f"Preset JSON missing (`{preset_json}`). Google is scored; no Fast/Safe columns.",
            "",
        ]
    lines += [
        "Maps UI minutes are Google's own label. Phase B is this planner's clock "
        f"(**{SPEED_KMH:.0f} km/h** moving + Jafari VF + stop table + Miotti climb). "
        "Google's snapped geometry is timed on that clock. Fast/Safe/Leisure come from "
        "the preset scoreboard, rescaled to the same moving speed if needed. "
        "Do not also scale this planner's paths onto Maps minutes-per-km; the clocks "
        "already share a 20 km/h moving cruise.",
        "",
        "## Per fixture",
        "",
        "| Route | Maps km / min | Maps v | Fast B | Fast v | Google B | Google v | ΔB vs Fast | jumps |",
        "|------:|--------------:|-------:|-------:|-------:|---------:|---------:|-----------:|------:|",
    ]
    for job in jobs:
        if job.get("error"):
            lines.append(
                f"| {job['route_n']} | — | — | — | — | ERROR | — | — | — |"
            )
            continue
        cmp_ = job["compare"]
        vs = cmp_.get("vs") or {}
        fast = vs.get("fast") or {}
        d_fast = fast.get("delta_phase_b_google_minus_preset")
        lines.append(
            f"| {job['route_n']} | "
            f"{_fmt(cmp_.get('maps_ui_km'), 1)} / {_fmt(cmp_.get('maps_ui_min'), 0)} | "
            f"{_fmt(cmp_.get('maps_implied_kmh'), 2)} | "
            f"{_fmt(fast.get('phase_b_min'), 2)} | {_fmt(fast.get('implied_kmh'), 2)} | "
            f"**{_fmt(job['score']['phase_b_min'], 2)}** | "
            f"{_fmt(job['score'].get('implied_kmh'), 2)} | "
            f"{_fmt(d_fast, 2)} | {job['score']['n_jump_legs']} |"
        )
    fast_vs = [
        (j.get("compare") or {}).get("vs", {}).get("fast") or {}
        for j in jobs
        if not j.get("error")
    ]
    fast_v = [r["implied_kmh"] for r in fast_vs if r.get("implied_kmh")]
    g_v = [
        j["score"]["implied_kmh"]
        for j in jobs
        if not j.get("error") and j.get("score", {}).get("implied_kmh")
    ]
    if fast_v or g_v:
        lines += [
            "",
            "## Door-to-door speed (length / Phase B)",
            "",
        ]
        if fast_v:
            lines.append(
                f"Fast mean **{sum(fast_v)/len(fast_v):.2f} km/h** "
                f"(n={len(fast_v)}; min {min(fast_v):.2f}, max {max(fast_v):.2f})."
            )
        if g_v:
            lines.append(
                f"Google snapped mean **{sum(g_v)/len(g_v):.2f} km/h** "
                f"(n={len(g_v)}; min {min(g_v):.2f}, max {max(g_v):.2f})."
            )
        lines.append("")
    lines += ["", "## Detail", ""]
    for job in jobs:
        title = f"### r{job['route_n']:02d} — {job['title']}"
        lines.append(title)
        lines.append("")
        if job.get("error"):
            lines.append(f"- **Error:** {job['error']}")
            lines.append("")
            continue
        s = job["score"]
        c = s["core"]
        cmp_ = job["compare"]
        lines += [
            f"- Files: `{job['gpx_name']}`"
            + (f" · screenshot `{job['screenshot']}`" if job.get("screenshot") else " · no screenshot"),
            f"- Maps UI: {_fmt(cmp_.get('maps_ui_km'), 1)} km / {_fmt(cmp_.get('maps_ui_min'), 0)} min"
            + (f" · via {job.get('via')}" if job.get("via") else ""),
            f"- GPX geodesic {s['gpx_geodesic_m']:.0f} m · snapped {s['snapped_length_m']:.0f} m "
            f"(ratio {s['length_ratio_snapped_over_gpx']}) · "
            f"samples {s['n_sampled']} → anchors {s['n_anchors']} · "
            f"mean snap {s['mean_snap_m']} m (max {s['max_snap_m']})",
            f"- Google on this graph: len {c['length_m']:.0f} m · sig {c['signal_count']} · "
            f"elev {c.get('elevation_gain')} m · VF {c.get('vehicular_free_pct')}% · "
            f"TfL cw {c.get('tfl_cycleway_pct')}% · accidents {c.get('accidents')} · "
            f"cruise {s['cruise_min']} min · **Phase B {s['phase_b_min']} min**",
        ]
        if cmp_.get("phase_b_minus_maps_ui_min") is not None:
            lines.append(
                f"- Phase B − Maps UI: {cmp_['phase_b_minus_maps_ui_min']:+.2f} min "
                "(clocks differ; do not treat as a path error by itself)"
            )
        vs = cmp_.get("vs") or {}
        if vs:
            lines.append(
                "- vs presets (Phase B, Google minus preset): "
                + ", ".join(
                    f"{p} {_fmt(vs[p].get('delta_phase_b_google_minus_preset'), 2)} min "
                    f"(len {_fmt(vs[p].get('delta_len_google_minus_preset'), 0)} m)"
                    for p in ("fastest", "fast", "safe", "leisure")
                    if p in vs
                )
            )
        if s["n_jump_legs"]:
            lines.append(
                f"- **Jump legs:** {s['n_jump_legs']} stitch(es) where A* was much longer "
                "than the Google chord — likely an OSM/Google geometry mismatch."
            )
        if s["length_ratio_snapped_over_gpx"] and s["length_ratio_snapped_over_gpx"] > 1.15:
            lines.append(
                "- Snapped length is >15% over the GPX geodesic. Treat this row as a "
                "map-match warning, not a clean Google-vs-Fast comparison."
            )
        lines.append("")
    lines += [
        "## How to read",
        "",
        "- **Google B / Google v** = Maps geometry on this planner's clock "
        f"({SPEED_KMH:.0f} km/h moving + stops/climb).",
        "- **Fast B / Fast v** = this planner's Fast path on the same clock "
        "(preset JSON rescaled if it was timed at another cruise).",
        "- **Maps v** = advertised km / advertised min (Google's own label).",
        "- Negative ΔB vs Fast means the Google line is quicker *on this clock* than Fast.",
        "- VF% on Google uses the unmasked vehicular-free set (same as fastest). Fast/Safe VF% use each preset's VF mask.",
        "",
        f"JSON: `{report_json}`",
        "",
    ]
    report_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {report_md}")
    print(f"Wrote {report_json}")


def collect_jobs(args) -> list[dict]:
    jobs = []
    if args.gpx:
        n = args.route[0] if args.route else 1
        slug, title = folder_for_route(n)
        gpx_path = Path(args.gpx).expanduser().resolve()
        if not gpx_path.is_file():
            raise SystemExit(f"GPX not found: {gpx_path}")
        folder = COMPARE_DIR / slug
        jobs.append(
            {
                "route_n": n,
                "slug": slug,
                "title": title,
                "folder": folder,
                "gpx_path": gpx_path,
            }
        )
        return jobs

    want = set(args.route) if args.route else {n for n, _, _ in ROUTE_FOLDERS}
    for n, slug, title in ROUTE_FOLDERS:
        if n not in want:
            continue
        folder = COMPARE_DIR / slug
        gpx_path = find_gpx(folder)
        if gpx_path is None:
            if args.route:
                raise SystemExit(f"No GPX in {folder} (drop google.gpx there)")
            continue
        jobs.append(
            {
                "route_n": n,
                "slug": slug,
                "title": title,
                "folder": folder,
                "gpx_path": gpx_path,
            }
        )
    if not jobs:
        raise SystemExit(
            f"No google.gpx files under {COMPARE_DIR}. "
            "Run with --init, paste tracks, then re-run."
        )
    return jobs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--init", action="store_true", help="Create the 11 drop folders + notes.txt")
    parser.add_argument(
        "--route",
        type=int,
        action="append",
        metavar="N",
        help="Fixture number 1–11 (repeatable). Default: every folder that has a GPX.",
    )
    parser.add_argument("--gpx", help="Score this GPX as --route N (default r1)")
    args = parser.parse_args()

    if args.init:
        write_init()
        if not args.gpx and not args.route:
            return 0

    write_init(force_notes=False)
    jobs = collect_jobs(args)

    run_dir, report_md, report_json = resolve_output_paths()
    preset_json = find_preset_json(run_dir)
    overlay_dir = run_dir / "overlays"
    print(f"Output run folder: {run_dir}", flush=True)
    print(f"Preset JSON: {preset_json}", flush=True)

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

    preset_blob = {}
    preset_by_route: dict[int, dict[str, dict]] = {}
    if preset_json.is_file():
        preset_blob = json.loads(preset_json.read_text(encoding="utf-8"))
        preset_by_route = load_preset_rows(preset_json)
        src_speed = float(preset_blob.get("speed_kmh") or SPEED_KMH)
        if abs(src_speed - SPEED_KMH) > 1e-9:
            print(
                f"    rescaling preset clock {src_speed:g} → {SPEED_KMH:g} km/h "
                "(cruise only; penalties unchanged)"
            )
            for presets in preset_by_route.values():
                for key, row in list(presets.items()):
                    presets[key] = _rescale_preset_clock(row, src_speed, SPEED_KMH)
        print(
            f"Preset scoreboard {preset_json.name}  "
            f"Fast<=Safe={(preset_blob.get('pivot') or {}).get('fast', {}).get('fast_leq_safe_phase_b')}"
        )
    else:
        print(f"WARNING: {preset_json} not found - scoring Google only")

    fixtures = bac.parse_test_routes()
    try:
        preset_weights, _preset_src = load_presets()
    except Exception as exc:
        preset_weights = {}
        print(f"WARNING: could not load Fast/Safe/Leisure weights ({exc})")

    overlay_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for i, job in enumerate(jobs, 1):
        print(f"[{i}/{len(jobs)}] r{job['route_n']:02d} {job['title']}  {job['gpx_path'].name} ...", flush=True)
        try:
            gpx = parse_gpx(job["gpx_path"])
            notes = parse_notes(job["folder"] / "notes.txt")
            advertised_min = notes_float(notes, "google_duration_min")
            advertised_km = notes_float(notes, "google_distance_km")
            if advertised_min is None:
                advertised_min = gpx["advertised_min"]
            if advertised_km is None:
                advertised_km = gpx["advertised_km"]
            via = notes.get("via") or gpx.get("via")
            score = score_track(
                app_mod, tfl_live, pathfinding, rte, make_heuristic, gpx
            )
            shot = find_screenshot(job["folder"])
            cmp_ = compare_block(
                score,
                preset_by_route.get(job["route_n"]),
                advertised_min,
                advertised_km,
            )
            rec = {
                "route_n": job["route_n"],
                "slug": job["slug"],
                "title": job["title"],
                "gpx_name": job["gpx_path"].name,
                "gpx_path": str(job["gpx_path"]),
                "screenshot": shot.name if shot else None,
                "via": via,
                "logged_in": notes.get("logged_in", "unknown"),
                "captured_utc": notes.get("captured_utc") or gpx.get("captured_utc"),
                "gpx_meta": {
                    "n_trkpt": gpx["n_trkpt"],
                    "geodesic_m": gpx["geodesic_m"],
                    "advertised_km": gpx["advertised_km"],
                    "advertised_min": gpx["advertised_min"],
                },
                "score": score,
                "compare": cmp_,
            }
            path_nodes = score.pop("_path_nodes", None)
            snapped_latlon = path_to_latlon(app_mod, path_nodes) if path_nodes else []
            preset_geoms = {"fast": [], "safe": [], "leisure": []}
            if preset_weights and 1 <= job["route_n"] <= len(fixtures):
                print("    routing Fast/Safe/Leisure for overlay ...", flush=True)
                preset_geoms = route_preset_geoms(
                    app_mod,
                    tfl_live,
                    pathfinding,
                    make_heuristic,
                    compute_lb,
                    park_opening_hours,
                    fixtures[job["route_n"] - 1],
                    preset_weights,
                )
            overlay_path = overlay_dir / f"{job['slug']}.html"
            write_overlay_html(
                overlay_path,
                title=f"r{job['route_n']:02d} {job['title']}",
                gpx=[[float(a), float(b)] for a, b in gpx["points"]],
                snapped=snapped_latlon,
                fast=preset_geoms.get("fast") or [],
                safe=preset_geoms.get("safe") or [],
                leisure=preset_geoms.get("leisure") or [],
                meta={
                    "maps_km": advertised_km,
                    "maps_min": advertised_min,
                    "gpx_m": gpx["geodesic_m"],
                    "via": via,
                },
            )
            rec["overlay"] = str(overlay_path)
            vs_fast = (cmp_.get("vs") or {}).get("fast") or {}
            print(
                f"    snapped={score['snapped_length_m']:.0f} m  "
                f"sig={score['core']['signal_count']}  "
                f"elev={score['core'].get('elevation_gain')}  "
                f"B={score['phase_b_min']}  "
                f"Maps={advertised_min}  "
                f"dB vs Fast={vs_fast.get('delta_phase_b_google_minus_preset')}  "
                f"jumps={score['n_jump_legs']}"
            )
            print(f"    overlay {overlay_path}")
            results.append(rec)
        except Exception as exc:
            print(f"    ERROR: {exc}")
            results.append(
                {
                    "route_n": job["route_n"],
                    "slug": job["slug"],
                    "title": job["title"],
                    "gpx_name": job["gpx_path"].name,
                    "gpx_path": str(job["gpx_path"]),
                    "error": str(exc),
                }
            )

    write_report(
        results,
        preset_blob,
        report_md=report_md,
        report_json=report_json,
        preset_json=preset_json,
    )
    n_ok = sum(1 for r in results if not r.get("error"))
    print(f"Scored {n_ok}/{len(results)} GPX file(s)")
    return 0 if n_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
