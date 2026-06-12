"""
Resolve pre-noding (source, target) node pairs to osm_id and fan out TfL tags on noded meshes.

Used by apply_tfl_export.py and apply_tfl_manual_edits.py after graph rebuilds.
"""
from __future__ import annotations

import ast
from collections import defaultdict

import networkx as nx

from graph_io import load_graph, fast_path


def split_semicolons(val) -> list[str]:
    if val is None:
        return []
    s = str(val)
    if not s.strip():
        return []
    return [p.strip() for p in s.split(";") if p.strip()]


def dedupe_preserve_order(items, key_fn=None) -> list:
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


def parse_node_id(node_id):
    """Parse debug-app / export node id (tuple or '(lon, lat)' string)."""
    if isinstance(node_id, tuple) and len(node_id) == 2:
        return (round(float(node_id[0]), 6), round(float(node_id[1]), 6))
    s = str(node_id).strip()
    try:
        parsed = ast.literal_eval(s)
        if isinstance(parsed, (list, tuple)) and len(parsed) == 2:
            return (round(float(parsed[0]), 6), round(float(parsed[1]), 6))
    except (ValueError, SyntaxError, TypeError):
        pass
    return s


def edge_key_pairs(source, target) -> set[tuple]:
    u = parse_node_id(source)
    v = parse_node_id(target)
    keys = {(u, v), (v, u), (str(u), str(v)), (str(v), str(u))}
    keys.add((str(source), str(target)))
    keys.add((str(target), str(source)))
    return keys


def osm_id_on_edge(G, source, target) -> str | None:
    for u, v in edge_key_pairs(source, target):
        if G.has_edge(u, v):
            oid = str(G.edges[u, v].get("osm_id", "")).strip()
            if oid:
                return oid
    return None


def build_osm_index(G) -> dict[str, list[tuple]]:
    index: dict[str, list[tuple]] = defaultdict(list)
    for u, v, data in G.edges(data=True):
        oid = str(data.get("osm_id", "")).strip()
        if oid:
            index[oid].append((u, v))
    return dict(index)


def resolve_osm_id(rec, G, G_legacy) -> str | None:
    """Order: explicit osm_id on record -> new graph -> legacy graph."""
    explicit = str(rec.get("osm_id") or "").strip()
    if explicit:
        return explicit
    source, target = rec.get("source"), rec.get("target")
    if source is None or target is None:
        return None
    oid = osm_id_on_edge(G, source, target)
    if oid:
        return oid
    if G_legacy is not None:
        return osm_id_on_edge(G_legacy, source, target)
    return None


def edges_for_record(rec, G, osm_index, G_legacy) -> tuple[list[tuple], str | None]:
    """Return (edges, mode) where mode is 'osm_id', 'direct', or None."""
    source, target = rec.get("source"), rec.get("target")
    if source is None or target is None:
        return [], None

    osm_id = resolve_osm_id(rec, G, G_legacy)
    if osm_id and osm_id in osm_index:
        return list(osm_index[osm_id]), "osm_id"

    direct = []
    seen = set()
    for u, v in edge_key_pairs(source, target):
        if G.has_edge(u, v) and (u, v) not in seen:
            seen.add((u, v))
            direct.append((u, v))
    if direct:
        return direct, "direct"
    return [], None


def merge_tfl_tag_strings(existing_prog: str, existing_route: str, prog_add: str, route_add: str) -> tuple[str, str]:
    """Merge semicolon-separated programme/route strings (deduped, programmes lowercased)."""
    prog_items = [p.lower() for p in split_semicolons(existing_prog)]
    route_items = split_semicolons(existing_route)
    for p in split_semicolons(prog_add):
        p = p.lower()
        if p and p not in prog_items:
            prog_items.append(p)
    for r in split_semicolons(route_add):
        if r and r not in route_items:
            route_items.append(r)
    return ";".join(dedupe_preserve_order(prog_items)), ";".join(dedupe_preserve_order(route_items))


def aggregate_export_tags_by_osm_id(
    export_edges: list[dict],
    G,
    G_legacy,
    osm_index: dict[str, list[tuple]],
) -> tuple[dict[str, dict[str, str]], int, int, int]:
    """
    Map export records to osm_id and merge tags per parent way.
    Returns (osm_id -> {programme, route}, records_resolved, unique_osm_ids, records_skipped).
    """
    by_osm: dict[str, dict[str, str]] = {}
    resolved = 0
    skipped = 0
    for rec in export_edges:
        osm_id = resolve_osm_id(rec, G, G_legacy)
        if not osm_id or osm_id not in osm_index:
            skipped += 1
            continue
        resolved += 1
        prog = str(rec.get("tfl_cycle_programme") or "").strip()
        route = str(rec.get("tfl_cycle_route") or "").strip()
        if osm_id not in by_osm:
            by_osm[osm_id] = {"programme": "", "route": ""}
        merged_prog, merged_route = merge_tfl_tag_strings(
            by_osm[osm_id]["programme"], by_osm[osm_id]["route"], prog, route
        )
        by_osm[osm_id]["programme"] = merged_prog
        by_osm[osm_id]["route"] = merged_route
    return by_osm, resolved, len(by_osm), skipped


def load_legacy_graph(legacy_path: str, script_dir: str):
    """Load optional legacy graph; return None if path is empty."""
    if not legacy_path:
        return None
    import os

    path = os.path.normpath(os.path.join(script_dir, legacy_path))
    if not os.path.isfile(path) and not os.path.isfile(fast_path(path)):
        raise FileNotFoundError(f"Legacy graph not found: {path} (or .gpickle)")
    print(f"   Loading legacy graph for osm_id lookup: {path}...")
    G_legacy = load_graph(path)
    print(f"   -> Legacy: {G_legacy.number_of_nodes()} nodes, {G_legacy.number_of_edges()} edges.")
    return G_legacy


def apply_tags_to_osm_ids(G, osm_index: dict, tags_by_osm: dict[str, dict[str, str]]) -> int:
    """Set tfl_cycle_programme/route on every directed edge for each osm_id. Returns edge count."""
    n = 0
    for osm_id, tags in tags_by_osm.items():
        prog = tags.get("programme", "")
        route = tags.get("route", "")
        for u, v in osm_index.get(osm_id, []):
            if not G.has_edge(u, v):
                continue
            G.edges[u, v]["tfl_cycle_programme"] = prog
            G.edges[u, v]["tfl_cycle_route"] = route
            n += 1
    return n
