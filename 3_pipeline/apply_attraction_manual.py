"""
Apply manual attraction regions from the debug app to the graph.

Reads: 3_pipeline/attraction_manual_regions.json
Sets is_park / is_river / is_sight and merges attraction_name (does not clear OSM is_park).

Run after TfL steps on the final graph:
  python apply_attraction_manual.py
  python apply_attraction_manual.py --pickle-only

When changing, update 0_documentation/GRAPH.md.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from attraction_spatial import (
    build_edge_strtree,
    clear_manual_river_sight_tags,
    edge_geometries,
    geometry_from_geojson,
    init_attraction_attrs,
    tag_buffered_line,
    tag_point_radius,
    tag_polygon,
    tag_river_polygon,
)
from graph_io import load_graph, save_graph, fast_path
from shapely.geometry import LineString, Point

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "1_data"))
REGIONS_PATH = os.path.join(SCRIPT_DIR, "attraction_manual_regions.json")
DEFAULT_GRAPH = os.path.join(DATA_DIR, "london_elev_final_tfl.graphml")


def _load_regions(path: str) -> list[dict]:
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("regions", [])


def _apply_region(G, region: dict, edge_list, tree) -> int:
    rtype = str(region.get("type", "")).strip().lower()
    name = str(region.get("name", "") or "").strip()
    geom_dict = region.get("geometry")
    if not geom_dict:
        return 0

    if rtype == "park":
        poly = geometry_from_geojson(geom_dict)
        if poly is None:
            return 0
        return tag_polygon(G, poly, edge_list=edge_list, tree=tree, name=name)

    if rtype == "river":
        geom = geometry_from_geojson(geom_dict)
        if geom is None:
            return 0
        if geom.geom_type in ("Polygon", "MultiPolygon"):
            return tag_river_polygon(
                G, geom, edge_list=edge_list, tree=tree, name=name,
            )
        if geom.geom_type == "LineString":
            buffer_m = float(region.get("buffer_m") or 200)
            return tag_buffered_line(
                G, geom, buffer_m, edge_list=edge_list, tree=tree, name=name,
            )
        return 0

    if rtype == "sight":
        if geom_dict.get("type") == "Point":
            coords = geom_dict.get("coordinates", [])
            if len(coords) < 2:
                return 0
            lon, lat = float(coords[0]), float(coords[1])
        else:
            pt = geometry_from_geojson(geom_dict)
            if pt is None or pt.is_empty:
                return 0
            lon, lat = float(pt.x), float(pt.y)
        radius_m = float(region.get("radius_m") or 200)
        return tag_point_radius(
            G, lon, lat, radius_m, edge_list=edge_list, tree=tree, name=name,
        )

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply manual attraction regions")
    parser.add_argument("--input", default=DEFAULT_GRAPH, help="Input graph path")
    parser.add_argument("--output", default=None, help="Output path (default: overwrite input)")
    parser.add_argument("--regions", default=REGIONS_PATH, help="Manual regions JSON")
    parser.add_argument("--pickle-only", action="store_true", help="Save .gpickle only")
    args = parser.parse_args()

    input_path = os.path.normpath(os.path.join(SCRIPT_DIR, args.input))
    output_path = os.path.normpath(os.path.join(SCRIPT_DIR, args.output)) if args.output else input_path
    regions_path = os.path.normpath(args.regions)

    if not os.path.isfile(input_path) and not os.path.isfile(fast_path(input_path)):
        print(f"ERROR: Graph not found: {input_path}")
        return 1

    regions = _load_regions(regions_path)
    print("--- APPLY MANUAL ATTRACTION REGIONS ---")
    print(f"Input:   {input_path}")
    print(f"Regions: {regions_path} ({len(regions)} regions)")

    G = load_graph(input_path)
    init_attraction_attrs(G)

    print("1. Clearing previous manual is_river / is_sight tags...")
    cleared_river, cleared_sight = clear_manual_river_sight_tags(G)
    print(f"   -> Cleared is_river on {cleared_river:,} edges, is_sight on {cleared_sight:,} edges")

    if not regions:
        print("No regions to apply; saving graph unchanged.")
        save_graph(G, output_path, write_graphml=not args.pickle_only, write_fast=True)
        return 0

    print("2. Building edge spatial index...")
    t0 = time.perf_counter()
    edge_list = edge_geometries(G)
    tree, edge_list = build_edge_strtree(edge_list)
    print(f"   -> {len(edge_list):,} edges in {time.perf_counter() - t0:.1f}s")

    print("3. Applying regions...")
    total_ops = 0
    for i, region in enumerate(regions):
        n = _apply_region(G, region, edge_list, tree)
        total_ops += n
        if (i + 1) % 50 == 0:
            print(f"   -> {i + 1}/{len(regions)} regions...")

    for flag in ("is_park", "is_river", "is_sight"):
        count = sum(
            1 for _u, _v, d in G.edges(data=True)
            if str(d.get(flag, "")).strip().lower() == "yes"
        )
        print(f"   -> {flag}=yes: {count:,} edges")

    print(f"   -> {total_ops:,} edge-tag operations")
    print(f"4. Saving to {output_path}...")
    save_graph(G, output_path, write_graphml=not args.pickle_only, write_fast=True)
    print("SUCCESS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
