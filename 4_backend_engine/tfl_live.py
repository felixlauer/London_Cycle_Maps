"""
Shared module: live TfL disruption data (fetch, spatial match, lookup table).
Imported by app.py and app_debug.py. Call init(G) once at startup to build
the edge spatial index; call update_disruptions() to fetch + match.
Matching uses alignment ratio (>= 50% edge length in zone) and angularity for short edges.
When changing, update 0_documentation/APP_MAIN.md and APP_DEBUG.md.
"""
import os
import json
import math
import time
import logging
from datetime import datetime, timezone

import requests
from shapely.wkt import loads as load_wkt
from shapely.geometry import LineString, Point, Polygon, shape as geojson_to_shapely
from shapely.strtree import STRtree
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

log = logging.getLogger("tfl_live")
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
TFL_API_URL = "https://api.tfl.gov.uk/Road/all/Disruption"
TFL_APP_KEY = os.environ.get("TFL_APP_KEY", "")
API_TIMEOUT_S = 15

# Matching refinement (aligned with 3_pipeline/tag_tfl_routes.py)
POINT_BUFFER_DEG = 0.0001          # ~11 m at London — only edges with BOTH endpoints within this (tighter)
LINE_BUFFER_DEG = 0.0001           # ~10 m corridor for LineString/MultiLineString
POLYGON_EDGE_BUFFER_DEG = 0.00005 # ~5 m tolerance for polygon boundary
ALIGNMENT_THRESHOLD = 0.5          # >= 50% of edge length must lie in disruption zone (tag_tfl_routes)
MAX_ANGLE_DEG = 45.0               # angularity: edge must be roughly parallel to disruption line
ANGULAR_MAX_LENGTH_DEG = 0.00018   # ~20 m at London; angularity check only for shorter edges

SEVERITY_MULTIPLIERS = {
    "minimal": 1.1,
    "low": 1.15,
    "moderate": 1.3,
    "serious": 1.5,
    "severe": 2.0,
}
# Lower penalty for Recurring Works (planned/repeating works, less urgent to avoid)
RECURRING_WORKS_MULTIPLIER = 1.08

# ---------------------------------------------------------------------------
# Module-level state (each process gets its own copy)
# ---------------------------------------------------------------------------
_edge_tree = None       # STRtree
_edge_geoms = []        # parallel list of Shapely LineStrings
_edge_keys = []         # parallel list of (u, v) tuples
_graph_ref = None       # reference to G for geometry helpers

TFL_LIVE_LOOKUP = {}    # {(u, v): disruption_dict}
TFL_LIVE_VIS_CACHE = [] # [{id, p, b, type, severity, description}, ...]
TFL_RAW_GEOM_CACHE = [] # [{ type, coordinates, b, disruption_id, severity, category }, ...] — ground truth from TfL
_last_update = None     # datetime
_last_error = None      # str | None
_disruption_count = 0
_raw_disruptions = []   # last raw JSON for inspector enrichment
_raw_disruptions_by_id = {}  # id -> full disruption dict for lookup by click


def init(G):
    """Build STRtree from all edge geometries. Call once at startup."""
    global _edge_tree, _edge_geoms, _edge_keys, _graph_ref
    _graph_ref = G
    t0 = time.time()
    geoms = []
    keys = []
    for u, v, data in G.edges(data=True):
        wkt = data.get("geometry")
        if wkt:
            try:
                line = load_wkt(wkt)
            except Exception:
                p1 = (float(G.nodes[u]["x"]), float(G.nodes[u]["y"]))
                p2 = (float(G.nodes[v]["x"]), float(G.nodes[v]["y"]))
                line = LineString([p1, p2])
        else:
            p1 = (float(G.nodes[u]["x"]), float(G.nodes[u]["y"]))
            p2 = (float(G.nodes[v]["x"]), float(G.nodes[v]["y"]))
            line = LineString([p1, p2])
        geoms.append(line)
        keys.append((u, v))
    _edge_geoms = geoms
    _edge_keys = keys
    _edge_tree = STRtree(geoms)
    elapsed = time.time() - t0
    log.info("tfl_live: STRtree built from %d edges in %.1f s", len(geoms), elapsed)


