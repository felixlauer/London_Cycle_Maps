import networkx as nx
import requests
import time
import os
import json

# --- CONFIG ---
INPUT_GRAPH = os.path.join("..", "1_data", "london.graphml")
OUTPUT_GRAPH = os.path.join("..", "1_data", "london_elev.graphml")
CACHE_FILE = "elevation_partial.json"

# SAFE SETTINGS
BATCH_SIZE = 50       # Small batch = Short URL = No Error 400/414
DELAY_SECONDS = 0.5   # 2 requests per second (Safe for free tier)

def chunked_list(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def main():
    print("--- 1. LOADING DATA ---")
    if not os.path.exists(INPUT_GRAPH):
        print(f"Error: {INPUT_GRAPH} not found.")
        return

    G = nx.read_graphml(INPUT_GRAPH)
    all_nodes = [n for n, d in G.nodes(data=True) if 'x' in d and 'y' in d]
    print(f"   -> Graph has {len(all_nodes)} nodes with coordinates.")

    # 2. LOAD CHECKPOINT (RESUME CAPABILITY)
    elevation_cache = {}
    if os.path.exists(CACHE_FILE):
        print(f"   -> Found checkpoint file '{CACHE_FILE}'. Loading...")
        try:
            with open(CACHE_FILE, 'r') as f:
                elevation_cache = json.load(f)
            print(f"   -> Resumed with {len(elevation_cache)} nodes already fetched.")
        except:
            print("   -> Checkpoint file corrupted. Starting fresh.")

    # 3. IDENTIFY MISSING NODES
    # Only fetch nodes we haven't cached yet
    nodes_to_fetch = [n for n in all_nodes if n not in elevation_cache]
    
    if not nodes_to_fetch:
        print("   -> All nodes already cached! Skipping fetch.")
    else:
        print(f"--- 2. FETCHING ELEVATION FOR {len(nodes_to_fetch)} MISSING NODES ---")
        batches = list(chunked_list(nodes_to_fetch, BATCH_SIZE))
        print(f"   -> Processing {len(batches)} batches (Batch Size: {BATCH_SIZE})...")

        for i, batch in enumerate(batches):
            # Format coords to 5 decimal places
            lats = ["{:.5f}".format(G.nodes[n]['y']) for n in batch]
            lons = ["{:.5f}".format(G.nodes[n]['x']) for n in batch]
            
            url = f"https://api.open-meteo.com/v1/elevation?latitude={','.join(lats)}&longitude={','.join(lons)}"
            
            success = False
            retries = 0
            
            while not success and retries < 3:
                try:
                    r = requests.get(url, timeout=10)
                    
                    if r.status_code == 200:
                        data = r.json()
                        if 'elevation' in data:
                            elevs = data['elevation']
                            for node, elev in zip(batch, elevs):
                                elevation_cache[node] = float(elev) if elev is not None else 0.0
                        success = True
                    elif r.status_code == 429:
                        print(f"      [!] Rate Limit (429). Pausing 10s...")
                        time.sleep(10)
                        retries += 1
                    else:
                        print(f"      [!] Error {r.status_code}. Retrying...")
                        time.sleep(2)
                        retries += 1
                        
                except Exception as e:
                    print(f"      [!] Connection Error. Retrying...")
                    time.sleep(2)
                    retries += 1

            # Save Checkpoint every 20 batches
            if i % 20 == 0:
                with open(CACHE_FILE, 'w') as f:
                    json.dump(elevation_cache, f)
                print(f"   Batch {i}/{len(batches)} done. (Saved checkpoint)")
            
            time.sleep(DELAY_SECONDS)

        # Final Save
        with open(CACHE_FILE, 'w') as f:
            json.dump(elevation_cache, f)

    # 4. APPLY TO GRAPH
    print(f"--- 3. APPLYING DATA TO GRAPH ---")
    
    # Update nodes
    nx.set_node_attributes(G, elevation_cache, 'elevation')

    print("--- 4. CALCULATING EDGE SLOPES ---")
    count_flat = 0
    count_uphill = 0
    count_downhill = 0
    
    for u, v, data in G.edges(data=True):
        # We look up in elevation_cache directly for speed
        if u in elevation_cache and v in elevation_cache:
            ele_u = elevation_cache[u]
            ele_v = elevation_cache[v]
            length = float(data.get('length', 1.0))
            
            if length > 0.1: 
                rise = ele_v - ele_u
                grade = rise / length 
                
                # Cap outliers
                if grade > 0.3: grade = 0.3
                if grade < -0.3: grade = -0.3
                
                data['grade'] = grade
                
                if grade > 0.01: count_uphill += 1
                elif grade < -0.01: count_downhill += 1
                else: count_flat += 1
            else:
                data['grade'] = 0.0
        else:
            data['grade'] = 0.0
            count_flat += 1

    print(f"   -> Stats: {count_uphill} Ups / {count_downhill} Downs / {count_flat} Flats")

    print(f"--- 5. SAVING TO {OUTPUT_GRAPH} ---")
    nx.write_graphml(G, OUTPUT_GRAPH)
    
    # Optional: Clean up cache if successful
    # os.remove(CACHE_FILE) 
    print("SUCCESS! Graph enriched.")

if __name__ == "__main__":
    main()