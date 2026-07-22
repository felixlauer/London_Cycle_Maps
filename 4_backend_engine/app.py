"""
Main routing backend: /route, /inspect, /profiles. Uses 1_data/london_elev_final_tfl.gpickle (fast) or .graphml fallback.
Profile-driven routing via user_profiles.json (local mock DB). When changing API or cost logic, update 0_documentation/APP_MAIN.md.
"""
from flask import Flask, request, jsonify, g
from flask_cors import CORS
import math
import networkx as nx
import numpy as np
from scipy.spatial import cKDTree
from shapely.wkt import loads as load_wkt
import os
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "3_pipeline"))
from graph_io import load_graph, fast_path

import tfl_live
import tomtom_live
import live_disruptions
import santander_live
from route_time_estimate import cruise_duration_min, duration_speed_multiplier_for_preset
from routing_heuristic import (
    compute_optimized_cost_per_metre_lower_bound,
    get_route_algorithm,
    get_route_fastest_heuristic_epsilon,
    get_route_heuristic_epsilon,
    green_reward,
    make_backward_heuristic,
    make_heuristic,
    set_penalty_floors,
    tfl_network_reward,
    vehicular_free_reward,
)
import pathfinding
import edge_cost_arrays
import graph_csr
import pathfinding_numba
import mapbox_usage
import weather_proxy
from barrier_clusters import (
    BARRIER_HARD_COST,
    barrier_additive_penalty,
    barrier_is_hard_block,
    barrier_cluster_meta,
)
from cost_masks import (
    is_service_access_denied,
    is_service_alley,
    is_vehicular_free,
    masks_surface_and_hill,
    routing_width_m,
    vf_allowed_masks,
    vf_flags,
    VF_MASK_ALL,
)
import night_time
import translation_layer
import user_profiles
import park_opening_hours
import auth_admin
import auth_middleware
import auth_rate_limit
import route_vias
from cycleway_clusters import classify_cycleway_edge
from auth_middleware import require_auth, assert_profile_access, extract_bearer_token
from auth_rate_limit import client_ip_from_request

# --- CONFIGURATION ---
# UPDATED: Pointing to the final, clean, dual-pass processed graph
GRAPH_PATH = os.path.join("..", "1_data", "london_elev_final_tfl.graphml")

USE_RELOADER = os.environ.get("FLASK_USE_RELOADER", "").lower() in ("1", "true", "yes")

app = Flask(__name__)
CORS(app)
auth_middleware.init_auth(app)

G = None
node_data = []
NODE_KDTREE = None
NODE_IDS = []
# Set True when static routing cache was applied (skips cold junction/tables/CSR/geom).
_ROUTING_CACHE_HIT = False
JUNCTION_CLUSTER_SUPPRESSED = frozenset()


