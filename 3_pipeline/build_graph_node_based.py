"""
BACKUP: Node-based point snap (barrier, give_way, stop on nodes).
Original build_graph.py before edge-based barrier/give_way/stop implementation.
Build directed routing graph from PostgreSQL (planet_osm_line + planet_osm_point).
Output: 1_data/london.graphml (+ graph_debug_report.txt).

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

            best_node = node_list[indices[i]][0]
            node_data = G.nodes[best_node]
            pt = df_points.iloc[i]

            hw = str(pt['highway']).lower()
            barrier = str(pt['barrier']).lower()
            crossing = str(pt['crossing']).lower()

            if hw == 'traffic_signals':
                node_data['traffic_signals'] = 'yes'
            elif hw == 'mini_roundabout':
                node_data['mini_roundabout'] = 'yes'
            elif hw == 'crossing':
                node_data['crossing'] = 'yes'
                if crossing:
                    node_data['crossing_type'] = crossing
            elif hw == 'give_way':
                node_data['give_way'] = 'yes'
            elif hw == 'stop':
                node_data['stop_sign'] = 'yes'

            if barrier:
                node_data['barrier'] = barrier

            snap_count += 1

        print(f"   -> Snapped {snap_count} point features to graph nodes.")
    print(f"   -> Missed {snap_miss} features (no node within {SNAP_THRESHOLD} deg).")

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
                    count_motorway_banned, count_oneway, count_contraflow, nodes_removed)

    print("SUCCESS! Enhanced directed graph built.")


def generate_report(G, df_lines, df_points, snap_count, snap_miss,
                    motorway_banned, oneway_count, contraflow_count, islands_removed):
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
        'hgv', 'traffic_calming',
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

    # --- NODE / INTERSECTION TAG COVERAGE ---
    w("")
    w("-" * 80)
    w("  4. INTERSECTION / NODE TAG COVERAGE")
    w("-" * 80)

    node_tags = ['traffic_signals', 'mini_roundabout', 'crossing', 'crossing_type',
                 'give_way', 'stop_sign', 'barrier']

    w(f"  Raw point features from SQL:  {len(df_points):>10,}")
    w(f"  Successfully snapped:         {snap_count:>10,}")
    w(f"  Missed (too far):             {snap_miss:>10,}")
    w("")

    node_tag_counts = {tag: 0 for tag in node_tags}
    barrier_values = []
    crossing_type_values = []

    for node_id, data in G.nodes(data=True):
        for tag in node_tags:
            val = str(data.get(tag, '')).strip()
            if val and val.lower() != 'none':
                node_tag_counts[tag] += 1
                if tag == 'barrier':
                    barrier_values.append(val)
                if tag == 'crossing_type':
                    crossing_type_values.append(val)

    w(f"  {'NODE TAG':<35} {'COUNT':>10} {'/ TOTAL NODES':>15}")
    w(f"  {'-'*35} {'-'*10} {'-'*15}")

    for tag in node_tags:
        cnt = node_tag_counts[tag]
        pct = (cnt / total_nodes * 100) if total_nodes > 0 else 0
        w(f"  {tag:<35} {cnt:>10,} {total_nodes:>10,}   ({pct:.2f}%)")

    # Barrier value distribution
    if barrier_values:
        from collections import Counter
        w(f"\n  [barrier] — {len(barrier_values)} tagged nodes, value distribution:")
        for val, cnt in Counter(barrier_values).most_common(15):
            w(f"    {val:<40} {cnt:>8,}")

    # Crossing type distribution
    if crossing_type_values:
        from collections import Counter
        w(f"\n  [crossing_type] — {len(crossing_type_values)} tagged nodes, value distribution:")
        for val, cnt in Counter(crossing_type_values).most_common(15):
            w(f"    {val:<40} {cnt:>8,}")

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
