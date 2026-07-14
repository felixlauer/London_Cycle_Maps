"""
Debug backend: overlay endpoints and /inspect. Port 5001. Graph: london_elev_final_tfl.gpickle (fast) or .graphml fallback.
When changing, update 0_documentation/APP_DEBUG.md
"""
from flask import Flask, jsonify, request
from flask_cors import CORS
import networkx as nx
from shapely.wkt import loads as load_wkt
from shapely.geometry import Point, LineString
from sqlalchemy import create_engine, text
import os
import sys
import time
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "3_pipeline"))
from graph_io import load_graph, fast_path
from attraction_spatial import (
    region_tagging_zone,
    zone_to_leaflet_rings,
)

import tfl_live
import live_disruptions
from barrier_clusters import barrier_cluster_meta, cluster_legend
from cycleway_clusters import classify_cycleway_edge, cluster_legend as cycleway_cluster_legend
from park_opening_hours import (
    LONDON_TZ,
    build_request_hours_context,
    is_park_edge_open,
    london_now,
)

# --- CONFIGURATION (set DB_PASS etc. via env or .env; do not commit secrets) ---
GRAPH_PATH = os.path.join("..", "1_data", "london_elev_final_tfl.graphml")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASS = os.environ.get("DB_PASS", "")
DB_NAME = os.environ.get("DB_NAME", "london_routing")
DB_HOST = os.environ.get("DB_HOST", "localhost")

app = Flask(__name__)
CORS(app)

# Flask debug reloader imports this module twice (parent watcher + child server).
# Default off — set FLASK_USE_RELOADER=1 only if you need auto-reload on code changes.
USE_RELOADER = os.environ.get("FLASK_USE_RELOADER", "").lower() in ("1", "true", "yes")

G = None
node_data = []


def _should_run_bootstrap():
    if not USE_RELOADER:
        return True
    return os.environ.get("WERKZEUG_RUN_MAIN") == "true"


def bootstrap_debug_engine():
    global G, node_data
    t_boot = time.perf_counter()
    print("--- STARTING DEBUG ENGINE (PORT 5001) ---")
    if not os.path.exists(GRAPH_PATH) and not os.path.exists(fast_path(GRAPH_PATH)):
        print(f"CRITICAL ERROR: {GRAPH_PATH} (or .gpickle) not found.")
        exit()

    print(f"Loading graph (fast pickle preferred): {GRAPH_PATH}...")
    t0 = time.perf_counter()
    G = load_graph(GRAPH_PATH)
    print(f"Graph ready with {len(G.nodes())} nodes ({time.perf_counter() - t0:.1f}s).")

    node_data = []
    for node, data in G.nodes(data=True):
        if 'x' in data and 'y' in data:
            node_data.append({'id': node, 'x': float(data['x']), 'y': float(data['y'])})

    t0 = time.perf_counter()
    live_disruptions.init(G)
    if not live_disruptions.live_fetch_enabled():
        print(f"--> Live disruption index: init only, fetch off ({time.perf_counter() - t0:.1f}s)")
    else:
        live_disruptions.start_background_refresh()
        print(f"--> Live disruption index: {time.perf_counter() - t0:.1f}s")

    t0 = time.perf_counter()
    build_all_debug_caches()
    print(f"--> Debug cache build: {time.perf_counter() - t0:.1f}s")
    print(f"--- Bootstrap complete in {time.perf_counter() - t_boot:.1f}s ---")

def get_nearest_node(lat, lon):
    best_node = None
    min_dist = float('inf')
    for node in node_data:
        dist = (node['y'] - lat)**2 + (node['x'] - lon)**2
        if dist < min_dist:
            min_dist = dist
            best_node = node['id']
    return best_node

def extract_segment_geometry(u, v):
    """Polyline [[lat, lon], ...] for edge u→v. Never mutates G (thread-safe)."""
    import edge_geom_store

    edge_data = G.get_edge_data(u, v)
    if not edge_data:
        return edge_geom_store.coords_for_edge(None, G, u, v)
    if G.is_multigraph():
        edge_data = next(iter(edge_data.values()))
    return edge_geom_store.coords_for_edge(edge_data, G, u, v)

BAD_SURFACES = [
    'grass', 'dirt', 'sand', 'ground', 'unpaved', 'sett', 'gravel', 'wood',
    'fine_gravel', 'earth', 'mud', 'woodchips', 'cobblestone', 'pebblestone',
    'clay', 'grit', 'grass_paver', 'stone', 'unhewn_cobblestone', 'stepping_stones'
]
BAD_SMOOTHNESS = ['bad', 'very_bad', 'horrible', 'impassable']

LIT_VALUES = ['yes', 'true', '24/7', 'on', 'designated']

STEEP_CACHE = []
SURFACE_CACHE = []
UNLIT_CACHE = []

def get_edge_coords(u, v, data):
    """Overlay helper: same resolution as extract_segment_geometry (no graph writeback)."""
    import edge_geom_store

    return edge_geom_store.coords_for_edge(data, G, u, v)

def make_bounds(coords):
    lats = [p[0] for p in coords]
    lons = [p[1] for p in coords]
    return (min(lats), max(lats), min(lons), max(lons))

def get_edge_midpoint(u, v, data, coords=None):
    """Return (lat, lon) of edge midpoint for point-based overlays."""
    if coords is None:
        coords = get_edge_coords(u, v, data)
    if not coords:
        return None
    n = len(coords)
    if n == 0:
        return None
    if n == 1:
        return (coords[0][0], coords[0][1])
    mid = n // 2
    if n % 2 == 0:
        lat = (coords[mid - 1][0] + coords[mid][0]) / 2.0
        lon = (coords[mid - 1][1] + coords[mid][1]) / 2.0
    else:
        lat, lon = coords[mid][0], coords[mid][1]
    return (lat, lon)

# Caches for cycleway, HGV, and point-based overlays (filled in build_all_debug_caches)
CYCLEWAY_CACHE = []  # meaningful cycleway* infra with cluster metadata
HGV_BANNED_CACHE = []
TRAFFIC_CALMING_POINTS = []       # way-based: [{lat, lon, type, source: 'way'}, ...]
TRAFFIC_CALMING_POINT_POINTS = [] # point-based: [{lat, lon, type, source: 'point'}, ...]
JUNCTION_POINTS = []             # [{lat, lon, type}, ...] (edge-based: roundabout, circular, etc.)

# Node-based point caches (filled in build_all_debug_caches); graph node: x=lon, y=lat
BARRIER_POINTS = []          # [{lat, lon, type}, ...]
TRAFFIC_SIGNALS_POINTS = []  # [{lat, lon}, ...]
MINI_ROUNDABOUT_POINTS = []
CROSSING_POINTS = []
GIVE_WAY_POINTS = []
STOP_POINTS = []

# TfL cycle routes (edges with tfl_cycle_programme); programme = first category for color
TFL_ROUTES_CACHE = []  # [{id, p, b, programme, route}, ...]

# Attraction / green mode (is_park, is_river, is_sight on graph edges)
ATTRACTION_PARK_CACHE = []   # [{id, p, b, name, opening_hours}, ...]
ATTRACTION_RIVER_CACHE = []
ATTRACTION_SIGHT_CACHE = []

MAX_SEGMENTS_LIMIT = 20000
GRAPH_NETWORK_LIMIT = 15000
GRAPH_NETWORK_CACHE = []  # [{id, p, b, h}, ...] one entry per physical edge (undirected)

