import networkx as nx
import os
import rasterio
import numpy as np
from math import radians, cos, sin, asin, sqrt

# --- CONFIG ---
INPUT_GRAPH = os.path.join("..", "1_data", "london.graphml")
OUTPUT_GRAPH = os.path.join("..", "1_data", "london_elev.graphml")
DEM_FILE = os.path.join("..", "1_data", "London_SRTM30m.tif") 

# Constants from Thesis
IDW_POWER = 2.0  #
SMOOTHING_WINDOW_M = 30.0  #
ANCHOR_DIST_M = 30.0  #

def haversine(lon1, lat1, lon2, lat2):
    """
    Calculate the great circle distance between two points 
    on the earth (specified in decimal degrees)
    """
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1 
    dlat = lat2 - lat1 
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a)) 
    r = 6371000 
    return c * r

def get_elevation_idw(src, x, y):
    """
    Extracts elevation using Inverse Distance Weighting (IDW) 
    from the 9 surrounding cells (3x3 window).
    """
    try:
        row, col = src.index(x, y)
        data = src.read(1, window=rasterio.windows.Window(col - 1, row - 1, 3, 3))
        
        if data.shape != (3, 3):
            val = next(src.sample([(x, y)]))[0]
            return float(val)

        transform = src.transform
        numerator = 0.0
        denominator = 0.0
        
        for d_r in range(3):
            for d_c in range(3):
                val = data[d_r, d_c]
                if val < -1000: continue
                
                cell_x, cell_y = transform * (col - 1 + d_c + 0.5, row - 1 + d_r + 0.5)
                dist = sqrt((x - cell_x)**2 + (y - cell_y)**2)
                
                if dist < 1e-6: return float(val)
                
                weight = 1.0 / (dist ** IDW_POWER)
                numerator += weight * val
                denominator += weight
        
        if denominator == 0: return 0.0
        return numerator / denominator

    except Exception:
        try:
            val = next(src.sample([(x, y)]))[0]
            return float(val) if val > -1000 else 0.0
        except:
            return 0.0

def correct_tunnels_and_bridges(G):
    """
    Identifies tunnels/bridges and interpolates elevation between 
    endpoints +/- 30m.
    """
    print("   -> Correcting Tunnels and Bridges...")
    
    target_edges = []
    for u, v, data in G.edges(data=True):
        is_tunnel = data.get('tunnel') in ['yes', 'true', '1']
        is_bridge = data.get('bridge') in ['yes', 'true', '1']
        if is_tunnel or is_bridge:
            target_edges.append((u, v))
            
    if not target_edges: return

    tb_graph = G.edge_subgraph(target_edges).copy()
    
    for component in nx.connected_components(tb_graph):
        comp_subgraph = tb_graph.subgraph(component)
        endpoints = [n for n, d in comp_subgraph.degree() if d == 1]
        
        if len(endpoints) != 2: continue
            
        start_node, end_node = endpoints
        
        def find_anchor(start_n, forbidden_nodes):
            visited = {start_n}
            queue = [(start_n, 0)]
            
            while queue:
                curr, dist = queue.pop(0)
                if dist >= ANCHOR_DIST_M:
                    return curr, G.nodes[curr].get('elevation', 0)
                
                for neighbor in G.neighbors(curr):
                    if neighbor not in forbidden_nodes and neighbor not in visited:
                        # Check graph type for edge access
                        edge_data = G.get_edge_data(curr, neighbor)
                        if G.is_multigraph():
                            attr = edge_data[next(iter(edge_data))]
                        else:
                            attr = edge_data
                            
                        edge_len = float(attr.get('length', 10))
                        new_dist = dist + edge_len
                        visited.add(neighbor)
                        queue.append((neighbor, new_dist))
            return start_n, G.nodes[start_n].get('elevation', 0)

        tunnel_nodes = set(component)
        anchor_start, ele_start = find_anchor(start_node, tunnel_nodes)
        anchor_end, ele_end = find_anchor(end_node, tunnel_nodes)
        
        as_x, as_y = G.nodes[anchor_start]['x'], G.nodes[anchor_start]['y']
        ae_x, ae_y = G.nodes[anchor_end]['x'], G.nodes[anchor_end]['y']
        total_dist = haversine(as_x, as_y, ae_x, ae_y)
        
        if total_dist == 0: continue

        for node in component:
            n_x, n_y = G.nodes[node]['x'], G.nodes[node]['y']
            dist_from_start = haversine(as_x, as_y, n_x, n_y)
            
            ratio = dist_from_start / total_dist
            if ratio > 1: ratio = 1
            if ratio < 0: ratio = 0
            
            new_ele = ele_start + (ele_end - ele_start) * ratio
            G.nodes[node]['elevation'] = new_ele

