"""
Debug backend: overlay endpoints (/debug/heatmap, /debug/surfaces, /debug/unlit, /accidents) and /inspect. Port 5001.
When changing, update 0_documentation/APP_DEBUG.md
"""
from flask import Flask, jsonify, request
from flask_cors import CORS
import networkx as nx
from shapely.wkt import loads as load_wkt
from shapely.geometry import Point, LineString
from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
import tfl_live
import live_disruptions

# --- CONFIGURATION (set DB_PASS etc. via env or .env; do not commit secrets) ---
GRAPH_PATH = os.path.join("..", "1_data", "london_elev_final_tfl.graphml")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASS = os.environ.get("DB_PASS", "")
DB_NAME = os.environ.get("DB_NAME", "london_routing")
DB_HOST = os.environ.get("DB_HOST", "localhost")

app = Flask(__name__)
CORS(app)

print("--- STARTING DEBUG ENGINE (PORT 5001) ---")
if not os.path.exists(GRAPH_PATH):
    print(f"CRITICAL ERROR: {GRAPH_PATH} not found.")
    exit()

print(f"Loading graph from {GRAPH_PATH}...")
G = nx.read_graphml(GRAPH_PATH)
print(f"Graph Loaded with {len(G.nodes())} nodes.")

# Build Node Index for inspector
node_data = []
for node, data in G.nodes(data=True):
    if 'x' in data and 'y' in data:
        node_data.append({'id': node, 'x': float(data['x']), 'y': float(data['y'])})

live_disruptions.init(G)

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
    edge_data = G.get_edge_data(u, v)
    coords = []
    if 'geometry' in edge_data:
        try:
            line = load_wkt(edge_data['geometry'])
            segment_coords = list(line.coords)
            u_x, u_y = G.nodes[u]['x'], G.nodes[u]['y']
            start_dist = (segment_coords[0][0] - u_x)**2 + (segment_coords[0][1] - u_y)**2
            end_dist = (segment_coords[-1][0] - u_x)**2 + (segment_coords[-1][1] - u_y)**2
            if end_dist < start_dist:
                segment_coords.reverse()
            for x, y in segment_coords:
                coords.append([y, x])
            return coords
        except:
            pass
    node_u = G.nodes[u]
    node_v = G.nodes[v]
    coords.append([float(node_u['y']), float(node_u['x'])])
    coords.append([float(node_v['y']), float(node_v['x'])])
    return coords

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
    coords = []
    if 'geometry' in data:
        try:
            line = load_wkt(data['geometry'])
            coords = [[y, x] for x, y in line.coords]
        except:
            pass
    else:
        if 'y' in G.nodes[u] and 'y' in G.nodes[v]:
            coords = [
                [float(G.nodes[u]['y']), float(G.nodes[u]['x'])],
                [float(G.nodes[v]['y']), float(G.nodes[v]['x'])]
            ]
    return coords

def make_bounds(coords):
    lats = [p[0] for p in coords]
    lons = [p[1] for p in coords]
    return (min(lats), max(lats), min(lons), max(lons))

def get_edge_midpoint(u, v, data):
    """Return (lat, lon) of edge midpoint for point-based overlays."""
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

# Caches for cycleway, HGV, and point-based overlays (filled in pre_process_graph)
CYCLEWAY_GENERAL = []   # has cycleway / cycleway_left / right / both (non-empty)
CYCLEWAY_SEGREGATED = []
HGV_BANNED_CACHE = []
TRAFFIC_CALMING_POINTS = []       # way-based: [{lat, lon, type, source: 'way'}, ...]
TRAFFIC_CALMING_POINT_POINTS = [] # point-based: [{lat, lon, type, source: 'point'}, ...]
JUNCTION_POINTS = []             # [{lat, lon, type}, ...] (edge-based: roundabout, circular, etc.)

# Node-based point caches (filled in build_node_point_caches); graph node: x=lon, y=lat
BARRIER_POINTS = []          # [{lat, lon, type}, ...]
TRAFFIC_SIGNALS_POINTS = []  # [{lat, lon}, ...]
MINI_ROUNDABOUT_POINTS = []
CROSSING_POINTS = []
GIVE_WAY_POINTS = []
STOP_POINTS = []

# TfL cycle routes (edges with tfl_cycle_programme); programme = first category for color
TFL_ROUTES_CACHE = []  # [{id, p, b, programme, route}, ...]

MAX_SEGMENTS_LIMIT = 20000

