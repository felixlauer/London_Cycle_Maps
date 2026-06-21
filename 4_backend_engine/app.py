"""
Main routing backend: /route, /inspect, /profiles. Uses 1_data/london_elev_final_tfl.gpickle (fast) or .graphml fallback.
Profile-driven routing via user_profiles.json (local mock DB). When changing API or cost logic, update 0_documentation/APP_MAIN.md.
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import math
import networkx as nx
import numpy as np
from scipy.spatial import cKDTree
from shapely.wkt import loads as load_wkt
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "3_pipeline"))
from graph_io import load_graph, fast_path

import tfl_live
import tomtom_live
import live_disruptions
from routing_heuristic import (
    TFL_CYCLEWAY_REWARD,
    TFL_QUIETWAY_REWARD,
    GREEN_REWARD,
    VEHICULAR_FREE_REWARD,
    compute_optimized_cost_per_metre_lower_bound,
    make_heuristic,
    set_penalty_floors,
)
from barrier_clusters import (
    BARRIER_HARD_COST,
    barrier_additive_penalty,
    barrier_is_hard_block,
    barrier_cluster_meta,
)
from cost_masks import (
    is_segregated_cycling,
    is_service_access_denied,
    is_service_alley,
    is_vehicular_free,
    masks_surface_and_hill,
    routing_width_m,
)
import user_profiles
import park_opening_hours

# --- CONFIGURATION ---
# UPDATED: Pointing to the final, clean, dual-pass processed graph
GRAPH_PATH = os.path.join("..", "1_data", "london_elev_final_tfl.graphml")

USE_RELOADER = os.environ.get("FLASK_USE_RELOADER", "").lower() in ("1", "true", "yes")

app = Flask(__name__)
CORS(app)

G = None
node_data = []
NODE_KDTREE = None
NODE_IDS = []


def _should_run_bootstrap():
    if not USE_RELOADER:
        return True
    return os.environ.get("WERKZEUG_RUN_MAIN") == "true"


def bootstrap_routing_engine():
    global G, node_data, NODE_KDTREE, NODE_IDS
    t_boot = time.perf_counter()
    print("--- STARTING STANDARD ROUTING ENGINE ---")
    if not os.path.exists(GRAPH_PATH) and not os.path.exists(fast_path(GRAPH_PATH)):
        print(f"CRITICAL ERROR: {GRAPH_PATH} (or .gpickle) not found.")
        exit()

    print(f"Loading graph (fast pickle preferred): {GRAPH_PATH}...")
    t0 = time.perf_counter()
    G = load_graph(GRAPH_PATH)
    node_data = []
    for node, data in G.nodes(data=True):
        if 'x' in data and 'y' in data:
            node_data.append({'id': node, 'x': float(data['x']), 'y': float(data['y'])})
    print(f"Graph loaded with {len(G.nodes())} nodes ({time.perf_counter() - t0:.1f}s).")
    park_hours_n = len(G.graph.get("park_opening_hours_unique") or [])
    print(f"--> Park opening_hours catalog: {park_hours_n} unique strings")

    t0 = time.perf_counter()
    coords = np.array([[n['x'], n['y']] for n in node_data], dtype=np.float64)
    NODE_IDS = [n['id'] for n in node_data]
    NODE_KDTREE = cKDTree(coords)
    print(f"--> Node KD-tree: {len(NODE_IDS)} nodes ({time.perf_counter() - t0:.1f}s)")

    t0 = time.perf_counter()
    live_disruptions.init(G)
    print(f"--> Live disruption index: {time.perf_counter() - t0:.1f}s")
    print(f"--- Bootstrap complete in {time.perf_counter() - t_boot:.1f}s ---")


if _should_run_bootstrap():
    bootstrap_routing_engine()

def get_nearest_node(lat, lon):
    if NODE_KDTREE is None or not NODE_IDS:
        return None
    _, idx = NODE_KDTREE.query([lon, lat])
    return NODE_IDS[int(idx)]

# Weights are passed per-request (no globals) for multi-user safety; see make_weight_optimized().

BAD_SURFACES = frozenset([
    'grass', 'dirt', 'sand', 'ground', 'unpaved', 'sett', 'gravel', 'wood',
    'fine_gravel', 'earth', 'mud', 'woodchips', 'cobblestone', 'pebblestone',
    'clay', 'grit', 'grass_paver', 'stone', 'unhewn_cobblestone', 'stepping_stones'
])
BAD_SMOOTHNESS = frozenset(['bad', 'very_bad', 'horrible', 'impassable'])

# --- BASE PHYSICS (implementation.md) ---
CYCLIST_SPEED_MPS = 16.0 / 3.6   # ~4.44 m/s (16 km/h)
SIGNAL_WAIT_SECONDS = 20         # Slightly increased so signal penalty is more visible
WIDTH_STD_M = 1.5
WIDTH_MIN_M = 1.25
SPEED_DIFF_NEGLIGIBLE_KMH = 20
SPEED_DIFF_LOW_KMH = 30
M_MIN = 0.1   # Ensure edge weight never zero/negative for A*
R_MIN = 0.1   # Reward multiplier minimum (rewards implemented as R < 1, not negative penalty)

# Highway-type length multipliers (cost ∝ length × M_highway × …)
PEDESTRIAN_HIGHWAY_M = 4.0
STEPS_HIGHWAY_M = 50.0
PEDESTRIAN_HIGHWAY_TYPES = frozenset(['footway', 'pedestrian', 'path'])
CYCLEWAY_TAG_KEYS = ('cycleway', 'cycleway_left', 'cycleway_right', 'cycleway_both')

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


def _has_dedicated_cycle_infrastructure(d):
    if str(d.get('type', '')).strip().lower() == 'cycleway':
        return True
    return any(str(d.get(k, '')).strip() for k in CYCLEWAY_TAG_KEYS)


def _highway_type_multiplier(d, pedestrian_highway_m: float | None = None):
    """Length multiplier for pedestrian ways without dedicated cycle infrastructure."""
    highway = str(d.get('type', '')).strip().lower()
    if highway == 'steps':
        return STEPS_HIGHWAY_M
    ped_m = pedestrian_highway_m if pedestrian_highway_m is not None else PEDESTRIAN_HIGHWAY_M
    if highway == 'service':
        if is_service_access_denied(d):
            return 1.0  # hard-blocked earlier in weight_fn
        if is_service_alley(d):
            return ped_m
        return STEPS_HIGHWAY_M
    if highway in PEDESTRIAN_HIGHWAY_TYPES and not _has_dedicated_cycle_infrastructure(d):
        return ped_m
    return 1.0


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
    """Width in metres for routing penalties and narrow overlays (see cost_masks.routing_width_m)."""
    return routing_width_m(d)

def _tfl_programmes(d):
    prog = str(d.get('tfl_cycle_programme', '')).strip().lower()
    if not prog: return []
    return [p.strip() for p in prog.split(';') if p.strip()]

def _is_tfl_cycleway_or_superhighway(d):
    programmes = _tfl_programmes(d)
    return 'cycleway' in programmes or 'superhighway' in programmes

def _is_tfl_quietway(d):
    return 'quietway' in _tfl_programmes(d)

def _is_yes_attr(val):
    return str(val or '').strip().lower() in ('yes', 'true', '1')


def _has_attraction_edge(d):
    """Green/scenic: OSM parks, manual park/river/sight regions (graph edge flags)."""
    return (
        _is_yes_attr(d.get('is_park'))
        or _is_yes_attr(d.get('is_river'))
        or _is_yes_attr(d.get('is_sight'))
    )


def _is_green_edge(d):
    """Park and river scenic edges only (excludes is_sight)."""
    return _is_yes_attr(d.get('is_park')) or _is_yes_attr(d.get('is_river'))

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


def _node_mini_roundabout_penalty(node_data):
    """Unsignalised mini-roundabout — same scale as zebra/give_way, separate from crossing penalty."""
    if str(node_data.get('traffic_signals', '')).lower() == 'yes':
        return 0.0
    if str(node_data.get('mini_roundabout', '')).strip().lower() in ('yes', 'true', '1'):
        return INTERSECTION_PENALTY_METRES
    return 0.0

def _edge_barrier_penalty(edge_data):
    """Additive barrier cost (cluster groups 2–4). See barrier_clusters.py."""
    return barrier_additive_penalty(edge_data)


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
    Prefer cached car_physical_road_count when set at bootstrap.
    """
    if node_id not in G.nodes:
        return 0
    nd = G.nodes[node_id]
    cached = nd.get('car_physical_road_count')
    if cached is not None:
        return int(cached)
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


