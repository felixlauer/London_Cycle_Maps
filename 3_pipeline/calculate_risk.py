from sqlalchemy import create_engine, text
import pandas as pd
from tqdm import tqdm
import time
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

def main():
    print("--- FINAL RISK CALCULATION ---")
    
    db_url = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:5432/{DB_NAME}"
    engine = create_engine(db_url)
    conn = engine.connect()

    # --- PHASE 1: PREPARATION ---
    print("\n[PHASE 1] Resetting Scores...")
    conn.execute(text("ALTER TABLE ways ADD COLUMN IF NOT EXISTS accident_count INTEGER DEFAULT 0;"))
    conn.execute(text("UPDATE ways SET accident_count = 0;"))
    conn.commit()

    # --- PHASE 2: THE FIX (GEOGRAPHY INDEXES) ---
    print("\n[PHASE 2] Building 'Geography' Indexes...")
    print("   (This allows us to measure METERS efficiently)")
    
    # We create an index on the CASTED data ((geometry::geography))
    # This matches your query exactly.
    print("   -> Indexing Roads (Geography)...")
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_ways_geog ON ways USING GIST ((geometry::geography));"))
    conn.commit()

    print("   -> Indexing Accidents (Geography)...")
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_accidents_geog ON accidents USING GIST ((geometry::geography));"))
    conn.commit()
    print("   -> Indexes Ready.")

    # --- PHASE 3: CALCULATION ---
    print("\n[PHASE 3] Calculating Risk...")
    
    # Get all Accident IDs
    accident_ids = pd.read_sql("SELECT collision_id FROM accidents", conn)['collision_id'].tolist()
    total_accidents = len(accident_ids)
    
    # Batch Process (Larger batch size is safe now)
    batch_size = 1000
    
    for i in tqdm(range(0, total_accidents, batch_size), desc="Matching Accidents"):
        batch = accident_ids[i : i + batch_size]
        if not batch: continue
        
        ids_tuple = tuple(batch)
        
        # The Query (Unchanged, but now it has an index to use!)
        sql = text("""
            WITH relevant_roads AS (
                SELECT w.osm_id
                FROM ways w
                JOIN accidents a 
                ON ST_DWithin(w.geometry::geography, a.geometry::geography, 15)
                WHERE a.collision_id IN :ids
            )
            UPDATE ways
            SET accident_count = accident_count + 1
            FROM relevant_roads
            WHERE ways.osm_id = relevant_roads.osm_id;
        """)
        
        conn.execute(sql, {"ids": ids_tuple})
        conn.commit()

    print("\nSUCCESS! Risk calculation complete.")
    conn.close()

if __name__ == "__main__":
    main()