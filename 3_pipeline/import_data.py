import pandas as pd
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

# UPDATED: Pointing to the new clean file
CSV_PATH = os.path.join("..", "1_data", "london_cyclist_collisions.csv")

def main():
    print("--- STARTING CLEAN IMPORT (London Cyclists Only) ---")
    
    # 1. Connect
    db_url = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:5432/{DB_NAME}"
    engine = create_engine(db_url)
    print("Connected to database.")

    # 2. Smart Column Detection
    possible_id_cols = ['collision_index', 'collision_reference', 'accident_index']
    try:
        header = pd.read_csv(CSV_PATH, nrows=0).columns.tolist()
    except FileNotFoundError:
        print(f"ERROR: Could not find file at {CSV_PATH}")
        return

    id_col = next((col for col in possible_id_cols if col in header), None)
    if not id_col:
        print("ERROR: Could not find ID column.")
        return
    print(f"Detected ID column: '{id_col}'")

    # 3. Read Data
    cols_to_load = [id_col, 'location_easting_osgr', 'location_northing_osgr', 
                    'collision_severity', 'number_of_vehicles', 'date', 'time']
    # Safety check to only load columns that exist
    cols_to_load = [c for c in cols_to_load if c in header]

    print("Reading CSV...")
    df = pd.read_csv(CSV_PATH, usecols=cols_to_load)

    # 4. Clean & Rename
    df = df.dropna(subset=['location_easting_osgr', 'location_northing_osgr'])
    df = df.rename(columns={id_col: 'collision_id'})
    print(f"Importing {len(df)} specific cycling accidents...")

    # 5. Convert to Geometry
    gdf = gpd.GeoDataFrame(
        df, 
        geometry=gpd.points_from_xy(df.location_easting_osgr, df.location_northing_osgr),
        crs="EPSG:27700"
    ).to_crs("EPSG:4326")

    # 6. Upload
    gdf.to_postgis("accidents", engine, if_exists='replace', index=False)
    print("SUCCESS! Clean data is in the database.")

if __name__ == "__main__":
    main()