def _cache_junction_node_flags(graph):
    """One-time pass: car_physical_road_count + is_dangerous_junction on each node."""
    t0 = time.perf_counter()
    dangerous = 0
    for node_id in graph.nodes:
        physical = set()
        for u in graph.predecessors(node_id):
            ed = graph.get_edge_data(u, node_id)
            if _is_car_allowed_edge(ed):
                physical.add((min(u, node_id), max(u, node_id)))
        for w in graph.successors(node_id):
            ed = graph.get_edge_data(node_id, w)
            if _is_car_allowed_edge(ed):
                physical.add((min(node_id, w), max(node_id, w)))
        count = len(physical)
        nd = graph.nodes[node_id]
        nd['car_physical_road_count'] = count
        if str(nd.get('traffic_signals', '')).lower() == 'yes':
            nd['is_dangerous_junction'] = False
        elif count >= JUNCTION_DANGER_MIN_CAR_ROADS:
            nd['is_dangerous_junction'] = True
            dangerous += 1
        else:
            nd['is_dangerous_junction'] = False
    print(
        f"--> Junction flags: {dangerous} dangerous junctions "
        f"({time.perf_counter() - t0:.1f}s)"
    )


def _junction_danger_penalty(node_id):
    """
    Complex junction without signals: O(1) lookup on is_dangerous_junction (bootstrap cache).
    """
    if node_id not in G.nodes:
        return 0.0
    if not G.nodes[node_id].get('is_dangerous_junction', False):
        return 0.0
    return 8.0


