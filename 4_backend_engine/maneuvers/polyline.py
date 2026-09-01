"""Google / Mapbox polyline encoding (precision 5 or 6)."""
from __future__ import annotations


def encode_polyline(coords_latlon: list[list[float]], *, precision: int = 6) -> str:
    """
    Encode [[lat, lon], ...] to a polyline string.

    MapLibre Navigation / Mapbox Directions typically use precision 6
    (``polyline6``). Classic Google polyline is precision 5.
    """
    if not coords_latlon:
        return ""
    factor = 10**precision
    result: list[str] = []
    prev_lat = 0
    prev_lon = 0
    for pt in coords_latlon:
        lat = int(round(float(pt[0]) * factor))
        lon = int(round(float(pt[1]) * factor))
        result.append(_encode_signed(lat - prev_lat))
        result.append(_encode_signed(lon - prev_lon))
        prev_lat, prev_lon = lat, lon
    return "".join(result)


def _encode_signed(n: int) -> str:
    value = ~(n << 1) if n < 0 else (n << 1)
    chars: list[str] = []
    while value >= 0x20:
        chars.append(chr((0x20 | (value & 0x1F)) + 63))
        value >>= 5
    chars.append(chr(value + 63))
    return "".join(chars)
