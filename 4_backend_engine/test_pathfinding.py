"""Unit tests for pathfinding.astar_unidirectional and astar_bidirectional."""
from __future__ import annotations

import unittest

import networkx as nx

from pathfinding import astar_bidirectional, astar_unidirectional


def _haversine_stub(u, v, G, goal):
    """Crude admissible heuristic from node id numeric distance."""
    gu = G.nodes[u]
    gv = G.nodes[goal]
    dx = float(gu["x"]) - float(gv["x"])
    dy = float(gu["y"]) - float(gv["y"])
    return (dx * dx + dy * dy) ** 0.5


def _make_heuristic(G, goal):
    def h(u, _v):
        return _haversine_stub(u, None, G, goal)

    return h


def _length_weight(_u, _v, d):
    return float(d.get("length", 1.0))


class TestPathfinding(unittest.TestCase):
    def _grid_with_oneway(self) -> nx.DiGraph:
        """3-node line A->B->C plus shortcut D->C (one-way only forward)."""
        G = nx.DiGraph()
        for n, x, y in [("A", 0, 0), ("B", 1, 0), ("C", 2, 0), ("D", 0, 1)]:
            G.add_node(n, x=x, y=y)
        G.add_edge("A", "B", length=1.0)
        G.add_edge("B", "C", length=1.0)
        G.add_edge("A", "D", length=1.0)
        G.add_edge("D", "C", length=1.5)  # one-way D->C only
        return G

    def _path_cost(self, G, path, weight_fn):
        total = 0.0
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            total += weight_fn(u, v, G[u][v])
        return total

    def test_uni_bi_same_path_simple(self):
        G = self._grid_with_oneway()
        h_fwd = _make_heuristic(G, "C")
        h_bwd = _make_heuristic(G, "A")

        path_uni, stats_uni = astar_unidirectional(
            G, "A", "C", h_fwd, _length_weight
        )
        path_bi, stats_bi = astar_bidirectional(
            G, "A", "C", h_fwd, h_bwd, _length_weight
        )

        self.assertEqual(path_uni, path_bi)
        self.assertAlmostEqual(
            self._path_cost(G, path_uni, _length_weight),
            self._path_cost(G, path_bi, _length_weight),
        )
        self.assertGreater(stats_uni["expansions"], 0)
        self.assertGreater(stats_bi["expansions"], 0)

    def test_oneway_forces_asymmetric_expansion(self):
        G = self._grid_with_oneway()
        h_fwd = _make_heuristic(G, "C")
        h_bwd = _make_heuristic(G, "A")

        _, stats_uni = astar_unidirectional(G, "A", "C", h_fwd, _length_weight)
        _, stats_bi = astar_bidirectional(
            G, "A", "C", h_fwd, h_bwd, _length_weight
        )

        # Bidirectional should not expand more than unidirectional on this tiny graph.
        self.assertLessEqual(stats_bi["expansions"], stats_uni["expansions"])

    def test_source_equals_target(self):
        G = self._grid_with_oneway()
        h = _make_heuristic(G, "A")
        path, stats = astar_unidirectional(G, "A", "A", h, _length_weight)
        self.assertEqual(path, ["A"])
        self.assertEqual(stats["expansions"], 0)

        path_bi, stats_bi = astar_bidirectional(
            G, "A", "A", h, h, _length_weight
        )
        self.assertEqual(path_bi, ["A"])
        self.assertEqual(stats_bi["expansions"], 0)

    def test_no_path_raises(self):
        G = nx.DiGraph()
        G.add_node("X", x=0, y=0)
        G.add_node("Y", x=1, y=1)
        h = _make_heuristic(G, "Y")
        with self.assertRaises(nx.NetworkXNoPath):
            astar_unidirectional(G, "X", "Y", h, _length_weight)


if __name__ == "__main__":
    unittest.main()
