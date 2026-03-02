"""
TomTom Traffic Incident API (v5): fetch, spatial match to graph edges, lookup table.
Uses the same STRtree as tfl_live (call tfl_live.init(G) first). Populates TOMTOM_EDGES and TOMTOM_VIS.
Imported by live_disruptions; do not call from app.py directly for routing (use live_disruptions).
"""
import os
import logging
from datetime import datetime, timezone

import requests
from shapely.geometry import LineString
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

log = logging.getLogger("tomtom_live")
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# Configuration (same as 6_verification/tomtom_api_dummy_call.py)
# ---------------------------------------------------------------------------
TOMTOM_API_URL = "https://api.tomtom.com/traffic/services/5/incidentDetails"
TOMTOM_API_KEY = os.environ.get("TOMTOM_API_KEY", "")
LONDON_BBOX = "-0.510375,51.286760,0.334015,51.691874"
FIELDS = "{incidents{type,geometry{type,coordinates},properties{id,iconCategory,magnitudeOfDelay,events{description,code},startTime,endTime,length}}}"
API_TIMEOUT_S = 15

# Cluster A: Impassable
ICON_ROAD_CLOSED = 8
# Cluster B: Roadworks (surface penalty)
ICON_ROADWORKS = 9
# Cluster C: Jams/accidents (magnitude-based)
ICON_CLUSTER_C = {1, 6, 7, 12, 13, 14}  # Accident, Traffic Jam, Lane Closed, Detour, Cluster, Broken Down
# Cluster D: Weather/environmental (flat 1.3x)
ICON_CLUSTER_D = {2, 3, 4, 5, 10, 11}  # Fog, Dangerous Conditions, Rain, Ice, Wind, Flooding

MAGNITUDE_MULTIPLIERS = {0: 1.1, 1: 1.1, 2: 1.3, 3: 1.5, 4: 2.0}
ENVIRONMENTAL_MULTIPLIER = 1.3

# Default tolerance for click hit-test (degrees); same as TfL
TOMTOM_CLICK_TOLERANCE_DEG = 0.00025

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------
TOMTOM_EDGES = {}   # {(u, v): penalty_dict}
TOMTOM_VIS = []     # [{id, p, b, type, source: "tomtom", iconCategory, magnitudeOfDelay, description}, ...]
_raw_incidents_by_id = {}  # id -> full incident dict for left-click detail
_last_update = None
_last_error = None


def _fetch_tomtom_json():
    """GET TomTom incidentDetails. Returns (list of incident features, error_str|None)."""
    if not TOMTOM_API_KEY:
        return [], "TOMTOM_API_KEY not set"
    params = {
        "key": TOMTOM_API_KEY,
        "bbox": LONDON_BBOX,
        "fields": FIELDS,
        "language": "en-GB",
        "timeValidityFilter": "present",
    }
    try:
        resp = requests.get(TOMTOM_API_URL, params=params, timeout=API_TIMEOUT_S)
        resp.raise_for_status()
        data = resp.json()
        incidents = data.get("incidents") if isinstance(data, dict) else []
        if not isinstance(incidents, list):
            return [], "Unexpected incidents type"
        return incidents, None
    except requests.RequestException as exc:
        return [], str(exc)


def _classify_incident(inc):
    """Return (cluster_type, severity_mult, is_closed, temporary_bad_surface, environmental_hazard, description, iconCategory, magnitudeOfDelay)."""
    props = inc.get("properties") or {}
    icon = int(props.get("iconCategory", 0))
    mag = int(props.get("magnitudeOfDelay", 0))
    if mag not in MAGNITUDE_MULTIPLIERS:
        mag = min(MAGNITUDE_MULTIPLIERS.keys(), key=lambda k: abs(k - mag))
    desc_list = []
    for ev in props.get("events") or []:
        if isinstance(ev, dict) and ev.get("description"):
            desc_list.append(str(ev["description"]))
    description = " ".join(desc_list)[:200] if desc_list else ""

    if icon == ICON_ROAD_CLOSED:
        return "closure", 2.0, True, False, False, description, icon, mag
    if icon == ICON_ROADWORKS:
        return "roadworks", 1.2, False, True, False, description, icon, mag
    if icon in ICON_CLUSTER_C:
        mult = MAGNITUDE_MULTIPLIERS.get(mag, 1.3)
        return "jam", mult, False, False, False, description, icon, mag
    if icon in ICON_CLUSTER_D:
        return "environmental", ENVIRONMENTAL_MULTIPLIER, False, False, True, description, icon, mag
    # Unknown: treat as low-severity jam
    return "other", 1.1, False, False, False, description, icon, mag


def _incident_to_geometry(inc):
    """Return Shapely LineString from incident GeoJSON, or None."""
    geom = inc.get("geometry")
    if not geom or geom.get("type") != "LineString":
        return None
    coords = geom.get("coordinates")
    if not coords or len(coords) < 2:
        return None
    try:
        # GeoJSON: [lon, lat]
        return LineString(coords)
    except Exception:
        return None


