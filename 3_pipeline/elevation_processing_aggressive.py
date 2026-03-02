"""
Smooth and correct elevation; output final graph for routing.
Input: 1_data/london_elev_raw.graphml -> Output: 1_data/london_elev_final.graphml.
If you change output attributes or file names, update 0_documentation/GRAPH.md
"""
import os
import sys
import networkx as nx
import rasterio
import numpy as np
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
SHORT_LIMIT = 12.0        # "Short" (<12m)
INTERMEDIATE_LIMIT = 50.0 # "Intermediate" (<50m)
PATCH_SIZE = 5            # 5x5 smoothing
CAP_LIMIT = 0.20          # 20% Hard Cap

# --- UPDATED CONFIGURATION ---
# We REMOVE 'path' because we can't verify if it's a cycleway (missing tags).
# We KEEP 'footway' because in UK/London, footways are illegal to cycle unless marked.
FLATTEN_CLASSES = {
    'pedestrian', 'steps', 'footway', 'corridor', 'platform', # Walking structures
    'motorway', 'motorway_link', 'trunk', 'trunk_link'        # High-speed car only
}

# Hardcoded Projections
WGS84_WKT = 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]'
BNG_WKT = 'PROJCS["OSGB 1936 / British National Grid",GEOGCS["OSGB 1936",DATUM["OSGB_1936",SPHEROID["Airy 1830",6377563.396,299.3249646]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",49],PARAMETER["central_meridian",-2],PARAMETER["scale_factor",0.9996012717],PARAMETER["false_easting",400000],PARAMETER["false_northing",-100000],UNIT["metre",1]]'

def calculate_metrics(G):
    total_ascent = 0.0
    count_steep = 0
    count_short_steep = 0
    
    for u, v, data in G.edges(data=True):
        grade = float(data.get('grade', 0.0))
        length = float(data.get('length', 0.0))
        
        if grade > 0:
            total_ascent += (grade * length)
            
        if abs(grade) > STEEP_THRESHOLD:
            count_steep += 1
            if length < SHORT_LIMIT:
                count_short_steep += 1
                
    return total_ascent, count_steep, count_short_steep

def analyze_connectivity(node, G, exclude_neighbor, threshold):
    steep_lengths = []
    all_neighbors = set(list(G.successors(node)) + list(G.predecessors(node)))
    
    for nbr in all_neighbors:
        if nbr == exclude_neighbor: continue 
        
        edge_data_list = []
        if G.has_edge(node, nbr):
            raw_data = G[node][nbr]
            if G.is_multigraph(): edge_data_list.extend(raw_data.values())
            else: edge_data_list.append(raw_data)

        if G.has_edge(nbr, node):
            raw_data = G[nbr][node]
            if G.is_multigraph(): edge_data_list.extend(raw_data.values())
            else: edge_data_list.append(raw_data)

        for d in edge_data_list:
            if abs(float(d.get('grade', 0.0))) > threshold:
                steep_lengths.append(float(d.get('length', 0.0)))
                
    return steep_lengths

def main():
    print("--- 1. LOADING RAW GRAPH ---")
    if not os.path.exists(INPUT_GRAPH):
        print("Error: Input graph not found.")
        return
    G = nx.read_graphml(INPUT_GRAPH)
    print(f"   -> Nodes: {len(G.nodes())} | Edges: {len(G.edges())}")

    # --- BASELINE METRICS ---
    print("\n--- 2. CALCULATING BASELINE METRICS ---")
    ascent_start, steep_start, noise_start = calculate_metrics(G)
    print(f"   -> Total Ascent:      {ascent_start/1000:.2f} km")
    print(f"   -> Steep Segments:    {steep_start}")
    print(f"   -> Short Noise (<{SHORT_LIMIT}m): {noise_start}")

    # --- STEP 1: PIXEL-LEVEL SMOOTHING ---
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
                        transform=src.transform
                    ))
                    valid = window[window > -1000]
                    if valid.size > 0: 
                        new_ele = float(np.median(valid))
                        old_ele = float(G.nodes[node].get('elevation', 0.0))
                        
                        updates[node] = new_ele
                        deltas.append(abs(new_ele - old_ele))
                except: pass
    except Exception as e:
        print(f"Warning: Could not open VRT: {e}")

    for n, ele in updates.items(): G.nodes[n]['elevation'] = ele
    
    print(f"   -> Updated {len(updates)} nodes.")
    if deltas:
        print(f"   -> AVG Height Change:    {np.mean(deltas)*100:.2f} cm")
        print(f"   -> MEDIAN Height Change: {np.median(deltas)*100:.2f} cm")

    # --- STEP 2: RECALCULATE GRADES ---
    for u, v, data in G.edges(data=True):
        ele_u = G.nodes[u].get('elevation', 0.0)
        ele_v = G.nodes[v].get('elevation', 0.0)
        length = float(data.get('length', 1.0))
        if length > 0.1: data['grade'] = (ele_v - ele_u) / length
        else: data['grade'] = 0.0

