"""
Apply manual TfL cycle route edits from the debug app to the graph.
Reads: 3_pipeline/tfl_manual_edits.json (produced by the Modify TfL mode in the debug app)
Reads: 1_data/london_elev_final_tfl.graphml (or --input)
Writes: same path (overwrites) or --output.

File format (tfl_manual_edits.json):
  {
    "added": [ { "source": "<node_id>", "target": "<node_id>", "programme": "cycleway|quietway|superhighway", "route": "Q15" } ],
    "removed": [ { "source": "<node_id>", "target": "<node_id>" } ],
    "history": [ { "type": "add"|"remove", ... } ]  // used by debug app for undo
  }

- Duplicates: before applying, added and removed lists are deduplicated (same segment can be clicked multiple times). Removed: unique by (source, target). Added: unique by (source, target), with programme and route merged from all occurrences.
- Removed: edges in "removed" get tfl_cycle_programme and tfl_cycle_route set to "". For a directed graph,
  if the reverse edge (target, source) exists, it is also cleared (same physical road, other direction).
- Added: edges in "added" get the given programme and route merged with existing (semicolon-separated).
  If the reverse edge (target, source) exists, it gets the same tags (both directions of the road).
Run after tag_tfl_routes.py. When changing paths or format, update 0_documentation/GRAPH.md.
"""
import json
import os
import argparse
import networkx as nx

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "1_data")
EDITS_PATH = os.path.join(SCRIPT_DIR, "tfl_manual_edits.json")
DEFAULT_GRAPH = os.path.join(DATA_DIR, "london_elev_final_tfl.graphml")

def _split_semicolons(val):
    """Split a semicolon-separated tag string into a list of stripped non-empty items."""
    if val is None:
        return []
    s = str(val)
    if not s.strip():
        return []
    return [p.strip() for p in s.split(";") if p.strip()]


def _dedupe_preserve_order(items, key_fn=None):
    """Deduplicate while preserving first-seen order."""
    if key_fn is None:
        key_fn = lambda x: x
    seen = set()
    out = []
    for it in items:
        k = key_fn(it)
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


def _normalize_edge_tfl_tags(G, u, v):
    """
    Remove accidental duplicates already present in graph tags (semicolon lists).
    Returns True if a change was applied.
    """
    if not G.has_edge(u, v):
        return False
    ed = G.edges[u, v]
    before_prog = str(ed.get("tfl_cycle_programme", "")).strip()
    before_route = str(ed.get("tfl_cycle_route", "")).strip()

    # programme: normalize to lowercase
    prog_items = [p.lower() for p in _split_semicolons(before_prog)]
    prog_items = _dedupe_preserve_order(prog_items)

    # route: keep original case, but dedupe by stripped value
    route_items = _split_semicolons(before_route)
    route_items = _dedupe_preserve_order(route_items)

    after_prog = ";".join(prog_items)
    after_route = ";".join(route_items)
    changed = (after_prog != before_prog) or (after_route != before_route)
    if changed:
        ed["tfl_cycle_programme"] = after_prog
        ed["tfl_cycle_route"] = after_route
    return changed


def _merge_into_edge(G, u, v, programmes, routes):
    """
    Merge programme(s) and route(s) into an edge's TfL tags if missing.
    Assumes edge tags are already normalized (no duplicates).
    Returns True if edge tags changed.
    """
    if not G.has_edge(u, v):
        return False
    ed = G.edges[u, v]

    prog_items = [p.lower() for p in _split_semicolons(ed.get("tfl_cycle_programme", ""))]
    route_items = _split_semicolons(ed.get("tfl_cycle_route", ""))

    prog_before = list(prog_items)
    route_before = list(route_items)

    for p in programmes:
        p = str(p).strip().lower()
        if not p:
            continue
        if p not in prog_items:
            prog_items.append(p)

    for r in routes:
        r = str(r).strip()
        if not r:
            continue
        if r not in route_items:
            route_items.append(r)

    prog_items = _dedupe_preserve_order(prog_items)
    route_items = _dedupe_preserve_order(route_items)

    changed = (prog_items != prog_before) or (route_items != route_before)
    if changed:
        ed["tfl_cycle_programme"] = ";".join(prog_items)
        ed["tfl_cycle_route"] = ";".join(route_items)
    return changed


def _deduplicate_edits(added, removed):
    """
    Remove duplicates before applying. Same segment can be clicked multiple times.
    - removed: unique by (source, target); keep first occurrence.
    - added: unique by (source, target); merge programme and route from all occurrences
      (semicolon-separated, unique values) so repeated clicks don't add the same edge twice.
    Returns (added_deduped, removed_deduped).
    """
    # Removed: unique (source, target)
    seen_removed = set()
    removed_deduped = []
    for rec in removed:
        u, v = rec.get("source"), rec.get("target")
        if u is None or v is None:
            continue
        key = (str(u), str(v))
        if key in seen_removed:
            continue
        seen_removed.add(key)
        removed_deduped.append(rec)

    # Added: unique (source, target), merge programme and route
    added_by_edge = {}
    for rec in added:
        u, v = rec.get("source"), rec.get("target")
        if u is None or v is None:
            continue
        key = (str(u), str(v))
        programme = (rec.get("programme") or "").strip().lower()
        route = (rec.get("route") or "").strip() or "manual"
        if programme not in ("cycleway", "quietway", "superhighway"):
            programme = "cycleway"
        if key not in added_by_edge:
            added_by_edge[key] = {"source": u, "target": v, "programmes": [], "routes": []}
        if programme not in added_by_edge[key]["programmes"]:
            added_by_edge[key]["programmes"].append(programme)
        if route not in added_by_edge[key]["routes"]:
            added_by_edge[key]["routes"].append(route)
    added_deduped = []
    for key, agg in added_by_edge.items():
        added_deduped.append({
            "source": agg["source"],
            "target": agg["target"],
            "programme": ";".join(agg["programmes"]),
            "route": ";".join(agg["routes"]),
        })
    return added_deduped, removed_deduped


