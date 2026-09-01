"""Instruction templates (MANEUVER_ENGINE_SPEC §5.1)."""
from __future__ import annotations

from .naming import display_name, generic_facility_label, parent_street


def _onto(name: str | None) -> str:
    return f" onto {name}" if name else ""


_COMPASS = (
    "north", "north-east", "east", "south-east",
    "south", "south-west", "west", "north-west",
)


def compass_word(bearing_deg: float | None) -> str | None:
    """Eight-point compass name for a departure bearing."""
    if bearing_deg is None:
        return None
    try:
        deg = float(bearing_deg) % 360.0
    except (TypeError, ValueError):
        return None
    return _COMPASS[int((deg + 22.5) % 360.0 // 45.0)]


def _side_word(modifier: str | None) -> str:
    if not modifier:
        return "left"
    if "uturn" in modifier:
        return "around"
    if "right" in modifier:
        return "right"
    if "left" in modifier:
        return "left"
    return "left"


def build_instruction(
    *,
    kind: str,
    modifier: str | None,
    edge_in: dict,
    edge_out: dict,
    class_in: str,
    class_out: str,
    depart_bearing: float | None = None,
) -> str:
    name_out = display_name(edge_out, class_out)
    parent_out = parent_street(edge_out)
    parent_in = parent_street(edge_in) or display_name(edge_in, class_in)

    if kind == "depart":
        label = name_out or generic_facility_label(class_out) or "your route"
        # "Head north on High Holborn" — a compass word orients the rider before
        # the first turn, which a bare "Head on ..." cannot.
        compass = compass_word(depart_bearing)
        lead = f"Head {compass}" if compass else "Head"
        if label.startswith("the "):
            return f"{lead} along {label}"
        return f"{lead} on {label}"

    if kind == "arrive":
        return "You have arrived at your destination"

    if kind == "facility_up":
        parent = parent_out or parent_in
        if class_out == "bus_lane":
            return "Use the bus lane"
        if class_out == "painted_lane":
            return "Use the cycle lane"
        if class_out == "shared_path":
            return f"Join the shared path along {parent}" if parent else "Join the shared path"
        if parent:
            return f"Join the cycle track along {parent}"
        return "Join the cycle track"

    if kind == "facility_down":
        target = name_out or parent_out or parent_in
        if target:
            return f"Return to {target}"
        return "Rejoin the road"

    if kind == "fork":
        side = _side_word(modifier)
        label = name_out or generic_facility_label(class_out) or "the cycleway"
        if class_out in ("segregated", "shared_path", "painted_lane", "bus_lane"):
            return f"Keep {side} on {label}"
        return f"Keep {side}{_onto(name_out)}".replace(" onto None", "")

    if kind == "uturn":
        return "Make a U-turn"

    if kind == "roundabout_enter":
        return "Enter the roundabout"

    if kind == "roundabout_exit":
        return f"At the roundabout, take the exit{_onto(name_out)}"

    if kind == "new_name":
        if modifier and modifier.startswith("slight"):
            return f"Bear slight {_side_word(modifier)}{_onto(name_out)}"
        return f"Continue{_onto(name_out)}" if name_out else "Continue"

    # turn / end of road
    if modifier == "uturn":
        return "Make a U-turn"
    if modifier and modifier.startswith("slight"):
        return f"Bear slight {_side_word(modifier)}{_onto(name_out)}"
    if modifier and modifier.startswith("sharp"):
        return f"Turn sharp {_side_word(modifier)}{_onto(name_out)}"
    return f"Turn {_side_word(modifier)}{_onto(name_out)}"
