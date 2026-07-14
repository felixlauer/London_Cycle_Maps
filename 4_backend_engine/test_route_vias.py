"""Unit tests for route_vias (no Flask / graph)."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))

import route_vias


class ParseViasTests(unittest.TestCase):
    def test_empty(self):
        vias, err = route_vias.parse_vias_arg(None)
        self.assertEqual(vias, [])
        self.assertIsNone(err)
        vias, err = route_vias.parse_vias_arg("  ")
        self.assertEqual(vias, [])
        self.assertIsNone(err)

    def test_one_and_three(self):
        vias, err = route_vias.parse_vias_arg("51.5,-0.1")
        self.assertIsNone(err)
        self.assertEqual(vias, [(51.5, -0.1)])
        vias, err = route_vias.parse_vias_arg("51.5,-0.1;51.51,-0.12;51.52,-0.13")
        self.assertIsNone(err)
        self.assertEqual(len(vias), 3)

    def test_cap_at_max(self):
        raw = ";".join(f"51.{i},-0.{i}" for i in range(4))
        vias, err = route_vias.parse_vias_arg(raw)
        self.assertIsNone(vias)
        self.assertIn(str(route_vias.MAX_VIAS), err)

    def test_bad_pair(self):
        vias, err = route_vias.parse_vias_arg("51.5")
        self.assertIsNone(vias)
        self.assertIsNotNone(err)
        vias, err = route_vias.parse_vias_arg("abc,def")
        self.assertIsNone(vias)
        self.assertIsNotNone(err)


class AggregateStatsTests(unittest.TestCase):
    def test_sum_and_pct(self):
        a = {
            "length_m": 1000,
            "duration_min": 5,
            "accidents": 1,
            "illumination_pct": 50,
            "rough_pct": 0,
            "elevation_gain": 10,
            "steep_count": 1,
            "tfl_cycleway_pct": 20,
            "tfl_quietway_pct": 10,
            "speed_stress_km": 0.2,
            "green_km": 0.1,
            "green_pct": 10,
            "vehicular_free_pct": 0,
            "barrier_count": 0,
            "barrier_penalty_count": 0,
            "give_way_count": 0,
            "stop_sign_count": 0,
            "calming_count": 0,
            "signal_count": 0,
            "junction_count": 0,
            "disruption_count": 0,
        }
        b = {
            **a,
            "length_m": 1000,
            "duration_min": 7,
            "illumination_pct": 100,
            "tfl_cycleway_pct": 0,
            "tfl_quietway_pct": 0,
        }
        out = route_vias.aggregate_path_stats([a, b])
        self.assertEqual(out["length_m"], 2000)
        self.assertEqual(out["duration_min"], 12.0)
        self.assertEqual(out["illumination_pct"], 75.0)
        self.assertEqual(out["tfl_network_pct"], 15.0)

    def test_concatenate_paths(self):
        p = route_vias.concatenate_paths([[1, 2, 3], [3, 4], [4, 5]])
        self.assertEqual(p, [1, 2, 3, 4, 5])


if __name__ == "__main__":
    unittest.main()
