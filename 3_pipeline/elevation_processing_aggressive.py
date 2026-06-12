"""
Smooth and correct elevation; output final graph for routing.
Input: 1_data/london_elev_raw.gpickle -> Output: 1_data/london_elev_final.gpickle.
If you change output attributes or file names, update 0_documentation/GRAPH.md

Usage:
  python elevation_processing_aggressive.py           # full run (DEM smooth + hill filter)
  python elevation_processing_aggressive.py --skip-dem  # hill filter only (fast; grades from raw)
"""
import argparse
import os
import sys
from collections import defaultdict

import networkx as nx
import numpy as np
import rasterio
from graph_io import load_graph, save_graph, fast_path
from pyproj import Transformer

# --- SILENCE WARNINGS ---
os.environ['PROJ_LIB'] = os.path.join(sys.prefix, 'Library', 'share', 'proj')
os.environ['CPL_LOG'] = 'OFF'

# --- CONFIGURATION ---
INPUT_GRAPH = os.path.join("..", "1_data", "london_elev_raw.graphml")
OUTPUT_GRAPH = os.path.join("..", "1_data", "london_elev_final.graphml")
DEM_FILE = os.path.join("..", "1_data", "London_LIDAR_Virtual.vrt")

# --- TUNING PARAMETERS ---
STEEP_THRESHOLD = 0.033   # 3.3%
SHORT_LIMIT = 12.0        # metric reporting: short steep edges
INTERMEDIATE_LIMIT = 50.0 # suspicious-node smoothing window (edge length)
PATCH_SIZE = 5            # 5x5 median DEM patch
CAP_LIMIT = 0.20          # 20% hard cap

# Connected ascent-hill length (metres along steep subgraph)
HILL_KEEP_M = 100.0       # full grade
HILL_HALF_M = 50.0        # 0.5x grade between HALF_M and KEEP_M
HILL_HALF_FACTOR = 0.5

FLATTEN_CLASSES = {
    'pedestrian', 'steps', 'footway', 'corridor', 'platform',
    'motorway', 'motorway_link', 'trunk', 'trunk_link',
}

WGS84_WKT = 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]'
BNG_WKT = 'PROJCS["OSGB 1936 / British National Grid",GEOGCS["OSGB 1936",DATUM["OSGB_1936",SPHEROID["Airy 1830",6377563.396,299.3249646]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",49],PARAMETER["central_meridian",-2],PARAMETER["scale_factor",0.9996012717],PARAMETER["false_easting",400000],PARAMETER["false_northing",-100000],UNIT["metre",1]]'


def calculate_metrics(G):
    total_ascent = 0.0
    count_steep = 0
    count_ascent_steep = 0
    count_short_steep = 0
    network_m = 0.0

    for _u, _v, data in G.edges(data=True):
        grade = float(data.get('grade', 0.0))
        length = float(data.get('length', 0.0))
        network_m += length

        if grade > 0:
            total_ascent += grade * length

        if abs(grade) > STEEP_THRESHOLD:
            count_steep += 1
            if length < SHORT_LIMIT:
                count_short_steep += 1
        if grade > STEEP_THRESHOLD:
            count_ascent_steep += 1

    steep_per_100km = 100.0 * count_ascent_steep / (network_m / 1000.0) if network_m else 0.0
    return {
        'ascent_m': total_ascent,
        'steep': count_steep,
        'ascent_steep': count_ascent_steep,
        'short_steep': count_short_steep,
        'network_km': network_m / 1000.0,
        'steep_per_100km': steep_per_100km,
    }