def _edge_display_point(edge_data, lat_key, lon_key, coords=None):
    """Return (lat, lon) for edge point feature: stored position or edge geometry midpoint."""
    lat = edge_data.get(lat_key)
    lon = edge_data.get(lon_key)
    if lat is not None and lon is not None:
        try:
            return float(lat), float(lon)
        except (TypeError, ValueError):
            pass
    if coords:
        n = len(coords)
        if n == 0:
            return None, None
        if n == 1:
            return coords[0][0], coords[0][1]
        mid = n // 2
        if n % 2 == 0:
            return (coords[mid - 1][0] + coords[mid][0]) / 2.0, (coords[mid - 1][1] + coords[mid][1]) / 2.0
        return coords[mid][0], coords[mid][1]
    wkt = edge_data.get('geometry')
    if wkt:
        try:
            line = load_wkt(wkt)
            if line and hasattr(line, 'interpolate'):
                mid = line.interpolate(0.5, normalized=True)
                return float(mid.y), float(mid.x)
        except Exception:
            pass
    return None, None


def _is_yes_attr(val) -> bool:
    return str(val or "").strip().lower() in ("yes", "true", "1")


def build_all_debug_caches():
    """One pass over edges for overlay caches, graph network, and edge point features."""
    global GRAPH_NETWORK_CACHE, ATTRACTION_PARK_CACHE, ATTRACTION_RIVER_CACHE, ATTRACTION_SIGHT_CACHE
    ATTRACTION_PARK_CACHE = []
    ATTRACTION_RIVER_CACHE = []
    ATTRACTION_SIGHT_CACHE = []
    print("--- PRE-PROCESSING GRAPH FOR DEBUGGING (single edge pass) ---")
    print(f"--> Scanning {G.number_of_edges()} edges...")
    steep_ignored = 0
    steep_error = 0
    surface_count = 0
    unlit_count = 0
    cycleway_counts = {1: 0, 2: 0, 3: 0}
    hgv_count = 0
    tc_points = 0
    jn_points = 0
    tfl_count = 0
    attr_park = attr_river = attr_sight = 0
    n_barrier = n_gw = n_stop = n_tc_pt = 0
    seen_physical = set()
    GRAPH_NETWORK_CACHE = []

    for u, v, data in G.edges(data=True):
        coords = None
        grade = float(data.get('grade', 0.0))
        lit_raw = str(data.get('lit', '')).lower().strip()

        # Steep cache: everything above 3.3%
        if grade >= 0.033:
            if grade >= 0.40:
                steep_error += 1
            if coords is None:
                coords = get_edge_coords(u, v, data)
            if coords:
                STEEP_CACHE.append({
                    "id": f"{u}-{v}",
                    "g": round(grade, 3),
                    "p": coords,
                    "b": make_bounds(coords)
                })
        else:
            steep_ignored += 1

        # Surface cache: bad road surface, bad cycleway_surface, bad smoothness, or no surface info
        surface_val = str(data.get('surface', '')).lower().strip()
        cycleway_surface_val = str(data.get('cycleway_surface', '')).lower().strip()
        smoothness_val = str(data.get('smoothness', '')).lower().strip()
        has_surface_info = bool(surface_val and surface_val != 'none')
        has_cycleway_surface_info = bool(cycleway_surface_val and cycleway_surface_val != 'none')
        if surface_val in BAD_SURFACES:
            if coords is None:
                coords = get_edge_coords(u, v, data)
            if coords:
                surface_count += 1
                SURFACE_CACHE.append({
                    "id": f"s-{u}-{v}", "t": "surface", "s": surface_val,
                    "p": coords, "b": make_bounds(coords)
                })
        elif cycleway_surface_val in BAD_SURFACES:
            if coords is None:
                coords = get_edge_coords(u, v, data)
            if coords:
                surface_count += 1
                SURFACE_CACHE.append({
                    "id": f"cs-{u}-{v}", "t": "cycleway_surface", "s": cycleway_surface_val,
                    "p": coords, "b": make_bounds(coords)
                })
        elif smoothness_val in BAD_SMOOTHNESS:
            if coords is None:
                coords = get_edge_coords(u, v, data)
            if coords:
                surface_count += 1
                SURFACE_CACHE.append({
                    "id": f"sm-{u}-{v}", "t": "smoothness", "s": smoothness_val,
                    "p": coords, "b": make_bounds(coords)
                })
        elif not has_surface_info and not has_cycleway_surface_info:
            if coords is None:
                coords = get_edge_coords(u, v, data)
            if coords:
                surface_count += 1
                SURFACE_CACHE.append({
                    "id": f"nd-{u}-{v}", "t": "no_data", "s": "",
                    "p": coords, "b": make_bounds(coords)
                })

        # Unlit cache: anything NOT confirmed lit
        if lit_raw not in LIT_VALUES:
            if coords is None:
                coords = get_edge_coords(u, v, data)
            if coords:
                unlit_count += 1
                lit_type = "no" if lit_raw in ['no', 'limited'] else "unknown"
                UNLIT_CACHE.append({
                    "id": f"l-{u}-{v}",
                    "t": lit_type,
                    "p": coords,
                    "b": make_bounds(coords)
                })

        # Cycleway overlay: meaningful cycleway* values only (not no / crossing / segregated=yes)
        cw_meta = classify_cycleway_edge(data)
        if cw_meta:
            if coords is None:
                coords = get_edge_coords(u, v, data)
            if coords:
                cluster = cw_meta["cluster"]
                cycleway_counts[cluster] = cycleway_counts.get(cluster, 0) + 1
                CYCLEWAY_CACHE.append({
                    "id": f"cw-{u}-{v}",
                    "p": coords,
                    "b": make_bounds(coords),
                    "c": cw_meta["cluster_key"],
                    "v": cw_meta["tag"],
                    "color": cw_meta["cluster_color"],
                })

        # HGV banned: hgv=no
        hgv_val = str(data.get('hgv', '')).lower().strip()
        if hgv_val == 'no':
            if coords is None:
                coords = get_edge_coords(u, v, data)
            if coords:
                hgv_count += 1
                HGV_BANNED_CACHE.append({
                    "id": f"hgv-{u}-{v}", "p": coords, "b": make_bounds(coords)
                })

        # Traffic calming: way-based (midpoint) and point-based (stored position)
        tc = str(data.get('traffic_calming', '')).strip()
        if tc:
            pt = get_edge_midpoint(u, v, data, coords)
            if pt:
                tc_points += 1
                TRAFFIC_CALMING_POINTS.append({"lat": pt[0], "lon": pt[1], "type": tc, "source": "way"})
        jn = str(data.get('junction', '')).strip()
        if jn:
            pt = get_edge_midpoint(u, v, data, coords)
            if pt:
                jn_points += 1
                JUNCTION_POINTS.append({"lat": pt[0], "lon": pt[1], "type": jn})

        # TfL cycle routes (cycleway, quietway, superhighway)
        tfl_prog = str(data.get('tfl_cycle_programme', '')).strip()
        if tfl_prog:
            if coords is None:
                coords = get_edge_coords(u, v, data)
            if coords:
                tfl_count += 1
                programme = tfl_prog.split(';')[0].strip().lower() if tfl_prog else ''
                route = str(data.get('tfl_cycle_route', '')).strip()
                TFL_ROUTES_CACHE.append({
                    "id": f"tfl-{u}-{v}", "p": coords, "b": make_bounds(coords),
                    "programme": programme, "route": route
                })

        name = str(data.get("attraction_name", "") or "").strip()
        if _is_yes_attr(data.get("is_park")):
            if coords is None:
                coords = get_edge_coords(u, v, data)
            if coords:
                attr_park += 1
                ATTRACTION_PARK_CACHE.append({
                    "id": f"park-{u}-{v}", "p": coords, "b": make_bounds(coords), "name": name,
                    "opening_hours": str(data.get("opening_hours", "") or "").strip(),
                })
        if _is_yes_attr(data.get("is_river")):
            if coords is None:
                coords = get_edge_coords(u, v, data)
            if coords:
                attr_river += 1
                ATTRACTION_RIVER_CACHE.append({
                    "id": f"river-{u}-{v}", "p": coords, "b": make_bounds(coords), "name": name,
                })
        if _is_yes_attr(data.get("is_sight")):
            if coords is None:
                coords = get_edge_coords(u, v, data)
            if coords:
                attr_sight += 1
                ATTRACTION_SIGHT_CACHE.append({
                    "id": f"sight-{u}-{v}", "p": coords, "b": make_bounds(coords), "name": name,
                })

        # Graph network: one segment per physical road (dedupe u,v and v,u)
        physical = (min(u, v), max(u, v))
        if physical not in seen_physical:
            if coords is None:
                coords = get_edge_coords(u, v, data)
            if coords:
                seen_physical.add(physical)
                h = str(data.get('type', '')).strip().lower() or 'unknown'
                GRAPH_NETWORK_CACHE.append({
                    "id": f"gn-{physical[0]}-{physical[1]}",
                    "p": coords,
                    "b": make_bounds(coords),
                    "h": h,
                })

        # Edge point features: barrier, give_way, stop_sign, traffic_calming_point
        if data.get('barrier'):
            lat, lon = _edge_display_point(data, 'barrier_lat', 'barrier_lon', coords)
            if lat is not None and lon is not None:
                details = {"barrier": str(data['barrier']).strip().lower()}
                if data.get('barrier_confidence') is not None:
                    try:
                        details["barrier_confidence"] = float(data['barrier_confidence'])
                    except (TypeError, ValueError):
                        pass
                meta = barrier_cluster_meta(data)
                if meta:
                    details.update(meta)
                BARRIER_POINTS.append({"lat": lat, "lon": lon, "type": details["barrier"], "details": details})
                n_barrier += 1
        tc_pt = str(data.get('traffic_calming_point', '')).strip()
        if tc_pt:
            lat, lon = _edge_display_point(data, 'traffic_calming_point_lat', 'traffic_calming_point_lon', coords)
            if lat is not None and lon is not None:
                TRAFFIC_CALMING_POINT_POINTS.append({"lat": lat, "lon": lon, "type": tc_pt, "source": "point"})
                n_tc_pt += 1
        if str(data.get('give_way', '')).strip().lower() in ('yes', 'true', '1'):
            lat, lon = _edge_display_point(data, 'give_way_lat', 'give_way_lon', coords)
            if lat is not None and lon is not None:
                GIVE_WAY_POINTS.append({"lat": lat, "lon": lon})
                n_gw += 1
        if str(data.get('stop_sign', '')).strip().lower() in ('yes', 'true', '1'):
            lat, lon = _edge_display_point(data, 'stop_sign_lat', 'stop_sign_lon', coords)
            if lat is not None and lon is not None:
                STOP_POINTS.append({"lat": lat, "lon": lon})
                n_stop += 1

    print(f"--> Steep cache: {len(STEEP_CACHE)} (errors: {steep_error}, ignored: {steep_ignored})")
    print(f"--> Surface cache: {surface_count} bad-surface segments")
    print(f"--> Unlit cache: {unlit_count} unlit segments")
    print(
        f"--> Cycleway clusters: segregated={cycleway_counts.get(1, 0)}, "
        f"bus_shared={cycleway_counts.get(2, 0)}, car_shared={cycleway_counts.get(3, 0)}"
    )
    print(f"--> HGV banned: {hgv_count}")
    print(f"--> Traffic calming points: {tc_points}, Junction points: {jn_points}")
    print(f"--> TfL cycle routes: {tfl_count} edges")
    print(f"--> Attraction edges: park={attr_park}, river={attr_river}, sight={attr_sight}")
    print(f"--> Graph network cache: {len(GRAPH_NETWORK_CACHE)} physical edges")

    n_ts = n_mr = n_cross = 0
    print(f"--> Scanning {G.number_of_nodes()} nodes for point overlays...")
    for node_id, data in G.nodes(data=True):
        if 'x' not in data or 'y' not in data:
            continue
        lat = float(data['y'])
        lon = float(data['x'])
        pt = {"lat": lat, "lon": lon}
        if data.get('traffic_signals'):
            TRAFFIC_SIGNALS_POINTS.append(pt)
            n_ts += 1
        if data.get('mini_roundabout'):
            MINI_ROUNDABOUT_POINTS.append(pt)
            n_mr += 1
        if data.get('crossing'):
            CROSSING_POINTS.append(pt)
            n_cross += 1
    print(f"--> Point caches: barrier={n_barrier} (edges), give_way={n_gw} (edges), stop={n_stop} (edges), traffic_calming_point={n_tc_pt}, traffic_signals={n_ts}, mini_roundabout={n_mr}, crossing={n_cross}")