# ---------------------------------------------------------------------------
# TfL API fetch
# ---------------------------------------------------------------------------

def _fetch_tfl_json():
    """GET /Road/all/Disruption. Returns (list[dict], error_str|None)."""
    params = {"stripContent": "false"}
    if TFL_APP_KEY:
        params["app_key"] = TFL_APP_KEY
    try:
        resp = requests.get(TFL_API_URL, params=params, timeout=API_TIMEOUT_S)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            return [], "Unexpected response type: " + type(data).__name__
        return data, None
    except requests.RequestException as exc:
        return [], str(exc)


# ---------------------------------------------------------------------------
# Geometry parsing
# TfL per disruption can return: (1) roadDisruptionLines[] with multiLineString WKT (line geometry),
# (2) geometry = GeoJSON Polygon/MultiPolygon (area "boxes"), (3) geography = GeoJSON Point (one coord),
# (4) point = "[lon,lat]" string (one coord). Often only (3) or (4); (2) when present is the exact area.
# ---------------------------------------------------------------------------

def _parse_disruption_geometries(disruption):
    """Return list of Shapely geometries for a single disruption (priority order)."""
    geoms = []

    # 1. roadDisruptionLines (WKT MultiLineString / LineString)
    for rdl in disruption.get("roadDisruptionLines") or []:
        mls = rdl.get("multiLineString") or ""
        if mls.strip():
            try:
                geoms.append(load_wkt(mls))
            except Exception:
                pass

    if geoms:
        return geoms

    # 2. geometry field (GeoJSON Polygon / MultiPolygon)
    geo_field = disruption.get("geometry")
    if isinstance(geo_field, dict) and geo_field.get("type"):
        try:
            geoms.append(geojson_to_shapely(geo_field))
        except Exception:
            pass

    if geoms:
        return geoms

    # 3. geography field (GeoJSON Point) or point string "[lon,lat]"
    geog = disruption.get("geography")
    if isinstance(geog, dict) and geog.get("type"):
        try:
            geoms.append(geojson_to_shapely(geog))
        except Exception:
            pass

    if not geoms:
        pt_str = disruption.get("point") or ""
        pt_str = pt_str.strip().strip("[]")
        if pt_str:
            try:
                parts = [float(x) for x in pt_str.split(",")]
                if len(parts) == 2:
                    geoms.append(Point(parts[0], parts[1]))
            except Exception:
                pass

    return geoms


def _get_all_geometry_sources(disruption):
    """Return list of (source_name, Shapely_geom) for every geometry TfL provides.
    Used for ground-truth display: show exactly what TfL parsed (all points, all polygons/lines).
    source_name: 'roadDisruptionLines' | 'geometry' | 'geography' | 'point'."""
    out = []

    for rdl in disruption.get("roadDisruptionLines") or []:
        mls = rdl.get("multiLineString") or ""
        if mls.strip():
            try:
                out.append(("roadDisruptionLines", load_wkt(mls)))
            except Exception:
                pass

    geo_field = disruption.get("geometry")
    if isinstance(geo_field, dict) and geo_field.get("type"):
        try:
            out.append(("geometry", geojson_to_shapely(geo_field)))
        except Exception:
            pass

    geog = disruption.get("geography")
    if isinstance(geog, dict) and geog.get("type"):
        try:
            out.append(("geography", geojson_to_shapely(geog)))
        except Exception:
            pass

    pt_str = (disruption.get("point") or "").strip().strip("[]")
    if pt_str:
        try:
            parts = [float(x) for x in pt_str.split(",")]
            if len(parts) == 2:
                out.append(("point", Point(parts[0], parts[1])))
        except Exception:
            pass

    return out


def _count_disruption_sources(active):
    """Return counts per geometry source and polygon count for debug printout."""
    by_source = {"roadDisruptionLines": 0, "geometry": 0, "geography": 0, "point": 0}
    polygon_count = 0
    point_only_count = 0
    for d in active:
        sources = _get_all_geometry_sources(d)
        seen = set()
        has_polygon = False
        for name, geom in sources:
            if name not in seen:
                by_source[name] = by_source.get(name, 0) + 1
                seen.add(name)
            if geom and geom.geom_type in ("Polygon", "MultiPolygon"):
                has_polygon = True
        if has_polygon:
            polygon_count += 1
        if sources and all(g.geom_type == "Point" for _, g in sources):
            point_only_count += 1
    return by_source, polygon_count, point_only_count


