"""
Admissible A* heuristics for main-app routing.
Reward factors are the single source of truth shared with make_weight_optimized in app.py.
"""
import math

TFL_CYCLEWAY_REWARD = 0.75
TFL_QUIETWAY_REWARD = 0.75
GREEN_REWARD = 0.8
VEHICULAR_FREE_REWARD = 0.85
R_MIN = 0.1
M_MIN = 0.1

PENALTY_FLOOR_KEYS = (
    "risk_weight",
    "light_weight",
    "surface_weight",
    "speed_weight",
    "width_weight",
)

PENALTY_FLOORS: dict[str, float] = {k: 0.0 for k in PENALTY_FLOOR_KEYS}


def set_penalty_floors(floors: dict[str, float]) -> None:
    """Set graph-wide admissible penalty floors (from app bootstrap)."""
    global PENALTY_FLOORS
    PENALTY_FLOORS = {k: float(floors.get(k, 0.0)) for k in PENALTY_FLOOR_KEYS}


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
    graph this usually leaves m_lb at 1.0 — same effective h as when penalties were
    omitted from the heuristic entirely.
    """
    m_lb = 1.0
    for key in PENALTY_FLOOR_KEYS:
        weight = w.get(key, 0.0)
        if weight > 0:
            m_lb += weight * PENALTY_FLOORS.get(key, 0.0)
    m_lb = max(M_MIN, m_lb)

    r_lb = 1.0
    if w.get("tfl_cycleway_weight", 0.0) > 0:
        r_lb *= TFL_CYCLEWAY_REWARD
    if w.get("tfl_quietway_weight", 0.0) > 0:
        r_lb *= TFL_QUIETWAY_REWARD
    if w.get("green_weight", 0.0) > 0:
        r_lb *= GREEN_REWARD
    w_vf = w.get("vehicular_free_weight", 0.0)
    if w_vf > 0:
        r_lb *= 1.0 - (1.0 - VEHICULAR_FREE_REWARD) * w_vf
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