if _should_run_bootstrap():
    bootstrap_debug_engine()

@app.route('/debug/heatmap', methods=['GET'])
def get_elevation_heatmap():
    try:
        if not request.args.get('min_lat'):
            return jsonify([])

        min_lat = float(request.args.get('min_lat'))
        max_lat = float(request.args.get('max_lat'))
        min_lon = float(request.args.get('min_lon'))
        max_lon = float(request.args.get('max_lon'))

        visible_segments = [
            {"id": seg['id'], "g": seg['g'], "p": seg['p']}
            for seg in STEEP_CACHE
            if (seg['b'][0] < max_lat and seg['b'][1] > min_lat and
                seg['b'][2] < max_lon and seg['b'][3] > min_lon)
        ]

        return jsonify(visible_segments)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _dist_from_center(lat, lon, center_lat, center_lon):
    return (lat - center_lat) ** 2 + (lon - center_lon) ** 2

@app.route('/debug/surfaces', methods=['GET'])
def get_surface_heatmap():
    try:
        if not request.args.get('min_lat'):
            return jsonify({"segments": [], "limit_reached": False})

        min_lat = float(request.args.get('min_lat'))
        max_lat = float(request.args.get('max_lat'))
        min_lon = float(request.args.get('min_lon'))
        max_lon = float(request.args.get('max_lon'))
        include_no_data = request.args.get('include_no_data', '1') == '1'
        center_lat = (min_lat + max_lat) / 2.0
        center_lon = (min_lon + max_lon) / 2.0

        in_bbox = [
            {"id": seg['id'], "t": seg['t'], "s": seg['s'], "p": seg['p'], "b": seg['b']}
            for seg in SURFACE_CACHE
            if (seg['b'][0] < max_lat and seg['b'][1] > min_lat and
                seg['b'][2] < max_lon and seg['b'][3] > min_lon)
        ]

        other = [s for s in in_bbox if s['t'] != 'no_data']
        no_data = [s for s in in_bbox if s['t'] == 'no_data']
        limit_reached = False
        if include_no_data:
            # Sort no_data by distance from bbox centre, take at most MAX_SEGMENTS_LIMIT
            no_data.sort(key=lambda s: _dist_from_center(
                (s['b'][0] + s['b'][1]) / 2, (s['b'][2] + s['b'][3]) / 2, center_lat, center_lon))
            if len(no_data) > MAX_SEGMENTS_LIMIT:
                no_data = no_data[:MAX_SEGMENTS_LIMIT]
                limit_reached = True
        else:
            no_data = []

        segments = other + no_data
        # Enforce total cap of 20k: if over limit, keep 'other' first then fill with no_data
        if len(segments) > MAX_SEGMENTS_LIMIT:
            limit_reached = True
            other_count = len(other)
            if other_count >= MAX_SEGMENTS_LIMIT:
                segments = other[:MAX_SEGMENTS_LIMIT]
            else:
                segments = other + no_data[:MAX_SEGMENTS_LIMIT - other_count]
        for s in segments:
            s.pop('b', None)
        return jsonify({"segments": segments, "limit_reached": limit_reached})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/debug/unlit', methods=['GET'])
