"""
Signal clusters + edge entry/exit (Phase 1).

Groups nearby OSM traffic_signals nodes into one logical junction, **expands**
the cluster to untagged junction-interior nodes (footway / crossing mesh),
**merges** nearby seed clusters linked by short carriageway, then **closes** carriageway holes, then **spatially post-merges** nearby expanded
clusters (multi-box junctions) and re-marks entry/exit so former A→B links
become internal.

Expansion reaches the ped mesh via a short **road bridge** (≤2 hops on
carriageway stubs) then mesh-only BFS — so cut-throughs pay even when the
tagged stop-line is not on the footway.

Interior closure then claims unclaimed nodes that have ≥2 short-edge neighbours
in the same cluster (within close radius of a seed), converting through-junction
carriageway from repeated entries into internals.

Cost pays once per entry (like give_way).

Does NOT require rebuild_graph — uses existing node traffic_signals=yes tags.
Derived at routing-cache prebuild / cold app startup; persisted in the cache.

Kill-switch: SIGNAL_CLUSTERS=0|false|off → leave edges unmarked (legacy node cost).
"""
from __future__ import annotations

import math
import os
from collections import Counter, defaultdict, deque
from typing import Any

# Spatial merge radius (m) — same junction footprint (raised 25→30 Jul 2026).
SIGNAL_CLUSTER_RADIUS_M = 30.0
# Max graph path length (m) along internal edges between two signal nodes,
# and for expanding untagged interior nodes from signal seeds.
SIGNAL_CLUSTER_PATH_L_M = 40.0
SIGNAL_CLUSTER_CELL_DEG = 0.00032
# Non-internal highway types may still be walked if a single edge is this short
# (typical stop-line / corner links on the carriageway) — seed linking + road bridge.
SIGNAL_INTERNAL_EDGE_MAX_M = 25.0
# Max short carriageway hops from a signal seed to a ped/cycle portal before
# mesh-only expand. Noding shares the crossing vertex but does not collapse the
# junction to one node — stop-line → corner → zebra is often 2 hops.
SIGNAL_BRIDGE_MAX_HOPS = 2
# Second-pass cluster merge: short link between seeds of different clusters.
SIGNAL_CLUSTER_MERGE_MAX_M = 35.0
SIGNAL_CLUSTER_MERGE_MAX_HOPS = 2
# Interior closure: claim holes within this of a seed (≈ R + 10 m).
SIGNAL_CLUSTER_CLOSE_RADIUS_M = 40.0
# After expand+close: merge nearby *expanded* clusters (multi-box junctions).
# Direct member edge required (no multi-hop path glue through dense grids).
SIGNAL_POST_MERGE_CENTROID_M = 41.0

INTERNAL_HIGHWAY_TYPES = frozenset(
    {
        "footway",
        "path",
        "pedestrian",
        "crossing",
        "cycleway",
        "bridleway",
        "steps",
        "corridor",
    }
)

PED_ENTRY_HIGHWAY_TYPES = frozenset(
    {"footway", "path", "pedestrian", "steps", "corridor", "bridleway"}
)


def signal_clusters_enabled() -> bool:
    return _SIGNAL_CLUSTERS_ENABLED