def _make_bounds(coords):
    """coords: [[lat, lon], ...]. Return (min_lat, max_lat, min_lon, max_lon)."""
    if not coords:
        return (0, 0, 0, 0)
    lats = [p[0] for p in coords]
    lons = [p[1] for p in coords]
    return (min(lats), max(lats), min(lons), max(lons))


def update_disruptions():
    """Fetch TomTom, match to edges using tfl_live STRtree, fill TOMTOM_EDGES and TOMTOM_VIS.
    Requires tfl_live.init(G) to have been called. Returns (success, message, count)."""
    global TOMTOM_EDGES, TOMTOM_VIS, _raw_incidents_by_id, _last_update, _last_error

    import tfl_live
    keys = tfl_live.get_edge_keys()
    if not keys:
        msg = "STRtree not built — call tfl_live.init(G) first"
        _last_error = msg
        log.warning("tomtom_live: %s", msg)
        return False, msg, 0

    incidents, err = _fetch_tomtom_json()
    if err:
        _last_error = err
        log.warning("tomtom_live: fetch failed: %s", err)
        return False, err, 0

    raw_by_id = {(inc.get("properties") or {}).get("id") or f"inc-{i}": inc for i, inc in enumerate(incidents)}

    new_edges = {}
    new_vis = []
    matched_incidents = 0
    total_matched_edges = 0

    for inc in incidents:
        geom = _incident_to_geometry(inc)
        if geom is None or geom.is_empty:
            continue
        try:
            indices = tfl_live.match_geometry_to_edges(geom)
        except Exception as exc:
            log.warning("tomtom_live: match error for incident %s: %s", inc.get("properties", {}).get("id"), exc)
            continue
        if not indices:
            continue

        cluster_type, sev_mult, is_closed, temp_bad_surface, env_hazard, description, icon, mag = _classify_incident(inc)
        inc_id = (inc.get("properties") or {}).get("id") or "unknown"

        rec = {
            "is_closed": is_closed,
            "severity_multiplier": sev_mult,
            "temporary_bad_surface": temp_bad_surface,
            "environmental_hazard": env_hazard,
            "description": description,
            "disruption_id": inc_id,
            "source": "tomtom",
            "iconCategory": icon,
            "magnitudeOfDelay": mag,
            "cluster_type": cluster_type,
        }

        for idx in indices:
            key = keys[idx]
            existing = new_edges.get(key)
            if existing is None or sev_mult > existing["severity_multiplier"]:
                new_edges[key] = rec
            coords = tfl_live.get_edge_coords_latlon(idx)
            if coords and len(coords) >= 2:
                new_vis.append({
                    "id": f"tomtom-{inc_id}-{idx}",
                    "p": coords,
                    "b": _make_bounds(coords),
                    "type": cluster_type,
                    "source": "tomtom",
                    "iconCategory": icon,
                    "magnitudeOfDelay": mag,
                    "description": description,
                })

        matched_incidents += 1
        total_matched_edges += len(indices)

    TOMTOM_EDGES = new_edges
    TOMTOM_VIS = new_vis
    globals()["_raw_incidents_by_id"] = raw_by_id
    _last_update = datetime.now(timezone.utc)
    _last_error = None
    msg = f"Fetched {len(incidents)} TomTom incidents, {matched_incidents} matched to {total_matched_edges} edges"
    log.info("tomtom_live: %s", msg)
    return True, msg, matched_incidents


def get_tomtom_disruptions_at(lat, lon, tolerance_deg=None):
    """Return list of full TomTom incident dicts at or near (lat, lon). Hit-tests TOMTOM_VIS segments."""
    if tolerance_deg is None:
        tolerance_deg = TOMTOM_CLICK_TOLERANCE_DEG
    from shapely.geometry import Point as ShapelyPoint
    click_point = ShapelyPoint(lon, lat).buffer(tolerance_deg)
    seen_ids = set()
    out = []
    for s in TOMTOM_VIS:
        coords = s.get("p") or []
        if len(coords) < 2:
            continue
        try:
            # coords are [lat, lon]
            line = LineString([(c[1], c[0]) for c in coords])
            if not line.intersects(click_point):
                continue
        except Exception:
            continue
        # id format: "tomtom-{incident_id}-{idx}" (incident_id may contain hyphens)
        parts = (s.get("id") or "").split("-")
        if len(parts) >= 3:
            inc_id = "-".join(parts[1:-1])
        else:
            inc_id = s.get("disruption_id") or "unknown"
        if inc_id in seen_ids:
            continue
        seen_ids.add(inc_id)
        full = _raw_incidents_by_id.get(inc_id)
        if full is not None:
            out.append(full)
    return out


def get_status():
    """Return status dict for /admin/tomtom_status."""
    return {
        "loaded": len(TOMTOM_EDGES) > 0,
        "edge_count": len(TOMTOM_EDGES),
        "last_update": _last_update.isoformat() if _last_update else None,
        "error": _last_error,
    }
