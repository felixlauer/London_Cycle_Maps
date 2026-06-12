"""
Apply manual TfL cycle route edits from the debug app to the graph.
Reads: 3_pipeline/tfl_manual_edits.json
Uses tfl_osm_translate for legacy (source,target) -> osm_id fan-out after noded rebuilds.

Run after apply_tfl_export.py when export is ground truth. When changing paths, update GRAPH.md.
"""
from __future__ import annotations

import argparse
import json
import os

from graph_io import load_graph, save_graph, fast_path
from tfl_osm_translate import (
    build_osm_index,
    dedupe_preserve_order,
    edges_for_record,
    load_legacy_graph,
    split_semicolons,
)


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "1_data")
EDITS_PATH = os.path.join(SCRIPT_DIR, "tfl_manual_edits.json")
DEFAULT_GRAPH = os.path.join(DATA_DIR, "london_elev_final_tfl.graphml")


def _normalize_edge_tfl_tags(G, u, v):
    if not G.has_edge(u, v):
        return False
    ed = G.edges[u, v]
    before_prog = str(ed.get("tfl_cycle_programme", "")).strip()
    before_route = str(ed.get("tfl_cycle_route", "")).strip()
    prog_items = [p.lower() for p in split_semicolons(before_prog)]
    prog_items = dedupe_preserve_order(prog_items)
    route_items = dedupe_preserve_order(split_semicolons(before_route))
    after_prog = ";".join(prog_items)
    after_route = ";".join(route_items)
    changed = (after_prog != before_prog) or (after_route != before_route)
    if changed:
        ed["tfl_cycle_programme"] = after_prog
        ed["tfl_cycle_route"] = after_route
    return changed


def _merge_into_edge(G, u, v, programmes, routes):
    if not G.has_edge(u, v):
        return False
    ed = G.edges[u, v]
    prog_items = [p.lower() for p in split_semicolons(ed.get("tfl_cycle_programme", ""))]
    route_items = split_semicolons(ed.get("tfl_cycle_route", ""))
    prog_before = list(prog_items)
    route_before = list(route_items)
    for p in programmes:
        p = str(p).strip().lower()
        if p and p not in prog_items:
            prog_items.append(p)
    for r in routes:
        r = str(r).strip()
        if r and r not in route_items:
            route_items.append(r)
    prog_items = dedupe_preserve_order(prog_items)
    route_items = dedupe_preserve_order(route_items)
    changed = (prog_items != prog_before) or (route_items != route_before)
    if changed:
        ed["tfl_cycle_programme"] = ";".join(prog_items)
        ed["tfl_cycle_route"] = ";".join(route_items)
    return changed


def _deduplicate_edits(added, removed):
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
    added_deduped = [
        {
            "source": agg["source"],
            "target": agg["target"],
            "programme": ";".join(agg["programmes"]),
            "route": ";".join(agg["routes"]),
        }
        for agg in added_by_edge.values()
    ]
    return added_deduped, removed_deduped


def main():
    parser = argparse.ArgumentParser(description="Apply manual TfL edits to the graph")
    parser.add_argument("--input", default=DEFAULT_GRAPH, help="Input graph path")
    parser.add_argument("--output", default=None, help="Output graph path (default: overwrite input)")
    parser.add_argument("--edits", default=EDITS_PATH, help="Path to tfl_manual_edits.json")
    parser.add_argument(
        "--legacy-graph",
        default=None,
        help="Pre-noding graph for osm_id lookup when node ids no longer exist on the new mesh",
    )
    parser.add_argument(
        "--pickle-only",
        action="store_true",
        help="Save .gpickle only (skip GraphML write)",
    )
    args = parser.parse_args()
    input_path = os.path.normpath(os.path.join(SCRIPT_DIR, args.input))
    edits_path = os.path.normpath(os.path.join(SCRIPT_DIR, args.edits))
    output_path = os.path.normpath(os.path.join(SCRIPT_DIR, args.output or args.input))

    if not os.path.isfile(edits_path):
        print(f"ERROR: Edits file not found: {edits_path}")
        return 1
    if not os.path.isfile(input_path) and not os.path.isfile(fast_path(input_path)):
        print(f"ERROR: Graph not found: {input_path} (or .gpickle)")
        return 1

    with open(edits_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    added_raw = data.get("added", [])
    removed_raw = data.get("removed", [])
    added, removed = _deduplicate_edits(added_raw, removed_raw)

    print("--- APPLY TfL MANUAL EDITS ---")
    print(f"1. Loading graph from {input_path}...")
    G = load_graph(input_path)
    print(f"   -> {G.number_of_nodes()} nodes, {G.number_of_edges()} edges.")

    G_legacy = None
    if args.legacy_graph:
        try:
            G_legacy = load_legacy_graph(args.legacy_graph, SCRIPT_DIR)
        except FileNotFoundError as e:
            print(f"ERROR: {e}")
            return 1

    osm_index = build_osm_index(G)
    print(f"   -> osm_id index: {len(osm_index)} parent way(s).")

    touched = set()
    for rec in added + removed:
        for u, v in edges_for_record(rec, G, osm_index, G_legacy)[0]:
            touched.add((u, v))
    n_norm = sum(1 for u, v in touched if _normalize_edge_tfl_tags(G, u, v))
    if n_norm:
        print(f"   -> Normalized tags on {n_norm} edge(s) before applying edits.")

    print("2. Applying removals (osm_id fan-out)...")
    n_removed = n_remove_osm = n_remove_direct = n_remove_skipped = 0
    for rec in removed:
        edges, mode = edges_for_record(rec, G, osm_index, G_legacy)
        if not edges:
            n_remove_skipped += 1
            continue
        if mode == "osm_id":
            n_remove_osm += 1
        else:
            n_remove_direct += 1
        for u, v in edges:
            if G.has_edge(u, v):
                ed = G.edges[u, v]
                if str(ed.get("tfl_cycle_programme", "")).strip() or str(ed.get("tfl_cycle_route", "")).strip():
                    ed["tfl_cycle_programme"] = ""
                    ed["tfl_cycle_route"] = ""
                    n_removed += 1
    print(
        f"   -> Cleared {n_removed} edge(s) "
        f"({n_remove_osm} via osm_id, {n_remove_direct} direct, {n_remove_skipped} skipped)."
    )

    print("3. Applying additions (osm_id fan-out)...")
    n_added = n_add_osm = n_add_direct = n_add_skipped = 0
    for rec in added:
        edges, mode = edges_for_record(rec, G, osm_index, G_legacy)
        if not edges:
            n_add_skipped += 1
            continue
        if mode == "osm_id":
            n_add_osm += 1
        else:
            n_add_direct += 1
        programmes = [p.strip().lower() for p in (rec.get("programme") or "").split(";") if p.strip()]
        routes = [r.strip() or "manual" for r in (rec.get("route") or "").split(";") if r.strip()]
        programmes = [p for p in programmes if p in ("cycleway", "quietway", "superhighway")] or ["cycleway"]
        routes = routes or ["manual"]
        for u, v in edges:
            _normalize_edge_tfl_tags(G, u, v)
            if _merge_into_edge(G, u, v, programmes, routes):
                n_added += 1
    print(
        f"   -> Set/merged {n_added} edge(s) "
        f"({n_add_osm} via osm_id, {n_add_direct} direct, {n_add_skipped} skipped)."
    )

    print(f"4. Saving graph to {output_path}...")
    save_graph(G, output_path, write_graphml=not args.pickle_only, write_fast=True)
    print("SUCCESS.")
    return 0


if __name__ == "__main__":
    exit(main())
