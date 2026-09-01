"""Bearings and turn angles for edge-path maneuvers (MANEUVER_ENGINE_SPEC §2.4)."""
from __future__ import annotations

import math
from typing import Sequence

from . import constants as C

# Path points are [lat, lon] to match Tuned /route paths.


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from point1 to point2, degrees [0, 360)."""
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δλ = math.radians(lon2 - lon1)
    x = math.sin(Δλ) * math.cos(φ2)
    y = math.cos(φ1) * math.sin(φ2) - math.sin(φ1) * math.cos(φ2) * math.cos(Δλ)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def signed_delta_deg(bearing_before: float, bearing_after: float) -> float:
    """
    Turn angle in (-180, 180].

    Positive = turn right (clockwise from travel direction).
    Negative = turn left.
    """
    return (bearing_after - bearing_before + 180.0) % 360.0 - 180.0


def _edge_coords(edge: dict) -> list[list[float]]:
    """Return [[lat, lon], ...] for an edge."""
    geom = edge.get("coords") or edge.get("geometry_coords") or edge.get("path")
    if geom:
        out = []
        for pt in geom:
            if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                continue
            out.append([float(pt[0]), float(pt[1])])
        if len(out) >= 2:
            return out
    # Fallback: straight line u -> v as (lon,lat) graph nodes or lat/lon pair dicts
    u, v = edge.get("u"), edge.get("v")
    if u is not None and v is not None:
        def _xy(n):
            if isinstance(n, dict):
                # graph nodes often {x: lon, y: lat}
                if "lat" in n and "lon" in n:
                    return [float(n["lat"]), float(n["lon"])]
                return [float(n["y"]), float(n["x"])]
            if isinstance(n, (list, tuple)) and len(n) >= 2:
                # Tuned graph node id is often (lon, lat)
                return [float(n[1]), float(n[0])]
            raise ValueError("unrecognized node")
        return [_xy(u), _xy(v)]
    raise ValueError("edge has no coordinates")


def edge_length_m(edge: dict) -> float:
    if edge.get("length") is not None:
        try:
            return float(edge["length"])
        except (TypeError, ValueError):
            pass
    coords = _edge_coords(edge)
    total = 0.0
    for i in range(1, len(coords)):
        total += haversine_m(coords[i - 1][0], coords[i - 1][1], coords[i][0], coords[i][1])
    return total


def _bearing_along(coords: Sequence[Sequence[float]], *, from_end: bool, arm_m: float) -> float:
    """Bearing of the last (or first) arm_m metres along a polyline."""
    if len(coords) < 2:
        raise ValueError("need ≥2 coordinates")
    if not from_end:
        # first arm_m: walk from start
        traveled = 0.0
        for i in range(1, len(coords)):
            a, b = coords[i - 1], coords[i]
            seg = haversine_m(a[0], a[1], b[0], b[1])
            if traveled + seg >= arm_m or i == len(coords) - 1:
                return bearing_deg(coords[0][0], coords[0][1], b[0], b[1])
            traveled += seg
        return bearing_deg(coords[0][0], coords[0][1], coords[-1][0], coords[-1][1])

    # last arm_m: walk from end backwards to find start of arm, then bearing toward end
    traveled = 0.0
    end = coords[-1]
    for i in range(len(coords) - 1, 0, -1):
        a, b = coords[i - 1], coords[i]
        seg = haversine_m(a[0], a[1], b[0], b[1])
        if traveled + seg >= arm_m or i == 1:
            # bearing along the final approach into end
            return bearing_deg(a[0], a[1], end[0], end[1])
        traveled += seg
    return bearing_deg(coords[0][0], coords[0][1], end[0], end[1])


def initial_bearing(coords: Sequence[Sequence[float]], arm_m: float) -> float:
    """Bearing of the first ``arm_m`` metres of a polyline."""
    return _bearing_along(coords, from_end=False, arm_m=arm_m)


def junction_turn(
    edge_in: dict,
    edge_out: dict,
    *,
    arm_m: float = C.ARM_M,
) -> dict:
    """Compute bearings and signed Δθ at the shared junction."""
    cin = _edge_coords(edge_in)
    cout = _edge_coords(edge_out)
    b_before = _bearing_along(cin, from_end=True, arm_m=arm_m)
    b_after = _bearing_along(cout, from_end=False, arm_m=arm_m)
    delta = signed_delta_deg(b_before, b_after)
    return {
        "bearing_before": round(b_before, 2),
        "bearing_after": round(b_after, 2),
        "delta_deg": round(delta, 2),
        "location": [cin[-1][1], cin[-1][0]],  # [lon, lat] OSRM convention
        "location_latlon": [cin[-1][0], cin[-1][1]],
    }


def modifier_from_delta(delta_deg: float) -> str:
    """OSRM-like modifier. Positive Δθ = right."""
    a = abs(delta_deg)
    if a < C.STRAIGHT_DEG:
        return "straight"
    if a > C.UTURN_DEG:
        return "uturn"
    side = "right" if delta_deg > 0 else "left"
    if a < 45.0:
        return f"slight {side}"
    if a < 120.0:
        return side
    return f"sharp {side}"
