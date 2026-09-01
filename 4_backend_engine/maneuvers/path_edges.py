"""Convert a Tuned A* node path into maneuver-engine edge dicts."""
from __future__ import annotations

from typing import Any, Callable


def graph_path_to_edges(
    G,
    path_nodes: list,
    *,
    extract_segment_geometry: Callable[[Any, Any], list],
) -> list[dict]:
    """
    Build directed edge records for maneuvers.engine from a node path.

    ``extract_segment_geometry(u, v)`` must return [[lat, lon], ...]
    (same as ``app.extract_segment_geometry``).
    """
    if len(path_nodes) < 2:
        return []

    edges: list[dict] = []
    for i in range(len(path_nodes) - 1):
        u, v = path_nodes[i], path_nodes[i + 1]
        attr = _edge_attr(G, u, v)
        coords = extract_segment_geometry(u, v) or []
        if len(coords) < 2:
            # Graph nodes are (lon, lat)
            try:
                coords = [
                    [float(u[1]), float(u[0])],
                    [float(v[1]), float(v[0])],
                ]
            except (TypeError, IndexError, ValueError):
                coords = []
        try:
            deg = int(G.degree(v))
        except Exception:
            deg = 2
        edges.append({
            "u": u,
            "v": v,
            "coords": coords,
            "length": float(attr.get("length") or 0.0),
            "name": attr.get("name", ""),
            "type": attr.get("type", ""),
            "cycleway": attr.get("cycleway", ""),
            "cycleway_left": attr.get("cycleway_left", ""),
            "cycleway_right": attr.get("cycleway_right", ""),
            "cycleway_both": attr.get("cycleway_both", ""),
            "junction": attr.get("junction", ""),
            "lcn_ref": attr.get("lcn_ref", ""),
            "rcn_ref": attr.get("rcn_ref", ""),
            "ncn_ref": attr.get("ncn_ref", ""),
            "cycle_network": attr.get("cycle_network", ""),
            "tfl_cycle_programme": attr.get("tfl_cycle_programme", ""),
            "street:name": attr.get("street:name") or attr.get("street_name") or "",
            "is_sidepath:of:name": (
                attr.get("is_sidepath:of:name") or attr.get("is_sidepath_of_name") or ""
            ),
            "_junction_degree": deg,
        })
    return edges


def _edge_attr(G, u, v) -> dict:
    data = G.get_edge_data(u, v)
    if data is None:
        return {}
    if getattr(G, "is_multigraph", lambda: False)():
        if 0 in data:
            return dict(data[0])
        return dict(next(iter(data.values())))
    return dict(data)


def concatenate_node_paths(paths: list[list]) -> list:
    """Join leg node paths without duplicating joint nodes."""
    if not paths:
        return []
    out = list(paths[0])
    for p in paths[1:]:
        if not p:
            continue
        out.extend(p[1:] if out else p)
    return out