def _classify_disruption(disruption):
    """Return (type_str, severity_str, severity_multiplier, description)."""
    has_closure = bool(disruption.get("hasClosures"))
    is_diversion = False
    for rdl in disruption.get("roadDisruptionLines") or []:
        if rdl.get("isDiversion"):
            is_diversion = True
            break

    if has_closure:
        dtype = "closure"
    elif is_diversion:
        dtype = "diversion"
    else:
        cat = (disruption.get("category") or "").strip()
        if cat == "Works":
            dtype = "works"
        elif cat in ("Collisions", "Emergency service incidents",
                     "Traffic Incidents", "Network delays"):
            dtype = "incident"
        else:
            dtype = "other"

    severity = (disruption.get("severity") or "Moderate").strip()
    status = (disruption.get("status") or "").strip()
    if status == "Recurring Works":
        sev_mult = RECURRING_WORKS_MULTIPLIER
    else:
        sev_mult = SEVERITY_MULTIPLIERS.get(severity.lower(), 1.3)
    description = (disruption.get("comments") or disruption.get("location") or "")[:200]

    return dtype, severity, sev_mult, description, has_closure, is_diversion


# ---------------------------------------------------------------------------
# Spatial matching (disruption geometry → graph edges)
# Uses alignment ratio (>= 50% edge length in zone) and angularity for short edges.
# ---------------------------------------------------------------------------

def _angle_deg_between_lines(line_a, line_b):
    """Angle in [0, 180] between directions of two LineStrings (first-to-last bearing)."""
    coords_a = list(line_a.coords)
    coords_b = list(line_b.coords)
    if len(coords_a) < 2 or len(coords_b) < 2:
        return 0.0
    dx_a = coords_a[-1][0] - coords_a[0][0]
    dy_a = coords_a[-1][1] - coords_a[0][1]
    dx_b = coords_b[-1][0] - coords_b[0][0]
    dy_b = coords_b[-1][1] - coords_b[0][1]
    len_a = math.hypot(dx_a, dy_a)
    len_b = math.hypot(dx_b, dy_b)
    if len_a < 1e-12 or len_b < 1e-12:
        return 0.0
    dot = dx_a * dx_b + dy_a * dy_b
    cos_a = max(-1.0, min(1.0, dot / (len_a * len_b)))
    return math.degrees(math.acos(cos_a))


def _is_roughly_parallel(edge_geom, ref_line, max_angle_deg=MAX_ANGLE_DEG):
    """True if edge direction is within max_angle_deg of parallel/anti-parallel to ref line."""
    angle = _angle_deg_between_lines(edge_geom, ref_line)
    dev = min(angle, 180.0 - angle)
    return dev <= max_angle_deg


