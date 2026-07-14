#!/usr/bin/env python3
"""Unit tests for lazy EdgeGeomStore + cache alignment (no full London graph)."""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

import networkx as nx
import numpy as np

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

import edge_geom_store as egs


def _tiny_digraph():
    G = nx.DiGraph()
    a = (-0.12, 51.50)
    b = (-0.11, 51.51)
    c = (-0.10, 51.50)
    G.add_node(a, x=a[0], y=a[1], _x=a[0], _y=a[1])
    G.add_node(b, x=b[0], y=b[1], _x=b[0], _y=b[1])
    G.add_node(c, x=c[0], y=c[1], _x=c[0], _y=c[1])
    G.add_edge(
        a,
        b,
        geometry="LINESTRING (-0.12 51.50, -0.11 51.51)",
        length=100.0,
    )
    G.add_edge(
        b,
        c,
        geometry="LINESTRING (-0.11 51.51, -0.10 51.50)",
        length=120.0,
    )
    return G, a, b, c


class TestEdgeGeomStore(unittest.TestCase):
    def tearDown(self):
        egs.clear_geom_store()

    def test_store_lookup_matches_wkt(self):
        G, a, b, c = _tiny_digraph()
        coords0 = egs.parse_edge_coords_no_write(G, a, b, G[a][b])
        coords1 = egs.parse_edge_coords_no_write(G, b, c, G[b][c])
        flat = np.asarray(coords0 + coords1, dtype=np.float32)
        offsets = np.array(
            [0, len(coords0), len(coords0) + len(coords1)], dtype=np.int64
        )
        egs.install_geom_store(offsets, flat)
        G[a][b]["_eid"] = 0
        G[b][c]["_eid"] = 1

        got = egs.coords_for_edge(G[a][b], G, a, b)
        self.assertEqual(len(got), len(coords0))
        self.assertTrue(math.isclose(got[0][0], coords0[0][0], abs_tol=1e-5))
        self.assertTrue(math.isclose(got[-1][1], coords0[-1][1], abs_tol=1e-5))

    def test_wkt_fallback_does_not_mutate_edge_dict(self):
        G, a, b, _c = _tiny_digraph()
        d = G[a][b]
        self.assertNotIn("_coords", d)
        out = egs.coords_for_edge(d, G, a, b)
        self.assertGreaterEqual(len(out), 2)
        self.assertNotIn("_coords", d)
        self.assertNotIn("_eid", d)

    def test_alignment_ok_and_tamper_fails(self):
        G, a, b, c = _tiny_digraph()
        coords0 = egs.parse_edge_coords_no_write(G, a, b, G[a][b])
        coords1 = egs.parse_edge_coords_no_write(G, b, c, G[b][c])
        flat = np.asarray(coords0 + coords1, dtype=np.float32)
        offsets = np.array(
            [0, len(coords0), len(coords0) + len(coords1)], dtype=np.int64
        )
        edge_u = np.array([a, b], dtype=np.float64)
        edge_v = np.array([b, c], dtype=np.float64)

        egs.assert_cache_edge_alignment(
            G,
            edge_u=edge_u,
            edge_v=edge_v,
            geom_offsets=offsets,
            geom_flat=flat,
            n_table_edges=2,
            sample_n=10,
        )

        bad_u = edge_u.copy()
        bad_u[0, 0] += 0.01
        with self.assertRaisesRegex(ValueError, "alignment"):
            egs.assert_cache_edge_alignment(
                G,
                edge_u=bad_u,
                edge_v=edge_v,
                geom_offsets=offsets,
                geom_flat=flat,
                n_table_edges=2,
            )

        bad_flat = flat.copy()
        bad_flat[0, 0] += 1e-3
        with self.assertRaisesRegex(ValueError, "alignment"):
            egs.assert_cache_edge_alignment(
                G,
                edge_u=edge_u,
                edge_v=edge_v,
                geom_offsets=offsets,
                geom_flat=bad_flat,
                n_table_edges=2,
            )

    def test_alignment_tolerance_passes_small_drift(self):
        G, a, b, c = _tiny_digraph()
        coords0 = egs.parse_edge_coords_no_write(G, a, b, G[a][b])
        coords1 = egs.parse_edge_coords_no_write(G, b, c, G[b][c])
        flat = np.asarray(coords0 + coords1, dtype=np.float32)
        offsets = np.array(
            [0, len(coords0), len(coords0) + len(coords1)], dtype=np.int64
        )
        edge_u = np.array([a, b], dtype=np.float64)
        edge_v = np.array([b, c], dtype=np.float64)

        flat2 = flat.copy()
        flat2[0, 0] += 5e-6
        egs.assert_cache_edge_alignment(
            G,
            edge_u=edge_u,
            edge_v=edge_v,
            geom_offsets=offsets,
            geom_flat=flat2,
            n_table_edges=2,
        )

    def test_multigraph_refused(self):
        G = nx.MultiDiGraph()
        n0 = (0.0, 0.0)
        n1 = (1.0, 1.0)
        G.add_node(n0, x=0.0, y=0.0)
        G.add_node(n1, x=1.0, y=1.0)
        G.add_edge(n0, n1, key=0, geometry="LINESTRING (0 0, 1 1)")
        with self.assertRaisesRegex(ValueError, "MultiDiGraph"):
            egs.assert_cache_edge_alignment(
                G,
                edge_u=np.array([n0], dtype=np.float64),
                edge_v=np.array([n1], dtype=np.float64),
                geom_offsets=np.array([0, 2], dtype=np.int64),
                geom_flat=np.array([[0.0, 0.0], [1.0, 1.0]], dtype=np.float32),
                n_table_edges=1,
            )


if __name__ == "__main__":
    unittest.main()
