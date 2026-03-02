import pandas as pd
import os

# --- CONFIGURATION ---
# We define London as the 32 Boroughs + City + Heathrow
# Based on your screenshot, this is IDs 1 through 32, plus 57.
LONDON_DISTRICTS = list(range(1, 33)) + [57]

INPUT_DIR = os.path.join("..", "1_data")
OUTPUT_FILE = os.path.join(INPUT_DIR, "london_cyclist_collisions.csv")

def main():
    print("--- STARTING DATA PRE-PROCESSING ---")

    # 1. Load Vehicle Data (To find the bikes)
    print("1. Loading Vehicle Data...")
    try:
        # We only need the collision ID and the vehicle type
        veh_cols = ['collision_index', 'vehicle_type']
        # Try finding the file (handling capital/lowercase naming issues)
        veh_path = os.path.join(INPUT_DIR, "vehicles.csv")
        if not os.path.exists(veh_path):
             # Try capital V if lowercase doesn't exist
             veh_path = os.path.join(INPUT_DIR, "Vehicles.csv")
        
        df_veh = pd.read_csv(veh_path, usecols=veh_cols, low_memory=False)
    except FileNotFoundError:
        print("ERROR: Could not find 'vehicles.csv' in 1_data folder.")
        return

    # Filter: Keep only Pedal Cycles (Type 1)
    bike_crashes = df_veh[df_veh['vehicle_type'] == 1]
    
    # Get a unique list of Collision IDs that involved a bike
    # set() makes looking them up instant
    bike_collision_ids = set(bike_crashes['collision_index'].unique())
    print(f"   -> Found {len(bike_collision_ids)} collisions involving cyclists.")


    # 2. Load Accident Data (To filter by location)
    print("2. Loading Accident Data...")
    acc_path = os.path.join(INPUT_DIR, "accidents.csv")
    
    # We load everything because we want to save a clean full file at the end
    df_acc = pd.read_csv(acc_path, low_memory=False)
    initial_count = len(df_acc)
    print(f"   -> Loaded {initial_count} total UK accidents.")

    # 3. Apply Filters
    print("3. Applying Filters (London + Cyclists)...")
    
    # Filter A: Location (London only)
    # specific column name depends on dataset version, usually 'local_authority_district'
    df_london = df_acc[df_acc['local_authority_district'].isin(LONDON_DISTRICTS)]
    
    # Filter B: Cyclists (Must be in our bike_collision_ids list)
    df_final = df_london[df_london['collision_index'].isin(bike_collision_ids)]
    
    final_count = len(df_final)
    print(f"   -> Reduced from {initial_count} to {final_count} rows.")
    print(f"   -> Kept {final_count / initial_count * 100:.2f}% of data.")

    # 4. Save
    print(f"4. Saving clean file to: {OUTPUT_FILE}")
    df_final.to_csv(OUTPUT_FILE, index=False)
    print("SUCCESS! Pre-processing complete.")

if __name__ == "__main__":
    main()