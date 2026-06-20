"""
Tag graph edges inside OSM park polygons (is_park=yes, attraction_name, opening_hours from OSM).

Reads: 1_data/osm_park_polygons.geojson, 3_pipeline/park_hours_overrides.json
Reads/writes: london_elev_final.gpickle (default, before TfL steps)

Run after elevation_processing_aggressive.py:
  python tag_attractions_osm.py
  python tag_attractions_osm.py --input ../1_data/london_elev_final.gpickle

When changing, update 0_documentation/GRAPH.md and run fetch_osm_park_polygons.py first.
"""
from __future__ import annotations

import argparse
import json
import os
import time

from attraction_spatial import (
    build_edge_strtree,
    clear_osm_park_tags,
    compile_park_hours_catalog,
    edge_geometries,
    geometry_from_geojson,
    init_attraction_attrs,
    tag_polygon,
)
from graph_io import load_graph, save_graph, fast_path
from park_hours_overrides import (
    load_park_hours_overrides,
    resolve_polygon_opening_hours,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "1_data"))
PARKS_GEOJSON = os.path.join(DATA_DIR, "osm_park_polygons.geojson")
DEFAULT_INPUT = os.path.join(DATA_DIR, "london_elev_final.graphml")


def _load_park_features(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("features", [])


def main() -> int:
    parser = argparse.ArgumentParser(description="Tag edges in OSM park polygons")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Input graph (.graphml or .gpickle)")
    parser.add_argument("--output", default=None, help="Output path (default: overwrite input)")
    parser.add_argument("--parks", default=PARKS_GEOJSON, help="Park polygons GeoJSON")
    parser.add_argument("--pickle-only", action=argparse.BooleanOptionalAction, default=True,
                        help="Save .gpickle only (default). Use --no-pickle-only for GraphML.")
    args = parser.parse_args()

    input_path = os.path.normpath(os.path.join(SCRIPT_DIR, args.input))
    output_path = os.path.normpath(os.path.join(SCRIPT_DIR, args.output)) if args.output else input_path
    parks_path = os.path.normpath(args.parks)

    if not os.path.isfile(parks_path):
        print(f"ERROR: Park GeoJSON not found: {parks_path}")
        print("       Run: python fetch_osm_park_polygons.py")
        return 1
    if not os.path.isfile(input_path) and not os.path.isfile(fast_path(input_path)):
        print(f"ERROR: Graph not found: {input_path}")
        return 1

    print("--- TAG OSM PARKS ON GRAPH ---")
    print(f"Input:  {input_path}")
    print(f"Parks:  {parks_path}")

    G = load_graph(input_path)
    init_attraction_attrs(G)

    print("1. Clearing existing is_park tags...")
    cleared = clear_osm_park_tags(G)
    print(f"   -> Cleared is_park on {cleared:,} edges")

    print("2. Building edge spatial index...")
    t0 = time.perf_counter()
    edge_list = edge_geometries(G)
    tree, edge_list = build_edge_strtree(edge_list)
    print(f"   -> {len(edge_list):,} edges indexed in {time.perf_counter() - t0:.1f}s")

    features = _load_park_features(parks_path)
    overrides = load_park_hours_overrides()
    if overrides:
        print(f"   -> {len(overrides)} manual opening_hours override(s) loaded")
    print(f"3. Tagging {len(features):,} park polygons...")
    total_tagged = 0
    polygons_ok = 0
    t1 = time.perf_counter()
    for i, feat in enumerate(features):
        geom_dict = feat.get("geometry")
        if not geom_dict:
            continue
        try:
            poly = geometry_from_geojson(geom_dict)
        except Exception:
            continue
        if poly is None or poly.is_empty:
            continue
        props = feat.get("properties") or {}
        name = str(props.get("name", "") or "").strip()
        if name.lower() == "nan":
            name = ""
        opening_hours = resolve_polygon_opening_hours(
            name,
            str(props.get("opening_hours", "") or "").strip(),
            overrides,
        )
        n = tag_polygon(G, poly, edge_list=edge_list, tree=tree, name=name, opening_hours=opening_hours)
        if n > 0:
            polygons_ok += 1
            total_tagged += n
        if (i + 1) % 500 == 0:
            print(f"   -> Processed {i + 1}/{len(features)} polygons...")

    elapsed = time.perf_counter() - t1
    park_edges = sum(
        1 for _u, _v, d in G.edges(data=True)
        if str(d.get("is_park", "")).strip().lower() == "yes"
    )
    park_with_hours = sum(
        1 for _u, _v, d in G.edges(data=True)
        if str(d.get("is_park", "")).strip().lower() == "yes"
        and str(d.get("opening_hours", "")).strip()
    )
    unique_hours = compile_park_hours_catalog(G)
    print(f"   -> {polygons_ok} polygons tagged at least one edge")
    print(f"   -> {total_tagged:,} edge-tag operations in {elapsed:.1f}s")
    print(f"   -> {park_edges:,} directed edges with is_park=yes")
    print(f"   -> {park_with_hours:,} park edges with opening_hours")
    print(f"   -> {len(unique_hours)} unique opening_hours strings in catalog")

    print(f"4. Saving to {output_path}...")
    save_graph(G, output_path, write_graphml=not args.pickle_only, write_fast=True)
    print("SUCCESS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
