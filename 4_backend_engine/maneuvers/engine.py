"""
Orchestrate Option B: edge list → junction decisions → navigation-ish structure.

Step 1 focus: decide_junctions + build_navigation_from_edges for tests.
Full OSRM voice/banner schedules come later with the HTML preview.
"""
from __future__ import annotations

from typing import Any

from . import constants as C
from .facility import smooth_facility_classes
from .geometry_nav import edge_length_m, initial_bearing, junction_turn
from .instructions import build_instruction
from .naming import continuity_key
from .speak_policy import decide_junction


def _degree_default(edge_in: dict, edge_out: dict) -> int:
    """Synthetic / unknown topology: infer minimal degree from name change."""
    # Callers may set edge_out['_junction_degree']
    d = edge_out.get("_junction_degree")
    if d is not None:
        return int(d)
    d = edge_in.get("_junction_degree")
    if d is not None:
        return int(d)
    return 2


def _depart_bearing(edge: dict) -> float | None:
    """Bearing of the first ARM_M metres of the route, for the departure cue."""
    coords = edge.get("coords") or []
    if len(coords) < 2:
        return None
    try:
        return initial_bearing(coords, C.ARM_M)
    except (ValueError, TypeError, IndexError):
        return None


def decide_junctions(edges: list[dict]) -> list[dict]:
    """
    Walk consecutive edges; return one record per junction (spoken or suppressed).

    Each record:
      index, speak, gate, maneuver_type, modifier, instruction, kind, features, turn
    """
    if len(edges) < 2:
        return []

    classes = smooth_facility_classes(edges)
    keys = [continuity_key(e, classes[i]) for i, e in enumerate(edges)]
    lengths = [edge_length_m(e) for e in edges]

    events: list[dict] = []
    dist_since = 10**9  # allow first junction to speak freely

    for i in range(len(edges) - 1):
        e_in, e_out = edges[i], edges[i + 1]
        turn = junction_turn(e_in, e_out)
        decision = decide_junction(
            edge_in=e_in,
            edge_out=e_out,
            class_in=classes[i],
            class_out=classes[i + 1],
            key_in=keys[i],
            key_out=keys[i + 1],
            delta_deg=turn["delta_deg"],
            dist_since_last_spoken_m=dist_since,
            degree=_degree_default(e_in, e_out),
            len_in_m=lengths[i],
            len_out_m=lengths[i + 1],
        )
        instruction = None
        if decision.speak:
            instruction = build_instruction(
                kind=decision.instruction_kind or "turn",
                modifier=decision.modifier,
                edge_in=e_in,
                edge_out=e_out,
                class_in=classes[i],
                class_out=classes[i + 1],
            )
            dist_since = 0.0
        else:
            dist_since += lengths[i + 1]

        events.append({
            "index": i,
            "speak": decision.speak,
            "gate": decision.gate,
            "maneuver_type": decision.maneuver_type,
            "modifier": decision.modifier,
            "kind": decision.instruction_kind,
            "instruction": instruction,
            "reasons": decision.reasons,
            "features": decision.features,
            "turn": turn,
            "class_in": classes[i],
            "class_out": classes[i + 1],
        })
    return events


def build_navigation_from_edges(edges: list[dict]) -> dict[str, Any]:
    """
    Build a minimal navigation object for tests / later MapLibre mapping.

    Includes depart + junction speaks + arrive as ordered maneuvers.
    """
    if not edges:
        return {"distance": 0.0, "duration": 0.0, "maneuvers": [], "legs": [{"steps": []}]}

    classes = smooth_facility_classes(edges)
    lengths = [edge_length_m(e) for e in edges]
    total_m = sum(lengths)

    maneuvers: list[dict] = []

    # Depart
    first = edges[0]
    depart_mod = "straight"
    maneuvers.append({
        "index": -1,
        "speak": True,
        "gate": "S1",
        "maneuver_type": "depart",
        "modifier": depart_mod,
        "kind": "depart",
        "instruction": build_instruction(
            kind="depart",
            modifier=depart_mod,
            edge_in=first,
            edge_out=first,
            class_in=classes[0],
            class_out=classes[0],
            depart_bearing=_depart_bearing(first),
        ),
        "location": None,
    })

    junctions = decide_junctions(edges)
    for ev in junctions:
        if not ev["speak"]:
            continue
        maneuvers.append({
            "index": ev["index"],
            "speak": True,
            "gate": ev["gate"],
            "maneuver_type": ev["maneuver_type"],
            "modifier": ev["modifier"],
            "kind": ev["kind"],
            "instruction": ev["instruction"],
            "location": ev["turn"]["location"],
            "bearing_before": ev["turn"]["bearing_before"],
            "bearing_after": ev["turn"]["bearing_after"],
            "delta_deg": ev["turn"]["delta_deg"],
            "features": ev["features"],
        })

    # Arrive
    last = edges[-1]
    maneuvers.append({
        "index": len(edges) - 1,
        "speak": True,
        "gate": "S2",
        "maneuver_type": "arrive",
        "modifier": None,
        "kind": "arrive",
        "instruction": build_instruction(
            kind="arrive",
            modifier=None,
            edge_in=last,
            edge_out=last,
            class_in=classes[-1],
            class_out=classes[-1],
        ),
        "location": None,
    })

    return {
        "distance": round(total_m, 1),
        "duration": 0.0,
        "maneuvers": maneuvers,
        "junctions": junctions,
        "meta": {
            "n_edges": len(edges),
            "n_spoken_junctions": sum(1 for m in maneuvers if m["gate"] not in ("S1", "S2")),
            "facility_classes": classes,
        },
    }
