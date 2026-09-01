"""Speak / suppress decision table (MANEUVER_ENGINE_SPEC §4)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import constants as C
from .facility import protection_rank
from .geometry_nav import modifier_from_delta
from .naming import (
    display_name,
    meaningful_name_change,
    parent_street,
)


@dataclass
class SpeakDecision:
    speak: bool
    gate: str
    maneuver_type: str | None = None
    modifier: str | None = None
    instruction_kind: str | None = None  # turn | facility_up | facility_down | fork | …
    reasons: list[str] = field(default_factory=list)
    features: dict[str, Any] = field(default_factory=dict)


def _is_roundabout_edge(edge: dict) -> bool:
    j = str(edge.get("junction") or "").strip().lower()
    return j == "roundabout" or bool(edge.get("mini_roundabout"))


def decide_junction(
    *,
    edge_in: dict,
    edge_out: dict,
    class_in: str,
    class_out: str,
    key_in: tuple,
    key_out: tuple,
    delta_deg: float,
    dist_since_last_spoken_m: float,
    degree: int | None = None,
    len_in_m: float,
    len_out_m: float,
) -> SpeakDecision:
    """
    Evaluate S* / Q* gates for one junction.

    Priority: S3–S6, S10 > Q > S7–S9  (facility/roundabout/uturn beat suppress;
    routine turns respect suppress). Depart/arrive handled outside.
    """
    modifier = modifier_from_delta(delta_deg)
    abs_d = abs(delta_deg)
    name_in = display_name(edge_in, class_in)
    name_out = display_name(edge_out, class_out)
    parent_in = parent_street(edge_in) or (
        name_in if class_in in ("painted_lane", "bus_lane", "carriageway") else None
    )
    parent_out = parent_street(edge_out) or (
        name_out if class_out in ("painted_lane", "bus_lane", "carriageway") else None
    )
    same_continuity = key_in == key_out
    name_changed = meaningful_name_change(name_in or parent_in, name_out or parent_out)
    class_changed = class_in != class_out
    prot_delta = protection_rank(class_out) - protection_rank(class_in)
    # negative prot_delta => more protected (lower rank)

    deg = 2 if degree is None else int(degree)
    is_fork = deg >= 3 and abs_d >= C.STRAIGHT_DEG
    is_end_of_road = deg <= 2 and abs_d >= C.TURN_SPEAK_DEG and name_changed

    features = {
        "delta_deg": delta_deg,
        "modifier": modifier,
        "name_in": name_in,
        "name_out": name_out,
        "parent_in": parent_in,
        "parent_out": parent_out,
        "class_in": class_in,
        "class_out": class_out,
        "same_continuity": same_continuity,
        "name_changed": name_changed,
        "class_changed": class_changed,
        "protection_delta": prot_delta,
        "degree": deg,
        "is_fork": is_fork,
        "dist_since_last_spoken_m": dist_since_last_spoken_m,
        "len_in_m": len_in_m,
        "len_out_m": len_out_m,
    }

    rb_in = _is_roundabout_edge(edge_in)
    rb_out = _is_roundabout_edge(edge_out)

    # --- Hard SPEAK overrides (beat suppress) ---
    # S3 enter roundabout
    if not rb_in and rb_out:
        return SpeakDecision(
            True, "S3", "roundabout", modifier, "roundabout_enter",
            ["entering roundabout"], features,
        )
    # S4 exit roundabout
    if rb_in and not rb_out:
        return SpeakDecision(
            True, "S4", "exit roundabout", modifier, "roundabout_exit",
            ["leaving roundabout"], features,
        )

    # S5 facility up (more protected)
    if class_changed and prot_delta < 0:
        return SpeakDecision(
            True, "S5", "notification", "straight" if abs_d < C.TURN_SPEAK_DEG else modifier,
            "facility_up",
            [f"facility {class_in} -> {class_out}"], features,
        )
    # S6 facility down
    if class_changed and prot_delta > 0:
        return SpeakDecision(
            True, "S6", "notification", "straight" if abs_d < C.TURN_SPEAK_DEG else modifier,
            "facility_down",
            [f"facility {class_in} -> {class_out}"], features,
        )

    # S10 forced U-turn (not artefact)
    if abs_d >= C.UTURN_DEG and min(len_in_m, len_out_m) >= C.UTURN_ARTEFACT_M:
        return SpeakDecision(
            True, "S10", "turn", "uturn", "uturn",
            ["hard uturn"], features,
        )

    # --- Suppress gates ---
    # Q3 (micro edge) and Q4 (speak gap): DISABLED for v1 recall-first.
    # Prefer too many steps/icons over missing turns. Q4-B later can silence
    # only voice cues without dropping maneuvers. Q3 may return softened.
    #
    # Q7 U-turn artefact
    if abs_d >= C.UTURN_DEG and min(len_in_m, len_out_m) < C.UTURN_ARTEFACT_M:
        return SpeakDecision(False, "Q7", reasons=["uturn artefact"], features=features)

    # Q5 name flicker both empty-ish
    if name_changed and not (name_in or parent_in) and not (name_out or parent_out):
        return SpeakDecision(False, "Q5", reasons=["empty name flicker"], features=features)

    # Q1 same continuity + gentle
    if same_continuity and abs_d < C.TURN_SPEAK_DEG:
        return SpeakDecision(False, "Q1", reasons=["same continuity gentle"], features=features)

    # Q2 same continuity + medium bend, not fork/eor
    if (
        same_continuity
        and abs_d < C.MEDIUM_BEND_SUPPRESS_DEG
        and not is_fork
        and not is_end_of_road
        and not class_changed
    ):
        return SpeakDecision(False, "Q2", reasons=["same continuity medium bend"], features=features)

    # --- Routine speak gates ---
    # S7 true turn
    if abs_d >= C.TURN_SPEAK_DEG and (
        name_changed or not same_continuity or is_end_of_road or deg >= 3
    ):
        mtype = "end of road" if is_end_of_road else "turn"
        return SpeakDecision(
            True, "S7", mtype, modifier, "turn",
            ["true turn"], features,
        )

    # S9 fork
    if is_fork and abs_d >= C.STRAIGHT_DEG:
        side = "right" if delta_deg > 0 else "left"
        return SpeakDecision(
            True, "S9", "fork", f"slight {side}" if abs_d < 45 else side, "fork",
            ["fork"], features,
        )

    # S8 named change shallow
    if name_changed and abs_d >= C.NAME_CHANGE_DEG:
        mtype = "new name" if abs_d < C.TURN_SPEAK_DEG else "turn"
        return SpeakDecision(
            True, "S8", mtype, modifier, "new_name",
            ["name change"], features,
        )

    # Default suppress (grace over chatter)
    return SpeakDecision(False, "Q_default", reasons=["no speak gate"], features=features)
