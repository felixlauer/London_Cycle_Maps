"""
Build directed routing graph from PostgreSQL (planet_osm_line + planet_osm_point).
Output: 1_data/london.graphml (+ graph_debug_report.txt).
Barrier, give_way, and stop_sign are snapped to EDGES (with original position stored).
Traffic_signals, mini_roundabout, crossing remain on NODES.

When changing parsed tags, build rules, or pipeline steps, update:
  0_documentation/GRAPH.md
"""
import networkx as nx
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime
from scipy.spatial import cKDTree
import numpy as np
import os
from shapely.wkt import loads as wkt_loads
from shapely.geometry import Point, LineString
from shapely.strtree import STRtree

# Load DB credentials from backend .env (gitignored) so it works locally
try:
    from dotenv import load_dotenv
    _env = os.path.join(os.path.dirname(__file__), "..", "4_backend_engine", ".env")
    load_dotenv(_env)
except ImportError:
    pass

# --- CONFIGURATION (set DB_PASS etc. via env or .env; do not commit secrets) ---
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASS = os.environ.get("DB_PASS", "")
DB_NAME = os.environ.get("DB_NAME", "london_routing")
DB_HOST = os.environ.get("DB_HOST", "localhost")
OUTPUT_PATH = os.path.join("..", "1_data", "london.graphml")
REPORT_PATH = os.path.join("..", "1_data", "graph_debug_report.txt")

# Snap threshold for matching point features to graph nodes (degrees ~20m at London latitude)
SNAP_THRESHOLD = 0.0002
# Stricter threshold for give_way/stop so sign hits the correct road only
SNAP_THRESHOLD_SIGN = 0.00015
# Kerb: only snap to these highway types (pedestrian ways)
PEDESTRIAN_HIGHWAY_TYPES = frozenset(['footway', 'pedestrian', 'path', 'steps'])
# Straight segment: length/straight_line_distance <= this
STRAIGHT_RATIO_MAX = 1.05
# Orthogonal distance (m) above which barrier_confidence = 0
BARRIER_ORTHOGONAL_THRESHOLD_M = 4.0
# Approx metres per degree at London (~51.5°): 111e3 for rough conversion
DEG_TO_M = 111000.0
# Traffic calming points: same snap threshold as barrier
SNAP_THRESHOLD_TC_POINT = 0.0002
# Highway types where cars are not allowed (for calming: prefer car-allowed edges)
HIGHWAY_TYPES_NO_CARS = frozenset([
    'footway', 'cycleway', 'path', 'pedestrian', 'steps', 'bridleway', 'corridor',
    'proposed', 'construction', 'cycleway:left', 'cycleway:right', 'cycleway:both',
])

