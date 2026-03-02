"""
Main routing backend: /route and /inspect. Uses 1_data/london_elev_final_tfl.graphml.
When changing API or cost logic, update 0_documentation/APP_MAIN.md (and TASKS.md if needed).
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import networkx as nx
from shapely.wkt import loads as load_wkt
from shapely.geometry import Point, LineString
import os
import tfl_live
import tomtom_live
import live_disruptions

# --- CONFIGURATION ---
# UPDATED: Pointing to the final, clean, dual-pass processed graph
GRAPH_PATH = os.path.join("..", "1_data", "london_elev_final_tfl.graphml")

app = Flask(__name__)
CORS(app)

print("--- STARTING STANDARD ROUTING ENGINE ---")
if not os.path.exists(GRAPH_PATH):
    print(f"CRITICAL ERROR: {GRAPH_PATH} not found.")
    exit()

print(f"Loading graph from {GRAPH_PATH}...")
G = nx.read_graphml(GRAPH_PATH)

# Build Node Index
node_data = []
for node, data in G.nodes(data=True):
    if 'x' in data and 'y' in data:
        node_data.append({'id': node, 'x': float(data['x']), 'y': float(data['y'])})
print(f"Graph Loaded with {len(G.nodes())} nodes.")

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

# Weights are passed per-request (no globals) for multi-user safety; see make_weight_optimized().

BAD_SURFACES = [
    'grass', 'dirt', 'sand', 'ground', 'unpaved', 'sett', 'gravel', 'wood',
    'fine_gravel', 'earth', 'mud', 'woodchips', 'cobblestone', 'pebblestone',
    'clay', 'grit', 'grass_paver', 'stone', 'unhewn_cobblestone', 'stepping_stones'
]

# --- BASE PHYSICS (implementation.md) ---
CYCLIST_SPEED_MPS = 16.0 / 3.6   # ~4.44 m/s (16 km/h)
SIGNAL_WAIT_SECONDS = 20         # Slightly increased so signal penalty is more visible
WIDTH_STD_M = 1.5
WIDTH_MIN_M = 1.25
SPEED_DIFF_NEGLIGIBLE_KMH = 20
SPEED_DIFF_LOW_KMH = 30
M_MIN = 0.1   # Ensure edge weight never zero/negative for A*
R_MIN = 0.1   # Reward multiplier minimum (rewards implemented as R < 1, not negative penalty)

# --- CONSTANTS ---
UP_THRESH = 0.033
DOWN_THRESH = -0.033

# Junction danger: only count edges where cars are allowed (exclude pedestrian/cycle-only).
# OSM highway types that are typically no motor traffic:
HIGHWAY_TYPES_NO_CARS = frozenset([
    'footway', 'cycleway', 'path', 'pedestrian', 'steps', 'bridleway', 'corridor',
    'proposed', 'construction', 'cycleway:left', 'cycleway:right', 'cycleway:both',
])
# Dangerous junction = at least this many physical car-allowed roads meeting at the node
JUNCTION_DANGER_MIN_CAR_ROADS = 4

def is_lit(d):
    val = str(d.get('lit', '')).lower()
    return val in ['yes', 'true', '24/7', 'on', 'designated']

# --- NODE/EDGE HELPERS (for cost factors) ---
def _parse_maxspeed_kmh(d):
    """Return maxspeed in km/h. Infer from highway if missing. UK: often mph."""
    raw = str(d.get('maxspeed', '')).strip()
    if raw:
        raw_lower = raw.lower()
        if 'mph' in raw_lower:
            try:
                num = float(''.join(c for c in raw.split()[0] if c.isdigit() or c == '.'))
                return num * 1.60934
            except (ValueError, IndexError):
                pass
        try:
            return float(''.join(c for c in raw if c.isdigit() or c == '.'))
        except ValueError:
            pass
    highway = str(d.get('type', '')).lower()
    if 'residential' in highway or 'living_street' in highway or 'unclassified' in highway:
        return 30.0
    if 'primary' in highway or 'trunk' in highway:
        return 50.0
    if 'secondary' in highway:
        return 48.0
    return 30.0

def _get_width_m(d):
    """Width in meters. Prefer cycleway_width then width."""
    for key in ('cycleway_width', 'width'):
        val = d.get(key)
        if val is None: continue
        s = str(val).strip().lower().replace(',', '.')
        try:
            num = float(''.join(c for c in s if c.isdigit() or c == '.'))
            if 'ft' in s or 'foot' in s: num *= 0.3048
            return max(0.0, num)
        except ValueError:
            pass
    return None

def _tfl_programmes(d):
    prog = str(d.get('tfl_cycle_programme', '')).strip().lower()
    if not prog: return []
    return [p.strip() for p in prog.split(';') if p.strip()]

def _is_tfl_cycleway_or_superhighway(d):
    programmes = _tfl_programmes(d)
    return 'cycleway' in programmes or 'superhighway' in programmes

def _is_tfl_quietway(d):
    return 'quietway' in _tfl_programmes(d)

def _is_green_edge(d):
    """Park-like: path types + natural surface or unlit."""
    highway = str(d.get('type', '')).lower()
    if highway not in ('footway', 'cycleway', 'path', 'bridleway'):
        return False
    surface = str(d.get('surface', '')).lower()
    natural = surface in ('grass', 'ground', 'earth', 'gravel', 'dirt', 'mud', 'woodchips', '')
    unlit = str(d.get('lit', '')).lower() in ('no', 'false', '')
    return natural or unlit

# Only zebra/uncontrolled crossings get the junction penalty (cycling on main road: unmarked is not a risk, signals are separate mode)
CROSSING_PENALTY_VALUES = frozenset(['zebra', 'uncontrolled'])
# Zebra/uncontrolled crossing penalty = half of signal virtual distance (~44 m) so it matches importance
INTERSECTION_PENALTY_METRES = (SIGNAL_WAIT_SECONDS * CYCLIST_SPEED_MPS) * 0.5

def _node_intersection_penalty(node_data):
    """Fixed cost only for zebra or uncontrolled crossings (not give_way, mini_roundabout, unmarked, or traffic_signals).
    Return value in metres: INTERSECTION_PENALTY_METRES (half of signal penalty) added when junction_weight is 1."""
    crossing = str(node_data.get('crossing') or '').strip().lower()
    crossing_type = str(node_data.get('crossing_type') or '').strip().lower()
    if crossing in CROSSING_PENALTY_VALUES or crossing_type in CROSSING_PENALTY_VALUES:
        return INTERSECTION_PENALTY_METRES
    return 0.0

def _edge_barrier_penalty(edge_data):
    """Barrier on edge: passable=low, disruptive=medium, dismount=high. Scaled by barrier_confidence (0-1)."""
    if not edge_data:
        return 0.0
    b = str(edge_data.get('barrier', '')).strip().lower()
    if not b:
        return 0.0
    if b in ('bollard', 'cycle_barrier'):
        base = 3.0
    elif b in ('gate', 'lift_gate', 'swing_gate', 'chicane', 'kerb', 'planter', 'block'):
        base = 12.0
    elif b in ('stile', 'steps', 'kissing_gate', 'turnstile', 'height_restrictor'):
        base = 35.0
    else:
        base = 8.0
    try:
        conf = float(edge_data.get('barrier_confidence', 1.0))
    except (TypeError, ValueError):
        conf = 1.0
    return base * max(0.0, min(1.0, conf))


def _edge_give_way_penalty(edge_data):
    """Give-way sign on edge (only on edge that ends at the sign). Same magnitude as zebra crossing."""
    if not edge_data:
        return 0.0
    if str(edge_data.get('give_way', '')).strip().lower() in ('yes', 'true', '1'):
        return INTERSECTION_PENALTY_METRES
    return 0.0


def _edge_stop_sign_penalty(edge_data):
    """Stop sign on edge (only on edge that ends at the sign). Same magnitude as zebra crossing."""
    if not edge_data:
        return 0.0
    if str(edge_data.get('stop_sign', '')).strip().lower() in ('yes', 'true', '1'):
        return INTERSECTION_PENALTY_METRES
    return 0.0

def _node_signal_penalty(node_data):
    """Virtual distance = wait time * cyclist speed."""
    if str(node_data.get('traffic_signals', '')).lower() != 'yes':
        return 0.0
    return SIGNAL_WAIT_SECONDS * CYCLIST_SPEED_MPS


def _is_car_allowed_edge(edge_data):
    """True if this edge is a road type where cars are typically allowed (excludes footway, cycleway, path, etc.)."""
    if not edge_data:
        return False
    t = str(edge_data.get('type', '')).strip().lower()
    if not t:
        return True   # unknown: assume car-allowed to avoid over-penalising
    return t not in HIGHWAY_TYPES_NO_CARS


def _count_car_physical_roads_at_node(node_id):
    """
    Count physical car-allowed roads meeting at this node.
    One physical road = one undirected link: (u,v) and (v,u) count as one road.
    Only edges with car-allowed highway type are counted (excludes footway, cycleway, path, etc.).
    """
    if node_id not in G.nodes:
        return 0
    physical = set()
    for u in G.predecessors(node_id):
        ed = G.get_edge_data(u, node_id)
        if _is_car_allowed_edge(ed):
            physical.add((min(u, node_id), max(u, node_id)))
    for w in G.successors(node_id):
        ed = G.get_edge_data(node_id, w)
        if _is_car_allowed_edge(ed):
            physical.add((min(node_id, w), max(node_id, w)))
    return len(physical)


def _junction_danger_penalty(node_id):
    """
    Complex junction without signals: proxy for right-turn / merge danger.
    Only counts car-allowed roads; counts physical roads (one-way + two-way = one road).
    Dangerous when >= JUNCTION_DANGER_MIN_CAR_ROADS (4) such roads meet.
    Crossings are not used here (may move to edge-based logic later).
    """
    if node_id not in G.nodes:
        return 0.0
    node_data = G.nodes[node_id]
    if str(node_data.get('traffic_signals', '')).lower() == 'yes':
        return 0.0
    car_road_count = _count_car_physical_roads_at_node(node_id)
    if car_road_count < JUNCTION_DANGER_MIN_CAR_ROADS:
        return 0.0
    return 8.0

def _speed_stress_multiplier(d):
    """Mild penalty by speed difference to cyclist (Literature Table 7)."""
    maxspeed_kmh = _parse_maxspeed_kmh(d)
    cyclist_kmh = CYCLIST_SPEED_MPS * 3.6
    diff = maxspeed_kmh - cyclist_kmh
    if diff < SPEED_DIFF_NEGLIGIBLE_KMH: return 0.0
    if diff <= SPEED_DIFF_LOW_KMH: return 0.15
    return 0.35

def _width_penalty_multiplier(d):
    """Width < 1.5m: slight; < 1.25m: moderate (not impassable)."""
    w = _get_width_m(d)
    if w is None: return 0.0
    if w >= WIDTH_STD_M: return 0.0
    if w >= WIDTH_MIN_M: return 0.2
    return 0.5

def _traffic_calming_additive(d, source='way'):
    """Fixed distance cost per segment with calming. source: 'way' (OSM way tag), 'point' (snapped point), 'both' (max of both)."""
    def _cost(tc):
        if not tc: return 0.0
        if tc in ('cushion', 'choker'): return 5.0
        return 10.0
    way_tc = str(d.get('traffic_calming', '') or '').strip().lower()
    point_tc = str(d.get('traffic_calming_point', '') or '').strip().lower()
    if source == 'way':
        return _cost(way_tc)
    if source == 'point':
        return _cost(point_tc)
    if source == 'both':
        return max(_cost(way_tc), _cost(point_tc))
    return _cost(way_tc)

# --- COST FUNCTIONS ---
def weight_fastest(u, v, d):
    return float(d.get('length', 1.0))


def make_weight_optimized(w):
    """
    Return a weight function (u, v, d) -> cost using request-scoped weights (no globals).
    Rewards (TfL, green) are implemented as multiplier R < 1 on length, not negative penalty,
    to keep A* heuristic well-behaved.
    """
    def weight_fn(u, v, d):
        length = float(d.get('length', 1.0))
        grade = float(d.get('grade', 0.0))

        # --- Multipliers M (penalties only; no negative terms) ---
        risk_penalty = float(d.get('risk', 0.0)) * w.get('risk_weight', 0.0)
        is_illuminated = is_lit(d)
        light_penalty = (0.0 if is_illuminated else 0.5) * w.get('light_weight', 0.0)
        surface = str(d.get('surface', '')).lower()
        surface_penalty = (3.0 if surface in BAD_SURFACES else 0.0) * w.get('surface_weight', 0.0)
        speed_m = _speed_stress_multiplier(d) * w.get('speed_weight', 0.0)
        width_m = _width_penalty_multiplier(d) * w.get('width_weight', 0.0)

        M_total = 1.0 + risk_penalty + light_penalty + surface_penalty + speed_m + width_m
        M_total = max(M_MIN, M_total)

        # --- Reward R: multiply by factor < 1 for preferred edges (no negative penalty) ---
        R = 1.0
        if w.get('tfl_cycleway_weight', 0.0) > 0 and _is_tfl_cycleway_or_superhighway(d):
            R *= 0.75
        if w.get('tfl_quietway_weight', 0.0) > 0 and _is_tfl_quietway(d):
            R *= 0.75
        if w.get('green_weight', 0.0) > 0 and _is_green_edge(d):
            R *= 0.8
        R = max(R_MIN, R)

        # --- Additives A (fixed per edge/node) ---
        node_v = G.nodes[v] if v in G.nodes else {}
        A_intersection = _node_intersection_penalty(node_v) * w.get('junction_weight', 0.0)
        A_barrier = _edge_barrier_penalty(d) * w.get('barrier_weight', 0.0)
        A_give_way = _edge_give_way_penalty(d) * w.get('junction_weight', 0.0)
        A_stop_sign = _edge_stop_sign_penalty(d) * w.get('junction_weight', 0.0)
        A_signal = _node_signal_penalty(node_v) * w.get('signal_weight', 0.0)
        A_junction = _junction_danger_penalty(v) * w.get('junction_weight', 0.0)
        calming_src = w.get('calming_source', 'way')
        A_calming = _traffic_calming_additive(d, calming_src) * w.get('calming_weight', 0.0)
        A_total = A_intersection + A_barrier + A_give_way + A_stop_sign + A_signal + A_junction + A_calming

        # --- Hill H ---
        WORK_COEFF = 20.0
        hill_cost = 0.0
        if grade > 0:
            work_penalty = grade * WORK_COEFF
            power_penalty = (grade * 20.0) ** 2 if grade > UP_THRESH else 0.0
            hill_cost = length * (work_penalty + power_penalty)
        elif grade < DOWN_THRESH:
            hill_cost = length * 1.5
        H = hill_cost * w.get('hill_weight', 0.0)

        # --- Dynamic live disruptions (TfL + TomTom, lookup table O(1)) ---
        if w.get('tfl_live_weight', 0.0) > 0:
            disruption = live_disruptions.get_edge_disruption(u, v)
            if disruption:
                if disruption.get('has_closure') or disruption.get('is_closed'):
                    return 1e9
                live_w = w['tfl_live_weight']
                if disruption.get('is_diversion'):
                    M_total += 5.0 * live_w
                cat = disruption.get('category', '')
                if cat == 'Works':
                    M_total += 3.0 * live_w
                elif cat in ('Collisions', 'Emergency service incidents',
                             'Traffic Incidents', 'Network delays'):
                    M_total += 2.0 * live_w
                if disruption.get('temporary_bad_surface'):
                    M_total += 3.0 * live_w
                if disruption.get('environmental_hazard'):
                    M_total *= 1.3
                sev_mult = disruption.get('severity_multiplier', 1.0)
                if sev_mult > 1.0:
                    M_total *= sev_mult

        return (length * M_total * R) + A_total + H
    return weight_fn

# --- HELPERS ---
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

def reconstruct_path_geometry(path_nodes):
    full_coords = []
    for i in range(len(path_nodes) - 1):
        segment = extract_segment_geometry(path_nodes[i], path_nodes[i+1])
        full_coords.extend(segment)
    return full_coords

# --- STATS ---
def calculate_path_stats(path_nodes, calming_source='way'):
    total_length = 0.0
    total_accidents = 0.0
    lit_length = 0.0
    rough_length = 0.0
    total_climb = 0.0
    steep_count = 0
    tfl_cycleway_length = 0.0
    tfl_quietway_length = 0.0
    speed_stress_length = 0.0
    narrow_length = 0.0
    green_length = 0.0
    barrier_count = 0
    give_way_count = 0
    stop_sign_count = 0
    calming_count = 0
    signal_count = 0
    junction_count = 0
    disruption_count = 0
    for i in range(len(path_nodes) - 1):
        u = path_nodes[i]
        v = path_nodes[i+1]
        edge_data = G.get_edge_data(u, v) or {}
        l = float(edge_data.get('length', 0))
        total_length += l
        total_accidents += float(edge_data.get('risk', 0))
        if is_lit(edge_data): lit_length += l
        s = str(edge_data.get('surface', '')).lower()
        if s in BAD_SURFACES: rough_length += l
        grade = float(edge_data.get('grade', 0.0))
        if grade > 0: total_climb += (grade * l)
        if grade > UP_THRESH or grade < DOWN_THRESH: steep_count += 1

        if _is_tfl_cycleway_or_superhighway(edge_data): tfl_cycleway_length += l
        if _is_tfl_quietway(edge_data): tfl_quietway_length += l
        if _speed_stress_multiplier(edge_data) > 0: speed_stress_length += l
        if _get_width_m(edge_data) is not None and _get_width_m(edge_data) < WIDTH_STD_M: narrow_length += l
        if _is_green_edge(edge_data): green_length += l
        if _traffic_calming_additive(edge_data, calming_source) > 0: calming_count += 1

        if _edge_barrier_penalty(edge_data) > 0: barrier_count += 1
        if _edge_give_way_penalty(edge_data) > 0: give_way_count += 1
        if _edge_stop_sign_penalty(edge_data) > 0: stop_sign_count += 1
        node_v = G.nodes[v] if v in G.nodes else {}
        if _node_signal_penalty(node_v) > 0: signal_count += 1
        if _node_intersection_penalty(node_v) > 0 or _junction_danger_penalty(v) > 0: junction_count += 1
        if live_disruptions.get_edge_disruption(u, v): disruption_count += 1

    duration_min = total_length / (CYCLIST_SPEED_MPS * 60.0) if CYCLIST_SPEED_MPS else total_length / 266.0
    pct_lit = (lit_length / total_length * 100) if total_length > 0 else 0
    pct_rough = (rough_length / total_length * 100) if total_length > 0 else 0
    narrow_km = narrow_length / 1000.0
    speed_stress_km = speed_stress_length / 1000.0
    speed_stress_pct = (speed_stress_length / total_length * 100) if total_length > 0 else 0
    green_km = green_length / 1000.0
    tfl_cycleway_pct = (tfl_cycleway_length / total_length * 100) if total_length > 0 else 0
    tfl_quietway_pct = (tfl_quietway_length / total_length * 100) if total_length > 0 else 0
    return {
        "length_m": round(total_length, 0), "accidents": int(total_accidents),
        "duration_min": round(duration_min, 1), "illumination_pct": round(pct_lit, 0),
        "rough_pct": round(pct_rough, 0), "elevation_gain": round(total_climb, 0),
        "steep_count": steep_count,
        "tfl_cycleway_pct": round(tfl_cycleway_pct, 1), "tfl_quietway_pct": round(tfl_quietway_pct, 1),
        "speed_stress_km": round(speed_stress_km, 2), "speed_stress_pct": round(speed_stress_pct, 1),
        "narrow_km": round(narrow_km, 2), "green_km": round(green_km, 2),
        "barrier_count": barrier_count, "give_way_count": give_way_count, "stop_sign_count": stop_sign_count,
        "calming_count": calming_count, "signal_count": signal_count, "junction_count": junction_count,
        "disruption_count": disruption_count,
    }

def get_lit_sections(path_nodes):
    out = []
    for i in range(len(path_nodes) - 1):
        u, v = path_nodes[i], path_nodes[i+1]
        if is_lit(G.get_edge_data(u, v) or {}):
            out.append(extract_segment_geometry(u, v))
    return out

def get_steep_sections(path_nodes):
    out = []
    for i in range(len(path_nodes) - 1):
        u, v = path_nodes[i], path_nodes[i+1]
        grade = float((G.get_edge_data(u, v) or {}).get('grade', 0.0))
        if grade > UP_THRESH or grade < DOWN_THRESH:
            out.append(extract_segment_geometry(u, v))
    return out

def get_tfl_cycleway_sections(path_nodes):
    out = []
    for i in range(len(path_nodes) - 1):
        u, v = path_nodes[i], path_nodes[i+1]
        d = G.get_edge_data(u, v) or {}
        if _is_tfl_cycleway_or_superhighway(d):
            out.append(extract_segment_geometry(u, v))
    return out

def get_tfl_quietway_sections(path_nodes):
    out = []
    for i in range(len(path_nodes) - 1):
        u, v = path_nodes[i], path_nodes[i+1]
        d = G.get_edge_data(u, v) or {}
        if _is_tfl_quietway(d):
            out.append(extract_segment_geometry(u, v))
    return out

def get_green_sections(path_nodes):
    out = []
    for i in range(len(path_nodes) - 1):
        u, v = path_nodes[i], path_nodes[i+1]
        d = G.get_edge_data(u, v) or {}
        if _is_green_edge(d):
            out.append(extract_segment_geometry(u, v))
    return out


def get_narrow_sections(path_nodes):
    """Segments where width < WIDTH_STD_M (for overlay)."""
    out = []
    for i in range(len(path_nodes) - 1):
        u, v = path_nodes[i], path_nodes[i+1]
        d = G.get_edge_data(u, v) or {}
        w = _get_width_m(d)
        if w is not None and w < WIDTH_STD_M:
            out.append(extract_segment_geometry(u, v))
    return out


def get_disruption_sections(path_nodes):
    """Route-only: segments of the given path that have a live disruption (TfL or TomTom).
    Same pattern as get_lit_sections, get_steep_sections, get_narrow_sections: only path edges,
    no bbox or global segment list. Used for overlay in main app."""
    out = []
    for i in range(len(path_nodes) - 1):
        u, v = path_nodes[i], path_nodes[i+1]
        if live_disruptions.get_edge_disruption(u, v):
            out.append(extract_segment_geometry(u, v))
    return out


def _edge_display_point(edge_data, lat_key, lon_key):
    """Return (lat, lon) for edge point feature: use stored position or edge geometry midpoint."""
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


def get_node_highlights(path_nodes, w=None):
    """
    For the optimized path, collect node- and edge-based features for map icons.
    Barrier, give_way, stop_sign are EDGE-based: plot a single point at stored original position.
    Only includes a highlight when that feature actually receives a penalty (weight > 0 and penalty > 0).
    """
    w = w or {}
    out = []
    seen = set()  # (key, type) to avoid duplicate markers

    # --- Edge-based: barrier, give_way, stop_sign (plot point at stored position only) ---
    for i in range(len(path_nodes) - 1):
        u, v = path_nodes[i], path_nodes[i + 1]
        ed = G.get_edge_data(u, v) or {}
        key = (u, v)

        if w.get('barrier_weight', 0.0) > 0 and _edge_barrier_penalty(ed) > 0 and (key, 'barrier') not in seen:
            seen.add((key, 'barrier'))
            lat, lon = _edge_display_point(ed, 'barrier_lat', 'barrier_lon')
            if lat is not None and lon is not None:
                out.append({"lat": lat, "lon": lon, "type": "barrier", "details": {"barrier": str(ed.get('barrier', '')).strip().lower()}})

        if w.get('junction_weight', 0.0) > 0:
            if _edge_give_way_penalty(ed) > 0 and (key, 'give_way') not in seen:
                seen.add((key, 'give_way'))
                lat, lon = _edge_display_point(ed, 'give_way_lat', 'give_way_lon')
                if lat is not None and lon is not None:
                    out.append({"lat": lat, "lon": lon, "type": "give_way", "details": {"give_way": "yes"}})
            if _edge_stop_sign_penalty(ed) > 0 and (key, 'stop_sign') not in seen:
                seen.add((key, 'stop_sign'))
                lat, lon = _edge_display_point(ed, 'stop_sign_lat', 'stop_sign_lon')
                if lat is not None and lon is not None:
                    out.append({"lat": lat, "lon": lon, "type": "stop_sign", "details": {"stop_sign": "yes"}})

    # --- Node-based: signal, junction (zebra), junction_danger, calming ---
    for i in range(len(path_nodes)):
        v = path_nodes[i]
        if v not in G.nodes:
            continue
        node_data = G.nodes[v]
        lat = float(node_data.get('y', 0))
        lon = float(node_data.get('x', 0))

        if w.get('signal_weight', 0.0) > 0 and _node_signal_penalty(node_data) > 0 and (v, 'signal') not in seen:
            seen.add((v, 'signal'))
            out.append({"lat": lat, "lon": lon, "type": "signal", "details": {"traffic_signals": "yes"}})

        if w.get('junction_weight', 0.0) > 0:
            if _node_intersection_penalty(node_data) > 0 and (v, 'junction') not in seen:
                seen.add((v, 'junction'))
                details = {'crossing': node_data.get('crossing_type') or node_data.get('crossing') or 'zebra/uncontrolled'}
                out.append({"lat": lat, "lon": lon, "type": "junction", "details": details})
            car_road_count = _count_car_physical_roads_at_node(v)
            if _junction_danger_penalty(v) > 0 and (v, 'junction_danger') not in seen:
                seen.add((v, 'junction_danger'))
                out.append({"lat": lat, "lon": lon, "type": "junction_danger", "details": {"car_road_count": car_road_count}})

        if w.get('calming_weight', 0.0) > 0 and i > 0:
            u = path_nodes[i - 1]
            ed = G.get_edge_data(u, v) or {}
            calming_src = w.get('calming_source', 'way')
            # Way-based calming: use edge geometry midpoint (no stored position for way tag)
            if calming_src in ('way', 'both'):
                tc = str(ed.get('traffic_calming', '') or '').strip().lower()
                if tc and _traffic_calming_additive(ed, 'way') > 0 and (v, 'calming_way') not in seen:
                    seen.add((v, 'calming_way'))
                    lat_way, lon_way = _edge_display_point(ed, 'traffic_calming_point_lat', 'traffic_calming_point_lon')  # fallback to midpoint
                    if lat_way is None or lon_way is None:
                        lat_way, lon_way = lat, lon
                    out.append({"lat": lat_way, "lon": lon_way, "type": "calming", "details": {"traffic_calming": tc, "source": "way"}})
            # Point-based calming: use stored point position
            if calming_src in ('point', 'both'):
                tc_pt = str(ed.get('traffic_calming_point', '') or '').strip().lower()
                if tc_pt and _traffic_calming_additive(ed, 'point') > 0 and (v, 'calming_point') not in seen:
                    seen.add((v, 'calming_point'))
                    lat_pt, lon_pt = _edge_display_point(ed, 'traffic_calming_point_lat', 'traffic_calming_point_lon')
                    if lat_pt is not None and lon_pt is not None:
                        out.append({"lat": lat_pt, "lon": lon_pt, "type": "calming", "details": {"traffic_calming": tc_pt, "source": "point"}})

    return out


# --- INSPECTOR ENDPOINT ---

@app.route('/inspect', methods=['GET'])
def inspect_segment():
    """
    Finds edge closest to click. Returns tags + geometry + specific elevation data.
    """
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
        
        # Check all edges connected to nearest node
        candidates = []
        for v in G.neighbors(u): candidates.append((u, v))
        for v in G.predecessors(u): candidates.append((v, u))
            
        for (src, dst) in candidates:
            edge_data = G.get_edge_data(src, dst)
            
            # Geometry check
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
            # Prepare tags
            tags = {k: v for k, v in best_edge_data.items() if k != 'geometry'}
            
            # Add specific elevation details
            ele_u = G.nodes[best_u].get('elevation', 0.0)
            ele_v = G.nodes[best_v].get('elevation', 0.0)
            
            # Formatting to 2 decimals
            tags['elevation_start'] = round(float(ele_u), 2)
            tags['elevation_end'] = round(float(ele_v), 2)
            tags['grade'] = round(float(tags.get('grade', 0.0)), 3) # Keep grade slightly more precise
            
            # Add Geometry for overlay (Red Line)
            geometry = extract_segment_geometry(best_u, best_v)

            disruption = live_disruptions.get_edge_disruption(best_u, best_v)
            if disruption:
                tags['tfl_live_category'] = disruption.get('category', '')
                tags['tfl_live_severity'] = disruption.get('severity', '')
                tags['tfl_live_description'] = disruption.get('description', '')
                if disruption.get('source') == 'tomtom' or disruption.get('iconCategory') is not None:
                    tags['tfl_live_iconCategory'] = disruption.get('iconCategory', '')
                    tags['tfl_live_magnitudeOfDelay'] = disruption.get('magnitudeOfDelay', '')

            return jsonify({
                "tags": tags,
                "geometry": geometry
            })
        else:
            return jsonify({"error": "No edge found"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- LIVE TfL DISRUPTIONS ENDPOINT ---

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
    """Return TfL disruption status (edge_count, last_update) for main app overlay/refresh UI."""
    try:
        st = live_disruptions.get_status().get("tfl", tfl_live.get_status())
        return jsonify(st)
    except Exception as e:
        return jsonify({"error": str(e), "edge_count": 0, "last_update": None}), 500


@app.route('/admin/tomtom_status', methods=['GET'])
def admin_tomtom_status():
    """Return TomTom disruption status for main app overlay/refresh UI."""
    try:
        st = live_disruptions.get_status().get("tomtom", tomtom_live.get_status())
        return jsonify(st)
    except Exception as e:
        return jsonify({"error": str(e), "edge_count": 0, "last_update": None}), 500


@app.route('/tfl_disruptions', methods=['GET'])
def get_tfl_disruptions():
    """Return TfL matched segments in bbox for main app overlay (same shape as debug)."""
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


@app.route('/tomtom_disruptions', methods=['GET'])
def get_tomtom_disruptions():
    """Return TomTom matched segments in bbox for main app overlay."""
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


@app.route('/tfl_disruption_at', methods=['GET'])
def get_tfl_disruption_at():
    """Return full TfL disruption payload(s) at lat/lon for left-click detail (main app)."""
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


@app.route('/tomtom_disruption_at', methods=['GET'])
def get_tomtom_disruption_at():
    """Return full TomTom incident payload(s) at lat/lon for left-click detail (main app)."""
    try:
        lat = request.args.get('lat', type=float)
        lon = request.args.get('lon', type=float)
        if lat is None or lon is None:
            return jsonify({"disruptions": []})
        tolerance = request.args.get('tolerance', type=float) or 0.00025
        disruptions = tomtom_live.get_tomtom_disruptions_at(lat, lon, tolerance_deg=tolerance)
        return jsonify({"disruptions": disruptions})
    except Exception as e:
        return jsonify({"error": str(e), "disruptions": []}), 500


# --- ROUTING ENDPOINTS ---

@app.route('/route', methods=['GET'])
def get_route():
    try:
        start_lat = float(request.args.get('start_lat'))
        start_lon = float(request.args.get('start_lon'))
        end_lat = float(request.args.get('end_lat'))
        end_lon = float(request.args.get('end_lon'))

        # Request-scoped weights (no globals; safe for concurrent users)
        w = {
            "risk_weight": float(request.args.get('risk_weight', 1.0)),
            "light_weight": float(request.args.get('light_weight', 0.0)),
            "surface_weight": float(request.args.get('surface_weight', 0.0)),
            "hill_weight": float(request.args.get('hill_weight', 0.0)),
            "tfl_cycleway_weight": float(request.args.get('tfl_cycleway_weight', 0.0)),
            "tfl_quietway_weight": float(request.args.get('tfl_quietway_weight', 0.0)),
            "speed_weight": float(request.args.get('speed_weight', 0.0)),
            "width_weight": float(request.args.get('width_weight', 0.0)),
            "green_weight": float(request.args.get('green_weight', 0.0)),
            "barrier_weight": float(request.args.get('barrier_weight', 0.0)),
            "calming_weight": float(request.args.get('calming_weight', 0.0)),
            "calming_source": request.args.get('calming_source', 'way').strip().lower() or 'way',
            "junction_weight": float(request.args.get('junction_weight', 0.0)),
            "signal_weight": float(request.args.get('signal_weight', 0.0)),
            "tfl_live_weight": float(request.args.get('tfl_live_weight', 0.0)),
        }

        start_node = get_nearest_node(start_lat, start_lon)
        end_node = get_nearest_node(end_lat, end_lon)

        if not start_node or not end_node:
            return jsonify({"error": "Could not snap to network"}), 400

        path_fastest = nx.astar_path(G, start_node, end_node, weight=weight_fastest)
        coords_fastest = reconstruct_path_geometry(path_fastest)
        stats_fastest = calculate_path_stats(path_fastest)

        weight_optimized = make_weight_optimized(w)
        path_optimized = nx.astar_path(G, start_node, end_node, weight=weight_optimized)
        coords_optimized = reconstruct_path_geometry(path_optimized)
        stats_optimized = calculate_path_stats(path_optimized, calming_source=w.get('calming_source', 'way'))

        # Route-only overlay chunks (only segments on path_optimized that match each criterion)
        lit_chunks = get_lit_sections(path_optimized)
        steep_chunks = get_steep_sections(path_optimized)
        tfl_cycleway_chunks = get_tfl_cycleway_sections(path_optimized)
        tfl_quietway_chunks = get_tfl_quietway_sections(path_optimized)
        green_chunks = get_green_sections(path_optimized)
        narrow_chunks = get_narrow_sections(path_optimized)
        disruption_chunks = get_disruption_sections(path_optimized)  # path-only, like lit/steep/narrow
        node_highlights = get_node_highlights(path_optimized, w)

        return jsonify({
            "status": "success",
            "fastest": {"path": coords_fastest, "stats": stats_fastest},
            "safest": {
                "path": coords_optimized,
                "stats": stats_optimized,
                "lit_chunks": lit_chunks,
                "steep_chunks": steep_chunks,
                "tfl_cycleway_chunks": tfl_cycleway_chunks,
                "tfl_quietway_chunks": tfl_quietway_chunks,
                "green_chunks": green_chunks,
                "narrow_chunks": narrow_chunks,
                "disruption_chunks": disruption_chunks,
                "node_highlights": node_highlights,
            },
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)