def correct_rivers(G):
    """
    Enforces monotonic flow for waterways.
    """
    print("   -> Correcting Rivers...")
    river_edges = []
    for u, v, data in G.edges(data=True):
        if 'waterway' in data:
            river_edges.append((u, v))
            
    changed = True
    passes = 0
    max_passes = 5 
    
    while changed and passes < max_passes:
        changed = False
        passes += 1
        for u, v in river_edges:
            if 'elevation' not in G.nodes[u] or 'elevation' not in G.nodes[v]:
                continue
            ele_u = G.nodes[u]['elevation']
            ele_v = G.nodes[v]['elevation']
            
            if ele_v > ele_u:
                G.nodes[v]['elevation'] = ele_u
                changed = True

def smooth_roads(G):
    """
    Applies Simple Moving Average (SMA) to road nodes using a 30m window.
    """
    print("   -> Smoothing Roads (SMA 30m)...")
    
    smoothed_values = {}
    is_multigraph = G.is_multigraph() # Check once
    
    for node in G.nodes():
        if 'elevation' not in G.nodes[node]:
            continue
            
        window_nodes = []
        queue = [(node, 0)] 
        visited = {node}
        
        while queue:
            curr, dist = queue.pop(0)
            window_nodes.append(curr)
            
            if dist < (SMOOTHING_WINDOW_M / 2):
                for neighbor in G.neighbors(curr):
                    if neighbor not in visited:
                        edge_data = G.get_edge_data(curr, neighbor)
                        
                        if edge_data:
                            # Handle Graph vs MultiGraph safely
                            if is_multigraph:
                                first_key = next(iter(edge_data))
                                attrs = edge_data[first_key]
                            else:
                                attrs = edge_data
                            
                            try:
                                w_len = float(attrs.get('length', 10.0))
                            except (ValueError, TypeError):
                                w_len = 10.0
                            
                            if (dist + w_len) <= (SMOOTHING_WINDOW_M / 2):
                                visited.add(neighbor)
                                queue.append((neighbor, dist + w_len))
        
        elevations = [G.nodes[n]['elevation'] for n in window_nodes]
        if elevations:
            smoothed_values[node] = sum(elevations) / len(elevations)
        
    nx.set_node_attributes(G, smoothed_values, 'elevation')

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

    print(f"--- 2. ENRICHING ELEVATION (IDW) ---")
    nodes_with_coords = [n for n, d in G.nodes(data=True) if 'x' in d and 'y' in d]
    updates = {}
    
    try:
        with rasterio.open(DEM_FILE) as src:
            total = len(nodes_with_coords)
            for i, n in enumerate(nodes_with_coords):
                x = float(G.nodes[n]['x'])
                y = float(G.nodes[n]['y'])
                ele = get_elevation_idw(src, x, y)
                updates[n] = ele
                
                if i % 25000 == 0:
                    print(f"      Processed {i}/{total} nodes...")
                    
    except Exception as e:
        print(f"   [!] Error reading raster: {e}")
        return

    nx.set_node_attributes(G, updates, 'elevation')

    print("--- 3. APPLYING THESIS CORRECTIONS ---")
    correct_tunnels_and_bridges(G)
    correct_rivers(G)
    smooth_roads(G)

    print("--- 4. CALCULATING FINAL PHYSICS ---")
    count_flat = 0
    count_uphill = 0
    count_downhill = 0
    is_multigraph = G.is_multigraph()
    
    for u, v, data in G.edges(data=True):
        if 'elevation' in G.nodes[u] and 'elevation' in G.nodes[v]:
            ele_u = G.nodes[u]['elevation']
            ele_v = G.nodes[v]['elevation']
            length = float(data.get('length', 1.0))
            
            if length > 0.1: 
                rise = ele_v - ele_u
                grade = rise / length 
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
    print(f"SUCCESS! Processed graph saved to {OUTPUT_GRAPH}")

if __name__ == "__main__":
    main()