# One junction charge per ~35 m cluster (startup grid union-find on penalty nodes only).
JUNCTION_CLUSTER_RADIUS_M = 35.0
JUNCTION_CLUSTER_CELL_DEG = 0.00032


def _haversine_m(lon1, lat1, lon2, lat2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _speed_stress_multiplier(d):
    """Mild penalty by speed difference to cyclist (Literature Table 7)."""
    maxspeed_kmh = _parse_maxspeed_kmh(d)
    cyclist_kmh = CYCLIST_SPEED_MPS * 3.6
    diff = maxspeed_kmh - cyclist_kmh
    if diff < SPEED_DIFF_NEGLIGIBLE_KMH:
        return 0.0
    if diff <= SPEED_DIFF_LOW_KMH:
        return 0.15
    return 0.35


def _width_penalty_multiplier(d):
    """Width < 1.5m: slight; < 1.25m: moderate (not impassable)."""
    w = _get_width_m(d)
    if w is None:
        return 0.0
    if w >= WIDTH_STD_M:
        return 0.0
    if w >= WIDTH_MIN_M:
        return 0.2
    return 0.5


def _junction_cluster_score(node_id):
    """Higher = preferred representative for junction_weight penalties in a cluster."""
    if node_id not in G.nodes:
        return -1
    nd = G.nodes[node_id]
    if str(nd.get('traffic_signals', '')).lower() == 'yes':
        return -1
    score = 0
    if _node_intersection_penalty(nd) > 0:
        score += 100
    car = int(nd.get('car_physical_road_count', 0))
    if car >= JUNCTION_DANGER_MIN_CAR_ROADS:
        score += car
    if str(nd.get('mini_roundabout', '')).strip().lower() in ('yes', 'true', '1'):
        score += 50
    return score


def _build_junction_cluster_suppression():
    """Suppress duplicate junction penalties within JUNCTION_CLUSTER_RADIUS_M (once per physical junction)."""
    candidates = [n for n in G.nodes if _junction_cluster_score(n) > 0]
    if not candidates:
        return frozenset()

    parent = {n: n for n in candidates}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    grid = {}
    cell = JUNCTION_CLUSTER_CELL_DEG
    for n in candidates:
        lon, lat = float(n[0]), float(n[1])
        key = (int(lon / cell), int(lat / cell))
        grid.setdefault(key, []).append(n)

    r_m = JUNCTION_CLUSTER_RADIUS_M
    for n in candidates:
        lon1, lat1 = float(n[0]), float(n[1])
        cx, cy = int(lon1 / cell), int(lat1 / cell)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for m in grid.get((cx + dx, cy + dy), []):
                    if m is n:
                        continue
                    if _haversine_m(lon1, lat1, float(m[0]), float(m[1])) <= r_m:
                        union(n, m)

    clusters = {}
    for n in candidates:
        clusters.setdefault(find(n), []).append(n)

    suppressed = set()
    for members in clusters.values():
        rep = max(members, key=_junction_cluster_score)
        for n in members:
            if n != rep:
                suppressed.add(n)
    return frozenset(suppressed)


def _build_heuristic_penalty_floors(graph):
    """
    One O(edges) scan: admissible minimum penalty increment per multiplier type at weight=1.
    If any edge has zero increment for a type, floor is 0 (path may use only those edges).
    """
    t0 = time.perf_counter()
    has_zero_risk = False
    min_risk = float('inf')
    has_lit = False
    has_good_surface = False
    has_zero_speed_stress = False
    has_zero_width_penalty = False

    for _u, _v, d in graph.edges(data=True):
        risk = float(d.get('risk', 0.0))
        if risk <= 0:
            has_zero_risk = True
        elif risk < min_risk:
            min_risk = risk

        if is_lit(d):
            has_lit = True
        surface = str(d.get('surface', '')).lower()
        if surface not in BAD_SURFACES:
            has_good_surface = True
        if _speed_stress_multiplier(d) <= 0:
            has_zero_speed_stress = True
        width_m = _get_width_m(d)
        if width_m is None or width_m >= WIDTH_STD_M:
            has_zero_width_penalty = True

    floors = {
        'risk_weight': 0.0 if has_zero_risk else (min_risk if min_risk != float('inf') else 0.0),
        'light_weight': 0.0 if has_lit else 0.5,
        'surface_weight': 0.0 if has_good_surface else 3.0,
        'speed_weight': 0.0 if has_zero_speed_stress else 0.15,
        'width_weight': 0.0 if has_zero_width_penalty else 0.2,
    }
    set_penalty_floors(floors)
    print(
        f"--> Heuristic penalty floors: {floors} ({time.perf_counter() - t0:.1f}s)"
    )


if G is not None:
    _cache_junction_node_flags(G)
    _build_heuristic_penalty_floors(G)

JUNCTION_CLUSTER_SUPPRESSED = _build_junction_cluster_suppression()
print(
    f"Junction cluster dedup: {len(JUNCTION_CLUSTER_SUPPRESSED)} nodes suppressed "
    f"(radius {JUNCTION_CLUSTER_RADIUS_M:.0f} m)."
)


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
def _park_edge_blocked(d, hours_map, fallback_open):
    if _is_yes_attr(d.get('is_park')) and not park_opening_hours.is_park_edge_open(d, hours_map, fallback_open):
        return True
    return False


def make_weight_fastest(hours_map, fallback_open):
    def weight_fn(u, v, d):
        if is_service_access_denied(d):
            return BARRIER_HARD_COST
        if barrier_is_hard_block(d):
            return BARRIER_HARD_COST
        if _park_edge_blocked(d, hours_map, fallback_open):
            return BARRIER_HARD_COST
        return float(d.get('length', 1.0)) * _highway_type_multiplier(d)
    return weight_fn


def make_weight_optimized(w, hours_map, fallback_open):
    """
    Return a weight function (u, v, d) -> cost using request-scoped weights (no globals).
    Rewards (TfL, green) are implemented as multiplier R < 1 on length, not negative penalty,
    to keep A* heuristic well-behaved.
    """
    w_risk = w.get('risk_weight', 0.0)
    w_light = w.get('light_weight', 0.0)
    w_surface = w.get('surface_weight', 0.0)
    w_hill = w.get('hill_weight', 0.0)
    w_tfl_cw = w.get('tfl_cycleway_weight', 0.0)
    w_tfl_qw = w.get('tfl_quietway_weight', 0.0)
    w_speed = w.get('speed_weight', 0.0)
    w_width = w.get('width_weight', 0.0)
    w_green = w.get('green_weight', 0.0)
    w_barrier = w.get('barrier_weight', 0.0)
    w_calming = w.get('calming_weight', 0.0)
    w_junction = w.get('junction_weight', 0.0)
    w_signal = w.get('signal_weight', 0.0)
    w_tfl_live = w.get('tfl_live_weight', 0.0)
    w_vf = w.get('vehicular_free_weight', 0.0)
    calming_src = w.get('calming_source', 'way')
    tfl_live_on = w_tfl_live > 0
    tfl_cw_on = w_tfl_cw > 0
    tfl_qw_on = w_tfl_qw > 0
    green_on = w_green > 0
    vf_on = w_vf > 0
    hill_on = w_hill > 0
    hard_cost = BARRIER_HARD_COST
    junction_suppressed = JUNCTION_CLUSTER_SUPPRESSED
    ped_highway_m = w.get("pedestrian_highway_m")
    if ped_highway_m is not None:
        ped_highway_m = float(ped_highway_m)

    def weight_fn(u, v, d):
        if is_service_access_denied(d):
            return hard_cost
        if barrier_is_hard_block(d):
            return hard_cost
        if _park_edge_blocked(d, hours_map, fallback_open):
            return hard_cost

        disruption = None
        if tfl_live_on:
            disruption = live_disruptions.get_edge_disruption(u, v)
            if disruption and (disruption.get('has_closure') or disruption.get('is_closed')):
                return hard_cost

        length = float(d.get('length', 1.0))

        vehicular_free = is_vehicular_free(d)
        on_steps = masks_surface_and_hill(d)

        risk_penalty = 0.0 if vehicular_free else float(d.get('risk', 0.0)) * w_risk
        light_penalty = (0.0 if is_lit(d) else 0.5) * w_light
        surface = str(d.get('surface', '')).lower()
        surface_penalty = (
            0.0 if on_steps else (3.0 if surface in BAD_SURFACES else 0.0) * w_surface
        )
        speed_m = 0.0 if vehicular_free else _speed_stress_multiplier(d) * w_speed
        width_m = _width_penalty_multiplier(d) * w_width

        M_total = 1.0 + risk_penalty + light_penalty + surface_penalty + speed_m + width_m
        M_total = max(M_MIN, M_total)

        R = 1.0
        if tfl_cw_on and _is_tfl_cycleway_or_superhighway(d):
            R *= TFL_CYCLEWAY_REWARD
        if tfl_qw_on and _is_tfl_quietway(d):
            R *= TFL_QUIETWAY_REWARD
        if green_on and _has_attraction_edge(d):
            R *= GREEN_REWARD
        if vf_on and is_segregated_cycling(d):
            R *= 1.0 - (1.0 - VEHICULAR_FREE_REWARD) * w_vf
        R = max(R_MIN, R)

        node_v = G.nodes[v] if v in G.nodes else {}
        if v in junction_suppressed:
            A_intersection = 0.0
            A_mini_roundabout = 0.0
            A_junction = 0.0
        else:
            A_intersection = _node_intersection_penalty(node_v) * w_junction
            A_mini_roundabout = _node_mini_roundabout_penalty(node_v) * w_junction
            A_junction = (8.0 if node_v.get('is_dangerous_junction', False) else 0.0) * w_junction
        A_barrier = _edge_barrier_penalty(d) * w_barrier
        A_give_way = _edge_give_way_penalty(d) * w_junction
        A_stop_sign = _edge_stop_sign_penalty(d) * w_junction
        A_signal = _node_signal_penalty(node_v) * w_signal
        A_calming = (
            0.0 if vehicular_free else _traffic_calming_additive(d, calming_src) * w_calming
        )
        A_total = (
            A_intersection + A_mini_roundabout + A_barrier + A_give_way + A_stop_sign
            + A_signal + A_junction + A_calming
        )

        H = 0.0
        if hill_on and not on_steps:
            grade = float(d.get('grade', 0.0))
            hill_cost = 0.0
            if grade > 0:
                work_penalty = grade * 20.0
                power_penalty = (grade * 20.0) ** 2 if grade > UP_THRESH else 0.0
                hill_cost = length * (work_penalty + power_penalty)
            elif grade < DOWN_THRESH:
                hill_cost = length * 1.5
            H = hill_cost * w_hill

        if disruption:
            if disruption.get('is_diversion'):
                M_total += 5.0 * w_tfl_live
            cat = disruption.get('category', '')
            if cat == 'Works':
                M_total += 3.0 * w_tfl_live
            elif cat in ('Collisions', 'Emergency service incidents',
                         'Traffic Incidents', 'Network delays'):
                M_total += 2.0 * w_tfl_live
            if disruption.get('temporary_bad_surface'):
                M_total += 3.0 * w_tfl_live
            if disruption.get('environmental_hazard'):
                M_total *= 1.3
            sev_mult = disruption.get('severity_multiplier', 1.0)
            if sev_mult > 1.0:
                M_total *= sev_mult

        M_highway = _highway_type_multiplier(d, ped_highway_m)
        return (length * M_total * M_highway * R) + A_total + H
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


def _coords_close(a, b, eps=1e-7):
    return abs(a[0] - b[0]) < eps and abs(a[1] - b[1]) < eps


def apply_endpoint_stubs(coords, start_snap, end_snap):
    """Prepend/append exact edge snap points for seamless map polylines (visual only)."""
    if not coords:
        start_pt = [start_snap.snap_lat, start_snap.snap_lon]
        end_pt = [end_snap.snap_lat, end_snap.snap_lon]
        if _coords_close(start_pt, end_pt):
            return [start_pt]
        return [start_pt, end_pt]
    out = list(coords)
    start_pt = [start_snap.snap_lat, start_snap.snap_lon]
    if not _coords_close(start_pt, out[0]):
        out.insert(0, start_pt)
    end_pt = [end_snap.snap_lat, end_snap.snap_lon]
    if not _coords_close(end_pt, out[-1]):
        out.append(end_pt)
    return out


def _snap_meta(snap):
    return {
        "distance_m": round(snap.distance_m, 1),
        "anchor": str(snap.anchor_node),
    }

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
    scenic_green_length = 0.0
    segregated_cycling_length = 0.0
    barrier_count = 0
    barrier_penalty_count = 0
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
        vehicular_free = is_vehicular_free(edge_data)
        on_steps = masks_surface_and_hill(edge_data)
        if not vehicular_free:
            total_accidents += float(edge_data.get('risk', 0))
        if is_lit(edge_data): lit_length += l
        s = str(edge_data.get('surface', '')).lower()
        smoothness = str(edge_data.get('smoothness', '')).lower()
        if not on_steps and (s in BAD_SURFACES or smoothness in BAD_SMOOTHNESS):
            rough_length += l
        if is_segregated_cycling(edge_data):
            segregated_cycling_length += l
        grade = float(edge_data.get('grade', 0.0))
        if not on_steps:
            if grade > 0:
                total_climb += (grade * l)
            if grade > UP_THRESH or grade < DOWN_THRESH:
                steep_count += 1

        if _is_tfl_cycleway_or_superhighway(edge_data): tfl_cycleway_length += l
        if _is_tfl_quietway(edge_data): tfl_quietway_length += l
        if not vehicular_free and _speed_stress_multiplier(edge_data) > 0:
            speed_stress_length += l
        width_m = _get_width_m(edge_data)
        if width_m is not None and width_m < WIDTH_STD_M:
            narrow_length += l
        if _has_attraction_edge(edge_data): green_length += l
        if _is_green_edge(edge_data): scenic_green_length += l
        if (
            not vehicular_free
            and _traffic_calming_additive(edge_data, calming_source) > 0
        ):
            calming_count += 1

        if barrier_is_hard_block(edge_data) or _edge_barrier_penalty(edge_data) > 0:
            barrier_count += 1
        if _edge_barrier_penalty(edge_data) > 0:
            barrier_penalty_count += 1
        if _edge_give_way_penalty(edge_data) > 0: give_way_count += 1
        if _edge_stop_sign_penalty(edge_data) > 0: stop_sign_count += 1
        node_v = G.nodes[v] if v in G.nodes else {}
        if _node_signal_penalty(node_v) > 0: signal_count += 1
        if v not in JUNCTION_CLUSTER_SUPPRESSED and (
            _node_intersection_penalty(node_v) > 0
            or _node_mini_roundabout_penalty(node_v) > 0
            or node_v.get('is_dangerous_junction', False)
        ):
            junction_count += 1
        if live_disruptions.get_edge_disruption(u, v): disruption_count += 1

    duration_min = total_length / (CYCLIST_SPEED_MPS * 60.0) if CYCLIST_SPEED_MPS else total_length / 266.0
    pct_lit = (lit_length / total_length * 100) if total_length > 0 else 0
    pct_rough = (rough_length / total_length * 100) if total_length > 0 else 0
    narrow_km = narrow_length / 1000.0
    speed_stress_km = speed_stress_length / 1000.0
    speed_stress_pct = (speed_stress_length / total_length * 100) if total_length > 0 else 0
    green_km = green_length / 1000.0
    pct_green = (scenic_green_length / total_length * 100) if total_length > 0 else 0
    pct_vf = (segregated_cycling_length / total_length * 100) if total_length > 0 else 0
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
        "green_pct": round(pct_green, 1), "vehicular_free_pct": round(pct_vf, 1),
        "barrier_count": barrier_count, "barrier_penalty_count": barrier_penalty_count,
        "give_way_count": give_way_count, "stop_sign_count": stop_sign_count,
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
        if _has_attraction_edge(d):
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


def get_node_highlights(path_nodes, w=None, overlay_mode=False):
    """
    For the optimized path, collect node- and edge-based features for map icons.
    Barrier, give_way, stop_sign are EDGE-based: plot a single point at stored original position.
    When overlay_mode=False, only includes highlights for features with weight > 0 (legacy).
    When overlay_mode=True, returns all features on the path for client-side overlay toggles.
    """
    w = w or {}
    out = []
    seen = set()  # (key, type) to avoid duplicate markers

    def weight_on(key):
        return overlay_mode or w.get(key, 0.0) > 0

    calming_src = 'both' if overlay_mode else w.get('calming_source', 'way')

    # --- Edge-based: barrier, give_way, stop_sign (plot point at stored position only) ---
    for i in range(len(path_nodes) - 1):
        u, v = path_nodes[i], path_nodes[i + 1]
        ed = G.get_edge_data(u, v) or {}
        key = (u, v)

        if weight_on('barrier_weight') and (barrier_is_hard_block(ed) or _edge_barrier_penalty(ed) > 0) and (key, 'barrier') not in seen:
            seen.add((key, 'barrier'))
            lat, lon = _edge_display_point(ed, 'barrier_lat', 'barrier_lon')
            if lat is not None and lon is not None:
                details = {"barrier": str(ed.get('barrier', '')).strip().lower()}
                meta = barrier_cluster_meta(ed)
                if meta:
                    details.update(meta)
                out.append({"lat": lat, "lon": lon, "type": "barrier", "details": details})

        if weight_on('junction_weight'):
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

        if weight_on('signal_weight') and _node_signal_penalty(node_data) > 0 and (v, 'signal') not in seen:
            seen.add((v, 'signal'))
            out.append({"lat": lat, "lon": lon, "type": "signal", "details": {"traffic_signals": "yes"}})

        if weight_on('junction_weight') and v not in JUNCTION_CLUSTER_SUPPRESSED:
            if _node_intersection_penalty(node_data) > 0 and (v, 'junction') not in seen:
                seen.add((v, 'junction'))
                details = {'crossing': node_data.get('crossing_type') or node_data.get('crossing') or 'zebra/uncontrolled'}
                out.append({"lat": lat, "lon": lon, "type": "junction", "details": details})
            if _node_mini_roundabout_penalty(node_data) > 0 and (v, 'mini_roundabout') not in seen:
                seen.add((v, 'mini_roundabout'))
                out.append({"lat": lat, "lon": lon, "type": "mini_roundabout", "details": {"mini_roundabout": "yes"}})
            car_road_count = int(node_data.get('car_physical_road_count', 0))
            if node_data.get('is_dangerous_junction', False) and (v, 'junction_danger') not in seen:
                seen.add((v, 'junction_danger'))
                out.append({"lat": lat, "lon": lon, "type": "junction_danger", "details": {"car_road_count": car_road_count}})

        if weight_on('calming_weight') and i > 0:
            u = path_nodes[i - 1]
            ed = G.get_edge_data(u, v) or {}
            if is_vehicular_free(ed):
                continue
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

        snap = tfl_live.snap_to_edge(lat, lon)
        if not snap:
            return jsonify({"error": "No edge found within snap distance"}), 404

        best_u, best_v = snap.u, snap.v
        best_edge_data = G.get_edge_data(best_u, best_v)

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
                "geometry": geometry,
                "snap_point": [snap.snap_lat, snap.snap_lon],
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


# --- OVERLAY CATALOG (main app route visualization) ---

ROUTE_OVERLAY_CATALOG = {
    "version": 1,
    "edge": [
        {"id": "lit", "label": "Lit segments", "chunk_key": "lit_chunks"},
        {"id": "steep", "label": "Steep / uphill", "chunk_key": "steep_chunks"},
        {"id": "tflCycleway", "label": "TfL cycleways", "chunk_key": "tfl_cycleway_chunks"},
        {"id": "tflQuietway", "label": "TfL quietways", "chunk_key": "tfl_quietway_chunks"},
        {"id": "green", "label": "Green / scenic", "chunk_key": "green_chunks"},
        {"id": "narrow", "label": "Narrow facility", "chunk_key": "narrow_chunks"},
        {"id": "disruptions", "label": "Live disruptions", "chunk_key": "disruption_chunks"},
    ],
    "point": [
        {"id": "barriers", "label": "Barriers", "highlight_types": ["barrier"]},
        {"id": "signals", "label": "Traffic signals", "highlight_types": ["signal"]},
        {"id": "junctionDanger", "label": "Junctions & crossings",
         "highlight_types": ["junction", "junction_danger", "give_way", "stop_sign", "mini_roundabout"]},
        {"id": "calming", "label": "Traffic calming", "highlight_types": ["calming"]},
    ],
}


@app.route('/overlay_catalog', methods=['GET'])
def get_overlay_catalog():
    """Metadata for main-app route overlay picker (display only; routing uses profile weights)."""
    return jsonify(ROUTE_OVERLAY_CATALOG)


# --- PROFILE ENDPOINTS ---

@app.route('/profiles', methods=['GET'])
def list_profiles():
    try:
        return jsonify({"profiles": user_profiles.list_profiles()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/profiles/<user_id>', methods=['GET'])
def get_profile(user_id):
    try:
        profile = user_profiles.get_profile(user_id)
        if not profile:
            return jsonify({"error": "Profile not found"}), 404
        return jsonify(profile)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/profiles', methods=['POST'])
def create_profile():
    try:
        body = request.get_json(silent=True) or {}
        name = body.get("name", "")
        weights = body.get("weights", {})
        profile, err = user_profiles.create_profile(name, weights)
        if err:
            return jsonify({"error": err}), 400
        return jsonify(profile), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- ROUTING ENDPOINTS ---

@app.route('/route', methods=['GET'])
def get_route():
    try:
        start_lat = float(request.args.get('start_lat'))
        start_lon = float(request.args.get('start_lon'))
        end_lat = float(request.args.get('end_lat'))
        end_lon = float(request.args.get('end_lon'))

        profile_id = (request.args.get('profile_id') or '').strip() or None
        active_profile_id = None

        if profile_id:
            profile_weights = user_profiles.get_profile_weights(profile_id)
            if profile_weights is None:
                return jsonify({"error": f"Profile not found: {profile_id}"}), 404
            w = user_profiles.clamp_weights(profile_weights)
            w["calming_source"] = user_profiles.CALMING_SOURCE
            active_profile_id = profile_id
        else:
            w = user_profiles.build_weight_dict_from_request(request.args)

        t_route = time.perf_counter()
        start_snap = tfl_live.snap_to_edge(start_lat, start_lon)
        end_snap = tfl_live.snap_to_edge(end_lat, end_lon)
        t_snap = time.perf_counter() - t_route

        if not start_snap or not end_snap:
            return jsonify({"error": "Could not snap to network"}), 400

        start_node = start_snap.anchor_node
        end_node = end_snap.anchor_node

        at_time = park_opening_hours.london_now()
        unique_hours = G.graph.get("park_opening_hours_unique") or []
        hours_map, fallback_open = park_opening_hours.build_request_hours_context(unique_hours, at_time)

        weight_fastest = make_weight_fastest(hours_map, fallback_open)
        h_fast = make_heuristic(end_node, G, cost_per_m=1.0)
        t0 = time.perf_counter()
        path_fastest = nx.astar_path(G, start_node, end_node, heuristic=h_fast, weight=weight_fastest)
        t_fast = time.perf_counter() - t0
        coords_fastest = apply_endpoint_stubs(
            reconstruct_path_geometry(path_fastest), start_snap, end_snap
        )
        stats_fastest = calculate_path_stats(path_fastest)

        scale = compute_optimized_cost_per_metre_lower_bound(w)
        h_opt = make_heuristic(end_node, G, cost_per_m=scale)
        weight_optimized = make_weight_optimized(w, hours_map, fallback_open)
        t0 = time.perf_counter()
        path_optimized = nx.astar_path(G, start_node, end_node, heuristic=h_opt, weight=weight_optimized)
        t_opt = time.perf_counter() - t0

        t_compute = t_snap + t_fast + t_opt
        if os.environ.get("ROUTE_BENCHMARK", "").lower() in ("1", "true", "yes"):
            print(
                f"ROUTE_BENCHMARK snap={t_snap*1000:.1f}ms fastest={t_fast*1000:.1f}ms "
                f"optimized={t_opt*1000:.1f}ms scale={scale:.3f}"
            )
        coords_optimized = apply_endpoint_stubs(
            reconstruct_path_geometry(path_optimized), start_snap, end_snap
        )
        stats_optimized = calculate_path_stats(path_optimized, calming_source=user_profiles.CALMING_SOURCE)

        # Route-only overlay chunks (only segments on path_optimized that match each criterion)
        lit_chunks = get_lit_sections(path_optimized)
        steep_chunks = get_steep_sections(path_optimized)
        tfl_cycleway_chunks = get_tfl_cycleway_sections(path_optimized)
        tfl_quietway_chunks = get_tfl_quietway_sections(path_optimized)
        green_chunks = get_green_sections(path_optimized)
        narrow_chunks = get_narrow_sections(path_optimized)
        disruption_chunks = get_disruption_sections(path_optimized)  # path-only, like lit/steep/narrow
        node_highlights = get_node_highlights(path_optimized, w, overlay_mode=True)

        return jsonify({
            "status": "success",
            "meta": {
                "cost_per_m_lower_bound": round(scale, 4),
                "active_profile_id": active_profile_id,
                "weights": {k: w[k] for k in user_profiles.ROUTING_WEIGHT_KEYS},
                "calming_source": user_profiles.CALMING_SOURCE,
                "timing_ms": {
                    "snap": round(t_snap * 1000, 1),
                    "fastest_astar": round(t_fast * 1000, 1),
                    "optimized_astar": round(t_opt * 1000, 1),
                    "total": round(t_compute * 1000, 1),
                },
                "snap": {
                    "start": _snap_meta(start_snap),
                    "end": _snap_meta(end_snap),
                },
                "park_hours_at": at_time.isoformat(),
                "park_fallback_open": fallback_open,
                "park_hours_map_size": len(hours_map),
            },
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
    app.run(debug=True, port=5000, use_reloader=USE_RELOADER)