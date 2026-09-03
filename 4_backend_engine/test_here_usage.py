"""Unit tests for file-backed HERE search call hard cuts."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import here_usage


class HereUsageTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self._tmpdir.name) / "here_usage.json"
        here_usage._path_override = self.path
        self.env = mock.patch.dict(os.environ, {
            "HERE_SEARCH_CALL_LIMIT": "3",
            "HERE_SEARCH_CALLS_USED": "0",
        }, clear=False)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        here_usage._path_override = None
        self._tmpdir.cleanup()

    def test_try_consume_hard_cuts(self):
        self.assertTrue(here_usage.check(1).allowed)
        self.assertTrue(here_usage.try_consume().allowed)
        self.assertTrue(here_usage.try_consume().allowed)
        self.assertTrue(here_usage.try_consume().allowed)
        self.assertEqual(here_usage.snapshot()["search_calls"], 3)
        denied = here_usage.try_consume()
        self.assertFalse(denied.allowed)
        self.assertFalse(here_usage.check().allowed)
        self.assertEqual(here_usage.snapshot()["search_calls"], 3)

    def test_check_does_not_increment(self):
        here_usage.try_consume()
        here_usage.check()
        self.assertEqual(here_usage.snapshot()["search_calls"], 1)

    def test_persists_across_reload(self):
        here_usage.try_consume()
        snap = here_usage.snapshot()
        self.assertEqual(snap["search_calls"], 1)
        self.assertTrue(self.path.exists())


if __name__ == "__main__":
    unittest.main()
