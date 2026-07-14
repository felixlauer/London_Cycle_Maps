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

# Production default: bounded-suboptimal A* (cost <= (1+eps) x optimal). Verified
# 2026-07-09: exact path match vs eps=0.5 on routes 1 and 10 (Safe preset).
# Override with ROUTE_HEURISTIC_EPSILON env.
DEFAULT_ROUTE_HEURISTIC_EPSILON = 0.75


def get_route_heuristic_epsilon() -> float:
    """ROUTE_HEURISTIC_EPSILON env overrides; else DEFAULT_ROUTE_HEURISTIC_EPSILON."""
    import os

    raw = os.environ.get("ROUTE_HEURISTIC_EPSILON")
    if raw is None or not str(raw).strip():
        return DEFAULT_ROUTE_HEURISTIC_EPSILON
    try:
        return max(0.0, float(raw))
    except ValueError:
        return DEFAULT_ROUTE_HEURISTIC_EPSILON


# Fastest leg: admissible scale is 1.0 (cost ≈ length × M_highway, M_highway ≥ 1).
# Default 0 keeps exact shortest/fastest. Override with ROUTE_FASTEST_HEURISTIC_EPSILON.
DEFAULT_ROUTE_FASTEST_HEURISTIC_EPSILON = 0.0


def get_route_fastest_heuristic_epsilon() -> float:
    """ROUTE_FASTEST_HEURISTIC_EPSILON env; default 0 (exact fastest path)."""
    import os

    raw = os.environ.get("ROUTE_FASTEST_HEURISTIC_EPSILON")
    if raw is None or not str(raw).strip():
        return DEFAULT_ROUTE_FASTEST_HEURISTIC_EPSILON
    try:
        return max(0.0, float(raw))
    except ValueError:
        return DEFAULT_ROUTE_FASTEST_HEURISTIC_EPSILON

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


def _node_xy(nd) -> tuple[float, float]:
    """Prefer bootstrap-stamped floats _x/_y; fall back to x/y."""
    if "_x" in nd and "_y" in nd:
        return nd["_x"], nd["_y"]
    return float(nd["x"]), float(nd["y"])


def make_heuristic(goal_node, G, cost_per_m: float = 1.0, csr=None):
    """A* heuristic: h(u, v) with v the goal node.

    When ``csr`` is provided (Phase B), uses dense lat/lon radian arrays instead
    of ``G.nodes[u]`` attr lookups. Values match ``haversine_m`` within float noise.
    """
    scale = float(cost_per_m)
    if csr is not None:
        t = csr.node_to_idx.get(goal_node)
        if t is None:
            raise KeyError(f"goal_node {goal_node!r} not in CSR")
        goal_lon_rad = float(csr.lon_rad[t])
        goal_lat_rad = float(csr.lat_rad[t])
        goal_cos = float(csr.cos_lat[t])
        node_to_idx = csr.node_to_idx
        lat_rad = csr.lat_rad
        lon_rad = csr.lon_rad
        cos_lat = csr.cos_lat

        def heuristic(u, _v):
            ui = node_to_idx[u]
            p1 = float(lat_rad[ui])
            dl = float(lon_rad[ui]) - goal_lon_rad
            dp = p1 - goal_lat_rad
            a = (
                math.sin(dp * 0.5) ** 2
                + float(cos_lat[ui]) * goal_cos * math.sin(dl * 0.5) ** 2
            )
            return scale * (2.0 * 6371000.0 * math.asin(min(1.0, math.sqrt(a))))

        return heuristic

    goal_lon, goal_lat = _node_xy(G.nodes[goal_node])

    def heuristic(u, v):
        lon, lat = _node_xy(G.nodes[u])
        return haversine_m(lon, lat, goal_lon, goal_lat) * scale

    return heuristic


def make_heuristic_xy(goal_node, G, cost_per_m: float = 1.0, csr=None):
    """Alias for make_heuristic (uses stamped _x/_y or CSR arrays when present)."""
    return make_heuristic(goal_node, G, cost_per_m=cost_per_m, csr=csr)


def make_backward_heuristic(start_node, G, cost_per_m: float = 1.0, csr=None):
    """Bidirectional backward frontier: h(u) = haversine(u, start) * scale."""
    scale = float(cost_per_m)
    if csr is not None:
        s = csr.node_to_idx.get(start_node)
        if s is None:
            raise KeyError(f"start_node {start_node!r} not in CSR")
        start_lon_rad = float(csr.lon_rad[s])
        start_lat_rad = float(csr.lat_rad[s])
        start_cos = float(csr.cos_lat[s])
        node_to_idx = csr.node_to_idx
        lat_rad = csr.lat_rad
        lon_rad = csr.lon_rad
        cos_lat = csr.cos_lat

        def heuristic(u, _v):
            ui = node_to_idx[u]
            p1 = float(lat_rad[ui])
            dl = float(lon_rad[ui]) - start_lon_rad
            dp = p1 - start_lat_rad
            a = (
                math.sin(dp * 0.5) ** 2
                + float(cos_lat[ui]) * start_cos * math.sin(dl * 0.5) ** 2
            )
            return scale * (2.0 * 6371000.0 * math.asin(min(1.0, math.sqrt(a))))

        return heuristic

    start_lon, start_lat = _node_xy(G.nodes[start_node])

    def heuristic(u, _v):
        lon, lat = _node_xy(G.nodes[u])
        return haversine_m(lon, lat, start_lon, start_lat) * scale

    return heuristic


def get_route_algorithm() -> str:
    """ROUTE_ALGORITHM env: 'uni' (default) or 'bi'. Request ?alg= overrides at call site."""
    import os

    raw = os.environ.get("ROUTE_ALGORITHM", "uni").strip().lower()
    return "bi" if raw in ("bi", "bidirectional", "bidir") else "uni"