def pre_process_graph():
    print("--- PRE-PROCESSING GRAPH FOR DEBUGGING ---")
    steep_ignored = 0
    steep_error = 0
    surface_count = 0
    unlit_count = 0
    cycleway_g = 0
    cycleway_seg = 0
    hgv_count = 0
    tc_points = 0
    jn_points = 0
    tfl_count = 0

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
            # No surface or cycleway_surface tag — show as "no data"
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
                # Classify: explicit no vs no data
                lit_type = "no" if lit_raw in ['no', 'limited'] else "unknown"
                UNLIT_CACHE.append({
                    "id": f"l-{u}-{v}",
                    "t": lit_type,
                    "p": coords,
                    "b": make_bounds(coords)
                })

        # Cycleway caches (GRAPH.md 3.3)
        cw = str(data.get('cycleway', '')).strip()
        cw_left = str(data.get('cycleway_left', '')).strip()
        cw_right = str(data.get('cycleway_right', '')).strip()
        cw_both = str(data.get('cycleway_both', '')).strip()
        has_general = bool(cw or cw_left or cw_right or cw_both)
        if has_general:
            if coords is None:
                coords = get_edge_coords(u, v, data)
            if coords:
                cycleway_g += 1
                CYCLEWAY_GENERAL.append({
                    "id": f"cw-{u}-{v}", "p": coords, "b": make_bounds(coords),
                    "v": cw or cw_left or cw_right or cw_both
                })
        seg_val = str(data.get('segregated', '')).lower().strip()
        if seg_val == 'yes':
            if coords is None:
                coords = get_edge_coords(u, v, data)
            if coords:
                cycleway_seg += 1
                CYCLEWAY_SEGREGATED.append({
                    "id": f"cws-{u}-{v}", "p": coords, "b": make_bounds(coords)
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
            pt = get_edge_midpoint(u, v, data)
            if pt:
                tc_points += 1
                TRAFFIC_CALMING_POINTS.append({"lat": pt[0], "lon": pt[1], "type": tc, "source": "way"})
        jn = str(data.get('junction', '')).strip()
        if jn:
            pt = get_edge_midpoint(u, v, data)
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
                # First programme for color; store route label too
                programme = tfl_prog.split(';')[0].strip().lower() if tfl_prog else ''
                route = str(data.get('tfl_cycle_route', '')).strip()
                TFL_ROUTES_CACHE.append({
                    "id": f"tfl-{u}-{v}", "p": coords, "b": make_bounds(coords),
                    "programme": programme, "route": route
                })

    print(f"--> Steep cache: {len(STEEP_CACHE)} (errors: {steep_error}, ignored: {steep_ignored})")
    print(f"--> Surface cache: {surface_count} bad-surface segments")
    print(f"--> Unlit cache: {unlit_count} unlit segments")
    print(f"--> Cycleway: general={cycleway_g}, segregated={cycleway_seg}")
    print(f"--> HGV banned: {hgv_count}")
    print(f"--> Traffic calming points: {tc_points}, Junction points: {jn_points}")
    print(f"--> TfL cycle routes: {tfl_count} edges")

pre_process_graph()


def _edge_display_point(edge_data, lat_key, lon_key):
    """Return (lat, lon) for edge point feature: stored position or edge geometry midpoint."""
    lat = edge_data.get(lat_key)
    lon = edge_data.get(lon_key)
    if lat is not None and lon is not None:
        try:
            return float(lat), float(lon)
        except (TypeError, ValueError):
            pass
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


def build_node_point_caches():
    """Build point caches: nodes for traffic_signals/crossing/mini_roundabout; EDGES for barrier/give_way/stop (stored position); traffic_calming point-based."""
    n_barrier = n_ts = n_mr = n_cross = n_gw = n_stop = n_tc_pt = 0
    # From NODES: traffic_signals, mini_roundabout, crossing
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
    # From EDGES: barrier, give_way, stop_sign (plot point at stored original position only)
    for u, v, data in G.edges(data=True):
        if data.get('barrier'):
            lat, lon = _edge_display_point(data, 'barrier_lat', 'barrier_lon')
            if lat is not None and lon is not None:
                details = {"barrier": str(data['barrier']).strip().lower()}
                if data.get('barrier_confidence') is not None:
                    try:
                        details["barrier_confidence"] = float(data['barrier_confidence'])
                    except (TypeError, ValueError):
                        pass
                BARRIER_POINTS.append({"lat": lat, "lon": lon, "type": details["barrier"], "details": details})
                n_barrier += 1
        tc_pt = str(data.get('traffic_calming_point', '')).strip()
        if tc_pt:
            lat, lon = _edge_display_point(data, 'traffic_calming_point_lat', 'traffic_calming_point_lon')
            if lat is not None and lon is not None:
                TRAFFIC_CALMING_POINT_POINTS.append({"lat": lat, "lon": lon, "type": tc_pt, "source": "point"})
                n_tc_pt += 1
        if str(data.get('give_way', '')).strip().lower() in ('yes', 'true', '1'):
            lat, lon = _edge_display_point(data, 'give_way_lat', 'give_way_lon')
            if lat is not None and lon is not None:
                GIVE_WAY_POINTS.append({"lat": lat, "lon": lon})
                n_gw += 1
        if str(data.get('stop_sign', '')).strip().lower() in ('yes', 'true', '1'):
            lat, lon = _edge_display_point(data, 'stop_sign_lat', 'stop_sign_lon')
            if lat is not None and lon is not None:
                STOP_POINTS.append({"lat": lat, "lon": lon})
                n_stop += 1
    print(f"--> Point caches: barrier={n_barrier} (edges), give_way={n_gw} (edges), stop={n_stop} (edges), traffic_calming_point={n_tc_pt}, traffic_signals={n_ts}, mini_roundabout={n_mr}, crossing={n_cross}")

build_node_point_caches()

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
        click_point = Point(lon, lat)

        u = get_nearest_node(lat, lon)
        if not u:
            return jsonify({"error": "No graph data"}), 404

        best_edge_data = None
        best_u = None
        best_v = None
        min_distance = float('inf')

        candidates = []
        for v in G.neighbors(u): candidates.append((u, v))
        for v in G.predecessors(u): candidates.append((v, u))

        for (src, dst) in candidates:
            edge_data = G.get_edge_data(src, dst)
            if 'geometry' in edge_data:
                line = load_wkt(edge_data['geometry'])
            else:
                p1 = (float(G.nodes[src]['x']), float(G.nodes[src]['y']))
                p2 = (float(G.nodes[dst]['x']), float(G.nodes[dst]['y']))
                line = LineString([p1, p2])
            dist = line.distance(click_point)
            if dist < min_distance:
                min_distance = dist
                best_edge_data = edge_data
                best_u = src
                best_v = dst

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
            })
        else:
            return jsonify({"error": "No edge found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _get_edge_at_point(lat, lon):
    """Return (best_u, best_v, edge_data, geometry) for the edge nearest to (lat, lon), or (None, None, None, None)."""
    click_point = Point(lon, lat)
    u = get_nearest_node(lat, lon)
    if not u:
        return (None, None, None, None)
    best_u = best_v = None
    best_data = None
    min_distance = float('inf')
    candidates = []
    for v in G.neighbors(u):
        candidates.append((u, v))
    for v in G.predecessors(u):
        candidates.append((v, u))
    for (src, dst) in candidates:
        edge_data = G.get_edge_data(src, dst)
        if 'geometry' in edge_data:
            line = load_wkt(edge_data['geometry'])
        else:
            p1 = (float(G.nodes[src]['x']), float(G.nodes[src]['y']))
            p2 = (float(G.nodes[dst]['x']), float(G.nodes[dst]['y']))
            line = LineString([p1, p2])
        dist = line.distance(click_point)
        if dist < min_distance:
            min_distance = dist
            best_data = edge_data
            best_u, best_v = src, dst
    if best_u is None:
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
        if not request.args.get('min_lat') or not request.args.get('layer'):
            return jsonify({"segments": [], "limit_reached": False})
        min_lat = float(request.args.get('min_lat'))
        max_lat = float(request.args.get('max_lat'))
        min_lon = float(request.args.get('min_lon'))
        max_lon = float(request.args.get('max_lon'))
        layer = request.args.get('layer', 'general').lower()
        center_lat = (min_lat + max_lat) / 2.0
        center_lon = (min_lon + max_lon) / 2.0

        if layer == 'general':
            cache = CYCLEWAY_GENERAL
        elif layer == 'segregated':
            cache = CYCLEWAY_SEGREGATED
        else:
            return jsonify({"segments": [], "limit_reached": False})

        in_bbox = [
            {"id": s['id'], "p": s['p'], "v": s.get('v', ''), "b": s['b']}
            for s in cache
            if (s['b'][0] < max_lat and s['b'][1] > min_lat and
                s['b'][2] < max_lon and s['b'][3] > min_lon)
        ]
        limited, limit_reached = _limit_segments_by_center(
            in_bbox, center_lat, center_lon, MAX_SEGMENTS_LIMIT)
        for s in limited:
            if 'b' in s:
                s.pop('b')
        return jsonify({"segments": limited, "limit_reached": limit_reached})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
    app.run(debug=True, port=5001)