def get_unlit_heatmap():
    try:
        if not request.args.get('min_lat'):
            return jsonify({"segments": [], "limit_reached": False})

        min_lat = float(request.args.get('min_lat'))
        max_lat = float(request.args.get('max_lat'))
        min_lon = float(request.args.get('min_lon'))
        max_lon = float(request.args.get('max_lon'))
        include_unknown = request.args.get('include_unknown', '1') == '1'
        center_lat = (min_lat + max_lat) / 2.0
        center_lon = (min_lon + max_lon) / 2.0

        in_bbox = [
            {"id": seg['id'], "t": seg['t'], "p": seg['p'], "b": seg['b']}
            for seg in UNLIT_CACHE
            if (seg['b'][0] < max_lat and seg['b'][1] > min_lat and
                seg['b'][2] < max_lon and seg['b'][3] > min_lon)
        ]
        other = [s for s in in_bbox if s['t'] != 'unknown']
        unknown = [s for s in in_bbox if s['t'] == 'unknown']
        limit_reached = False
        if include_unknown:
            unknown.sort(key=lambda s: _dist_from_center(
                (s['b'][0] + s['b'][1]) / 2, (s['b'][2] + s['b'][3]) / 2, center_lat, center_lon))
            if len(unknown) > MAX_SEGMENTS_LIMIT:
                unknown = unknown[:MAX_SEGMENTS_LIMIT]
                limit_reached = True
        else:
            unknown = []

        segments = other + unknown
        if len(segments) > MAX_SEGMENTS_LIMIT:
            limit_reached = True
            other_count = len(other)
            if other_count >= MAX_SEGMENTS_LIMIT:
                segments = other[:MAX_SEGMENTS_LIMIT]
            else:
                segments = other + unknown[:MAX_SEGMENTS_LIMIT - other_count]
        for s in segments:
            s.pop('b', None)
        return jsonify({"segments": segments, "limit_reached": limit_reached})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- INSPECTOR ENDPOINT ---

