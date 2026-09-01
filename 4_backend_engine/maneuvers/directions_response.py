"""Wrap Tuned navigation into a Mapbox/MapLibre DirectionsResponse JSON."""
from __future__ import annotations

from typing import Any

from .polyline import encode_polyline
from .voice import METRIC, normalise_units


def to_directions_response(
    navigation: dict[str, Any],
    *,
    origin_latlon: list[float] | tuple[float, float],
    destination_latlon: list[float] | tuple[float, float],
    uuid: str = "tuned-byor-n0",
    profile: str = "cycling",
    voice_units: str = METRIC,
) -> dict[str, Any]:
    """
    Build a Directions API–shaped payload for MapLibre Navigation ``fromJson``.

    Geometry fields use **polyline6** strings (precision 6).

    ``routeOptions`` uses MapLibre kotlinx ``@SerialName`` keys
    (``voice_instructions``, ``banner_instructions``, ``access_token``, ``uuid``).
    CamelCase for those fields makes ``fromJson`` drop them →
    ``IllegalStateException: Using the default milestones requires…``.
    """
    route = _navigation_to_route(navigation)
    o_lat, o_lon = float(origin_latlon[0]), float(origin_latlon[1])
    d_lat, d_lon = float(destination_latlon[0]), float(destination_latlon[1])

    # Snake_case for SerialName fields — required by MapLibre Navigation models
    route["routeOptions"] = {
        "baseUrl": "https://tuned.local",
        "user": "tuned",
        "profile": profile,
        "coordinates": [[o_lon, o_lat], [d_lon, d_lat]],
        "language": "en",
        "geometries": "polyline6",
        "overview": "full",
        "steps": True,
        "voice_instructions": True,
        "banner_instructions": True,
        "voice_units": normalise_units(voice_units),
        "access_token": "pk.tuned",
        "uuid": uuid,
        "alternatives": False,
    }
    route["voiceLocale"] = "en-GB"
    route["weight_name"] = "tuned"
    route["weight"] = float(route.get("distance") or 0.0)

    return {
        "code": "Ok",
        "uuid": uuid,
        "waypoints": [
            {"name": "Origin", "location": [o_lon, o_lat]},
            {"name": "Destination", "location": [d_lon, d_lat]},
        ],
        "routes": [route],
    }


def _navigation_to_route(navigation: dict[str, Any]) -> dict[str, Any]:
    full_latlon = navigation.get("geometry_latlon") or []
    legs_out = []
    for leg in navigation.get("legs") or []:
        steps_out = []
        for step in leg.get("steps") or []:
            steps_out.append(_step_to_leg_step(step))
        legs_out.append({
            "distance": float(leg.get("distance") or 0.0),
            "duration": float(leg.get("duration") or 0.0),
            "summary": "",
            "steps": steps_out,
        })

    return {
        "distance": float(navigation.get("distance") or 0.0),
        "duration": float(navigation.get("duration") or 0.0),
        "geometry": encode_polyline(full_latlon, precision=6),
        "legs": legs_out,
    }


def _step_to_leg_step(step: dict[str, Any]) -> dict[str, Any]:
    man = step.get("maneuver") or {}
    latlon = step.get("geometry_latlon") or []
    if not latlon:
        geo = step.get("geometry") or {}
        if isinstance(geo, dict) and geo.get("coordinates"):
            latlon = [[c[1], c[0]] for c in geo["coordinates"]]

    location = man.get("location")
    if location and len(location) >= 2 and not (
        float(location[0]) == 0.0 and float(location[1]) == 0.0
    ):
        raw_loc = [float(location[0]), float(location[1])]
    elif latlon:
        mtype = (man.get("type") or "").lower()
        pt = latlon[-1] if mtype == "arrive" else latlon[0]
        raw_loc = [float(pt[1]), float(pt[0])]
    else:
        raw_loc = [0.0, 0.0]

    if len(latlon) < 2 and raw_loc != [0.0, 0.0]:
        latlon = [
            [raw_loc[1], raw_loc[0]],
            [raw_loc[1], raw_loc[0]],
        ]

    dist = float(step.get("distance") or 0.0)
    modifier = man.get("modifier") or "straight"
    man_type = man.get("type") or "turn"
    instruction = man.get("instruction") or ""

    out: dict[str, Any] = {
        "distance": dist,
        "duration": float(step.get("duration") or 0.0),
        "weight": float(step.get("weight") if step.get("weight") is not None else dist),
        "name": step.get("name") or "",
        "mode": step.get("mode") or "cycling",
        "driving_side": step.get("driving_side") or "left",
        "geometry": encode_polyline(latlon, precision=6),
        "maneuver": {
            "type": man_type,
            "modifier": modifier,
            "instruction": instruction,
            "location": raw_loc,
            "bearing_before": float(man.get("bearing_before") or 0.0),
            "bearing_after": float(man.get("bearing_after") or 0.0),
        },
        "intersections": [
            {
                "location": raw_loc,
                "bearings": [
                    int(man.get("bearing_before") or 0),
                    int(man.get("bearing_after") or 0),
                ],
                "entry": [True, True],
            }
        ],
    }

    # The maneuver engine owns the announcement schedule (maneuvers/voice.py);
    # this layer only reshapes it. A step without cues is a step that should stay
    # silent, so nothing is synthesized here.
    voice = step.get("voiceInstructions")
    if voice:
        out["voiceInstructions"] = voice

    banners = step.get("bannerInstructions")
    if banners:
        out["bannerInstructions"] = [_with_components(b) for b in banners]

    return out


def _with_components(banner: dict[str, Any]) -> dict[str, Any]:
    """MapLibre's BannerText expects a components array; fill it from the text."""
    primary = dict(banner.get("primary") or {})
    if primary and not primary.get("components"):
        primary["components"] = [{"type": "text", "text": primary.get("text") or ""}]
    out = dict(banner)
    if primary:
        out["primary"] = primary
    return out
