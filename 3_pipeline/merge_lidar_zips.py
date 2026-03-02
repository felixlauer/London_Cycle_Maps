import os
import zipfile
import glob
import re
import rasterio
from rasterio.merge import merge
import numpy as np

# --- CONFIGURATION ---
RAW_DIR = os.path.join("..", "1_data", "lidar_raw")
OUTPUT_FILE = os.path.join("..", "1_data", "London_LIDAR_DTM_1m.tif")

# --- FILTER SETTINGS (TQ GRID RANGE) ---
X_MIN, X_MAX = 0, 5
Y_MIN, Y_MAX = 5, 9

# --- SAFE NO DATA VALUE ---
SAFE_NODATA = -9999.0

def is_file_relevant(filename):
    match = re.search(r"TQ(\d)(\d)", filename, re.IGNORECASE)
    if match:
        x, y = int(match.group(1)), int(match.group(2))
        return (X_MIN <= x <= X_MAX) and (Y_MIN <= y <= Y_MAX)
    return False

def main():

    # --- 1. FILTER ZIP FILES ---
    all_zips = glob.glob(os.path.join(RAW_DIR, "*TQ*.zip"))
    relevant_zips = [z for z in all_zips if is_file_relevant(os.path.basename(z))]

    if not relevant_zips:
        raise RuntimeError("No matching tiles found")

    extracted_tifs = []

    # --- 2. EXTRACT DTM TIFFS ---
    for zf in relevant_zips:
        with zipfile.ZipFile(zf, 'r') as z:
            tif_files = [f for f in z.namelist() if f.lower().endswith(".tif") and "dtm" in f.lower()]
            for t in tif_files:
                out_path = os.path.join(RAW_DIR, os.path.basename(t))
                z.extract(t, RAW_DIR)
                extracted_tifs.append(out_path)

    if not extracted_tifs:
        raise RuntimeError("No DTM TIFFs extracted")

    # --- 3. MERGE ---
    src_files = [rasterio.open(fp) for fp in extracted_tifs]

    mosaic, out_trans = merge(src_files)

    # --- 4. CLEAN NODATA ---
    mosaic = mosaic.astype(np.float32)

    # UK LiDAR nodata fix
    mosaic[mosaic < -1e30] = SAFE_NODATA
    mosaic[np.isnan(mosaic)] = SAFE_NODATA

    # --- 5. WRITE OUTPUT ---
    out_meta = src_files[0].meta.copy()
    out_meta.update({
        "driver": "GTiff",
        "height": mosaic.shape[1],
        "width": mosaic.shape[2],
        "transform": out_trans,
        "nodata": SAFE_NODATA,
        "dtype": "float32",
        "compress": "lzw"
    })

    with rasterio.open(OUTPUT_FILE, "w", **out_meta) as dest:
        dest.write(mosaic)

    # --- 6. CLEANUP ---
    for src in src_files:
        src.close()

    for f in extracted_tifs:
        try:
            os.remove(f)
        except:
            pass

if __name__ == "__main__":
    main()
