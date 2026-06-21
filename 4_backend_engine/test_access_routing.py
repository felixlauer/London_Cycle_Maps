"""Unit tests for service access and barrier access routing (no graph or Flask load)."""
import unittest

from barrier_clusters import (
    barrier_additive_penalty,
    barrier_is_hard_block,
)
from cost_masks import (
    is_service_access_denied,
    is_service_alley,
    is_service_steps_like,
    masks_surface_and_hill,
    SERVICE_ACCESS_DENIED,
    BARRIER_ACCESS_DENIED,
)

PEDESTRIAN_HIGHWAY_M = 4.0
STEPS_HIGHWAY_M = 50.0


def _service_highway_m(d: dict) -> float:
    """Mirror app._highway_type_multiplier service branch (no Flask import)."""
    if is_service_access_denied(d):
        return 1.0
    if is_service_alley(d):
        return PEDESTRIAN_HIGHWAY_M
    return STEPS_HIGHWAY_M


class ServiceAccessTest(unittest.TestCase):
    def test_denied_access_values(self):
        self.assertEqual(SERVICE_ACCESS_DENIED, frozenset({"private", "no", "customers"}))

    def test_service_private_denied(self):
        self.assertTrue(is_service_access_denied({"type": "service", "access": "private"}))

    def test_service_private_overridden_by_bicycle_yes(self):
        d = {"type": "service", "access": "private", "bicycle": "yes"}
        self.assertFalse(is_service_access_denied(d))

    def test_service_private_overridden_by_bicycle_designated(self):
        d = {"type": "service", "access": "no", "bicycle": "designated"}
        self.assertFalse(is_service_access_denied(d))

    def test_service_customers_denied(self):
        self.assertTrue(is_service_access_denied({"type": "service", "access": "customers"}))

    def test_service_alley_pedestrian_multiplier(self):
        d = {"type": "service", "service": "alley", "access": ""}
        self.assertTrue(is_service_alley(d))
        self.assertFalse(is_service_steps_like(d))
        self.assertAlmostEqual(_service_highway_m(d), PEDESTRIAN_HIGHWAY_M)

    def test_service_driveway_steps_multiplier(self):
        d = {"type": "service", "service": "parking_aisle"}
        self.assertTrue(is_service_steps_like(d))
        self.assertAlmostEqual(_service_highway_m(d), STEPS_HIGHWAY_M)
        self.assertTrue(masks_surface_and_hill(d))

    def test_service_destination_routable_steps_like(self):
        d = {"type": "service", "access": "destination"}
        self.assertFalse(is_service_access_denied(d))
        self.assertAlmostEqual(_service_highway_m(d), STEPS_HIGHWAY_M)


class BarrierAccessTest(unittest.TestCase):
    def test_barrier_denied_values(self):
        self.assertEqual(BARRIER_ACCESS_DENIED, frozenset({"private", "no"}))

    def test_gate_private_hard_block_ignores_confidence(self):
        d = {
            "barrier": "gate",
            "barrier_access": "private",
            "barrier_confidence": 0.5,
        }
        self.assertTrue(barrier_is_hard_block(d))
        self.assertEqual(barrier_additive_penalty(d), 0.0)

    def test_gate_no_hard_block(self):
        self.assertTrue(
            barrier_is_hard_block({"barrier": "gate", "barrier_access": "no"})
        )

    def test_gate_private_overridden_by_barrier_bicycle(self):
        d = {
            "barrier": "gate",
            "barrier_access": "private",
            "barrier_bicycle": "yes",
            "barrier_confidence": 0.5,
        }
        self.assertFalse(barrier_is_hard_block(d))
        self.assertGreater(barrier_additive_penalty(d), 0.0)

    def test_park_gate_waiver_cluster3(self):
        d = {
            "barrier": "gate",
            "barrier_access": "",
            "is_park": "yes",
            "barrier_confidence": 1.0,
        }
        self.assertFalse(barrier_is_hard_block(d))
        self.assertEqual(barrier_additive_penalty(d), 0.0)

    def test_park_private_gate_still_blocked(self):
        d = {"barrier": "gate", "barrier_access": "private", "is_park": "yes"}
        self.assertTrue(barrier_is_hard_block(d))

    def test_park_bollard_still_penalised(self):
        d = {"barrier": "bollard", "is_park": "yes", "barrier_confidence": 1.0}
        self.assertGreater(barrier_additive_penalty(d), 0.0)


if __name__ == "__main__":
    unittest.main()
