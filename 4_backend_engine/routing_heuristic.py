"""
Admissible A* heuristics for main-app routing.

Reward formulas are the single source of truth shared with make_weight_optimized
in app.py: any change here changes both the cost function and the heuristic lower
bound in lockstep (admissibility). Rewards are multiplicative R < 1 on length with
per-reward saturation floors so weight-at-cap saturates instead of driving R
toward R_MIN (keeps the heuristic tight - see plan review notes).
"""
import math

# Saturation floors: deepest possible reward multiplier per reward type.
TFL_NETWORK_REWARD_FLOOR = 0.55   # cycleways + superhighways + quietways (merged)
GREEN_REWARD_FLOOR = 0.6
VEHICULAR_FREE_REWARD_FLOOR = 0.55

# Weight caps on the sweep scale (mirror user_profiles.WEIGHT_CAPS for these keys).
TFL_NETWORK_WEIGHT_CAP = 1.0
GREEN_WEIGHT_CAP = 1.0
VEHICULAR_FREE_WEIGHT_CAP = 3.0

R_MIN = 0.1
M_MIN = 0.1

PENALTY_FLOOR_KEYS = (
    "risk_weight",
    "light_weight",
    "surface_weight",
    "speed_weight",
)

PENALTY_FLOORS: dict[str, float] = {k: 0.0 for k in PENALTY_FLOOR_KEYS}


def set_penalty_floors(floors: dict[str, float]) -> None:
    """Set graph-wide admissible penalty floors (from app bootstrap)."""
    global PENALTY_FLOORS
    PENALTY_FLOORS = {k: float(floors.get(k, 0.0)) for k in PENALTY_FLOOR_KEYS}


def _lerp_reward(weight: float, floor: float, cap: float) -> float:
    """R = 1 at weight 0, linearly down to `floor` at `cap` (saturates beyond)."""
    t = min(max(float(weight), 0.0), cap) / cap
    return 1.0 - (1.0 - floor) * t


def tfl_network_reward(weight: float) -> float:
    """Reward multiplier for the merged TfL network (cycleway/superhighway/quietway)."""
    return _lerp_reward(weight, TFL_NETWORK_REWARD_FLOOR, TFL_NETWORK_WEIGHT_CAP)


def green_reward(weight: float) -> float:
    """Reward multiplier for green/scenic edges (parks, river, sights)."""
    return _lerp_reward(weight, GREEN_REWARD_FLOOR, GREEN_WEIGHT_CAP)


def vehicular_free_reward(weight: float) -> float:
    """Reward multiplier for segregated cycling infrastructure."""
    return _lerp_reward(weight, VEHICULAR_FREE_REWARD_FLOOR, VEHICULAR_FREE_WEIGHT_CAP)


def haversine_m(lon1, lat1, lon2, lat2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def compute_optimized_cost_per_metre_lower_bound(w: dict) -> float:
    """Per-request lower bound on length × M × R (additive H and A omitted).

    m_lb uses graph-wide penalty floors (see set_penalty_floors). Floors must be 0
    whenever any edge has zero penalty for that type (admissibility). On the London
    graph this usually leaves m_lb at 1.0 - same effective h as when penalties were
    omitted from the heuristic entirely.

    r_lb multiplies the deepest reward each active weight can produce, using the
    exact same reward functions as make_weight_optimized.
    """
    m_lb = 1.0
    for key in PENALTY_FLOOR_KEYS:
        weight = w.get(key, 0.0)
        if weight > 0:
            m_lb += weight * PENALTY_FLOORS.get(key, 0.0)
    m_lb = max(M_MIN, m_lb)

    r_lb = 1.0
    w_tfl = w.get("tfl_cycleway_weight", 0.0)
    if w_tfl > 0:
        r_lb *= tfl_network_reward(w_tfl)
    w_green = w.get("green_weight", 0.0)
    if w_green > 0:
        r_lb *= green_reward(w_green)
    w_vf = w.get("vehicular_free_weight", 0.0)
    if w_vf > 0:
        r_lb *= vehicular_free_reward(w_vf)
    r_lb = max(R_MIN, r_lb)
    return m_lb * r_lb


def make_heuristic(goal_node, G, cost_per_m: float = 1.0):
    """NetworkX A* heuristic: h(u, v) with v the goal node."""
    goal_lon = float(G.nodes[goal_node]["x"])
    goal_lat = float(G.nodes[goal_node]["y"])
    scale = float(cost_per_m)

    def heuristic(u, v):
        nd = G.nodes[u]
        return haversine_m(float(nd["x"]), float(nd["y"]), goal_lon, goal_lat) * scale

    return heuristic
