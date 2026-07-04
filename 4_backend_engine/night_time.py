"""
Offline darkness check for the lit-at-night preference (no API calls).

Uses the standard NOAA low-accuracy solar position approximation (good to a
fraction of a degree - far more than needed to decide "is it dark in London").
The light_weight penalty is applied only when the sun is below
DARK_SUN_ELEVATION_DEG (start of civil twilight, when street lighting matters).
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

LONDON_LAT = 51.5074
LONDON_LON = -0.1278

# Sun elevation below which we consider it "dark" for routing purposes.
DARK_SUN_ELEVATION_DEG = -3.0

# Development override: 'day' or 'night' forces is_dark() regardless of the
# actual sun position (set via `python app.py --day|--night`). None = real sun.
_forced_mode: str | None = None


def set_forced_mode(mode: str | None) -> None:
    """Force is_dark() to a fixed answer: 'day' -> False, 'night' -> True."""
    global _forced_mode
    if mode is not None:
        mode = mode.lower()
        if mode not in ("day", "night"):
            raise ValueError(f"forced mode must be 'day' or 'night', got {mode!r}")
    _forced_mode = mode
    if mode:
        print(f"[night_time] FORCED {mode.upper()} MODE - real sun position ignored")


def get_forced_mode() -> str | None:
    return _forced_mode


def solar_elevation_deg(dt: datetime, lat: float = LONDON_LAT, lon: float = LONDON_LON) -> float:
    """Sun elevation above the horizon in degrees at a UTC-aware datetime."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)

    # Days since J2000.0 epoch (2000-01-01 12:00 UTC), fractional.
    j2000 = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    d = (dt - j2000).total_seconds() / 86400.0

    # Mean longitude and mean anomaly of the sun (degrees).
    g = math.radians((357.529 + 0.98560028 * d) % 360.0)
    q = (280.459 + 0.98564736 * d) % 360.0
    # Ecliptic longitude.
    lam = math.radians(q + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g))
    # Obliquity of the ecliptic.
    e = math.radians(23.439 - 0.00000036 * d)

    # Right ascension and declination.
    ra = math.atan2(math.cos(e) * math.sin(lam), math.cos(lam))
    dec = math.asin(math.sin(e) * math.sin(lam))

    # Greenwich mean sidereal time (degrees) -> local hour angle.
    gmst = (18.697374558 + 24.06570982441908 * d) % 24.0
    lst_deg = (gmst * 15.0 + lon) % 360.0
    ha = math.radians(lst_deg) - ra

    lat_r = math.radians(lat)
    elevation = math.asin(
        math.sin(lat_r) * math.sin(dec) + math.cos(lat_r) * math.cos(dec) * math.cos(ha)
    )
    return math.degrees(elevation)


def is_dark(dt: datetime | None = None) -> bool:
    """True when the sun is below DARK_SUN_ELEVATION_DEG over London."""
    if _forced_mode is not None:
        return _forced_mode == "night"
    if dt is None:
        dt = datetime.now(timezone.utc)
    return solar_elevation_deg(dt) < DARK_SUN_ELEVATION_DEG
