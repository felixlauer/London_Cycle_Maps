"""Unit tests for local file-backed app_metrics counters."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app_metrics


class AppMetricsLocalTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self._tmpdir.name) / "app_metrics.json"
        app_metrics._path_override = self.path
        # Force local backend (no Supabase).
        self.env = mock.patch.dict(
            os.environ,
            {"SUPABASE_URL": "", "SUPABASE_SERVICE_ROLE_KEY": ""},
            clear=False,
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        app_metrics._path_override = None
        self._tmpdir.cleanup()

    def test_session_and_route_accumulate(self):
        # Tests call the sync helpers so they don't race daemon threads.
        app_metrics._record_session_sync()
        app_metrics._record_session_sync()
        app_metrics._record_route_sync(optimized_distance_m=1500.0)
        app_metrics._record_route_sync(optimized_distance_m=500.5)

        snap = app_metrics.snapshot()
        self.assertEqual(snap["sessions"], 2)
        self.assertEqual(snap["routes_computed"], 2)
        self.assertEqual(snap["unique_route_clients"], 0)
        self.assertAlmostEqual(snap["optimized_distance_m"], 2000.5)
        self.assertEqual(snap["backend"], "local")
        self.assertNotIn("client_hashes", snap)
        self.assertNotIn("_client_hashes", snap)

    def test_negative_distance_clamped(self):
        app_metrics._record_route_sync(optimized_distance_m=-10)
        snap = app_metrics.snapshot()
        self.assertEqual(snap["routes_computed"], 1)
        self.assertEqual(snap["optimized_distance_m"], 0.0)
        self.assertEqual(snap["unique_route_clients"], 0)

    def test_unique_clients_deduped_by_ip(self):
        app_metrics._record_route_sync(
            optimized_distance_m=10, client_ip="203.0.113.1"
        )
        app_metrics._record_route_sync(
            optimized_distance_m=20, client_ip="203.0.113.1"
        )
        app_metrics._record_route_sync(
            optimized_distance_m=30, client_ip="203.0.113.2"
        )
        snap = app_metrics.snapshot()
        self.assertEqual(snap["routes_computed"], 3)
        self.assertEqual(snap["unique_route_clients"], 2)
        self.assertNotIn("client_hashes", snap)
        self.assertNotIn("client_ip", snap)
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(len(raw.get("client_hashes") or []), 2)
        for item in raw["client_hashes"]:
            self.assertEqual(len(item), 32)

    def test_unknown_ip_does_not_count_as_a_client(self):
        app_metrics._record_route_sync(optimized_distance_m=1, client_ip="unknown")
        app_metrics._record_route_sync(optimized_distance_m=1, client_ip="  ")
        snap = app_metrics.snapshot()
        self.assertEqual(snap["routes_computed"], 2)
        self.assertEqual(snap["unique_route_clients"], 0)

    def test_ipv6_hash_is_case_insensitive(self):
        app_metrics._record_route_sync(
            optimized_distance_m=1, client_ip="2001:DB8::1"
        )
        app_metrics._record_route_sync(
            optimized_distance_m=1, client_ip="2001:db8::1"
        )
        snap = app_metrics.snapshot()
        self.assertEqual(snap["unique_route_clients"], 1)

    def test_client_hash_hex_never_returns_the_ip(self):
        digest = app_metrics.client_hash_hex("203.0.113.9")
        self.assertIsNotNone(digest)
        self.assertNotIn("203.0.113.9", digest)
        self.assertEqual(len(digest), 32)


if __name__ == "__main__":
    unittest.main()
