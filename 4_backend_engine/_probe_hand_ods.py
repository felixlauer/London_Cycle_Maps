"""Probe hand OD battery for signal-cluster entry uniqueness (v5.1 cache)."""
from __future__ import annotations

import os
import sys
import types
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("FLASK_USE_RELOADER", "0")
os.environ.setdefault("SKIP_DISRUPTION_FETCH", "1")


def _mock_flask() -> None:
    if "flask" in sys.modules and hasattr(sys.modules["flask"], "g"):
        return
    flask = types.ModuleType("flask")

    class _Flask:
        def __init__(self, *a, **k):
            self.config = {}

        def route(self, *a, **k):
            return lambda fn: fn

        def before_request(self, fn):
            return fn

        def after_request(self, fn):
            return fn

        def errorhandler(self, *a, **k):
            return lambda fn: fn

        def register_blueprint(self, *a, **k):
            return None

    flask.Flask = _Flask
    flask.g = types.SimpleNamespace()
    flask.request = types.SimpleNamespace(headers={}, args={}, get_json=lambda *a, **k: {})
    flask.jsonify = lambda x: x
    flask.Response = type("Response", (), {})
    sys.modules["flask"] = flask
    cors = types.ModuleType("flask_cors")
    cors.CORS = lambda *a, **k: None
    sys.modules["flask_cors"] = cors


_mock_flask()

import park_opening_hours
import tfl_live
import app as app_mod
import pathfinding
from routing_heuristic import make_heuristic
from signal_clusters import edge_has_signal_entry, edge_has_signal_exit
from routing_cache import FORMULA_ID

ODS = [
    ("OD1 Kensington", (51.49524339101414, -0.18044745616896934), (51.49547426052836, -0.1778347522439508)),
    ("OD2 Chelsea", (51.475943178072, -0.14950690405949194), (51.47698990588865, -0.1468878392539747)),
    ("OD3", (51.50523724368268, -0.2139777001297361), (51.50555382288083, -0.2122861425365424)),
    ("OD4", (51.51697265111577, -0.18423096056001168), (51.51738503283823, -0.18271964786771175)),
    ("OD5", (51.51523964387163, -0.15561211629629731), (51.51564199050269, -0.15307441240568925)),
    ("OD6", (51.51996426572465, -0.1437057241479187), (51.519592169336626, -0.1457309409044318)),
    ("OD7", (51.476587536394966, -0.19253135731156193), (51.477878518103964, -0.18974497535763746)),
    ("OD8", (51.454077419840125, -0.19226250252304916), (51.451950198728554, -0.19066062313348167)),
    ("OD9", (51.444929382651, -0.19815284097544755), (51.447129028640326, -0.1987409777653681)),
]


def _edge(G, u, v):
    ed = G.get_edge_data(u, v) or {}
    if "length" not in ed and ed and all(isinstance(k, int) for k in ed.keys()):
        ed = next(iter(ed.values()))
    return ed


def cluster_size_stats(G):
    sizes = Counter()
    for _, nd in G.nodes(data=True):
        cid = int(nd.get("signal_cluster_id") or 0)
        if cid > 0:
            sizes[cid] += 1
    vals = list(sizes.values())
    if not vals:
        return {}
    vals.sort()
    n = len(vals)

    def pct(p):
        return vals[min(n - 1, int(p * (n - 1)))]

    return {
        "clusters": n,
        "nodes": sum(vals),
        "median_nodes": pct(0.5),
        "p90_nodes": pct(0.9),
        "p99_nodes": pct(0.99),
        "max_nodes": vals[-1],
        "ge_50": sum(1 for v in vals if v >= 50),
        "ge_100": sum(1 for v in vals if v >= 100),
        "ge_200": sum(1 for v in vals if v >= 200),
    }


def main() -> int:
    G = app_mod.G
    if G is None:
        print("ERROR: graph not loaded")
        return 1

    print(f"formula_id={FORMULA_ID}")
    print(f"cache applied; nodes={G.number_of_nodes()}")
    stats = cluster_size_stats(G)
    print("cluster size stats:", stats)

    hours_map, fallback = park_opening_hours.build_request_hours_context(
        G.graph.get("park_opening_hours_unique") or [],
        park_opening_hours.london_now(),
    )
    wf = app_mod.make_weight_fastest(hours_map, fallback)

    print("\n=== Hand OD probes (fastest) ===")
    print(
        f"{'OD':<16} {'len':>5} {'ent':>4} {'uniq':>4} {'reent':>5} {'verdict':<18} entry_cids"
    )
    pass_n = 0
    for name, start_ll, end_ll in ODS:
        start = tfl_live.snap_to_edge(start_ll[0], start_ll[1])
        end = tfl_live.snap_to_edge(end_ll[0], end_ll[1])
        if not start or not end:
            print(f"{name}: FAIL snap")
            continue
        h = make_heuristic(end.anchor_node, G, cost_per_m=1.0)
        path, _ = pathfinding.astar_unidirectional(
            G, start.anchor_node, end.anchor_node, h, wf
        )
        entries = []
        length = 0.0
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            ed = _edge(G, u, v)
            length += float(ed.get("length") or 0)
            if edge_has_signal_entry(ed):
                cid = int(ed.get("signal_cluster_id") or 0)
                entries.append(cid)
        cids = entries
        uniq = len(set(cids))
        reent = len(cids) - uniq
        if uniq == 1 and len(cids) == 1:
            verdict = "YES"
            pass_n += 1
        elif uniq == 1 and len(cids) > 1:
            verdict = "REENTRY same id"
        elif uniq == 0:
            verdict = "NO ENTRY"
        else:
            verdict = "MULTI"
        print(
            f"{name:<16} {length:5.0f} {len(cids):4d} {uniq:4d} {reent:5d} {verdict:<18} {cids}"
        )

        # cluster run-length
        seq = []
        for n in path:
            cid = int(G.nodes[n].get("signal_cluster_id") or 0)
            if not seq or seq[-1] != cid:
                seq.append(cid)
        print(f"                 cluster runs: {seq}")

    print(f"\nPass (uniq=1 and entries=1): {pass_n}/9")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
