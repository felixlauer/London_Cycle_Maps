"""
Parse via waypoints for GET /route and aggregate multi-leg path stats.

via string format: "lat1,lon1;lat2,lon2" (max MAX_VIAS).
"""
from __future__ import annotations

MAX_VIAS = 3

# Fields summed across legs before percent recompute.
_SUM_KEYS = (
    "length_m",
    "accidents",
    "duration_min",
    "elevation_gain",
    "steep_count",
    "speed_stress_km",
    "green_km",
    "barrier_count",
    "barrier_penalty_count",
    "give_way_count",
    "stop_sign_count",
    "calming_count",
    "signal_count",
    "junction_count",
    "disruption_count",
)


def parse_vias_arg(raw: str | None) -> tuple[list[tuple[float, float]] | None, str | None]:
    """Return ([(lat, lon), ...], None) or (None, error_message). Empty → []."""
    if raw is None or not str(raw).strip():
        return [], None
    parts = [p.strip() for p in str(raw).split(";") if p.strip()]
    if len(parts) > MAX_VIAS:
        return None, f"At most {MAX_VIAS} via stops allowed."
    vias: list[tuple[float, float]] = []
    for i, part in enumerate(parts):
        bits = [b.strip() for b in part.split(",")]
        if len(bits) != 2:
            return None, f"Invalid via at index {i}: expected lat,lon."
        try:
            lat = float(bits[0])
            lon = float(bits[1])
        except ValueError:
            return None, f"Invalid via at index {i}: expected numeric lat,lon."
        vias.append((lat, lon))
    return vias, None


def concatenate_paths(paths: list[list]) -> list:
    """Join polylines; drop duplicate junction point between consecutive legs."""
    out: list = []
    for path in paths:
        if not path:
            continue
        if not out:
            out.extend(path)
        else:
            out.extend(path[1:] if len(path) > 1 else path)
    return out


def aggregate_path_stats(leg_stats: list[dict]) -> dict:
    """Sum additive metrics; recompute percentage fields from length-weighted shares."""
    if not leg_stats:
        return {}
    if len(leg_stats) == 1:
        return dict(leg_stats[0])

    totals = {k: 0.0 for k in _SUM_KEYS}
    # Reconstruct lengths used for percent fields via inverse of stored pct * length.
    lit_len = 0.0
    rough_len = 0.0
    scenic_green_len = 0.0
    vf_len = 0.0
    tfl_cw_len = 0.0
    tfl_qw_len = 0.0
    stress_len = 0.0

    for s in leg_stats:
        L = float(s.get("length_m") or 0)
        for k in _SUM_KEYS:
            totals[k] += float(s.get(k) or 0)
        lit_len += L * float(s.get("illumination_pct") or 0) / 100.0
        rough_len += L * float(s.get("rough_pct") or 0) / 100.0
        scenic_green_len += L * float(s.get("green_pct") or 0) / 100.0
        vf_len += L * float(s.get("vehicular_free_pct") or 0) / 100.0
        tfl_cw_len += L * float(s.get("tfl_cycleway_pct") or 0) / 100.0
        tfl_qw_len += L * float(s.get("tfl_quietway_pct") or 0) / 100.0
        stress_len += float(s.get("speed_stress_km") or 0) * 1000.0

    total_length = totals["length_m"]

    def pct(part: float) -> float:
        return round(part / total_length * 100, 1) if total_length > 0 else 0.0

    tfl_cw_pct = pct(tfl_cw_len)
    tfl_qw_pct = pct(tfl_qw_len)
    return {
        "length_m": round(total_length, 0),
        "accidents": int(totals["accidents"]),
        "duration_min": round(totals["duration_min"], 1),
        "illumination_pct": round(pct(lit_len), 0),
        "rough_pct": round(pct(rough_len), 0),
        "elevation_gain": round(totals["elevation_gain"], 0),
        "steep_count": int(totals["steep_count"]),
        "tfl_cycleway_pct": tfl_cw_pct,
        "tfl_quietway_pct": tfl_qw_pct,
        "tfl_network_pct": round(tfl_cw_pct + tfl_qw_pct, 1),
        "speed_stress_km": round(totals["speed_stress_km"], 2),
        "speed_stress_pct": pct(stress_len),
        "green_km": round(totals["green_km"], 2),
        "green_pct": pct(scenic_green_len),
        "vehicular_free_pct": pct(vf_len),
        "barrier_count": int(totals["barrier_count"]),
        "barrier_penalty_count": int(totals["barrier_penalty_count"]),
        "give_way_count": int(totals["give_way_count"]),
        "stop_sign_count": int(totals["stop_sign_count"]),
        "calming_count": int(totals["calming_count"]),
        "signal_count": int(totals["signal_count"]),
        "junction_count": int(totals["junction_count"]),
        "disruption_count": int(totals["disruption_count"]),
    }
