"""
Array-backed edge costs for production routing (v4 sequential).

Load-time numeric tables + timer-style SharedOverlays (parks + live coeffs).
Hot path uses d['_eid'] — no (u,v) edge_index dict.

Kill-switch: ARRAY_COSTS=0|false|no|off → callers fall back to Python weights.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

log = logging.getLogger("edge_cost_arrays")

_SHARED_LOCK = threading.Lock()
_G_REF = None  # NetworkX graph for live bake eid lookup
EDGE_TABLES = None  # EdgeCostTables | None
SHARED_OVERLAYS = None  # SharedOverlays | None


@dataclass
class EdgeCostTables:
    """Load-time numeric edge facts (one row per directed edge). No edge_index."""

    n_edges: int
    length: np.ndarray
    risk: np.ndarray
    vf_flags: np.ndarray
    masks_hill_surface: np.ndarray
    speed_stress: np.ndarray
    is_tfl: np.ndarray
    is_green: np.ndarray
    m_highway: np.ndarray
    barrier_base: np.ndarray
    calming_base: np.ndarray
    signal_base: np.ndarray
    junction_base: np.ndarray
    unlit_base: np.ndarray
    bad_surf_base: np.ndarray
    hard_static: np.ndarray
    hill_base: np.ndarray
    hard_cargo: np.ndarray
    is_park: np.ndarray
    park_oh_id: np.ndarray
    park_oh_exprs: list[str]


@dataclass
class SharedOverlays:
    """Timer-cadence bake (after live refresh / startup)."""

    park_open: np.ndarray
    park_blocked: np.ndarray
    fallback_open: bool
    has_live: bool
    live_closed: np.ndarray
    live_add_coeff: np.ndarray
    live_env_extra: np.ndarray
    live_sev_extra: np.ndarray
    impassable: np.ndarray
    bake_s: float


def array_costs_enabled() -> bool:
    raw = os.environ.get("ARRAY_COSTS", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def get_tables() -> EdgeCostTables | None:
    return EDGE_TABLES


def get_shared_overlays() -> SharedOverlays | None:
    with _SHARED_LOCK:
        return SHARED_OVERLAYS


def set_shared_overlays(shared: SharedOverlays) -> None:
    global SHARED_OVERLAYS
    with _SHARED_LOCK:
        SHARED_OVERLAYS = shared


def _live_soft_coeffs(disruption: dict) -> tuple[float, float, float]:
    add = 0.0
    if disruption.get("is_diversion"):
        add += 5.0
    cat = disruption.get("category", "")
    if cat == "Works":
        add += 3.0
    elif cat in (
        "Collisions",
        "Emergency service incidents",
        "Traffic Incidents",
        "Network delays",
    ):
        add += 2.0
    if disruption.get("temporary_bad_surface"):
        add += 3.0
    env_extra = 0.3 if disruption.get("environmental_hazard") else 0.0
    sev = float(disruption.get("severity_multiplier", 1.0) or 1.0)
    sev_extra = (sev - 1.0) if sev > 1.0 else 0.0
    return add, env_extra, sev_extra


def _parse_edge_coords(G, u, v, d) -> list[list[float]]:
    """[[lat, lon], ...] oriented from u toward v (same as extract_segment_geometry)."""
    from shapely.wkt import loads as load_wkt

    wkt = d.get("geometry")
    if wkt:
        try:
            line = load_wkt(wkt)
            segment_coords = list(line.coords)
            u_x = float(G.nodes[u].get("_x", G.nodes[u]["x"]))
            u_y = float(G.nodes[u].get("_y", G.nodes[u]["y"]))
            start_dist = (segment_coords[0][0] - u_x) ** 2 + (
                segment_coords[0][1] - u_y
            ) ** 2
            end_dist = (segment_coords[-1][0] - u_x) ** 2 + (
                segment_coords[-1][1] - u_y
            ) ** 2
            if end_dist < start_dist:
                segment_coords.reverse()
            return [[float(y), float(x)] for x, y in segment_coords]
        except Exception:
            pass
    nu, nv = G.nodes[u], G.nodes[v]
    return [
        [float(nu.get("_y", nu["y"])), float(nu.get("_x", nu["x"]))],
        [float(nv.get("_y", nv["y"])), float(nv.get("_x", nv["x"]))],
    ]


_GEOM_PREPARSE_STATE = "off"  # off | pending | ready | error
_GEOM_PREPARSE_LOCK = threading.Lock()
_GEOM_PREPARSE_STATS: dict[str, float | int | str] = {}


def geom_preparse_mode() -> str:
    """
    GEOM_PREPARSE env:
      background | 1 | true | yes  → background thread after bootstrap (default)
      sync                         → block bootstrap until all edges parsed
      0 | false | no | off         → leave lazy _coords on first use

    TODO(review): full-graph warm takes ~4 min (~221 s). Decide whether to keep
    background as default vs lazy (off) or a narrower warm set.
    """
    raw = os.environ.get("GEOM_PREPARSE", "background").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return "off"
    if raw in ("sync", "eager", "blocking"):
        return "sync"
    return "background"


def mark_geom_preparse_from_cache(n_edges: int) -> None:
    """Record that `_coords` were loaded from routing cache (skip runtime warm)."""
    global _GEOM_PREPARSE_STATE, _GEOM_PREPARSE_STATS
    with _GEOM_PREPARSE_LOCK:
        _GEOM_PREPARSE_STATE = "ready"
        _GEOM_PREPARSE_STATS = {
            "n_edges": int(n_edges),
            "n_parsed": 0,
            "n_already_cached": int(n_edges),
            "elapsed_s": 0.0,
            "source": "routing_cache",
        }


def get_geom_preparse_state() -> dict:
    with _GEOM_PREPARSE_LOCK:
        return {
            "state": _GEOM_PREPARSE_STATE,
            **dict(_GEOM_PREPARSE_STATS),
        }


def preparse_edge_geometries(G, *, progress_every: int = 500_000) -> dict:
    """
    Parse every edge WKT once into d['_coords'] (lat,lon lists).

    Idempotent: skips edges that already have _coords. Returns stats dict.
    """
    global _GEOM_PREPARSE_STATE, _GEOM_PREPARSE_STATS
    with _GEOM_PREPARSE_LOCK:
        _GEOM_PREPARSE_STATE = "pending"
    t0 = time.perf_counter()
    n_total = 0
    n_parsed = 0
    n_cached = 0
    try:
        for u, v, d in G.edges(data=True):
            n_total += 1
            if d.get("_coords") is not None:
                n_cached += 1
                continue
            d["_coords"] = _parse_edge_coords(G, u, v, d)
            n_parsed += 1
            if progress_every and n_parsed % progress_every == 0:
                log.info(
                    "geom_preparse: %d parsed (%.1f s elapsed)",
                    n_parsed,
                    time.perf_counter() - t0,
                )
        elapsed = time.perf_counter() - t0
        stats = {
            "n_edges": n_total,
            "n_parsed": n_parsed,
            "n_already_cached": n_cached,
            "elapsed_s": round(elapsed, 3),
            "edges_per_s": round(n_parsed / elapsed, 1) if elapsed > 0 else 0.0,
        }
        with _GEOM_PREPARSE_LOCK:
            _GEOM_PREPARSE_STATE = "ready"
            _GEOM_PREPARSE_STATS = stats
        log.info(
            "geom_preparse: done %d parsed / %d edges in %.1f s",
            n_parsed,
            n_total,
            elapsed,
        )
        return stats
    except Exception as exc:
        with _GEOM_PREPARSE_LOCK:
            _GEOM_PREPARSE_STATE = "error"
            _GEOM_PREPARSE_STATS = {"error": str(exc)}
        log.exception("geom_preparse failed")
        raise


def start_geom_preparse_background(G) -> None:
    """Daemon thread: full-graph _coords warm without blocking /route serve."""
    global _GEOM_PREPARSE_STATE
    mode = geom_preparse_mode()
    if mode == "off":
        with _GEOM_PREPARSE_LOCK:
            _GEOM_PREPARSE_STATE = "off"
        return
    if mode == "sync":
        return  # caller runs preparse_edge_geometries synchronously

    with _GEOM_PREPARSE_LOCK:
        _GEOM_PREPARSE_STATE = "pending"

    def _run():
        try:
            preparse_edge_geometries(G)
        except Exception:
            pass

    threading.Thread(target=_run, name="geom-preparse", daemon=True).start()
    log.info("geom_preparse: background thread started")


def stamp_node_xy(G) -> int:
    """Stamp float _x/_y on every node with coordinates. Returns count stamped."""
    n = 0
    for _nid, data in G.nodes(data=True):
        if "x" in data and "y" in data:
            data["_x"] = float(data["x"])
            data["_y"] = float(data["y"])
            n += 1
    return n


def build_edge_cost_tables(
    G,
    *,
    junction_suppressed: frozenset,
    bad_surfaces: frozenset,
    up_thresh: float,
    down_thresh: float,
    is_lit_fn: Callable,
    speed_stress_fn: Callable,
    is_tfl_fn: Callable,
    has_attraction_fn: Callable,
    highway_mult_fn: Callable,
    barrier_penalty_fn: Callable,
    give_way_fn: Callable,
    stop_sign_fn: Callable,
    calming_fn: Callable,
    signal_fn: Callable,
    intersection_fn: Callable,
    mini_rb_fn: Callable,
    is_yes_fn: Callable,
    parse_geometry: bool = True,
) -> tuple[EdgeCostTables, float]:
    """
    One pass: VF flags, cost columns, _eid, optional _coords.
    Requires junction danger flags + JUNCTION_CLUSTER_SUPPRESSED already built.
    """
    from barrier_clusters import (
        CARGO_IMPASSABLE_TAGS,
        CLUSTER_IMPASSABLE,
        barrier_access_denied,
        barrier_cluster_for_tag,
        normalize_barrier_tag,
    )
    from cost_masks import is_service_access_denied, masks_surface_and_hill, vf_flags

    t0 = time.perf_counter()
    edges = list(G.edges(data=True))
    n = len(edges)

    length = np.empty(n, dtype=np.float64)
    risk = np.empty(n, dtype=np.float64)
    vf = np.empty(n, dtype=np.int32)
    masks_hs = np.empty(n, dtype=np.uint8)
    speed = np.empty(n, dtype=np.float64)
    is_tfl = np.empty(n, dtype=np.uint8)
    is_green = np.empty(n, dtype=np.uint8)
    m_hw = np.empty(n, dtype=np.float64)
    barrier_b = np.empty(n, dtype=np.float64)
    calm_b = np.empty(n, dtype=np.float64)
    sig_b = np.empty(n, dtype=np.float64)
    give_b = np.empty(n, dtype=np.float64)
    stop_b = np.empty(n, dtype=np.float64)
    ix_b = np.empty(n, dtype=np.float64)
    mini_b = np.empty(n, dtype=np.float64)
    junc_b = np.empty(n, dtype=np.float64)
    hill_b = np.empty(n, dtype=np.float64)
    hard_svc = np.empty(n, dtype=np.uint8)
    hard_bar = np.empty(n, dtype=np.uint8)
    hard_cargo = np.empty(n, dtype=np.uint8)
    is_park_a = np.empty(n, dtype=np.uint8)
    park_oh_id = np.empty(n, dtype=np.int32)
    is_lit_a = np.empty(n, dtype=np.uint8)
    is_bad = np.empty(n, dtype=np.uint8)
    park_expr_to_id: dict[str, int] = {}
    park_oh_exprs: list[str] = []

    for i, (u, v, d) in enumerate(edges):
        d["_eid"] = i
        flags = int(vf_flags(d))
        d["_vf"] = flags
        vf[i] = flags

        if parse_geometry:
            d["_coords"] = _parse_edge_coords(G, u, v, d)

        length[i] = float(d.get("length", 1.0) or 1.0)
        risk[i] = float(d.get("risk", 0.0) or 0.0)
        g = float(d.get("grade", 0.0) or 0.0)
        is_lit_a[i] = 1 if is_lit_fn(d) else 0
        surf = str(d.get("surface", "")).lower()
        is_bad[i] = 1 if surf in bad_surfaces else 0
        on_steps = masks_surface_and_hill(d)
        masks_hs[i] = 1 if on_steps else 0
        speed[i] = float(speed_stress_fn(d))
        is_tfl[i] = 1 if is_tfl_fn(d) else 0
        is_green[i] = 1 if has_attraction_fn(d) else 0
        m_hw[i] = float(highway_mult_fn(d))
        barrier_b[i] = float(barrier_penalty_fn(d))
        give_b[i] = float(give_way_fn(d))
        stop_b[i] = float(stop_sign_fn(d))
        calm_b[i] = float(calming_fn(d, "both"))

        node_v = G.nodes[v] if v in G.nodes else {}
        if v in junction_suppressed:
            sig_b[i] = 0.0
            ix_b[i] = 0.0
            mini_b[i] = 0.0
            junc_b[i] = 0.0
        else:
            sig_b[i] = float(signal_fn(node_v))
            ix_b[i] = float(intersection_fn(node_v))
            mini_b[i] = float(mini_rb_fn(node_v))
            junc_b[i] = 8.0 if node_v.get("is_dangerous_junction", False) else 0.0

        if on_steps:
            hill_b[i] = 0.0
        else:
            hill_cost = 0.0
            if g > 0:
                work = g * 20.0
                power = (g * 20.0) ** 2 if g > up_thresh else 0.0
                hill_cost = length[i] * (work + power)
            elif g < down_thresh:
                hill_cost = length[i] * 1.5
            hill_b[i] = hill_cost

        hard_svc[i] = 1 if is_service_access_denied(d) else 0
        hard_bar[i] = 1 if (
            barrier_access_denied(d)
            or barrier_cluster_for_tag(normalize_barrier_tag(d.get("barrier")))
            == CLUSTER_IMPASSABLE
        ) else 0
        tag = normalize_barrier_tag(d.get("barrier"))
        hard_cargo[i] = 1 if (tag and tag in CARGO_IMPASSABLE_TAGS) else 0

        park = 1 if is_yes_fn(d.get("is_park")) else 0
        is_park_a[i] = park
        oh = str(d.get("opening_hours", "") or "").strip()
        if park and oh:
            pid = park_expr_to_id.get(oh)
            if pid is None:
                pid = len(park_oh_exprs)
                park_expr_to_id[oh] = pid
                park_oh_exprs.append(oh)
            park_oh_id[i] = pid
        else:
            park_oh_id[i] = -1

    hard_static = ((hard_svc != 0) | (hard_bar != 0)).astype(np.uint8)
    junction_base = give_b + stop_b + ix_b + mini_b + junc_b
    unlit_base = np.where(is_lit_a == 0, 0.5, 0.0).astype(np.float64)
    bad_surf_base = np.where(is_bad != 0, 3.0, 0.0).astype(np.float64)

    elapsed = time.perf_counter() - t0
    tables = EdgeCostTables(
        n_edges=n,
        length=length,
        risk=risk,
        vf_flags=vf,
        masks_hill_surface=masks_hs,
        speed_stress=speed,
        is_tfl=is_tfl,
        is_green=is_green,
        m_highway=m_hw,
        barrier_base=barrier_b,
        calming_base=calm_b,
        signal_base=sig_b,
        junction_base=junction_base,
        unlit_base=unlit_base,
        bad_surf_base=bad_surf_base,
        hard_static=hard_static,
        hill_base=hill_b,
        hard_cargo=hard_cargo,
        is_park=is_park_a,
        park_oh_id=park_oh_id,
        park_oh_exprs=park_oh_exprs,
    )
    return tables, elapsed


def build_shared_overlays(
    tables: EdgeCostTables,
    hours_map: dict,
    fallback_open: bool,
    G=None,
    include_live: bool = True,
) -> SharedOverlays:
    """Bake parks + (optional) live coeffs + impassable. Live eids via G[u][v]['_eid'].

    include_live=False: parks-only overlay for future depart_at (no soft/hard live).
    """
    import live_disruptions
    import park_opening_hours

    t0 = time.perf_counter()
    n = tables.n_edges
    n_expr = len(tables.park_oh_exprs)

    park_open = np.ones(n_expr, dtype=np.uint8)
    for pid, expr in enumerate(tables.park_oh_exprs):
        ed = {"is_park": "yes", "opening_hours": expr}
        park_open[pid] = (
            1 if park_opening_hours.is_park_edge_open(ed, hours_map, fallback_open) else 0
        )

    park_blocked = np.zeros(n, dtype=np.uint8)
    pid_a = tables.park_oh_id
    is_park = tables.is_park != 0
    has_oh = is_park & (pid_a >= 0)
    idx_oh = np.flatnonzero(has_oh)
    if idx_oh.size and n_expr:
        closed = park_open[pid_a[idx_oh]] == 0
        park_blocked[idx_oh[closed]] = 1
    if not fallback_open:
        park_blocked[is_park & (pid_a < 0)] = 1

    live_closed = np.zeros(n, dtype=np.uint8)
    live_add_coeff = np.zeros(n, dtype=np.float64)
    live_env_extra = np.zeros(n, dtype=np.float64)
    live_sev_extra = np.zeros(n, dtype=np.float64)
    has_live = False
    if include_live:
        lookup = live_disruptions.MASTER_LIVE_LOOKUP
        has_live = bool(lookup)
        graph = G if G is not None else _G_REF
        if has_live and graph is not None:
            for (u, v), disruption in lookup.items():
                ed = graph.get_edge_data(u, v)
                if not ed:
                    continue
                i = ed.get("_eid")
                if i is None:
                    continue
                if disruption.get("has_closure") or disruption.get("is_closed"):
                    live_closed[i] = 1
                    continue
                add_c, env_e, sev_e = _live_soft_coeffs(disruption)
                live_add_coeff[i] = add_c
                live_env_extra[i] = env_e
                live_sev_extra[i] = sev_e

    impassable = (
        (tables.hard_static != 0) | (park_blocked != 0) | (live_closed != 0)
    ).astype(np.uint8)

    return SharedOverlays(
        park_open=park_open,
        park_blocked=park_blocked,
        fallback_open=bool(fallback_open),
        has_live=has_live,
        live_closed=live_closed,
        live_add_coeff=live_add_coeff,
        live_env_extra=live_env_extra,
        live_sev_extra=live_sev_extra,
        impassable=impassable,
        bake_s=time.perf_counter() - t0,
    )


def refresh_shared_overlays_from_graph() -> SharedOverlays | None:
    """Rebuild SharedOverlays using current live lookup + London-now park hours."""
    global EDGE_TABLES
    if EDGE_TABLES is None or _G_REF is None:
        return None
    import park_opening_hours

    unique_hours = _G_REF.graph.get("park_opening_hours_unique") or []
    # Prefer table exprs if catalog empty
    if not unique_hours and EDGE_TABLES.park_oh_exprs:
        unique_hours = list(EDGE_TABLES.park_oh_exprs)
    at_time = park_opening_hours.london_now()
    hours_map, fallback_open = park_opening_hours.build_request_hours_context(
        unique_hours, at_time
    )
    shared = build_shared_overlays(
        EDGE_TABLES, hours_map, fallback_open, G=_G_REF
    )
    set_shared_overlays(shared)
    log.info(
        "edge_cost_arrays: shared overlays rebuilt in %.1f ms (live=%s impassable=%d)",
        shared.bake_s * 1000,
        shared.has_live,
        int(shared.impassable.sum()),
    )
    return shared


def install_tables(tables: EdgeCostTables, G) -> None:
    global EDGE_TABLES, _G_REF
    EDGE_TABLES = tables
    _G_REF = G


def make_array_cost_by_eid_fastest(
    tables: EdgeCostTables,
    hard_cost: float,
    shared: SharedOverlays,
    bike_type: str = "standard",
):
    """Return cost(eid: int) -> float (CSR / Numba-friendly)."""
    cargo = str(bike_type) == "cargo"
    length_a = tables.length
    mhw_a = tables.m_highway
    hard_cargo = tables.hard_cargo
    impassable = shared.impassable

    def cost(i: int) -> float:
        if i < 0:
            return hard_cost
        if impassable[i]:
            return hard_cost
        if cargo and hard_cargo[i]:
            return hard_cost
        return length_a[i] * mhw_a[i]

    return cost


def make_array_weight_fn_fastest(
    tables: EdgeCostTables,
    hard_cost: float,
    shared: SharedOverlays,
    bike_type: str = "standard",
):
    cost = make_array_cost_by_eid_fastest(tables, hard_cost, shared, bike_type=bike_type)

    def weight_fn(_u, _v, d):
        i = d.get("_eid")
        if i is None:
            return hard_cost
        return cost(int(i))

    return weight_fn


def make_array_cost_by_eid_optimized(
    tables: EdgeCostTables,
    w: dict,
    shared: SharedOverlays,
    *,
    hard_cost: float,
    m_min: float,
    r_min: float,
):
    """Return cost(eid: int) -> float matching make_array_weight_fn_optimized."""
    from cost_masks import vf_allowed_masks
    from routing_heuristic import (
        green_reward,
        tfl_network_reward,
        vehicular_free_reward,
    )

    w_risk = float(w.get("risk_weight", 0.0))
    w_light = float(w.get("light_weight", 0.0))
    w_surface = float(w.get("surface_weight", 0.0))
    w_hill = float(w.get("hill_weight", 0.0))
    w_tfl = float(w.get("tfl_cycleway_weight", 0.0))
    w_speed = float(w.get("speed_weight", 0.0))
    w_green = float(w.get("green_weight", 0.0))
    w_barrier = float(w.get("barrier_weight", 0.0))
    w_calming = float(w.get("calming_weight", 0.0))
    w_junction = float(w.get("junction_weight", 0.0))
    w_signal = float(w.get("signal_weight", 0.0))
    w_live = float(w.get("tfl_live_weight", 0.0))
    w_live_cap = min(w_live, 1.0)
    w_vf = float(w.get("vehicular_free_weight", 0.0))
    cargo = str(w.get("bike_type", "standard")) == "cargo"
    apply_live_soft = shared.has_live and w_live > 0.0

    r_tfl = tfl_network_reward(w_tfl) if w_tfl > 0 else 1.0
    r_green = green_reward(w_green) if w_green > 0 else 1.0
    r_vf = vehicular_free_reward(w_vf) if w_vf > 0 else 1.0
    tfl_on = w_tfl > 0
    green_on = w_green > 0
    vf_on = w_vf > 0

    vf_mask, vf_reward = vf_allowed_masks(
        shared_path=bool(w.get("vf_shared_path", True)),
        bus_lane=bool(w.get("vf_bus_lane", True)),
        painted_lane=bool(w.get("vf_painted_lane", False)),
    )

    length_a = tables.length
    risk_a = tables.risk
    vf_a = tables.vf_flags
    steps_a = tables.masks_hill_surface
    speed_a = tables.speed_stress
    tfl_a = tables.is_tfl
    green_a = tables.is_green
    mhw_a = tables.m_highway
    bar_a = tables.barrier_base
    junc_a = tables.junction_base
    unlit_a = tables.unlit_base
    bad_a = tables.bad_surf_base
    calm_a = tables.calming_base
    sig_a = tables.signal_base
    hill_a = tables.hill_base
    hard_cargo = tables.hard_cargo
    impassable = shared.impassable
    live_add_c = shared.live_add_coeff
    live_env_e = shared.live_env_extra
    live_sev_e = shared.live_sev_extra

    def cost(i: int) -> float:
        if i < 0:
            return hard_cost
        if impassable[i]:
            return hard_cost
        if cargo and hard_cargo[i]:
            return hard_cost

        edge_vf = int(vf_a[i])
        vehicular_free = bool(edge_vf & vf_mask)
        on_steps = bool(steps_a[i])

        risk_p = 0.0 if vehicular_free else risk_a[i] * w_risk
        light_p = unlit_a[i] * w_light
        surf_p = 0.0 if on_steps else bad_a[i] * w_surface
        speed_m = 0.0 if vehicular_free else speed_a[i] * w_speed
        m_total = max(m_min, 1.0 + risk_p + light_p + surf_p + speed_m)

        if apply_live_soft:
            m_total = m_total + live_add_c[i] * w_live
            m_total *= 1.0 + live_env_e[i] * w_live_cap
            m_total *= 1.0 + live_sev_e[i] * w_live_cap

        r = 1.0
        if tfl_on and tfl_a[i]:
            r *= r_tfl
        if green_on and green_a[i]:
            r *= r_green
        if vf_on and (edge_vf & vf_reward):
            r *= r_vf
        r = max(r_min, r)

        a_total = (
            bar_a[i] * w_barrier
            + junc_a[i] * w_junction
            + sig_a[i] * w_signal
            + (0.0 if vehicular_free else calm_a[i] * w_calming)
        )
        h = hill_a[i] * w_hill
        return (length_a[i] * m_total * mhw_a[i] * r) + a_total + h

    return cost


def make_array_weight_fn_optimized(
    tables: EdgeCostTables,
    w: dict,
    shared: SharedOverlays,
    *,
    hard_cost: float,
    m_min: float,
    r_min: float,
):
    cost = make_array_cost_by_eid_optimized(
        tables, w, shared, hard_cost=hard_cost, m_min=m_min, r_min=r_min
    )

    def weight_fn(_u, _v, d):
        i = d.get("_eid")
        if i is None:
            return hard_cost
        return cost(int(i))

    return weight_fn
