"""
Re-apply TfL cycle route tags from a previous export (e.g. tfl_edges_from_graph.json).
Use after re-running build_graph + elevation + tag_tfl_routes when you want to restore
the exact TfL state from a graph you had before the rebuild.

Reads:  --graph (default 1_data/london_elev_final_tfl.graphml)
        --export (default 3_pipeline/tfl_edges_from_graph.json)
Writes: --graph (overwrites). Run extract_tfl_from_graph.py first to create the export.

Behaviour: First zeros tfl_cycle_programme and tfl_cycle_route on every edge, then
applies only the edges from the export. So the result is exactly the exported state
(no leftover tags from the previous graph).

Export format: { "source_graph", "exported_at", "edges": [ { "source", "target",
  "tfl_cycle_programme", "tfl_cycle_route" }, ... ] }
Edges in the export are set; edges not in the export remain empty. Missing edges
(in graph but not in export) are skipped when applying; edges in export but not
in graph are skipped (e.g. graph changed).
"""
import json
import os
import argparse
import networkx as nx

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "1_data")
DEFAULT_GRAPH = os.path.join(DATA_DIR, "london_elev_final_tfl.graphml")
DEFAULT_EXPORT = os.path.join(SCRIPT_DIR, "tfl_edges_from_graph.json")


def main():
    parser = argparse.ArgumentParser(description="Re-apply TfL tags from export JSON to graph.")
    parser.add_argument("--graph", default=DEFAULT_GRAPH, help="GraphML to update (in-place)")
    parser.add_argument("--export", default=DEFAULT_EXPORT, help="JSON export from extract_tfl_from_graph.py")
    args = parser.parse_args()
    graph_path = os.path.normpath(os.path.abspath(args.graph))
    export_path = os.path.normpath(os.path.abspath(args.export))

    if not os.path.isfile(graph_path):
        print(f"ERROR: Graph not found: {graph_path}")
        return 1
    if not os.path.isfile(export_path):
        print(f"ERROR: Export file not found: {export_path}")
        return 1

    print("1. Loading graph...")
    G = nx.read_graphml(graph_path)
    print(f"   -> {G.number_of_nodes()} nodes, {G.number_of_edges()} edges.")

    print("2. Zeroing all TfL tags on the graph...")
    for u, v in G.edges():
        G.edges[u, v]["tfl_cycle_programme"] = ""
        G.edges[u, v]["tfl_cycle_route"] = ""
    print(f"   -> Cleared tfl_cycle_programme and tfl_cycle_route on all {G.number_of_edges()} edges.")

    print("3. Loading export...")
    with open(export_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    edges_in = data.get("edges") or []
    print(f"   -> {len(edges_in)} edges in export (from {data.get('source_graph', '?')}).")

    applied = 0
    skipped = 0
    for rec in edges_in:
        u = rec.get("source")
        v = rec.get("target")
        if u is None or v is None:
            skipped += 1
            continue
        if not G.has_edge(u, v):
            skipped += 1
            continue
        prog = str(rec.get("tfl_cycle_programme") or "").strip()
        route = str(rec.get("tfl_cycle_route") or "").strip()
        G.edges[u, v]["tfl_cycle_programme"] = prog
        G.edges[u, v]["tfl_cycle_route"] = route
        applied += 1

    print(f"4. Applied tags to {applied} edge(s); skipped {skipped}.")
    print(f"5. Saving graph to {graph_path}...")
    nx.write_graphml(G, graph_path)
    print("SUCCESS.")
    return 0


if __name__ == "__main__":
    exit(main())
