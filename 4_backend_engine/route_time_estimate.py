"""
Displayed ride-time estimates for route stats (does not affect routing).

Phase A (live): preset-specific cruise-speed multiplier on distance-only time.
Phase B (planned): cruise time + discrete penalties aligned with cost-function stops.
"""
from __future__ import annotations

# Phase A — Fast preset: fewer signal stops imply higher effective cruise speed.
FAST_PRESET_DURATION_SPEED_MULTIPLIER = 1.35

# Phase B — initial penalty budget (seconds); tune against cost function when implemented.
PENALTY_SECONDS = {
    "signal": 25.0,
    "give_way": 6.0,
    "stop_sign": 15.0,
    "junction": 10.0,
    "calming": 4.0,
    "barrier": 20.0,
    "climb_per_metre": 1.0,
}


def duration_speed_multiplier_for_preset(preset: str | None) -> float:
    """Return cruise-speed multiplier for displayed duration_min (1.0 = no adjustment)."""
    if preset == "fast":
        return FAST_PRESET_DURATION_SPEED_MULTIPLIER
    return 1.0


def cruise_duration_min(length_m: float, speed_kmh: float, duration_speed_multiplier: float = 1.0) -> float:
    """Distance-only ride time with optional preset multiplier (Phase A)."""
    if length_m <= 0 or speed_kmh <= 0:
        return 0.0
    effective_kmh = speed_kmh * max(duration_speed_multiplier, 0.01)
    speed_mps = effective_kmh / 3.6
    return length_m / (speed_mps * 60.0)


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
) -> float:
    """Phase B sketch — not wired to production yet. See documentation/tasks/route_time_phase_b.md."""
    cruise = cruise_duration_min(length_m, speed_kmh, 1.0)
    penalty_s = (
        signal_count * PENALTY_SECONDS["signal"]
        + give_way_count * PENALTY_SECONDS["give_way"]
        + stop_sign_count * PENALTY_SECONDS["stop_sign"]
        + junction_count * PENALTY_SECONDS["junction"]
        + calming_count * PENALTY_SECONDS["calming"]
        + barrier_penalty_count * PENALTY_SECONDS["barrier"]
        + elevation_gain * PENALTY_SECONDS["climb_per_metre"]
    )
    return cruise + penalty_s / 60.0
