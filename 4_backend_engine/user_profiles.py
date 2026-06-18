"""
Local mock user profile store for profile-driven routing.
Weights are activation scalars in [0.0, 1.0] only (0%–100% of each routing factor).
When changing schema or API, update 0_documentation/APP_MAIN.md.
"""
import json
import os
import re
import tempfile
from typing import Any

ROUTING_WEIGHT_KEYS = (
    "risk_weight",
    "light_weight",
    "surface_weight",
    "hill_weight",
    "tfl_cycleway_weight",
    "tfl_quietway_weight",
    "speed_weight",
    "width_weight",
    "green_weight",
    "barrier_weight",
    "calming_weight",
    "junction_weight",
    "signal_weight",
    "tfl_live_weight",
)

CALMING_SOURCE = "both"
WEIGHT_MIN = 0.0
WEIGHT_MAX = 1.0

_PROFILES_PATH = os.path.join(os.path.dirname(__file__), "user_profiles.json")


def clamp_weight(value: float) -> float:
    return max(WEIGHT_MIN, min(WEIGHT_MAX, float(value)))


def clamp_weights(weights: dict) -> dict:
    return {key: clamp_weight(weights.get(key, 0.0)) for key in ROUTING_WEIGHT_KEYS}


def validate_weights(weights: dict) -> tuple[bool, str | None]:
    if not isinstance(weights, dict):
        return False, "weights must be an object"
    for key in ROUTING_WEIGHT_KEYS:
        if key not in weights:
            return False, f"missing weight key: {key}"
        try:
            val = float(weights[key])
        except (TypeError, ValueError):
            return False, f"{key} must be a number"
        if val < WEIGHT_MIN or val > WEIGHT_MAX:
            return False, f"{key} must be between {WEIGHT_MIN} and {WEIGHT_MAX}"
    extra = set(weights.keys()) - set(ROUTING_WEIGHT_KEYS)
    if extra:
        return False, f"unknown weight keys: {', '.join(sorted(extra))}"
    return True, None


def _load_store() -> dict:
    if not os.path.isfile(_PROFILES_PATH):
        return {"profiles": {}}
    with open(_PROFILES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {"profiles": {}}


def _save_store(data: dict) -> None:
    profiles = data.get("profiles", {})
    for entry in profiles.values():
        if "weights" in entry:
            entry["weights"] = clamp_weights(entry["weights"])
    dir_name = os.path.dirname(_PROFILES_PATH)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp_path, _PROFILES_PATH)
    except Exception:
        if os.path.isfile(tmp_path):
            os.remove(tmp_path)
        raise


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "profile"


def list_profiles() -> list[dict[str, str]]:
    store = _load_store()
    profiles = store.get("profiles", {})
    return [{"id": pid, "name": entry.get("name", pid)} for pid, entry in sorted(profiles.items())]


def get_profile(user_id: str) -> dict[str, Any] | None:
    store = _load_store()
    entry = store.get("profiles", {}).get(user_id)
    if not entry:
        return None
    weights = clamp_weights(entry.get("weights", {}))
    return {
        "id": user_id,
        "name": entry.get("name", user_id),
        "weights": weights,
    }


def get_profile_weights(user_id: str) -> dict[str, float] | None:
    profile = get_profile(user_id)
    if not profile:
        return None
    return profile["weights"]


def create_profile(name: str, weights: dict) -> tuple[dict[str, Any] | None, str | None]:
    name = (name or "").strip()
    if not name:
        return None, "name is required"
    ok, err = validate_weights(weights)
    if not ok:
        return None, err

    store = _load_store()
    profiles = store.setdefault("profiles", {})
    base_id = _slugify(name)
    user_id = base_id
    n = 2
    while user_id in profiles:
        user_id = f"{base_id}_{n}"
        n += 1

    normalized = {key: float(weights[key]) for key in ROUTING_WEIGHT_KEYS}
    profiles[user_id] = {"name": name, "weights": normalized}
    _save_store(store)
    return get_profile(user_id), None


def build_weight_dict_from_request(args, defaults: dict | None = None) -> dict:
    """Parse explicit query-param weights; clamp each to [0.0, 1.0]."""
    base = defaults or {key: 0.0 for key in ROUTING_WEIGHT_KEYS}
    w = {}
    for key in ROUTING_WEIGHT_KEYS:
        if key in args and args.get(key) is not None and str(args.get(key)).strip() != "":
            w[key] = clamp_weight(float(args.get(key)))
        else:
            w[key] = clamp_weight(base.get(key, 0.0))
    w["calming_source"] = CALMING_SOURCE
    return w
