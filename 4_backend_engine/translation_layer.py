"""
Preset translation layer: dependency-matrix clamping of toxic weight combos.

weight_dependencies/weight_couplings.json is the single authored source of
mode_dominant, trigger and guardrail data (loaded once at import). On each
route request with a preset, antagonistic/floor triggers are evaluated against
the resolved weight vector; when a toxic combination trips, the weight that is
NOT mode_dominant[preset] is clamped just outside its trigger threshold so the
dominant weight's intent survives. All clamps are returned for the /route meta
(debugging + frontend display).

Custom profiles without a preset are not clamped - the wizard shows conflict
warnings instead (derived into preset_config.json by generate_preset_config.py).
"""
from __future__ import annotations

import json
import os

_COUPLINGS_PATH = os.path.join(
    os.path.dirname(__file__), "weight_dependencies", "weight_couplings.json"
)

CLAMPABLE_TYPES = ("antagonistic", "floor")
# Keys retired in profile schema v2 (width dropped, quietway merged into cycleway);
# couplings referencing them cannot be evaluated against the live weight vector.
RETIRED_WEIGHT_KEYS = frozenset({"width_weight", "tfl_quietway_weight"})
# How far below a gte-threshold the loser is clamped (keeps the effect as close
# to the user's intent as possible while exiting the toxic region).
GTE_CLAMP_STEP = 0.0001


def _load_couplings() -> list[dict]:
    with open(_COUPLINGS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    out = []
    for c in data.get("couplings", []):
        if c.get("type") not in CLAMPABLE_TYPES:
            continue
        if len(c.get("weights", [])) != 2 or not c.get("mode_dominant"):
            continue
        if not c.get("trigger"):
            continue
        if RETIRED_WEIGHT_KEYS & set(c["weights"]):
            continue
        out.append(c)
    return out


_COUPLINGS: list[dict] = _load_couplings()


def _condition_met(value: float, cond: dict) -> bool:
    if "gte" in cond and not (value >= float(cond["gte"])):
        return False
    if "lt" in cond and not (value < float(cond["lt"])):
        return False
    return True


def _trigger_tripped(weights: dict, trigger: dict) -> bool:
    for key, cond in trigger.items():
        if not _condition_met(float(weights.get(key, 0.0)), cond):
            return False
    return True


def _clamp_out_of_trigger(value: float, cond: dict) -> float | None:
    """Smallest change to `value` that makes its trigger condition false."""
    if "gte" in cond:
        threshold = float(cond["gte"])
        if value >= threshold:
            return max(0.0, threshold - GTE_CLAMP_STEP)
    if "lt" in cond:
        threshold = float(cond["lt"])
        if value < threshold:
            return threshold
    return None


def apply_preset_clamps(weights: dict, preset: str | None) -> tuple[dict, list[dict]]:
    """Clamp non-dominant weights of tripped couplings for the given preset.

    Returns (adjusted weights dict, clamp log). Clamps apply sequentially in
    file order on a working copy, so a clamp can also untrip later couplings.
    """
    if not preset:
        return dict(weights), []

    w = dict(weights)
    clamps: list[dict] = []
    for c in _COUPLINGS:
        dominant = (c.get("mode_dominant") or {}).get(preset)
        if not dominant or dominant not in c["weights"]:
            continue
        if not _trigger_tripped(w, c["trigger"]):
            continue
        loser = next(k for k in c["weights"] if k != dominant)
        cond = c["trigger"].get(loser)
        if not cond:
            continue  # trigger only constrains the dominant weight; nothing to clamp
        old = float(w.get(loser, 0.0))
        new = _clamp_out_of_trigger(old, cond)
        if new is None or new == old:
            continue
        w[loser] = new
        clamps.append({
            "coupling_id": c["id"],
            "preset": preset,
            "dominant": dominant,
            "clamped_weight": loser,
            "from": round(old, 4),
            "to": round(new, 4),
        })
    return w, clamps


def coupling_count() -> int:
    return len(_COUPLINGS)