# --- STEP 3: CLUSTER LOGIC ---
    print(f"\n--- 4. APPLYING CLUSTER LOGIC ---")
    
    stats = {
        "micro_noise_flat": 0, 
        "pedestrian_flat": 0, 
        "short_short_flat": 0, 
        "short_inter_damp": 0, 
        "chain_preserved": 0, 
        "capped": 0, 
        "others_damped": 0, 
        "isolated_flat": 0
    }
    
    for u, v, data in G.edges(data=True):
        length = float(data.get('length', 1.0))
        raw_grade = float(data.get('grade', 0.0))
        
        # 'type' comes from the 'highway' column in your DB
        highway = str(data.get('type', '')).lower()
        
        final_grade = raw_grade

        # --- 0. MICRO-SEGMENT PRE-FILTER (<5m) ---
        if length < 5.0:
            final_grade = 0.0
            data['grade'] = 0.0
            stats["micro_noise_flat"] += 1
            continue

        # --- 1. PEDESTRIAN CHECK (Strict List) ---
        # Since we lack the 'bicycle' tag, we only flatten types that are 
        # almost certainly not valid for climbing (Steps, Footways, Pedestrian Zones).
        if highway in FLATTEN_CLASSES:
            final_grade = 0.0
            stats["pedestrian_flat"] += 1
            data['grade'] = final_grade
            continue 
        
        # --- 2. STEEP SEGMENT ANALYSIS ---
        if abs(raw_grade) > STEEP_THRESHOLD:
            # Analyze Connectivity
            u_steep_lens = analyze_connectivity(u, G, v, STEEP_THRESHOLD)
            v_steep_lens = analyze_connectivity(v, G, u, STEEP_THRESHOLD)
            
            total_chain_count = 1 + len(u_steep_lens) + len(v_steep_lens)
            
            # A. CHAIN OF 3 RULE (Keep)
            if total_chain_count >= 3:
                stats["chain_preserved"] += 1
                final_grade = raw_grade # KEEP
                
            else:
                connected_lengths = u_steep_lens + v_steep_lens
                has_intermediate_neighbor = any(l > SHORT_LIMIT for l in connected_lengths)
                
                if length < SHORT_LIMIT:
                    if not connected_lengths:
                        final_grade = 0.0
                        stats["isolated_flat"] += 1
                    elif has_intermediate_neighbor:
                        final_grade = raw_grade * 0.3 # Reduce BY 70%
                        stats["short_inter_damp"] += 1
                    else:
                        final_grade = 0.0
                        stats["short_short_flat"] += 1
                elif length < INTERMEDIATE_LIMIT:
                     if not connected_lengths:
                         final_grade = raw_grade * 0.5 # Reduce BY 50%
                         stats["others_damped"] += 1

        # Safety Cap
        if abs(final_grade) > CAP_LIMIT:
            final_grade = CAP_LIMIT if final_grade > 0 else -CAP_LIMIT
            stats["capped"] += 1
            
        data['grade'] = final_grade

    # --- FINAL METRICS ---
    ascent_end, steep_end, noise_end = calculate_metrics(G)
    
    print("="*50)
    print("ULTIMATE CLUSTER REPORT")
    print("="*50)
    print(f"1. Pixel Smoothing Accuracy:")
    if deltas:
        print(f"   - The ground moved by Median {np.median(deltas)*100:.1f} cm.")
    print("-" * 50)
    print(f"2. Elevation Gain (The 'Flatness' Check):")
    print(f"   - Raw Ascent:     {ascent_start/1000:.2f} km")
    print(f"   - Cleaned Ascent: {ascent_end/1000:.2f} km")
    print(f"   - LOST:           {(ascent_start - ascent_end)/1000:.2f} km ({(1 - ascent_end/ascent_start)*100:.1f}%)")
    print("-" * 50)
    print(f"3. Logic Stats:")
    print(f"   - PRESERVED (Chain >3):   {stats['chain_preserved']}")
    print(f"   - FLATTENED (Micro <5m):  {stats['micro_noise_flat']} (Ignored)")
    print(f"   - FLATTENED (Strict List): {stats['pedestrian_flat']} (Steps/Footways)")
    print(f"   - FLATTENED (Sawtooth):   {stats['short_short_flat']}")
    print(f"   - FLATTENED (Isolated):   {stats['isolated_flat']}")
    print(f"   - DAMPED (Ramps):         {stats['short_inter_damp']} (0.3x Factor)")
    print(f"   - DAMPED (Medium Iso):    {stats['others_damped']} (0.5x Factor)")
    print(f"   - SAFETY CAPPED:          {stats['capped']}")
    print("="*50)

    nx.write_graphml(G, OUTPUT_GRAPH)
    print(f"\nSUCCESS! Final Graph saved to: {OUTPUT_GRAPH}")

if __name__ == "__main__":
    main()