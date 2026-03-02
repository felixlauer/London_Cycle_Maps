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
STEEP_THRESHOLD = 0.033   # 3.3% (Definition of "Steep")
SHORT_NOISE_LIMIT = 12.0  # < 12m: Flatten 100% (Factor 0.0)
MEDIUM_NOISE_LIMIT = 20.0 # 12-20m: Dampen 70% (Factor 0.3)
LONG_NOISE_LIMIT = 35.0   # 20-35m: Dampen 50% (Factor 0.5)
PATCH_SIZE = 5            # 5x5 pixel window for median smoothing
CAP_LIMIT = 0.20          # 20% Hard Cap (Safety Net)

# Hardcoded Projections
WGS84_WKT = 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]'
BNG_WKT = 'PROJCS["OSGB 1936 / British National Grid",GEOGCS["OSGB 1936",DATUM["OSGB_1936",SPHEROID["Airy 1830",6377563.396,299.3249646]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",49],PARAMETER["central_meridian",-2],PARAMETER["scale_factor",0.9996012717],PARAMETER["false_easting",400000],PARAMETER["false_northing",-100000],UNIT["metre",1]]'

def calculate_metrics(G):
    """Calculates total ascent and counts of short/steep artifacts."""
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
            if length < SHORT_NOISE_LIMIT:
                count_short_steep += 1
                
    return total_ascent, count_steep, count_short_steep

def is_connected_to_hill(node, G, exclude_neighbor, threshold):
    """
    Checks if 'node' has any OTHER steep edges connected to it.
    Robustly handles both DiGraph (Simple) and MultiDiGraph (Complex).
    """
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

        for data in edge_data_list:
            if abs(float(data.get('grade', 0.0))) > threshold: return True 
    return False

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
    print(f"   -> Short Noise (<{SHORT_NOISE_LIMIT}m): {noise_start}")

    # --- STEP 1: PIXEL-LEVEL SMOOTHING ---
    print(f"\n--- 3. RUNNING 5x5 MEDIAN SMOOTHING (Pixel Level) ---")
    nodes_to_fix = set()
    for u, v, data in G.edges(data=True):
        if float(data.get('length', 0)) < LONG_NOISE_LIMIT and float(data.get('grade', 0)) > STEEP_THRESHOLD:
            nodes_to_fix.add(u)
            nodes_to_fix.add(v)
            
    print(f"   -> Analyzing {len(nodes_to_fix)} suspicious nodes...")
    
    transformer = Transformer.from_crs(WGS84_WKT, BNG_WKT, always_xy=True)
    updates = {}
    deltas = [] # To store height differences
    
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
        print(f"   -> MAX Height Change:    {np.max(deltas):.2f} m")

    # --- STEP 2: RECALCULATE GRADES ---
    for u, v, data in G.edges(data=True):
        ele_u = G.nodes[u].get('elevation', 0.0)
        ele_v = G.nodes[v].get('elevation', 0.0)
        length = float(data.get('length', 1.0))
        if length > 0.1: data['grade'] = (ele_v - ele_u) / length
        else: data['grade'] = 0.0

    # --- STEP 3: SMART CONTEXT-AWARE FILTERING ---
    print(f"\n--- 4. APPLYING SMART 'ISOLATION' FILTER & DAMPING ---")
    
    stats = {"flattened": 0, "damped_heavy": 0, "damped_light": 0, "preserved_hill": 0, "capped": 0}
    
    for u, v, data in G.edges(data=True):
        length = float(data.get('length', 1.0))
        raw_grade = float(data.get('grade', 0.0))
        abs_grade = abs(raw_grade)
        
        final_grade = raw_grade
        
        # LOGIC: Only filter if it is Steep AND Short enough to be noise
        if abs_grade > STEEP_THRESHOLD and length < LONG_NOISE_LIMIT:
            
            # CONTEXT CHECK
            u_connected = is_connected_to_hill(u, G, v, STEEP_THRESHOLD)
            v_connected = is_connected_to_hill(v, G, u, STEEP_THRESHOLD)
            
            if u_connected or v_connected:
                stats["preserved_hill"] += 1
            else:
                # ISOLATED -> DAMPEN
                if length < SHORT_NOISE_LIMIT:
                    final_grade = 0.0
                    stats["flattened"] += 1
                elif length < MEDIUM_NOISE_LIMIT:
                    final_grade = raw_grade * 0.3
                    stats["damped_heavy"] += 1
                elif length < LONG_NOISE_LIMIT:
                    final_grade = raw_grade * 0.5
                    stats["damped_light"] += 1

        # SAFETY CAP
        if abs(final_grade) > CAP_LIMIT:
            final_grade = CAP_LIMIT if final_grade > 0 else -CAP_LIMIT
            stats["capped"] += 1
            
        data['grade'] = final_grade

    # --- FINAL METRICS ---
    ascent_end, steep_end, noise_end = calculate_metrics(G)
    
    print("="*50)
    print("ULTIMATE PROCESSING REPORT")
    print("="*50)
    print(f"1. Noise Analysis (Artifacts Removed):")
    print(f"   - Short & Steep Artifacts Before: {noise_start}")
    print(f"   - Short & Steep Artifacts After:  {noise_end}")
    print(f"   - REMOVED: {noise_start - noise_end} ({(1 - noise_end/noise_start)*100:.1f}% reduction)")
    print("-" * 50)
    print(f"2. Elevation Gain (The 'Flatness' Check):")
    print(f"   - Raw Ascent:     {ascent_start/1000:.2f} km")
    print(f"   - Cleaned Ascent: {ascent_end/1000:.2f} km")
    print(f"   - LOST:           {(ascent_start - ascent_end)/1000:.2f} km ({(1 - ascent_end/ascent_start)*100:.1f}%)")
    print("-" * 50)
    print(f"3. Smoothing Accuracy:")
    if deltas:
        print(f"   - The ground moved by Median {np.median(deltas)*100:.1f} cm.")
    print("-" * 50)
    print(f"4. Detailed Processing Stats:")
    print(f"   - Preserved Hills:      {stats['preserved_hill']} segments (Connected to other steep roads)")
    print(f"   - FLATTENED (0.0x):     {stats['flattened']} tiny artifacts (<{SHORT_NOISE_LIMIT}m)")
    print(f"   - DAMPED HEAVY (0.3x):  {stats['damped_heavy']} short artifacts ({SHORT_NOISE_LIMIT}-{MEDIUM_NOISE_LIMIT}m)")
    print(f"   - DAMPED LIGHT (0.5x):  {stats['damped_light']} medium artifacts ({MEDIUM_NOISE_LIMIT}-{LONG_NOISE_LIMIT}m)")
    print(f"   - SAFETY CAPPED:        {stats['capped']} segments (Hard limit >{CAP_LIMIT*100}%)")
    print("="*50)

    nx.write_graphml(G, OUTPUT_GRAPH)
    print(f"\nSUCCESS! Final Graph saved to: {OUTPUT_GRAPH}")

if __name__ == "__main__":
    main()