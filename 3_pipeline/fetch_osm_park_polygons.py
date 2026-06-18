"""
Build London park polygon cache for the attraction pipeline.

Preferred: read local OSM PBF (fast, no Overpass timeouts).
Fallback: Overpass API (shared servers — can 504 under load).

  python fetch_osm_park_polygons.py
  python fetch_osm_park_polygons.py --source pbf --pbf ../1_data/greater-london-260106.osm.pbf
  python fetch_osm_park_polygons.py --source overpass

Output: 1_data/osm_park_polygons.geojson

Tags: leisure=park, landuse=recreation_ground (not leisure=garden).

When changing filters, update 0_documentation/GRAPH.md.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "1_data"))
OUTPUT_PATH = os.path.join(DATA_DIR, "osm_park_polygons.geojson")

PBF_CANDIDATES = [
    os.path.join(DATA_DIR, "greater-london-260106.osm.pbf"),
    os.path.join(DATA_DIR, "london.pbf"),
    os.path.join(DATA_DIR, "london.osm.pbf"),
]

# south, west, north, east
LONDON_BBOX = (51.2868, -0.5104, 51.6918, 0.3340)
# pyogrio/geopandas bbox: minx, miny, maxx, maxy
READ_BBOX = (LONDON_BBOX[1], LONDON_BBOX[0], LONDON_BBOX[3], LONDON_BBOX[2])

OVERPASS_ENDPOINTS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]

CLIENT_TIMEOUT_SEC = 600
MAX_ATTEMPTS_PER_QUERY = 4
RETRY_BACKOFF_SEC = (15, 30, 60)

QUERY_TEMPLATES = [
    (
        "leisure=park",
        """
[out:json][timeout:240];
(
  way["leisure"="park"]({south},{west},{north},{east});
  relation["leisure"="park"]({south},{west},{north},{east});
);
out geom;
""",
    ),
    (
        "landuse=recreation_ground",
        """
