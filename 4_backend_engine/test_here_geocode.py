"""Unit tests for HERE suggestion mapping and lookup cache."""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))

import here_geocode


class HereGeocodeTests(unittest.TestCase):
    def setUp(self):
        here_geocode.reset_cache_for_tests()

    def test_skips_category_and_chain_queries(self):
        self.assertIsNone(here_geocode.map_suggestion({
            "resultType": "categoryQuery",
            "id": "here:query:1",
            "title": "restaurant",
        }))
        self.assertIsNone(here_geocode.map_suggestion({
            "resultType": "chainQuery",
            "id": "here:query:2",
            "title": "Pret",
        }))

    def test_maps_place_with_position_and_caches(self):
        item = {
            "id": "here:pds:place:abc",
            "resultType": "place",
            "title": "Dishoom",
            "address": {
                "label": "Dishoom, 5 Stable St, London N1C 4AB, England",
                "city": "London",
                "postalCode": "N1C 4AB",
            },
            "position": {"lat": 51.532, "lng": -0.125},
        }
        row = here_geocode.map_suggestion(item)
        self.assertEqual(row["mapbox_id"], "here:pds:place:abc")
        self.assertEqual(row["name"], "Dishoom")
        self.assertIn("N1C 4AB", row["place_formatted"])
        cached = here_geocode.cache_get("here:pds:place:abc")
        self.assertIsNotNone(cached)
        self.assertAlmostEqual(cached["lat"], 51.532)
        self.assertAlmostEqual(cached["lon"], -0.125)

    def test_lookup_uses_cache_without_http(self):
        here_geocode._cache_put("here:pds:place:cached", {
            "lat": 51.5,
            "lon": -0.1,
            "label": "Cached",
        })
        with mock.patch.object(here_geocode, "api_key", return_value="test-key"):
            with mock.patch.object(here_geocode, "_http_get") as http:
                out = here_geocode.lookup("here:pds:place:cached")
        http.assert_not_called()
        self.assertEqual(out["label"], "Cached")

    def test_lookup_http_when_uncached(self):
        payload = {
            "id": "here:pds:place:fresh",
            "title": "Imperial College",
            "address": {"label": "Imperial College, Exhibition Rd, London SW7 2AZ"},
            "position": {"lat": 51.4988, "lng": -0.1749},
        }
        with mock.patch.object(here_geocode, "api_key", return_value="test-key"):
            with mock.patch.object(here_geocode, "_http_get", return_value=payload) as http:
                out = here_geocode.lookup("here:pds:place:fresh")
        http.assert_called_once()
        self.assertAlmostEqual(out["lat"], 51.4988)
        self.assertEqual(out["label"], "Imperial College, Exhibition Rd, London SW7 2AZ")


if __name__ == "__main__":
    unittest.main()
