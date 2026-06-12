"""
Spatial matching of graph edges to park polygons, buffered lines, and point radii.

Used by tag_attractions_osm.py and apply_attraction_manual.py.
When changing tag names or thresholds, update 0_documentation/GRAPH.md.
"""
from __future__ import annotations

import math
from typing import Any

import networkx as nx
from shapely.geometry import LineString, Point, Polygon, shape as geojson_to_shapely
from shapely.ops import transform
from shapely.strtree import STRtree
from shapely.wkt import loads as wkt_loads

try:
    from pyproj import Transformer

    _TO_BNG = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
    _TO_WGS = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
    _HAS_PYPROJ = True
except Exception:
    _HAS_PYPROJ = False

ALIGNMENT_THRESHOLD = 0.5
DEG_TO_M_APPROX = 111000.0
DEFAULT_RIVER_BUFFER_M = 200.0
DEFAULT_SIGHT_RADIUS_M = 200.0


def _length_m_float(data: dict) -> float:
    try:
        return float(data.get("length") or 0)
    except (TypeError, ValueError):
        return 0.0


def _edge_linestring(G: nx.DiGraph, u, v, data: dict) -> LineString | None:
    wkt = data.get("geometry")
    if wkt and str(wkt).strip():
        try:
            geom = wkt_loads(str(wkt))
            if not geom.is_empty:
                return geom
        except Exception:
            pass
    try:
        p1 = (float(G.nodes[u]["x"]), float(G.nodes[u]["y"]))
        p2 = (float(G.nodes[v]["x"]), float(G.nodes[v]["y"]))
        return LineString([p1, p2])
    except (KeyError, TypeError, ValueError):
        return None


def edge_geometries(G: nx.DiGraph) -> list[tuple[Any, Any, LineString, float]]:
    """All edges with parseable geometry: (u, v, LineString, length_m)."""
    out = []
    for u, v, data in G.edges(data=True):
        geom = _edge_linestring(G, u, v, data)
        if geom is None or geom.is_empty:
            continue
        out.append((u, v, geom, _length_m_float(data)))
    return out


def build_edge_strtree(edge_list: list[tuple]) -> tuple[STRtree, list[tuple]]:
    geoms = [e[2] for e in edge_list]
    return STRtree(geoms), edge_list


def merge_attraction_name(edge_data: dict, name: str) -> None:
    name = (name or "").strip()
    if not name:
        return
    existing = str(edge_data.get("attraction_name", "") or "").strip()
    parts = [p.strip() for p in existing.split(";") if p.strip()] if existing else []
    if name not in parts:
        parts.append(name)
    edge_data["attraction_name"] = ";".join(parts)


def _overlap_ratio(edge_geom: LineString, zone_geom) -> float:
    edge_len = edge_geom.length
    if edge_len < 1e-15:
        return 0.0
    try:
        overlap = edge_geom.intersection(zone_geom)
        overlap_len = overlap.length if overlap and not overlap.is_empty else 0.0
    except Exception:
        return 0.0
    return overlap_len / edge_len


def _tag_edges_in_zone(
    G: nx.DiGraph,
    edge_list: list[tuple],
    tree: STRtree,
    zone_geom,
    *,
    set_park: bool = False,
    set_river: bool = False,
    set_sight: bool = False,
    name: str = "",
    threshold: float = ALIGNMENT_THRESHOLD,
) -> int:
    if zone_geom is None or zone_geom.is_empty:
        return 0
    try:
        idx = tree.query(zone_geom)
        indices = list(idx)
    except TypeError:
        indices = [idx] if idx is not None else []
    except Exception:
        return 0

    tagged = 0
    for j in indices:
        u, v, edge_geom, _length_m = edge_list[j]
        if _overlap_ratio(edge_geom, zone_geom) < threshold:
            continue
        if not G.has_edge(u, v):
            continue
        ed = G.edges[u, v]
        if set_park:
            ed["is_park"] = "yes"
        if set_river:
            ed["is_river"] = "yes"
        if set_sight:
            ed["is_sight"] = "yes"
        merge_attraction_name(ed, name)
        tagged += 1
    return tagged


def tag_polygon(
    G: nx.DiGraph,
    polygon_wgs84,
    *,
    edge_list: list[tuple] | None = None,
    tree: STRtree | None = None,
    name: str = "",
    threshold: float = ALIGNMENT_THRESHOLD,
) -> int:
    if edge_list is None or tree is None:
        edge_list = edge_geometries(G)
        tree, edge_list = build_edge_strtree(edge_list)
    return _tag_edges_in_zone(
        G, edge_list, tree, polygon_wgs84,
        set_park=True, name=name, threshold=threshold,
    )


def tag_river_polygon(
    G: nx.DiGraph,
    polygon_wgs84,
    *,
    edge_list: list[tuple] | None = None,
    tree: STRtree | None = None,
    name: str = "",
    threshold: float = ALIGNMENT_THRESHOLD,
) -> int:
    if edge_list is None or tree is None:
        edge_list = edge_geometries(G)
        tree, edge_list = build_edge_strtree(edge_list)
    return _tag_edges_in_zone(
        G, edge_list, tree, polygon_wgs84,
        set_river=True, name=name, threshold=threshold,
    )


def _to_bng(geom):
    if not _HAS_PYPROJ:
        return geom
    return transform(_TO_BNG.transform, geom)


