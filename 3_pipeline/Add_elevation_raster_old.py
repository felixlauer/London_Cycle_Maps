import networkx as nx
import os
import rasterio

# --- CONFIG ---
INPUT_GRAPH = os.path.join("..", "1_data", "london.graphml")
OUTPUT_GRAPH = os.path.join("..", "1_data", "london_elev.graphml")
DEM_FILE = os.path.join("..", "1_data", "London_SRTM30m.tif") 

def main():
    print("--- 1. LOADING GRAPH ---")
    if not os.path.exists(INPUT_GRAPH):
        print(f"Error: {INPUT_GRAPH} not found.")
        return
    G = nx.read_graphml(INPUT_GRAPH)
    print(f"   -> Graph loaded ({len(G.nodes())} nodes).")

    if not os.path.exists(DEM_FILE):
        print(f"Error: DEM file not found at {DEM_FILE}")
        return

    # 3. SAMPLING RAW ELEVATION
    print(f"--- 3. SAMPLING RAW ELEVATION ---")
    nodes_with_coords = [n for n, d in G.nodes(data=True) if 'x' in d and 'y' in d]
    updates = {}
    coords = [(float(G.nodes[n]['x']), float(G.nodes[n]['y'])) for n in nodes_with_coords]
    
    try:
        with rasterio.open(DEM_FILE) as src:
            sampled_values = src.sample(coords, indexes=1)
            for i, val in enumerate(sampled_values):
                ele = float(val[0])
                if ele < -1000: ele = 0.0
                updates[nodes_with_coords[i]] = ele
    except Exception as e:
        print(f"   [!] Error reading raster: {e}")
        return

    nx.set_node_attributes(G, updates, 'elevation')

    # 4. CALCULATING RAW SLOPES
    print("--- 4. CALCULATING RAW PHYSICS ---")
    count_flat = 0
    count_uphill = 0
    count_downhill = 0
    
    for u, v, data in G.edges(data=True):
        if 'elevation' in G.nodes[u] and 'elevation' in G.nodes[v]:
            ele_u = G.nodes[u]['elevation']
            ele_v = G.nodes[v]['elevation']
            length = float(data.get('length', 1.0))
            
            if length > 0.1: 
                rise = ele_v - ele_u
                grade = rise / length 
                
                # We keep the raw grade, no smoothing/capping
                data['grade'] = grade
                
                if grade > 0.0: count_uphill += 1
                elif grade < 0.0: count_downhill += 1
                else: count_flat += 1
            else:
                data['grade'] = 0.0
                count_flat += 1
        else:
            data['grade'] = 0.0
            count_flat += 1

    print(f"   -> Stats: {count_uphill} Ups / {count_downhill} Downs / {count_flat} Flats")
    nx.write_graphml(G, OUTPUT_GRAPH)
    print("SUCCESS! Raw Elevation Processed.")

if __name__ == "__main__":
    main()