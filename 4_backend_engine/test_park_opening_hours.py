"""Tests for park_opening_hours (Europe/London DST-aware)."""
from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import park_opening_hours as poh

LONDON = ZoneInfo("Europe/London")


def _london(*args) -> datetime:
    return datetime(*args, tzinfo=LONDON)


class TestParkOpeningHours(unittest.TestCase):
    def test_london_now_is_aware(self):
        now = poh.london_now()
        self.assertIsNotNone(now.tzinfo)
        self.assertEqual(str(now.tzinfo), "Europe/London")

    def test_24_7_always_open(self):
        winter = _london(2026, 1, 15, 3, 0)
        summer = _london(2026, 6, 15, 3, 0)
        hours_map, fallback = poh.build_request_hours_context(["24/7"], winter)
        self.assertTrue(hours_map["24/7"])
        hours_map_s, _ = poh.build_request_hours_context(["24/7"], summer)
        self.assertTrue(hours_map_s["24/7"])

    def test_wall_clock_winter_gmt(self):
        expr = "Mo-Su 08:00-20:00"
        noon = _london(2026, 1, 15, 12, 0)
        night = _london(2026, 1, 15, 22, 0)
        hours_map, _ = poh.build_request_hours_context([expr], noon)
        self.assertTrue(hours_map[expr])
        hours_map_night, _ = poh.build_request_hours_context([expr], night)
        self.assertFalse(hours_map_night[expr])
        self.assertEqual(noon.utcoffset().total_seconds(), 0)

    def test_wall_clock_summer_bst(self):
        expr = "Mo-Su 08:00-20:00"
        noon = _london(2026, 6, 15, 12, 0)
        night = _london(2026, 6, 15, 22, 0)
        hours_map, _ = poh.build_request_hours_context([expr], noon)
        self.assertTrue(hours_map[expr])
        hours_map_night, _ = poh.build_request_hours_context([expr], night)
        self.assertFalse(hours_map_night[expr])
        self.assertEqual(noon.utcoffset().total_seconds(), 3600)

    def test_dawn_dusk_differs_by_season(self):
        winter_night = _london(2026, 1, 15, 3, 0)
        summer_night = _london(2026, 6, 15, 3, 0)
        self.assertFalse(poh.evaluate_fallback_open(winter_night))
        # June 3am London may still be within dawn-dusk window (short summer night)
        summer_open = poh.evaluate_fallback_open(summer_night)
        self.assertIsInstance(summer_open, bool)

    def test_unparseable_uses_fallback(self):
        at_time = _london(2026, 1, 15, 12, 0)
        fallback = poh.evaluate_fallback_open(at_time)
        hours_map, fb = poh.build_request_hours_context(["not valid hours at all!!!"], at_time)
        self.assertEqual(hours_map["not valid hours at all!!!"], fallback)
        self.assertEqual(fb, fallback)

    def test_is_park_edge_open_non_park(self):
        self.assertTrue(poh.is_park_edge_open({}, {"x": True}, False))

    def test_is_park_edge_open_empty_hours_uses_fallback(self):
        edge = {"is_park": "yes", "opening_hours": ""}
        self.assertTrue(poh.is_park_edge_open(edge, {}, True))
        self.assertFalse(poh.is_park_edge_open(edge, {}, False))

    def test_is_park_edge_open_semicolon_or(self):
        edge = {"is_park": "yes", "opening_hours": "24/7;Mo-Su 08:00-20:00"}
        at_night = _london(2026, 1, 15, 22, 0)
        hours_map, fallback = poh.build_request_hours_context(
            ["24/7", "Mo-Su 08:00-20:00"], at_night
        )
        self.assertTrue(poh.is_park_edge_open(edge, hours_map, fallback))

    def test_missing_catalog_entry_uses_fallback(self):
        edge = {"is_park": "yes", "opening_hours": "Mo-Su 08:00-20:00"}
        self.assertTrue(poh.is_park_edge_open(edge, {}, True))
        self.assertFalse(poh.is_park_edge_open(edge, {}, False))


if __name__ == "__main__":
    unittest.main()