[out:json][timeout:240];
(
  way["landuse"="recreation_ground"]({south},{west},{north},{east});
  relation["landuse"="recreation_ground"]({south},{west},{north},{east});
);
out geom;
""",
    ),
]

EXCLUDED_ACCESS = frozenset({"private", "no", "customers"})
ACCESS_RE = re.compile(r'"access"=>"([^"]+)"', re.IGNORECASE)
OPENING_HOURS_RE = re.compile(r'"opening_hours"=>"([^"]+)"', re.IGNORECASE)

REQUEST_HEADERS = {
    "User-Agent": "LondonCycleMaps/1.0 (park polygon fetch; local pipeline)",
    "Accept": "application/json",
}


def _configure_proj() -> str | None:
    """
    Point PROJ at the active Python env (conda), not PostgreSQL PostGIS on Windows.

    PostGIS often ships an older proj.db; if it wins, geopandas/pyogrio fail with
    DATABASE.LAYOUT.VERSION.MINOR errors. Call before importing geopandas.
    """
    # Prefer conda/proj inside this Python env (override PostgreSQL PostGIS PROJ_LIB on PATH).
    prefixes = [p for p in (sys.prefix, os.environ.get("CONDA_PREFIX", "")) if p]
    subpaths = (
        os.path.join("Library", "share", "proj"),
        os.path.join("share", "proj"),
    )
    for prefix in prefixes:
        for sub in subpaths:
            path = os.path.join(prefix, sub)
            proj_db = os.path.join(path, "proj.db")
            if os.path.isfile(proj_db):
                os.environ["PROJ_LIB"] = path
                os.environ["PROJ_DATA"] = path
                print(f"  PROJ database: {path}")
                return path

    for key in ("PROJ_LIB", "PROJ_DATA"):
        existing = os.environ.get(key)
        if existing and os.path.isfile(os.path.join(existing, "proj.db")):
            os.environ["PROJ_LIB"] = existing
            os.environ["PROJ_DATA"] = existing
            return existing

    print(
        "  WARNING: Could not locate conda PROJ database. If you see CRS errors, run in PowerShell:\n"
        '    $env:PROJ_LIB="$env:CONDA_PREFIX\\Library\\share\\proj"\n'
        '    $env:PROJ_DATA=$env:PROJ_LIB'
    )
    return None


def _resolve_pbf(explicit: str | None) -> str | None:
    if explicit:
        path = os.path.normpath(explicit)
        return path if os.path.isfile(path) else None
    for path in PBF_CANDIDATES:
        if os.path.isfile(path):
            return path
    return None


def _access_value(row) -> str:
    if hasattr(row, "get"):
        direct = row.get("access")
        if direct is not None and str(direct).strip():
            return str(direct).strip().lower()
        other = row.get("other_tags") or ""
    else:
        direct = getattr(row, "access", None) if "access" in row.index else None
        if direct is not None and str(direct).strip():
            return str(direct).strip().lower()
        other = getattr(row, "other_tags", "") or ""
    m = ACCESS_RE.search(str(other))
    return m.group(1).strip().lower() if m else ""


def _opening_hours_value(row) -> str:
    if hasattr(row, "get"):
        direct = row.get("opening_hours")
        if direct is not None and str(direct).strip():
            return str(direct).strip()
        other = row.get("other_tags") or ""
    else:
        direct = getattr(row, "opening_hours", None) if "opening_hours" in row.index else None
        if direct is not None and str(direct).strip():
            return str(direct).strip()
        other = getattr(row, "other_tags", "") or ""
    m = OPENING_HOURS_RE.search(str(other))
    return m.group(1).strip() if m else ""


def _gdf_to_features(gdf) -> list[dict]:
    features = []
    skipped_access = 0
    skipped_geom = 0
    for _idx, row in gdf.iterrows():
        access = _access_value(row)
        if access in EXCLUDED_ACCESS:
            skipped_access += 1
            continue
        geom = row.geometry
        if geom is None or geom.is_empty or geom.geom_type not in ("Polygon", "MultiPolygon"):
            skipped_geom += 1
            continue
        osm_id = row.get("osm_id") or row.get("osm_way_id") or ""
        props = {
            "name": str(row.get("name") or "").strip(),
            "leisure": str(row.get("leisure") or "").strip(),
            "landuse": str(row.get("landuse") or "").strip(),
            "access": access,
            "opening_hours": _opening_hours_value(row),
            "osm_id": str(osm_id),
            "feature_id": f"way/{osm_id}" if osm_id else "",
        }
        features.append({
            "type": "Feature",
            "properties": props,
            "geometry": geom.__geo_interface__,
        })
    print(f"      -> {len(features)} features (skipped access={skipped_access}, geom={skipped_geom})")
    return features


def fetch_from_pbf(pbf_path: str, no_simplify: bool) -> list[dict]:
    _configure_proj()
    import geopandas as gpd

    print(f"1. Reading multipolygons from PBF: {pbf_path}")
    t0 = time.perf_counter()
    gdf = gpd.read_file(pbf_path, layer="multipolygons", bbox=READ_BBOX)
    print(f"   -> {len(gdf):,} multipolygons in bbox ({time.perf_counter() - t0:.1f}s)")

    leisure = gdf["leisure"].fillna("").astype(str).str.strip()
    landuse = gdf["landuse"].fillna("").astype(str).str.strip()
    mask = (leisure == "park") | (landuse == "recreation_ground")
    parks = gdf.loc[mask].copy()
    print(f"   -> {len(parks):,} with leisure=park or landuse=recreation_ground")

    features = _gdf_to_features(parks)
    if not features:
        raise RuntimeError("No park features extracted from PBF")

    if not no_simplify:
        print("2. Simplifying geometries...")
        features = _simplify_features(features)
    return features


def _bbox_query(template: str, bbox: tuple[float, float, float, float]) -> str:
    south, west, north, east = bbox
    return template.format(south=south, west=west, north=north, east=east).strip()


def _request_overpass(query: str, endpoints: list[str], timeout: int) -> dict:
    last_exc: Exception | None = None
    for endpoint in endpoints:
        url = endpoint.rstrip("/")
        if not url.endswith("/interpreter"):
            url = url + "/api/interpreter" if "/api/" not in url else url
        for attempt in range(MAX_ATTEMPTS_PER_QUERY):
            if attempt > 0:
                wait = RETRY_BACKOFF_SEC[min(attempt - 1, len(RETRY_BACKOFF_SEC) - 1)]
                print(f"      Retry in {wait}s (attempt {attempt + 1}/{MAX_ATTEMPTS_PER_QUERY})...")
                time.sleep(wait)
            try:
                resp = requests.post(url, data=query, headers=REQUEST_HEADERS, timeout=timeout)
                if resp.status_code in (406, 405):
                    resp = requests.get(
                        url, params={"data": query}, headers=REQUEST_HEADERS, timeout=timeout
                    )
                if resp.status_code in (429, 502, 503, 504):
                    print(f"      {endpoint}: HTTP {resp.status_code} — server busy or query too heavy")
                    last_exc = requests.HTTPError(f"{resp.status_code} from {endpoint}", response=resp)
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                last_exc = exc
                print(f"      {endpoint}: {exc}")
                continue
    raise RuntimeError(f"All Overpass endpoints failed. Last error: {last_exc}") from last_exc


def _way_to_coords(geometry: list) -> list | None:
    if not geometry:
        return None
    coords = [[float(n["lon"]), float(n["lat"])] for n in geometry if "lat" in n and "lon" in n]
    if len(coords) < 4:
        return None
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return coords


def _element_to_feature(el: dict) -> dict | None:
    tags = el.get("tags") or {}
    access = str(tags.get("access", "") or "").strip().lower()
    if access in EXCLUDED_ACCESS:
        return None
    geom_type = coordinates = None
    etype = el.get("type")
    if etype == "way" and el.get("geometry"):
        ring = _way_to_coords(el["geometry"])
        if ring:
            geom_type, coordinates = "Polygon", [ring]
    elif etype == "relation" and el.get("members"):
        outer_rings = []
        for mem in el["members"]:
            if mem.get("type") != "way" or mem.get("role") not in ("outer", ""):
                continue
            if "geometry" not in mem:
                continue
            ring = _way_to_coords(mem["geometry"])
            if ring:
                outer_rings.append(ring)
        if len(outer_rings) == 1:
            geom_type, coordinates = "Polygon", outer_rings
        elif len(outer_rings) > 1:
            geom_type, coordinates = "MultiPolygon", [[r] for r in outer_rings]
    if not geom_type:
        return None
    osm_id = el.get("id")
    etype_prefix = etype or "node"
    return {
        "type": "Feature",
        "properties": {
            "name": str(tags.get("name", "") or "").strip(),
            "leisure": str(tags.get("leisure", "") or ""),
            "landuse": str(tags.get("landuse", "") or ""),
            "access": access,
            "opening_hours": str(tags.get("opening_hours", "") or "").strip(),
            "osm_id": str(osm_id) if osm_id is not None else "",
            "feature_id": f"{etype_prefix}/{osm_id}" if osm_id is not None else "",
        },
        "geometry": {"type": geom_type, "coordinates": coordinates},
    }


def _overpass_to_features(data: dict) -> list[dict]:
    features = []
    skipped_access = skipped_geom = 0
    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        if str(tags.get("access", "") or "").strip().lower() in EXCLUDED_ACCESS:
            skipped_access += 1
            continue
        feat = _element_to_feature(el)
        if feat:
            features.append(feat)
        else:
            skipped_geom += 1
    if data.get("elements"):
        print(f"      -> {len(features)} features (skipped access={skipped_access}, geom={skipped_geom})")
    return features


def _merge_features(feature_lists: list[list[dict]]) -> list[dict]:
    by_id: dict[str, dict] = {}
    for batch in feature_lists:
        for feat in batch:
            fid = feat.get("properties", {}).get("feature_id") or feat.get("properties", {}).get("osm_id")
            by_id[str(fid) if fid else f"_anon_{len(by_id)}"] = feat
    return list(by_id.values())


def _simplify_features(features: list[dict], tolerance_m: float = 1.0) -> list[dict]:
    _configure_proj()
    import geopandas as gpd

    gdf = gpd.GeoDataFrame.from_features(features)
    try:
        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326")
        gdf = gdf.to_crs(epsg=27700)
        gdf["geometry"] = gdf.geometry.simplify(tolerance=tolerance_m, preserve_topology=True)
        gdf = gdf.to_crs(epsg=4326)
        mode = f"{tolerance_m}m (EPSG:27700)"
    except Exception as exc:
        print(f"  WARNING: PROJ simplify failed ({exc}); using ~{tolerance_m}m in degrees")
        tol_deg = tolerance_m / 111_000.0
        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326", allow_override=True)
        gdf["geometry"] = gdf.geometry.simplify(tolerance=tol_deg, preserve_topology=True)
        mode = f"~{tolerance_m}m (WGS84 degrees)"

    out = []
    for _idx, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        props = {k: row[k] for k in gdf.columns if k != "geometry"}
        out.append({
            "type": "Feature",
            "properties": {k: ("" if v is None else str(v)) for k, v in props.items()},
            "geometry": geom.__geo_interface__,
        })
    print(f"  Simplified {len(out)} features ({mode})")
    return out


def fetch_from_overpass(endpoints: list[str], timeout: int, no_simplify: bool) -> list[dict]:
    print("--- FETCH OSM PARK POLYGONS (Overpass) ---")
    print(f"  Bbox (S,W,N,E): {LONDON_BBOX}")
    print(f"  Mirrors: {', '.join(endpoints)}")
    print("  Note: Overpass is a shared service — 504 timeouts are intermittent, not a bug in this script.")

    all_batches: list[list[dict]] = []
    t_all = time.perf_counter()
    for i, (label, template) in enumerate(QUERY_TEMPLATES, 1):
        print(f"{i}. Querying {label}...")
        t0 = time.perf_counter()
        data = _request_overpass(_bbox_query(template, LONDON_BBOX), endpoints, timeout)
        print(f"   -> {len(data.get('elements', []))} elements in {time.perf_counter() - t0:.1f}s")
        all_batches.append(_overpass_to_features(data))
        if i < len(QUERY_TEMPLATES):
            time.sleep(2)
    print(f"   Total fetch time: {time.perf_counter() - t_all:.1f}s")

    print("2. Merging and deduplicating...")
    features = _merge_features(all_batches)
    if not features:
        raise RuntimeError("No park features extracted from Overpass")
    print(f"   -> {len(features)} unique features")

    if not no_simplify:
        print("3. Simplifying geometries...")
        features = _simplify_features(features)
    return features


def main() -> int:
    parser = argparse.ArgumentParser(description="Build osm_park_polygons.geojson from PBF or Overpass")
    parser.add_argument(
        "--source",
        choices=("auto", "pbf", "overpass"),
        default="auto",
        help="auto = local PBF if found, else Overpass (default: auto)",
    )
    parser.add_argument("--pbf", default=None, help="Path to .osm.pbf (default: 1_data/greater-london-*.osm.pbf)")
    parser.add_argument("--endpoint", action="append", dest="endpoints", help="Overpass URL (repeatable)")
    parser.add_argument("--timeout", type=int, default=CLIENT_TIMEOUT_SEC)
    parser.add_argument("--no-simplify", action="store_true")
    args = parser.parse_args()

    _configure_proj()
    os.makedirs(DATA_DIR, exist_ok=True)
    pbf_path = _resolve_pbf(args.pbf)
    use_pbf = args.source == "pbf" or (args.source == "auto" and pbf_path)

    try:
        if use_pbf:
            if not pbf_path:
                print("ERROR: --source pbf but no .osm.pbf found under 1_data/")
                return 1
            print("--- FETCH OSM PARK POLYGONS (local PBF) ---")
            features = fetch_from_pbf(pbf_path, args.no_simplify)
        else:
            if args.source == "auto":
                print("(No local PBF found — falling back to Overpass)")
            endpoints = args.endpoints or list(OVERPASS_ENDPOINTS)
            features = fetch_from_overpass(endpoints, args.timeout, args.no_simplify)
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        if not use_pbf and pbf_path:
            print(f"Tip: use local PBF instead: python fetch_osm_park_polygons.py --source pbf --pbf {pbf_path}")
        return 1

    collection = {"type": "FeatureCollection", "features": features}
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(collection, f, separators=(",", ":"))
    print(f"SUCCESS: Wrote {len(features)} features to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