def main():
    print("--- BUILDING DIRECTED ROUTING GRAPH (ENHANCED) ---")

    db_url = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:5432/{DB_NAME}"
    engine = create_engine(db_url)

    # =====================================================================
    # STEP 1: FETCH ROAD NETWORK (planet_osm_line)
    # =====================================================================
    print("1. Fetching road network with all tags...")

    sql_lines = """
    SELECT
        osm_id, name,
        COALESCE(accident_count, 0) as accident_count,
        highway as fclass,
        surface, oneway, bicycle, bridge, tunnel, junction, width,

        -- Already parsed (keep)
        tags->'maxspeed'            as maxspeed,
        tags->'lit'                 as lit,
        tags->'oneway:bicycle'      as oneway_bicycle,
        tags->'cycleway'            as cycleway,

        -- 1. Strategic Cycling Networks
        tags->'lcn_ref'             as lcn_ref,
        tags->'rcn_ref'             as rcn_ref,
        tags->'ncn_ref'             as ncn_ref,
        tags->'cycle_network'       as cycle_network,

        -- 2A. Side-Specific Cycleway Tags
        tags->'cycleway:left'       as cycleway_left,
        tags->'cycleway:right'      as cycleway_right,
        tags->'cycleway:both'       as cycleway_both,

        -- 2B. Protection & Separation
        tags->'segregated'          as segregated,
        tags->'cycleway:separation'             as cycleway_separation,
        tags->'cycleway:left:separation'        as cycleway_left_separation,
        tags->'cycleway:right:separation'       as cycleway_right_separation,
        tags->'cycleway:buffer'                 as cycleway_buffer,

        -- 2C. Quality & Geometry
        tags->'cycleway:width'      as cycleway_width,
        tags->'cycleway:surface'    as cycleway_surface,
        tags->'smoothness'          as smoothness,
        tags->'cycleway:smoothness' as cycleway_smoothness,

        -- 3. Traffic & Road Stress
        tags->'hgv'                 as hgv,
        tags->'traffic_calming'     as traffic_calming,

        -- Geometry
        ST_Length(ST_Transform(way, 4326)::geography) as length_meters,
        ST_AsText(ST_Transform(way, 4326)) as wkt,
        ST_X(ST_StartPoint(ST_Transform(way, 4326))) as u_x,
        ST_Y(ST_StartPoint(ST_Transform(way, 4326))) as u_y,
        ST_X(ST_EndPoint(ST_Transform(way, 4326)))   as v_x,
        ST_Y(ST_EndPoint(ST_Transform(way, 4326)))   as v_y
    FROM planet_osm_line
    WHERE highway IS NOT NULL;
    """

    df = pd.read_sql(sql_lines, engine)

    # All text columns that need empty-string fill
    text_cols = [
        'surface', 'oneway', 'bicycle', 'bridge', 'tunnel', 'maxspeed', 'lit',
        'oneway_bicycle', 'cycleway', 'width', 'junction',
        # New: networks
        'lcn_ref', 'rcn_ref', 'ncn_ref', 'cycle_network',
        # New: cycleway infra
        'cycleway_left', 'cycleway_right', 'cycleway_both',
        'segregated', 'cycleway_separation', 'cycleway_left_separation',
        'cycleway_right_separation', 'cycleway_buffer',
        'cycleway_width', 'cycleway_surface', 'smoothness', 'cycleway_smoothness',
        # New: traffic
        'hgv', 'traffic_calming',
    ]
    df[text_cols] = df[text_cols].fillna('')

    print(f"   -> Loaded {len(df)} raw segments from planet_osm_line.")

    # =====================================================================
    # STEP 2: BUILD DIRECTED GRAPH
    # =====================================================================
    print("2. Building directed graph with direction rules...")

    G = nx.DiGraph()

    count_motorway_banned = 0
    count_oneway = 0
    count_contraflow = 0

    for index, row in df.iterrows():
        # 1. MOTORWAY & LEGALITY CHECK
        highway = str(row['fclass']).lower()
        bicycle_access = str(row['bicycle']).lower()

        if bicycle_access == 'no':
            continue

        if 'motorway' in highway and bicycle_access not in ['yes', 'designated', 'permissive']:
            count_motorway_banned += 1
            continue

        # 2. PREPARE GEOMETRY
        u = (round(row['u_x'], 6), round(row['u_y'], 6))
        v = (round(row['v_x'], 6), round(row['v_y'], 6))

        # 3. ALL ATTRIBUTES
        attrs = {
            'osm_id':       str(row['osm_id']),
            'name':         str(row['name']),
            'length':       float(row['length_meters']),
            'risk':         float(row['accident_count']),
            'type':         highway,
            'geometry':     str(row['wkt']),
            # Physical
            'surface':      str(row['surface']),
            'lit':          str(row['lit']),
            'maxspeed':     str(row['maxspeed']),
            'width':        str(row['width']),
            'bridge':       str(row['bridge']),
            'tunnel':       str(row['tunnel']),
            'junction':     str(row['junction']),
            'smoothness':   str(row['smoothness']),
            # Cycling infrastructure
            'cycleway':             str(row['cycleway']),
            'cycleway_left':        str(row['cycleway_left']),
            'cycleway_right':       str(row['cycleway_right']),
            'cycleway_both':        str(row['cycleway_both']),
            'segregated':           str(row['segregated']),
            'cycleway_separation':          str(row['cycleway_separation']),
            'cycleway_left_separation':     str(row['cycleway_left_separation']),
            'cycleway_right_separation':    str(row['cycleway_right_separation']),
            'cycleway_buffer':      str(row['cycleway_buffer']),
            'cycleway_width':       str(row['cycleway_width']),
            'cycleway_surface':     str(row['cycleway_surface']),
            'cycleway_smoothness':  str(row['cycleway_smoothness']),
            # Strategic networks
            'lcn_ref':          str(row['lcn_ref']),
            'rcn_ref':          str(row['rcn_ref']),
            'ncn_ref':          str(row['ncn_ref']),
            'cycle_network':    str(row['cycle_network']),
            # Traffic stress
            'hgv':              str(row['hgv']),
            'traffic_calming':  str(row['traffic_calming']),
        }

        # 4. DIRECTION LOGIC (unchanged)
        oneway_tag = str(row['oneway']).lower()
        oneway_bike = str(row['oneway_bicycle']).lower()

        is_oneway_car = oneway_tag in ['yes', 'true', '1']
        is_reverse_car = oneway_tag in ['-1', 'reverse']
        has_contraflow = oneway_bike in ['no', 'false', '0']

        if not is_reverse_car or (is_reverse_car and has_contraflow):
            G.add_edge(u, v, **attrs)
            G.nodes[u]['x'], G.nodes[u]['y'] = u[0], u[1]
            G.nodes[v]['x'], G.nodes[v]['y'] = v[0], v[1]

        if not is_oneway_car or (is_oneway_car and has_contraflow):
            G.add_edge(v, u, **attrs)
            G.nodes[u]['x'], G.nodes[u]['y'] = u[0], u[1]
            G.nodes[v]['x'], G.nodes[v]['y'] = v[0], v[1]
            if is_oneway_car and has_contraflow:
                count_contraflow += 1

        if is_oneway_car or is_reverse_car:
            count_oneway += 1

    print(f"   -> Banned {count_motorway_banned} motorway segments.")
    print(f"   -> Processed {count_oneway} one-way streets.")
    print(f"   -> Enabled {count_contraflow} contraflow cycling exceptions.")
    print(f"   -> Graph before cleanup: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    # =====================================================================
    # STEP 3: CLEAN ISLANDS
    # =====================================================================
    print("3. Cleaning disconnected 'Islands'...")
    nodes_before = G.number_of_nodes()
    if G.number_of_nodes() > 0:
        largest = max(nx.weakly_connected_components(G), key=len)
        G = G.subgraph(largest).copy()
    nodes_removed = nodes_before - G.number_of_nodes()
    print(f"   -> Removed {nodes_removed} island nodes. Kept {G.number_of_nodes()} nodes, {G.number_of_edges()} edges.")

    # =====================================================================
    # STEP 4: FETCH & SNAP INTERSECTION DATA (planet_osm_point)
    # =====================================================================
    print("4. Fetching intersection data from planet_osm_point...")

    sql_points = """
    SELECT
        osm_id,
        highway,
        barrier,
        tags->'crossing' as crossing,
        ST_X(ST_Transform(way, 4326)) as lon,
        ST_Y(ST_Transform(way, 4326)) as lat
    FROM planet_osm_point
    WHERE
        highway IN ('traffic_signals', 'mini_roundabout', 'crossing', 'give_way', 'stop')
        OR barrier IS NOT NULL;
    """

    df_points = pd.read_sql(sql_points, engine)
    point_text_cols = ['highway', 'barrier', 'crossing']
    df_points[point_text_cols] = df_points[point_text_cols].fillna('')

    print(f"   -> Loaded {len(df_points)} point features.")

    # Build spatial index (KD-tree) of graph nodes for O(log N) nearest-neighbor per point
    node_list = []
    for node_id, data in G.nodes(data=True):
        if 'x' in data and 'y' in data:
            node_list.append((node_id, float(data['x']), float(data['y'])))

    n_nodes = len(node_list)
    if n_nodes == 0:
        print("   -> No graph nodes with coordinates; skipping point snap.")
        snap_count, snap_miss = 0, len(df_points)
    else:
        coords = np.array([[n[1], n[2]] for n in node_list], dtype=np.float64)
        tree = cKDTree(coords)

        # Query all points at once (vectorized)
        points_arr = np.column_stack([df_points['lon'].astype(np.float64), df_points['lat'].astype(np.float64)])
        distances, indices = tree.query(points_arr, k=1, distance_upper_bound=SNAP_THRESHOLD)

        # Handle single-point query (scipy returns scalar instead of array)
        if np.isscalar(indices):
            indices = np.array([indices])
            distances = np.array([distances])

        snap_count = 0
        snap_miss = 0

        for i in range(len(df_points)):
            if indices[i] >= n_nodes or np.isinf(distances[i]):
                snap_miss += 1
                continue

            pt = df_points.iloc[i]
            hw = str(pt['highway']).lower()
            crossing = str(pt['crossing']).lower()
            # Only snap traffic_signals, mini_roundabout, crossing to NODES (barrier, give_way, stop go to edges)
            if hw not in ('traffic_signals', 'mini_roundabout', 'crossing'):
                continue

            best_node = node_list[indices[i]][0]
            node_data = G.nodes[best_node]

            if hw == 'traffic_signals':
                node_data['traffic_signals'] = 'yes'
            elif hw == 'mini_roundabout':
                node_data['mini_roundabout'] = 'yes'
            elif hw == 'crossing':
                node_data['crossing'] = 'yes'
                if crossing:
                    node_data['crossing_type'] = crossing

            snap_count += 1

        print(f"   -> Snapped {snap_count} point features (signals/crossing/mini_roundabout) to graph nodes.")
    print(f"   -> Missed {snap_miss} features (no node within {SNAP_THRESHOLD} deg).")

    # =====================================================================
    # STEP 4b: SNAP BARRIER / GIVE_WAY / STOP TO EDGES (store original position)
    # =====================================================================
    print("4b. Snapping barrier, give_way, stop to edges...")

    edge_list = []  # (u, v, LineString)
    for u, v, data in G.edges(data=True):
        wkt = data.get('geometry')
        if not wkt or not wkt.strip():
            continue
        try:
            line = wkt_loads(wkt)
            if line is None or line.is_empty:
                continue
            if hasattr(line, 'coords'):
                coords = list(line.coords)
            else:
                coords = [(line.x, line.y)]
            if len(coords) < 2:
                continue
            # WKT from PostGIS is (lon lat) = (x y) in Shapely
            ls = LineString(coords)
            edge_list.append((u, v, ls))
        except Exception:
            continue

    barrier_snap = 0
    kerb_snap = 0
    kerb_no_pedestrian_way = 0
    confidence_band_0 = 0
    confidence_band_low = 0
    confidence_band_mid = 0
    confidence_band_1 = 0
    give_way_snap = 0
    stop_snap = 0

    def _is_pedestrian_edge(idx):
        u, v, _ = edge_list[idx]
        t = str(G.edges[u, v].get('type', '')).strip().lower()
        return t in PEDESTRIAN_HIGHWAY_TYPES

    def _barrier_confidence(pt, line, threshold_m):
        """Return 0-1 confidence: curved -> 0.5; straight -> 1 - (d_orth_m / threshold_m) clamped."""
        coords = list(line.coords)
        if len(coords) < 2:
            return 0.5
        start, end = coords[0], coords[-1]
        d_straight = Point(start).distance(Point(end))
        length_deg = line.length
        if d_straight < 1e-12:
            return 0.5
        ratio = length_deg / d_straight
        if ratio > STRAIGHT_RATIO_MAX:
            return 0.5
        d_orth_deg = pt.distance(line)
        d_orth_m = d_orth_deg * DEG_TO_M
        if d_orth_m >= threshold_m:
            return 0.0
        return max(0.0, 1.0 - d_orth_m / threshold_m)

    if edge_list:
        geoms = [item[2] for item in edge_list]
        strtree = STRtree(geoms)

        df_barrier = df_points[df_points['barrier'].notna() & (df_points['barrier'].astype(str).str.strip() != '')]
        df_kerb = df_barrier[df_barrier['barrier'].astype(str).str.strip().str.lower() == 'kerb']
        df_other_barrier = df_barrier[df_barrier['barrier'].astype(str).str.strip().str.lower() != 'kerb']

        # --- Kerb: only snap to pedestrian ways; skip if no pedestrian edge within threshold ---
        for i, row in df_kerb.iterrows():
            lon, lat = float(row['lon']), float(row['lat'])
            pt = Point(lon, lat)
            buf = pt.buffer(SNAP_THRESHOLD)
            candidates = strtree.query(buf)
            if len(candidates) == 0:
                kerb_no_pedestrian_way += 1
                continue
            pedestrian_idx = [idx for idx in candidates if _is_pedestrian_edge(idx)]
            best_dist = float('inf')
            best_idx = None
            for idx in pedestrian_idx:
                u, v, line = edge_list[idx]
                d = pt.distance(line)
                if d < best_dist and d <= SNAP_THRESHOLD:
                    best_dist = d
                    best_idx = idx
            if best_idx is None:
                kerb_no_pedestrian_way += 1
                continue
            u, v, _ = edge_list[best_idx]
            G.edges[u, v]['barrier'] = 'kerb'
            G.edges[u, v]['barrier_lon'] = lon
            G.edges[u, v]['barrier_lat'] = lat
            G.edges[u, v]['barrier_confidence'] = 1.0
            if G.has_edge(v, u):
                G.edges[v, u]['barrier'] = 'kerb'
                G.edges[v, u]['barrier_lon'] = lon
                G.edges[v, u]['barrier_lat'] = lat
                G.edges[v, u]['barrier_confidence'] = 1.0
            kerb_snap += 1

        # --- Other barriers: snap to nearest edge, set barrier_confidence from orthogonal distance ---
        for i, row in df_other_barrier.iterrows():
            lon, lat = float(row['lon']), float(row['lat'])
            pt = Point(lon, lat)
            buf = pt.buffer(SNAP_THRESHOLD)
            candidates = strtree.query(buf)
            if len(candidates) == 0:
                continue
            best_dist = float('inf')
            best_idx = None
            for idx in candidates:
                u, v, line = edge_list[idx]
                d = pt.distance(line)
                if d < best_dist and d <= SNAP_THRESHOLD:
                    best_dist = d
                    best_idx = idx
            if best_idx is None:
                continue
            u, v, line = edge_list[best_idx]
            conf = _barrier_confidence(pt, line, BARRIER_ORTHOGONAL_THRESHOLD_M)
            if conf <= 0:
                confidence_band_0 += 1
            elif conf < 0.5:
                confidence_band_low += 1
            elif conf < 1.0:
                confidence_band_mid += 1
            else:
                confidence_band_1 += 1
            barrier_type = str(row['barrier']).strip().lower()
            G.edges[u, v]['barrier'] = barrier_type
            G.edges[u, v]['barrier_lon'] = lon
            G.edges[u, v]['barrier_lat'] = lat
            G.edges[u, v]['barrier_confidence'] = conf
            if G.has_edge(v, u):
                G.edges[v, u]['barrier'] = barrier_type
                G.edges[v, u]['barrier_lon'] = lon
                G.edges[v, u]['barrier_lat'] = lat
                G.edges[v, u]['barrier_confidence'] = conf
            barrier_snap += 1

        # --- Give way & Stop: snap to nearest edge, only tag edge that ENDS at the sign (direction rule) ---
        def _snap_sign_to_edge(df_sign, sign_key, sign_lon_key, sign_lat_key, thresh):
            count = 0
            for i, row in df_sign.iterrows():
                lon, lat = float(row['lon']), float(row['lat'])
                pt = Point(lon, lat)
                buf = pt.buffer(thresh)
                candidates = strtree.query(buf)
                if len(candidates) == 0:
                    continue
                best_dist = float('inf')
                best_idx = None
                for idx in candidates:
                    u, v, line = edge_list[idx]
                    d = pt.distance(line)
                    if d < best_dist and d <= thresh:
                        best_dist = d
                        best_idx = idx
                if best_idx is None:
                    continue
                u, v, line = edge_list[best_idx]
                # Project point onto line; if project param > 0.5 then sign is near v (tag (u,v)); else near u (tag (v,u))
                try:
                    proj = line.project(pt, normalized=True)
                except Exception:
                    proj = 0.5
                if proj > 0.5:
                    # sign at end v -> tag edge (u,v)
                    edge_u, edge_v = u, v
                else:
                    # sign at end u -> tag edge that ends at u, i.e. (v,u)
                    edge_u, edge_v = v, u
                if not G.has_edge(edge_u, edge_v):
                    continue
                G.edges[edge_u, edge_v][sign_key] = 'yes'
                G.edges[edge_u, edge_v][sign_lon_key] = lon
                G.edges[edge_u, edge_v][sign_lat_key] = lat
                count += 1
            return count

        df_gw = df_points[df_points['highway'].astype(str).str.lower() == 'give_way']
        df_stop = df_points[df_points['highway'].astype(str).str.lower() == 'stop']
        give_way_snap = _snap_sign_to_edge(df_gw, 'give_way', 'give_way_lon', 'give_way_lat', SNAP_THRESHOLD_SIGN)
        stop_snap = _snap_sign_to_edge(df_stop, 'stop_sign', 'stop_sign_lon', 'stop_sign_lat', SNAP_THRESHOLD_SIGN)

    print(f"   -> Barrier: non-kerb snapped: {barrier_snap}; kerb snapped to pedestrian: {kerb_snap}; kerb no pedestrian way: {kerb_no_pedestrian_way}.")
    print(f"   -> Barrier confidence bands: 0: {confidence_band_0}, (0,0.5): {confidence_band_low}, [0.5,1): {confidence_band_mid}, 1: {confidence_band_1}.")
    print(f"   -> give_way: {give_way_snap}; stop: {stop_snap}.")

    # =====================================================================
    # STEP 4c: SNAP TRAFFIC_CALMING (POINTS) TO EDGES (separate columns; prefer car-allowed)
    # =====================================================================
    tc_point_snap = 0
    tc_point_car_allowed = 0
    tc_point_fallback = 0
    df_tc_points = pd.DataFrame()
    sql_tc_points = """
    SELECT
        osm_id,
        ST_X(ST_Transform(way, 4326)) AS lon,
        ST_Y(ST_Transform(way, 4326)) AS lat,
        TRIM(BOTH FROM (tags->'traffic_calming')) AS traffic_calming
    FROM planet_osm_point
    WHERE tags->'traffic_calming' IS NOT NULL
      AND TRIM(BOTH FROM (tags->'traffic_calming')) != '';
    """
    try:
        df_tc_points = pd.read_sql(sql_tc_points, engine)
    except Exception as e:
        print(f"   (Traffic calming points query failed: {e})")
    if not df_tc_points.empty and edge_list:
        print("4c. Snapping traffic_calming (points) to edges...")
        geoms = [item[2] for item in edge_list]
        strtree_tc = STRtree(geoms)

        def _is_car_allowed_edge(idx):
            u, v, _ = edge_list[idx]
            t = str(G.edges[u, v].get('type', '')).strip().lower()
            return t not in HIGHWAY_TYPES_NO_CARS

        for i, row in df_tc_points.iterrows():
            lon, lat = float(row['lon']), float(row['lat'])
            pt = Point(lon, lat)
            buf = pt.buffer(SNAP_THRESHOLD_TC_POINT)
            candidates = strtree_tc.query(buf)
            if len(candidates) == 0:
                continue
            car_allowed_idx = [idx for idx in candidates if _is_car_allowed_edge(idx)]
            search_idx = car_allowed_idx if car_allowed_idx else list(candidates)
            best_dist = float('inf')
            best_idx = None
            for idx in search_idx:
                u, v, line = edge_list[idx]
                d = pt.distance(line)
                if d < best_dist and d <= SNAP_THRESHOLD_TC_POINT:
                    best_dist = d
                    best_idx = idx
            if best_idx is None:
                continue
            u, v, _ = edge_list[best_idx]
            tc_val = str(row['traffic_calming']).strip().lower()
            used_car = car_allowed_idx and best_idx in car_allowed_idx
            if used_car:
                tc_point_car_allowed += 1
            else:
                tc_point_fallback += 1
            G.edges[u, v]['traffic_calming_point'] = tc_val
            G.edges[u, v]['traffic_calming_point_lon'] = lon
            G.edges[u, v]['traffic_calming_point_lat'] = lat
            if G.has_edge(v, u):
                G.edges[v, u]['traffic_calming_point'] = tc_val
                G.edges[v, u]['traffic_calming_point_lon'] = lon
                G.edges[v, u]['traffic_calming_point_lat'] = lat
            tc_point_snap += 1
        print(f"   -> Traffic calming (points) snapped: {tc_point_snap} (car-allowed: {tc_point_car_allowed}, fallback: {tc_point_fallback}).")

    # =====================================================================
    # STEP 5: SAVE GRAPH
    # =====================================================================
    print(f"5. Saving to {OUTPUT_PATH}...")
    nx.write_graphml(G, OUTPUT_PATH)
    print("   -> Graph saved.")

    # =====================================================================
    # STEP 6: GENERATE DEBUG REPORT
    # =====================================================================
    print(f"6. Generating debug report -> {REPORT_PATH}")
    generate_report(G, df, df_points, snap_count, snap_miss,
                    count_motorway_banned, count_oneway, count_contraflow, nodes_removed,
                    barrier_snap=barrier_snap, give_way_snap=give_way_snap, stop_snap=stop_snap,
                    kerb_snap=kerb_snap, kerb_no_pedestrian_way=kerb_no_pedestrian_way,
                    confidence_band_0=confidence_band_0, confidence_band_low=confidence_band_low,
                    confidence_band_mid=confidence_band_mid, confidence_band_1=confidence_band_1,
                    tc_point_snap=tc_point_snap, tc_point_car_allowed=tc_point_car_allowed,
                    tc_point_fallback=tc_point_fallback)

    print("SUCCESS! Enhanced directed graph built.")


def generate_report(G, df_lines, df_points, snap_count, snap_miss,
                    motorway_banned, oneway_count, contraflow_count, islands_removed,
                    barrier_snap=0, give_way_snap=0, stop_snap=0,
                    kerb_snap=0, kerb_no_pedestrian_way=0,
                    confidence_band_0=0, confidence_band_low=0, confidence_band_mid=0, confidence_band_1=0,
                    tc_point_snap=0, tc_point_car_allowed=0, tc_point_fallback=0):
    """Writes a comprehensive debug report covering every tag."""

    lines = []
    w = lines.append

    w("=" * 80)
    w("  LONDON CYCLE MAPS — GRAPH BUILD DEBUG REPORT")
    w(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    w("=" * 80)

    # --- GENERAL STATS ---
    w("")
    w("-" * 80)
    w("  1. GENERAL STATISTICS")
    w("-" * 80)
    total_nodes = G.number_of_nodes()
    total_edges = G.number_of_edges()
    w(f"  Total graph nodes:           {total_nodes:>10,}")
    w(f"  Total graph edges:           {total_edges:>10,}")
    w(f"  Raw segments from SQL:       {len(df_lines):>10,}")
    w(f"  Motorway segments banned:    {motorway_banned:>10,}")
    w(f"  One-way streets processed:   {oneway_count:>10,}")
    w(f"  Contraflow exceptions:       {contraflow_count:>10,}")
    w(f"  Island nodes removed:        {islands_removed:>10,}")

    # --- EDGE TAG COVERAGE ---
    w("")
    w("-" * 80)
    w("  2. EDGE TAG COVERAGE (non-empty values per tag)")
    w("-" * 80)

    edge_tags = [
        'osm_id', 'name', 'type', 'length', 'risk', 'geometry',
        'surface', 'lit', 'maxspeed', 'width', 'bridge', 'tunnel', 'junction', 'smoothness',
        'cycleway', 'cycleway_left', 'cycleway_right', 'cycleway_both',
        'segregated', 'cycleway_separation', 'cycleway_left_separation',
        'cycleway_right_separation', 'cycleway_buffer',
        'cycleway_width', 'cycleway_surface', 'cycleway_smoothness',
        'lcn_ref', 'rcn_ref', 'ncn_ref', 'cycle_network',
        'hgv', 'traffic_calming',
        'barrier_confidence', 'traffic_calming_point', 'traffic_calming_point_lat', 'traffic_calming_point_lon',
    ]

    # Collect edge data
    edge_data_lists = {tag: [] for tag in edge_tags}
    for u, v, data in G.edges(data=True):
        for tag in edge_tags:
            val = str(data.get(tag, '')).strip()
            edge_data_lists[tag].append(val)

    w(f"  {'TAG':<35} {'NON-EMPTY':>10} {'/ TOTAL':>10} {'COVERAGE':>10}")
    w(f"  {'-'*35} {'-'*10} {'-'*10} {'-'*10}")

    for tag in edge_tags:
        vals = edge_data_lists[tag]
        non_empty = sum(1 for v in vals if v and v != '0' and v != '0.0' and v.lower() != 'none')
        total = len(vals)
        pct = (non_empty / total * 100) if total > 0 else 0
        w(f"  {tag:<35} {non_empty:>10,} {total:>10,} {pct:>9.1f}%")

    # --- EDGE TAG VALUE DISTRIBUTIONS ---
    w("")
    w("-" * 80)
    w("  3. EDGE TAG VALUE DISTRIBUTIONS (top values per tag)")
    w("-" * 80)

    categorical_tags = [
        'type', 'surface', 'lit', 'maxspeed', 'smoothness',
        'cycleway', 'cycleway_left', 'cycleway_right', 'cycleway_both',
        'segregated', 'cycleway_separation', 'cycleway_left_separation',
        'cycleway_right_separation', 'cycleway_buffer',
        'cycleway_surface', 'cycleway_smoothness',
        'lcn_ref', 'rcn_ref', 'ncn_ref', 'cycle_network',
        'hgv', 'traffic_calming', 'traffic_calming_point',
        'bridge', 'tunnel', 'junction',
    ]

    for tag in categorical_tags:
        vals = edge_data_lists[tag]
        non_empty_vals = [v for v in vals if v and v.lower() != 'none']
        if not non_empty_vals:
            w(f"\n  [{tag}] — ALL EMPTY (0 values)")
            continue

        from collections import Counter
        counts = Counter(non_empty_vals)
        top = counts.most_common(20)
        w(f"\n  [{tag}] — {len(non_empty_vals):,} values, {len(counts)} unique")
        for val, cnt in top:
            pct = cnt / len(non_empty_vals) * 100
            w(f"    {val:<40} {cnt:>8,}  ({pct:>5.1f}%)")

    # --- NODE / INTERSECTION TAG COVERAGE (barrier, give_way, stop_sign are on EDGES now) ---
    w("")
    w("-" * 80)
    w("  4. INTERSECTION / NODE TAG COVERAGE")
    w("-" * 80)

    node_tags = ['traffic_signals', 'mini_roundabout', 'crossing', 'crossing_type']

    w(f"  Raw point features from SQL:  {len(df_points):>10,}")
    w(f"  Node-snapped (signals/crossing/mr): {snap_count:>10,}")
    w(f"  Missed (node):                {snap_miss:>10,}")
    w(f"  Edge-snapped barrier (non-kerb): {barrier_snap:>10,}")
    w(f"  Kerb snapped to pedestrian:  {kerb_snap:>10,}")
    w(f"  Kerb no pedestrian way:       {kerb_no_pedestrian_way:>10,}")
    w(f"  Barrier confidence bands:    0: {confidence_band_0}, (0,0.5): {confidence_band_low}, [0.5,1): {confidence_band_mid}, 1: {confidence_band_1}")
    w(f"  Edge-snapped give_way:        {give_way_snap:>10,}")
    w(f"  Edge-snapped stop_sign:       {stop_snap:>10,}")
    w(f"  Traffic calming (points) snapped: {tc_point_snap:>10,} (car-allowed: {tc_point_car_allowed}, fallback: {tc_point_fallback})")
    w("")

    node_tag_counts = {tag: 0 for tag in node_tags}
    crossing_type_values = []

    for node_id, data in G.nodes(data=True):
        for tag in node_tags:
            val = str(data.get(tag, '')).strip()
            if val and val.lower() != 'none':
                node_tag_counts[tag] += 1
                if tag == 'crossing_type':
                    crossing_type_values.append(val)

    w(f"  {'NODE TAG':<35} {'COUNT':>10} {'/ TOTAL NODES':>15}")
    w(f"  {'-'*35} {'-'*10} {'-'*15}")

    for tag in node_tags:
        cnt = node_tag_counts[tag]
        pct = (cnt / total_nodes * 100) if total_nodes > 0 else 0
        w(f"  {tag:<35} {cnt:>10,} {total_nodes:>10,}   ({pct:.2f}%)")

    # Crossing type distribution
    if crossing_type_values:
        from collections import Counter
        w(f"\n  [crossing_type] — {len(crossing_type_values)} tagged nodes, value distribution:")
        for val, cnt in Counter(crossing_type_values).most_common(15):
            w(f"    {val:<40} {cnt:>8,}")

    # --- EDGE POINT-DERIVED (barrier, give_way, stop_sign) ---
    w("")
    w("-" * 80)
    w("  4b. EDGE TAG COVERAGE (point-derived: barrier, give_way, stop_sign)")
    w("-" * 80)

    barrier_count = give_way_count = stop_count = 0
    barrier_values = []
    for u, v, data in G.edges(data=True):
        if str(data.get('barrier', '')).strip():
            barrier_count += 1
            barrier_values.append(str(data.get('barrier', '')).strip().lower())
        if str(data.get('give_way', '')).strip():
            give_way_count += 1
        if str(data.get('stop_sign', '')).strip():
            stop_count += 1

    w(f"  Edges with barrier:           {barrier_count:>10,} / {total_edges:,}")
    w(f"  Edges with give_way:          {give_way_count:>10,} / {total_edges:,}")
    w(f"  Edges with stop_sign:         {stop_count:>10,} / {total_edges:,}")
    if barrier_values:
        from collections import Counter
        w(f"\n  [barrier] — value distribution on edges:")
        for val, cnt in Counter(barrier_values).most_common(15):
            w(f"    {val:<40} {cnt:>8,}")

    barrier_confidence_count = sum(1 for _u, _v, d in G.edges(data=True) if d.get('barrier_confidence') is not None)
    tc_point_count = sum(1 for _u, _v, d in G.edges(data=True) if str(d.get('traffic_calming_point', '')).strip())
    w(f"  Edges with barrier_confidence:  {barrier_confidence_count:>10,} / {total_edges:,}")
    w(f"  Edges with traffic_calming_point: {tc_point_count:>10,} / {total_edges:,}")

    # --- RISK DISTRIBUTION ---
    w("")
    w("-" * 80)
    w("  5. RISK (ACCIDENT COUNT) DISTRIBUTION")
    w("-" * 80)

    risk_vals = [float(d.get('risk', 0)) for _, _, d in G.edges(data=True)]
    nonzero_risk = [r for r in risk_vals if r > 0]
    w(f"  Edges with risk > 0:         {len(nonzero_risk):>10,} / {total_edges:,}")
    if nonzero_risk:
        w(f"  Min risk (non-zero):         {min(nonzero_risk):>10.1f}")
        w(f"  Max risk:                    {max(nonzero_risk):>10.1f}")
        w(f"  Mean risk (non-zero):        {sum(nonzero_risk)/len(nonzero_risk):>10.2f}")

    # --- NETWORK REFS SUMMARY ---
    w("")
    w("-" * 80)
    w("  6. STRATEGIC CYCLING NETWORK SUMMARY")
    w("-" * 80)

    for ref_tag in ['lcn_ref', 'rcn_ref', 'ncn_ref']:
        vals = [v for v in edge_data_lists[ref_tag] if v and v.lower() != 'none']
        if vals:
            from collections import Counter
            counts = Counter(vals)
            w(f"\n  [{ref_tag}] — {len(vals):,} edges across {len(counts)} routes:")
            for val, cnt in counts.most_common(30):
                w(f"    {val:<40} {cnt:>8,} edges")
        else:
            w(f"\n  [{ref_tag}] — no data found")

    w("")
    w("=" * 80)
    w("  END OF REPORT")
    w("=" * 80)

    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f"   -> Report written: {len(lines)} lines.")


if __name__ == "__main__":
    main()
