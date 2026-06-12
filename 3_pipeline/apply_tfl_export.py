"""
Re-apply TfL cycle route tags from tfl_edges_from_graph.json (master export / ground truth).

After a noded rebuild, export records use old (source, target) node ids. This script
resolves them via --legacy-graph to parent osm_id and fans out tags to all split sub-edges.

Reads:  --graph (default london_elev_final_tfl; use london_elev_final when skipping tag step)
        --export (default tfl_edges_from_graph.json)
        --legacy-graph (pre-noding graph matching the export)
Writes: --output (default: overwrite --graph)

Behaviour: zeros all TfL tags, then applies merged export tags per osm_id (export is authoritative).
"""
import json
import os
import argparse

from graph_io import load_graph, save_graph, fast_path
from tfl_osm_translate import (
    aggregate_export_tags_by_osm_id,
    apply_tags_to_osm_ids,
    build_osm_index,
    load_legacy_graph,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "1_data")
DEFAULT_GRAPH = os.path.join(DATA_DIR, "london_elev_final_tfl.graphml")
DEFAULT_EXPORT = os.path.join(SCRIPT_DIR, "tfl_edges_from_graph.json")


def main():
    parser = argparse.ArgumentParser(description="Re-apply TfL tags from export JSON to graph.")
    parser.add_argument("--graph", default=DEFAULT_GRAPH, help="Input graph path (canonical .graphml name)")
    parser.add_argument(
        "--output",
        default=None,
        help="Output graph path (default: overwrite --graph). Use london_elev_final_tfl when --graph is elev_final.",
    )
    parser.add_argument("--export", default=DEFAULT_EXPORT, help="JSON export from extract_tfl_from_graph.py")
    parser.add_argument(
        "--legacy-graph",
        default=None,
        help="Pre-noding graph to map export (source,target) pairs to osm_id (required after mesh rebuild)",
    )
    parser.add_argument(
        "--pickle-only",
        action="store_true",
        help="Save .gpickle only (skip GraphML write)",
    )
    args = parser.parse_args()
    graph_path = os.path.normpath(os.path.abspath(args.graph))
    output_path = os.path.normpath(os.path.abspath(args.output or args.graph))
    export_path = os.path.normpath(os.path.abspath(args.export))

    if not os.path.isfile(graph_path) and not os.path.isfile(fast_path(graph_path)):
        print(f"ERROR: Graph not found: {graph_path} (or .gpickle)")
        return 1
    if not os.path.isfile(export_path):
        print(f"ERROR: Export file not found: {export_path}")
        return 1

    print("--- APPLY TfL EXPORT (ground truth from tfl_edges_from_graph.json) ---")
    print(f"1. Loading graph from {graph_path}...")
    G = load_graph(graph_path)
    print(f"   -> {G.number_of_nodes()} nodes, {G.number_of_edges()} edges.")

    G_legacy = None
    if args.legacy_graph:
        try:
            G_legacy = load_legacy_graph(args.legacy_graph, SCRIPT_DIR)
        except FileNotFoundError as e:
            print(f"ERROR: {e}")
            return 1

    print("2. Zeroing all TfL tags on the graph...")
    for u, v in G.edges():
        G.edges[u, v]["tfl_cycle_programme"] = ""
        G.edges[u, v]["tfl_cycle_route"] = ""
    print(f"   -> Cleared tags on all {G.number_of_edges()} edges.")

    print("3. Loading export...")
    with open(export_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    edges_in = data.get("edges") or []
    print(f"   -> {len(edges_in)} records in export (from {data.get('source_graph', '?')}).")

    osm_index = build_osm_index(G)
    print(f"   -> osm_id index: {len(osm_index)} parent way(s).")

    tags_by_osm, resolved, unique_osm, skipped = aggregate_export_tags_by_osm_id(
        edges_in, G, G_legacy, osm_index
    )
    print(
        f"4. Resolved {resolved} export record(s) -> {unique_osm} unique osm_id(s); "
        f"skipped {skipped} unresolved."
    )
    if skipped and G_legacy is None:
        print(
            "   WARNING: Many records skipped without --legacy-graph. "
            "Pass the pre-noding graph that matches the export node ids."
        )

    n_applied = apply_tags_to_osm_ids(G, osm_index, tags_by_osm)
    print(f"5. Applied tags to {n_applied} directed edge(s) on the new mesh.")

    print(f"6. Saving graph to {output_path}...")
    save_graph(G, output_path, write_graphml=not args.pickle_only, write_fast=True)
    print("SUCCESS.")
    return 0


if __name__ == "__main__":
    exit(main())
