"""Display names and continuity keys (MANEUVER_ENGINE_SPEC §2.2–2.3)."""
from __future__ import annotations

import re

_EMPTY = frozenset({
    "", "nan", "none", "null", "untitled", "-", "n/a", "na",
})

_FACILITY_GENERIC = {
    "segregated": "the cycle track",
    "shared_path": "the shared path",
    "bus_lane": "the bus lane",
    "painted_lane": "the cycle lane",
    "carriageway": None,
    "service": None,
    "other": None,
}


def normalize_name(raw) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.lower() in _EMPTY:
        return None
    s = re.sub(r"\s+", " ", s)
    # Drop leading "the " for continuity comparisons only via continuity_key
    return s


def _norm_key_part(name: str | None) -> str:
    if not name:
        return ""
    s = name.lower().strip()
    if s.startswith("the "):
        s = s[4:]
    return re.sub(r"\s+", " ", s)


def network_ref(edge: dict) -> str | None:
    """Humanized TfL / LCN / RCN / NCN label if present."""
    prog = str(edge.get("tfl_cycle_programme") or "").strip().lower()
    # Prefer explicit refs
    for key, prefix in (
        ("ncn_ref", "NCN"),
        ("rcn_ref", "RCN"),
        ("lcn_ref", "LCN"),
    ):
        val = normalize_name(edge.get(key))
        if val:
            return f"{prefix} {val}"
    if prog and prog not in _EMPTY and prog != "nan":
        # e.g. cycleway / superhighway / quietway
        label = prog.replace("_", " ").title()
        return label
    return None


def parent_street(edge: dict) -> str | None:
    """Parent street for sidepaths / lanes when tagged."""
    for key in ("street:name", "is_sidepath:of:name", "street_name", "is_sidepath_of_name"):
        val = normalize_name(edge.get(key))
        if val:
            return val
    return None


def display_name(edge: dict, facility_cls: str) -> str | None:
    """
    What we say 'onto …' — priority per spec.
    Does not fall back to facility generics here (those are for copy templates).
    """
    name = normalize_name(edge.get("name"))
    if name:
        return name
    parent = parent_street(edge)
    if parent:
        return parent
    ref = network_ref(edge)
    if ref:
        return ref
    return None


def generic_facility_label(facility_cls: str) -> str | None:
    return _FACILITY_GENERIC.get(facility_cls)


def continuity_key(edge: dict, facility_cls: str) -> tuple[str, str, str]:
    """
    Anti-spam identity: (normalized parent-or-display, class, network ref).
    """
    parent = parent_street(edge)
    shown = display_name(edge, facility_cls)
    # Prefer parent for tracks that inherit street identity
    label = parent or shown
    ref = network_ref(edge) or ""
    return (_norm_key_part(label), facility_cls, _norm_key_part(ref))


def meaningful_name_change(a: str | None, b: str | None) -> bool:
    ka, kb = _norm_key_part(a), _norm_key_part(b)
    if not ka and not kb:
        return False
    if not ka or not kb:
        # empty -> named or named -> empty: treat as change only if other side meaningful
        return bool(ka or kb)
    return ka != kb
