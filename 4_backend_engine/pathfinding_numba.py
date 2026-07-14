"""
Phase C — Numba @njit uni A* over GraphCSR + edge cost arrays.

Python prepares scalars + array refs; Numba runs heap + neighbors + cost + heuristic.
Kill-switch: NUMBA_ASTAR=0|false|no|off → callers keep pure-Python CSR A*.
If numba is not installed, is_available() is False and callers fall back.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

import numpy as np

log = logging.getLogger("pathfinding_numba")

try:
    from numba import njit

    _NUMBA_IMPORT_OK = True
except ImportError:  # pragma: no cover
    _NUMBA_IMPORT_OK = False

    def njit(*_a, **_k):  # type: ignore
        def deco(fn):
            return fn

        return deco


INF = 1.0e300
HARD_SENTINEL = -1  # missing eid


def numba_astar_enabled() -> bool:
    raw = os.environ.get("NUMBA_ASTAR", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def is_available() -> bool:
    return bool(_NUMBA_IMPORT_OK)


@dataclass
class NumbaScratch:
    """Reusable per-process buffers sized to the graph."""

    n_nodes: int
    heap_cap: int
    g: np.ndarray  # float64[n_nodes]
    stamp: np.ndarray  # int32[n_nodes] — g valid when == gen
    closed_stamp: np.ndarray  # int32[n_nodes] — closed when == gen
    parent: np.ndarray  # int32[n_nodes]
    heap_f: np.ndarray  # float64[heap_cap]
    heap_tie: np.ndarray  # int64[heap_cap]
    heap_node: np.ndarray  # int32[heap_cap]
    gen: np.ndarray  # int32 shape (1,)


_SCRATCH: NumbaScratch | None = None
_WARMED = False


def get_scratch(n_nodes: int, n_edges: int = 0) -> NumbaScratch:
    """Allocate search scratch.

    Heap must hold more than ``n_nodes`` entries: A* keeps multiple (stale)
    open-set records per node. Capacity ``n_nodes + n_edges`` is a safe upper
    bound (at most one push per arc relaxation).
    """
    global _SCRATCH
    heap_cap = int(n_nodes + max(n_edges, n_nodes) + 8)
    if (
        _SCRATCH is None
        or _SCRATCH.n_nodes != n_nodes
        or _SCRATCH.heap_cap < heap_cap
    ):
        _SCRATCH = NumbaScratch(
            n_nodes=n_nodes,
            heap_cap=heap_cap,
            g=np.empty(n_nodes, dtype=np.float64),
            stamp=np.zeros(n_nodes, dtype=np.int32),
            closed_stamp=np.zeros(n_nodes, dtype=np.int32),
            parent=np.full(n_nodes, -1, dtype=np.int32),
            heap_f=np.empty(heap_cap, dtype=np.float64),
            heap_tie=np.empty(heap_cap, dtype=np.int64),
            heap_node=np.empty(heap_cap, dtype=np.int32),
            gen=np.ones(1, dtype=np.int32),
        )
    return _SCRATCH


@njit(cache=True)
def _heap_push(hf, ht, hn, size, cap, f, tie, node):
    if size >= cap:
        return -1  # overflow
    i = size
    size += 1
    hf[i] = f
    ht[i] = tie
    hn[i] = node
    while i > 0:
        p = (i - 1) // 2
        fp = hf[p]
        fi = hf[i]
        if fp < fi or (fp == fi and ht[p] <= ht[i]):
            break
        hf[p], hf[i] = fi, fp
        ht[p], ht[i] = ht[i], ht[p]
        hn[p], hn[i] = hn[i], hn[p]
        i = p
    return size


@njit(cache=True)
def _heap_pop(hf, ht, hn, size):
    f0 = hf[0]
    t0 = ht[0]
    n0 = hn[0]
    size -= 1
    if size > 0:
        hf[0] = hf[size]
        ht[0] = ht[size]
        hn[0] = hn[size]
        i = 0
        while True:
            l = 2 * i + 1
            r = l + 1
            if l >= size:
                break
            best = l
            if r < size:
                fl = hf[l]
                fr = hf[r]
                if fr < fl or (fr == fl and ht[r] < ht[l]):
                    best = r
            fb = hf[best]
            fi = hf[i]
            if fi < fb or (fi == fb and ht[i] <= ht[best]):
                break
            hf[i], hf[best] = fb, fi
            ht[i], ht[best] = ht[best], ht[i]
            hn[i], hn[best] = hn[best], hn[i]
            i = best
    return f0, t0, n0, size


@njit(cache=True)
def _haversine_m(lat_rad_u, lon_rad_u, cos_lat_u, goal_lat_rad, goal_lon_rad, goal_cos):
    dp = lat_rad_u - goal_lat_rad
    dl = lon_rad_u - goal_lon_rad
    a = np.sin(dp * 0.5) ** 2 + cos_lat_u * goal_cos * np.sin(dl * 0.5) ** 2
    if a > 1.0:
        a = 1.0
    return 2.0 * 6371000.0 * np.arcsin(np.sqrt(a))


@njit(cache=True)
def _cost_fastest(eid, impassable, hard_cargo, length, mhw, hard_cost, cargo):
    if eid < 0:
        return hard_cost
    if impassable[eid] != 0:
        return hard_cost
    if cargo != 0 and hard_cargo[eid] != 0:
        return hard_cost
    return length[eid] * mhw[eid]


@njit(cache=True)
def _cost_optimized(
    eid,
    impassable,
    hard_cargo,
    length,
    risk,
    vf_flags,
    masks_hs,
    speed,
    is_tfl,
    is_green,
    mhw,
    bar,
    junc,
    unlit,
    bad,
    calm,
    sig,
    hill,
    live_add,
    live_env,
    live_sev,
    hard_cost,
    m_min,
    r_min,
    w_risk,
    w_light,
    w_surface,
    w_hill,
    w_speed,
    w_barrier,
    w_calming,
    w_junction,
    w_signal,
    w_live,
    w_live_cap,
    cargo,
    apply_live,
    vf_mask,
    vf_reward,
    r_tfl,
    r_green,
    r_vf,
    tfl_on,
    green_on,
    vf_on,
):
    if eid < 0:
        return hard_cost
    if impassable[eid] != 0:
        return hard_cost
    if cargo != 0 and hard_cargo[eid] != 0:
        return hard_cost

    edge_vf = int(vf_flags[eid])
    vehicular_free = (edge_vf & vf_mask) != 0
    on_steps = masks_hs[eid] != 0

    risk_p = 0.0 if vehicular_free else risk[eid] * w_risk
    light_p = unlit[eid] * w_light
    surf_p = 0.0 if on_steps else bad[eid] * w_surface
    speed_m = 0.0 if vehicular_free else speed[eid] * w_speed
    m_total = 1.0 + risk_p + light_p + surf_p + speed_m
    if m_total < m_min:
        m_total = m_min

    if apply_live != 0:
        m_total = m_total + live_add[eid] * w_live
        m_total *= 1.0 + live_env[eid] * w_live_cap
        m_total *= 1.0 + live_sev[eid] * w_live_cap

    r = 1.0
    if tfl_on != 0 and is_tfl[eid] != 0:
        r *= r_tfl
    if green_on != 0 and is_green[eid] != 0:
        r *= r_green
    if vf_on != 0 and (edge_vf & vf_reward) != 0:
        r *= r_vf
    if r < r_min:
        r = r_min

    a_total = (
        bar[eid] * w_barrier
        + junc[eid] * w_junction
        + sig[eid] * w_signal
        + (0.0 if vehicular_free else calm[eid] * w_calming)
    )
    h = hill[eid] * w_hill
    return (length[eid] * m_total * mhw[eid] * r) + a_total + h


@njit(cache=True)
def _astar_core(
    mode,  # 0=fastest, 1=optimized
    source,
    target,
    indptr,
    indices,
    eid_a,
    lat_rad,
    lon_rad,
    cos_lat,
    impassable,
    hard_cargo,
    length,
    mhw,
    risk,
    vf_flags,
    masks_hs,
    speed,
    is_tfl,
    is_green,
    bar,
    junc,
    unlit,
    bad,
    calm,
    sig,
    hill,
    live_add,
    live_env,
    live_sev,
    hard_cost,
    m_min,
    r_min,
    w_risk,
    w_light,
    w_surface,
    w_hill,
    w_speed,
    w_barrier,
    w_calming,
    w_junction,
    w_signal,
    w_live,
    w_live_cap,
    cargo,
    apply_live,
    vf_mask,
    vf_reward,
    r_tfl,
    r_green,
    r_vf,
    tfl_on,
    green_on,
    vf_on,
    cost_per_m,
    g,
    stamp,
    closed_stamp,
    parent,
    heap_f,
    heap_tie,
    heap_node,
    heap_cap,
    gen_arr,
):
    gen = gen_arr[0] + 1
    if gen <= 0:
        # overflow — caller should zero stamps; still proceed with gen=1
        gen = 1
    gen_arr[0] = gen

    goal_lat = lat_rad[target]
    goal_lon = lon_rad[target]
    goal_cos = cos_lat[target]
    scale = cost_per_m

    stamp[source] = gen
    g[source] = 0.0
    parent[source] = -1
    h0 = scale * _haversine_m(
        lat_rad[source], lon_rad[source], cos_lat[source], goal_lat, goal_lon, goal_cos
    )
    heap_size = _heap_push(heap_f, heap_tie, heap_node, 0, heap_cap, h0, 0, source)
    if heap_size < 0:
        return -1, 0, 0
    tie = 1
    expansions = 0
    edge_relaxations = 0

    while heap_size > 0:
        _f, _t, current, heap_size = _heap_pop(heap_f, heap_tie, heap_node, heap_size)
        if closed_stamp[current] == gen:
            continue
        closed_stamp[current] = gen
        expansions += 1

        if current == target:
            return 1, expansions, edge_relaxations

        g_cur = g[current]
        start = indptr[current]
        end = indptr[current + 1]
        for k in range(start, end):
            edge_relaxations += 1
            neighbor = indices[k]
            e = eid_a[k]
            if mode == 0:
                edge_cost = _cost_fastest(
                    e, impassable, hard_cargo, length, mhw, hard_cost, cargo
                )
            else:
                edge_cost = _cost_optimized(
                    e,
                    impassable,
                    hard_cargo,
                    length,
                    risk,
                    vf_flags,
                    masks_hs,
                    speed,
                    is_tfl,
                    is_green,
                    mhw,
                    bar,
                    junc,
                    unlit,
                    bad,
                    calm,
                    sig,
                    hill,
                    live_add,
                    live_env,
                    live_sev,
                    hard_cost,
                    m_min,
                    r_min,
                    w_risk,
                    w_light,
                    w_surface,
                    w_hill,
                    w_speed,
                    w_barrier,
                    w_calming,
                    w_junction,
                    w_signal,
                    w_live,
                    w_live_cap,
                    cargo,
                    apply_live,
                    vf_mask,
                    vf_reward,
                    r_tfl,
                    r_green,
                    r_vf,
                    tfl_on,
                    green_on,
                    vf_on,
                )
            tentative = g_cur + edge_cost
            if stamp[neighbor] != gen or tentative < g[neighbor]:
                stamp[neighbor] = gen
                g[neighbor] = tentative
                parent[neighbor] = current
                hn = scale * _haversine_m(
                    lat_rad[neighbor],
                    lon_rad[neighbor],
                    cos_lat[neighbor],
                    goal_lat,
                    goal_lon,
                    goal_cos,
                )
                f = tentative + hn
                heap_size = _heap_push(
                    heap_f, heap_tie, heap_node, heap_size, heap_cap, f, tie, neighbor
                )
                if heap_size < 0:
                    return -2, expansions, edge_relaxations
                tie += 1

    return 0, expansions, edge_relaxations


def pack_optimized_scalars(w: dict, shared, hard_cost: float, m_min: float, r_min: float):
    """Python-side scalars for Numba optimized cost (mirrors make_array_cost_by_eid_optimized)."""
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
    cargo = 1 if str(w.get("bike_type", "standard")) == "cargo" else 0
    apply_live = 1 if (shared.has_live and w_live > 0.0) else 0

    r_tfl = tfl_network_reward(w_tfl) if w_tfl > 0 else 1.0
    r_green = green_reward(w_green) if w_green > 0 else 1.0
    r_vf = vehicular_free_reward(w_vf) if w_vf > 0 else 1.0
    tfl_on = 1 if w_tfl > 0 else 0
    green_on = 1 if w_green > 0 else 0
    vf_on = 1 if w_vf > 0 else 0

    vf_mask, vf_reward = vf_allowed_masks(
        shared_path=bool(w.get("vf_shared_path", True)),
        bus_lane=bool(w.get("vf_bus_lane", True)),
        painted_lane=bool(w.get("vf_painted_lane", False)),
    )
    return {
        "hard_cost": float(hard_cost),
        "m_min": float(m_min),
        "r_min": float(r_min),
        "w_risk": w_risk,
        "w_light": w_light,
        "w_surface": w_surface,
        "w_hill": w_hill,
        "w_speed": w_speed,
        "w_barrier": w_barrier,
        "w_calming": w_calming,
        "w_junction": w_junction,
        "w_signal": w_signal,
        "w_live": w_live,
        "w_live_cap": w_live_cap,
        "cargo": cargo,
        "apply_live": apply_live,
        "vf_mask": int(vf_mask),
        "vf_reward": int(vf_reward),
        "r_tfl": float(r_tfl),
        "r_green": float(r_green),
        "r_vf": float(r_vf),
        "tfl_on": tfl_on,
        "green_on": green_on,
        "vf_on": vf_on,
    }


def _empty_arrays(n_edges: int):
    """Unused — kept for tests; production passes real table columns."""
    z8 = np.zeros(max(n_edges, 1), dtype=np.uint8)
    z64 = np.zeros(max(n_edges, 1), dtype=np.float64)
    z32 = np.zeros(max(n_edges, 1), dtype=np.int32)
    return z8, z64, z32


def astar_numba_unidirectional(
    csr,
    source,
    target,
    tables,
    shared,
    *,
    mode: str,
    cost_per_m: float,
    hard_cost: float,
    bike_type: str = "standard",
    opt_scalars: dict | None = None,
) -> tuple[list, dict]:
    """
    Uni A* in Numba. mode: 'fastest' | 'optimized'.
    Returns (path_node_ids, stats) like pathfinding.astar_csr_unidirectional.
    """
    import networkx as nx

    if not is_available():
        raise RuntimeError("numba is not installed")

    t0 = time.perf_counter()
    s = csr.node_to_idx.get(source)
    t = csr.node_to_idx.get(target)
    if s is None or t is None:
        raise nx.NetworkXNoPath(f"No path from {source} to {target}")
    if s == t:
        return [source], {"expansions": 0, "edge_relaxations": 0, "elapsed_s": 0.0}

    scratch = get_scratch(csr.n_nodes, csr.n_edges)
    # Prevent int32 gen overflow from leaving stale stamps
    if scratch.gen[0] > 2_000_000_000:
        scratch.stamp.fill(0)
        scratch.closed_stamp.fill(0)
        scratch.gen[0] = 1

    mode_i = 0 if mode == "fastest" else 1
    cargo = 1 if str(bike_type) == "cargo" else 0

    # Always pass real table columns (fastest mode ignores optimized-only fields).
    risk = tables.risk
    vf_flags = tables.vf_flags
    masks_hs = tables.masks_hill_surface
    speed = tables.speed_stress
    is_tfl = tables.is_tfl
    is_green = tables.is_green
    bar = tables.barrier_base
    junc = tables.junction_base
    unlit = tables.unlit_base
    bad = tables.bad_surf_base
    calm = tables.calming_base
    sig = tables.signal_base
    hill = tables.hill_base
    live_add = shared.live_add_coeff
    live_env = shared.live_env_extra
    live_sev = shared.live_sev_extra

    if mode_i == 0:
        sc = {
            "hard_cost": float(hard_cost),
            "m_min": 0.1,
            "r_min": 0.1,
            "w_risk": 0.0,
            "w_light": 0.0,
            "w_surface": 0.0,
            "w_hill": 0.0,
            "w_speed": 0.0,
            "w_barrier": 0.0,
            "w_calming": 0.0,
            "w_junction": 0.0,
            "w_signal": 0.0,
            "w_live": 0.0,
            "w_live_cap": 0.0,
            "cargo": cargo,
            "apply_live": 0,
            "vf_mask": 0,
            "vf_reward": 0,
            "r_tfl": 1.0,
            "r_green": 1.0,
            "r_vf": 1.0,
            "tfl_on": 0,
            "green_on": 0,
            "vf_on": 0,
        }
    else:
        if opt_scalars is None:
            raise ValueError("opt_scalars required for optimized mode")
        sc = opt_scalars

    found, expansions, edge_relaxations = _astar_core(
        mode_i,
        int(s),
        int(t),
        csr.indptr,
        csr.indices,
        csr.eid,
        csr.lat_rad,
        csr.lon_rad,
        csr.cos_lat,
        shared.impassable,
        tables.hard_cargo,
        tables.length,
        tables.m_highway,
        risk,
        vf_flags,
        masks_hs,
        speed,
        is_tfl,
        is_green,
        bar,
        junc,
        unlit,
        bad,
        calm,
        sig,
        hill,
        live_add,
        live_env,
        live_sev,
        float(sc["hard_cost"]),
        float(sc["m_min"]),
        float(sc["r_min"]),
        float(sc["w_risk"]),
        float(sc["w_light"]),
        float(sc["w_surface"]),
        float(sc["w_hill"]),
        float(sc["w_speed"]),
        float(sc["w_barrier"]),
        float(sc["w_calming"]),
        float(sc["w_junction"]),
        float(sc["w_signal"]),
        float(sc["w_live"]),
        float(sc["w_live_cap"]),
        int(sc["cargo"]),
        int(sc["apply_live"]),
        int(sc["vf_mask"]),
        int(sc["vf_reward"]),
        float(sc["r_tfl"]),
        float(sc["r_green"]),
        float(sc["r_vf"]),
        int(sc["tfl_on"]),
        int(sc["green_on"]),
        int(sc["vf_on"]),
        float(cost_per_m),
        scratch.g,
        scratch.stamp,
        scratch.closed_stamp,
        scratch.parent,
        scratch.heap_f,
        scratch.heap_tie,
        scratch.heap_node,
        int(scratch.heap_cap),
        scratch.gen,
    )

    elapsed = time.perf_counter() - t0
    stats = {
        "expansions": int(expansions),
        "edge_relaxations": int(edge_relaxations),
        "elapsed_s": elapsed,
    }
    if found == -1 or found == -2:
        raise RuntimeError(
            f"Numba A* open-heap overflow (code={found}, expansions={expansions}). "
            "Scratch heap_cap too small — report graph sizes."
        )
    if expansions > csr.n_nodes:
        log.warning(
            "numba A* expansions=%d > n_nodes=%d (mode=%s) — heuristic may be broken",
            expansions,
            csr.n_nodes,
            mode,
        )
    if found != 1:
        raise nx.NetworkXNoPath(f"No path from {source} to {target}")

    # Reconstruct path (Python)
    path_idx = [int(t)]
    cur = int(t)
    parent = scratch.parent
    while cur != int(s):
        p = int(parent[cur])
        if p < 0:
            raise nx.NetworkXNoPath(f"Broken parent chain from {source} to {target}")
        path_idx.append(p)
        cur = p
    path_idx.reverse()
    path = [csr.idx_to_node[i] for i in path_idx]
    return path, stats


def warmup(csr, tables, shared, hard_cost: float = 1.0e12) -> float:
    """Compile Numba kernels once; returns compile+warmup seconds."""
    global _WARMED
    if not is_available() or csr is None or tables is None or shared is None:
        return 0.0
    if _WARMED:
        return 0.0
    t0 = time.perf_counter()
    get_scratch(csr.n_nodes, csr.n_edges)
    # Trivial same-node call still compiles wrappers; also run a tiny different pair.
    s_node = csr.idx_to_node[0]
    try:
        astar_numba_unidirectional(
            csr,
            s_node,
            s_node,
            tables,
            shared,
            mode="fastest",
            cost_per_m=1.0,
            hard_cost=hard_cost,
            bike_type="standard",
        )
    except Exception as exc:  # pragma: no cover
        log.warning("numba warmup same-node: %s", exc)

    # Force compile of both modes with a real search if neighbors exist
    if csr.n_nodes > 1 and int(csr.indptr[1]) > int(csr.indptr[0]):
        nbr = int(csr.indices[int(csr.indptr[0])])
        t_node = csr.idx_to_node[nbr]
        sc = pack_optimized_scalars(
            {
                "risk_weight": 0.0,
                "bike_type": "standard",
                "vf_shared_path": True,
                "vf_bus_lane": True,
                "vf_painted_lane": False,
            },
            shared,
            hard_cost,
            0.1,
            0.1,
        )
        try:
            astar_numba_unidirectional(
                csr,
                s_node,
                t_node,
                tables,
                shared,
                mode="fastest",
                cost_per_m=1.0,
                hard_cost=hard_cost,
            )
            astar_numba_unidirectional(
                csr,
                s_node,
                t_node,
                tables,
                shared,
                mode="optimized",
                cost_per_m=1.0,
                hard_cost=hard_cost,
                opt_scalars=sc,
            )
        except Exception as exc:  # pragma: no cover
            log.warning("numba warmup search: %s", exc)

    elapsed = time.perf_counter() - t0
    _WARMED = True
    log.info("pathfinding_numba: warmup %.2f s", elapsed)
    return elapsed