def main():
    parser = argparse.ArgumentParser(description="Apply manual TfL edits to the graph")
    parser.add_argument("--input", default=DEFAULT_GRAPH, help="Input GraphML path")
    parser.add_argument("--output", default=None, help="Output GraphML path (default: overwrite input)")
    parser.add_argument("--edits", default=EDITS_PATH, help="Path to tfl_manual_edits.json")
    args = parser.parse_args()
    input_path = os.path.normpath(os.path.join(SCRIPT_DIR, args.input))
    edits_path = os.path.normpath(os.path.join(SCRIPT_DIR, args.edits))
    output_path = os.path.normpath(os.path.join(SCRIPT_DIR, args.output or args.input))

    if not os.path.isfile(edits_path):
        print(f"ERROR: Edits file not found: {edits_path}")
        return 1
    if not os.path.isfile(input_path):
        print(f"ERROR: Graph not found: {input_path}")
        return 1

    with open(edits_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    added_raw = data.get("added", [])
    removed_raw = data.get("removed", [])
    added, removed = _deduplicate_edits(added_raw, removed_raw)
    n_dup_added = len(added_raw) - len(added)
    n_dup_removed = len(removed_raw) - len(removed)

    print("--- APPLY TfL MANUAL EDITS ---")
    if n_dup_added or n_dup_removed:
        print(f"   Duplicate cleaner: {n_dup_added} duplicate add(s), {n_dup_removed} duplicate remove(s) -> {len(added)} add(s), {len(removed)} remove(s) to apply.")
    print(f"1. Loading graph from {input_path}...")
    G = nx.read_graphml(input_path)
    print(f"   -> {G.number_of_nodes()} nodes, {G.number_of_edges()} edges.")

    # Pre-normalize existing tags on all touched edges (and their reverse if present)
    touched = set()
    for rec in removed:
        u, v = rec.get("source"), rec.get("target")
        if u is None or v is None:
            continue
        touched.add((u, v))
        touched.add((v, u))
    for rec in added:
        u, v = rec.get("source"), rec.get("target")
        if u is None or v is None:
            continue
        touched.add((u, v))
        touched.add((v, u))
    n_norm = 0
    for (u, v) in touched:
        if _normalize_edge_tfl_tags(G, u, v):
            n_norm += 1
    if n_norm:
        print(f"   -> Normalized duplicate semicolon tags on {n_norm} edge(s) before applying edits.")

    print("2. Applying removals (including reverse direction when present)...")
    n_removed = 0
    for rec in removed:
        u, v = rec.get("source"), rec.get("target")
        if u is None or v is None:
            continue
        for (a, b) in [(u, v), (v, u)]:
            if G.has_edge(a, b):
                ed = G.edges[a, b]
                # Only write if not already empty
                if str(ed.get("tfl_cycle_programme", "")).strip() or str(ed.get("tfl_cycle_route", "")).strip():
                    ed["tfl_cycle_programme"] = ""
                    ed["tfl_cycle_route"] = ""
                    n_removed += 1
    print(f"   -> Cleared TfL tags on {n_removed} edge(s).")

    print("3. Applying additions (merge with existing; both directions when reverse edge exists)...")
    n_added = 0
    for rec in added:
        u, v = rec.get("source"), rec.get("target")
        if u is None or v is None:
            continue
        programmes = [p.strip().lower() for p in (rec.get("programme") or "").split(";") if p.strip()]
        routes = [r.strip() or "manual" for r in (rec.get("route") or "").split(";") if r.strip()]
        programmes = [p for p in programmes if p in ("cycleway", "quietway", "superhighway")]
        if not programmes:
            programmes = ["cycleway"]
        if not routes:
            routes = ["manual"]
        # Apply to (u,v) and, if present, (v,u) so both directions of the same road get the tag
        for (a, b) in [(u, v), (v, u)]:
            # Skip if edge doesn't exist
            if not G.has_edge(a, b):
                continue
            # Ensure normalized before merge (defensive; should already be done above)
            _normalize_edge_tfl_tags(G, a, b)
            # Only merge if it would actually change something (idempotent across repeated runs)
            if _merge_into_edge(G, a, b, programmes, routes):
                n_added += 1
    print(f"   -> Set/merged TfL tags on {n_added} edge(s).")

    print(f"4. Saving graph to {output_path}...")
    nx.write_graphml(G, output_path)
    print("SUCCESS. Re-run debug app to see updated TfL overlay.")
    return 0


if __name__ == "__main__":
    exit(main())