def _should_run_bootstrap():
    if os.environ.get("ROUTING_CACHE_BUILD", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return False
    if not USE_RELOADER:
        return True
    return os.environ.get("WERKZEUG_RUN_MAIN") == "true"


def _apply_early_cli_env():
    """Flags that must take effect before bootstrap (import-time)."""
    if "--no-live" in sys.argv:
        os.environ["SKIP_DISRUPTION_FETCH"] = "1"
    if "--weather-test" in sys.argv:
        os.environ["WEATHER_TEST_MODE"] = "1"


_apply_early_cli_env()


def bootstrap_routing_engine():
    global G, node_data, NODE_KDTREE, NODE_IDS, _ROUTING_CACHE_HIT
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

    # Node XY stamps for heuristics (cost tables / VF / _coords built after junction cluster).
    t0 = time.perf_counter()
    n_xy = edge_cost_arrays.stamp_node_xy(G)
    print(f"--> Node XY stamps: {n_xy} nodes ({time.perf_counter() - t0:.1f}s)")

    # Try static routing cache before live STRtree / cold rebuilds.
    import routing_cache

    bundle, reason = routing_cache.try_load(GRAPH_PATH, G)
    if bundle is not None:
        t0 = time.perf_counter()
        print(f"--> Routing cache: loading ({reason})...", flush=True)
        try:
            _apply_routing_cache_early(bundle)
            _ROUTING_CACHE_HIT = True
            print(
                f"--> Routing cache: applied in {time.perf_counter() - t0:.1f}s "
                f"(formula={bundle.meta.get('formula_id')})"
            )
        except Exception as exc:
            print(f"--> Routing cache: apply failed ({exc}); falling back to cold build")
            _ROUTING_CACHE_HIT = False
            live_disruptions.init(G)
            if live_disruptions.live_fetch_enabled():
                live_disruptions.start_background_refresh()
            santander_live.start_background_refresh()
    else:
        print(f"--> Routing cache: miss ({reason})")
        t0 = time.perf_counter()
        live_disruptions.init(G)
        if not live_disruptions.live_fetch_enabled():
            print(f"--> Live disruption index: init only, fetch off ({time.perf_counter() - t0:.1f}s)")
        else:
            live_disruptions.start_background_refresh()
            print(f"--> Live disruption index: {time.perf_counter() - t0:.1f}s")
        santander_live.start_background_refresh()

    print(f"--- Early bootstrap complete in {time.perf_counter() - t_boot:.1f}s ---")


def _apply_routing_cache_early(bundle):
    """Stamp graph + install tables/CSR/STRtree from cache. Sets module globals later."""
    global JUNCTION_CLUSTER_SUPPRESSED
    import routing_cache
    from routing_heuristic import set_penalty_floors

    suppressed = routing_cache.apply_bundle_to_graph(G, bundle)
    JUNCTION_CLUSTER_SUPPRESSED = suppressed
    set_penalty_floors(bundle.floors)

    tables = routing_cache.bundle_to_tables(bundle)
    edge_cost_arrays.install_tables(tables, G)
    csr = routing_cache.bundle_to_csr(bundle)
    graph_csr.set_csr(csr)

    geoms, keys = routing_cache.wkb_geoms_and_keys(bundle)
    # Map keys to actual G node objects when float-tuple identity matches.
    mapped_keys = []
    for u, v in keys:
        if u not in G or v not in G:
            raise KeyError(f"cache edge endpoints not in G: {u!r}->{v!r}")
        mapped_keys.append((u, v))
    tfl_live.init_from_geoms(G, geoms, mapped_keys)
    if live_disruptions.live_fetch_enabled():
        live_disruptions.start_background_refresh()
    else:
        print("--> Live disruption index: from cache, fetch off")
    santander_live.start_background_refresh()


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
CYCLIST_SPEED_MPS = 16.0 / 3.6   # ~4.44 m/s (16 km/h) - penalty physics reference speed
DEFAULT_STATS_SPEED_KMH = 16.0   # duration_min fallback when no bike type given
WIDTH_STD_M = 1.5                # narrow stats/overlay threshold (width_weight removed from cost)
SIGNAL_WAIT_SECONDS = 20         # Slightly increased so signal penalty is more visible
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

_TFL_NETWORK_PROGRAMMES = frozenset(['cycleway', 'superhighway', 'quietway'])

def _is_tfl_network(d):
    """Merged TfL network: cycleways, superhighways and quietways share one reward."""
    return any(p in _TFL_NETWORK_PROGRAMMES for p in _tfl_programmes(d))

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

    floors = {
        'risk_weight': 0.0 if has_zero_risk else (min_risk if min_risk != float('inf') else 0.0),
        'light_weight': 0.0 if has_lit else 0.5,
        'surface_weight': 0.0 if has_good_surface else 3.0,
        'speed_weight': 0.0 if has_zero_speed_stress else 0.15,
    }
    set_penalty_floors(floors)
    print(
        f"--> Heuristic penalty floors: {floors} ({time.perf_counter() - t0:.1f}s)"
    )


if G is not None and not _ROUTING_CACHE_HIT:
    _cache_junction_node_flags(G)
    _build_heuristic_penalty_floors(G)
    _t_junc_cluster = time.perf_counter()
    JUNCTION_CLUSTER_SUPPRESSED = _build_junction_cluster_suppression()
    print(
        f"--> Junction cluster dedup: {len(JUNCTION_CLUSTER_SUPPRESSED)} nodes suppressed "
        f"(radius {JUNCTION_CLUSTER_RADIUS_M:.0f} m; "
        f"{time.perf_counter() - _t_junc_cluster:.1f}s)"
    )
elif G is not None and _ROUTING_CACHE_HIT:
    print(
        f"--> Junction/floors/cluster: from routing cache "
        f"({len(JUNCTION_CLUSTER_SUPPRESSED)} suppressed)"
    )


def _finish_routing_from_cache():
    """Shared overlays + Numba warmup after cache hit (geom already stamped)."""
    if G is None:
        return
    live_disruptions.set_on_master_rebuilt(
        edge_cost_arrays.refresh_shared_overlays_from_graph
    )
    shared = edge_cost_arrays.refresh_shared_overlays_from_graph()
    if shared is not None:
        print(
            f"--> Shared overlays: bake {shared.bake_s*1000:.1f} ms "
            f"(live={shared.has_live}, impassable={int(shared.impassable.sum()):,})"
        )
    csr = graph_csr.get_csr()
    tables = edge_cost_arrays.get_tables()
    if csr is not None:
        print(
            f"--> Graph CSR: {csr.n_nodes:,} nodes, {csr.n_edges:,} arcs "
            f"(from routing cache; CSR_ASTAR="
            f"{'on' if graph_csr.csr_astar_enabled() else 'off'} for search)"
        )
    if tables is not None:
        vf_n = int(np.count_nonzero(tables.vf_flags))
        print(
            f"--> Edge cost arrays: {tables.n_edges:,} edges from routing cache "
            f"(VF flagged={vf_n:,}; ARRAY_COSTS="
            f"{'on' if edge_cost_arrays.array_costs_enabled() else 'off'})"
        )
    if (
        pathfinding_numba.numba_astar_enabled()
        and pathfinding_numba.is_available()
        and tables is not None
        and shared is not None
        and csr is not None
    ):
        warm_s = pathfinding_numba.warmup(csr, tables, shared, hard_cost=BARRIER_HARD_COST)
        print(f"--> Numba A* warmup: {warm_s:.1f}s (NUMBA_ASTAR=on)")
    elif not pathfinding_numba.is_available():
        print("--> Numba A*: skipped (numba not installed)")
    elif not pathfinding_numba.numba_astar_enabled():
        print("--> Numba A*: skipped (NUMBA_ASTAR=off)")
    # Geometry already on edges from cache — do not start GEOM_PREPARSE.
    n_e = int(tables.n_edges) if tables is not None else 0
    edge_cost_arrays.mark_geom_preparse_from_cache(n_e)
    print("--> Geometry: from routing cache (runtime GEOM_PREPARSE skipped)")


def _install_edge_cost_arrays():
    """One edge pass: VF + cost tables + _eid + _coords; initial SharedOverlays."""
    if G is None:
        return
    tables, build_s = edge_cost_arrays.build_edge_cost_tables(
        G,
        junction_suppressed=JUNCTION_CLUSTER_SUPPRESSED,
        bad_surfaces=BAD_SURFACES,
        up_thresh=UP_THRESH,
        down_thresh=DOWN_THRESH,
        is_lit_fn=is_lit,
        speed_stress_fn=_speed_stress_multiplier,
        is_tfl_fn=_is_tfl_network,
        has_attraction_fn=_has_attraction_edge,
        highway_mult_fn=_highway_type_multiplier,
        barrier_penalty_fn=_edge_barrier_penalty,
        give_way_fn=_edge_give_way_penalty,
        stop_sign_fn=_edge_stop_sign_penalty,
        calming_fn=_traffic_calming_additive,
        signal_fn=_node_signal_penalty,
        intersection_fn=_node_intersection_penalty,
        mini_rb_fn=_node_mini_roundabout_penalty,
        is_yes_fn=_is_yes_attr,
        parse_geometry=False,  # lazy _coords on first extract_segment_geometry (avoids ~minutes of WKT)
    )
    edge_cost_arrays.install_tables(tables, G)
    vf_n = int(np.count_nonzero(tables.vf_flags))
    print(
        f"--> Edge cost arrays: {tables.n_edges:,} edges in {build_s:.1f}s "
        f"(VF flagged={vf_n:,}; ARRAY_COSTS="
        f"{'on' if edge_cost_arrays.array_costs_enabled() else 'off'})"
    )
    live_disruptions.set_on_master_rebuilt(
        edge_cost_arrays.refresh_shared_overlays_from_graph
    )
    shared = edge_cost_arrays.refresh_shared_overlays_from_graph()
    if shared is not None:
        print(
            f"--> Shared overlays: bake {shared.bake_s*1000:.1f} ms "
            f"(live={shared.has_live}, impassable={int(shared.impassable.sum()):,})"
        )
    # Always build CSR after tables (Phase B NX/bi heuristics + optional CSR A*).
    # CSR_ASTAR only gates whether uni /route uses CSR search vs NetworkX.
    csr = graph_csr.build_csr(G)
    graph_csr.set_csr(csr)
    print(
        f"--> Graph CSR: {csr.n_nodes:,} nodes, {csr.n_edges:,} arcs "
        f"in {csr.build_s:.1f}s "
        f"(CSR_ASTAR={'on' if graph_csr.csr_astar_enabled() else 'off'} for search)"
    )
    tables = edge_cost_arrays.get_tables()
    shared = edge_cost_arrays.get_shared_overlays()
    if (
        pathfinding_numba.numba_astar_enabled()
        and pathfinding_numba.is_available()
        and tables is not None
        and shared is not None
    ):
        warm_s = pathfinding_numba.warmup(csr, tables, shared, hard_cost=BARRIER_HARD_COST)
        print(f"--> Numba A* warmup: {warm_s:.1f}s (NUMBA_ASTAR=on)")
    elif not pathfinding_numba.is_available():
        print("--> Numba A*: skipped (numba not installed)")
    elif not pathfinding_numba.numba_astar_enabled():
        print("--> Numba A*: skipped (NUMBA_ASTAR=off)")

    # Phase D: WKT → _coords for all edges (TTF; not A*).
    # TODO(review): keep vs drop — full warm ~4 min after every start; see
    # 0_documentation/testing/geom_preparse_phase_d_report.md
    # Prefer routing cache (prebuild_routing_cache.py) over runtime warm.
    geom_mode = edge_cost_arrays.geom_preparse_mode()
    if geom_mode == "sync":
        print("--> Geometry preparse: sync (blocking)...", flush=True)
        stats = edge_cost_arrays.preparse_edge_geometries(G)
        print(
            f"--> Geometry preparse: {stats['n_parsed']:,} parsed in "
            f"{stats['elapsed_s']:.1f}s (GEOM_PREPARSE=sync)"
        )
    elif geom_mode == "background":
        edge_cost_arrays.start_geom_preparse_background(G)
        print("--> Geometry preparse: background thread started (GEOM_PREPARSE=background)")
    else:
        print("--> Geometry preparse: skipped (GEOM_PREPARSE=off; lazy _coords)")


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


if G is not None:
    if _ROUTING_CACHE_HIT:
        _finish_routing_from_cache()
    else:
        _install_edge_cost_arrays()

# --- COST FUNCTIONS ---
DEPART_AT_FUTURE_THRESHOLD = timedelta(minutes=30)


def parse_depart_at_arg(raw: str | None):
    """Optional ISO depart_at; naive → Europe/London. Invalid/empty → london_now()."""
    if not raw or not str(raw).strip():
        return park_opening_hours.london_now()
    try:
        dt = datetime.fromisoformat(str(raw).strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=park_opening_hours.LONDON_TZ)
        return dt.astimezone(park_opening_hours.LONDON_TZ)
    except Exception:
        return park_opening_hours.london_now()


def is_future_depart_at(at_time: datetime, now: datetime | None = None) -> bool:
    """True when at_time is more than 30 minutes ahead of London now."""
    now = now or park_opening_hours.london_now()
    return (at_time - now) > DEPART_AT_FUTURE_THRESHOLD


def _park_edge_blocked(d, hours_map, fallback_open):
    if _is_yes_attr(d.get('is_park')) and not park_opening_hours.is_park_edge_open(d, hours_map, fallback_open):
        return True
    return False


def make_weight_fastest(hours_map, fallback_open, apply_live: bool = True):
    def weight_fn(u, v, d):
        if is_service_access_denied(d):
            return BARRIER_HARD_COST
        if barrier_is_hard_block(d):
            return BARRIER_HARD_COST
        if _park_edge_blocked(d, hours_map, fallback_open):
            return BARRIER_HARD_COST
        if apply_live:
            disruption = live_disruptions.get_edge_disruption(u, v)
            if disruption and (disruption.get('has_closure') or disruption.get('is_closed')):
                return BARRIER_HARD_COST
        return float(d.get('length', 1.0)) * _highway_type_multiplier(d)
    return weight_fn


def make_weight_optimized(w, hours_map, fallback_open, apply_live: bool = True):
    """
    Return a weight function (u, v, d) -> cost using request-scoped weights (no globals).
    Rewards (TfL network, green, vehicular-free) are multipliers R < 1 on length -
    never subtraction - lerped by weight with saturation floors (routing_heuristic
    owns the formulas so the A* lower bound stays admissible in lockstep).
    """
    w_risk = w.get('risk_weight', 0.0)
    w_light = w.get('light_weight', 0.0)
    w_surface = w.get('surface_weight', 0.0)
    w_hill = w.get('hill_weight', 0.0)
    w_tfl_cw = w.get('tfl_cycleway_weight', 0.0)
    w_speed = w.get('speed_weight', 0.0)
    w_green = w.get('green_weight', 0.0)
    w_barrier = w.get('barrier_weight', 0.0)
    w_calming = w.get('calming_weight', 0.0)
    w_junction = w.get('junction_weight', 0.0)
    w_signal = w.get('signal_weight', 0.0)
    w_tfl_live = w.get('tfl_live_weight', 0.0)
    w_vf = w.get('vehicular_free_weight', 0.0)
    calming_src = w.get('calming_source', 'way')
    bike_type = str(w.get('bike_type', 'standard'))
    tfl_cw_on = w_tfl_cw > 0
    green_on = w_green > 0
    vf_on = w_vf > 0
    hill_on = w_hill > 0
    # Rewards precomputed once per request (formulas shared with the heuristic).
    r_tfl = tfl_network_reward(w_tfl_cw)
    r_green = green_reward(w_green)
    r_vf = vehicular_free_reward(w_vf)
    # Configurable vehicular-free set (infrastructure question): int AND per edge.
    vf_mask_allowed, vf_reward_allowed = vf_allowed_masks(
        shared_path=bool(w.get('vf_shared_path', True)),
        bus_lane=bool(w.get('vf_bus_lane', True)),
        painted_lane=bool(w.get('vf_painted_lane', False)),
    )
    hard_cost = BARRIER_HARD_COST
    junction_suppressed = JUNCTION_CLUSTER_SUPPRESSED
    ped_highway_m = w.get("pedestrian_highway_m")
    if ped_highway_m is not None:
        ped_highway_m = float(ped_highway_m)

    def weight_fn(u, v, d):
        if is_service_access_denied(d):
            return hard_cost
        if barrier_is_hard_block(d, bike_type):
            return hard_cost
        if _park_edge_blocked(d, hours_map, fallback_open):
            return hard_cost

        # Live closures always hard-block when apply_live (Leave now);
        # future Depart at ignores soft + hard live (honest v1 policy).
        disruption = None
        if apply_live:
            disruption = live_disruptions.get_edge_disruption(u, v)
            if disruption and (disruption.get('has_closure') or disruption.get('is_closed')):
                return hard_cost

        length = float(d.get('length', 1.0))

        edge_vf = d.get('_vf', 0)
        vehicular_free = bool(edge_vf & vf_mask_allowed)
        on_steps = masks_surface_and_hill(d)

        risk_penalty = 0.0 if vehicular_free else float(d.get('risk', 0.0)) * w_risk
        light_penalty = (0.0 if is_lit(d) else 0.5) * w_light
        surface = str(d.get('surface', '')).lower()
        surface_penalty = (
            0.0 if on_steps else (3.0 if surface in BAD_SURFACES else 0.0) * w_surface
        )
        speed_m = 0.0 if vehicular_free else _speed_stress_multiplier(d) * w_speed

        M_total = 1.0 + risk_penalty + light_penalty + surface_penalty + speed_m
        M_total = max(M_MIN, M_total)

        R = 1.0
        if tfl_cw_on and _is_tfl_network(d):
            R *= r_tfl
        if green_on and _has_attraction_edge(d):
            R *= r_green
        if vf_on and (edge_vf & vf_reward_allowed):
            R *= r_vf
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
            # Soft jam/works penalties scale with tfl_live_weight (jam-comfort
            # question); closures were already hard-blocked above.
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
                M_total *= 1.0 + 0.3 * min(w_tfl_live, 1.0)
            sev_mult = disruption.get('severity_multiplier', 1.0)
            if sev_mult > 1.0:
                M_total *= 1.0 + (sev_mult - 1.0) * min(w_tfl_live, 1.0)

        M_highway = _highway_type_multiplier(d, ped_highway_m)
        return (length * M_total * M_highway * R) + A_total + H
    return weight_fn

# --- HELPERS ---
def extract_segment_geometry(u, v):
    """Polyline [[lat, lon], ...] for edge u→v. Never mutates G (thread-safe)."""
    import edge_geom_store

    edge_data = G.get_edge_data(u, v)
    if not edge_data:
        return edge_geom_store.coords_for_edge(None, G, u, v)
    if G.is_multigraph():
        edge_data = next(iter(edge_data.values()))
    return edge_geom_store.coords_for_edge(edge_data, G, u, v)

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
    distance_m = round(snap.distance_m, 1)
    return {
        "distance_m": distance_m,
        "anchor": str(snap.anchor_node),
        # Soft warn: route still succeeds; client should prompt user to check accuracy.
        "far": snap.distance_m > tfl_live.SNAP_SOFT_WARN_M,
    }

# --- STATS ---
def calculate_path_stats(
    path_nodes,
    calming_source='way',
    speed_kmh=None,
    vf_mask_allowed=None,
    duration_speed_multiplier: float = 1.0,
):
    total_length = 0.0
    total_accidents = 0.0
    lit_length = 0.0
    rough_length = 0.0
    total_climb = 0.0
    steep_count = 0
    tfl_cycleway_length = 0.0
    tfl_quietway_length = 0.0
    speed_stress_length = 0.0
    green_length = 0.0
    scenic_green_length = 0.0
    vf_selected_length = 0.0
    barrier_count = 0
    barrier_penalty_count = 0
    give_way_count = 0
    stop_sign_count = 0
    calming_count = 0
    signal_count = 0
    junction_count = 0
    disruption_count = 0
    vf_mask = vf_mask_allowed if vf_mask_allowed is not None else VF_MASK_ALL
    for i in range(len(path_nodes) - 1):
        u = path_nodes[i]
        v = path_nodes[i+1]
        edge_data = G.get_edge_data(u, v) or {}
        l = float(edge_data.get('length', 0))
        total_length += l
        edge_vf = int(edge_data.get('_vf', 0)) or vf_flags(edge_data)
        vehicular_free = bool(edge_vf & vf_mask) if vf_mask_allowed is not None else is_vehicular_free(edge_data)
        on_steps = masks_surface_and_hill(edge_data)
        if not vehicular_free:
            total_accidents += float(edge_data.get('risk', 0))
        if is_lit(edge_data): lit_length += l
        s = str(edge_data.get('surface', '')).lower()
        smoothness = str(edge_data.get('smoothness', '')).lower()
        if not on_steps and (s in BAD_SURFACES or smoothness in BAD_SMOOTHNESS):
            rough_length += l
        if vehicular_free:
            vf_selected_length += l
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

    duration_min = cruise_duration_min(
        total_length,
        float(speed_kmh) if speed_kmh else DEFAULT_STATS_SPEED_KMH,
        duration_speed_multiplier,
    )
    pct_lit = (lit_length / total_length * 100) if total_length > 0 else 0
    pct_rough = (rough_length / total_length * 100) if total_length > 0 else 0
    speed_stress_km = speed_stress_length / 1000.0
    speed_stress_pct = (speed_stress_length / total_length * 100) if total_length > 0 else 0
    green_km = green_length / 1000.0
    pct_green = (scenic_green_length / total_length * 100) if total_length > 0 else 0
    pct_vf = (vf_selected_length / total_length * 100) if total_length > 0 else 0
    tfl_cycleway_pct = (tfl_cycleway_length / total_length * 100) if total_length > 0 else 0
    tfl_quietway_pct = (tfl_quietway_length / total_length * 100) if total_length > 0 else 0
    tfl_network_pct = tfl_cycleway_pct + tfl_quietway_pct
    return {
        "length_m": round(total_length, 0), "accidents": int(total_accidents),
        "duration_min": round(duration_min, 1), "illumination_pct": round(pct_lit, 0),
        "rough_pct": round(pct_rough, 0), "elevation_gain": round(total_climb, 0),
        "steep_count": steep_count,
        "tfl_cycleway_pct": round(tfl_cycleway_pct, 1), "tfl_quietway_pct": round(tfl_quietway_pct, 1),
        "tfl_network_pct": round(tfl_network_pct, 1),
        "speed_stress_km": round(speed_stress_km, 2), "speed_stress_pct": round(speed_stress_pct, 1),
        "green_km": round(green_km, 2),
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
        # Merged TfL infrastructure: cycleways + superhighways + quietways.
        if _is_tfl_network(d):
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


def get_vehicular_free_sections(path_nodes, vf_mask_allowed):
    out = []
    vf_mask = vf_mask_allowed if vf_mask_allowed is not None else VF_MASK_ALL
    for i in range(len(path_nodes) - 1):
        u, v = path_nodes[i], path_nodes[i+1]
        d = G.get_edge_data(u, v) or {}
        edge_vf = int(d.get('_vf', 0)) or vf_flags(d)
        if bool(edge_vf & vf_mask):
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


def _edge_length_m(d):
    try:
        return float(d.get('length', 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _typed_chunk(path, kind, length_m, **extra):
    """Typed overlay feature for v2 (legacy bare polylines remain separate)."""
    feat = {"path": path, "kind": kind, "length_m": round(float(length_m or 0.0), 2)}
    feat.update(extra)
    return feat


def _edge_attrs(u, v):
    raw = G.get_edge_data(u, v) or {}
    if G.is_multigraph():
        return next(iter(raw.values())) if raw else {}
    return raw or {}


def _merge_path_coords(paths):
    """Concatenate consecutive edge polylines, dropping duplicate joints."""
    out = []
    for path in paths:
        if not path:
            continue
        if not out:
            out.extend(path)
            continue
        # Drop first point if it duplicates the previous end
        if _coords_close(out[-1], path[0]):
            out.extend(path[1:])
        else:
            out.extend(path)
    return out


def _collapse_edge_runs(edge_feats):
    """
    Merge path-adjacent edges that share the same run_key into one feature.
    Each edge_feat needs: {run_key, kind, path, length_m, edge_i, ...}.
    Non-adjacent edges (gap in edge_i) never merge even with the same key.
    O(n) in emitted edges.
    """
    if not edge_feats:
        return []
    runs = []
    cur = None
    paths_buf = []
    last_i = None
    for feat in edge_feats:
        key = feat.get("run_key")
        edge_i = feat.get("edge_i")
        adjacent = last_i is not None and edge_i is not None and edge_i == last_i + 1
        if cur is None or key != cur["run_key"] or not adjacent:
            if cur is not None:
                cur["path"] = _merge_path_coords(paths_buf)
                cur["length_m"] = round(float(cur.get("length_m") or 0.0), 2)
                if "elev_gain_m" in cur:
                    cur["elev_gain_m"] = round(float(cur["elev_gain_m"] or 0.0), 1)
                cur.pop("run_key", None)
                cur.pop("edge_i", None)
                runs.append(cur)
            cur = {k: v for k, v in feat.items() if k not in ("path",)}
            cur["length_m"] = float(feat.get("length_m") or 0.0)
            if "elev_gain_m" in feat:
                cur["elev_gain_m"] = float(feat.get("elev_gain_m") or 0.0)
            paths_buf = [feat["path"]]
        else:
            cur["length_m"] = float(cur.get("length_m") or 0.0) + float(feat.get("length_m") or 0.0)
            if "elev_gain_m" in feat:
                cur["elev_gain_m"] = float(cur.get("elev_gain_m") or 0.0) + float(
                    feat.get("elev_gain_m") or 0.0
                )
            for field in ("name", "label", "surface", "category", "description"):
                if not cur.get(field) and feat.get(field):
                    cur[field] = feat[field]
            paths_buf.append(feat["path"])
        last_i = edge_i
    if cur is not None:
        cur["path"] = _merge_path_coords(paths_buf)
        cur["length_m"] = round(float(cur.get("length_m") or 0.0), 2)
        if "elev_gain_m" in cur:
            cur["elev_gain_m"] = round(float(cur["elev_gain_m"] or 0.0), 1)
        cur.pop("run_key", None)
        cur.pop("edge_i", None)
        runs.append(cur)
    for i, r in enumerate(runs):
        r["run_id"] = f"{r.get('kind', 'x')}-{i}"
    return runs


def _attraction_label(d, kind):
    name = str(d.get("attraction_name") or "").strip()
    if name:
        # Multiple names joined with ";" — take first
        return name.split(";")[0].strip()
    if kind == "river":
        return "River"
    if kind == "park":
        return "Park"
    if kind == "sight":
        return "Attraction"
    return kind


def get_typed_green_sections(path_nodes):
    """Park / river / sight runs (park wins). Connected same-name runs merged."""
    edges = []
    for i in range(len(path_nodes) - 1):
        u, v = path_nodes[i], path_nodes[i + 1]
        d = _edge_attrs(u, v)
        kind = None
        if _is_yes_attr(d.get("is_park")):
            kind = "park"
        elif _is_yes_attr(d.get("is_river")):
            kind = "river"
        elif _is_yes_attr(d.get("is_sight")):
            kind = "sight"
        if not kind:
            continue
        name = _attraction_label(d, kind)
        edges.append({
            "edge_i": i,
            "run_key": (kind, name.lower()),
            "kind": kind,
            "name": name,
            "label": name if kind != "river" else "River",
            "path": extract_segment_geometry(u, v),
            "length_m": _edge_length_m(d),
        })
    return _collapse_edge_runs(edges)


def get_typed_cycle_sections(path_nodes):
    """
    Cycle infrastructure runs. Vehicular-free / OSM cycleway clusters win;
    TfL only when the edge has no VF infrastructure.
    """
    edges = []
    for i in range(len(path_nodes) - 1):
        u, v = path_nodes[i], path_nodes[i + 1]
        d = _edge_attrs(u, v)
        kind = None
        classified = classify_cycleway_edge(d)
        if classified:
            key = classified.get("cluster_key")
            if key in ("segregated", "bus_shared", "car_shared"):
                kind = key
        if kind is None and is_vehicular_free(d):
            kind = "segregated"
        if kind is None and _is_tfl_network(d):
            kind = "tfl"
        if not kind:
            continue
        edges.append({
            "edge_i": i,
            "run_key": kind,
            "kind": kind,
            "path": extract_segment_geometry(u, v),
            "length_m": _edge_length_m(d),
        })
    return _collapse_edge_runs(edges)


def get_typed_surface_sections(path_nodes):
    """Rough / unpaved runs, merged by surface type."""
    edges = []
    for i in range(len(path_nodes) - 1):
        u, v = path_nodes[i], path_nodes[i + 1]
        d = _edge_attrs(u, v)
        if str(d.get("type") or "").strip().lower() == "steps":
            continue
        surface = str(d.get("surface") or "").strip().lower()
        smoothness = str(d.get("smoothness") or "").strip().lower()
        if surface not in BAD_SURFACES and smoothness not in BAD_SMOOTHNESS:
            continue
        surface_label = surface if surface in BAD_SURFACES else (smoothness or "rough")
        edges.append({
            "edge_i": i,
            "run_key": ("rough", surface_label),
            "kind": "rough",
            "surface": surface_label,
            "label": surface_label.replace("_", " "),
            "path": extract_segment_geometry(u, v),
            "length_m": _edge_length_m(d),
        })
    return _collapse_edge_runs(edges)


def get_typed_hill_sections(path_nodes):
    """Connected steep runs with cumulative |elevation| change (hm)."""
    edges = []
    for i in range(len(path_nodes) - 1):
        u, v = path_nodes[i], path_nodes[i + 1]
        d = _edge_attrs(u, v)
        grade = float(d.get("grade", 0.0) or 0.0)
        if not (grade > UP_THRESH or grade < DOWN_THRESH):
            continue
        length_m = _edge_length_m(d)
        try:
            ele_u = float(G.nodes[u].get("elevation", 0.0) or 0.0)
            ele_v = float(G.nodes[v].get("elevation", 0.0) or 0.0)
            elev_gain_m = abs(ele_v - ele_u)
        except (TypeError, ValueError, KeyError):
            elev_gain_m = abs(grade) * length_m
        edges.append({
            "edge_i": i,
            "run_key": "steep",
            "kind": "steep",
            "path": extract_segment_geometry(u, v),
            "length_m": length_m,
            "elev_gain_m": elev_gain_m,
            "grade": round(grade, 4),
        })
    return _collapse_edge_runs(edges)


def get_typed_light_sections(path_nodes):
    """Connected lit / unlit runs."""
    edges = []
    for i in range(len(path_nodes) - 1):
        u, v = path_nodes[i], path_nodes[i + 1]
        d = _edge_attrs(u, v)
        kind = "lit" if is_lit(d) else "unlit"
        edges.append({
            "edge_i": i,
            "run_key": kind,
            "kind": kind,
            "path": extract_segment_geometry(u, v),
            "length_m": _edge_length_m(d),
        })
    return _collapse_edge_runs(edges)


def get_typed_disruption_sections(path_nodes):
    """Connected traffic runs — one feature (and one marker) per jam."""
    edges = []
    for i in range(len(path_nodes) - 1):
        u, v = path_nodes[i], path_nodes[i + 1]
        info = live_disruptions.get_edge_disruption(u, v)
        if not info:
            continue
        d = _edge_attrs(u, v)
        if not isinstance(info, dict):
            info = {}
        did = str(info.get("disruption_id") or "").strip()
        edges.append({
            "edge_i": i,
            "run_key": ("traffic", did or "_adj"),
            "kind": "traffic",
            "path": extract_segment_geometry(u, v),
            "length_m": _edge_length_m(d),
            "source": info.get("source") or "live",
            "severity": info.get("severity") or info.get("magnitudeOfDelay"),
            "category": info.get("category") or info.get("iconCategory") or "Disruption",
            "description": (info.get("description") or "")[:180],
            "disruption_id": did,
        })
    return _collapse_edge_runs(edges)


def build_v2_overlay_bundle(path_nodes, live_applied=False):
    """Typed overlay payload for v2 mode rail (keeps legacy keys elsewhere)."""
    return {
        "green_typed": get_typed_green_sections(path_nodes),
        "cycle_typed": get_typed_cycle_sections(path_nodes),
        "surface_typed": get_typed_surface_sections(path_nodes),
        "hill_typed": get_typed_hill_sections(path_nodes),
        "light_typed": get_typed_light_sections(path_nodes),
        "disruption_typed": get_typed_disruption_sections(path_nodes) if live_applied else [],
    }


ELEVATION_PROFILE_MAX_POINTS = 120


def build_elevation_profile(path_nodes, max_points=ELEVATION_PROFILE_MAX_POINTS):
    """
    Distance-elevation samples along the optimized path (Dynamic Island chart).
    Returns [{"d_m": metres_from_start, "elev_m": node_elevation}, ...],
    downsampled to max_points keeping first and last samples.
    """
    if not path_nodes or len(path_nodes) < 2:
        return []

    def _node_elev(n, fallback=0.0):
        try:
            return float(G.nodes[n].get("elevation", fallback) or fallback)
        except (TypeError, ValueError, KeyError):
            return fallback

    samples = [(0.0, _node_elev(path_nodes[0]))]
    dist = 0.0
    for i in range(len(path_nodes) - 1):
        u, v = path_nodes[i], path_nodes[i + 1]
        d = _edge_attrs(u, v)
        dist += _edge_length_m(d)
        samples.append((dist, _node_elev(v, samples[-1][1])))

    if len(samples) > max_points:
        step = (len(samples) - 1) / (max_points - 1)
        picked = [samples[int(round(i * step))] for i in range(max_points)]
        picked[0] = samples[0]
        picked[-1] = samples[-1]
        samples = picked

    return [{"d_m": round(d, 1), "elev_m": round(e, 1)} for d, e in samples]


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


# --- SANTANDER CYCLE HIRE (BikePoint + walk proxy) ---

@app.route('/santander/candidates', methods=['GET'])
def santander_candidates():
    """Nearest BikePoints within radius until 3 suitable (need=bikes|docks). Soft-fail 1B."""
    try:
        lat = request.args.get('lat', type=float)
        lon = request.args.get('lon', type=float)
        if lat is None or lon is None:
            return jsonify({"error": "lat and lon required"}), 400
        need = request.args.get('need', 'bikes')
        radius_m = request.args.get('radius_m', type=float)
        if radius_m is None:
            radius_m = santander_live.DEFAULT_RADIUS_M
        result = santander_live.get_candidates(lat, lon, need=need, radius_m=radius_m)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/santander/walk', methods=['POST'])
def santander_walk():
    """ORS foot-walking polyline between two points. Body: {from:[lat,lon], to:[lat,lon]}."""
    try:
        body = request.get_json(silent=True) or {}
        frm = body.get("from")
        to = body.get("to")
        if (
            not isinstance(frm, (list, tuple)) or len(frm) < 2
            or not isinstance(to, (list, tuple)) or len(to) < 2
        ):
            return jsonify({"error": "from and to must be [lat, lon]"}), 400
        result = santander_live.walk_route(
            float(frm[0]), float(frm[1]), float(to[0]), float(to[1])
        )
        return jsonify(result)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/admin/santander_status', methods=['GET'])
def admin_santander_status():
    try:
        return jsonify(santander_live.get_status())
    except Exception as e:
        return jsonify({"error": str(e), "station_count": 0}), 500


@app.route('/admin/update_santander', methods=['POST'])
def admin_update_santander():
    try:
        ok, message, count = santander_live.update_bikepoints()
        return jsonify({"ok": ok, "message": message, "count": count})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e), "count": 0}), 500


# --- OVERLAY CATALOG (main app route visualization) ---

ROUTE_OVERLAY_CATALOG = {
    "version": 1,
    "edge": [
        {"id": "lit", "label": "Lit segments", "chunk_key": "lit_chunks"},
        {"id": "steep", "label": "Steep / uphill", "chunk_key": "steep_chunks"},
        {"id": "tflCycleway", "label": "TfL infrastructure (incl. quietways)", "chunk_key": "tfl_cycleway_chunks"},
        {"id": "green", "label": "Green / scenic", "chunk_key": "green_chunks"},
        {"id": "vehicularFree", "label": "Car-free corridors", "chunk_key": "vehicular_free_chunks"},
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


@app.route('/night_status', methods=['GET'])
def night_status():
    """Whether London is dark for lighting overlay / light routing gate.

    Optional `at` / `depart_at` (ISO) evaluates darkness at that instant so
    depart-at planning can preview night routing, overlays, and charts.
    """
    raw = (request.args.get("at") or request.args.get("depart_at") or "").strip()
    at_time = parse_depart_at_arg(raw or None) if raw else None
    return jsonify({
        "is_dark": bool(night_time.is_dark(at_time)),
        "forced_mode": night_time.get_forced_mode(),
        "at": at_time.isoformat() if at_time is not None else None,
    })


@app.route('/overlay_catalog', methods=['GET'])
def get_overlay_catalog():
    """Metadata for main-app route overlay picker (display only; routing uses profile weights)."""
    return jsonify(ROUTE_OVERLAY_CATALOG)


# --- PROFILE ENDPOINTS ---

@app.route('/profiles', methods=['GET'])
def list_profiles():
    try:
        return jsonify({"profiles": g.profile_store.list_profiles(g.user_id)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/profiles/<profile_id>', methods=['GET'])
def get_profile(profile_id):
    try:
        profile = g.profile_store.get_profile(profile_id, g.user_id)
        err_resp, status = assert_profile_access(profile)
        if err_resp is not None:
            return err_resp, status
        return jsonify(profile)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Payload sanitization: only these fields are read from the client body.
# user_id comes from the verified JWT and is_system is hardcoded False in the
# store - client-sent user_id / is_system / id / slug are dropped.
ALLOWED_CREATE_FIELDS = {"name", "weights", "bike_type", "preset", "toggles"}


@app.route('/profiles', methods=['POST'])
@require_auth
def create_profile():
    try:
        raw = request.get_json(silent=True) or {}
        body = {k: v for k, v in raw.items() if k in ALLOWED_CREATE_FIELDS}
        profile, err = g.profile_store.create_profile(
            g.user_id,
            body.get("name", ""),
            body.get("weights", {}),
            bike_type=body.get("bike_type"),
            preset=body.get("preset"),
            toggles=body.get("toggles"),
        )
        if err:
            status = 401 if err == "authentication required" else 400
            return jsonify({"error": err}), status
        return jsonify(profile), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/profiles/<profile_id>', methods=['PUT'])
@require_auth
def update_profile(profile_id):
    try:
        existing = g.profile_store.get_profile(profile_id, g.user_id)
        err_resp, status = assert_profile_access(existing)
        if err_resp is not None:
            return err_resp, status
        if existing.get("is_system"):
            return jsonify({"error": "cannot edit system presets"}), 400
        raw = request.get_json(silent=True) or {}
        body = {k: v for k, v in raw.items() if k in ALLOWED_CREATE_FIELDS}
        profile, err = g.profile_store.update_profile(
            profile_id,
            g.user_id,
            body.get("name", ""),
            body.get("weights", {}),
            bike_type=body.get("bike_type"),
            preset=body.get("preset"),
            toggles=body.get("toggles"),
        )
        if err:
            status = 401 if err == "authentication required" else (
                404 if err == "profile not found" else 400
            )
            return jsonify({"error": err}), status
        return jsonify(profile), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/profiles/<profile_id>', methods=['DELETE'])
@require_auth
def delete_profile(profile_id):
    try:
        profile = g.profile_store.get_profile(profile_id, g.user_id)
        err_resp, status = assert_profile_access(profile)
        if err_resp is not None:
            return err_resp, status
        if profile.get("is_system"):
            return jsonify({"error": "cannot delete system presets"}), 400
        ok, err = g.profile_store.delete_profile(profile_id, g.user_id)
        if not ok:
            status = 401 if err == "authentication required" else 404
            return jsonify({"error": err or "profile not found"}), status
        return jsonify({"ok": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- AUTH ACCOUNT ENDPOINTS (server-side Supabase; rate-limited) ---


def _rate_limited(result):
    """Return a 429 Flask response when RateLimitResult.allowed is False."""
    if result.allowed:
        return None
    resp = jsonify({"error": result.message})
    resp.status_code = 429
    if result.retry_after_s:
        resp.headers["Retry-After"] = str(result.retry_after_s)
    return resp


def _quota_blocked(result):
    """Return a 429 when mapbox_usage.QuotaResult.allowed is False."""
    if result.allowed:
        return None
    resp = jsonify({
        "error": result.message or "Mapbox quota exceeded",
        "month": result.month,
        "used": result.used,
        "limit": result.limit,
        "remaining": result.remaining,
    })
    resp.status_code = 429
    return resp


@app.route('/auth/login', methods=['POST'])
def auth_login():
    if not auth_admin.anon_configured():
        return jsonify({"error": "auth not configured"}), 503
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip()
    password = body.get("password") or ""
    if not email or "@" not in email or not password:
        return jsonify({"error": "email and password required"}), 400
    ip = client_ip_from_request(request)
    blocked = _rate_limited(auth_rate_limit.check_login_allowed(ip, email))
    if blocked:
        return blocked
    session, err = auth_admin.sign_in(email, password)
    if err or not session:
        lock = auth_rate_limit.record_login_failure(email)
        if lock is not None and not lock.allowed:
            return _rate_limited(lock)
        # Uniform message — do not reveal whether the email exists.
        return jsonify({"error": "Invalid email or password."}), 401
    auth_rate_limit.clear_login_failures(email)
    return jsonify(session)


@app.route('/auth/signup', methods=['POST'])
def auth_signup():
    if not auth_admin.anon_configured():
        return jsonify({"error": "auth not configured"}), 503
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip()
    password = body.get("password") or ""
    display_name = body.get("display_name")
    if display_name is None:
        display_name = body.get("name")
    if not email or "@" not in email or not password:
        return jsonify({"error": "email and password required"}), 400
    ip = client_ip_from_request(request)
    blocked = _rate_limited(auth_rate_limit.check_signup_allowed(ip))
    if blocked:
        return blocked
    session, err, needs_confirm = auth_admin.sign_up(email, password, display_name)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"session": session, "needs_confirm": needs_confirm}), 201


@app.route('/auth/account', methods=['PATCH'])
@require_auth
def auth_update_account():
    """Update account profile fields (currently display_name only)."""
    if g.test_mode:
        return jsonify({"error": "account update is not available in test mode"}), 400
    if not g.user_id:
        return jsonify({"error": "authentication required"}), 401
    if not auth_admin.configured():
        return jsonify({"error": "auth not configured"}), 503
    body = request.get_json(silent=True) or {}
    if "display_name" not in body and "name" not in body:
        return jsonify({"error": "display_name required"}), 400
    display_name = body.get("display_name")
    if display_name is None:
        display_name = body.get("name")
    blocked = _rate_limited(auth_rate_limit.check_user_sensitive_allowed(g.user_id))
    if blocked:
        return blocked
    name, err = auth_admin.update_display_name(g.user_id, display_name)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"status": "updated", "display_name": name})


@app.route('/auth/password-reset', methods=['POST'])
def auth_password_reset():
    """Check email exists, then send reset mail (rate-limited)."""
    if not auth_admin.configured() or not auth_admin.anon_configured():
        return jsonify({"error": "auth not configured"}), 503
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip()
    redirect_to = (body.get("redirect_to") or "").strip()
    if not email or "@" not in email:
        return jsonify({"error": "valid email required"}), 400
    if not redirect_to:
        return jsonify({"error": "redirect_to required"}), 400
    ip = client_ip_from_request(request)
    blocked = _rate_limited(auth_rate_limit.check_reset_allowed(ip, email))
    if blocked:
        return blocked
    try:
        if not auth_admin.user_exists_by_email(email):
            return jsonify({"error": "No account found for this email address."}), 404
        err = auth_admin.send_password_reset(email, redirect_to)
        if err:
            return jsonify({"error": err}), 500
        return jsonify({"status": "sent"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/auth/refresh', methods=['POST'])
def auth_refresh():
    if not auth_admin.anon_configured():
        return jsonify({"error": "auth not configured"}), 503
    body = request.get_json(silent=True) or {}
    refresh_token = (body.get("refresh_token") or "").strip()
    if not refresh_token:
        return jsonify({"error": "refresh_token required"}), 400
    ip = client_ip_from_request(request)
    blocked = _rate_limited(auth_rate_limit.check_ip_auth_budget(ip))
    if blocked:
        return blocked
    session, err = auth_admin.refresh_session(refresh_token)
    if err or not session:
        return jsonify({"error": err or "Session refresh failed."}), 401
    return jsonify(session)


@app.route('/auth/change-password', methods=['POST'])
@require_auth
def auth_change_password():
    if g.test_mode:
        return jsonify({"error": "password change is not available in test mode"}), 400
    if not g.user_id:
        return jsonify({"error": "authentication required"}), 401
    if not auth_admin.anon_configured():
        return jsonify({"error": "auth not configured"}), 503
    body = request.get_json(silent=True) or {}
    current_password = body.get("current_password") or ""
    new_password = body.get("new_password") or ""
    confirm_password = body.get("confirm_password") or ""
    if new_password != confirm_password:
        return jsonify({"error": "New passwords do not match."}), 400
    # Resolve email from the authenticated user — never trust a body email field.
    try:
        user_resp = auth_admin._service_client().auth.admin.get_user_by_id(g.user_id)
        user_obj = getattr(user_resp, "user", None) or user_resp
        email = (auth_admin._user_email(user_obj) or "").strip()
    except Exception:
        email = ""
    if not email:
        return jsonify({"error": "Could not resolve account email."}), 400
    blocked = _rate_limited(auth_rate_limit.check_user_sensitive_allowed(g.user_id))
    if blocked:
        return blocked
    # Also count against login budget for the password re-check.
    ip = client_ip_from_request(request)
    login_block = _rate_limited(auth_rate_limit.check_login_allowed(ip, email))
    if login_block:
        return login_block
    err = auth_admin.change_password(email, current_password, new_password)
    if err:
        if err == "Current password is incorrect.":
            lock = auth_rate_limit.record_login_failure(email)
            if lock is not None and not lock.allowed:
                return _rate_limited(lock)
            return jsonify({"error": err}), 401
        return jsonify({"error": err}), 400
    auth_rate_limit.clear_login_failures(email)
    return jsonify({"status": "updated"})


@app.route('/auth/set-password', methods=['POST'])
@require_auth
def auth_set_password():
    """Set a new password using the recovery (or logged-in) access token."""
    if g.test_mode:
        return jsonify({"error": "password change is not available in test mode"}), 400
    if not g.user_id:
        return jsonify({"error": "authentication required"}), 401
    body = request.get_json(silent=True) or {}
    new_password = body.get("new_password") or ""
    confirm_password = body.get("confirm_password") or ""
    if new_password != confirm_password:
        return jsonify({"error": "Passwords do not match."}), 400
    blocked = _rate_limited(auth_rate_limit.check_user_sensitive_allowed(g.user_id))
    if blocked:
        return blocked
    token = extract_bearer_token(request)
    err = auth_admin.update_password_with_access_token(token or "", new_password)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"status": "updated"})


@app.route('/auth/check-email', methods=['POST'])
def auth_check_email():
    """Return 404 when no auth.users row exists for the email (reset pre-check)."""
    if not auth_admin.configured():
        return jsonify({"error": "auth not configured"}), 503
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip()
    if not email or "@" not in email:
        return jsonify({"error": "valid email required"}), 400
    ip = client_ip_from_request(request)
    blocked = _rate_limited(auth_rate_limit.check_ip_auth_budget(ip))
    if blocked:
        return blocked
    try:
        if not auth_admin.user_exists_by_email(email):
            return jsonify({"error": "No account found for this email address."}), 404
        return jsonify({"exists": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/auth/account', methods=['DELETE'])
@require_auth
def auth_delete_account():
    """GDPR account deletion — removes auth.users; profiles cascade."""
    if g.test_mode:
        return jsonify({"error": "account deletion is not available in test mode"}), 400
    if not g.user_id:
        return jsonify({"error": "authentication required"}), 401
    if not auth_admin.configured():
        return jsonify({"error": "auth not configured"}), 503
    blocked = _rate_limited(auth_rate_limit.check_user_sensitive_allowed(g.user_id))
    if blocked:
        return blocked
    try:
        auth_admin.delete_user(g.user_id)
        return jsonify({"status": "deleted"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- GEOCODING (Mapbox key stays server-side) ---

LONDON_BBOX = "-0.51,51.28,0.33,51.69"


@app.route('/geocode/suggest', methods=['GET'])
def geocode_suggest():
    token = (os.environ.get("MAPBOX_API_KEY") or "").strip()
    if not token:
        return jsonify({"error": "geocoding not configured"}), 503
    q = (request.args.get("q") or "").strip()
    session_token = (request.args.get("session_token") or "").strip()
    if not q or not session_token:
        return jsonify({"error": "q and session_token required"}), 400
    ip = client_ip_from_request(request)
    blocked = _rate_limited(auth_rate_limit.check_geocode_allowed(ip))
    if blocked:
        return blocked
    quota_block = _quota_blocked(mapbox_usage.check_search_session(session_token))
    if quota_block:
        return quota_block
    import urllib.parse
    import urllib.request

    params = urllib.parse.urlencode({
        "q": q,
        "session_token": session_token,
        "access_token": token,
        "limit": "5",
        "language": "en",
        "types": "address,poi,place",
        "country": "GB",
        "bbox": LONDON_BBOX,
    })
    url = f"https://api.mapbox.com/search/searchbox/v1/suggest?{params}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            import json
            data = json.loads(resp.read().decode("utf-8"))
        mapbox_usage.record_search_session(session_token)
        return jsonify({"suggestions": data.get("suggestions") or []})
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route('/geocode/retrieve/<path:mapbox_id>', methods=['GET'])
def geocode_retrieve(mapbox_id):
    token = (os.environ.get("MAPBOX_API_KEY") or "").strip()
    if not token:
        return jsonify({"error": "geocoding not configured"}), 503
    session_token = (request.args.get("session_token") or "").strip()
    if not session_token:
        return jsonify({"error": "session_token required"}), 400
    ip = client_ip_from_request(request)
    blocked = _rate_limited(auth_rate_limit.check_geocode_allowed(ip))
    if blocked:
        return blocked
    quota_block = _quota_blocked(mapbox_usage.check_search_session(session_token))
    if quota_block:
        return quota_block
    import urllib.parse
    import urllib.request
    import json

    params = urllib.parse.urlencode({
        "session_token": session_token,
        "access_token": token,
    })
    url = (
        f"https://api.mapbox.com/search/searchbox/v1/retrieve/"
        f"{urllib.parse.quote(mapbox_id, safe='')}?{params}"
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        feature = (data.get("features") or [None])[0]
        if not feature or not feature.get("geometry", {}).get("coordinates"):
            return jsonify({"error": "No coordinates in retrieve response"}), 404
        lon, lat = feature["geometry"]["coordinates"]
        props = feature.get("properties") or {}
        label = (
            props.get("full_address")
            or props.get("name")
            or props.get("place_formatted")
            or f"{lat:.4f}, {lon:.4f}"
        )
        mapbox_usage.record_search_session(session_token)
        return jsonify({"lat": lat, "lon": lon, "label": label})
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route('/weather', methods=['GET'])
def get_weather():
    """
    Open-Meteo proxy for the expanded island weather strip.
    Query: lat, lon, optional at (ISO datetime — nearest hourly UTC slot).
    """
    try:
        lat = float(request.args.get("lat"))
        lon = float(request.args.get("lon"))
    except (TypeError, ValueError):
        return jsonify({"error": "lat and lon required"}), 400
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return jsonify({"error": "lat/lon out of range"}), 400
    at = (request.args.get("at") or "").strip() or None
    try:
        payload = weather_proxy.fetch_weather(lat, lon, at)
        return jsonify(payload)
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route('/mapbox/quota', methods=['GET'])
def mapbox_quota():
    """Monthly Mapbox usage vs hard cutoffs (file-backed)."""
    return jsonify(mapbox_usage.snapshot())


@app.route('/mapbox/map_load', methods=['POST'])
def mapbox_map_load():
    """
    Reserve one GL JS map load before the client initializes Map.
    Hard-cuts when MAPBOX_MAP_LOAD_LIMIT is reached (default 45k / mo).
    """
    result = mapbox_usage.try_consume_map_load()
    blocked = _quota_blocked(result)
    if blocked:
        return blocked
    return jsonify({
        "ok": True,
        "month": result.month,
        "used": result.used,
        "limit": result.limit,
        "remaining": result.remaining,
    })


@app.route('/preset_config', methods=['GET'])
def get_preset_config():
    """Generated wizard config (see 6_verification/generate_preset_config.py)."""
    cfg = user_profiles.load_preset_config()
    if cfg is None:
        return jsonify({"error": "preset_config.json not found - run generate_preset_config.py"}), 404
    return jsonify(cfg)


# --- ROUTING ENDPOINTS ---

@app.route('/route', methods=['GET'])
def get_route():
    try:
        # purpose=commit (default) counts toward 5 Get-Route/IP/min.
        # purpose=prefetch is background UI calc and is NOT rate-limited
        # (product accepts that informed attackers could spam prefetch).
        purpose = (request.args.get("purpose") or "commit").strip().lower()
        if purpose not in ("commit", "prefetch"):
            purpose = "commit"
        if purpose == "commit":
            blocked = _rate_limited(
                auth_rate_limit.check_route_commit_allowed(client_ip_from_request(request))
            )
            if blocked:
                return blocked

        start_lat = float(request.args.get('start_lat'))
        start_lon = float(request.args.get('start_lon'))
        end_lat = float(request.args.get('end_lat'))
        end_lon = float(request.args.get('end_lon'))

        vias, via_err = route_vias.parse_vias_arg(request.args.get("vias"))
        if via_err:
            return jsonify({"error": via_err}), 400

        profile_id = (request.args.get('profile_id') or '').strip() or None
        active_profile_id = None
        bike_type = user_profiles.DEFAULT_BIKE_TYPE
        preset = None
        translation_clamps = []
        light_gated_off = False
        # Parse depart time before light gating so night simulation follows depart_at.
        depart_at_raw = (request.args.get("depart_at") or "").strip()
        at_time = parse_depart_at_arg(depart_at_raw or None)
        depart_mode = "depart_at" if depart_at_raw else "now"
        is_dark_at = bool(night_time.is_dark(at_time))

        if profile_id:
            profile = g.profile_store.get_profile(profile_id, g.user_id)
            if profile is None:
                return jsonify({"error": f"Profile not found: {profile_id}"}), 404
            if not g.test_mode and not profile.get("is_system", True) and g.user_id is None:
                return jsonify({"error": "authentication required for custom profiles"}), 401
            w = dict(profile["weights"])
            w["calming_source"] = user_profiles.CALMING_SOURCE
            active_profile_id = profile_id
            bike_type = profile["bike_type"]
            preset = profile.get("preset")
            toggles = profile["toggles"]

            w, translation_clamps = translation_layer.apply_preset_clamps(w, preset)

            # Gate lit-road preference on darkness at depart time (or now).
            if not is_dark_at:
                if w.get("light_weight", 0.0) > 0:
                    light_gated_off = True
                w["light_weight"] = 0.0

            vf_sel = toggles.get("vf_infrastructure", {})
            w["vf_shared_path"] = bool(vf_sel.get("shared_path", True))
            w["vf_bus_lane"] = bool(vf_sel.get("bus_lane", True))
            w["vf_painted_lane"] = bool(vf_sel.get("painted_lane", False))
        else:
            w = user_profiles.build_weight_dict_from_request(request.args)
            toggles = {}

        # Session bike override (does not mutate stored profile).
        bt_arg = (request.args.get('bike_type') or '').strip().lower()
        if bt_arg in user_profiles.BIKE_TYPES:
            bike_type = bt_arg

        w["bike_type"] = bike_type
        speed_kmh = user_profiles.BIKE_SPEEDS_KMH.get(bike_type, 15.0)
        vf_mask_allowed, _ = vf_allowed_masks(
            shared_path=bool(w.get("vf_shared_path", True)),
            bus_lane=bool(w.get("vf_bus_lane", True)),
            painted_lane=bool(w.get("vf_painted_lane", False)),
        )

        waypoints = [(start_lat, start_lon)] + list(vias) + [(end_lat, end_lon)]

        t_route = time.perf_counter()
        snaps = []
        for lat, lon in waypoints:
            snap = tfl_live.snap_to_edge(
                lat, lon, max_distance_m=tfl_live.SNAP_MAX_DISTANCE_M_ROUTE
            )
            if not snap:
                return jsonify({
                    "error": (
                        "Could not snap to network — "
                        "TUNE currently only supports Greater London"
                    ),
                }), 400
            snaps.append(snap)
        t_snap = time.perf_counter() - t_route

        live_applied = not is_future_depart_at(at_time)
        if not live_applied:
            w = dict(w)
            w["tfl_live_weight"] = 0.0

        unique_hours = G.graph.get("park_opening_hours_unique") or []
        hours_map, fallback_open = park_opening_hours.build_request_hours_context(unique_hours, at_time)

        tables = edge_cost_arrays.get_tables()
        shared = edge_cost_arrays.get_shared_overlays()
        if not live_applied and tables is not None:
            shared = edge_cost_arrays.build_shared_overlays(
                tables, hours_map, fallback_open, G=G, include_live=False
            )
        use_arrays = (
            edge_cost_arrays.array_costs_enabled()
            and tables is not None
            and shared is not None
        )
        csr = graph_csr.get_csr()
        cost_fast_eid = None
        cost_opt_eid = None
        if use_arrays:
            weight_fastest = edge_cost_arrays.make_array_weight_fn_fastest(
                tables, BARRIER_HARD_COST, shared, bike_type=bike_type
            )
            weight_optimized = edge_cost_arrays.make_array_weight_fn_optimized(
                tables,
                w,
                shared,
                hard_cost=BARRIER_HARD_COST,
                m_min=M_MIN,
                r_min=R_MIN,
            )
            cost_fast_eid = edge_cost_arrays.make_array_cost_by_eid_fastest(
                tables, BARRIER_HARD_COST, shared, bike_type=bike_type
            )
            cost_opt_eid = edge_cost_arrays.make_array_cost_by_eid_optimized(
                tables,
                w,
                shared,
                hard_cost=BARRIER_HARD_COST,
                m_min=M_MIN,
                r_min=R_MIN,
            )
        else:
            weight_fastest = make_weight_fastest(
                hours_map, fallback_open, apply_live=live_applied
            )
            weight_optimized = make_weight_optimized(
                w, hours_map, fallback_open, apply_live=live_applied
            )

        route_alg = (request.args.get("alg") or get_route_algorithm()).strip().lower()
        if route_alg not in ("bi", "uni"):
            route_alg = "uni"
        alg_label = "bidirectional" if route_alg == "bi" else "unidirectional"
        use_csr = (
            route_alg == "uni"
            and use_arrays
            and graph_csr.csr_astar_enabled()
            and csr is not None
            and cost_fast_eid is not None
            and cost_opt_eid is not None
        )
        use_numba = (
            use_csr
            and pathfinding_numba.numba_astar_enabled()
            and pathfinding_numba.is_available()
            and tables is not None
            and shared is not None
        )
        opt_scalars = None
        if use_numba:
            opt_scalars = pathfinding_numba.pack_optimized_scalars(
                w, shared, BARRIER_HARD_COST, M_MIN, R_MIN
            )

        eps_fast = get_route_fastest_heuristic_epsilon()
        scale_fast = 1.0 * (1.0 + eps_fast)
        eps = get_route_heuristic_epsilon()
        scale = compute_optimized_cost_per_metre_lower_bound(w) * (1.0 + eps)

        legs_out = []
        leg_timings = []
        t_fast_total = 0.0
        t_opt_total = 0.0
        exp_fast_total = 0
        exp_opt_total = 0
        relax_fast_total = 0
        relax_opt_total = 0

        for leg_i in range(len(snaps) - 1):
            start_snap = snaps[leg_i]
            end_snap = snaps[leg_i + 1]
            start_node = start_snap.anchor_node
            end_node = end_snap.anchor_node

            h_fast_fwd = make_heuristic(end_node, G, cost_per_m=scale_fast, csr=csr)
            h_fast_bwd = make_backward_heuristic(start_node, G, cost_per_m=scale_fast, csr=csr)
            t0 = time.perf_counter()
            path_fastest, stats_fast = pathfinding.run_astar(
                G,
                start_node,
                end_node,
                algorithm=route_alg,
                heuristic_fwd=h_fast_fwd,
                heuristic_bwd=h_fast_bwd,
                weight_fn=weight_fastest,
                csr=csr if use_csr else None,
                cost_by_eid=cost_fast_eid if use_csr else None,
                cost_per_m=scale_fast if use_csr else None,
                numba_kwargs=(
                    {
                        "csr": csr,
                        "source": start_node,
                        "target": end_node,
                        "tables": tables,
                        "shared": shared,
                        "mode": "fastest",
                        "cost_per_m": scale_fast,
                        "hard_cost": BARRIER_HARD_COST,
                        "bike_type": bike_type,
                    }
                    if use_numba
                    else None
                ),
            )
            t_fast = time.perf_counter() - t0
            coords_fastest = apply_endpoint_stubs(
                reconstruct_path_geometry(path_fastest), start_snap, end_snap
            )
            stats_fastest = calculate_path_stats(
                path_fastest, speed_kmh=speed_kmh, vf_mask_allowed=vf_mask_allowed
            )

            h_opt_fwd = make_heuristic(end_node, G, cost_per_m=scale, csr=csr)
            h_opt_bwd = make_backward_heuristic(start_node, G, cost_per_m=scale, csr=csr)
            t0 = time.perf_counter()
            path_optimized, stats_opt = pathfinding.run_astar(
                G,
                start_node,
                end_node,
                algorithm=route_alg,
                heuristic_fwd=h_opt_fwd,
                heuristic_bwd=h_opt_bwd,
                weight_fn=weight_optimized,
                csr=csr if use_csr else None,
                cost_by_eid=cost_opt_eid if use_csr else None,
                cost_per_m=scale if use_csr else None,
                numba_kwargs=(
                    {
                        "csr": csr,
                        "source": start_node,
                        "target": end_node,
                        "tables": tables,
                        "shared": shared,
                        "mode": "optimized",
                        "cost_per_m": scale,
                        "hard_cost": BARRIER_HARD_COST,
                        "bike_type": bike_type,
                        "opt_scalars": opt_scalars,
                    }
                    if use_numba
                    else None
                ),
            )
            t_opt = time.perf_counter() - t0
            coords_optimized = apply_endpoint_stubs(
                reconstruct_path_geometry(path_optimized), start_snap, end_snap
            )
            stats_optimized = calculate_path_stats(
                path_optimized,
                calming_source=user_profiles.CALMING_SOURCE,
                speed_kmh=speed_kmh,
                vf_mask_allowed=vf_mask_allowed,
                duration_speed_multiplier=duration_speed_multiplier_for_preset(preset),
            )

            lit_chunks = get_lit_sections(path_optimized)
            steep_chunks = get_steep_sections(path_optimized)
            tfl_cycleway_chunks = get_tfl_cycleway_sections(path_optimized)
            green_chunks = get_green_sections(path_optimized)
            vehicular_free_chunks = get_vehicular_free_sections(path_optimized, vf_mask_allowed)
            disruption_chunks = (
                get_disruption_sections(path_optimized) if live_applied else []
            )
            node_highlights = get_node_highlights(path_optimized, w, overlay_mode=True)
            overlay_typed = build_v2_overlay_bundle(path_optimized, live_applied=live_applied)
            elevation_profile = build_elevation_profile(path_optimized)

            t_fast_total += t_fast
            t_opt_total += t_opt
            exp_fast_total += stats_fast["expansions"]
            exp_opt_total += stats_opt["expansions"]
            relax_fast_total += stats_fast["edge_relaxations"]
            relax_opt_total += stats_opt["edge_relaxations"]
            leg_timings.append({
                "index": leg_i,
                "fastest_astar": round(t_fast * 1000, 1),
                "optimized_astar": round(t_opt * 1000, 1),
            })
            legs_out.append({
                "index": leg_i,
                "from": _snap_meta(start_snap),
                "to": _snap_meta(end_snap),
                "fastest": {"path": coords_fastest, "stats": stats_fastest},
                "safest": {
                    "path": coords_optimized,
                    "stats": stats_optimized,
                    "lit_chunks": lit_chunks,
                    "steep_chunks": steep_chunks,
                    "tfl_cycleway_chunks": tfl_cycleway_chunks,
                    "green_chunks": green_chunks,
                    "vehicular_free_chunks": vehicular_free_chunks,
                    "disruption_chunks": disruption_chunks,
                    "node_highlights": node_highlights,
                    "elevation_profile": elevation_profile,
                    **overlay_typed,
                },
            })

        t_compute = t_snap + t_fast_total + t_opt_total
        if os.environ.get("ROUTE_BENCHMARK", "").lower() in ("1", "true", "yes"):
            _imp = None
            if use_arrays and shared is not None:
                _imp = int(shared.impassable.sum())
            print(
                f"ROUTE_BENCHMARK alg={route_alg} array_costs={use_arrays} "
                f"csr={use_csr} numba={use_numba} legs={len(legs_out)} "
                f"snap={t_snap*1000:.1f}ms "
                f"fastest={t_fast_total*1000:.1f}ms(exp={exp_fast_total}) "
                f"optimized={t_opt_total*1000:.1f}ms(exp={exp_opt_total}) "
                f"scale={scale:.3f} eps={eps} eps_fast={eps_fast} "
                f"light_gated={light_gated_off} purpose={purpose} "
                f"impassable={_imp} live={bool(shared and getattr(shared, 'has_live', False)) if use_arrays else 'n/a'}"
            )

        coords_fastest_all = route_vias.concatenate_paths(
            [leg["fastest"]["path"] for leg in legs_out]
        )
        coords_opt_all = route_vias.concatenate_paths(
            [leg["safest"]["path"] for leg in legs_out]
        )
        stats_fastest_all = route_vias.aggregate_path_stats(
            [leg["fastest"]["stats"] for leg in legs_out]
        )
        stats_optimized_all = route_vias.aggregate_path_stats(
            [leg["safest"]["stats"] for leg in legs_out]
        )

        def _merge_chunks(key):
            out = []
            for leg in legs_out:
                out.extend(leg["safest"].get(key) or [])
            return out

        def _merge_elevation_profiles():
            """Concatenate per-leg profiles, offsetting distances by prior legs."""
            out = []
            offset = 0.0
            for leg in legs_out:
                prof = leg["safest"].get("elevation_profile") or []
                for i, p in enumerate(prof):
                    if out and i == 0:
                        continue  # joint point duplicates previous leg end
                    out.append({
                        "d_m": round(p["d_m"] + offset, 1),
                        "elev_m": p["elev_m"],
                    })
                if prof:
                    offset += prof[-1]["d_m"]
            return out

        return jsonify({
            "status": "success",
            "meta": {
                "cost_per_m_lower_bound": round(scale, 4),
                "heuristic_epsilon": eps,
                "fastest_heuristic_epsilon": eps_fast,
                "fastest_cost_per_m": round(scale_fast, 4),
                "algorithm": alg_label,
                "auth": {"mode": g.auth_mode, "user_id": g.user_id},
                "active_profile_id": active_profile_id,
                "weights": {k: w[k] for k in user_profiles.ROUTING_WEIGHT_KEYS},
                "calming_source": user_profiles.CALMING_SOURCE,
                "bike_type": bike_type,
                "preset": preset,
                "speed_kmh": speed_kmh,
                "translation_clamps": translation_clamps,
                "light_gated_off": light_gated_off,
                "is_dark": is_dark_at,
                "leg_count": len(legs_out),
                "purpose": purpose,
                "timing_ms": {
                    "snap": round(t_snap * 1000, 1),
                    "fastest_astar": round(t_fast_total * 1000, 1),
                    "optimized_astar": round(t_opt_total * 1000, 1),
                    "total": round(t_compute * 1000, 1),
                    "legs": leg_timings,
                },
                "search_stats": {
                    "fastest_expansions": exp_fast_total,
                    "fastest_edge_relaxations": relax_fast_total,
                    "optimized_expansions": exp_opt_total,
                    "optimized_edge_relaxations": relax_opt_total,
                },
                "snap": {
                    "start": _snap_meta(snaps[0]),
                    "end": _snap_meta(snaps[-1]),
                    "vias": [_snap_meta(s) for s in snaps[1:-1]],
                },
                "park_hours_at": at_time.isoformat(),
                "park_fallback_open": fallback_open,
                "park_hours_map_size": len(hours_map),
                "depart_mode": depart_mode,
                "live_applied": live_applied,
                "array_costs": use_arrays,
                "csr_astar": use_csr,
                "numba_astar": use_numba,
                "geom_preparse": edge_cost_arrays.get_geom_preparse_state(),
            },
            "legs": legs_out,
            "fastest": {"path": coords_fastest_all, "stats": stats_fastest_all},
            "safest": {
                "path": coords_opt_all,
                "stats": stats_optimized_all,
                "lit_chunks": _merge_chunks("lit_chunks"),
                "steep_chunks": _merge_chunks("steep_chunks"),
                "tfl_cycleway_chunks": _merge_chunks("tfl_cycleway_chunks"),
                "green_chunks": _merge_chunks("green_chunks"),
                "vehicular_free_chunks": _merge_chunks("vehicular_free_chunks"),
                "disruption_chunks": _merge_chunks("disruption_chunks"),
                "node_highlights": _merge_chunks("node_highlights"),
                "elevation_profile": _merge_elevation_profiles(),
                "green_typed": _merge_chunks("green_typed"),
                "cycle_typed": _merge_chunks("cycle_typed"),
                "surface_typed": _merge_chunks("surface_typed"),
                "hill_typed": _merge_chunks("hill_typed"),
                "light_typed": _merge_chunks("light_typed"),
                "disruption_typed": _merge_chunks("disruption_typed"),
            },
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="Tuned Cycling routing backend")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--day", action="store_true",
                            help="Force day mode (light_weight always gated off)")
    mode_group.add_argument("--night", action="store_true",
                            help="Force night mode (light_weight always active)")
    parser.add_argument(
        "--no-live",
        action="store_true",
        help="Skip TfL/TomTom fetch+poll (same as SKIP_DISRUPTION_FETCH=1 or LIVE_DISRUPTIONS=0)",
    )
    parser.add_argument(
        "--weather-test",
        action="store_true",
        help="Synthetic extreme weather on /weather — random scenario rotates every UTC minute",
    )
    parser.add_argument(
        "--mobile",
        action="store_true",
        help="Bind to 0.0.0.0 so phones on the LAN can reach the API (default is localhost only)",
    )
    args = parser.parse_args()

    if args.day:
        night_time.set_forced_mode("day")
    elif args.night:
        night_time.set_forced_mode("night")
    # --no-live applied in _apply_early_cli_env() before bootstrap

    if args.weather_test or weather_proxy.is_test_mode():
        print(
            "WEATHER TEST MODE: /weather returns synthetic extremes "
            "(random scenario each UTC minute — expand island to preview)"
        )

    bind_host = "0.0.0.0" if args.mobile else "127.0.0.1"
    if args.mobile:
        print(
            "MOBILE DEBUG: listening on 0.0.0.0:5000 — "
            "pair with npm start -- --v2 --mobile and open http://<PC_LAN_IP>:3000"
        )

    app.run(debug=True, host=bind_host, port=5000, use_reloader=USE_RELOADER)