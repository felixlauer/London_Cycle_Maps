"""
Static routing cache: prebuilt once after the graph pipeline, loaded at server start.

Artifacts (next to the final graph):
  1_data/london_elev_final_tfl.routing_cache/
    meta.json
    tables.npz          # EdgeCostTables columns (uncompressed .npz for fast load)
    park_oh_exprs.json
    floors.json
    csr.npz             # CSR arrays + idx_to_node (n,2)
    nodes.npz           # car counts, dangerous flags, cluster-suppressed (CSR order)
    edges.npz           # edge_u/edge_v (n,2) endpoints aligned with table rows
    geom_offsets.npy    # int64 offsets (mmap-friendly)
    geom_flat.npy       # float32 (n_pts, 2) lat/lon
    geom_wkb.npz        # offsets + uint8 blob (Shapely WKB for STRtree)

Bump CACHE_FORMAT_VERSION or FORMULA_ID when on-disk layout or cost logic changes.
Kill-switch: ROUTING_CACHE=0|false|off → ignore cache and rebuild at startup.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

log = logging.getLogger("routing_cache")

# Bump when npz/json/npy layout or apply semantics change (v2: lazy geom store, .npy).
CACHE_FORMAT_VERSION = 2
# Bump when edge-cost / junction / heuristic-floor formulas change (invalidates cache).
FORMULA_ID = "2026-07-13-v1"

TABLE_ARRAY_NAMES = (
    "length",
    "risk",
    "vf_flags",
    "masks_hill_surface",
    "speed_stress",
    "is_tfl",
    "is_green",
    "m_highway",
    "barrier_base",
    "calming_base",
    "signal_base",
    "junction_base",
    "unlit_base",
    "bad_surf_base",
    "hard_static",
    "hill_base",
    "hard_cargo",
    "is_park",
    "park_oh_id",
)


@dataclass
class RoutingCacheBundle:
    """In-memory cache payload after load (before apply)."""

    meta: dict
    tables_arrays: dict[str, np.ndarray]
    park_oh_exprs: list[str]
    floors: dict[str, float]
    csr_arrays: dict[str, np.ndarray]
    car_physical_road_count: np.ndarray
    is_dangerous_junction: np.ndarray
    cluster_suppressed: np.ndarray
    edge_u: np.ndarray
    edge_v: np.ndarray
    geom_offsets: np.ndarray
    geom_flat: np.ndarray  # float32 (n_pts, 2) lat,lon
    wkb_offsets: np.ndarray
    wkb_blob: np.ndarray  # uint8


def cache_enabled() -> bool:
    raw = os.environ.get("ROUTING_CACHE", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def default_cache_dir(graph_path: str | Path) -> Path:
    """
    Companion directory for a graph path.
    london_elev_final_tfl.graphml|gpickle → london_elev_final_tfl.routing_cache/
    """
    p = Path(graph_path).resolve()
    name = p.name
    for suf in (".gpickle", ".graphml", ".pickle"):
        if name.endswith(suf):
            name = name[: -len(suf)]
            break
    return p.parent / f"{name}.routing_cache"


def graph_fingerprint(graph_path: str | Path, G=None) -> dict[str, Any]:
    """Stable-ish identity for invalidation (size/mtime + optional counts)."""
    p = Path(graph_path)
    # Prefer gpickle companion when callers pass .graphml
    candidates = [p]
    if p.suffix == ".graphml":
        candidates.insert(0, p.with_suffix(".gpickle"))
    chosen = None
    for c in candidates:
        if c.is_file():
            chosen = c
            break
    if chosen is None:
        chosen = p
    st = chosen.stat() if chosen.is_file() else None
    fp = {
        "path": str(chosen),
        "size": int(st.st_size) if st else None,
        "mtime_ns": int(st.st_mtime_ns) if st else None,
    }
    if G is not None:
        fp["n_nodes"] = int(G.number_of_nodes())
        fp["n_edges"] = int(G.number_of_edges())
    return fp


def _node_to_xy(nid) -> tuple[float, float]:
    if isinstance(nid, tuple) and len(nid) >= 2:
        return float(nid[0]), float(nid[1])
    raise TypeError(f"Unsupported node id type for cache: {type(nid)!r}")


def _xy_to_node(xy: np.ndarray):
    return (float(xy[0]), float(xy[1]))


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_routing_cache(
    cache_dir: Path,
    *,
    graph_path: str | Path,
    G,
    tables,
    csr,
    floors: dict[str, float],
    junction_suppressed: frozenset | set,
    build_timings: dict[str, float] | None = None,
) -> dict[str, Any]:
    """
    Persist tables, CSR, junction flags, floors, edge geom coords + WKB.

    Requires d['_eid'] on edges and junction flags already on nodes.
    Builds geom arrays from WKT (or existing _coords) in edge-table order.
    """
    from shapely.geometry import LineString
    from shapely.wkt import loads as load_wkt

    t_all = time.perf_counter()
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    if getattr(G, "is_multigraph", lambda: False)():
        raise ValueError(
            "routing cache save refuses MultiDiGraph (need edge keys in sidecar)"
        )

    n_edges = int(tables.n_edges)
    n_nodes = int(csr.n_nodes)

    # --- edges aligned with table rows via _eid ---
    edge_u = np.empty((n_edges, 2), dtype=np.float64)
    edge_v = np.empty((n_edges, 2), dtype=np.float64)
    edge_by_eid: list = [None] * n_edges
    missing = 0
    for u, v, d in G.edges(data=True):
        eid = d.get("_eid")
        if eid is None:
            missing += 1
            continue
        i = int(eid)
        if i < 0 or i >= n_edges:
            raise ValueError(f"_eid out of range: {i}")
        edge_u[i] = _node_to_xy(u)
        edge_v[i] = _node_to_xy(v)
        edge_by_eid[i] = (u, v, d)
    if missing:
        raise ValueError(f"{missing} edges missing _eid; cannot save cache")
    if any(x is None for x in edge_by_eid):
        raise ValueError("edge table has gaps vs _eid stamping")

    # --- node flags in CSR order ---
    car_count = np.empty(n_nodes, dtype=np.int16)
    dangerous = np.empty(n_nodes, dtype=np.uint8)
    suppressed = np.zeros(n_nodes, dtype=np.uint8)
    idx_to_node = np.empty((n_nodes, 2), dtype=np.float64)
    for i, nid in enumerate(csr.idx_to_node):
        idx_to_node[i] = _node_to_xy(nid)
        nd = G.nodes[nid]
        car_count[i] = int(nd.get("car_physical_road_count", 0))
        dangerous[i] = 1 if nd.get("is_dangerous_junction") else 0
        if nid in junction_suppressed:
            suppressed[i] = 1

    # --- tables ---
    tables_dict = {name: np.asarray(getattr(tables, name)) for name in TABLE_ARRAY_NAMES}
    tables_dict["n_edges"] = np.asarray([n_edges], dtype=np.int64)

    # --- CSR ---
    csr_dict = {
        "indptr": np.asarray(csr.indptr, dtype=np.int64),
        "indices": np.asarray(csr.indices, dtype=np.int32),
        "eid": np.asarray(csr.eid, dtype=np.int32),
        "lon": np.asarray(csr.lon, dtype=np.float64),
        "lat": np.asarray(csr.lat, dtype=np.float64),
        "lon_rad": np.asarray(csr.lon_rad, dtype=np.float64),
        "lat_rad": np.asarray(csr.lat_rad, dtype=np.float64),
        "cos_lat": np.asarray(csr.cos_lat, dtype=np.float64),
        "idx_to_node": idx_to_node,
        "n_nodes": np.asarray([n_nodes], dtype=np.int64),
        "n_edges": np.asarray([int(csr.n_edges)], dtype=np.int64),
    }

    # --- geometry: coords (lat,lon) + WKB in table/eid order ---
    t_geom = time.perf_counter()
    offsets = np.zeros(n_edges + 1, dtype=np.int64)
    coords_chunks: list[np.ndarray] = []
    wkb_chunks: list[bytes] = []
    wkb_offsets = np.zeros(n_edges + 1, dtype=np.int64)
    n_pts = 0
    n_wkb = 0
    for i, (u, v, d) in enumerate(edge_by_eid):
        coords = d.get("_coords")
        if coords is None:
            from edge_geom_store import parse_edge_coords_no_write

            coords = parse_edge_coords_no_write(G, u, v, d)
        arr = np.asarray(coords, dtype=np.float32).reshape(-1, 2)
        coords_chunks.append(arr)
        offsets[i] = n_pts
        n_pts += arr.shape[0]

        wkt = d.get("geometry")
        if wkt:
            try:
                line = load_wkt(wkt)
            except Exception:
                line = LineString(
                    [
                        (float(G.nodes[u]["x"]), float(G.nodes[u]["y"])),
                        (float(G.nodes[v]["x"]), float(G.nodes[v]["y"])),
                    ]
                )
        else:
            line = LineString(
                [
                    (float(G.nodes[u]["x"]), float(G.nodes[u]["y"])),
                    (float(G.nodes[v]["x"]), float(G.nodes[v]["y"])),
                ]
            )
        blob = line.wkb
        wkb_chunks.append(blob)
        wkb_offsets[i] = n_wkb
        n_wkb += len(blob)
    offsets[-1] = n_pts
    wkb_offsets[-1] = n_wkb
    geom_flat = (
        np.vstack(coords_chunks).astype(np.float32)
        if coords_chunks
        else np.empty((0, 2), dtype=np.float32)
    )
    wkb_blob = np.empty(n_wkb, dtype=np.uint8)
    pos = 0
    for blob in wkb_chunks:
        n = len(blob)
        wkb_blob[pos : pos + n] = np.frombuffer(blob, dtype=np.uint8)
        pos += n
    geom_s = time.perf_counter() - t_geom

    # --- write files (uncompressed npz = stored, fast load) ---
    np.savez(cache_dir / "tables.npz", **tables_dict)
    np.savez(cache_dir / "csr.npz", **csr_dict)
    np.savez(
        cache_dir / "nodes.npz",
        car_physical_road_count=car_count,
        is_dangerous_junction=dangerous,
        cluster_suppressed=suppressed,
    )
    np.savez(cache_dir / "edges.npz", edge_u=edge_u, edge_v=edge_v)
    # Standalone .npy for mmap-friendly lazy geom store (not .npz).
    np.save(cache_dir / "geom_offsets.npy", offsets)
    np.save(cache_dir / "geom_flat.npy", geom_flat)
    # Remove legacy geom_coords.npz if present from older format.
    legacy = cache_dir / "geom_coords.npz"
    if legacy.is_file():
        try:
            legacy.unlink()
        except OSError:
            pass
    np.savez(
        cache_dir / "geom_wkb.npz",
        offsets=wkb_offsets,
        blob=wkb_blob,
    )
    _write_json(cache_dir / "park_oh_exprs.json", list(tables.park_oh_exprs))
    _write_json(cache_dir / "floors.json", {k: float(v) for k, v in floors.items()})

    meta = {
        "cache_format_version": CACHE_FORMAT_VERSION,
        "formula_id": FORMULA_ID,
        "graph": graph_fingerprint(graph_path, G),
        "n_nodes": n_nodes,
        "n_edges": n_edges,
        "n_coord_points": int(n_pts),
        "n_wkb_bytes": int(n_wkb),
        "build_timings_s": build_timings or {},
        "geom_extract_s": round(geom_s, 3),
        "save_wall_s": round(time.perf_counter() - t_all, 3),
    }
    # Content hash over key array shapes for quick sanity
    h = hashlib.sha256()
    h.update(edge_u.tobytes())
    h.update(edge_v.tobytes())
    h.update(tables_dict["length"].tobytes())
    h.update(csr_dict["indptr"].tobytes())
    meta["content_sha256_16"] = h.hexdigest()[:16]
    _write_json(cache_dir / "meta.json", meta)
    log.info(
        "routing_cache: saved %s (%d edges, geom %.1fs, total %.1fs)",
        cache_dir,
        n_edges,
        geom_s,
        meta["save_wall_s"],
    )
    return meta


def meta_compatible(meta: dict, graph_path: str | Path, G) -> tuple[bool, str]:
    if int(meta.get("cache_format_version", -1)) != CACHE_FORMAT_VERSION:
        return False, "cache_format_version mismatch"
    if str(meta.get("formula_id", "")) != FORMULA_ID:
        return False, f"formula_id mismatch (cache={meta.get('formula_id')}, code={FORMULA_ID})"
    fp = graph_fingerprint(graph_path, G)
    gmeta = meta.get("graph") or {}
    if gmeta.get("size") != fp.get("size") or gmeta.get("mtime_ns") != fp.get("mtime_ns"):
        return False, "graph file size/mtime mismatch"
    if fp.get("n_nodes") is not None and int(meta.get("n_nodes", -1)) != int(fp["n_nodes"]):
        return False, "n_nodes mismatch"
    if fp.get("n_edges") is not None and int(meta.get("n_edges", -1)) != int(fp["n_edges"]):
        return False, "n_edges mismatch"
    return True, "ok"


def load_routing_cache(cache_dir: Path, *, mmap_geom: bool = True) -> RoutingCacheBundle:
    cache_dir = Path(cache_dir)
    meta = _read_json(cache_dir / "meta.json")
    tables_npz = np.load(cache_dir / "tables.npz")
    tables_arrays = {k: tables_npz[k] for k in tables_npz.files}
    csr_npz = np.load(cache_dir / "csr.npz")
    csr_arrays = {k: csr_npz[k] for k in csr_npz.files}
    nodes = np.load(cache_dir / "nodes.npz")
    edges = np.load(cache_dir / "edges.npz")
    mmap_mode = "r" if mmap_geom else None
    offsets_path = cache_dir / "geom_offsets.npy"
    flat_path = cache_dir / "geom_flat.npy"
    if offsets_path.is_file() and flat_path.is_file():
        geom_offsets = np.load(offsets_path, mmap_mode=mmap_mode)
        geom_flat = np.load(flat_path, mmap_mode=mmap_mode)
    else:
        # Legacy v1: geom_coords.npz (will fail format version check on v2+)
        geom = np.load(cache_dir / "geom_coords.npz")
        geom_offsets = geom["offsets"]
        geom_flat = geom["flat"]
    wkb = np.load(cache_dir / "geom_wkb.npz")
    park_oh_exprs = list(_read_json(cache_dir / "park_oh_exprs.json"))
    floors = {k: float(v) for k, v in _read_json(cache_dir / "floors.json").items()}
    return RoutingCacheBundle(
        meta=meta,
        tables_arrays=tables_arrays,
        park_oh_exprs=park_oh_exprs,
        floors=floors,
        csr_arrays=csr_arrays,
        car_physical_road_count=nodes["car_physical_road_count"],
        is_dangerous_junction=nodes["is_dangerous_junction"],
        cluster_suppressed=nodes["cluster_suppressed"],
        edge_u=edges["edge_u"],
        edge_v=edges["edge_v"],
        geom_offsets=geom_offsets,
        geom_flat=geom_flat,
        wkb_offsets=wkb["offsets"],
        wkb_blob=wkb["blob"],
    )


def bundle_to_tables(bundle: RoutingCacheBundle):
    from edge_cost_arrays import EdgeCostTables

    a = bundle.tables_arrays
    n = int(a["n_edges"][0])
    return EdgeCostTables(
        n_edges=n,
        length=a["length"],
        risk=a["risk"],
        vf_flags=a["vf_flags"],
        masks_hill_surface=a["masks_hill_surface"],
        speed_stress=a["speed_stress"],
        is_tfl=a["is_tfl"],
        is_green=a["is_green"],
        m_highway=a["m_highway"],
        barrier_base=a["barrier_base"],
        calming_base=a["calming_base"],
        signal_base=a["signal_base"],
        junction_base=a["junction_base"],
        unlit_base=a["unlit_base"],
        bad_surf_base=a["bad_surf_base"],
        hard_static=a["hard_static"],
        hill_base=a["hill_base"],
        hard_cargo=a["hard_cargo"],
        is_park=a["is_park"],
        park_oh_id=a["park_oh_id"],
        park_oh_exprs=list(bundle.park_oh_exprs),
    )


def bundle_to_csr(bundle: RoutingCacheBundle):
    from graph_csr import GraphCSR

    a = bundle.csr_arrays
    n_nodes = int(a["n_nodes"][0])
    idx_arr = a["idx_to_node"]
    idx_to_node = [_xy_to_node(idx_arr[i]) for i in range(n_nodes)]
    node_to_idx = {nid: i for i, nid in enumerate(idx_to_node)}
    return GraphCSR(
        n_nodes=n_nodes,
        n_edges=int(a["n_edges"][0]),
        idx_to_node=idx_to_node,
        node_to_idx=node_to_idx,
        indptr=a["indptr"],
        indices=a["indices"],
        eid=a["eid"],
        lon=a["lon"],
        lat=a["lat"],
        lon_rad=a["lon_rad"],
        lat_rad=a["lat_rad"],
        cos_lat=a["cos_lat"],
        build_s=0.0,
    )


def apply_bundle_to_graph(G, bundle: RoutingCacheBundle) -> frozenset:
    """
    Stamp junction flags + ``_eid``/``_vf`` on edges; install EdgeGeomStore.
    Does **not** materialize per-edge ``_coords`` lists (lazy store).
    """
    from edge_geom_store import assert_cache_edge_alignment, install_geom_store

    t0 = time.perf_counter()
    if getattr(G, "is_multigraph", lambda: False)():
        raise ValueError(
            "routing cache apply refuses MultiDiGraph (need edge keys in sidecar)"
        )

    csr = bundle_to_csr(bundle)
    tables = bundle_to_tables(bundle)
    n_edges = tables.n_edges

    assert_cache_edge_alignment(
        G,
        edge_u=bundle.edge_u,
        edge_v=bundle.edge_v,
        geom_offsets=bundle.geom_offsets,
        geom_flat=bundle.geom_flat,
        n_table_edges=n_edges,
    )

    # Node flags
    suppressed: set = set()
    for i, nid in enumerate(csr.idx_to_node):
        if nid not in G.nodes:
            raise KeyError(f"cache node {nid!r} not in graph")
        nd = G.nodes[nid]
        nd["car_physical_road_count"] = int(bundle.car_physical_road_count[i])
        nd["is_dangerous_junction"] = bool(bundle.is_dangerous_junction[i])
        if bundle.cluster_suppressed[i]:
            suppressed.add(nid)

    # Edge stamps via endpoint map (order-independent) — _eid/_vf only
    eid_map = {}
    for i in range(n_edges):
        u = _xy_to_node(bundle.edge_u[i])
        v = _xy_to_node(bundle.edge_v[i])
        eid_map[(u, v)] = i

    vf = tables.vf_flags
    stamped = 0
    for u, v, d in G.edges(data=True):
        i = eid_map.get((u, v))
        if i is None:
            raise KeyError(f"edge {u!r}->{v!r} missing from routing cache")
        d["_eid"] = int(i)
        d["_vf"] = int(vf[i])
        stamped += 1
    if stamped != n_edges:
        raise ValueError(f"stamped {stamped} edges but cache has {n_edges}")

    install_geom_store(bundle.geom_offsets, bundle.geom_flat)

    log.info(
        "routing_cache: applied stamps (_eid/_vf) to %d nodes / %d edges in %.2fs "
        "(geom via EdgeGeomStore, no per-edge _coords)",
        csr.n_nodes,
        n_edges,
        time.perf_counter() - t0,
    )
    return frozenset(suppressed)


def wkb_geoms_and_keys(bundle: RoutingCacheBundle):
    """Return (list[BaseGeometry], list[(u,v)]) for tfl_live.init_from_geoms."""
    from shapely import from_wkb

    n = bundle.edge_u.shape[0]
    offsets = bundle.wkb_offsets
    blob = bundle.wkb_blob
    # Build contiguous bytes objects then vectorize
    raw = []
    keys = []
    for i in range(n):
        a, b = int(offsets[i]), int(offsets[i + 1])
        raw.append(bytes(blob[a:b]))
        keys.append(
            (_xy_to_node(bundle.edge_u[i]), _xy_to_node(bundle.edge_v[i]))
        )
    geoms = list(from_wkb(raw))
    return geoms, keys


def try_load(
    graph_path: str | Path,
    G,
    cache_dir: Path | None = None,
) -> tuple[RoutingCacheBundle | None, str]:
    """Return (bundle, reason). bundle is None if unavailable/incompatible."""
    if not cache_enabled():
        return None, "ROUTING_CACHE disabled"
    cache_dir = Path(cache_dir) if cache_dir else default_cache_dir(graph_path)
    meta_path = cache_dir / "meta.json"
    if not meta_path.is_file():
        return None, f"no cache at {cache_dir}"
    try:
        meta = _read_json(meta_path)
        ok, reason = meta_compatible(meta, graph_path, G)
        if not ok:
            return None, reason
        if getattr(G, "is_multigraph", lambda: False)():
            return None, "MultiDiGraph unsupported for routing cache"
        bundle = load_routing_cache(cache_dir)
        # Alignment runs again in apply_bundle_to_graph; peek here so try_load
        # fails closed before callers assume a good bundle.
        from edge_geom_store import assert_cache_edge_alignment

        n_tables = int(bundle.tables_arrays["n_edges"][0])
        assert_cache_edge_alignment(
            G,
            edge_u=bundle.edge_u,
            edge_v=bundle.edge_v,
            geom_offsets=bundle.geom_offsets,
            geom_flat=bundle.geom_flat,
            n_table_edges=n_tables,
        )
        return bundle, "ok"
    except Exception as exc:
        log.exception("routing_cache: load failed")
        return None, f"load error: {exc}"


def arrays_close(a: np.ndarray, b: np.ndarray, *, rtol=0.0, atol=0.0) -> bool:
    if a.shape != b.shape or a.dtype != b.dtype:
        # allow int/uint width differences if values equal
        if a.shape != b.shape:
            return False
        return bool(np.array_equal(a, b))
    if np.issubdtype(a.dtype, np.floating):
        return bool(np.allclose(a, b, rtol=rtol, atol=atol, equal_nan=True))
    return bool(np.array_equal(a, b))


def compare_tables(a, b) -> list[str]:
    """Return list of mismatch descriptions (empty = equal)."""
    errs = []
    if a.n_edges != b.n_edges:
        errs.append(f"n_edges {a.n_edges} != {b.n_edges}")
        return errs
    for name in TABLE_ARRAY_NAMES:
        aa, bb = getattr(a, name), getattr(b, name)
        if not arrays_close(aa, bb, atol=1e-9 if np.issubdtype(aa.dtype, np.floating) else 0):
            errs.append(f"tables.{name} mismatch")
    if list(a.park_oh_exprs) != list(b.park_oh_exprs):
        errs.append("park_oh_exprs mismatch")
    return errs


def compare_csr(a, b) -> list[str]:
    errs = []
    if a.n_nodes != b.n_nodes or a.n_edges != b.n_edges:
        errs.append(f"csr size {a.n_nodes}/{a.n_edges} != {b.n_nodes}/{b.n_edges}")
        return errs
    for name in ("indptr", "indices", "eid", "lon", "lat", "lon_rad", "lat_rad", "cos_lat"):
        aa, bb = getattr(a, name), getattr(b, name)
        atol = 1e-12 if name.endswith("rad") or name == "cos_lat" else 1e-9
        if name in ("indptr", "indices", "eid"):
            if not np.array_equal(aa, bb):
                errs.append(f"csr.{name} mismatch")
        elif not np.allclose(aa, bb, atol=atol, rtol=0.0):
            errs.append(f"csr.{name} mismatch")
    if a.idx_to_node != b.idx_to_node:
        # tolerate float tuple identity via allclose on stacked
        aa = np.asarray(a.idx_to_node, dtype=np.float64)
        bb = np.asarray(b.idx_to_node, dtype=np.float64)
        if not np.allclose(aa, bb, atol=0.0, rtol=0.0):
            errs.append("csr.idx_to_node mismatch")
    return errs