def apply_hill_length_filter(G):
    """
    Union-find on ascent-steep edges (grade > STEEP_THRESHOLD) sharing a node.
    Component length = sum of member edge lengths.
    < HILL_HALF_M -> flatten ascent; HALF_M..KEEP_M -> halve; >= KEEP_M -> keep.
    Descents and sub-threshold grades are unchanged.
    """
    steep_members = []
    node_to_local = defaultdict(list)

    for idx, (u, v, data) in enumerate(G.edges(data=True)):
        grade = float(data.get('grade', 0.0))
        if grade <= STEEP_THRESHOLD:
            continue
        length = float(data.get('length', 0.0))
        local = len(steep_members)
        steep_members.append((idx, u, v, length, grade))
        node_to_local[u].append(local)
        node_to_local[v].append(local)

    parent = list(range(len(steep_members)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for locals_at_node in node_to_local.values():
        for i in range(1, len(locals_at_node)):
            union(locals_at_node[0], locals_at_node[i])

    comps = defaultdict(list)
    for i in range(len(steep_members)):
        comps[find(i)].append(i)

    stats = {
        'hill_components': len(comps),
        'hill_flat': 0,
        'hill_halved': 0,
        'hill_kept': 0,
    }

    for members in comps.values():
        chain_m = sum(steep_members[i][3] for i in members)
        if chain_m >= HILL_KEEP_M:
            mult = 1.0
            stats['hill_kept'] += len(members)
        elif chain_m >= HILL_HALF_M:
            mult = HILL_HALF_FACTOR
            stats['hill_halved'] += len(members)
        else:
            mult = 0.0
            stats['hill_flat'] += len(members)

        for i in members:
            _edge_idx, u, v, _length, grade = steep_members[i]
            G[u][v]['grade'] = grade * mult

    return stats


def main():
    parser = argparse.ArgumentParser(description="Elevation smoothing and hill-length filter")
    parser.add_argument(
        "--skip-dem",
        action="store_true",
        help="Skip 5x5 DEM median pass (use grades already on london_elev_raw)",
    )
    args = parser.parse_args()

    print("--- 1. LOADING RAW GRAPH ---")
    if not os.path.exists(INPUT_GRAPH) and not os.path.exists(fast_path(INPUT_GRAPH)):
        print("Error: Input graph not found (.graphml or .gpickle).")
        return
    G = load_graph(INPUT_GRAPH)
    print(f"   -> Nodes: {len(G.nodes())} | Edges: {len(G.edges())}")

    print("\n--- 2. CALCULATING BASELINE METRICS ---")
    start = calculate_metrics(G)
    print(f"   -> Total Ascent:           {start['ascent_m']/1000:.2f} km")
    print(f"   -> Ascent-steep edges:     {start['ascent_steep']:,}")
    print(f"   -> Steep per 100 km:       {start['steep_per_100km']:.1f}")
    print(f"   -> Short steep (<{SHORT_LIMIT}m): {start['short_steep']:,}")

    deltas = []
    if args.skip_dem:
        print("\n--- 3. DEM SMOOTHING SKIPPED (--skip-dem) ---")
    else:
        print(f"\n--- 3. RUNNING 5x5 MEDIAN SMOOTHING (Pixel Level) ---")
        nodes_to_fix = set()
        for u, v, data in G.edges(data=True):
            if float(data.get('length', 0)) < INTERMEDIATE_LIMIT and float(data.get('grade', 0)) > STEEP_THRESHOLD:
                nodes_to_fix.add(u)
                nodes_to_fix.add(v)

        print(f"   -> Analyzing {len(nodes_to_fix)} suspicious nodes...")

        transformer = Transformer.from_crs(WGS84_WKT, BNG_WKT, always_xy=True)
        updates = {}
        deltas = []

        try:
            with rasterio.open(DEM_FILE) as src:
                offset = PATCH_SIZE / 2.0
                for i, node in enumerate(nodes_to_fix):
                    try:
                        lon, lat = float(G.nodes[node]['x']), float(G.nodes[node]['y'])
                        easting, northing = transformer.transform(lon, lat)
                        window = src.read(1, window=rasterio.windows.from_bounds(
                            easting - offset, northing - offset,
                            easting + offset, northing + offset,
                            transform=src.transform,
                        ))
                        valid = window[window > -1000]
                        if valid.size > 0:
                            new_ele = float(np.median(valid))
                            old_ele = float(G.nodes[node].get('elevation', 0.0))
                            updates[node] = new_ele
                            deltas.append(abs(new_ele - old_ele))
                    except Exception:
                        pass
                    if i > 0 and i % 100000 == 0:
                        print(f"      Processed {i} nodes...")
        except Exception as e:
            print(f"Warning: Could not open VRT: {e}")

        for n, ele in updates.items():
            G.nodes[n]['elevation'] = ele

        print(f"   -> Updated {len(updates)} nodes.")
        if deltas:
            print(f"   -> AVG Height Change:    {np.mean(deltas)*100:.2f} cm")
            print(f"   -> MEDIAN Height Change: {np.median(deltas)*100:.2f} cm")

        print("\n--- 4. RECALCULATING GRADES ---")
        for u, v, data in G.edges(data=True):
            ele_u = G.nodes[u].get('elevation', 0.0)
            ele_v = G.nodes[v].get('elevation', 0.0)
            length = float(data.get('length', 1.0))
            if length > 0.1:
                data['grade'] = (ele_v - ele_u) / length
            else:
                data['grade'] = 0.0

        mid = calculate_metrics(G)
        print(f"   -> After smooth: ascent-steep {mid['ascent_steep']:,}  steep/100km {mid['steep_per_100km']:.1f}")

    print("\n--- 5. PEDESTRIAN / MICRO PRE-FILTERS ---")
    stats = {
        'micro_noise_flat': 0,
        'pedestrian_flat': 0,
        'capped': 0,
    }

    for u, v, data in G.edges(data=True):
        length = float(data.get('length', 1.0))
        raw_grade = float(data.get('grade', 0.0))
        highway = str(data.get('type', '')).lower()
        final_grade = raw_grade

        if length < 5.0:
            final_grade = 0.0
            stats['micro_noise_flat'] += 1
        elif highway in FLATTEN_CLASSES:
            final_grade = 0.0
            stats['pedestrian_flat'] += 1

        data['grade'] = final_grade

    print(
        f"   -> Micro <5m flattened: {stats['micro_noise_flat']:,}  "
        f"Pedestrian types: {stats['pedestrian_flat']:,}"
    )

    print(
        f"\n--- 6. CONNECTED HILL LENGTH FILTER "
        f"(flat <{HILL_HALF_M}m, half {HILL_HALF_M}-{HILL_KEEP_M}m, keep >={HILL_KEEP_M}m) ---"
    )
    hill_stats = apply_hill_length_filter(G)
    stats.update(hill_stats)
    print(f"   -> Hill components: {stats['hill_components']:,}")
    print(f"   -> Ascent edges flattened: {stats['hill_flat']:,}")
    print(f"   -> Ascent edges halved:    {stats['hill_halved']:,}")
    print(f"   -> Ascent edges kept:      {stats['hill_kept']:,}")

    print("\n--- 7. SAFETY CAP (+/- 20%) ---")
    for u, v, data in G.edges(data=True):
        final_grade = float(data.get('grade', 0.0))
        if abs(final_grade) > CAP_LIMIT:
            final_grade = CAP_LIMIT if final_grade > 0 else -CAP_LIMIT
            stats['capped'] += 1
        data['grade'] = final_grade

    end = calculate_metrics(G)

    print("=" * 50)
    print("ELEVATION PROCESSING REPORT")
    print("=" * 50)
    if deltas:
        print(f"1. Pixel smoothing median shift: {np.median(deltas)*100:.1f} cm")
    print("-" * 50)
    print("2. Elevation gain:")
    print(f"   - Raw input:      {start['ascent_m']/1000:.2f} km")
    print(f"   - Final output:   {end['ascent_m']/1000:.2f} km")
    lost_pct = (1 - end['ascent_m'] / start['ascent_m']) * 100 if start['ascent_m'] else 0
    print(f"   - Removed:        {(start['ascent_m'] - end['ascent_m'])/1000:.2f} km ({lost_pct:.1f}%)")
    print("-" * 50)
    print("3. Ascent-steep edges (grade > 3.3%):")
    print(f"   - Raw input:      {start['ascent_steep']:,}  ({start['steep_per_100km']:.1f} / 100 km)")
    print(f"   - Final output:   {end['ascent_steep']:,}  ({end['steep_per_100km']:.1f} / 100 km)")
    print(f"   - Short steep:    {end['short_steep']:,}")
    print("-" * 50)
    print("4. Hill-length logic:")
    print(f"   - Components:     {stats['hill_components']:,}")
    print(f"   - Flattened:      {stats['hill_flat']:,}")
    print(f"   - Halved:         {stats['hill_halved']:,}")
    print(f"   - Kept full:      {stats['hill_kept']:,}")
    print(f"   - Grade capped:   {stats['capped']:,}")
    print("=" * 50)

    save_graph(G, OUTPUT_GRAPH, write_graphml=False, write_fast=True)
    print(f"\nSUCCESS! Final Graph saved to: {fast_path(OUTPUT_GRAPH)}")


if __name__ == "__main__":
    main()
