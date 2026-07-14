#!/usr/bin/env python3
"""
Prebuild static routing cache for the final London graph.

Runs the same junction / floors / edge-table / CSR / geometry derivation as
app.py startup, then writes an efficient sidecar next to the graph:

  1_data/london_elev_final_tfl.routing_cache/

Automatically invoked at the end of run_graph_pipeline.py; also runnable alone:

  cd c:\\London_Cycle_Maps\\3_pipeline
  python prebuild_routing_cache.py
  python prebuild_routing_cache.py --graph ../1_data/london_elev_final_tfl.graphml
  python prebuild_routing_cache.py --parity   # rebuild in-memory and compare (slow)

When changing cache layout or cost formulas, bump FORMULA_ID / CACHE_FORMAT_VERSION
in 4_backend_engine/routing_cache.py and re-run this script.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import types
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
BACKEND_DIR = REPO_ROOT / "4_backend_engine"
DATA_DIR = REPO_ROOT / "1_data"
DEFAULT_GRAPH = DATA_DIR / "london_elev_final_tfl.graphml"


def _mock_flask() -> None:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Prebuild routing cache sidecar")
    parser.add_argument(
        "--graph",
        default=str(DEFAULT_GRAPH),
        help="Canonical graph path (.graphml; .gpickle preferred if present)",
    )
    parser.add_argument(
        "--cache-dir",
        default=None,
        help="Override output directory (default: <graph_stem>.routing_cache)",
    )
    parser.add_argument(
        "--parity",
        action="store_true",
        help="After save, rebuild tables/CSR in-memory and compare to cache (slow)",
    )
    parser.add_argument(
        "--skip-geom-verify",
        action="store_true",
        help="With --parity, skip per-edge _coords spot checks",
    )
    args = parser.parse_args()

    os.environ["ROUTING_CACHE_BUILD"] = "1"
    os.environ["FLASK_USE_RELOADER"] = "0"
    os.environ["SKIP_DISRUPTION_FETCH"] = "1"
    os.environ["GEOM_PREPARSE"] = "off"
    os.environ["ROUTING_CACHE"] = "0"  # force cold compute while building

    sys.path.insert(0, str(BACKEND_DIR))
    sys.path.insert(0, str(SCRIPT_DIR))

    _mock_flask()
    os.chdir(BACKEND_DIR)

    from graph_io import load_graph, fast_path
    import edge_cost_arrays
    import graph_csr
    import routing_cache
    import app as app_mod

    graph_path = Path(args.graph)
    if not graph_path.is_file() and not Path(fast_path(str(graph_path))).is_file():
        print(f"ERROR: graph not found: {graph_path}")
        return 1

    cache_dir = (
        Path(args.cache_dir)
        if args.cache_dir
        else routing_cache.default_cache_dir(graph_path)
    )

    print("=" * 72)
    print("  Prebuild routing cache")
    print(f"  Graph: {graph_path}")
    print(f"  Cache: {cache_dir}")
    print("=" * 72)

    t_all = time.perf_counter()
    timings: dict[str, float] = {}

    t0 = time.perf_counter()
    print("Loading graph...", flush=True)
    G = load_graph(str(graph_path))
    timings["graph_load"] = round(time.perf_counter() - t0, 3)
    print(
        f"  {G.number_of_nodes():,} nodes / {G.number_of_edges():,} edges "
        f"({timings['graph_load']:.1f}s)",
        flush=True,
    )

    app_mod.G = G

    t0 = time.perf_counter()
    n_xy = edge_cost_arrays.stamp_node_xy(G)
    timings["node_xy"] = round(time.perf_counter() - t0, 3)
    print(f"--> Node XY stamps: {n_xy} ({timings['node_xy']:.1f}s)", flush=True)

    t0 = time.perf_counter()
    app_mod._cache_junction_node_flags(G)
    timings["junction_flags"] = round(time.perf_counter() - t0, 3)

    t0 = time.perf_counter()
    app_mod._build_heuristic_penalty_floors(G)
    timings["heuristic_floors"] = round(time.perf_counter() - t0, 3)
    from routing_heuristic import PENALTY_FLOORS

    floors = {k: float(PENALTY_FLOORS[k]) for k in PENALTY_FLOORS}

    t0 = time.perf_counter()
    suppressed = app_mod._build_junction_cluster_suppression()
    app_mod.JUNCTION_CLUSTER_SUPPRESSED = suppressed
    timings["junction_cluster"] = round(time.perf_counter() - t0, 3)
    print(
        f"--> Junction cluster: {len(suppressed)} suppressed "
        f"({timings['junction_cluster']:.1f}s)",
        flush=True,
    )

    # Build tables WITH geometry parse so _coords exist before save
    t0 = time.perf_counter()
    print("--> Edge cost tables + geometry parse (slow, once)...", flush=True)
    tables, build_s = edge_cost_arrays.build_edge_cost_tables(
        G,
        junction_suppressed=suppressed,
        bad_surfaces=app_mod.BAD_SURFACES,
        up_thresh=app_mod.UP_THRESH,
        down_thresh=app_mod.DOWN_THRESH,
        is_lit_fn=app_mod.is_lit,
        speed_stress_fn=app_mod._speed_stress_multiplier,
        is_tfl_fn=app_mod._is_tfl_network,
        has_attraction_fn=app_mod._has_attraction_edge,
        highway_mult_fn=app_mod._highway_type_multiplier,
        barrier_penalty_fn=app_mod._edge_barrier_penalty,
        give_way_fn=app_mod._edge_give_way_penalty,
        stop_sign_fn=app_mod._edge_stop_sign_penalty,
        calming_fn=app_mod._traffic_calming_additive,
        signal_fn=app_mod._node_signal_penalty,
        intersection_fn=app_mod._node_intersection_penalty,
        mini_rb_fn=app_mod._node_mini_roundabout_penalty,
        is_yes_fn=app_mod._is_yes_attr,
        parse_geometry=True,
    )
    timings["edge_cost_tables"] = round(build_s, 3)
    print(f"--> Edge cost tables: {tables.n_edges:,} in {build_s:.1f}s", flush=True)
    edge_cost_arrays.install_tables(tables, G)

    t0 = time.perf_counter()
    csr = graph_csr.build_csr(G)
    graph_csr.set_csr(csr)
    timings["csr"] = round(time.perf_counter() - t0, 3)
    print(
        f"--> CSR: {csr.n_nodes:,} nodes / {csr.n_edges:,} arcs "
        f"({timings['csr']:.1f}s)",
        flush=True,
    )

    print(f"--> Writing cache to {cache_dir} ...", flush=True)
    t0 = time.perf_counter()
    meta = routing_cache.save_routing_cache(
        cache_dir,
        graph_path=graph_path,
        G=G,
        tables=tables,
        csr=csr,
        floors=floors,
        junction_suppressed=suppressed,
        build_timings=timings,
    )
    timings["save"] = round(time.perf_counter() - t0, 3)

    # Reload sanity (bypass ROUTING_CACHE=0 kill-switch used during cold build)
    t0 = time.perf_counter()
    try:
        bundle = routing_cache.load_routing_cache(cache_dir)
        ok, reason = routing_cache.meta_compatible(bundle.meta, graph_path, G)
        if not ok:
            print(f"ERROR: reload meta incompatible: {reason}")
            return 1
        from edge_geom_store import assert_cache_edge_alignment

        assert_cache_edge_alignment(
            G,
            edge_u=bundle.edge_u,
            edge_v=bundle.edge_v,
            geom_offsets=bundle.geom_offsets,
            geom_flat=bundle.geom_flat,
            n_table_edges=tables.n_edges,
            sample_n=512,
        )
    except Exception as exc:
        print(f"ERROR: reload failed: {exc}")
        return 1
    loaded_tables = routing_cache.bundle_to_tables(bundle)
    loaded_csr = routing_cache.bundle_to_csr(bundle)
    errs = routing_cache.compare_tables(tables, loaded_tables)
    errs += routing_cache.compare_csr(csr, loaded_csr)
    timings["reload_verify"] = round(time.perf_counter() - t0, 3)
    if errs:
        print("ERROR: reload parity failed:")
        for e in errs:
            print(f"  - {e}")
        return 1
    print(f"--> Reload verify + alignment OK ({timings['reload_verify']:.1f}s)", flush=True)

    if args.parity:
        print("--> Full parity rebuild (tables+CSR, no geom parse)...", flush=True)
        t0 = time.perf_counter()
        # Clear eid so rebuild assigns fresh
        for _u, _v, d in G.edges(data=True):
            d.pop("_eid", None)
            d.pop("_vf", None)
        tables2, _ = edge_cost_arrays.build_edge_cost_tables(
            G,
            junction_suppressed=suppressed,
            bad_surfaces=app_mod.BAD_SURFACES,
            up_thresh=app_mod.UP_THRESH,
            down_thresh=app_mod.DOWN_THRESH,
            is_lit_fn=app_mod.is_lit,
            speed_stress_fn=app_mod._speed_stress_multiplier,
            is_tfl_fn=app_mod._is_tfl_network,
            has_attraction_fn=app_mod._has_attraction_edge,
            highway_mult_fn=app_mod._highway_type_multiplier,
            barrier_penalty_fn=app_mod._edge_barrier_penalty,
            give_way_fn=app_mod._edge_give_way_penalty,
            stop_sign_fn=app_mod._edge_stop_sign_penalty,
            calming_fn=app_mod._traffic_calming_additive,
            signal_fn=app_mod._node_signal_penalty,
            intersection_fn=app_mod._node_intersection_penalty,
            mini_rb_fn=app_mod._node_mini_roundabout_penalty,
            is_yes_fn=app_mod._is_yes_attr,
            parse_geometry=False,
        )
        csr2 = graph_csr.build_csr(G)
        errs = routing_cache.compare_tables(loaded_tables, tables2)
        errs += routing_cache.compare_csr(loaded_csr, csr2)
        if not args.skip_geom_verify:
            # Spot-check first/mid/last edge coords vs fresh parse
            from edge_cost_arrays import _parse_edge_coords
            import numpy as np

            sample_eids = {0, n_edges // 2, n_edges - 1} if (n_edges := tables.n_edges) else set()
            for u, v, d in G.edges(data=True):
                eid = int(d.get("_eid", -1))
                if eid not in sample_eids:
                    continue
                fresh = np.asarray(_parse_edge_coords(G, u, v, d), dtype=np.float32)
                a, b = int(bundle.geom_offsets[eid]), int(bundle.geom_offsets[eid + 1])
                cached = bundle.geom_flat[a:b]
                if fresh.shape != cached.shape or not np.allclose(
                    fresh, cached, atol=1e-5, rtol=0.0
                ):
                    errs.append(f"geom coords mismatch eid={eid}")
                sample_eids.discard(eid)
                if not sample_eids:
                    break
        timings["parity"] = round(time.perf_counter() - t0, 3)
        if errs:
            print("ERROR: parity failed:")
            for e in errs:
                print(f"  - {e}")
            return 1
        print(f"--> Parity OK ({timings['parity']:.1f}s)", flush=True)

    total = time.perf_counter() - t_all
    print("")
    print("=" * 72)
    print(f"  ROUTING CACHE COMPLETE ({total / 60:.1f} min)")
    print(f"  Output: {cache_dir}")
    print(f"  formula_id={meta.get('formula_id')} sha={meta.get('content_sha256_16')}")
    print(f"  Timings (s): {timings}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
