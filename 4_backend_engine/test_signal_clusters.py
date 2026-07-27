"""Unit tests for Phase 1 signal clusters + entry/exit marking."""
from __future__ import annotations

import os
import unittest

import networkx as nx

os.environ.setdefault("SIGNAL_CLUSTERS", "1")

from signal_clusters import (  # noqa: E402
    SIGNAL_CLUSTER_RADIUS_M,
    SIGNAL_POST_MERGE_CENTROID_M,
    _refresh_signal_clusters_enabled,
    apply_signal_clusters,
    build_signal_clusters,
    close_cluster_interior,
    edge_has_signal_entry,
    edge_has_signal_exit,
    expand_cluster_membership,
    mark_signal_entry_exit_edges,
    merge_adjacent_clusters,
    spatial_post_merge,
)


def _node(lon, lat):
    return (float(lon), float(lat))


class SignalClusterTests(unittest.TestCase):
    def setUp(self):
        os.environ["SIGNAL_CLUSTERS"] = "1"
        _refresh_signal_clusters_enabled()

    def test_multi_node_junction_one_cluster(self):
        G = nx.DiGraph()
        a = _node(-0.10000, 51.50000)
        b = _node(-0.10008, 51.50000)
        c = _node(-0.10000, 51.50005)
        outside = _node(-0.10040, 51.50000)
        far = _node(-0.10120, 51.50000)

        for n in (a, b, c, outside, far):
            G.add_node(n, x=n[0], y=n[1])
        G.nodes[a]["traffic_signals"] = "yes"
        G.nodes[b]["traffic_signals"] = "yes"
        G.nodes[c]["traffic_signals"] = "yes"
        G.nodes[far]["traffic_signals"] = "yes"

        for u, v in ((a, b), (b, a), (a, c), (c, a), (b, c), (c, b)):
            G.add_edge(u, v, length=8.0, type="footway")
        G.add_edge(outside, a, length=30.0, type="footway")
        G.add_edge(a, outside, length=30.0, type="residential")
        approach_far = _node(-0.10150, 51.50000)
        G.add_node(approach_far, x=approach_far[0], y=approach_far[1])
        G.add_edge(approach_far, far, length=20.0, type="primary")
        G.add_edge(far, approach_far, length=20.0, type="primary")

        seeds = build_signal_clusters(G)
        self.assertEqual(seeds[a], seeds[b])
        self.assertEqual(seeds[a], seeds[c])
        self.assertNotEqual(seeds[a], seeds[far])
        self.assertEqual(len(set(seeds.values())), 2)

        meta = apply_signal_clusters(G)
        self.assertGreaterEqual(meta["entry_edges"], 2)
        self.assertTrue(edge_has_signal_entry(G[outside][a]))
        self.assertFalse(edge_has_signal_entry(G[a][b]))
        self.assertTrue(edge_has_signal_exit(G[a][outside]))

    def test_footway_bypass_pays_via_expanded_interior(self):
        """
        Classic free-ride: tagged signal on carriageway; parallel footway never
        touches the signal node but crosses the junction via untagged nodes.
        After expansion those interior nodes are in the cluster → footway entry pays.
        """
        G = nx.DiGraph()
        sig = _node(0.0, 51.5)
        road_in = _node(-0.00020, 51.5)
        road_out = _node(0.00020, 51.5)
        # Parallel footway: ends outside R=30 m; mid beside signal (expanded)
        foot_in = _node(-0.00050, 51.50005)  # ~35 m west — outside R
        foot_mid = _node(0.0, 51.50005)
        foot_out = _node(0.00050, 51.50005)

        for n in (sig, road_in, road_out, foot_in, foot_mid, foot_out):
            G.add_node(n, x=n[0], y=n[1])
        G.nodes[sig]["traffic_signals"] = "yes"

        G.add_edge(road_in, sig, length=15.0, type="primary")
        G.add_edge(sig, road_out, length=15.0, type="primary")
        G.add_edge(sig, foot_mid, length=6.0, type="footway")
        G.add_edge(foot_mid, sig, length=6.0, type="footway")
        G.add_edge(foot_in, foot_mid, length=36.0, type="footway")
        G.add_edge(foot_mid, foot_out, length=36.0, type="footway")

        seeds = build_signal_clusters(G)
        self.assertEqual(seeds[sig], 1)
        expanded = expand_cluster_membership(G, seeds)
        self.assertIn(foot_mid, expanded, "untagged footway node beside signal must expand in")
        self.assertNotIn(foot_in, expanded)

        meta = mark_signal_entry_exit_edges(G, expanded, seeds)
        self.assertTrue(edge_has_signal_entry(G[foot_in][foot_mid]), "ped entry into interior")
        self.assertTrue(edge_has_signal_entry(G[road_in][sig]))
        self.assertGreaterEqual(meta["entry_ped_edges"], 1)
        self.assertIn("footway", meta["entry_by_highway"])

    def test_road_bridge_one_hop_reaches_footway(self):
        """Signal on stop-line; footway attaches one short primary hop away."""
        G = nx.DiGraph()
        sig = _node(0.0, 51.5)
        kerb = _node(0.00010, 51.5)  # ~7 m east
        foot_mid = _node(0.00010, 51.50006)  # ~7 m north of kerb
        foot_in = _node(-0.00045, 51.50006)  # outside R
        road_in = _node(-0.00025, 51.5)

        for n in (sig, kerb, foot_mid, foot_in, road_in):
            G.add_node(n, x=n[0], y=n[1])
        G.nodes[sig]["traffic_signals"] = "yes"

        G.add_edge(road_in, sig, length=18.0, type="primary")
        G.add_edge(sig, kerb, length=7.0, type="primary")
        G.add_edge(kerb, sig, length=7.0, type="primary")
        G.add_edge(kerb, foot_mid, length=7.0, type="footway")
        G.add_edge(foot_mid, kerb, length=7.0, type="footway")
        G.add_edge(foot_in, foot_mid, length=32.0, type="footway")

        seeds = build_signal_clusters(G)
        expanded = expand_cluster_membership(G, seeds)
        self.assertIn(kerb, expanded)
        self.assertIn(foot_mid, expanded)
        self.assertNotIn(road_in, expanded, "approach must not be swallowed")

        mark_signal_entry_exit_edges(G, expanded, seeds)
        self.assertTrue(edge_has_signal_entry(G[foot_in][foot_mid]))
        self.assertTrue(edge_has_signal_entry(G[road_in][sig]))

    def test_road_bridge_two_hops_then_closure_claims_corner(self):
        """stop-line → corner → kerb: expand leaves corner out; closure claims it."""
        G = nx.DiGraph()
        sig = _node(0.0, 51.5)
        corner = _node(0.00008, 51.5)  # ~5.5 m
        kerb = _node(0.00016, 51.5)  # ~11 m from sig
        foot_mid = _node(0.00016, 51.50005)
        foot_in = _node(-0.00045, 51.50005)
        road_in = _node(-0.00025, 51.5)

        for n in (sig, corner, kerb, foot_mid, foot_in, road_in):
            G.add_node(n, x=n[0], y=n[1])
        G.nodes[sig]["traffic_signals"] = "yes"

        G.add_edge(road_in, sig, length=18.0, type="primary")
        for u, v in ((sig, corner), (corner, sig), (corner, kerb), (kerb, corner)):
            G.add_edge(u, v, length=6.0, type="primary")
        G.add_edge(kerb, foot_mid, length=6.0, type="footway")
        G.add_edge(foot_mid, kerb, length=6.0, type="footway")
        G.add_edge(foot_in, foot_mid, length=32.0, type="footway")

        seeds = build_signal_clusters(G)
        expanded = expand_cluster_membership(G, seeds)
        self.assertNotIn(
            corner,
            expanded,
            "pure road bridge node without mesh must not join at expand",
        )
        self.assertIn(kerb, expanded)

        closed, n_closed, _holes = close_cluster_interior(G, expanded, seeds)
        self.assertGreaterEqual(n_closed, 1)
        self.assertIn(corner, closed, "closure fills carriageway hole")
        self.assertNotIn(road_in, closed, "approach with one cluster neighbour stays out")

        mark_signal_entry_exit_edges(G, closed, seeds)
        self.assertTrue(edge_has_signal_entry(G[foot_in][foot_mid]))
        self.assertTrue(edge_has_signal_entry(G[road_in][sig]))
        self.assertFalse(edge_has_signal_entry(G[sig][corner]))
        self.assertFalse(edge_has_signal_entry(G[corner][kerb]))

    def test_interior_closure_stops_reentry_charge(self):
        """Path through hole used to pay twice; after closure only one entry."""
        G = nx.DiGraph()
        road_in = _node(-0.00030, 51.5)
        sig = _node(0.0, 51.5)
        hole = _node(0.00010, 51.5)  # ~7 m
        kerb = _node(0.00020, 51.5)  # ~14 m
        foot = _node(0.00020, 51.50006)
        road_out = _node(0.00045, 51.5)

        for n in (road_in, sig, hole, kerb, foot, road_out):
            G.add_node(n, x=n[0], y=n[1])
        G.nodes[sig]["traffic_signals"] = "yes"

        for u, v, L in (
            (road_in, sig, 22.0),
            (sig, hole, 7.0),
            (hole, kerb, 7.0),
            (kerb, road_out, 18.0),
        ):
            G.add_edge(u, v, length=L, type="primary")
            G.add_edge(v, u, length=L, type="primary")
        G.add_edge(kerb, foot, length=6.0, type="footway")
        G.add_edge(foot, kerb, length=6.0, type="footway")

        meta = apply_signal_clusters(G)
        self.assertGreaterEqual(meta["closed_nodes"], 1)
        self.assertIn("signal_cluster_id", G.nodes[hole])
        self.assertEqual(G.nodes[hole]["signal_cluster_id"], G.nodes[sig]["signal_cluster_id"])
        self.assertTrue(edge_has_signal_entry(G[road_in][sig]))
        self.assertFalse(edge_has_signal_entry(G[sig][hole]))
        self.assertFalse(edge_has_signal_entry(G[hole][kerb]))
        # Leaving the closed interior toward road_out is exit, not a second entry back
        self.assertTrue(edge_has_signal_exit(G[kerb][road_out]))
        self.assertFalse(edge_has_signal_entry(G[kerb][road_out]))

    def test_merge_nearby_corner_clusters_beyond_R(self):
        """Two seeds ~32 m apart (outside R=30) linked by short road → merge pass."""
        self.assertEqual(SIGNAL_CLUSTER_RADIUS_M, 30.0)
        G = nx.DiGraph()
        a = _node(0.0, 51.5)
        mid = _node(0.00022, 51.5)  # ~15 m
        b = _node(0.00045, 51.5)  # ~31.5 m from a
        for n in (a, mid, b):
            G.add_node(n, x=n[0], y=n[1], traffic_signals="yes")
        for u, v in ((a, mid), (mid, a), (mid, b), (b, mid)):
            G.add_edge(u, v, length=16.0, type="primary")

        seeds = build_signal_clusters(G)
        # Crow-flies ~31.5 m > R=30 → may be separate before merge
        before = len(set(seeds.values()))
        merged, n_merged = merge_adjacent_clusters(G, seeds)
        self.assertEqual(merged[a], merged[b])
        self.assertEqual(len(set(merged.values())), 1)
        if before > 1:
            self.assertGreaterEqual(n_merged, 1)

    def test_far_corridor_lights_do_not_merge(self):
        """Seeds ~80 m apart stay separate after merge."""
        G = nx.DiGraph()
        a = _node(0.0, 51.5)
        b = _node(0.00115, 51.5)  # ~80 m
        # Chain of short edges so merge BFS could walk if we allowed it
        nodes = [a]
        prev = a
        for i in range(1, 5):
            n = _node(0.00023 * i, 51.5)
            G.add_node(n, x=n[0], y=n[1])
            G.add_edge(prev, n, length=16.0, type="primary")
            G.add_edge(n, prev, length=16.0, type="primary")
            nodes.append(n)
            prev = n
        G.add_node(b, x=b[0], y=b[1], traffic_signals="yes")
        G.nodes[a]["traffic_signals"] = "yes"
        G.add_edge(prev, b, length=16.0, type="primary")
        G.add_edge(b, prev, length=16.0, type="primary")

        seeds = build_signal_clusters(G)
        merged, _ = merge_adjacent_clusters(G, seeds)
        self.assertNotEqual(merged[a], merged[b])

        # Spatial post-merge must also leave them separate (80 m > 41)
        cluster = dict(merged)
        post, post_seeds, n_post = spatial_post_merge(G, cluster, merged)
        self.assertEqual(n_post, 0)
        self.assertNotEqual(post[a], post[b])

    def test_spatial_post_merge_centroid_edge(self):
        """Two expanded boxes ~40 m apart with member edge → one cluster; A→B becomes internal."""
        self.assertEqual(SIGNAL_POST_MERGE_CENTROID_M, 41.0)
        G = nx.DiGraph()
        seed_a = _node(0.0, 51.5)
        kerb_a = _node(0.00012, 51.5)  # ~8 m
        kerb_b = _node(0.00048, 51.5)  # ~34 m from seed_a
        seed_b = _node(0.00058, 51.5)  # ~41 m from seed_a
        road_in = _node(-0.00030, 51.5)
        road_out = _node(0.00085, 51.5)

        for n in (seed_a, kerb_a, kerb_b, seed_b, road_in, road_out):
            G.add_node(n, x=n[0], y=n[1])
        G.nodes[seed_a]["traffic_signals"] = "yes"
        G.nodes[seed_b]["traffic_signals"] = "yes"

        for u, v, L in (
            (road_in, seed_a, 22.0),
            (seed_a, kerb_a, 8.0),
            (kerb_a, kerb_b, 26.0),
            (kerb_b, seed_b, 8.0),
            (seed_b, road_out, 20.0),
        ):
            G.add_edge(u, v, length=L, type="primary")
            G.add_edge(v, u, length=L, type="primary")
        # Mesh so expand claims kerbs
        foot_a = _node(0.00012, 51.50005)
        foot_b = _node(0.00048, 51.50005)
        for n in (foot_a, foot_b):
            G.add_node(n, x=n[0], y=n[1])
        G.add_edge(kerb_a, foot_a, length=6.0, type="footway")
        G.add_edge(foot_a, kerb_a, length=6.0, type="footway")
        G.add_edge(kerb_b, foot_b, length=6.0, type="footway")
        G.add_edge(foot_b, kerb_b, length=6.0, type="footway")

        meta = apply_signal_clusters(G)
        self.assertGreaterEqual(meta.get("post_merged", 0), 1)
        self.assertEqual(G.nodes[seed_a]["signal_cluster_id"], G.nodes[seed_b]["signal_cluster_id"])
        # Cross link between former boxes must not charge entry
        self.assertFalse(edge_has_signal_entry(G[kerb_a][kerb_b]))
        self.assertFalse(edge_has_signal_exit(G[kerb_a][kerb_b]))
        self.assertTrue(edge_has_signal_entry(G[road_in][seed_a]))
        self.assertTrue(edge_has_signal_exit(G[seed_b][road_out]))

    def test_spatial_post_merge_no_seed_cap_or_path_glue(self):
        """Edge-linked seeds ~52 m apart stay separate (no seed-cap; centroid > 41)."""
        G = nx.DiGraph()
        seed_a = _node(0.0, 51.5)
        seed_b = _node(0.00075, 51.5)  # ~52 m
        for n in (seed_a, seed_b):
            G.add_node(n, x=n[0], y=n[1], traffic_signals="yes")
        G.add_edge(seed_a, seed_b, length=52.0, type="primary")
        G.add_edge(seed_b, seed_a, length=52.0, type="primary")

        seeds = {seed_a: 1, seed_b: 2}
        cluster = {seed_a: 1, seed_b: 2}
        out, out_seeds, n = spatial_post_merge(G, cluster, seeds)
        self.assertEqual(n, 0)
        self.assertNotEqual(out[seed_a], out[seed_b])

    def test_kill_switch_clears_marks(self):
        G = nx.DiGraph()
        a = _node(0.0, 51.5)
        b = _node(0.0002, 51.5)
        G.add_node(a, x=a[0], y=a[1], traffic_signals="yes")
        G.add_node(b, x=b[0], y=b[1])
        G.add_edge(b, a, length=20.0, type="residential")
        apply_signal_clusters(G)
        self.assertTrue(edge_has_signal_entry(G[b][a]))

        os.environ["SIGNAL_CLUSTERS"] = "0"
        try:
            _refresh_signal_clusters_enabled()
            meta = apply_signal_clusters(G)
            self.assertEqual(meta["enabled"], 0)
            self.assertFalse(edge_has_signal_entry(G[b][a]))
        finally:
            os.environ["SIGNAL_CLUSTERS"] = "1"
            _refresh_signal_clusters_enabled()


if __name__ == "__main__":
    unittest.main()
