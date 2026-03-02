"""
Add node elevation and edge grade to london.graphml using LIDAR VRT.
Output: 1_data/london_elev_raw.graphml.
If you change output attributes or file names, update 0_documentation/GRAPH.md
"""
import os
import sys
import networkx as nx
import rasterio
from pyproj import Transformer

# --- SILENCE THE NOISE ---
os.environ['PROJ_LIB'] = os.path.join(sys.prefix, 'Library', 'share', 'proj')
os.environ['CPL_LOG'] = 'OFF' 

# --- CONFIG ---
INPUT_GRAPH = os.path.join("..", "1_data", "london.graphml")
OUTPUT_GRAPH = os.path.join("..", "1_data", "london_elev_raw.graphml")
DEM_FILE = os.path.join("..", "1_data", "London_LIDAR_Virtual.vrt") 

# --- HARDCODED PROJECTION STRINGS ---
WGS84_WKT = 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]'
BNG_WKT = 'PROJCS["OSGB 1936 / British National Grid",GEOGCS["OSGB 1936",DATUM["OSGB_1936",SPHEROID["Airy 1830",6377563.396,299.3249646]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",49],PARAMETER["central_meridian",-2],PARAMETER["scale_factor",0.9996012717],PARAMETER["false_easting",400000],PARAMETER["false_northing",-100000],UNIT["metre",1]]'

def main():
    print("--- 1. LOADING GRAPH ---")
    if not os.path.exists(INPUT_GRAPH):
        print(f"Error: {INPUT_GRAPH} not found.")
        return
    G = nx.read_graphml(INPUT_GRAPH)
    print(f"   -> Graph loaded ({len(G.nodes())} nodes).")

    # Initialize the Transformer with hardcoded strings
    transformer = Transformer.from_crs(WGS84_WKT, BNG_WKT, always_xy=True)

    # 2. TRANSFORM AND SAMPLE
    print("--- 2. TRANSFORMING COORDS & SAMPLING 1M LIDAR ---")
    nodes_with_coords = [n for n, d in G.nodes(data=True) if 'x' in d and 'y' in d]
    
    # Transform (lon, lat) to (Easting, Northing)
    raw_coords = [(float(G.nodes[n]['x']), float(G.nodes[n]['y'])) for n in nodes_with_coords]
    transformed_coords = [transformer.transform(lon, lat) for lon, lat in raw_coords]
    
    updates = {}
    zero_default_count = 0
    
    try:
        with rasterio.open(DEM_FILE) as src:
            # src.sample reads the exact 1m pixels from the VRT/ZIPs
            sampled_values = src.sample(transformed_coords, indexes=1)
            
            for i, val in enumerate(sampled_values):
                ele = float(val[0])
                
                # Check for "No Data" values (-9999 is our VRT standard)
                if ele <= -1000: 
                    ele = 0.0
                    zero_default_count += 1
                
                updates[nodes_with_coords[i]] = ele
                
                if i % 50000 == 0 and i > 0:
                    print(f"      Processed {i} nodes...")

    except Exception as e:
        print(f"   [!] Error: {e}")
        return

    nx.set_node_attributes(G, updates, 'elevation')

    # 3. CALCULATING PHYSICS
    print("--- 3. CALCULATING SEGMENT PHYSICS ---")
    count_total = len(G.edges())
    count_uphill = 0
    count_downhill = 0
    count_flat = 0
    
    for u, v, data in G.edges(data=True):
        if 'elevation' in G.nodes[u] and 'elevation' in G.nodes[v]:
            ele_u = G.nodes[u]['elevation']
            ele_v = G.nodes[v]['elevation']
            length = float(data.get('length', 1.0))
            
            if length > 0.1: 
                # Raw Grade = Rise / Run
                grade = (ele_v - ele_u) / length 
                data['grade'] = grade
                
                # Using 0.1% as the threshold for "flat"
                if grade > 0.001: 
                    count_uphill += 1
                elif grade < -0.001: 
                    count_downhill += 1
                else: 
                    count_flat += 1
            else:
                data['grade'] = 0.0
                count_flat += 1
        else:
            data['grade'] = 0.0
            count_flat += 1

    # --- 4. FINAL SUMMARY ---
    print("\n" + "="*40)
    print("        LIDAR PROCESSING SUMMARY")
    print("="*40)
    print(f"Total Road Segments:    {count_total}")
    print(f"Uphill Segments:        {count_uphill}")
    print(f"Downhill Segments:      {count_downhill}")
    print(f"Flat Segments:          {count_flat}")
    print(f"Nodes Missing LIDAR:    {zero_default_count}")
    print("="*40)
    
    # --- 5. SAVING ---
    nx.write_graphml(G, OUTPUT_GRAPH)
    print(f"\nSUCCESS! High-precision graph saved to: {OUTPUT_GRAPH}")

if __name__ == "__main__":
    main()