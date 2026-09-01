"""Serialize Option B maneuvers to an OSRM-/MapLibre-shaped navigation object."""
from __future__ import annotations

from typing import Any

from . import constants as C
from .engine import build_navigation_from_edges
from .facility import smooth_facility_classes
from .geometry_nav import edge_length_m
from .naming import display_name
from .voice import METRIC, build_step_voice, normalise_units


def build_osrm_navigation(
    edges: list[dict],
    *,
    route_coords_latlon: list[list[float]] | None = None,
    duration_min: float | None = None,
    include_debug: bool = False,
    voice_units: str = METRIC,
) -> dict[str, Any]:
    """
    Return ``navigation`` suitable for ``/route?navigate=1`` and MapLibre BYOR.

    Geometry uses [[lon, lat], ...] in ``geometry.coordinates`` (GeoJSON order)
    plus ``geometry_latlon`` [[lat, lon], ...] matching Tuned ``safest.path``.

    Step ``i`` carries the maneuver that *starts* it (OSRM convention) while its
    voice and banner instructions announce the maneuver that *ends* it, i.e. the
    maneuver of step ``i + 1``.
    """
    voice_units = normalise_units(voice_units)
    base = build_navigation_from_edges(edges)
    classes = smooth_facility_classes(edges)
    lengths = [edge_length_m(e) for e in edges]
    total_m = float(base.get("distance") or sum(lengths) or 0.0)
    duration_s = float(duration_min or 0.0) * 60.0

    spoken = [m for m in base["maneuvers"] if m.get("speak")]
    full_latlon = route_coords_latlon or _concat_coords(edges)

    # Pass 1 — geometry and metrics per step. Chaining needs the *next* step's
    # length, so the steps are measured before any instruction is attached.
    steps: list[dict] = []
    for i, man in enumerate(spoken):
        nxt = spoken[i + 1] if i + 1 < len(spoken) else None
        is_arrive = man.get("gate") == "S2" or man.get("kind") == "arrive"
        e0 = _step_start_edge(man)
        e1 = _step_end_edge_exclusive(nxt, len(edges))
        slice_edges = edges[e0:e1]
        geom_latlon = _concat_coords(slice_edges)
        if not geom_latlon and route_coords_latlon and i == 0:
            geom_latlon = list(route_coords_latlon)
        # Arrive (and any empty step): MapLibre Replay crashes on empty step geometry.
        if not geom_latlon and full_latlon:
            end = full_latlon[-1]
            geom_latlon = [list(end), list(end)]
        dist = sum(lengths[j] for j in range(e0, min(e1, len(lengths))))
        dur = (dist / total_m * duration_s) if total_m > 0 else 0.0
        name = None
        if slice_edges:
            name = display_name(slice_edges[0], classes[e0] if e0 < len(classes) else "other")
        loc = man.get("location")
        if (not loc or loc == [0.0, 0.0]) and geom_latlon:
            # Arrive uses the destination point (end of geometry).
            pt = geom_latlon[-1] if is_arrive else geom_latlon[0]
            loc = [pt[1], pt[0]]
        bearings = _bearings(man)
        modifier = man.get("modifier")
        if modifier is None:
            # MapLibre sample fixtures always set a string modifier (arrive too).
            modifier = "straight"
        steps.append({
            "distance": round(dist, 1),
            "duration": round(dur, 1),
            "weight": round(dist, 1),
            "name": name or "",
            "mode": "cycling",
            "driving_side": "left",
            "maneuver": {
                "type": man.get("maneuver_type") or "turn",
                "modifier": modifier,
                "instruction": man.get("instruction") or "",
                "location": loc,
                "bearing_before": bearings[0] if bearings[0] is not None else 0.0,
                "bearing_after": bearings[1] if bearings[1] is not None else 0.0,
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [[p[1], p[0]] for p in geom_latlon],
            },
            "geometry_latlon": geom_latlon,
            "tuned": {
                "gate": man.get("gate"),
                "kind": man.get("kind"),
            },
        })

    # Pass 2 — voice / banner schedule for the maneuver ending each step.
    _attach_instructions(steps, spoken, voice_units)

    out: dict[str, Any] = {
        "distance": round(total_m, 1),
        "duration": round(duration_s, 1),
        "geometry": {
            "type": "LineString",
            "coordinates": [[p[1], p[0]] for p in full_latlon],
        },
        "geometry_latlon": full_latlon,
        "legs": [
            {
                "distance": round(total_m, 1),
                "duration": round(duration_s, 1),
                "steps": steps,
            }
        ],
        "meta": {
            **(base.get("meta") or {}),
            "engine": "tuned_option_b",
            "n_steps": len(steps),
        },
    }
    if include_debug:
        out["debug"] = {
            "maneuvers": base.get("maneuvers"),
            "junctions_summary": [
                {
                    "index": j.get("index"),
                    "speak": j.get("speak"),
                    "gate": j.get("gate"),
                    "instruction": j.get("instruction"),
                }
                for j in (base.get("junctions") or [])
            ],
        }
    return out


