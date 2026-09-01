"""
Displayed ride-time estimates for route stats (does not affect routing).

Phase A (legacy): preset-specific cruise-speed multiplier on distance-only time.
Phase B (default): cruise (optional Jafari VF speed uplift) + stop/climb penalties.
"""
from __future__ import annotations

import os

# Phase A — Fast preset: fewer signal stops imply higher effective cruise speed.
# Unused when ROUTE_TIME_MODEL=penalties (default). Kept for rollback / compares.
FAST_PRESET_DURATION_SPEED_MULTIPLIER = 1.35

# Phase B — penalty budget (seconds).
# signal: must match app.SIGNAL_WAIT_SECONDS and wizard FAST_SECONDS_PER_UNIT.signal_count.
# After Phase 1, signal_count = signal-cluster *entries* on the path (not raw OSM nodes).
# Climb: Miotti & Hellweg SSRN 5050670 — https://ssrn.com/abstract=5050670
#   standard 2.58 s/m elev gain; e-bike 1.54 s/m. Downhill does NOT raise speed → no descent bonus.
CLIMB_SECONDS_PER_METRE_BY_BIKE = {
    "standard": 2.58,
    "road": 2.58,  # no separate estimate yet — treat as standard
    "ebike": 1.54,
    "cargo": 2.58,  # no separate estimate — treat as standard (conservative)
}

# Stop seconds aligned with A* additive metres at 16 km/h (CYCLIST_SPEED_MPS).
# signal 7.5 s → 33.3 m; crossing family (give-way / stop) half signal → 16.7 m;
# junction danger 8 m; calming "otherwise" 10 m; soft barrier permeable cluster 15 m.
# Does not change path search — only displayed ETA after A*.
PENALTY_SECONDS = {
    "signal": 7.5,
    "give_way": 3.75,
    "stop_sign": 3.75,
    "junction": 1.8,
    "calming": 2.25,
    "barrier": 3.375,
    "climb_per_metre": CLIMB_SECONDS_PER_METRE_BY_BIKE["standard"],
}

# Jafari et al. (2025) JCMR — speed uplift vs mixed traffic (baseline 20.36 km/h).
# https://doi.org/10.1016/j.jcmr.2024.100049
# Mapped onto our cost_masks VF bits (priority: core > painted > bus > shared).
JAFARI_SPEED_UPLIFT_BY_VF_CLASS = {
    "core": 0.0751,  # Separated lane +7.51%
    "painted_lane": 0.0359,  # Simple lane +3.59%
    "bus_lane": 0.0064,  # no Jafari class — treat as shared path (still motor traffic)
    "shared_path": 0.0064,  # Shared path +0.64%
    # Dedicated path +1.62% has no distinct OSM bit; physical separation → core.
}


def route_time_model() -> str:
    """Display duration model: 'penalties' (Phase B, default) or 'phase_a' / 'cruise'."""
    return (os.environ.get("ROUTE_TIME_MODEL") or "penalties").strip().lower()


def climb_seconds_per_metre_for_bike(bike_type: str | None) -> float:
    """Elevation-gain delay (s/m) for Phase B; Miotti & Hellweg SSRN 5050670."""
    key = (bike_type or "standard").strip().lower()
    return float(
        CLIMB_SECONDS_PER_METRE_BY_BIKE.get(key, CLIMB_SECONDS_PER_METRE_BY_BIKE["standard"])
    )


def duration_speed_multiplier_for_preset(preset: str | None) -> float:
    """Phase A only — return 1.0 when Phase B is the active display model."""
    if route_time_model() in ("penalties", "phase_b", "b"):
        return 1.0
    if preset == "fast":
        return FAST_PRESET_DURATION_SPEED_MULTIPLIER
    return 1.0


def cruise_duration_min(
    length_m: float, speed_kmh: float, duration_speed_multiplier: float = 1.0
) -> float:
    """Distance-only ride time with optional preset multiplier (Phase A)."""
    if length_m <= 0 or speed_kmh <= 0:
        return 0.0
    effective_kmh = speed_kmh * max(duration_speed_multiplier, 0.01)
    speed_mps = effective_kmh / 3.6
    return length_m / (speed_mps * 60.0)


def cruise_duration_min_with_vf(
    length_m: float,
    speed_kmh: float,
    vf_lengths_m: dict[str, float] | None = None,
) -> float:
    """Cruise time with per-class Jafari speed uplift on VF metres; rest = mixed traffic."""
    if length_m <= 0 or speed_kmh <= 0:
        return 0.0
    speed_mps = speed_kmh / 3.6
    parts = vf_lengths_m or {}
    # Highest segregation first so dual-flag edges are not double-counted by callers.
    order = ("core", "painted_lane", "bus_lane", "shared_path")
    used = 0.0
    seconds = 0.0
    for key in order:
        seg_m = float(parts.get(key) or 0.0)
        if seg_m <= 0:
            continue
        uplift = float(JAFARI_SPEED_UPLIFT_BY_VF_CLASS.get(key) or 0.0)
        seconds += seg_m / (speed_mps * (1.0 + uplift))
        used += seg_m
    mixed_m = max(0.0, float(length_m) - used)
    seconds += mixed_m / speed_mps
    return seconds / 60.0


def estimate_duration_min_phase_b(
    length_m: float,
    speed_kmh: float,
    *,
    signal_count: int = 0,
    give_way_count: int = 0,
    stop_sign_count: int = 0,
    junction_count: int = 0,
    calming_count: int = 0,
    barrier_penalty_count: int = 0,
    elevation_gain: float = 0.0,
    bike_type: str | None = "standard",
    climb_s_per_m: float | None = None,
    vf_lengths_m: dict[str, float] | None = None,
) -> float:
    """Phase B: Jafari-aware cruise + metric penalties (Miotti climb by bike type)."""
    cruise = cruise_duration_min_with_vf(length_m, speed_kmh, vf_lengths_m)
    climb_rate = (
        float(climb_s_per_m)
        if climb_s_per_m is not None
        else climb_seconds_per_metre_for_bike(bike_type)
    )
    penalty_s = (
        signal_count * PENALTY_SECONDS["signal"]
        + give_way_count * PENALTY_SECONDS["give_way"]
        + stop_sign_count * PENALTY_SECONDS["stop_sign"]
        + junction_count * PENALTY_SECONDS["junction"]
        + calming_count * PENALTY_SECONDS["calming"]
        + barrier_penalty_count * PENALTY_SECONDS["barrier"]
        + elevation_gain * climb_rate
    )
    return cruise + penalty_s / 60.0


def classify_vf_length_bucket(edge_vf: int, vf_mask_allowed: int) -> str | None:
    """Return Jafari/VF class key for an edge, or None if mixed / not in allowed mask."""
    from cost_masks import (
        VF_MASK_BUS_LANE,
        VF_MASK_CORE,
        VF_MASK_PAINTED_LANE,
        VF_MASK_SHARED_PATH,
    )

    if not (edge_vf & vf_mask_allowed):
        return None
    if edge_vf & VF_MASK_CORE & vf_mask_allowed:
        return "core"
    if edge_vf & VF_MASK_PAINTED_LANE & vf_mask_allowed:
        return "painted_lane"
    if edge_vf & VF_MASK_BUS_LANE & vf_mask_allowed:
        return "bus_lane"
    if edge_vf & VF_MASK_SHARED_PATH & vf_mask_allowed:
        return "shared_path"
    return None