def _buffer_wgs84_from_bng(bng_geom, buffer_m: float):
    if _HAS_PYPROJ:
        buffered = bng_geom.buffer(float(buffer_m))
        return transform(_TO_WGS.transform, buffered)
    buf_deg = float(buffer_m) / DEG_TO_M_APPROX
    return bng_geom.buffer(buf_deg)


def tag_buffered_line(
    G: nx.DiGraph,
    line_wgs84: LineString,
    buffer_m: float,
    *,
    edge_list: list[tuple] | None = None,
    tree: STRtree | None = None,
    name: str = "",
    threshold: float = ALIGNMENT_THRESHOLD,
) -> int:
    if line_wgs84 is None or line_wgs84.is_empty or len(line_wgs84.coords) < 2:
        return 0
    bng_line = _to_bng(line_wgs84)
    zone = _buffer_wgs84_from_bng(bng_line, buffer_m)
    if edge_list is None or tree is None:
        edge_list = edge_geometries(G)
        tree, edge_list = build_edge_strtree(edge_list)
    return _tag_edges_in_zone(
        G, edge_list, tree, zone,
        set_river=True, name=name, threshold=threshold,
    )


def tag_point_radius(
    G: nx.DiGraph,
    lon: float,
    lat: float,
    radius_m: float,
    *,
    edge_list: list[tuple] | None = None,
    tree: STRtree | None = None,
    name: str = "",
    threshold: float = ALIGNMENT_THRESHOLD,
) -> int:
    pt = Point(float(lon), float(lat))
    bng_pt = _to_bng(pt)
    zone = _buffer_wgs84_from_bng(bng_pt, radius_m)
    if edge_list is None or tree is None:
        edge_list = edge_geometries(G)
        tree, edge_list = build_edge_strtree(edge_list)
    return _tag_edges_in_zone(
        G, edge_list, tree, zone,
        set_sight=True, name=name, threshold=threshold,
    )


def geometry_from_geojson(geom_dict: dict):
    """Return Shapely geometry from GeoJSON geometry dict."""
    if not geom_dict:
        return None
    return geojson_to_shapely(geom_dict)


def region_tagging_zone(region: dict):
    """
    Shapely polygon (WGS84) used for spatial matching — same zones as apply_attraction_manual.
    Park / river: drawn polygon. Sight: point + radius_m. Legacy river LineString + buffer_m still supported.
    """
    rtype = str(region.get("type", "")).strip().lower()
    geom_dict = region.get("geometry")
    if not geom_dict:
        return None

    if rtype in ("park", "river"):
        geom = geometry_from_geojson(geom_dict)
        if geom is None or geom.is_empty:
            return None
        if geom.geom_type in ("Polygon", "MultiPolygon"):
            return geom
        if rtype == "river" and geom.geom_type == "LineString":
            buffer_m = float(region.get("buffer_m") or DEFAULT_RIVER_BUFFER_M)
            bng_line = _to_bng(geom)
            return _buffer_wgs84_from_bng(bng_line, buffer_m)
        return None

    if rtype == "sight":
        if geom_dict.get("type") == "Point":
            coords = geom_dict.get("coordinates", [])
            if len(coords) < 2:
                return None
            lon, lat = float(coords[0]), float(coords[1])
        else:
            pt = geometry_from_geojson(geom_dict)
            if pt is None or pt.is_empty:
                return None
            lon, lat = float(pt.x), float(pt.y)
        radius_m = float(region.get("radius_m") or DEFAULT_SIGHT_RADIUS_M)
        bng_pt = _to_bng(Point(lon, lat))
        return _buffer_wgs84_from_bng(bng_pt, radius_m)

    return None


def zone_to_leaflet_rings(zone_geom) -> list[list[list[float]]]:
    """Exterior rings for Leaflet Polygon: [[[lat, lon], ...], ...]."""
    if zone_geom is None or zone_geom.is_empty:
        return []
    polys = []
    if zone_geom.geom_type == "Polygon":
        polys = [zone_geom]
    elif zone_geom.geom_type == "MultiPolygon":
        polys = list(zone_geom.geoms)
    else:
        return []
    rings = []
    for poly in polys:
        if poly.is_empty:
            continue
        ring = [[float(c[1]), float(c[0])] for c in poly.exterior.coords]
        if len(ring) >= 3:
            rings.append(ring)
    return rings


def clear_manual_river_sight_tags(G: nx.DiGraph) -> tuple[int, int]:
    """Clear is_river and is_sight on all edges before re-applying manual regions JSON."""
    rivers = sights = 0
    for _u, _v, d in G.edges(data=True):
        if str(d.get("is_river", "")).strip().lower() == "yes":
            d["is_river"] = ""
            rivers += 1
        if str(d.get("is_sight", "")).strip().lower() == "yes":
            d["is_sight"] = ""
            sights += 1
    return rivers, sights


def clear_osm_park_tags(G: nx.DiGraph) -> int:
    """Clear is_park on all edges (OSM re-apply). Does not touch is_river/is_sight."""
    n = 0
    for _u, _v, d in G.edges(data=True):
        if str(d.get("is_park", "")).strip().lower() == "yes":
            d["is_park"] = ""
            n += 1
    return n


def init_attraction_attrs(G: nx.DiGraph) -> None:
    """Ensure attraction keys exist on every edge."""
    for _u, _v, d in G.edges(data=True):
        for key in ("is_park", "is_river", "is_sight", "attraction_name"):
            if key not in d:
                d[key] = ""
