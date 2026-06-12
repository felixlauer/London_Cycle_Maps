"""
Admissible A* heuristics for main-app routing.
Reward factors are the single source of truth shared with make_weight_optimized in app.py.
"""
import math

TFL_CYCLEWAY_REWARD = 0.75
TFL_QUIETWAY_REWARD = 0.75
GREEN_REWARD = 0.8
R_MIN = 0.1


def haversine_m(lon1, lat1, lon2, lat2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def compute_optimized_cost_per_metre_lower_bound(w: dict) -> float:
    """Per-request lower bound on length × M × R (additive H and A omitted)."""
    m_lb = 1.0
    r_lb = 1.0
    if w.get("tfl_cycleway_weight", 0.0) > 0:
        r_lb *= TFL_CYCLEWAY_REWARD
    if w.get("tfl_quietway_weight", 0.0) > 0:
        r_lb *= TFL_QUIETWAY_REWARD
    if w.get("green_weight", 0.0) > 0:
        r_lb *= GREEN_REWARD
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
