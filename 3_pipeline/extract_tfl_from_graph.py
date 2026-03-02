"""
Extract TfL cycle route tags from the current graph into a single JSON file.
Use this to back up TfL state before re-running build_graph (and elevation, etc.),
so tags can be re-applied later from this file instead of relying on manual-edits JSON.

Reads:  1_data/london_elev_final_tfl.graphml (or --input)
Writes: 3_pipeline/tfl_edges_from_graph.json (or --output)

Format:
  {
    "source_graph": "filename",
    "exported_at": "ISO8601",
    "edges": [
      {
        "source": "<node_id>",
        "target": "<node_id>",
        "tfl_cycle_programme": "cycleway;superhighway",
        "tfl_cycle_route": "Q15;CS3"
      },
      ...
    ]
  }

Node IDs are written as in the graph (string). Only edges with at least one of
tfl_cycle_programme or tfl_cycle_route non-empty are included.
To re-apply: use a script that loads a graph and this file, then sets each edge's
tfl_cycle_programme and tfl_cycle_route from the list (see 0_documentation/GRAPH.md).
"""
import json
import os
import argparse
from datetime import datetime, timezone
import networkx as nx

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "1_data")
DEFAULT_GRAPH = os.path.join(DATA_DIR, "london_elev_final_tfl.graphml")
DEFAULT_OUTPUT = os.path.join(SCRIPT_DIR, "tfl_edges_from_graph.json")


def main():
    parser = argparse.ArgumentParser(description="Export TfL edge tags from graph to JSON.")
    parser.add_argument("--input", default=DEFAULT_GRAPH, help="Input GraphML path")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Output JSON path")
    args = parser.parse_args()
    input_path = os.path.normpath(os.path.abspath(args.input))
    output_path = os.path.normpath(os.path.abspath(args.output))

    if not os.path.isfile(input_path):
        print(f"ERROR: Graph not found: {input_path}")
        return 1

    print("1. Loading graph...")
    G = nx.read_graphml(input_path)
    print(f"   -> {G.number_of_nodes()} nodes, {G.number_of_edges()} edges.")

    edges_out = []
    for u, v, data in G.edges(data=True):
        prog = str(data.get("tfl_cycle_programme") or "").strip()
        route = str(data.get("tfl_cycle_route") or "").strip()
        if not prog and not route:
            continue
        # Ensure JSON-serializable node ids (GraphML usually gives strings)
        su, sv = str(u), str(v)
        edges_out.append({
            "source": su,
            "target": sv,
            "tfl_cycle_programme": prog,
            "tfl_cycle_route": route,
        })

    payload = {
        "source_graph": os.path.basename(input_path),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "edges": edges_out,
    }

    print(f"2. Writing {len(edges_out)} TfL-tagged edges to {output_path}...")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print("SUCCESS. Use this file to re-apply TfL tags after a fresh graph build.")
    return 0


if __name__ == "__main__":
    exit(main())