def _match_geometry_to_edges(geom):
    """Return set of indices into _edge_geoms that match the disruption geometry.
    Uses alignment ratio (>= 50% edge length in zone) and angularity for short edges."""
    if _edge_tree is None:
        return set()

    matched = set()

    if geom.geom_type == "Point":
        # Match any edge that intersects the point buffer (junction-style: all arms at the point)
        buffered = geom.buffer(POINT_BUFFER_DEG)
        candidate_idxs = _edge_tree.query(buffered)
        for idx in candidate_idxs:
            edge_geom = _edge_geoms[idx]
            if not edge_geom.intersects(buffered):
                continue
            matched.add(idx)

    elif geom.geom_type in ("LineString", "MultiLineString"):
        buffered = geom.buffer(LINE_BUFFER_DEG)
        ref_line = geom if geom.geom_type == "LineString" else None  # angularity only for single LineString
        candidate_idxs = _edge_tree.query(buffered)
        for idx in candidate_idxs:
            edge_geom = _edge_geoms[idx]
            edge_len = edge_geom.length
            if edge_len < 1e-12:
                continue
            try:
                overlap = edge_geom.intersection(buffered)
                overlap_len = overlap.length if overlap and not overlap.is_empty else 0.0
            except Exception:
                overlap_len = 0.0
            if overlap_len / edge_len < ALIGNMENT_THRESHOLD:
                continue
            if ref_line is not None and edge_len < ANGULAR_MAX_LENGTH_DEG and not _is_roughly_parallel(edge_geom, ref_line):
                continue
            matched.add(idx)

    elif geom.geom_type in ("Polygon", "MultiPolygon"):
        # Match edges where >= 50% of edge length lies inside the polygon
        try:
            zone = geom.buffer(POLYGON_EDGE_BUFFER_DEG) if geom.is_valid else geom
        except Exception:
            zone = geom
        candidate_idxs = _edge_tree.query(geom)
        for idx in candidate_idxs:
            edge_geom = _edge_geoms[idx]
            if not edge_geom.intersects(zone):
                continue
            edge_len = edge_geom.length
            if edge_len < 1e-12:
                matched.add(idx)
                continue
            try:
                overlap = edge_geom.intersection(geom)
                overlap_len = overlap.length if overlap and not overlap.is_empty else 0.0
            except Exception:
                overlap_len = edge_len
            if overlap_len / edge_len >= ALIGNMENT_THRESHOLD:
                matched.add(idx)
    else:
        # Other geometry: match any edge that intersects the buffer (same as Point)
        buffered = geom.buffer(POINT_BUFFER_DEG)
        candidate_idxs = _edge_tree.query(buffered)
        for idx in candidate_idxs:
            edge_geom = _edge_geoms[idx]
            if edge_geom.intersects(buffered):
                matched.add(idx)

    return matched


def _edge_coords_latlon(idx):
    """Return [[lat, lon], ...] for edge at index (for vis cache)."""
    line = _edge_geoms[idx]
    return [[y, x] for x, y in line.coords]


def _make_bounds(coords):
    lats = [p[0] for p in coords]
    lons = [p[1] for p in coords]
    return (min(lats), max(lats), min(lons), max(lons))


def _shapely_to_latlon_coords(geom):
    """Convert Shapely (x,y)=(lon,lat) to list of [lat, lon] or list of lists for frontend."""
    if geom is None or geom.is_empty:
        return None
    if geom.geom_type == "Point":
        return [geom.y, geom.x]
    if geom.geom_type == "LineString":
        return [[y, x] for x, y in geom.coords]
    if geom.geom_type == "MultiLineString":
        return [[[y, x] for x, y in line.coords] for line in geom.geoms]
    if geom.geom_type == "Polygon":
        exterior = [[y, x] for x, y in geom.exterior.coords]
        return exterior
    if geom.geom_type == "MultiPolygon":
        return [[[y, x] for x, y in poly.exterior.coords] for poly in geom.geoms]
    return None


def _geom_bounds(geom):
    """Return (min_lat, max_lat, min_lon, max_lon) for a Shapely geometry."""
    try:
        b = geom.bounds
        if b is None or len(b) < 4:
            return None
        # Shapely bounds: (minx, miny, maxx, maxy) = (min_lon, min_lat, max_lon, max_lat)
        return (b[1], b[3], b[0], b[2])
    except Exception:
        return None


def _geom_to_raw_features(geom, disruption_id, severity, category, dtype, source_name="", sub_idx=0):
    """Convert one Shapely geometry to list of raw feature dicts for ground-truth overlay.
    Each feature: { type: 'point'|'line'|'polygon', coordinates, b, disruption_id, severity, category, source }."""
    out = []
    if geom is None or geom.is_empty:
        return out
    coords = _shapely_to_latlon_coords(geom)
    if coords is None:
        return out
    b = _geom_bounds(geom)
    if b is None:
        return out
    meta = {"b": b, "disruption_id": disruption_id, "severity": severity, "category": category, "disruption_type": dtype, "source": source_name}
    if geom.geom_type == "Point":
        out.append({"type": "point", "coordinates": coords, **meta})
    elif geom.geom_type == "LineString":
        out.append({"type": "line", "coordinates": coords, **meta})
    elif geom.geom_type == "MultiLineString":
        for i, line in enumerate(coords):
            if len(line) >= 2:
                line_b = (min(p[0] for p in line), max(p[0] for p in line), min(p[1] for p in line), max(p[1] for p in line))
                out.append({"type": "line", "coordinates": line, "b": line_b, **meta})
    elif geom.geom_type == "Polygon":
        if len(coords) >= 3:
            out.append({"type": "polygon", "coordinates": coords, **meta})
    elif geom.geom_type == "MultiPolygon":
        for i, ring in enumerate(coords):
            if len(ring) >= 3:
                ring_b = (min(p[0] for p in ring), max(p[0] for p in ring), min(p[1] for p in ring), max(p[1] for p in ring))
                out.append({"type": "polygon", "coordinates": ring, "b": ring_b, **meta})
    return out


