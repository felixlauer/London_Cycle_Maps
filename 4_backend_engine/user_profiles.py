"""
Local mock user profile store for profile-driven routing (schema v2).

Weights are on the sweep/multiplier scale with per-weight caps (see WEIGHT_CAPS,
kept in sync with preset_config.json). Profiles additionally carry bike_type,
preset id, and toggle answers from the preset wizard.

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
    "vehicular_free_weight",
    "speed_weight",
    "green_weight",
    "barrier_weight",
    "calming_weight",
    "junction_weight",
    "signal_weight",
    "tfl_live_weight",
)

# Sweep-scale caps (single runtime source: preset_config.json; these are the
# fallback and must match generate_preset_config.WEIGHT_CAPS).
_FALLBACK_WEIGHT_CAPS = {
    "signal_weight": 2.0,
    "speed_weight": 2.0,
    "junction_weight": 3.0,
    "risk_weight": 2.0,
    "hill_weight": 3.0,
    "calming_weight": 1.5,
    "barrier_weight": 1.5,
    "green_weight": 1.0,
    "vehicular_free_weight": 3.0,
    "tfl_cycleway_weight": 1.0,
    "light_weight": 1.0,
    "surface_weight": 1.0,
    "tfl_live_weight": 1.0,
}

CALMING_SOURCE = "both"
WEIGHT_MIN = 0.0
EPSILON = 0.0001

BIKE_TYPES = ("standard", "road", "ebike", "cargo")
BIKE_SPEEDS_KMH = {"standard": 15.0, "road": 21.0, "ebike": 18.0, "cargo": 15.0}
DEFAULT_BIKE_TYPE = "standard"

DEFAULT_TOGGLES = {
    "light_night": False,
    "surface": False,
    "jam_comfort": True,
    "vf_infrastructure": {"shared_path": True, "bus_lane": True, "painted_lane": False},
}

_BASE_DIR = os.path.dirname(__file__)
_PROFILES_PATH = os.path.join(_BASE_DIR, "user_profiles.json")
_PRESET_CONFIG_PATH = os.path.join(_BASE_DIR, "preset_config.json")


def _load_weight_caps() -> dict[str, float]:
    try:
        with open(_PRESET_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        caps = cfg.get("weight_caps") or {}
        if all(k in caps for k in ROUTING_WEIGHT_KEYS):
            return {k: float(caps[k]) for k in ROUTING_WEIGHT_KEYS}
    except (OSError, ValueError):
        pass
    return dict(_FALLBACK_WEIGHT_CAPS)


WEIGHT_CAPS = _load_weight_caps()


def load_preset_config() -> dict | None:
    try:
        with open(_PRESET_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def clamp_weight(key: str, value: float) -> float:
    cap = WEIGHT_CAPS.get(key, 1.0)
    return max(WEIGHT_MIN, min(cap, float(value)))


def clamp_weights(weights: dict) -> dict:
    return {key: clamp_weight(key, weights.get(key, 0.0)) for key in ROUTING_WEIGHT_KEYS}


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
        cap = WEIGHT_CAPS.get(key, 1.0)
        if val < WEIGHT_MIN or val > cap:
            return False, f"{key} must be between {WEIGHT_MIN} and {cap}"
    extra = set(weights.keys()) - set(ROUTING_WEIGHT_KEYS)
    if extra:
        return False, f"unknown weight keys: {', '.join(sorted(extra))}"
    return True, None


def _normalize_toggles(toggles: Any) -> dict:
    out = {
        "light_night": bool((toggles or {}).get("light_night", False)),
        "surface": bool((toggles or {}).get("surface", False)),
        "jam_comfort": bool((toggles or {}).get("jam_comfort", True)),
    }
    vf = (toggles or {}).get("vf_infrastructure") or {}
    out["vf_infrastructure"] = {
        "shared_path": bool(vf.get("shared_path", True)),
        "bus_lane": bool(vf.get("bus_lane", True)),
        "painted_lane": bool(vf.get("painted_lane", False)),
    }
    return out


def _normalize_bike_type(bike_type: Any) -> str:
    bt = str(bike_type or DEFAULT_BIKE_TYPE).strip().lower()
    return bt if bt in BIKE_TYPES else DEFAULT_BIKE_TYPE


def _load_store() -> dict:
    if not os.path.isfile(_PROFILES_PATH):
        return {"schema": 2, "profiles": {}}
    with open(_PROFILES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {"schema": 2, "profiles": {}}


def _save_store(data: dict) -> None:
    data["schema"] = 2
    profiles = data.get("profiles", {})
    for entry in profiles.values():
        if "weights" in entry:
            entry["weights"] = clamp_weights(entry["weights"])
        entry["bike_type"] = _normalize_bike_type(entry.get("bike_type"))
        entry["toggles"] = _normalize_toggles(entry.get("toggles"))
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
    return [
        {
            "id": pid,
            "name": entry.get("name", pid),
            "preset": entry.get("preset"),
            "bike_type": _normalize_bike_type(entry.get("bike_type")),
        }
        for pid, entry in sorted(profiles.items())
    ]


def get_profile(user_id: str) -> dict[str, Any] | None:
    store = _load_store()
    entry = store.get("profiles", {}).get(user_id)
    if not entry:
        return None
    return {
        "id": user_id,
        "name": entry.get("name", user_id),
        "preset": entry.get("preset"),
        "bike_type": _normalize_bike_type(entry.get("bike_type")),
        "toggles": _normalize_toggles(entry.get("toggles")),
        "weights": clamp_weights(entry.get("weights", {})),
    }


def get_profile_weights(user_id: str) -> dict[str, float] | None:
    profile = get_profile(user_id)
    if not profile:
        return None
    return profile["weights"]


def create_profile(
    name: str,
    weights: dict,
    bike_type: str | None = None,
    preset: str | None = None,
    toggles: dict | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
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

    profiles[user_id] = {
        "name": name,
        "preset": (str(preset).strip().lower() or None) if preset else None,
        "bike_type": _normalize_bike_type(bike_type),
        "toggles": _normalize_toggles(toggles),
        "weights": {key: float(weights[key]) for key in ROUTING_WEIGHT_KEYS},
    }
    _save_store(store)
    return get_profile(user_id), None


def build_weight_dict_from_request(args, defaults: dict | None = None) -> dict:
    """Parse explicit query-param weights; clamp each to [0, cap] on the sweep scale."""
    base = defaults or {key: 0.0 for key in ROUTING_WEIGHT_KEYS}
    w = {}
    for key in ROUTING_WEIGHT_KEYS:
        if key in args and args.get(key) is not None and str(args.get(key)).strip() != "":
            w[key] = clamp_weight(key, float(args.get(key)))
        else:
            w[key] = clamp_weight(key, base.get(key, 0.0))
    w["calming_source"] = CALMING_SOURCE
    return w
