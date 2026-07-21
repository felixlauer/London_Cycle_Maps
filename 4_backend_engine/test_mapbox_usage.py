"""Unit tests for file-backed Mapbox usage hard cuts."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import mapbox_usage


class MapboxUsageTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self._tmpdir.name) / "usage.json"
        mapbox_usage._path_override = self.path
        self.env = mock.patch.dict(os.environ, {
            "MAPBOX_SEARCH_SESSION_LIMIT": "3",
            "MAPBOX_MAP_LOAD_LIMIT": "2",
            "MAPBOX_SEARCH_SESSIONS_USED": "0",
            "MAPBOX_MAP_LOADS_USED": "0",
        }, clear=False)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        mapbox_usage._path_override = None
        self._tmpdir.cleanup()

    def test_search_counts_unique_sessions_and_hard_cuts(self):
        self.assertTrue(mapbox_usage.check_search_session("a").allowed)
        self.assertTrue(mapbox_usage.record_search_session("a").allowed)
        self.assertEqual(mapbox_usage.snapshot()["search_sessions"], 1)

        # Same session does not consume another slot
        self.assertTrue(mapbox_usage.record_search_session("a").allowed)
        self.assertEqual(mapbox_usage.snapshot()["search_sessions"], 1)

        self.assertTrue(mapbox_usage.record_search_session("b").allowed)
        self.assertTrue(mapbox_usage.record_search_session("c").allowed)
        self.assertEqual(mapbox_usage.snapshot()["search_sessions"], 3)

        blocked = mapbox_usage.check_search_session("d")
        self.assertFalse(blocked.allowed)
        # Existing session still ok at limit
        self.assertTrue(mapbox_usage.check_search_session("a").allowed)

    def test_map_load_hard_cut(self):
        self.assertTrue(mapbox_usage.try_consume_map_load().allowed)
        self.assertTrue(mapbox_usage.try_consume_map_load().allowed)
        denied = mapbox_usage.try_consume_map_load()
        self.assertFalse(denied.allowed)
        self.assertEqual(mapbox_usage.snapshot()["map_loads"], 2)

    def test_persists_across_reload(self):
        mapbox_usage.record_search_session("x")
        mapbox_usage.try_consume_map_load()
        # Simulate new process reading same file
        snap = mapbox_usage.snapshot()
        self.assertEqual(snap["search_sessions"], 1)
        self.assertEqual(snap["map_loads"], 1)
        self.assertTrue(self.path.exists())


if __name__ == "__main__":
    unittest.main()