@app.route('/inspect', methods=['GET'])
def inspect_segment():
    try:
        lat = float(request.args.get('lat'))
        lon = float(request.args.get('lon'))

        snap = tfl_live.snap_to_edge(lat, lon)
        if not snap:
            return jsonify({"error": "No edge found within snap distance"}), 404

        best_u, best_v = snap.u, snap.v
        best_edge_data = G.get_edge_data(best_u, best_v)

        if best_edge_data:
            tags = {k: v for k, v in best_edge_data.items() if k != 'geometry'}
            ele_u = G.nodes[best_u].get('elevation', 0.0)
            ele_v = G.nodes[best_v].get('elevation', 0.0)
            tags['elevation_start'] = round(float(ele_u), 2)
            tags['elevation_end'] = round(float(ele_v), 2)
            tags['grade'] = round(float(tags.get('grade', 0.0)), 3)
            if 'length' in tags:
                try:
                    tags['length'] = round(float(tags['length']), 0)
                except (TypeError, ValueError):
                    pass
            geometry = extract_segment_geometry(best_u, best_v)
            disruption = live_disruptions.get_edge_disruption(best_u, best_v)
            if disruption:
                tags['tfl_live_category'] = disruption.get('category', '')
                tags['tfl_live_severity'] = disruption.get('severity', '')
                tags['tfl_live_description'] = disruption.get('description', '')
                if disruption.get('iconCategory') is not None:
                    tags['tfl_live_iconCategory'] = disruption.get('iconCategory', '')
                if disruption.get('magnitudeOfDelay') is not None:
                    tags['tfl_live_magnitudeOfDelay'] = disruption.get('magnitudeOfDelay', '')
            return jsonify({
                "tags": tags,
                "geometry": geometry,
                "source": str(best_u),
                "target": str(best_v),
                "snap_point": [snap.snap_lat, snap.snap_lon],
            })
        else:
            return jsonify({"error": "No edge found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _get_edge_at_point(lat, lon):
    """Return (best_u, best_v, edge_data, geometry) for the edge nearest to (lat, lon), or (None, None, None, None)."""
    snap = tfl_live.snap_to_edge(lat, lon)
    if not snap:
        return (None, None, None, None)
    best_u, best_v = snap.u, snap.v
    best_data = G.get_edge_data(best_u, best_v)
    if best_data is None:
        return (None, None, None, None)
    geom = extract_segment_geometry(best_u, best_v)
    return (best_u, best_v, best_data, geom)


def _route_from_closest_tfl_segment(lat, lon):
    """Return route label (e.g. Q15) from the TfL segment nearest to (lat, lon), or empty string."""
    click = Point(lon, lat)
    best_route = ''
    best_dist = float('inf')
    for s in TFL_ROUTES_CACHE:
        route = str(s.get('route', '')).strip()
        if not route:
            continue
        coords = s.get('p')  # list of [lat, lon]
        if not coords or len(coords) < 2:
            continue
        line = LineString([(c[1], c[0]) for c in coords])
        d = line.distance(click)
        if d < best_dist:
            best_dist = d
            best_route = route.split(';')[0].strip() if route else ''
    return best_route


# --- TfL MANUAL EDITS (modify suite) ---
import json as _json
TFL_EDITS_PATH = os.path.join(os.path.dirname(__file__), "..", "3_pipeline", "tfl_manual_edits.json")


def _load_tfl_edits():
    """Load { added: [...], removed: [...], history: [...] } from file. Create default if missing."""
    if os.path.isfile(TFL_EDITS_PATH):
        try:
            with open(TFL_EDITS_PATH, "r", encoding="utf-8") as f:
                data = _json.load(f)
            if "history" not in data:
                data["history"] = []
            return data
        except Exception:
            pass
    return {"added": [], "removed": [], "history": []}


def _save_tfl_edits(data):
    """Save { added, removed } to file."""
    os.makedirs(os.path.dirname(TFL_EDITS_PATH), exist_ok=True)
    with open(TFL_EDITS_PATH, "w", encoding="utf-8") as f:
        _json.dump(data, f, indent=2)


@app.route('/modify/tfl_edits', methods=['GET'])
def get_tfl_edits():
    """Return current manual edits with geometry for each edge (for overlay)."""
    try:
        data = _load_tfl_edits()
        added = []
        for rec in data.get("added", []):
            u, v = rec.get("source"), rec.get("target")
            if u is None or v is None:
                continue
            geom = extract_segment_geometry(u, v) if G.has_edge(u, v) else None
            if geom:
                added.append({"source": str(u), "target": str(v), "programme": rec.get("programme", ""), "route": rec.get("route", ""), "geometry": geom})
        removed = []
        for rec in data.get("removed", []):
            u, v = rec.get("source"), rec.get("target")
            if u is None or v is None:
                continue
            geom = extract_segment_geometry(u, v) if G.has_edge(u, v) else None
            if geom:
                removed.append({"source": str(u), "target": str(v), "geometry": geom})
        return jsonify({"added": added, "removed": removed})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/modify/tfl_add', methods=['POST'])
def modify_tfl_add():
    """Add segment at (lat, lon) with programme; route from clicked edge or nearest TfL segment. Persist to file."""
    try:
        body = request.get_json() or {}
        lat = float(body.get("lat"))
        lon = float(body.get("lon"))
        programme = str(body.get("programme", "cycleway")).strip().lower()
        if programme not in ("cycleway", "quietway", "superhighway"):
            programme = "cycleway"
        best_u, best_v, edge_data, geometry = _get_edge_at_point(lat, lon)
        if best_u is None:
            return jsonify({"error": "No edge found"}), 404
        route = ''
        if edge_data:
            route = str(edge_data.get("tfl_cycle_route", "")).strip()
            if route:
                route = route.split(";")[0].strip()
        if not route:
            route = _route_from_closest_tfl_segment(lat, lon)
        data = _load_tfl_edits()
        rec = {
            "source": str(best_u),
            "target": str(best_v),
            "programme": programme,
            "route": route or "manual",
        }
        data["added"].append(rec)
        data.setdefault("history", []).append({"type": "add", **rec})
        _save_tfl_edits(data)
        return jsonify({
            "source": str(best_u),
            "target": str(best_v),
            "programme": programme,
            "route": route or "manual",
            "geometry": geometry,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/modify/tfl_remove', methods=['POST'])
def modify_tfl_remove():
    """Remove TfL tag from segment at (lat, lon). Persist to file."""
    try:
        body = request.get_json() or {}
        lat = float(body.get("lat"))
        lon = float(body.get("lon"))
        best_u, best_v, _, geometry = _get_edge_at_point(lat, lon)
        if best_u is None:
            return jsonify({"error": "No edge found"}), 404
        data = _load_tfl_edits()
        rec = {"source": str(best_u), "target": str(best_v)}
        data["removed"].append(rec)
        data.setdefault("history", []).append({"type": "remove", **rec})
        _save_tfl_edits(data)
        return jsonify({
            "source": str(best_u),
            "target": str(best_v),
            "geometry": geometry,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/modify/tfl_undo', methods=['POST'])
def modify_tfl_undo():
    """Undo last add or remove: pop from history and remove that entry from added or removed. Return new added/removed with geometry."""
    try:
        data = _load_tfl_edits()
        history = data.get("history", [])
        if not history:
            return jsonify({"error": "Nothing to undo", "added": [], "removed": []}), 400
        last = history.pop()
        if last.get("type") == "add":
            # Remove first matching add (same source, target, programme, route)
            added = data["added"]
            for i, rec in enumerate(added):
                if (rec.get("source") == last.get("source") and rec.get("target") == last.get("target")
                        and rec.get("programme") == last.get("programme") and rec.get("route") == last.get("route")):
                    added.pop(i)
                    break
        else:
            # Remove first matching remove (same source, target)
            removed = data["removed"]
            for i, rec in enumerate(removed):
                if rec.get("source") == last.get("source") and rec.get("target") == last.get("target"):
                    removed.pop(i)
                    break
        data["history"] = history
        _save_tfl_edits(data)
        # Return current added/removed with geometry for overlay
        added_out = []
        for rec in data.get("added", []):
            u, v = rec.get("source"), rec.get("target")
            if u is None or v is None:
                continue
            geom = extract_segment_geometry(u, v) if G.has_edge(u, v) else None
            if geom:
                added_out.append({"source": str(u), "target": str(v), "programme": rec.get("programme", ""), "route": rec.get("route", ""), "geometry": geom})
        removed_out = []
        for rec in data.get("removed", []):
            u, v = rec.get("source"), rec.get("target")
            if u is None or v is None:
                continue
            geom = extract_segment_geometry(u, v) if G.has_edge(u, v) else None
            if geom:
                removed_out.append({"source": str(u), "target": str(v), "geometry": geom})
        return jsonify({"ok": True, "undone": last, "added": added_out, "removed": removed_out})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- ATTRACTION MANUAL REGIONS (modify suite) ---
import uuid as _uuid

ATTRACTION_MANUAL_PATH = os.path.join(os.path.dirname(__file__), "..", "3_pipeline", "attraction_manual_regions.json")
OSM_PARKS_GEOJSON_PATH = os.path.join(os.path.dirname(__file__), "..", "1_data", "osm_park_polygons.geojson")


def _load_attraction_manual():
    if os.path.isfile(ATTRACTION_MANUAL_PATH):
        try:
            with open(ATTRACTION_MANUAL_PATH, "r", encoding="utf-8") as f:
                data = _json.load(f)
            if "history" not in data:
                data["history"] = []
            if "regions" not in data:
                data["regions"] = []
            return data
        except Exception:
            pass
    return {"regions": [], "history": []}


def _save_attraction_manual(data):
    os.makedirs(os.path.dirname(ATTRACTION_MANUAL_PATH), exist_ok=True)
    with open(ATTRACTION_MANUAL_PATH, "w", encoding="utf-8") as f:
        _json.dump(data, f, indent=2)


def _ring_to_leaflet(ring):
    """GeoJSON ring [lon,lat] -> Leaflet [[lat,lon],...]."""
    out = []
    for c in ring:
        if len(c) >= 2:
            out.append([float(c[1]), float(c[0])])
    return out


def _geom_to_leaflet_positions(geom):
    """Convert GeoJSON geometry to Leaflet overlay position(s)."""
    if not geom:
        return []
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if gtype == "Polygon" and coords:
        return [_ring_to_leaflet(r) for r in coords if r]
    if gtype == "MultiPolygon" and coords:
        polys = []
        for poly in coords:
            if poly:
                polys.append(_ring_to_leaflet(poly[0]))
        return polys
    if gtype == "LineString" and coords:
        return [_ring_to_leaflet(coords)]
    if gtype == "Point" and coords and len(coords) >= 2:
        return [[float(coords[1]), float(coords[0])]]
    return []


def _attraction_region_payload(rec: dict) -> dict:
    """Region for debug UI: source geometry + tagging zone (matches apply_attraction_manual)."""
    geom = rec.get("geometry")
    zone = region_tagging_zone(rec)
    return {
        "id": rec.get("id", ""),
        "type": rec.get("type", ""),
        "name": rec.get("name", ""),
        "buffer_m": rec.get("buffer_m"),
        "radius_m": rec.get("radius_m"),
        "positions": _geom_to_leaflet_positions(geom),
        "zone_positions": zone_to_leaflet_rings(zone),
    }


@app.route('/modify/attraction_regions', methods=['GET'])
def get_attraction_regions():
    try:
        data = _load_attraction_manual()
        out = [_attraction_region_payload(rec) for rec in data.get("regions", [])]
        return jsonify({"regions": out})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/modify/attraction_zone_preview', methods=['POST'])
def attraction_zone_preview():
    """Tagging zone for scratch geometry (same thresholds as pipeline)."""
    try:
        body = request.get_json() or {}
        rtype = str(body.get("type", "")).strip().lower()
        if rtype not in ("park", "river", "sight"):
            return jsonify({"error": "type must be park, river, or sight"}), 400
        geometry = body.get("geometry")
        if not geometry or not geometry.get("type"):
            return jsonify({"error": "geometry required"}), 400
        region = {"type": rtype, "geometry": geometry}
        if rtype == "river" and geometry.get("type") == "LineString":
            region["buffer_m"] = float(body.get("buffer_m") or 200)
        if rtype == "sight":
            region["radius_m"] = float(body.get("radius_m") or 200)
        zone = region_tagging_zone(region)
        return jsonify({
            "zone_positions": zone_to_leaflet_rings(zone),
            "buffer_m": region.get("buffer_m"),
            "radius_m": region.get("radius_m"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/modify/osm_park_polygons', methods=['GET'])
def get_osm_park_polygons():
    """Cached OSM park polygons for overlay while drawing manual regions."""
    try:
        if not os.path.isfile(OSM_PARKS_GEOJSON_PATH):
            return jsonify({"polygons": [], "message": "Run fetch_osm_park_polygons.py"})
        with open(OSM_PARKS_GEOJSON_PATH, "r", encoding="utf-8") as f:
            collection = _json.load(f)
        polygons = []
        for feat in collection.get("features", []):
            geom = feat.get("geometry")
            if not geom or geom.get("type") not in ("Polygon", "MultiPolygon"):
                continue
            props = feat.get("properties") or {}
            for ring_set in _geom_to_leaflet_positions(geom):
                if ring_set:
                    polygons.append({
                        "name": props.get("name", ""),
                        "positions": ring_set,
                    })
        return jsonify({"polygons": polygons})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/modify/attraction_add_region', methods=['POST'])
def modify_attraction_add_region():
    try:
        body = request.get_json() or {}
        rtype = str(body.get("type", "")).strip().lower()
        if rtype not in ("park", "river", "sight"):
            return jsonify({"error": "type must be park, river, or sight"}), 400
        geometry = body.get("geometry")
        if not geometry or not geometry.get("type"):
            return jsonify({"error": "geometry required"}), 400
        name = str(body.get("name", "") or "").strip()
        region = {
            "id": str(body.get("id") or _uuid.uuid4()),
            "type": rtype,
            "name": name,
            "geometry": geometry,
        }
        if rtype == "river" and geometry.get("type") == "LineString":
            region["buffer_m"] = float(body.get("buffer_m") or 200)
        if rtype == "sight":
            region["radius_m"] = float(body.get("radius_m") or 200)
        data = _load_attraction_manual()
        data["regions"].append(region)
        data.setdefault("history", []).append({"type": "add", "id": region["id"]})
        _save_attraction_manual(data)
        return jsonify({
            "ok": True,
            "region": _attraction_region_payload(region),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/modify/attraction_undo', methods=['POST'])
def modify_attraction_undo():
    try:
        data = _load_attraction_manual()
        history = data.get("history", [])
        if not history:
            return jsonify({"error": "Nothing to undo", "regions": []}), 400
        last = history.pop()
        if last.get("type") == "add":
            rid = last.get("id")
            data["regions"] = [r for r in data.get("regions", []) if r.get("id") != rid]
        data["history"] = history
        _save_attraction_manual(data)
        out = [_attraction_region_payload(rec) for rec in data.get("regions", [])]
        return jsonify({"ok": True, "undone": last, "regions": out})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- LIVE TfL DISRUPTIONS ENDPOINTS ---

@app.route('/admin/update_tfl', methods=['POST'])
def admin_update_tfl():
    try:
        ok, message, count = live_disruptions.update_disruptions(fetch_tfl=True)
        return jsonify({"ok": ok, "message": message, "count": count})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e), "count": 0}), 500


@app.route('/admin/update_tomtom', methods=['POST'])
def admin_update_tomtom():
    try:
        ok, message, count = live_disruptions.update_disruptions(fetch_tomtom=True)
        return jsonify({"ok": ok, "message": message, "count": count})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e), "count": 0}), 500


@app.route('/admin/tfl_status', methods=['GET'])
def admin_tfl_status():
    return jsonify(live_disruptions.get_status().get("tfl", tfl_live.get_status()))


@app.route('/admin/tomtom_status', methods=['GET'])
def admin_tomtom_status():
    return jsonify(live_disruptions.get_status().get("tomtom", {}))


@app.route('/debug/tfl_disruptions', methods=['GET'])
def get_tfl_disruptions():
    try:
        if not request.args.get('min_lat'):
            return jsonify({"segments": [], "limit_reached": False})
        min_lat = float(request.args.get('min_lat'))
        max_lat = float(request.args.get('max_lat'))
        min_lon = float(request.args.get('min_lon'))
        max_lon = float(request.args.get('max_lon'))
        segments, limit_reached = live_disruptions.get_vis_segments_in_bbox(
            min_lat, max_lat, min_lon, max_lon, source="tfl")
        return jsonify({"segments": segments, "limit_reached": limit_reached})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/debug/tomtom_disruptions', methods=['GET'])
def get_tomtom_disruptions():
    try:
        if not request.args.get('min_lat'):
            return jsonify({"segments": [], "limit_reached": False})
        min_lat = float(request.args.get('min_lat'))
        max_lat = float(request.args.get('max_lat'))
        min_lon = float(request.args.get('min_lon'))
        max_lon = float(request.args.get('max_lon'))
        segments, limit_reached = live_disruptions.get_vis_segments_in_bbox(
            min_lat, max_lat, min_lon, max_lon, source="tomtom")
        return jsonify({"segments": segments, "limit_reached": limit_reached})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/debug/tfl_disruptions_raw', methods=['GET'])
def get_tfl_disruptions_raw():
    """Return TfL ground-truth geometries (points, lines, polygons) in bbox for overlay."""
    try:
        if not request.args.get('min_lat'):
            return jsonify({"points": [], "lines": [], "polygons": [], "limit_reached": False})
        min_lat = float(request.args.get('min_lat'))
        max_lat = float(request.args.get('max_lat'))
        min_lon = float(request.args.get('min_lon'))
        max_lon = float(request.args.get('max_lon'))
        features, limit_reached = tfl_live.get_raw_geometries_in_bbox(
            min_lat, max_lat, min_lon, max_lon)
        points = [f for f in features if f["type"] == "point"]
        lines = [f for f in features if f["type"] == "line"]
        polygons = [f for f in features if f["type"] == "polygon"]
        return jsonify({
            "points": points,
            "lines": lines,
            "polygons": polygons,
            "limit_reached": limit_reached,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/debug/tfl_disruption_at', methods=['GET'])
def get_tfl_disruption_at():
    """Return full TfL disruption payload(s) at the given lat/lon (for left-click inspector)."""
    try:
        lat = request.args.get('lat', type=float)
        lon = request.args.get('lon', type=float)
        if lat is None or lon is None:
            return jsonify({"disruptions": []})
        tolerance = request.args.get('tolerance', type=float) or 0.00025
        disruptions = tfl_live.get_disruptions_at(lat, lon, tolerance_deg=tolerance)
        return jsonify({"disruptions": disruptions})
    except Exception as e:
        return jsonify({"error": str(e), "disruptions": []}), 500


@app.route('/debug/tomtom_disruption_at', methods=['GET'])
def get_tomtom_disruption_at():
    """Return full TomTom incident payload(s) at the given lat/lon (for left-click inspector)."""
    try:
        import tomtom_live
        lat = request.args.get('lat', type=float)
        lon = request.args.get('lon', type=float)
        if lat is None or lon is None:
            return jsonify({"disruptions": []})
        tolerance = request.args.get('tolerance', type=float) or 0.00025
        disruptions = tomtom_live.get_tomtom_disruptions_at(lat, lon, tolerance_deg=tolerance)
        return jsonify({"disruptions": disruptions})
    except Exception as e:
        return jsonify({"error": str(e), "disruptions": []}), 500


# --- ACCIDENTS ENDPOINT ---

def _limit_segments_by_center(segments, center_lat, center_lon, limit):
    """Sort by distance from center and return at most `limit`; return (list, limit_reached)."""
    if len(segments) <= limit:
        return segments, False
    with_b = [(s, _dist_from_center(
        (s['b'][0] + s['b'][1]) / 2, (s['b'][2] + s['b'][3]) / 2, center_lat, center_lon))
        for s in segments]
    with_b.sort(key=lambda x: x[1])
    out = [x[0] for x in with_b[:limit]]
    for s in out:
        s.pop('b', None)
    return out, True

@app.route('/debug/cycleway', methods=['GET'])
def get_cycleway():
    try:
        if not request.args.get('min_lat'):
            return jsonify({"segments": [], "limit_reached": False})
        min_lat = float(request.args.get('min_lat'))
        max_lat = float(request.args.get('max_lat'))
        min_lon = float(request.args.get('min_lon'))
        max_lon = float(request.args.get('max_lon'))
        center_lat = (min_lat + max_lat) / 2.0
        center_lon = (min_lon + max_lon) / 2.0

        clusters_param = request.args.get('clusters', '').strip().lower()
        allowed_clusters = None
        if clusters_param:
            allowed_clusters = {c.strip() for c in clusters_param.split(',') if c.strip()}

        in_bbox = [
            {"id": s['id'], "p": s['p'], "c": s['c'], "v": s.get('v', ''), "color": s.get('color', '')}
            for s in CYCLEWAY_CACHE
            if (s['b'][0] < max_lat and s['b'][1] > min_lat and
                s['b'][2] < max_lon and s['b'][3] > min_lon)
            and (allowed_clusters is None or s['c'] in allowed_clusters)
        ]
        limited, limit_reached = _limit_segments_by_center(
            in_bbox, center_lat, center_lon, MAX_SEGMENTS_LIMIT)
        return jsonify({"segments": limited, "limit_reached": limit_reached})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/debug/cycleway_clusters', methods=['GET'])
def get_cycleway_clusters():
    """Cluster legend for cycleway overlay colours (matches cycleway_clusters.py)."""
    return jsonify(cycleway_cluster_legend())

@app.route('/debug/hgv_banned', methods=['GET'])
def get_hgv_banned():
    try:
        if not request.args.get('min_lat'):
            return jsonify({"segments": [], "limit_reached": False})
        min_lat = float(request.args.get('min_lat'))
        max_lat = float(request.args.get('max_lat'))
        min_lon = float(request.args.get('min_lon'))
        max_lon = float(request.args.get('max_lon'))
        center_lat = (min_lat + max_lat) / 2.0
        center_lon = (min_lon + max_lon) / 2.0
        in_bbox = [
            {"id": s['id'], "p": s['p'], "b": s['b']}
            for s in HGV_BANNED_CACHE
            if (s['b'][0] < max_lat and s['b'][1] > min_lat and
                s['b'][2] < max_lon and s['b'][3] > min_lon)
        ]
        limited, limit_reached = _limit_segments_by_center(
            in_bbox, center_lat, center_lon, MAX_SEGMENTS_LIMIT)
        for s in limited:
            s.pop('b', None)
        return jsonify({"segments": limited, "limit_reached": limit_reached})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/debug/graph_network', methods=['GET'])
def get_graph_network():
    """All graph edges in bbox (one per physical road), coloured by highway type; 15k centre cap."""
    try:
        if not request.args.get('min_lat'):
            return jsonify({"segments": [], "limit_reached": False})
        min_lat = float(request.args.get('min_lat'))
        max_lat = float(request.args.get('max_lat'))
        min_lon = float(request.args.get('min_lon'))
        max_lon = float(request.args.get('max_lon'))
        center_lat = (min_lat + max_lat) / 2.0
        center_lon = (min_lon + max_lon) / 2.0
        in_bbox = [
            {"id": s['id'], "p": s['p'], "h": s['h'], "b": s['b']}
            for s in GRAPH_NETWORK_CACHE
            if (s['b'][0] < max_lat and s['b'][1] > min_lat and
                s['b'][2] < max_lon and s['b'][3] > min_lon)
        ]
        limited, limit_reached = _limit_segments_by_center(
            in_bbox, center_lat, center_lon, GRAPH_NETWORK_LIMIT)
        for s in limited:
            s.pop('b', None)
        return jsonify({"segments": limited, "limit_reached": limit_reached})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


_ATTRACTION_LAYER_POOLS = {
    "park": lambda: ATTRACTION_PARK_CACHE,
    "river": lambda: ATTRACTION_RIVER_CACHE,
    "sight": lambda: ATTRACTION_SIGHT_CACHE,
}


def _parse_park_hours_at_time():
    """Optional ISO `at` query param; default Europe/London now."""
    from datetime import datetime

    raw = (request.args.get("at") or "").strip()
    if not raw:
        return london_now()
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=LONDON_TZ)
        return dt.astimezone(LONDON_TZ)
    except Exception:
        return london_now()


@app.route('/debug/attractions', methods=['GET'])
def get_attractions():
    """Edges tagged is_park / is_river / is_sight. layer=park|river|sight|all (default all).

    park_hours=1 on park layer: each park segment includes park_open (bool) at evaluation time.
    Optional at= ISO datetime (Europe/London) for fixed-time preview.
    """
    try:
        if not request.args.get("min_lat"):
            return jsonify({"segments": [], "limit_reached": False})
        min_lat = float(request.args.get("min_lat"))
        max_lat = float(request.args.get("max_lat"))
        min_lon = float(request.args.get("min_lon"))
        max_lon = float(request.args.get("max_lon"))
        center_lat = (min_lat + max_lat) / 2.0
        center_lon = (min_lon + max_lon) / 2.0
        layer = (request.args.get("layer", "all") or "all").strip().lower()
        if layer not in _ATTRACTION_LAYER_POOLS and layer != "all":
            layer = "all"
        park_hours = (request.args.get("park_hours", "") or "").strip().lower() in ("1", "true", "yes")
        kinds = list(_ATTRACTION_LAYER_POOLS.keys()) if layer == "all" else [layer]
        in_bbox = []
        for kind in kinds:
            for s in _ATTRACTION_LAYER_POOLS[kind]():
                b = s["b"]
                if b[0] < max_lat and b[1] > min_lat and b[2] < max_lon and b[3] > min_lon:
                    entry = {
                        "id": s["id"],
                        "p": s["p"],
                        "kind": kind,
                        "name": s.get("name", ""),
                        "b": b,
                    }
                    if kind == "park":
                        entry["_oh"] = s.get("opening_hours", "")
                    in_bbox.append(entry)
        limited, limit_reached = _limit_segments_by_center(
            in_bbox, center_lat, center_lon, MAX_SEGMENTS_LIMIT
        )
        meta = {}
        if park_hours:
            at_time = _parse_park_hours_at_time()
            unique = G.graph.get("park_opening_hours_unique") or []
            hours_map, fallback_open = build_request_hours_context(unique, at_time)
            meta["park_hours_at"] = at_time.isoformat()
            meta["park_fallback_open"] = fallback_open
            for s in limited:
                if s.get("kind") == "park":
                    s["park_open"] = is_park_edge_open(
                        {"is_park": "yes", "opening_hours": s.pop("_oh", "")},
                        hours_map,
                        fallback_open,
                    )
                else:
                    s.pop("_oh", None)
        for s in limited:
            s.pop("b", None)
            s.pop("_oh", None)
        return jsonify({"segments": limited, "limit_reached": limit_reached, **meta})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/debug/tfl_routes', methods=['GET'])
def get_tfl_routes():
    try:
        if not request.args.get('min_lat'):
            return jsonify({"segments": [], "limit_reached": False})
        min_lat = float(request.args.get('min_lat'))
        max_lat = float(request.args.get('max_lat'))
        min_lon = float(request.args.get('min_lon'))
        max_lon = float(request.args.get('max_lon'))
        center_lat = (min_lat + max_lat) / 2.0
        center_lon = (min_lon + max_lon) / 2.0
        in_bbox = [
            {"id": s['id'], "p": s['p'], "programme": s['programme'], "route": s.get('route', ''), "b": s['b']}
            for s in TFL_ROUTES_CACHE
            if (s['b'][0] < max_lat and s['b'][1] > min_lat and
                s['b'][2] < max_lon and s['b'][3] > min_lon)
        ]
        limited, limit_reached = _limit_segments_by_center(
            in_bbox, center_lat, center_lon, MAX_SEGMENTS_LIMIT)
        for s in limited:
            s.pop('b', None)
        return jsonify({"segments": limited, "limit_reached": limit_reached})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/debug/traffic_calming_points', methods=['GET'])
def get_traffic_calming_points():
    """Return traffic calming points. source=way|point|both (default way). Each point has type and source."""
    try:
        if not request.args.get('min_lat'):
            return jsonify([])
        min_lat = float(request.args.get('min_lat'))
        max_lat = float(request.args.get('max_lat'))
        min_lon = float(request.args.get('min_lon'))
        max_lon = float(request.args.get('max_lon'))
        src = (request.args.get('source', 'way').strip().lower() or 'way').replace(' ', '')
        if src not in ('way', 'point', 'both'):
            src = 'way'
        if src == 'way':
            pool = TRAFFIC_CALMING_POINTS
        elif src == 'point':
            pool = TRAFFIC_CALMING_POINT_POINTS
        else:
            pool = list(TRAFFIC_CALMING_POINTS) + list(TRAFFIC_CALMING_POINT_POINTS)
        points = [
            p for p in pool
            if min_lat <= p['lat'] <= max_lat and min_lon <= p['lon'] <= max_lon
        ]
        if len(points) > MAX_SEGMENTS_LIMIT:
            center_lat = (min_lat + max_lat) / 2.0
            center_lon = (min_lon + max_lon) / 2.0
            points.sort(key=lambda p: _dist_from_center(p['lat'], p['lon'], center_lat, center_lon))
            points = points[:MAX_SEGMENTS_LIMIT]
        return jsonify(points)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/debug/junction_points', methods=['GET'])
def get_junction_points():
    try:
        if not request.args.get('min_lat'):
            return jsonify([])
        min_lat = float(request.args.get('min_lat'))
        max_lat = float(request.args.get('max_lat'))
        min_lon = float(request.args.get('min_lon'))
        max_lon = float(request.args.get('max_lon'))
        points = [
            p for p in JUNCTION_POINTS
            if min_lat <= p['lat'] <= max_lat and min_lon <= p['lon'] <= max_lon
        ]
        if len(points) > MAX_SEGMENTS_LIMIT:
            center_lat = (min_lat + max_lat) / 2.0
            center_lon = (min_lon + max_lon) / 2.0
            points.sort(key=lambda p: _dist_from_center(p['lat'], p['lon'], center_lat, center_lon))
            points = points[:MAX_SEGMENTS_LIMIT]
        return jsonify(points)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _filter_points_bbox(points, min_lat, max_lat, min_lon, max_lon, get_lat_lon=None):
    if get_lat_lon is None:
        get_lat_lon = lambda p: (p['lat'], p['lon'])
    in_bbox = [p for p in points if min_lat <= get_lat_lon(p)[0] <= max_lat and min_lon <= get_lat_lon(p)[1] <= max_lon]
    if len(in_bbox) <= MAX_SEGMENTS_LIMIT:
        return in_bbox
    center_lat = (min_lat + max_lat) / 2.0
    center_lon = (min_lon + max_lon) / 2.0
    in_bbox.sort(key=lambda p: _dist_from_center(get_lat_lon(p)[0], get_lat_lon(p)[1], center_lat, center_lon))
    return in_bbox[:MAX_SEGMENTS_LIMIT]


@app.route('/debug/barrier_points', methods=['GET'])
def get_barrier_points():
    try:
        if not request.args.get('min_lat'):
            return jsonify([])
        min_lat, max_lat = float(request.args.get('min_lat')), float(request.args.get('max_lat'))
        min_lon, max_lon = float(request.args.get('min_lon')), float(request.args.get('max_lon'))
        return jsonify(_filter_points_bbox(BARRIER_POINTS, min_lat, max_lat, min_lon, max_lon))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/debug/barrier_clusters', methods=['GET'])
def get_barrier_clusters():
    """Cluster legend for barrier overlay colours (matches barrier_clusters.py)."""
    return jsonify(cluster_legend())

@app.route('/debug/traffic_signals_points', methods=['GET'])
def get_traffic_signals_points():
    try:
        if not request.args.get('min_lat'):
            return jsonify([])
        min_lat, max_lat = float(request.args.get('min_lat')), float(request.args.get('max_lat'))
        min_lon, max_lon = float(request.args.get('min_lon')), float(request.args.get('max_lon'))
        return jsonify(_filter_points_bbox(TRAFFIC_SIGNALS_POINTS, min_lat, max_lat, min_lon, max_lon))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/debug/mini_roundabout_points', methods=['GET'])
def get_mini_roundabout_points():
    try:
        if not request.args.get('min_lat'):
            return jsonify([])
        min_lat, max_lat = float(request.args.get('min_lat')), float(request.args.get('max_lat'))
        min_lon, max_lon = float(request.args.get('min_lon')), float(request.args.get('max_lon'))
        return jsonify(_filter_points_bbox(MINI_ROUNDABOUT_POINTS, min_lat, max_lat, min_lon, max_lon))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/debug/crossing_points', methods=['GET'])
def get_crossing_points():
    try:
        if not request.args.get('min_lat'):
            return jsonify([])
        min_lat, max_lat = float(request.args.get('min_lat')), float(request.args.get('max_lat'))
        min_lon, max_lon = float(request.args.get('min_lon')), float(request.args.get('max_lon'))
        return jsonify(_filter_points_bbox(CROSSING_POINTS, min_lat, max_lat, min_lon, max_lon))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/debug/give_way_points', methods=['GET'])
def get_give_way_points():
    try:
        if not request.args.get('min_lat'):
            return jsonify([])
        min_lat, max_lat = float(request.args.get('min_lat')), float(request.args.get('max_lat'))
        min_lon, max_lon = float(request.args.get('min_lon')), float(request.args.get('max_lon'))
        return jsonify(_filter_points_bbox(GIVE_WAY_POINTS, min_lat, max_lat, min_lon, max_lon))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/debug/stop_points', methods=['GET'])
def get_stop_points():
    try:
        if not request.args.get('min_lat'):
            return jsonify([])
        min_lat, max_lat = float(request.args.get('min_lat')), float(request.args.get('max_lat'))
        min_lon, max_lon = float(request.args.get('min_lon')), float(request.args.get('max_lon'))
        return jsonify(_filter_points_bbox(STOP_POINTS, min_lat, max_lat, min_lon, max_lon))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/accidents', methods=['GET'])
def get_accidents():
    try:
        db_url = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:5432/{DB_NAME}"
        engine = create_engine(db_url)
        conn = engine.connect()
        sql = text("SELECT ST_Y(geometry::geometry) as lat, ST_X(geometry::geometry) as lon FROM accidents")
        result = conn.execute(sql)
        points = [[row[0], row[1]] for row in result]
        conn.close()
        return jsonify(points)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5001, use_reloader=USE_RELOADER)