import geopandas as gpd
from sqlalchemy import create_engine
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

# UPDATED PATH: We now look inside the 'london_shapefiles' subfolder
SHP_PATH = os.path.join("..", "1_data", "london_shapefiles", "gis_osm_roads_free_1.shp")

def main():
    print("--- STARTING ROAD NETWORK IMPORT ---")
    
    # 1. Connect to Database
    db_url = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:5432/{DB_NAME}"
    engine = create_engine(db_url)
    print("Connected to database.")

    # 2. Read Shapefile
    print(f"Reading Shapefile from: {SHP_PATH}")
    print("This might take 30-60 seconds...")
    
    try:
        # Read the file
        gdf = gpd.read_file(SHP_PATH)
    except Exception as e:
        print(f"ERROR: Could not read file.")
        print(f"Details: {e}")
        print(f"Check: Is 'gis_osm_roads_free_1.shp' inside '1_data/london_shapefiles'?")
        return

    print(f"Loaded {len(gdf)} road segments.")

    # 3. Filter Data
    # We only care about specific columns for routing/risk analysis
    # 'fclass' tells us if it is a cycleway, primary road, residential, etc.
    cols_to_keep = ['osm_id', 'code', 'fclass', 'name', 'ref', 'geometry']
    
    # Ensure we only keep columns that actually exist in the file
    existing_cols = [c for c in cols_to_keep if c in gdf.columns]
    gdf = gdf[existing_cols]

    # 4. Upload to Database
    print("Uploading to PostGIS table 'ways' (this is heavy, give it 2-3 minutes)...")
    
    # We call the table 'ways' to match standard OSM terminology
    gdf.to_postgis("ways", engine, if_exists='replace', index=False, chunksize=5000)

    print("SUCCESS! Road network is now in the database.")

if __name__ == "__main__":
    main()