"""
Unified live disruptions: TfL + TomTom. Safe-update pattern: source-specific state
then merged MASTER_LIVE_LOOKUP for O(1) routing. app.py and app_debug.py use this module.
Call init(G) once; then update_disruptions(fetch_tfl=..., fetch_tomtom=...) and query get_edge_disruption(u, v).
"""
import logging

log = logging.getLogger("live_disruptions")
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# Internal source state (never overwrite one source when updating the other)
# ---------------------------------------------------------------------------
_TFL_EDGES = {}      # {(u, v): disruption_dict}
_TFL_VIS = []        # [{id, p, b, type, ...}]

_TOMTOM_EDGES = {}   # {(u, v): disruption_dict}
_TOMTOM_VIS = []     # [{id, p, b, type, source: "tomtom", iconCategory, magnitudeOfDelay, description}]

# Master state (exposed to app.py for A*)
MASTER_LIVE_LOOKUP = {}  # {(u, v): merged disruption_dict}


def init(G):
    """Build STRtree and edge list. Call once at startup. Required before any update."""
    import tfl_live
    tfl_live.init(G)


def _rebuild_master_lookup():
    """Merge _TFL_EDGES and _TOMTOM_EDGES into MASTER_LIVE_LOOKUP. Worst-case penalty per edge."""
    global MASTER_LIVE_LOOKUP
    merged = {}
    for key, rec in _TFL_EDGES.items():
        merged[key] = _normalize_tfl_rec(rec)
    for key, rec in _TOMTOM_EDGES.items():
        existing = merged.get(key)
        if existing is None:
            merged[key] = _normalize_tomtom_rec(rec)
        else:
            merged[key] = _merge_two(existing, _normalize_tomtom_rec(rec))
    MASTER_LIVE_LOOKUP = merged
    log.info("live_disruptions: master lookup rebuilt with %d edges", len(merged))


def _normalize_tfl_rec(rec):
    """TfL rec -> unified shape (has_closure, is_closed, severity_multiplier, etc.)."""
    return {
        "has_closure": bool(rec.get("has_closure")),
        "is_closed": False,
        "severity_multiplier": float(rec.get("severity_multiplier", 1.0)),
        "temporary_bad_surface": False,
        "environmental_hazard": False,
        "is_diversion": bool(rec.get("is_diversion")),
        "category": rec.get("category", ""),
        "severity": rec.get("severity", ""),
        "description": rec.get("description", ""),
        "source": "tfl",
        "disruption_id": rec.get("disruption_id", ""),
    }


def _normalize_tomtom_rec(rec):
    """TomTom rec -> unified shape."""
    return {
        "has_closure": False,
        "is_closed": bool(rec.get("is_closed")),
        "severity_multiplier": float(rec.get("severity_multiplier", 1.0)),
        "temporary_bad_surface": bool(rec.get("temporary_bad_surface")),
        "environmental_hazard": bool(rec.get("environmental_hazard")),
        "is_diversion": False,
        "category": rec.get("cluster_type", ""),
        "severity": "",
        "description": rec.get("description", ""),
        "source": "tomtom",
        "disruption_id": rec.get("disruption_id", ""),
        "iconCategory": rec.get("iconCategory"),
        "magnitudeOfDelay": rec.get("magnitudeOfDelay"),
    }


def _merge_two(a, b):
    """Merge two unified recs: max severity_multiplier, closure if either, union of surface/env flags."""
    return {
        "has_closure": a.get("has_closure") or b.get("has_closure"),
        "is_closed": a.get("is_closed") or b.get("is_closed"),
        "severity_multiplier": max(
            float(a.get("severity_multiplier", 1.0)),
            float(b.get("severity_multiplier", 1.0)),
        ),
        "temporary_bad_surface": a.get("temporary_bad_surface") or b.get("temporary_bad_surface"),
        "environmental_hazard": a.get("environmental_hazard") or b.get("environmental_hazard"),
        "is_diversion": a.get("is_diversion") or b.get("is_diversion"),
        "category": a.get("category") or b.get("category"),
        "severity": a.get("severity") or b.get("severity"),
        "description": a.get("description") or b.get("description"),
        "source": "tfl+tomtom",
        "disruption_id": a.get("disruption_id") or b.get("disruption_id"),
        "iconCategory": a.get("iconCategory") or b.get("iconCategory"),
        "magnitudeOfDelay": a.get("magnitudeOfDelay") if a.get("magnitudeOfDelay") is not None else b.get("magnitudeOfDelay"),
    }


def update_disruptions(fetch_tfl=False, fetch_tomtom=False):
    """Update one or both sources, then rebuild master lookup. Safe: updating one never clears the other.
    Returns (ok: bool, message: str, count: int). Count is for the updated source(s) or master size."""
    global _TFL_EDGES, _TFL_VIS, _TOMTOM_EDGES, _TOMTOM_VIS

    last_ok, last_msg, last_count = True, "", 0

    if fetch_tfl:
        import tfl_live
        ok, msg, count = tfl_live.update_disruptions()
        last_ok, last_msg, last_count = ok, msg, count
        if ok:
            _TFL_EDGES = dict(tfl_live.TFL_LIVE_LOOKUP)
            _TFL_VIS = list(tfl_live.TFL_LIVE_VIS_CACHE)
        else:
            log.warning("live_disruptions: TfL update failed: %s", msg)

    if fetch_tomtom:
        import tomtom_live
        ok, msg, count = tomtom_live.update_disruptions()
        last_ok, last_msg, last_count = ok, msg, count
        if ok:
            _TOMTOM_EDGES = dict(tomtom_live.TOMTOM_EDGES)
            _TOMTOM_VIS = list(tomtom_live.TOMTOM_VIS)
        else:
            log.warning("live_disruptions: TomTom update failed: %s", msg)

    _rebuild_master_lookup()
    if fetch_tfl and fetch_tomtom:
        return (last_ok, last_msg, len(MASTER_LIVE_LOOKUP))
    return (last_ok, last_msg, last_count)


def get_edge_disruption(u, v):
    """O(1) lookup. Returns merged disruption dict or None. Use this in weight_optimized."""
    return MASTER_LIVE_LOOKUP.get((u, v))


def get_vis_segments_in_bbox(min_lat, max_lat, min_lon, max_lon, source=None, limit=20000):
    """Return vis segments in bbox. source: 'tfl' | 'tomtom' | None (both, merged list)."""
    if source == "tfl":
        segs = _TFL_VIS
    elif source == "tomtom":
        segs = _TOMTOM_VIS
    else:
        segs = _TFL_VIS + _TOMTOM_VIS

    in_bbox = [
        s for s in segs
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
        item = {
            "id": s["id"],
            "p": s["p"],
            "type": s["type"],
            "severity": s.get("severity", ""),
            "category": s.get("category", ""),
            "description": s.get("description", ""),
            "source": s.get("source", "tfl"),
        }
        if "iconCategory" in s:
            item["iconCategory"] = s["iconCategory"]
        if "magnitudeOfDelay" in s:
            item["magnitudeOfDelay"] = s["magnitudeOfDelay"]
        out.append(item)
    return out, limit_reached


def get_status():
    """Merged status for both sources."""
    import tfl_live
    import tomtom_live
    tfl_status = tfl_live.get_status()
    tomtom_status = tomtom_live.get_status()
    return {
        "tfl": tfl_status,
        "tomtom": tomtom_status,
        "master_edge_count": len(MASTER_LIVE_LOOKUP),
    }
