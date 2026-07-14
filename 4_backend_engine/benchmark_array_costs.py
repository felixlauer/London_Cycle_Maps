#!/usr/bin/env python3
"""
Benchmark array-backed edge costs vs production make_weight_optimized.

Simulates load-time numeric tables + request-time weight application on all 11
standard test routes (safe + fast), production-style uni A*.

Backends compared:
  - python   — make_weight_optimized (baseline)
  - array v1 — numeric tables + dict (u,v) index + live dict + park string check
  - array v2 — thinned: d['_eid'], park open uint8 by hours id, live arrays
               scaled by w_live at bake (per request)
  - array v3 — shared timer-style bake: fused impassable[], park_blocked[],
               live *coefficients* (add_coeff / mult_extra) × request w_live,
               fused junction/unlit/surface bases. Jam-comfort is a scalar, not
               a second full cost array.

  cd c:\\London_Cycle_Maps
  python 4_backend_engine/benchmark_array_costs.py

Writes:
  0_documentation/testing/array_costs_report.md
  0_documentation/testing/array_costs_report.json

See: 0_documentation/route_generation_performance.md
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import types
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "4_backend_engine"
TEST_ROUTES_PATH = REPO_ROOT / "6_verification" / "test_routes.txt"
REPORT_DIR = REPO_ROOT / "0_documentation" / "testing"
REPORT_MD = REPORT_DIR / "array_costs_report.md"
REPORT_JSON = REPORT_DIR / "array_costs_report.json"

sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(REPO_ROOT / "3_pipeline"))

os.environ.setdefault("FLASK_USE_RELOADER", "0")
os.environ.setdefault("SKIP_DISRUPTION_FETCH", "1")

# Cost parity: relative + absolute tolerance on path total cost.
COST_RTOL = 1e-6
COST_ATOL = 1e-3


def _mock_flask():
    flask = types.ModuleType("flask")

    class _Flask:
        def __init__(self, *args, **kwargs):
            pass

        def route(self, *args, **kwargs):
            def decorator(fn):
                return fn

            return decorator

        def before_request(self, fn):
            return fn

    flask.Flask = _Flask
    flask.request = types.SimpleNamespace(args={})
    flask.g = types.SimpleNamespace()
    flask.jsonify = lambda x: x
    sys.modules["flask"] = flask

    cors = types.ModuleType("flask_cors")
    cors.CORS = lambda *args, **kwargs: None
    sys.modules["flask_cors"] = cors


def parse_test_routes(path: Path = TEST_ROUTES_PATH) -> list[dict]:
    routes = []
    current_name = None
    coords: list[tuple[float, float]] = []

    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            m = re.match(r"route\s+\d+:\s*(.+)", line, re.IGNORECASE)
            if m:
                if current_name and len(coords) >= 2:
                    routes.append(_route_dict(current_name, coords))
                current_name = line
                coords = []
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) == 2:
                coords.append((float(parts[0]), float(parts[1])))

    if current_name and len(coords) >= 2:
        routes.append(_route_dict(current_name, coords))
    return routes


def _route_dict(name: str, coords: list[tuple[float, float]]) -> dict:
    return {
        "name": name,
        "start_lat": coords[0][0],
        "start_lon": coords[0][1],
        "end_lat": coords[1][0],
        "end_lon": coords[1][1],
    }


def load_preset_weights() -> dict[str, dict]:
    path = BACKEND_DIR / "user_profiles.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out = {}
    for key, label in (("preset_fast", "fast"), ("preset_safe", "safe")):
        w = dict(data["profiles"][key]["weights"])
        w["calming_source"] = "both"
        w["bike_type"] = data["profiles"][key].get("bike_type", "standard")
        toggles = data["profiles"][key].get("toggles") or {}
        vf = toggles.get("vf_infrastructure") or {}
        w["vf_shared_path"] = bool(vf.get("shared_path", True))
        w["vf_bus_lane"] = bool(vf.get("bus_lane", True))
        w["vf_painted_lane"] = bool(vf.get("painted_lane", False))
        out[label] = w
    return out


@dataclass
class EdgeCostTables:
    """Load-time numeric edge facts (one row per directed edge)."""

    n_edges: int
    edge_index: dict[tuple, int]  # (u, v) -> i (v1 / overlay build only)
    length: np.ndarray
    risk: np.ndarray
    grade: np.ndarray
    vf_flags: np.ndarray
    is_lit: np.ndarray
    is_bad_surface: np.ndarray
    masks_hill_surface: np.ndarray  # steps / non-alley service
    speed_stress: np.ndarray
    is_tfl: np.ndarray
    is_green: np.ndarray  # attraction reward
    m_highway: np.ndarray
    barrier_base: np.ndarray
    give_way_base: np.ndarray
    stop_base: np.ndarray
    calming_base: np.ndarray
    signal_base: np.ndarray
    intersection_base: np.ndarray
    mini_rb_base: np.ndarray
    junction_danger_base: np.ndarray
    # v3 fused load-time columns (fewer multiplies in the hot path)
    junction_base: np.ndarray  # give+stop+ix+mini+danger (× w_junction)
    unlit_base: np.ndarray  # 0.5 if unlit else 0 (× w_light)
    bad_surf_base: np.ndarray  # 3.0 if bad surface else 0 (× w_surface; mask steps in fn)
    hard_static: np.ndarray  # hard_service | hard_barrier
    hill_base: np.ndarray  # metres of hill cost at w_hill=1
    hard_service: np.ndarray
    hard_barrier: np.ndarray  # always hard (access / impassable cluster)
    hard_cargo: np.ndarray  # cargo-only hard
    is_park: np.ndarray
    park_oh_id: np.ndarray  # int32: index into park_oh_exprs, or -1
    park_oh_exprs: list[str]  # unique opening_hours strings on park edges
    head_suppressed: np.ndarray  # junction cluster suppressed on head v


@dataclass
class RequestOverlays:
    """Per-request thin overlays for array_v2 weight callback."""

    park_open: np.ndarray  # uint8[len(park_oh_exprs)]
    fallback_open: bool
    has_live: bool
    live_closed: np.ndarray  # uint8[n_edges]
    live_m_add: np.ndarray  # float64[n_edges] — baked with w_live
    live_m_mult: np.ndarray  # float64[n_edges] — baked with w_live (default 1)


@dataclass
class SharedOverlays:
    """Timer-cadence bake (simulates post-disruption / every-N-min refresh).

    Live soft penalties are stored as *coefficients*, not scaled by ``w_live``:
      m = m + live_add_coeff[i] * w_live
      m *= 1 + live_env_extra[i] * min(w_live, 1)
      m *= 1 + live_sev_extra[i] * min(w_live, 1)

    So jam-comfort is one request scalar — not a second full cost array.
    Closures stay in ``impassable`` independent of ``w_live``.
    """

    park_open: np.ndarray  # uint8[n_exprs]
    park_blocked: np.ndarray  # uint8[n_edges] — closed parks expanded
    fallback_open: bool
    has_live: bool
    live_closed: np.ndarray  # uint8[n_edges]
    live_add_coeff: np.ndarray  # float64 — additive before × w_live
    live_env_extra: np.ndarray  # float64 — env hazard factor
    live_sev_extra: np.ndarray  # float64 — severity-1 factor
    impassable: np.ndarray  # uint8 — hard_static | park_blocked | live_closed
    bake_s: float



def build_edge_cost_tables(app_mod) -> tuple[EdgeCostTables, float]:
    """One-time pass over G.edges — mirrors production helpers into arrays.

    Also stamps ``d['_eid'] = i`` on every NetworkX edge for O(1) hot-path index
    (array_v2 — no dict lookup).
    """
    from barrier_clusters import (
        CARGO_IMPASSABLE_TAGS,
        CLUSTER_IMPASSABLE,
        barrier_access_denied,
        barrier_cluster_for_tag,
        normalize_barrier_tag,
    )
    from cost_masks import is_service_access_denied, masks_surface_and_hill, vf_flags

    G = app_mod.G
    t0 = time.perf_counter()
    edges = list(G.edges(data=True))
    n = len(edges)

    length = np.empty(n, dtype=np.float64)
    risk = np.empty(n, dtype=np.float64)
    grade = np.empty(n, dtype=np.float64)
    vf = np.empty(n, dtype=np.int32)
    is_lit_a = np.empty(n, dtype=np.uint8)
    is_bad = np.empty(n, dtype=np.uint8)
    masks_hs = np.empty(n, dtype=np.uint8)
    speed = np.empty(n, dtype=np.float64)
    is_tfl = np.empty(n, dtype=np.uint8)
    is_green = np.empty(n, dtype=np.uint8)
    m_hw = np.empty(n, dtype=np.float64)
    barrier_b = np.empty(n, dtype=np.float64)
    give_b = np.empty(n, dtype=np.float64)
    stop_b = np.empty(n, dtype=np.float64)
    calm_b = np.empty(n, dtype=np.float64)
    sig_b = np.empty(n, dtype=np.float64)
    ix_b = np.empty(n, dtype=np.float64)
    mini_b = np.empty(n, dtype=np.float64)
    junc_b = np.empty(n, dtype=np.float64)
    hill_b = np.empty(n, dtype=np.float64)
    hard_svc = np.empty(n, dtype=np.uint8)
    hard_bar = np.empty(n, dtype=np.uint8)
    hard_cargo = np.empty(n, dtype=np.uint8)
    is_park = np.empty(n, dtype=np.uint8)
    park_oh_id = np.empty(n, dtype=np.int32)
    head_sup = np.empty(n, dtype=np.uint8)
    edge_index: dict[tuple, int] = {}
    park_expr_to_id: dict[str, int] = {}
    park_oh_exprs: list[str] = []

    suppressed = app_mod.JUNCTION_CLUSTER_SUPPRESSED
    bad_surfaces = app_mod.BAD_SURFACES
    up_thresh = app_mod.UP_THRESH
    down_thresh = app_mod.DOWN_THRESH

    for i, (u, v, d) in enumerate(edges):
        edge_index[(u, v)] = i
        d["_eid"] = i  # hot-path index for array_v2
        length[i] = float(d.get("length", 1.0) or 1.0)
        risk[i] = float(d.get("risk", 0.0) or 0.0)
        g = float(d.get("grade", 0.0) or 0.0)
        grade[i] = g
        flags = int(d.get("_vf", 0) or 0) or int(vf_flags(d))
        vf[i] = flags
        is_lit_a[i] = 1 if app_mod.is_lit(d) else 0
        surf = str(d.get("surface", "")).lower()
        is_bad[i] = 1 if surf in bad_surfaces else 0
        on_steps = masks_surface_and_hill(d)
        masks_hs[i] = 1 if on_steps else 0
        speed[i] = float(app_mod._speed_stress_multiplier(d))
        is_tfl[i] = 1 if app_mod._is_tfl_network(d) else 0
        is_green[i] = 1 if app_mod._has_attraction_edge(d) else 0
        m_hw[i] = float(app_mod._highway_type_multiplier(d))
        barrier_b[i] = float(app_mod._edge_barrier_penalty(d))
        give_b[i] = float(app_mod._edge_give_way_penalty(d))
        stop_b[i] = float(app_mod._edge_stop_sign_penalty(d))
        calm_b[i] = float(app_mod._traffic_calming_additive(d, "both"))

        node_v = G.nodes[v] if v in G.nodes else {}
        head_sup[i] = 1 if v in suppressed else 0
        if head_sup[i]:
            sig_b[i] = 0.0
            ix_b[i] = 0.0
            mini_b[i] = 0.0
            junc_b[i] = 0.0
        else:
            sig_b[i] = float(app_mod._node_signal_penalty(node_v))
            ix_b[i] = float(app_mod._node_intersection_penalty(node_v))
            mini_b[i] = float(app_mod._node_mini_roundabout_penalty(node_v))
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

        park = 1 if app_mod._is_yes_attr(d.get("is_park")) else 0
        is_park[i] = park
        oh = str(d.get("opening_hours", "") or "").strip()
        if park and oh:
            pid = park_expr_to_id.get(oh)
            if pid is None:
                pid = len(park_oh_exprs)
                park_expr_to_id[oh] = pid
                park_oh_exprs.append(oh)
            park_oh_id[i] = pid
        else:
            park_oh_id[i] = -1  # not park, or park with empty hours → fallback_open

    hard_static = ((hard_svc != 0) | (hard_bar != 0)).astype(np.uint8)
    junction_base = give_b + stop_b + ix_b + mini_b + junc_b
    unlit_base = np.where(is_lit_a == 0, 0.5, 0.0).astype(np.float64)
    bad_surf_base = np.where(is_bad != 0, 3.0, 0.0).astype(np.float64)

    elapsed = time.perf_counter() - t0
    tables = EdgeCostTables(
        n_edges=n,
        edge_index=edge_index,
        length=length,
        risk=risk,
        grade=grade,
        vf_flags=vf,
        is_lit=is_lit_a,
        is_bad_surface=is_bad,
        masks_hill_surface=masks_hs,
        speed_stress=speed,
        is_tfl=is_tfl,
        is_green=is_green,
        m_highway=m_hw,
        barrier_base=barrier_b,
        give_way_base=give_b,
        stop_base=stop_b,
        calming_base=calm_b,
        signal_base=sig_b,
        intersection_base=ix_b,
        mini_rb_base=mini_b,
        junction_danger_base=junc_b,
        junction_base=junction_base,
        unlit_base=unlit_base,
        bad_surf_base=bad_surf_base,
        hard_static=hard_static,
        hill_base=hill_b,
        hard_service=hard_svc,
        hard_barrier=hard_bar,
        hard_cargo=hard_cargo,
        is_park=is_park,
        park_oh_id=park_oh_id,
        park_oh_exprs=park_oh_exprs,
        head_suppressed=head_sup,
    )
    return tables, elapsed


def _live_soft_coeffs(disruption: dict) -> tuple[float, float, float]:
    """Return (add_coeff, env_extra, sev_extra) before applying request ``w_live``.

    Production applies multiplicative factors *separately*:
      M += add_coeff * w_live
      M *= 1 + env_extra * min(w_live, 1)   # environmental_hazard → 0.3
      M *= 1 + sev_extra * min(w_live, 1)   # severity_multiplier - 1
    Do not sum env+sev into one factor — (1+a)(1+b) ≠ (1+a+b).
    """
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


def build_request_overlays(
    tables: EdgeCostTables,
    hours_map: dict,
    fallback_open: bool,
    w_live: float,
) -> RequestOverlays:
    """Bake park-open bits + live disruption arrays for one request / weight vector (v2)."""
    import live_disruptions
    import park_opening_hours

    n_expr = len(tables.park_oh_exprs)
    park_open = np.ones(n_expr, dtype=np.uint8)
    for pid, expr in enumerate(tables.park_oh_exprs):
        ed = {"is_park": "yes", "opening_hours": expr}
        park_open[pid] = (
            1 if park_opening_hours.is_park_edge_open(ed, hours_map, fallback_open) else 0
        )

    n = tables.n_edges
    live_closed = np.zeros(n, dtype=np.uint8)
    live_m_add = np.zeros(n, dtype=np.float64)
    live_m_mult = np.ones(n, dtype=np.float64)

    lookup = live_disruptions.MASTER_LIVE_LOOKUP
    has_live = bool(lookup)
    if has_live:
        w_live = float(w_live)
        w_cap = min(w_live, 1.0)
        for (u, v), disruption in lookup.items():
            i = tables.edge_index.get((u, v))
            if i is None:
                continue
            if disruption.get("has_closure") or disruption.get("is_closed"):
                live_closed[i] = 1
                continue
            add_c, env_e, sev_e = _live_soft_coeffs(disruption)
            live_m_add[i] = add_c * w_live
            live_m_mult[i] = (1.0 + env_e * w_cap) * (1.0 + sev_e * w_cap)
    return RequestOverlays(
        park_open=park_open,
        fallback_open=bool(fallback_open),
        has_live=has_live,
        live_closed=live_closed,
        live_m_add=live_m_add,
        live_m_mult=live_m_mult,
    )


def build_shared_overlays(
    tables: EdgeCostTables,
    hours_map: dict,
    fallback_open: bool,
) -> SharedOverlays:
    """Timer-style bake: parks + live coeffs + fused impassable (independent of w_live)."""
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

    # Expand closed exprs → per-edge park_blocked (vectorized, once per timer tick).
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
    lookup = live_disruptions.MASTER_LIVE_LOOKUP
    has_live = bool(lookup)
    if has_live:
        for (u, v), disruption in lookup.items():
            i = tables.edge_index.get((u, v))
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


def make_array_weight_fn(tables: EdgeCostTables, app_mod, w: dict, hours_map, fallback_open):
    """v1: array reads + dict index + live dict + park string check (original bench)."""
    from cost_masks import vf_allowed_masks
    from routing_heuristic import (
        green_reward,
        tfl_network_reward,
        vehicular_free_reward,
    )
    import live_disruptions
    import park_opening_hours

    hard = app_mod.BARRIER_HARD_COST
    m_min = app_mod.M_MIN
    r_min = app_mod.R_MIN

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
    w_vf = float(w.get("vehicular_free_weight", 0.0))
    cargo = str(w.get("bike_type", "standard")) == "cargo"

    r_tfl = tfl_network_reward(w_tfl) if w_tfl > 0 else 1.0
    r_green = green_reward(w_green) if w_green > 0 else 1.0
    r_vf = vehicular_free_reward(w_vf) if w_vf > 0 else 1.0
    tfl_on = w_tfl > 0
    green_on = w_green > 0
    vf_on = w_vf > 0
    hill_on = w_hill > 0

    vf_mask, vf_reward = vf_allowed_masks(
        shared_path=bool(w.get("vf_shared_path", True)),
        bus_lane=bool(w.get("vf_bus_lane", True)),
        painted_lane=bool(w.get("vf_painted_lane", False)),
    )
    idx = tables.edge_index
    exprs = tables.park_oh_exprs

    def weight_fn(u, v, _d):
        i = idx.get((u, v))
        if i is None:
            return hard
        if tables.hard_service[i] or tables.hard_barrier[i]:
            return hard
        if cargo and tables.hard_cargo[i]:
            return hard
        if tables.is_park[i]:
            pid = int(tables.park_oh_id[i])
            oh = exprs[pid] if pid >= 0 else ""
            ed = {"is_park": "yes", "opening_hours": oh}
            if not park_opening_hours.is_park_edge_open(ed, hours_map, fallback_open):
                return hard
        disruption = live_disruptions.get_edge_disruption(u, v)
        if disruption and (disruption.get("has_closure") or disruption.get("is_closed")):
            return hard

        length = tables.length[i]
        edge_vf = int(tables.vf_flags[i])
        vehicular_free = bool(edge_vf & vf_mask)
        on_steps = bool(tables.masks_hill_surface[i])
        risk_p = 0.0 if vehicular_free else tables.risk[i] * w_risk
        light_p = 0.0 if tables.is_lit[i] else 0.5 * w_light
        surf_p = 0.0 if on_steps else (3.0 if tables.is_bad_surface[i] else 0.0) * w_surface
        speed_m = 0.0 if vehicular_free else tables.speed_stress[i] * w_speed
        m_total = max(m_min, 1.0 + risk_p + light_p + surf_p + speed_m)
        r = 1.0
        if tfl_on and tables.is_tfl[i]:
            r *= r_tfl
        if green_on and tables.is_green[i]:
            r *= r_green
        if vf_on and (edge_vf & vf_reward):
            r *= r_vf
        r = max(r_min, r)
        a_total = (
            tables.barrier_base[i] * w_barrier
            + tables.give_way_base[i] * w_junction
            + tables.stop_base[i] * w_junction
            + tables.signal_base[i] * w_signal
            + tables.intersection_base[i] * w_junction
            + tables.mini_rb_base[i] * w_junction
            + tables.junction_danger_base[i] * w_junction
            + (0.0 if vehicular_free else tables.calming_base[i] * w_calming)
        )
        h = tables.hill_base[i] * w_hill if hill_on and not on_steps else 0.0
        if disruption:
            if disruption.get("is_diversion"):
                m_total += 5.0 * w_live
            cat = disruption.get("category", "")
            if cat == "Works":
                m_total += 3.0 * w_live
            elif cat in (
                "Collisions",
                "Emergency service incidents",
                "Traffic Incidents",
                "Network delays",
            ):
                m_total += 2.0 * w_live
            if disruption.get("temporary_bad_surface"):
                m_total += 3.0 * w_live
            if disruption.get("environmental_hazard"):
                m_total *= 1.0 + 0.3 * min(w_live, 1.0)
            sev = disruption.get("severity_multiplier", 1.0)
            if sev > 1.0:
                m_total *= 1.0 + (sev - 1.0) * min(w_live, 1.0)
        return (length * m_total * tables.m_highway[i] * r) + a_total + h

    return weight_fn


def make_array_weight_fn_v2(
    tables: EdgeCostTables,
    app_mod,
    w: dict,
    overlays: RequestOverlays,
):
    """v2 thinned callback: ``d['_eid']``, park uint8 by id, live arrays (skip if empty)."""
    from cost_masks import vf_allowed_masks
    from routing_heuristic import (
        green_reward,
        tfl_network_reward,
        vehicular_free_reward,
    )

    hard = app_mod.BARRIER_HARD_COST
    m_min = app_mod.M_MIN
    r_min = app_mod.R_MIN

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
    w_vf = float(w.get("vehicular_free_weight", 0.0))
    cargo = str(w.get("bike_type", "standard")) == "cargo"

    r_tfl = tfl_network_reward(w_tfl) if w_tfl > 0 else 1.0
    r_green = green_reward(w_green) if w_green > 0 else 1.0
    r_vf = vehicular_free_reward(w_vf) if w_vf > 0 else 1.0
    tfl_on = w_tfl > 0
    green_on = w_green > 0
    vf_on = w_vf > 0
    hill_on = w_hill > 0

    vf_mask, vf_reward = vf_allowed_masks(
        shared_path=bool(w.get("vf_shared_path", True)),
        bus_lane=bool(w.get("vf_bus_lane", True)),
        painted_lane=bool(w.get("vf_painted_lane", False)),
    )

    # Local bindings (avoid attribute lookup in the hot loop).
    length_a = tables.length
    risk_a = tables.risk
    vf_a = tables.vf_flags
    lit_a = tables.is_lit
    bad_a = tables.is_bad_surface
    steps_a = tables.masks_hill_surface
    speed_a = tables.speed_stress
    tfl_a = tables.is_tfl
    green_a = tables.is_green
    mhw_a = tables.m_highway
    bar_a = tables.barrier_base
    give_a = tables.give_way_base
    stop_a = tables.stop_base
    calm_a = tables.calming_base
    sig_a = tables.signal_base
    ix_a = tables.intersection_base
    mini_a = tables.mini_rb_base
    junc_a = tables.junction_danger_base
    hill_a = tables.hill_base
    hard_svc = tables.hard_service
    hard_bar = tables.hard_barrier
    hard_cargo = tables.hard_cargo
    is_park = tables.is_park
    park_id = tables.park_oh_id
    park_open = overlays.park_open
    fallback_open = overlays.fallback_open
    has_live = overlays.has_live
    live_closed = overlays.live_closed
    live_add = overlays.live_m_add
    live_mult = overlays.live_m_mult
    edge_index = tables.edge_index

    def weight_fn(_u, _v, d):
        i = d.get("_eid")
        if i is None:
            i = edge_index.get((_u, _v))
            if i is None:
                return hard

        if hard_svc[i] or hard_bar[i]:
            return hard
        if cargo and hard_cargo[i]:
            return hard

        if is_park[i]:
            pid = int(park_id[i])
            if pid < 0:
                if not fallback_open:
                    return hard
            elif not park_open[pid]:
                return hard

        if has_live:
            if live_closed[i]:
                return hard

        edge_vf = int(vf_a[i])
        vehicular_free = bool(edge_vf & vf_mask)
        on_steps = bool(steps_a[i])

        risk_p = 0.0 if vehicular_free else risk_a[i] * w_risk
        light_p = 0.0 if lit_a[i] else 0.5 * w_light
        surf_p = 0.0 if on_steps else (3.0 if bad_a[i] else 0.0) * w_surface
        speed_m = 0.0 if vehicular_free else speed_a[i] * w_speed
        m_total = max(m_min, 1.0 + risk_p + light_p + surf_p + speed_m)

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
            + give_a[i] * w_junction
            + stop_a[i] * w_junction
            + sig_a[i] * w_signal
            + ix_a[i] * w_junction
            + mini_a[i] * w_junction
            + junc_a[i] * w_junction
            + (0.0 if vehicular_free else calm_a[i] * w_calming)
        )
        h = hill_a[i] * w_hill if hill_on and not on_steps else 0.0

        if has_live:
            m_total = (m_total + live_add[i]) * live_mult[i]

        return (length_a[i] * m_total * mhw_a[i] * r) + a_total + h

    return weight_fn


def make_array_weight_fn_v3(
    tables: EdgeCostTables,
    app_mod,
    w: dict,
    shared: SharedOverlays,
):
    """v3: shared bake + live coeffs × w_live + fused impassable / junction bases."""
    from cost_masks import vf_allowed_masks
    from routing_heuristic import (
        green_reward,
        tfl_network_reward,
        vehicular_free_reward,
    )

    hard = app_mod.BARRIER_HARD_COST
    m_min = app_mod.M_MIN
    r_min = app_mod.R_MIN

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
    edge_index = tables.edge_index

    def weight_fn(_u, _v, d):
        i = d.get("_eid")
        if i is None:
            i = edge_index.get((_u, _v))
            if i is None:
                return hard

        if impassable[i]:
            return hard
        if cargo and hard_cargo[i]:
            return hard

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

    return weight_fn


def make_array_weight_fn_fastest(
    tables: EdgeCostTables,
    app_mod,
    shared: SharedOverlays,
    bike_type: str = "standard",
):
    """Array fastest: length × m_highway with shared impassable (+ cargo hard)."""
    hard = app_mod.BARRIER_HARD_COST
    cargo = str(bike_type) == "cargo"
    length_a = tables.length
    mhw_a = tables.m_highway
    hard_cargo = tables.hard_cargo
    impassable = shared.impassable
    edge_index = tables.edge_index

    def weight_fn(_u, _v, d):
        i = d.get("_eid")
        if i is None:
            i = edge_index.get((_u, _v))
            if i is None:
                return hard
        if impassable[i]:
            return hard
        if cargo and hard_cargo[i]:
            return hard
        return length_a[i] * mhw_a[i]

    return weight_fn


def path_total_cost(G, path, weight_fn) -> float:
    total = 0.0
    for i in range(len(path) - 1):
        u, v = path[i], path[i + 1]
        total += float(weight_fn(u, v, G[u][v]))
    return total


def path_length_m(G, path) -> float:
    total = 0.0
    for i in range(len(path) - 1):
        u, v = path[i], path[i + 1]
        total += float((G.get_edge_data(u, v) or {}).get("length", 0))
    return total


def microbench_edge_costs(
    tables,
    app_mod,
    weight_py,
    weight_arr,
    weight_arr_v2=None,
    weight_arr_v3=None,
    sample_n: int = 200_000,
) -> dict:
    """Time N edge evaluations for python vs array v1/v2/v3."""
    G = app_mod.G
    edges = list(tables.edge_index.keys())
    if not edges:
        return {}
    rng = np.random.default_rng(42)
    picks = rng.choice(len(edges), size=min(sample_n, len(edges)), replace=False)

    def _time(fn):
        t0 = time.perf_counter()
        for j in picks:
            u, v = edges[int(j)]
            fn(u, v, G[u][v])
        return time.perf_counter() - t0

    t_py = _time(weight_py)
    t_arr = _time(weight_arr)
    n = len(picks)
    out = {
        "sample_edges": n,
        "python_s": round(t_py, 3),
        "array_s": round(t_arr, 3),
        "speedup": round(t_py / t_arr, 2) if t_arr > 0 else 0.0,
        "python_us_per_edge": round(1e6 * t_py / n, 2),
        "array_us_per_edge": round(1e6 * t_arr / n, 2),
    }
    if weight_arr_v2 is not None:
        t_v2 = _time(weight_arr_v2)
        out["array_v2_s"] = round(t_v2, 3)
        out["speedup_v2"] = round(t_py / t_v2, 2) if t_v2 > 0 else 0.0
        out["array_v2_us_per_edge"] = round(1e6 * t_v2 / n, 2)
        out["v2_vs_v1"] = round(t_arr / t_v2, 2) if t_v2 > 0 else 0.0
    if weight_arr_v3 is not None:
        t_v3 = _time(weight_arr_v3)
        out["array_v3_s"] = round(t_v3, 3)
        out["speedup_v3"] = round(t_py / t_v3, 2) if t_v3 > 0 else 0.0
        out["array_v3_us_per_edge"] = round(1e6 * t_v3 / n, 2)
        if weight_arr_v2 is not None and out.get("array_v2_s"):
            out["v3_vs_v2"] = (
                round(out["array_v2_s"] / t_v3, 2) if t_v3 > 0 else 0.0
            )
    return out


def bootstrap():
    _mock_flask()
    os.chdir(BACKEND_DIR)
    import park_opening_hours
    import tfl_live
    import app as app_mod
    import pathfinding
    from routing_heuristic import (
        compute_optimized_cost_per_metre_lower_bound,
        get_route_heuristic_epsilon,
        make_heuristic,
    )

    if app_mod.G is None:
        raise RuntimeError("Graph failed to load.")
    return (
        app_mod,
        pathfinding,
        park_opening_hours,
        tfl_live,
        make_heuristic,
        compute_optimized_cost_per_metre_lower_bound,
        get_route_heuristic_epsilon,
    )


def run_route(
    app_mod,
    pathfinding_mod,
    park_opening_hours,
    tfl_live,
    make_heuristic,
    compute_lb,
    route: dict,
    weights: dict,
    eps: float,
    weight_fn,
    label: str,
) -> dict:
    G = app_mod.G
    start_snap = tfl_live.snap_to_edge(route["start_lat"], route["start_lon"])
    end_snap = tfl_live.snap_to_edge(route["end_lat"], route["end_lon"])
    if not start_snap or not end_snap:
        raise RuntimeError(f"Could not snap: {route['name']}")

    start_node = start_snap.anchor_node
    end_node = end_snap.anchor_node
    scale = compute_lb(weights) * (1.0 + eps)
    h = make_heuristic(end_node, G, cost_per_m=scale)

    t0 = time.perf_counter()
    path, stats = pathfinding_mod.astar_unidirectional(
        G, start_node, end_node, h, weight_fn
    )
    elapsed = time.perf_counter() - t0
    cost = path_total_cost(G, path, weight_fn)
    return {
        "label": label,
        "elapsed_s": round(elapsed, 3),
        "expansions": stats["expansions"],
        "edge_relaxations": stats["edge_relaxations"],
        "length_m": round(path_length_m(G, path), 1),
        "path_cost": cost,
        "path_nodes": path,
    }


def main() -> None:
    print("Bootstrapping engine...", flush=True)
    (
        app_mod,
        pathfinding_mod,
        park_opening_hours,
        tfl_live,
        make_heuristic,
        compute_lb,
        get_eps,
    ) = bootstrap()

    eps = get_eps()
    print(f"Building edge cost tables (load-time pass)...", flush=True)
    tables, build_s = build_edge_cost_tables(app_mod)
    print(
        f"  tables: {tables.n_edges:,} edges in {build_s:.1f}s "
        f"({tables.n_edges / max(build_s, 1e-9):,.0f} edges/s)",
        flush=True,
    )

    presets = load_preset_weights()
    routes = parse_test_routes()
    G = app_mod.G

    # Shared hours + timer-style shared overlays (parks + live coeffs, once).
    unique_hours = G.graph.get("park_opening_hours_unique") or []
    at_time = park_opening_hours.london_now()
    hours_map, fallback_open = park_opening_hours.build_request_hours_context(
        unique_hours, at_time
    )
    print("Building shared overlays (timer-style bake)...", flush=True)
    shared = build_shared_overlays(tables, hours_map, fallback_open)
    print(
        f"  shared bake {shared.bake_s:.3f}s | live={shared.has_live} | "
        f"park_exprs={len(tables.park_oh_exprs)} | "
        f"impassable={int(shared.impassable.sum()):,}",
        flush=True,
    )

    # Microbench: python vs v1 vs v2 vs v3 (safe weights).
    w_safe = presets["safe"]
    overlays_safe = build_request_overlays(
        tables, hours_map, fallback_open, float(w_safe.get("tfl_live_weight", 0.0))
    )
    weight_py_safe = app_mod.make_weight_optimized(w_safe, hours_map, fallback_open)
    weight_arr_safe = make_array_weight_fn(
        tables, app_mod, w_safe, hours_map, fallback_open
    )
    weight_v2_safe = make_array_weight_fn_v2(tables, app_mod, w_safe, overlays_safe)
    weight_v3_safe = make_array_weight_fn_v3(tables, app_mod, w_safe, shared)
    print("Microbench: 200k edge cost evaluations...", flush=True)
    micro = microbench_edge_costs(
        tables,
        app_mod,
        weight_py_safe,
        weight_arr_safe,
        weight_arr_v2=weight_v2_safe,
        weight_arr_v3=weight_v3_safe,
        sample_n=200_000,
    )
    print(
        f"  python {micro['python_s']}s | v1 {micro['array_s']}s ({micro['speedup']}x) | "
        f"v2 {micro.get('array_v2_s')}s ({micro.get('speedup_v2')}x) | "
        f"v3 {micro.get('array_v3_s')}s ({micro.get('speedup_v3')}x vs py, "
        f"{micro.get('v3_vs_v2')}x vs v2)",
        flush=True,
    )

    # Full routes: python vs v2 vs v3 (v1 already characterized; skip to save wall time).
    all_rows: list[dict] = []
    for preset_name, weights in presets.items():
        print(f"\n=== Preset: {preset_name} ===", flush=True)
        overlays = build_request_overlays(
            tables, hours_map, fallback_open, float(weights.get("tfl_live_weight", 0.0))
        )
        weight_py = app_mod.make_weight_optimized(weights, hours_map, fallback_open)
        weight_v2 = make_array_weight_fn_v2(tables, app_mod, weights, overlays)
        weight_v3 = make_array_weight_fn_v3(tables, app_mod, weights, shared)

        for route in routes:
            print(f"  {route['name']}...", flush=True)
            py = run_route(
                app_mod,
                pathfinding_mod,
                park_opening_hours,
                tfl_live,
                make_heuristic,
                compute_lb,
                route,
                weights,
                eps,
                weight_py,
                "python",
            )
            v2 = run_route(
                app_mod,
                pathfinding_mod,
                park_opening_hours,
                tfl_live,
                make_heuristic,
                compute_lb,
                route,
                weights,
                eps,
                weight_v2,
                "array_v2",
            )
            v3 = run_route(
                app_mod,
                pathfinding_mod,
                park_opening_hours,
                tfl_live,
                make_heuristic,
                compute_lb,
                route,
                weights,
                eps,
                weight_v3,
                "array_v3",
            )

            cost_py_on_py = py["path_cost"]
            cost_v3_on_py_path = path_total_cost(G, py["path_nodes"], weight_v3)
            exact_v2 = py["path_nodes"] == v2["path_nodes"]
            exact_v3 = py["path_nodes"] == v3["path_nodes"]
            cost_match = abs(cost_py_on_py - cost_v3_on_py_path) <= (
                COST_ATOL + COST_RTOL * abs(cost_py_on_py)
            )

            speedup_v2 = py["elapsed_s"] / v2["elapsed_s"] if v2["elapsed_s"] > 0 else 0.0
            speedup_v3 = py["elapsed_s"] / v3["elapsed_s"] if v3["elapsed_s"] > 0 else 0.0
            row = {
                "preset": preset_name,
                "route": route["name"],
                "python_s": py["elapsed_s"],
                "array_v2_s": v2["elapsed_s"],
                "array_v3_s": v3["elapsed_s"],
                "speedup_v2": round(speedup_v2, 2),
                "speedup_v3": round(speedup_v3, 2),
                "v3_vs_v2": round(v2["elapsed_s"] / v3["elapsed_s"], 2)
                if v3["elapsed_s"] > 0
                else 0.0,
                "python_exp": py["expansions"],
                "array_v2_exp": v2["expansions"],
                "array_v3_exp": v3["expansions"],
                "python_length_m": py["length_m"],
                "array_v2_length_m": v2["length_m"],
                "array_v3_length_m": v3["length_m"],
                "length_delta_m": round(v3["length_m"] - py["length_m"], 1),
                "exact_path_match": exact_v3,
                "exact_path_match_v2": exact_v2,
                "cost_python": round(cost_py_on_py, 3),
                "cost_array_v3_on_python_path": round(cost_v3_on_py_path, 3),
                "cost_parity_ok": cost_match,
            }
            all_rows.append(row)
            match = "exact" if exact_v3 else f"lenΔ={row['length_delta_m']:+.0f}"
            print(
                f"    py={py['elapsed_s']:.2f}s v2={v2['elapsed_s']:.2f}s "
                f"({speedup_v2:.2f}x) v3={v3['elapsed_s']:.2f}s ({speedup_v3:.2f}x) "
                f"path={match} cost_ok={cost_match}",
                flush=True,
            )

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "graph_nodes": G.number_of_nodes(),
        "graph_edges": G.number_of_edges(),
        "table_edges": tables.n_edges,
        "table_build_s": round(build_s, 2),
        "shared_bake_s": round(shared.bake_s, 3),
        "heuristic_epsilon": eps,
        "park_oh_exprs": len(tables.park_oh_exprs),
        "live_overlay_active": shared.has_live,
        "impassable_edges": int(shared.impassable.sum()),
        "microbench": micro,
        "array_v3": {
            "shared_overlays": True,
            "live_coeffs_not_scaled": True,
            "fused_impassable": True,
            "fused_junction_base": True,
            "park_blocked_expanded": True,
            "jam_comfort": "scalar w_live × live_add_coeff / live_mult_extra",
        },
    }

    def table_for(preset: str) -> str:
        rows = [r for r in all_rows if r["preset"] == preset]
        header = (
            "| Route | Python (s) | Array v2 (s) | Array v3 (s) | "
            "v2 speedup | v3 speedup | Path | Cost parity |"
        )
        sep = "|---|---:|---:|---:|---:|---:|---|---|"
        lines = [header, sep]
        for r in rows:
            match = "exact" if r["exact_path_match"] else "diverged"
            parity = "ok" if r["cost_parity_ok"] else "FAIL"
            lines.append(
                f"| {r['route']} | {r['python_s']:.2f} | {r['array_v2_s']:.2f} | "
                f"{r['array_v3_s']:.2f} | {r['speedup_v2']:.2f}x | {r['speedup_v3']:.2f}x | "
                f"{match} | {parity} |"
            )
        return "\n".join(lines)

    md = [
        "# Array-backed edge costs benchmark",
        "",
        f"Generated: {meta['generated_at']}",
        f"Graph: {meta['graph_nodes']:,} nodes, {meta['graph_edges']:,} edges",
        f"Edge tables built once: **{meta['table_edges']:,}** edges in "
        f"**{meta['table_build_s']} s** (startup cost, not per request)",
        f"Shared overlay bake: **{meta['shared_bake_s']} s** "
        f"(timer-style; impassable={meta['impassable_edges']:,})",
        f"Heuristic epsilon: {meta['heuristic_epsilon']}",
        f"Park hours exprs indexed: {meta['park_oh_exprs']} | "
        f"live overlay active: {meta['live_overlay_active']}",
        "",
        "Compares **python** vs array **v2** vs **v3** (shared bake + live coeffs × "
        "`w_live` + fused impassable). Microbench also includes v1.",
        "",
        "## Microbench (edge cost only, 200k edges, safe weights)",
        "",
        "| Backend | Time (s) | µs / edge | vs python |",
        "|---|---:|---:|---:|",
        f"| python | {micro['python_s']} | {micro['python_us_per_edge']} | 1.00x |",
        f"| array v1 | {micro['array_s']} | {micro['array_us_per_edge']} | {micro['speedup']}x |",
        f"| array v2 | {micro.get('array_v2_s')} | {micro.get('array_v2_us_per_edge')} | "
        f"{micro.get('speedup_v2')}x |",
        f"| array v3 | {micro.get('array_v3_s')} | {micro.get('array_v3_us_per_edge')} | "
        f"**{micro.get('speedup_v3')}x** |",
        "",
        f"v3 vs v2 microbench: **{micro.get('v3_vs_v2')}x**",
        "",
        "## Preset: fast",
        "",
        table_for("fast"),
        "",
        "## Preset: safe",
        "",
        table_for("safe"),
        "",
        "## How to read this",
        "",
        "- **Table build** is paid once at process start (like graph load).",
        "- **Shared bake** simulates the every-~5 min refresh (parks + live coeffs + "
        "fused `impassable[]`); not paid per `/route`.",
        "- **v2** = `_eid` + park uint8 by id + live arrays scaled by `w_live` per request.",
        "- **v3** = shared bake; jam-comfort is scalar `w_live` × `live_add_coeff` / "
        "`live_mult_extra` (not a second full cost array); one `impassable[i]` check.",
        "- **VF / cargo** stay request scalars/masks (8 VF combos, not 8 cost arrays).",
        "- **Cost parity** checks v3 costs on the python path match python costs.",
        "",
        "Re-run: `python 4_backend_engine/benchmark_array_costs.py`",
        "",
        "Spec: [`route_generation_performance.md`](../route_generation_performance.md)",
        "",
        "---",
        "",
        "## Analysis (10 Jul 2026) — array v1 / v2",
        "",
        "**v1:** ~9× microbench, ~1.6–2.5× full A*; exact + parity.",
        "",
        "**v2:** ~12.7× microbench, ~2.0–2.9× (fast) / ~1.8–2.7× (safe); exact + parity "
        "22/22. Gains from `_eid` + park uint8 (live was empty in that run).",
        "",
        "Amdahl: further Python thinning in the weight callback has diminishing returns; "
        "remaining time is heap / NetworkX / heuristic.",
        "",
        "## Analysis — array v3",
        "",
        "_Fill after this re-run: microbench v3 vs v2, full-route v3 speedups, shared "
        "bake time, path/cost fidelity, live active or not._",
        "",
        "### Jam-comfort design (not two cost arrays)",
        "",
        "Closures → `impassable` (independent of `tfl_live_weight`). Soft jams store "
        "`live_add_coeff` / `live_mult_extra`; request applies scalar `w_live`. Same path "
        "for a binary UI or a continuous slider. VF toggles = bitmasks; cargo = "
        "`hard_cargo` column — not per-option float cost arrays.",
        "",
        "### Related",
        "",
        "- Bi post-mortem: [`routing_performance_report.md`](routing_performance_report.md)",
        "- Ellipse analysis: [`ellipse_precompute_report.md`](ellipse_precompute_report.md)",
        "- Backlog: [`route_generation_performance.md`](../route_generation_performance.md)",
    ]
    REPORT_MD.write_text("\n".join(md), encoding="utf-8")
    REPORT_JSON.write_text(
        json.dumps({"meta": meta, "runs": all_rows}, indent=2),
        encoding="utf-8",
    )
    print(f"\nReport: {REPORT_MD}")
    print(f"JSON:   {REPORT_JSON}")
    print("ARRAY COST BENCHMARK DONE", flush=True)


if __name__ == "__main__":
    main()