# ---------------------------------------------------------------------------
# Time-window filter: only use disruptions when current time is between
# currentUpdateDateTime and endDateTime (if those fields are present).
# ---------------------------------------------------------------------------

def _parse_tfl_datetime(s):
    """Parse TfL ISO datetime string (e.g. '2026-03-02T09:47:41Z'). Return datetime in UTC or None."""
    if not s or not isinstance(s, str) or not s.strip():
        return None
    s = s.strip()
    try:
        # Handle Z suffix and optional fractional seconds
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _disruption_in_time_window(d):
    """True if current time (UTC) is between currentUpdateDateTime and endDateTime when present.
    If a bound is missing, that bound is not enforced."""
    now = datetime.now(timezone.utc)
    end = _parse_tfl_datetime(d.get("endDateTime"))
    if end is not None and now > end:
        return False
    current_update = _parse_tfl_datetime(d.get("currentUpdateDateTime"))
    if current_update is not None and now < current_update:
        return False
    return True


# ---------------------------------------------------------------------------
# Main update function
# ---------------------------------------------------------------------------

def update_disruptions():
    """Fetch TfL API, parse, match to edges, populate lookup + vis cache and raw ground-truth cache.
    Returns (success: bool, message: str, count: int)."""
    global TFL_LIVE_LOOKUP, TFL_LIVE_VIS_CACHE, TFL_RAW_GEOM_CACHE
    global _last_update, _last_error, _disruption_count, _raw_disruptions, _raw_disruptions_by_id

    if _edge_tree is None:
        msg = "STRtree not built — call init(G) first"
        _last_error = msg
        return False, msg, 0

    raw, err = _fetch_tfl_json()
    if err:
        _last_error = err
        log.warning("tfl_live: fetch failed: %s", err)
        return False, err, 0

    active = [d for d in raw
              if (d.get("status") or "").strip() in ("Active", "Active Long Term", "Recurring Works")
              and _disruption_in_time_window(d)]

    # Debug: breakdown by how TfL reports geometry (coordinate vs complex)
    by_source, polygon_count, point_only_count = _count_disruption_sources(active)
    log.info(
        "tfl_live: TfL reports %d active disruptions — by source: roadDisruptionLines=%d, geometry(polygon/area)=%d, geography(point)=%d, point(string)=%d; point-only=%d",
        len(active), by_source["roadDisruptionLines"], by_source["geometry"],
        by_source["geography"], by_source["point"], point_only_count,
    )
    if polygon_count > 0:
        log.info(
            "tfl_live: TfL returns area polygons (boxes) for %d disruption(s); these are drawn exactly as returned (not in frontend message).",
            polygon_count,
        )
    log.info(
        "tfl_live: Road type: TfL disruption API does not expose road type or road class; no road-type filter applied.",
    )

    _raw_disruptions = active
    _raw_disruptions_by_id = {str(d.get("id") or "unknown"): d for d in active}
    new_lookup = {}
    new_vis = []
    new_raw = []
    matched_disruptions = 0
    total_matched_edges = 0

    for disruption in active:
        did = disruption.get("id") or "unknown"
        dtype, severity, sev_mult, description, has_closure, is_diversion = \
            _classify_disruption(disruption)
        category = (disruption.get("category") or "").strip()

        # Matching: use first available geometry (priority order)
        geoms = _parse_disruption_geometries(disruption)
        if not geoms:
            continue

        # Ground truth: export every geometry TfL provided (all points, all polygons/lines)
        for source_name, geom in _get_all_geometry_sources(disruption):
            try:
                for feat in _geom_to_raw_features(geom, did, severity, category, dtype, source_name=source_name):
                    new_raw.append(feat)
            except Exception as exc:
                log.warning("tfl_live: raw geom export error for %s (%s): %s", did, source_name, exc)

        edge_indices = set()
        for geom in geoms:
            try:
                edge_indices |= _match_geometry_to_edges(geom)
            except Exception as exc:
                log.warning("tfl_live: geometry match error for %s: %s", did, exc)

        if not edge_indices:
            continue

        matched_disruptions += 1
        total_matched_edges += len(edge_indices)

        rec = {
            "has_closure": has_closure,
            "is_diversion": is_diversion,
            "category": category,
            "severity": severity,
            "severity_multiplier": sev_mult,
            "description": description,
            "disruption_id": did,
        }

        for idx in edge_indices:
            key = _edge_keys[idx]
            existing = new_lookup.get(key)
            if existing is None or sev_mult > existing["severity_multiplier"]:
                new_lookup[key] = rec

            coords = _edge_coords_latlon(idx)
            if coords and len(coords) >= 2:
                new_vis.append({
                    "id": f"tfl-live-{did}-{idx}",
                    "p": coords,
                    "b": _make_bounds(coords),
                    "type": dtype,
                    "severity": severity,
                    "category": category,
                    "description": description,
                })

    TFL_LIVE_LOOKUP = new_lookup
    TFL_LIVE_VIS_CACHE = new_vis
    TFL_RAW_GEOM_CACHE = new_raw
    _last_update = datetime.now(timezone.utc)
    _last_error = None
    _disruption_count = matched_disruptions

    msg = (f"Fetched {len(active)} active disruptions, "
           f"{matched_disruptions} matched to {total_matched_edges} edges")
    log.info("tfl_live: %s", msg)
    return True, msg, matched_disruptions


