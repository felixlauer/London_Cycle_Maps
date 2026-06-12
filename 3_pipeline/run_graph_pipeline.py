#!/usr/bin/env python3
"""
Run the London Cycle Maps graph pipeline end-to-end (sequential subprocesses).

Default (graph-only, PostgreSQL already loaded):
  noded_network → build_graph → elevation → tag_attractions_osm → [tag_tfl_routes] → apply_tfl_export → apply_tfl_manual_edits → apply_attraction_manual

TfL final stage (when tfl_edges_from_graph.json exists):
  Export JSON is ground truth; use --skip-tagging to skip geometry tagging.
  --legacy-graph maps old node ids to osm_id on the noded mesh (default: 1_data/legacy_graph.graphml).

Run from repo root or 3_pipeline/:
  python run_graph_pipeline.py
  python run_graph_pipeline.py --skip-tagging --legacy-graph ../1_data/legacy_graph.graphml
  python run_graph_pipeline.py --start-at apply_tfl_export.py --skip-tagging

When changing pipeline order, update 0_documentation/GRAPH.md.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "1_data"))
EXPORT_JSON = os.path.join(SCRIPT_DIR, "tfl_edges_from_graph.json")
MANUAL_EDITS_JSON = os.path.join(SCRIPT_DIR, "tfl_manual_edits.json")
ATTRACTION_MANUAL_JSON = os.path.join(SCRIPT_DIR, "attraction_manual_regions.json")
PARKS_GEOJSON = os.path.join(DATA_DIR, "osm_park_polygons.geojson")
ELEV_FINAL_GRAPH = os.path.join(DATA_DIR, "london_elev_final.graphml")
FINAL_GRAPH = os.path.join(DATA_DIR, "london_elev_final_tfl.graphml")
FINAL_GRAPH_FAST = os.path.join(DATA_DIR, "london_elev_final_tfl.gpickle")
DEFAULT_LEGACY_GRAPH = os.path.join(DATA_DIR, "legacy_graph.graphml")

STEPS_FROM_DB = [
    ("preprocess_data.py", "Prepare London cyclist collision CSV"),
    ("import_roads.py", "Import OSM roads into PostgreSQL"),
    ("import_data.py", "Import accidents into PostgreSQL"),
    ("calculate_risk.py", "Match accidents to road segments (accident_count)"),
]

STEPS_GRAPH_CORE = [
    ("noded_network.py", "Split highways at intersections (planet_osm_line_noded_enriched)"),
    ("build_graph.py", "Build graph (london.graphml + london.gpickle)"),
    ("Add_elevation_raster.py", "Sample LIDAR elevation (london_elev_raw.gpickle)"),
    ("elevation_processing_aggressive.py", "Smooth grades (london_elev_final.gpickle)"),
    ("tag_attractions_osm.py", "Tag OSM park polygons (is_park) on london_elev_final"),
    ("tag_tfl_routes.py", "Tag TfL routes from geometry (london_elev_final_tfl.gpickle + .graphml)"),
]

STEP_TFL_EXPORT = ("apply_tfl_export.py", "Restore TfL tags from tfl_edges_from_graph.json (ground truth)")
STEP_TFL_MANUAL = ("apply_tfl_manual_edits.py", "Apply debug-app manual TfL edits")
STEP_ATTRACTION_MANUAL = ("apply_attraction_manual.py", "Apply manual park/river/sight regions")

ALL_PIPELINE_SCRIPTS = (
    [s for s, _ in STEPS_FROM_DB]
    + [s for s, _ in STEPS_GRAPH_CORE]
    + [STEP_TFL_EXPORT[0], STEP_TFL_MANUAL[0], STEP_ATTRACTION_MANUAL[0]]
)


def _normalize_script_name(name: str) -> str:
    base = os.path.basename(name.strip())
    if not base.endswith(".py"):
        base += ".py"
    return base


def _slice_steps_from_start(
    steps: list[tuple[str, str]], start_at: str | None
) -> tuple[list[tuple[str, str]], int, str | None]:
    if not start_at:
        return steps, 0, None
    target = _normalize_script_name(start_at)
    for i, (script_name, _) in enumerate(steps):
        if script_name == target:
            if i > 0:
                print(f"  Resume: skipping {i} step(s), starting at {script_name}")
            return steps[i:], i, None
    valid = ", ".join(ALL_PIPELINE_SCRIPTS)
    return (
        steps,
        0,
        f"ERROR: --start-at '{start_at}' not in this pipeline run.\n"
        f"       Normalized target: {target}\n"
        f"       Valid script names: {valid}",
    )


def _resolve_legacy_path(explicit: str | None) -> str | None:
    if explicit:
        return os.path.normpath(explicit)
    if os.path.isfile(DEFAULT_LEGACY_GRAPH):
        return DEFAULT_LEGACY_GRAPH
    return None


def _legacy_cli_args(legacy_path: str | None) -> list[str]:
    if not legacy_path:
        return []
    return ["--legacy-graph", legacy_path]


def _run_step(script_name: str, description: str, extra_args: list[str] | None = None) -> int:
    path = os.path.join(SCRIPT_DIR, script_name)
    if not os.path.isfile(path):
        print(f"ERROR: Script not found: {path}")
        return 1
    cmd = [sys.executable, path] + (extra_args or [])
    print("")
    print("=" * 72)
    print(f"  {description}")
    print(f"  -> {' '.join(cmd)}")
    print("=" * 72)
    t0 = time.perf_counter()
    result = subprocess.run(cmd, cwd=SCRIPT_DIR)
    elapsed = time.perf_counter() - t0
    if result.returncode != 0:
        print(f"\nFAILED: {script_name} (exit {result.returncode}) after {elapsed:.1f}s")
        return result.returncode
    print(f"\nOK: {script_name} ({elapsed:.1f}s)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the graph build pipeline sequentially (stops on first failure).",
    )
    parser.add_argument("--from-db", action="store_true", help="Run DB prep steps first")
    parser.add_argument(
        "--skip-export",
        action="store_true",
        help="Do not run apply_tfl_export.py even if tfl_edges_from_graph.json exists",
    )
    parser.add_argument(
        "--apply-export",
        action="store_true",
        help="Run apply_tfl_export.py (requires tfl_edges_from_graph.json)",
    )
    parser.add_argument("--skip-manual", action="store_true", help="Skip apply_tfl_manual_edits.py")
    parser.add_argument(
        "--skip-osm-attractions",
        action="store_true",
        help="Skip tag_attractions_osm.py (requires osm_park_polygons.geojson unless also skipped)",
    )
    parser.add_argument(
        "--skip-attraction-manual",
        action="store_true",
        help="Skip apply_attraction_manual.py",
    )
    parser.add_argument(
        "--skip-tagging",
        action="store_true",
        help=(
            "Skip tag_tfl_routes.py; rely on tfl_edges_from_graph.json as TfL ground truth "
            "(export reads london_elev_final, writes london_elev_final_tfl)"
        ),
    )
    parser.add_argument(
        "--legacy-graph",
        default=None,
        help=(
            "Pre-noding graph for osm_id translation in export + manual steps "
            f"(default if present: {DEFAULT_LEGACY_GRAPH})"
        ),
    )
    parser.add_argument(
        "--pickle-only",
        action="store_true",
        help="TfL apply steps save .gpickle only (skip GraphML write on large final graph)",
    )
    parser.add_argument(
        "--start-at",
        metavar="SCRIPT",
        default=None,
        help="Resume at this script; skip earlier steps",
    )
    args = parser.parse_args()

    legacy_path = _resolve_legacy_path(args.legacy_graph)
    legacy_args = _legacy_cli_args(legacy_path)
    pickle_args = ["--pickle-only"] if args.pickle_only else []

    steps: list[tuple[str, str]] = []
    step_extra: dict[str, list[str]] = {}

    if args.from_db:
        steps.extend(STEPS_FROM_DB)

    graph_core = list(STEPS_GRAPH_CORE)
    if args.skip_tagging:
        graph_core = [s for s in graph_core if s[0] != "tag_tfl_routes.py"]
        print("(Skipping tag_tfl_routes.py — export JSON is TfL ground truth)")
    if args.skip_osm_attractions:
        graph_core = [s for s in graph_core if s[0] != "tag_attractions_osm.py"]
        print("(Skipping tag_attractions_osm.py)")
    steps.extend(graph_core)

    if not args.skip_osm_attractions and "tag_attractions_osm.py" in [s[0] for s in graph_core]:
        if not os.path.isfile(PARKS_GEOJSON):
            print(f"ERROR: OSM parks cache missing: {PARKS_GEOJSON}")
            print("       Run: python fetch_osm_park_polygons.py")
            print("       Or pass --skip-osm-attractions")
            return 1

    run_export = args.apply_export or (not args.skip_export and os.path.isfile(EXPORT_JSON))
    run_manual = not args.skip_manual

    if run_export or run_manual:
        if not legacy_path or not os.path.isfile(legacy_path):
            print(
                "ERROR: --legacy-graph required for TfL export/manual after a noded rebuild.\n"
                f"       Expected e.g. {DEFAULT_LEGACY_GRAPH} or pass --legacy-graph PATH"
            )
            return 1

    if run_export:
        if not os.path.isfile(EXPORT_JSON):
            print(f"ERROR: --apply-export set but file missing: {EXPORT_JSON}")
            return 1
        steps.append(STEP_TFL_EXPORT)
        export_extra = list(legacy_args) + list(pickle_args)
        if args.skip_tagging:
            export_extra.extend(["--graph", ELEV_FINAL_GRAPH, "--output", FINAL_GRAPH])
        step_extra[STEP_TFL_EXPORT[0]] = export_extra
    elif not args.skip_export:
        print(f"(Skipping TfL export — no file at {EXPORT_JSON})")

    if run_manual:
        if not os.path.isfile(MANUAL_EDITS_JSON):
            print(f"ERROR: Manual edits file not found: {MANUAL_EDITS_JSON}")
            print("       Create edits in the debug app or pass --skip-manual.")
            return 1
        steps.append(STEP_TFL_MANUAL)
        step_extra[STEP_TFL_MANUAL[0]] = list(legacy_args) + list(pickle_args)

    if not args.skip_attraction_manual:
        steps.append(STEP_ATTRACTION_MANUAL)
        step_extra[STEP_ATTRACTION_MANUAL[0]] = list(pickle_args)

    steps, skipped, start_err = _slice_steps_from_start(steps, args.start_at)
    if start_err:
        print(start_err)
        return 1

    print("London Cycle Maps — graph pipeline")
    print(f"  Working directory: {SCRIPT_DIR}")
    print(f"  Steps: {len(steps)}" + (f" ({skipped} skipped via --start-at)" if skipped else ""))
    if legacy_path:
        print(f"  Legacy graph (osm_id lookup): {legacy_path}")

    pipeline_start = time.perf_counter()
    for script_name, description in steps:
        code = _run_step(script_name, description, step_extra.get(script_name))
        if code != 0:
            return code

    total = time.perf_counter() - pipeline_start
    print("")
    print("=" * 72)
    print(f"  PIPELINE COMPLETE ({total / 60:.1f} min total)")
    if os.path.isfile(FINAL_GRAPH_FAST):
        print(f"  Output (runtime): {FINAL_GRAPH_FAST}")
    if os.path.isfile(FINAL_GRAPH):
        print(f"  Output (export):  {FINAL_GRAPH}")
    print("  Restart app.py / app_debug.py to load the new graph.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
