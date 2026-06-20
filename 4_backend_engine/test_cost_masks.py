"""Unit tests for cost_masks (no graph load required)."""
import unittest

from cost_masks import (
    is_segregated_cycling,
    is_steps,
    is_vehicular_free,
    routing_width_m,
)


class CostMasksTest(unittest.TestCase):
    def test_cycleway_highway_is_vehicular_free(self):
        self.assertTrue(is_vehicular_free({"type": "cycleway"}))

    def test_park_not_vehicular_free_or_reward(self):
        park = {"type": "residential", "is_park": "yes"}
        self.assertFalse(is_vehicular_free(park))
        self.assertFalse(is_segregated_cycling(park))
        self.assertFalse(is_vehicular_free({"type": "residential", "is_river": "yes"}))
        self.assertFalse(is_vehicular_free({"type": "residential", "is_sight": "yes"}))

    def test_footway_masked_not_rewarded(self):
        footway = {"type": "footway"}
        self.assertTrue(is_vehicular_free(footway))
        self.assertFalse(is_segregated_cycling(footway))

    def test_pedestrian_masked_not_rewarded(self):
        ped = {"type": "pedestrian"}
        self.assertTrue(is_vehicular_free(ped))
        self.assertFalse(is_segregated_cycling(ped))

    def test_cycleway_both_mask_and_reward(self):
        cw = {"type": "cycleway"}
        self.assertTrue(is_vehicular_free(cw))
        self.assertTrue(is_segregated_cycling(cw))

    def test_physical_cycleway_tag_whitelist(self):
        track = {"type": "primary", "cycleway": "track"}
        self.assertTrue(is_vehicular_free(track))
        self.assertTrue(is_segregated_cycling(track))
        self.assertTrue(is_vehicular_free({"type": "primary", "cycleway_left": "separate"}))
        self.assertFalse(is_vehicular_free({"type": "primary", "cycleway": "lane"}))
        self.assertFalse(is_segregated_cycling({"type": "primary", "cycleway": "lane"}))
        self.assertFalse(is_vehicular_free({"type": "primary", "cycleway": "shared_lane"}))
        self.assertFalse(is_vehicular_free({"type": "primary", "cycleway": "no"}))
        self.assertFalse(is_vehicular_free({"type": "primary", "segregated": "yes"}))

    def test_cycleway_separation(self):
        self.assertTrue(
            is_vehicular_free({"type": "primary", "cycleway_separation": "kerb"})
        )
        self.assertFalse(
            is_vehicular_free({"type": "primary", "cycleway_separation": "no"})
        )

    def test_superhighway_programme(self):
        self.assertTrue(
            is_vehicular_free({"type": "primary", "tfl_cycle_programme": "superhighway"})
        )
        self.assertFalse(
            is_vehicular_free({"type": "primary", "tfl_cycle_programme": "quietway"})
        )

    def test_residential_not_vehicular_free(self):
        self.assertFalse(is_vehicular_free({"type": "residential", "maxspeed": "30 mph"}))

    def test_steps(self):
        self.assertTrue(is_steps({"type": "steps"}))
        self.assertFalse(is_steps({"type": "footway"}))

    def test_routing_width_cycleway_only(self):
        d = {"type": "primary", "cycleway_width": "1.2", "width": "10"}
        self.assertAlmostEqual(routing_width_m(d), 1.2)

    def test_routing_width_vehicular_free_no_cw(self):
        self.assertIsNone(routing_width_m({"type": "cycleway", "width": "2"}))

    def test_routing_width_fallback_road(self):
        self.assertAlmostEqual(
            routing_width_m({"type": "residential", "width": "2"}),
            2.0,
        )


if __name__ == "__main__":
    unittest.main()
