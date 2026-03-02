import os
import glob
import re
import zipfile
import subprocess

# --- CONFIGURATION ---
RAW_DIR = os.path.join("..", "1_data", "lidar_raw")
VRT_FILE = os.path.join("..", "1_data", "London_LIDAR_Virtual.vrt")

# Your defined London bounds: X (0-5), Y (5-9)
X_MIN, X_MAX = 0, 5
Y_MIN, Y_MAX = 5, 9

def get_internal_tif_name(zip_path):
    """Opens the zip to find the actual .tif filename (case-sensitive)"""
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            tifs = [f for f in z.namelist() if f.endswith('.tif') and 'dtm' in f.lower()]
            return tifs[0] if tifs else None
    except:
        return None

def main():
    print(f"--- 1. FILTERING FOR LONDON BOX (X:{X_MIN}-{X_MAX}, Y:{Y_MIN}-{Y_MAX}) ---")
    
    all_zips = glob.glob(os.path.join(RAW_DIR, "*TQ*.zip"))
    vsi_paths = []
    
    for zf in all_zips:
        filename = os.path.basename(zf)
        # Regex to find the TQ grid coordinates (e.g., TQ28)
        match = re.search(r"TQ(\d)(\d)", filename, re.IGNORECASE)
        
        if match:
            x, y = int(match.group(1)), int(match.group(2))
            
            if (X_MIN <= x <= X_MAX) and (Y_MIN <= y <= Y_MAX):
                # Find the exact name inside (Fixes the skip skip skip errors)
                internal_name = get_internal_tif_name(zf)
                if internal_name:
                    abs_path = os.path.abspath(zf).replace("\\", "/")
                    vsi_paths.append(f"/vsizip/{abs_path}/{internal_name}")

    if not vsi_paths:
        print("ERROR: No files matched your grid range or ZIPs are empty.")
        return

    print(f"-> Selected {len(vsi_paths)} tiles for the London Virtual Map.")

    # --- 2. EXECUTE GDAL ---
    print("--- 2. STITCHING VIRTUAL MOSAIC ---")
    try:
        # -srcnodata: The weird value we found earlier
        # -vrtnodata: The clean -9999 value we want
        cmd = [
            'gdalbuildvrt', 
            '-srcnodata', '-3.4028234663852886e+38', 
            '-vrtnodata', '-9999', 
            VRT_FILE
        ] + vsi_paths
        
        subprocess.run(cmd, check=True)
        print(f"\nSUCCESS! Virtual map created: {VRT_FILE}")
        
    except Exception as e:
        print(f"\nFAILED: {e}")

if __name__ == "__main__":
    main()