# ---------------------------------------------------------------------------
# Public query API (also used by live_disruptions / tomtom_live for shared STRtree)
# ---------------------------------------------------------------------------

def match_geometry_to_edges(geom):
    """Return set of edge indices matching the given Shapely geometry. Used by TomTom matcher."""
    return _match_geometry_to_edges(geom)


def get_edge_keys():
    """Return list of (u, v) tuples parallel to _edge_geoms. Used by TomTom matcher."""
    return _edge_keys


def get_edge_coords_latlon(idx):
    """Return [[lat, lon], ...] for edge at index. Used by TomTom vis cache."""
    return _edge_coords_latlon(idx)


def get_edge_disruption(u, v):
    """O(1) lookup. Returns disruption dict or None."""
    return TFL_LIVE_LOOKUP.get((u, v))


def get_vis_segments_in_bbox(min_lat, max_lat, min_lon, max_lon, limit=20000):
    """Return disruption vis segments within viewport."""
    in_bbox = [
        s for s in TFL_LIVE_VIS_CACHE
        if (s["b"][0] < max_lat and s["b"][1] > min_lat and
            s["b"][2] < max_lon and s["b"][3] > min_lon)
    ]
    limit_reached = False
    if len(in_bbox) > limit:
        center_lat = (min_lat + max_lat) / 2.0
        center_lon = (min_lon + max_lon) / 2.0
        in_bbox.sort(key=lambda s: (
            ((s["b"][0] + s["b"][1]) / 2 - center_lat) ** 2 +
            ((s["b"][2] + s["b"][3]) / 2 - center_lon) ** 2))
        in_bbox = in_bbox[:limit]
        limit_reached = True

    out = []
    for s in in_bbox:
        out.append({
            "id": s["id"],
            "p": s["p"],
            "type": s["type"],
            "severity": s["severity"],
            "category": s.get("category", ""),
            "description": s["description"],
        })
    return out, limit_reached