def _attach_instructions(
    steps: list[dict],
    spoken: list[dict],
    voice_units: str,
) -> None:
    """
    Add ``voiceInstructions`` / ``bannerInstructions`` to each step in place.

    Step ``i`` announces ``spoken[i + 1]``. Where ``spoken[i + 2]`` follows within
    ``VOICE_CHAIN_M`` the two are spoken as one cue and the next step's own final
    cue is dropped, so a short connector is not read out twice.
    """
    n = len(steps)
    chained: list[bool] = [False] * n
    suppressed: list[bool] = [False] * n

    for i in range(n):
        suppressed[i] = chained[i - 1] if i > 0 else False
        if suppressed[i]:
            # Final cue already folded into the previous step; nothing to chain on.
            continue
        follow = spoken[i + 2] if i + 2 < len(spoken) else None
        if not (follow and follow.get("instruction")):
            continue
        if float(steps[i + 1]["distance"]) <= C.VOICE_CHAIN_M:
            chained[i] = True

    for i, step in enumerate(steps):
        target = spoken[i + 1] if i + 1 < len(spoken) else None
        instruction = (target or {}).get("instruction")
        if not instruction:
            continue
        follow = spoken[i + 2] if chained[i] and i + 2 < len(spoken) else None
        voice = build_step_voice(
            step_distance_m=float(step["distance"]),
            step_duration_s=float(step["duration"]),
            target_instruction=instruction,
            is_arrival=_is_arrive(target),
            depart_instruction=spoken[0].get("instruction") if i == 0 else None,
            chain_instruction=(follow or {}).get("instruction"),
            suppress_execute=suppressed[i],
            units=voice_units,
        )
        if voice:
            step["voiceInstructions"] = voice
        step["bannerInstructions"] = [
            {
                # Shown for the whole step, so it covers the countdown to the turn.
                "distanceAlongGeometry": float(step["distance"]),
                "primary": {
                    "text": instruction,
                    "type": target.get("maneuver_type") or "turn",
                    "modifier": target.get("modifier") or "straight",
                },
            }
        ]


def _is_arrive(man: dict) -> bool:
    return man.get("gate") == "S2" or man.get("kind") == "arrive"


def _step_start_edge(man: dict) -> int:
    gate = man.get("gate")
    if gate == "S1":
        return 0
    idx = int(man.get("index") if man.get("index") is not None else 0)
    # Junction at index i is at end of edge i → next step starts at i+1
    return max(0, idx + 1)


def _step_end_edge_exclusive(nxt: dict | None, n_edges: int) -> int:
    if nxt is None or nxt.get("gate") == "S2":
        return n_edges
    idx = int(nxt.get("index") if nxt.get("index") is not None else n_edges - 1)
    return max(0, idx + 1)


def _concat_coords(edges: list[dict]) -> list[list[float]]:
    out: list[list[float]] = []
    for e in edges:
        coords = e.get("coords") or []
        if not coords:
            continue
        if not out:
            out.extend([list(c) for c in coords])
        else:
            out.extend([list(c) for c in coords[1:]])
    return out


def _bearings(man: dict) -> tuple[float | None, float | None]:
    return man.get("bearing_before"), man.get("bearing_after")