def _refresh_signal_clusters_enabled() -> bool:
    global _SIGNAL_CLUSTERS_ENABLED
    _SIGNAL_CLUSTERS_ENABLED = os.environ.get("SIGNAL_CLUSTERS", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
    return _SIGNAL_CLUSTERS_ENABLED


_SIGNAL_CLUSTERS_ENABLED = True
_refresh_signal_clusters_enabled()


def is_signal_node(node_data: dict | None) -> bool:
    if not node_data:
        return False
    return str(node_data.get("traffic_signals", "")).lower() == "yes"


def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _node_lon_lat(node_id) -> tuple[float, float]:
    return float(node_id[0]), float(node_id[1])


def _edge_attrs(G, u, v) -> dict | None:
    ed = G.get_edge_data(u, v)
    if not ed:
        ed = G.get_edge_data(v, u)
    if not ed:
        return None
    if "length" not in ed and ed and all(isinstance(k, int) for k in ed.keys()):
        return next(iter(ed.values()))
    return ed


def _edge_length_m(edge_data: dict | None) -> float:
    if not edge_data:
        return 0.5
    length = float(edge_data.get("length", 0.0) or 0.0)
    return length if length > 0 else 0.5


def _edge_allowed_internal(edge_data: dict | None, length_m: float) -> bool:
    """Link signal *seeds* (includes short road corner stubs)."""
    if not edge_data:
        return False
    highway = str(edge_data.get("type", "")).strip().lower()
    if highway in INTERNAL_HIGHWAY_TYPES:
        return True
    return length_m <= SIGNAL_INTERNAL_EDGE_MAX_M


def _edge_allowed_expansion(edge_data: dict | None, length_m: float) -> bool:
    """
    Claim untagged *interior* nodes — ped/cycle/crossing mesh only.

    Must NOT include short carriageway stubs, or every approach within R is
    swallowed into the cluster and footway entries disappear.
    """
    del length_m
    if not edge_data:
        return False
    highway = str(edge_data.get("type", "")).strip().lower()
    return highway in INTERNAL_HIGHWAY_TYPES


def _edge_is_mesh(edge_data: dict | None) -> bool:
    if not edge_data:
        return False
    return str(edge_data.get("type", "")).strip().lower() in INTERNAL_HIGHWAY_TYPES


def _node_touches_mesh(G, nid) -> bool:
    for v in _neighbors_undirected(G, nid):
        if _edge_is_mesh(_edge_attrs(G, nid, v)):
            return True
    return False


def _road_bridge_portals(
    G,
    seed,
    *,
    max_hops: int = SIGNAL_BRIDGE_MAX_HOPS,
    edge_max_m: float = SIGNAL_INTERNAL_EDGE_MAX_M,
    path_max_m: float = SIGNAL_CLUSTER_PATH_L_M,
    r_m: float = SIGNAL_CLUSTER_RADIUS_M,
) -> dict[Any, float]:
    """
    Seed plus nodes reached by ≤ ``max_hops`` short *non-mesh* edges within R.

    These are BFS *starts* for mesh expansion only — claiming still requires a
    mesh-incident node (see ``expand_cluster_membership``).
    """
    portals: dict[Any, float] = {seed: 0.0}
    q: deque = deque([(seed, 0.0, 0)])  # node, path_m, hops
    lon_s, lat_s = _node_lon_lat(seed)
    while q:
        u, path_m, hops = q.popleft()
        if hops >= max_hops:
            continue
        for v in _neighbors_undirected(G, u):
            ed = _edge_attrs(G, u, v)
            if not ed or _edge_is_mesh(ed):
                continue
            length = _edge_length_m(ed)
            if length > edge_max_m:
                continue
            nd = path_m + length
            if nd > path_max_m:
                continue
            lon_v, lat_v = _node_lon_lat(v)
            if _haversine_m(lon_s, lat_s, lon_v, lat_v) > r_m:
                continue
            prev = portals.get(v)
            if prev is not None and prev <= nd:
                continue
            portals[v] = nd
            q.append((v, nd, hops + 1))
    return portals


def _clear_signal_edge_marks(G) -> None:
    for _u, _v, d in G.edges(data=True):
        d.pop("signal_entry", None)
        d.pop("signal_exit", None)
        d.pop("signal_cluster_id", None)
        d.pop("signal_entry_lat", None)
        d.pop("signal_entry_lon", None)
        d.pop("signal_exit_lat", None)
        d.pop("signal_exit_lon", None)
    for _nid, nd in G.nodes(data=True):
        nd.pop("signal_cluster_id", None)
        nd.pop("signal_cluster_rep", None)
        nd.pop("signal_cluster_seed", None)


def _neighbors_undirected(G, u):
    seen = set()
    if hasattr(G, "successors"):
        for v in G.successors(u):
            if v not in seen:
                seen.add(v)
                yield v
    if hasattr(G, "predecessors"):
        for v in G.predecessors(u):
            if v not in seen:
                seen.add(v)
                yield v


def _bfs_within_path_m(
    G,
    start,
    max_path_m: float,
    *,
    expansion_mesh: bool = False,
) -> dict[Any, float]:
    allow = _edge_allowed_expansion if expansion_mesh else _edge_allowed_internal
    dist = {start: 0.0}
    q: deque = deque([start])
    while q:
        u = q.popleft()
        du = dist[u]
        for v in _neighbors_undirected(G, u):
            ed = _edge_attrs(G, u, v)
            if not ed:
                continue
            length = _edge_length_m(ed)
            if not allow(ed, length):
                continue
            nd = du + length
            if nd > max_path_m:
                continue
            prev = dist.get(v)
            if prev is not None and prev <= nd:
                continue
            dist[v] = nd
            q.append(v)
    return dist


def build_signal_clusters(G) -> dict[Any, int]:
    """node → cluster_id for traffic_signals *seeds* only."""
    signals = [n for n, nd in G.nodes(data=True) if is_signal_node(nd)]
    if not signals:
        return {}

    signal_set = set(signals)
    parent = {n: n for n in signals}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    r_m = SIGNAL_CLUSTER_RADIUS_M
    l_m = SIGNAL_CLUSTER_PATH_L_M

    for s in signals:
        lon1, lat1 = _node_lon_lat(s)
        reached = _bfs_within_path_m(G, s, l_m, expansion_mesh=False)
        for t in reached:
            if t == s or t not in signal_set:
                continue
            lon2, lat2 = _node_lon_lat(t)
            if _haversine_m(lon1, lat1, lon2, lat2) <= r_m:
                union(s, t)

    roots: dict[Any, list] = defaultdict(list)
    for s in signals:
        roots[find(s)].append(s)

    cluster_of: dict[Any, int] = {}
    for i, members in enumerate(roots.values(), start=1):
        for n in members:
            cluster_of[n] = i
    return cluster_of


def merge_adjacent_clusters(
    G,
    seed_cluster_of: dict[Any, int],
) -> tuple[dict[Any, int], int]:
    """
    Union seed clusters linked by a short carriageway/mesh path (≤ hops / metres).

    Catches corner-signal pairs that fail crow-flies R but share one junction.
    Returns (remapped seed_cluster_of, n_clusters_merged_away).
    """
    if not seed_cluster_of:
        return {}, 0

    cids = sorted(set(int(c) for c in seed_cluster_of.values()))
    parent = {c: c for c in cids}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> bool:
        ra, rb = find(a), find(b)
        if ra == rb:
            return False
        parent[rb] = ra
        return True

    n_before = len(cids)
    max_hops = SIGNAL_CLUSTER_MERGE_MAX_HOPS
    max_path = SIGNAL_CLUSTER_MERGE_MAX_M
    edge_max = SIGNAL_INTERNAL_EDGE_MAX_M

    for s, cid in seed_cluster_of.items():
        cid = int(cid)
        dist: dict[Any, tuple[int, float]] = {s: (0, 0.0)}
        q: deque = deque([s])
        while q:
            u = q.popleft()
            hops, path_m = dist[u]
            if hops >= max_hops:
                continue
            for v in _neighbors_undirected(G, u):
                ed = _edge_attrs(G, u, v)
                if not ed:
                    continue
                length = _edge_length_m(ed)
                if length > edge_max:
                    continue
                nd = path_m + length
                if nd > max_path:
                    continue
                prev = dist.get(v)
                if prev is not None and prev[0] <= hops + 1 and prev[1] <= nd:
                    continue
                dist[v] = (hops + 1, nd)
                other = seed_cluster_of.get(v)
                if other is not None and int(other) != cid:
                    union(cid, int(other))
                q.append(v)

    # Remap to contiguous ids 1..N
    root_to_new: dict[int, int] = {}
    remapped: dict[Any, int] = {}
    next_id = 1
    for n, cid in seed_cluster_of.items():
        root = find(int(cid))
        if root not in root_to_new:
            root_to_new[root] = next_id
            next_id += 1
        remapped[n] = root_to_new[root]

    n_after = len(root_to_new)
    return remapped, n_before - n_after


def expand_cluster_membership(
    G,
    seed_cluster_of: dict[Any, int],
) -> dict[Any, int]:
    """
    Expand each seed cluster onto untagged ped/cycle/crossing mesh nodes.

    From each seed: up to ``SIGNAL_BRIDGE_MAX_HOPS`` short carriageway stubs
    (within R / L) yield *portals*; mesh-only BFS runs from each portal.
    Claim mesh-incident nodes within R of a seed. Pure road bridge nodes that
    do not touch the mesh are not claimed here (closure fills holes later).
    Conflicts → closer seed (bridge+mesh path_dist, then haversine).
    """
    if not seed_cluster_of:
        return {}

    seeds_by_cid: dict[int, list] = defaultdict(list)
    for nid, cid in seed_cluster_of.items():
        seeds_by_cid[int(cid)].append(nid)

    claims: dict[Any, tuple[float, float, int]] = {}
    r_m = SIGNAL_CLUSTER_RADIUS_M
    l_m = SIGNAL_CLUSTER_PATH_L_M

    for cid, seeds in seeds_by_cid.items():
        seed_set = set(seeds)
        for s in seeds:
            portals = _road_bridge_portals(G, s)
            for portal, bridge_m in portals.items():
                remaining = l_m - bridge_m
                if remaining < 0:
                    continue
                dist_map = _bfs_within_path_m(
                    G, portal, remaining, expansion_mesh=True
                )
                for n, mesh_d in dist_map.items():
                    # Do not absorb carriageway stubs: only mesh / seeds.
                    if n not in seed_set and mesh_d <= 0 and not _node_touches_mesh(G, n):
                        continue
                    lon_n, lat_n = _node_lon_lat(n)
                    near = False
                    min_hav = float("inf")
                    for seed in seed_set:
                        hav = _haversine_m(lon_n, lat_n, *_node_lon_lat(seed))
                        if hav < min_hav:
                            min_hav = hav
                        if hav <= r_m:
                            near = True
                    if not near:
                        continue
                    path_d = bridge_m + mesh_d
                    prev = claims.get(n)
                    cand = (path_d, min_hav, cid)
                    if prev is None or cand < prev:
                        claims[n] = cand

    expanded = {n: cid for n, (_pd, _hav, cid) in claims.items()}
    for n, cid in seed_cluster_of.items():
        expanded[n] = int(cid)
    return expanded


def close_cluster_interior(
    G,
    cluster_of: dict[Any, int],
    seed_cluster_of: dict[Any, int],
) -> tuple[dict[Any, int], int, int]:
    """
    Claim unclaimed nodes that sit *inside* a cluster footprint.

    A node is claimed when it has ≥2 short-edge neighbours in exactly one
    cluster and lies within ``SIGNAL_CLUSTER_CLOSE_RADIUS_M`` of a seed of
    that cluster. Approaches with a single cluster neighbour stay outside.

    Returns (cluster_of, closed_nodes, holes_remaining).
    """
    if not cluster_of:
        return {}, 0, 0

    out = dict(cluster_of)
    seeds_by_cid: dict[int, list] = defaultdict(list)
    for n, cid in seed_cluster_of.items():
        seeds_by_cid[int(cid)].append(n)

    members_by_cid: dict[int, set] = defaultdict(set)
    for n, cid in out.items():
        members_by_cid[int(cid)].add(n)

    edge_max = SIGNAL_INTERNAL_EDGE_MAX_M
    close_r = SIGNAL_CLUSTER_CLOSE_RADIUS_M
    closed = 0
    changed = True
    while changed:
        changed = False
        candidates: set = set()
        for cid, members in members_by_cid.items():
            for m in members:
                for v in _neighbors_undirected(G, m):
                    if v in out:
                        continue
                    ed = _edge_attrs(G, m, v)
                    if not ed:
                        continue
                    if _edge_length_m(ed) > edge_max:
                        continue
                    candidates.add(v)

        for v in candidates:
            if v in out:
                continue
            counts: Counter[int] = Counter()
            for w in _neighbors_undirected(G, v):
                cid = out.get(w)
                if not cid:
                    continue
                ed = _edge_attrs(G, v, w)
                if not ed or _edge_length_m(ed) > edge_max:
                    continue
                counts[int(cid)] += 1
            qualifying = [c for c, n in counts.items() if n >= 2]
            if len(qualifying) != 1:
                continue
            cid = qualifying[0]
            seeds = seeds_by_cid.get(cid) or []
            if not seeds:
                continue
            lon_v, lat_v = _node_lon_lat(v)
            if not any(
                _haversine_m(lon_v, lat_v, *_node_lon_lat(s)) <= close_r for s in seeds
            ):
                continue
            out[v] = cid
            members_by_cid[cid].add(v)
            closed += 1
            changed = True

    holes = _count_cluster_holes(G, out)
    return out, closed, holes


def _count_cluster_holes(G, cluster_of: dict[Any, int]) -> int:
    """Unclaimed nodes with ≥2 short-edge neighbours in the same cluster."""
    edge_max = SIGNAL_INTERNAL_EDGE_MAX_M
    holes = 0
    for n in G.nodes:
        if n in cluster_of:
            continue
        counts: Counter[int] = Counter()
        for v in _neighbors_undirected(G, n):
            cid = cluster_of.get(v)
            if not cid:
                continue
            ed = _edge_attrs(G, n, v)
            if not ed or _edge_length_m(ed) > edge_max:
                continue
            counts[int(cid)] += 1
        if any(k >= 2 for k in counts.values()):
            holes += 1
    return holes


def _cluster_centroid(members: list) -> tuple[float, float] | None:
    if not members:
        return None
    lon = sum(float(n[0]) for n in members) / len(members)
    lat = sum(float(n[1]) for n in members) / len(members)
    return lon, lat


def spatial_post_merge(
    G,
    cluster_of: dict[Any, int],
    seed_cluster_of: dict[Any, int],
) -> tuple[dict[Any, int], dict[Any, int], int]:
    """
    Merge expanded clusters that sit on the same physical junction.

    Union when centroids ≤ ``SIGNAL_POST_MERGE_CENTROID_M`` **and** some
    member of A shares a **direct** graph edge with some member of B.
    No seed-cap rule and no multi-hop path glue (those over-merged dense grids).

    Remaps cluster ids on membership and seeds. Returns
    (cluster_of, seed_cluster_of, n_clusters_merged_away).
    """
    if not cluster_of:
        return {}, dict(seed_cluster_of), 0

    members_by_cid: dict[int, list] = defaultdict(list)
    for n, cid in cluster_of.items():
        members_by_cid[int(cid)].append(n)

    cids = sorted(members_by_cid.keys())
    n_before = len(cids)
    if n_before <= 1:
        return dict(cluster_of), dict(seed_cluster_of), 0

    parent = {c: c for c in cids}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> bool:
        ra, rb = find(a), find(b)
        if ra == rb:
            return False
        parent[rb] = ra
        return True

    centroids: dict[int, tuple[float, float]] = {}
    for c in cids:
        cen = _cluster_centroid(members_by_cid[c])
        if cen is not None:
            centroids[c] = cen

    # Direct edge links between clusters (scan once).
    edge_linked: set[tuple[int, int]] = set()
    for u, v in G.edges():
        cu = int(cluster_of.get(u) or 0)
        cv = int(cluster_of.get(v) or 0)
        if cu > 0 and cv > 0 and cu != cv:
            edge_linked.add((cu, cv) if cu < cv else (cv, cu))

    centroid_cap = SIGNAL_POST_MERGE_CENTROID_M
    for ca, cb in edge_linked:
        cen_a = centroids.get(ca)
        cen_b = centroids.get(cb)
        if not cen_a or not cen_b:
            continue
        d_cent = _haversine_m(cen_a[0], cen_a[1], cen_b[0], cen_b[1])
        if d_cent <= centroid_cap:
            union(ca, cb)

    root_to_new: dict[int, int] = {}
    next_id = 1
    for c in cids:
        root = find(c)
        if root not in root_to_new:
            root_to_new[root] = next_id
            next_id += 1

    new_cluster = {n: root_to_new[find(int(cid))] for n, cid in cluster_of.items()}
    new_seeds: dict[Any, int] = {}
    for n, cid in seed_cluster_of.items():
        root = find(int(cid))
        if root in root_to_new:
            new_seeds[n] = root_to_new[root]

    n_after = len(root_to_new)
    return new_cluster, new_seeds, n_before - n_after


def _cluster_representatives(G, cluster_of: dict[Any, int], seeds: set) -> dict[int, Any]:
    members: dict[int, list] = defaultdict(list)
    for n, cid in cluster_of.items():
        members[cid].append(n)

    reps: dict[int, Any] = {}
    for cid, nodes in members.items():
        seed_nodes = [n for n in nodes if n in seeds]
        pool = seed_nodes or nodes

        def score(nid):
            deg = int(G.degree(nid)) if hasattr(G, "degree") else 0
            return (deg, -abs(float(nid[0])), -abs(float(nid[1])))

        reps[cid] = max(pool, key=score)
    return reps


def _highway_type(edge_data: dict) -> str:
    return str(edge_data.get("type", "")).strip().lower() or "unknown"


def mark_signal_entry_exit_edges(
    G,
    cluster_of: dict[Any, int] | None = None,
    seed_cluster_of: dict[Any, int] | None = None,
    *,
    merged_pairs: int = 0,
    closed_nodes: int = 0,
    holes_remaining: int = 0,
    post_merged: int = 0,
) -> dict[str, Any]:
    _clear_signal_edge_marks(G)
    if not signal_clusters_enabled():
        return {
            "enabled": 0,
            "signal_nodes": 0,
            "clusters": 0,
            "expanded_nodes": 0,
            "entry_edges": 0,
            "exit_edges": 0,
            "entry_by_highway": {},
            "entry_ped_edges": 0,
            "merged_pairs": 0,
            "closed_nodes": 0,
            "holes_remaining": 0,
            "post_merged": 0,
        }

    if seed_cluster_of is None:
        seed_cluster_of = build_signal_clusters(G)
        seed_cluster_of, merged_pairs = merge_adjacent_clusters(G, seed_cluster_of)
    if cluster_of is None:
        cluster_of = expand_cluster_membership(G, seed_cluster_of)
        cluster_of, c1, _ = close_cluster_interior(G, cluster_of, seed_cluster_of)
        cluster_of, seed_cluster_of, post_merged = spatial_post_merge(
            G, cluster_of, seed_cluster_of
        )
        cluster_of, c2, holes_remaining = close_cluster_interior(
            G, cluster_of, seed_cluster_of
        )
        closed_nodes = c1 + c2

    seeds = set(seed_cluster_of.keys())
    for nid, nd in G.nodes(data=True):
        cid = cluster_of.get(nid)
        if cid is not None:
            nd["signal_cluster_id"] = int(cid)
            if nid in seeds:
                nd["signal_cluster_seed"] = True

    reps = _cluster_representatives(G, cluster_of, seeds)
    for cid, rep in reps.items():
        if rep in G.nodes:
            G.nodes[rep]["signal_cluster_rep"] = True

    def cid_of(nid) -> int:
        return int(cluster_of.get(nid) or 0)

    entry_n = 0
    exit_n = 0
    entry_by_highway: dict[str, int] = defaultdict(int)
    entry_ped = 0

    for u, v, d in G.edges(data=True):
        cu, cv = cid_of(u), cid_of(v)
        if cu == 0 and cv == 0:
            continue
        if cu == 0 and cv > 0:
            d["signal_entry"] = True
            d["signal_cluster_id"] = cv
            rep = reps.get(cv, v)
            d["signal_entry_lon"] = float(rep[0])
            d["signal_entry_lat"] = float(rep[1])
            entry_n += 1
            hw = _highway_type(d)
            entry_by_highway[hw] += 1
            if hw in PED_ENTRY_HIGHWAY_TYPES:
                entry_ped += 1
        elif cu > 0 and cv == 0:
            d["signal_exit"] = True
            d["signal_cluster_id"] = cu
            rep = reps.get(cu, u)
            d["signal_exit_lon"] = float(rep[0])
            d["signal_exit_lat"] = float(rep[1])
            exit_n += 1
        elif cu > 0 and cv > 0 and cu != cv:
            d["signal_exit"] = True
            d["signal_entry"] = True
            d["signal_cluster_id"] = cv
            rep_in = reps.get(cv, v)
            rep_out = reps.get(cu, u)
            d["signal_entry_lon"] = float(rep_in[0])
            d["signal_entry_lat"] = float(rep_in[1])
            d["signal_exit_lon"] = float(rep_out[0])
            d["signal_exit_lat"] = float(rep_out[1])
            entry_n += 1
            exit_n += 1
            hw = _highway_type(d)
            entry_by_highway[hw] += 1
            if hw in PED_ENTRY_HIGHWAY_TYPES:
                entry_ped += 1

    return {
        "enabled": 1,
        "signal_nodes": len(seed_cluster_of),
        "clusters": len(reps),
        "expanded_nodes": len(cluster_of),
        "entry_edges": entry_n,
        "exit_edges": exit_n,
        "entry_by_highway": dict(sorted(entry_by_highway.items(), key=lambda kv: -kv[1])),
        "entry_ped_edges": entry_ped,
        "merged_pairs": int(merged_pairs),
        "closed_nodes": int(closed_nodes),
        "holes_remaining": int(holes_remaining),
        "post_merged": int(post_merged),
    }


def apply_signal_clusters(G, wait_metres: float | None = None) -> dict[str, Any]:
    del wait_metres
    if not signal_clusters_enabled():
        return mark_signal_entry_exit_edges(G, {}, {})
    seeds = build_signal_clusters(G)
    seeds, merged_pairs = merge_adjacent_clusters(G, seeds)
    expanded = expand_cluster_membership(G, seeds)
    expanded, closed1, _holes1 = close_cluster_interior(G, expanded, seeds)
    expanded, seeds, post_merged = spatial_post_merge(G, expanded, seeds)
    expanded, closed2, holes_remaining = close_cluster_interior(G, expanded, seeds)
    return mark_signal_entry_exit_edges(
        G,
        expanded,
        seeds,
        merged_pairs=merged_pairs,
        closed_nodes=closed1 + closed2,
        holes_remaining=holes_remaining,
        post_merged=post_merged,
    )


def edge_has_signal_entry(edge_data: dict | None) -> bool:
    if not edge_data:
        return False
    return edge_data.get("signal_entry") in (True, 1, "1", "yes", "true")


def edge_has_signal_exit(edge_data: dict | None) -> bool:
    if not edge_data:
        return False
    return edge_data.get("signal_exit") in (True, 1, "1", "yes", "true")