def _raw_feature_to_shapely(feat):
    """Build Shapely geometry from a TFL_RAW_GEOM_CACHE feature (coordinates are [lat, lon])."""
    if not feat or not feat.get("coordinates"):
        return None
    coords = feat["coordinates"]
    t = (feat.get("type") or "").strip().lower()
    try:
        if t == "point":
            if isinstance(coords[0], (int, float)):
                return Point(coords[1], coords[0])  # (lon, lat)
            return None
        if t == "line":
            if len(coords) < 2:
                return None
            return LineString([(c[1], c[0]) for c in coords])
        if t == "polygon":
            if len(coords) < 3:
                return None
            return Polygon([(c[1], c[0]) for c in coords])
    except Exception:
        return None
    return None


# Default tolerance for click hit-test (degrees); slightly larger than point marker
TFL_CLICK_TOLERANCE_DEG = 0.00025


def get_disruptions_at(lat, lon, tolerance_deg=None):
    """Return list of full TfL disruption dicts whose geometry is at or near (lat, lon).
    Uses TFL_RAW_GEOM_CACHE for hit-testing with a buffered point (slightly larger margin)."""
    if tolerance_deg is None:
        tolerance_deg = TFL_CLICK_TOLERANCE_DEG
    click_point = Point(lon, lat).buffer(tolerance_deg)
    seen_ids = set()
    out = []
    for feat in TFL_RAW_GEOM_CACHE:
        geom = _raw_feature_to_shapely(feat)
        if geom is None or geom.is_empty:
            continue
        try:
            if not geom.intersects(click_point):
                continue
        except Exception:
            continue
        did = feat.get("disruption_id") or "unknown"
        if did in seen_ids:
            continue
        seen_ids.add(did)
        full = _raw_disruptions_by_id.get(did)
        if full is not None:
            out.append(full)

    # Also hit-test matched segments (coloured polylines) so clicking on the road shows the disruption
    for s in TFL_LIVE_VIS_CACHE:
        coords = s.get("p") or []
        if len(coords) < 2:
            continue
        try:
            line = LineString([(c[1], c[0]) for c in coords])
            if not line.intersects(click_point):
                continue
        except Exception:
            continue
        # id format: "tfl-live-{disruption_id}-{edge_idx}"
        parts = (s.get("id") or "").split("-")
        if len(parts) >= 4:
            did = "-".join(parts[2:-1])
        else:
            did = s.get("disruption_id") or "unknown"
        if did in seen_ids:
            continue
        seen_ids.add(did)
        full = _raw_disruptions_by_id.get(did)
        if full is not None:
            out.append(full)
    return out


def get_raw_geometries_in_bbox(min_lat, max_lat, min_lon, max_lon, limit=5000):
    """Return TfL ground-truth geometries (points, lines, polygons) within viewport.
    For overlay: exact coordinates from TfL API."""
    in_bbox = [
        f for f in TFL_RAW_GEOM_CACHE
        if (f["b"][0] < max_lat and f["b"][1] > min_lat and
            f["b"][2] < max_lon and f["b"][3] > min_lon)
    ]
    limit_reached = False
    if len(in_bbox) > limit:
        center_lat = (min_lat + max_lat) / 2.0
        center_lon = (min_lon + max_lon) / 2.0
        in_bbox.sort(key=lambda f: (
            ((f["b"][0] + f["b"][1]) / 2 - center_lat) ** 2 +
            ((f["b"][2] + f["b"][3]) / 2 - center_lon) ** 2))
        in_bbox = in_bbox[:limit]
        limit_reached = True
    out = []
    for f in in_bbox:
        out.append({
            "type": f["type"],
            "coordinates": f["coordinates"],
            "disruption_id": f.get("disruption_id", ""),
            "severity": f.get("severity", ""),
            "category": f.get("category", ""),
            "disruption_type": f.get("disruption_type", ""),
            "source": f.get("source", ""),
        })
    return out, limit_reached


def get_status():
    """Return status dict for /admin/tfl_status."""
    return {
        "loaded": len(TFL_LIVE_LOOKUP) > 0,
        "edge_count": len(TFL_LIVE_LOOKUP),
        "disruption_count": _disruption_count,
        "last_update": _last_update.isoformat() if _last_update else None,
        "error": _last_error,
    }
