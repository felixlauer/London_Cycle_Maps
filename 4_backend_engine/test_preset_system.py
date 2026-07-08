"""
Regression tests for the preset system (no graph or Flask load).

Covers: structural hard blocks independent of weights, cargo barrier blocks,
VF flag precompute + allowed-set masks, translation-layer clamping, reward
lerp floors and heuristic admissibility, schema v2 validation.

Run from 4_backend_engine:
  python -m unittest test_preset_system -v
"""
import unittest

from barrier_clusters import (
    CARGO_IMPASSABLE_TAGS,
    barrier_is_hard_block,
)
from cost_masks import (
    VF_MASK_BUS_LANE,
    VF_MASK_CORE,
    VF_MASK_PAINTED_LANE,
    VF_MASK_SHARED_PATH,
    VF_REWARD_BUS_LANE,
    VF_REWARD_CORE,
    is_segregated_cycling,
    is_vehicular_free,
    vf_allowed_masks,
    vf_flags,
)
from routing_heuristic import (
    GREEN_REWARD_FLOOR,
    TFL_NETWORK_REWARD_FLOOR,
    VEHICULAR_FREE_REWARD_FLOOR,
    compute_optimized_cost_per_metre_lower_bound,
    green_reward,
    tfl_network_reward,
    vehicular_free_reward,
)
import translation_layer
import user_profiles


class HardBlockTest(unittest.TestCase):
    """Hard blocks are structural - they hold regardless of any weight vector."""

    def test_impassable_barrier_blocks_for_all_bikes(self):
        d = {"barrier": "fence"}
        for bike in ("standard", "road", "ebike", "cargo"):
            self.assertTrue(barrier_is_hard_block(d, bike))

    def test_cargo_group4_hostile_blocks(self):
        for tag in ("step", "log", "rising_kerb", "debris"):
            d = {"barrier": tag}
            self.assertTrue(barrier_is_hard_block(d, "cargo"), tag)
            self.assertFalse(barrier_is_hard_block(d, "standard"), tag)

    def test_cargo_chicane_tags_block_only_cargo(self):
        for tag in ("cycle_barrier", "motorcycle_barrier", "wicket_gate"):
            d = {"barrier": tag}
            self.assertTrue(barrier_is_hard_block(d, "cargo"), tag)
            self.assertFalse(barrier_is_hard_block(d, "standard"), tag)

    def test_access_denied_blocks_regardless_of_bike(self):
        d = {"barrier": "gate", "barrier_access": "private"}
        self.assertTrue(barrier_is_hard_block(d))
        self.assertTrue(barrier_is_hard_block(d, "cargo"))

    def test_bicycle_override_unblocks(self):
        d = {"barrier": "gate", "barrier_access": "private", "barrier_bicycle": "yes"}
        self.assertFalse(barrier_is_hard_block(d))


class VfFlagsTest(unittest.TestCase):
    def test_cycleway_is_core_and_rewarded(self):
        flags = vf_flags({"type": "cycleway"})
        self.assertTrue(flags & VF_MASK_CORE)
        self.assertTrue(flags & VF_REWARD_CORE)

    def test_footway_is_shared_path_no_reward(self):
        flags = vf_flags({"type": "footway"})
        self.assertTrue(flags & VF_MASK_SHARED_PATH)
        self.assertFalse(flags & VF_MASK_CORE)
        self.assertFalse(flags & (VF_REWARD_CORE | VF_REWARD_BUS_LANE))

    def test_share_busway_is_bus_lane(self):
        flags = vf_flags({"type": "residential", "cycleway": "share_busway"})
        self.assertTrue(flags & VF_MASK_BUS_LANE)
        self.assertTrue(flags & VF_REWARD_BUS_LANE)
        self.assertFalse(flags & VF_MASK_CORE)

    def test_park_edge_masked_but_not_rewarded(self):
        flags = vf_flags({"type": "cycleway", "is_park": "yes"})
        self.assertTrue(flags & VF_MASK_CORE)
        self.assertFalse(flags & VF_REWARD_CORE)

    def test_exclusive_painted_lane_on_carriageway(self):
        flags = vf_flags({
            "type": "primary",
            "cycleway": "lane",
            "cycleway_lane": "exclusive",
        })
        self.assertTrue(flags & VF_MASK_PAINTED_LANE)
        self.assertFalse(flags & VF_MASK_CORE)
        self.assertFalse(flags & VF_REWARD_CORE)

    def test_advisory_lane_not_painted_vf(self):
        flags = vf_flags({
            "type": "primary",
            "cycleway": "lane",
            "cycleway_lane": "advisory",
        })
        self.assertFalse(flags & VF_MASK_PAINTED_LANE)

    def test_lane_without_subtag_not_painted_vf(self):
        self.assertFalse(vf_flags({"type": "primary", "cycleway": "lane"}) & VF_MASK_PAINTED_LANE)

    def test_painted_lane_deselected(self):
        edge = {
            "type": "primary",
            "cycleway": "lane",
            "cycleway_lane": "exclusive",
        }
        mask_allowed, _ = vf_allowed_masks(shared_path=True, bus_lane=True, painted_lane=False)
        self.assertFalse(vf_flags(edge) & mask_allowed)
        mask_on, _ = vf_allowed_masks(painted_lane=True)
        self.assertTrue(vf_flags(edge) & mask_on)

    def test_plain_road_has_no_flags(self):
        self.assertEqual(vf_flags({"type": "residential"}), 0)

    def test_all_on_matches_legacy_classification(self):
        """With every class allowed, flag masking equals the legacy functions."""
        mask_allowed, reward_allowed = vf_allowed_masks(True, True)
        samples = [
            {"type": "cycleway"},
            {"type": "footway"},
            {"type": "path"},
            {"type": "bridleway"},
            {"type": "residential", "cycleway": "share_busway"},
            {"type": "residential", "cycleway": "track"},
            {"type": "residential", "cycleway_separation": "kerb"},
            {"type": "primary", "tfl_cycle_programme": "superhighway"},
            {"type": "residential"},
            {"type": "cycleway", "is_park": "yes"},
        ]
        for d in samples:
            flags = vf_flags(d)
            self.assertEqual(
                bool(flags & mask_allowed), is_vehicular_free(d), d
            )
            self.assertEqual(
                bool(flags & reward_allowed), is_segregated_cycling(d), d
            )

    def test_shared_path_deselected(self):
        mask_allowed, _ = vf_allowed_masks(shared_path=False, bus_lane=True)
        self.assertFalse(vf_flags({"type": "footway"}) & mask_allowed)
        self.assertTrue(vf_flags({"type": "cycleway"}) & mask_allowed)

    def test_bus_lane_deselected(self):
        mask_allowed, reward_allowed = vf_allowed_masks(shared_path=True, bus_lane=False)
        bus = vf_flags({"type": "residential", "cycleway": "share_busway"})
        self.assertFalse(bus & mask_allowed)
        self.assertFalse(bus & reward_allowed)


class TranslationLayerTest(unittest.TestCase):
    def _zero_weights(self):
        return {k: 0.0 for k in user_profiles.ROUTING_WEIGHT_KEYS}

    def test_no_preset_no_clamp(self):
        w = self._zero_weights()
        w["signal_weight"] = 2.0
        out, clamps = translation_layer.apply_preset_clamps(w, None)
        self.assertEqual(clamps, [])
        self.assertEqual(out, w)

    def test_fast_preset_raises_risk_floor(self):
        # signal_risk_arterial: signal >= 0.6 and risk < 0.4 is toxic;
        # fast mode keeps signal (dominant), so risk is raised to 0.4.
        w = self._zero_weights()
        w["signal_weight"] = 1.2
        w["risk_weight"] = 0.3
        out, clamps = translation_layer.apply_preset_clamps(w, "fast")
        ids = [c["coupling_id"] for c in clamps]
        self.assertIn("signal_risk_arterial", ids)
        self.assertEqual(out["risk_weight"], 0.4)
        self.assertEqual(out["signal_weight"], 1.2)

    def test_safe_preset_caps_signal(self):
        # Same toxic combo, safe mode keeps risk: signal is clamped below 0.6.
        w = self._zero_weights()
        w["signal_weight"] = 1.2
        w["risk_weight"] = 0.3
        out, clamps = translation_layer.apply_preset_clamps(w, "safe")
        ids = [c["coupling_id"] for c in clamps]
        self.assertIn("signal_risk_arterial", ids)
        self.assertLess(out["signal_weight"], 0.6)
        self.assertEqual(out["risk_weight"], 0.3)

    def test_untripped_trigger_untouched(self):
        # signal below its 0.6 arterial threshold: signal_risk_arterial must not
        # trip (other couplings may - e.g. risk_surface_floor caps risk in fast
        # mode when surface protection is off, which is authored behaviour).
        w = self._zero_weights()
        w["signal_weight"] = 0.2
        w["risk_weight"] = 1.0
        out, clamps = translation_layer.apply_preset_clamps(w, "fast")
        ids = [c["coupling_id"] for c in clamps]
        self.assertNotIn("signal_risk_arterial", ids)
        self.assertEqual(out["signal_weight"], 0.2)

    def test_floor_coupling_raises_surface_in_safe_mode(self):
        # risk_surface_floor: risk >= 0.6 with surface < 0.2; safe mode keeps
        # risk dominant and floors surface up to 0.2.
        w = self._zero_weights()
        w["risk_weight"] = 1.2
        out, clamps = translation_layer.apply_preset_clamps(w, "safe")
        ids = [c["coupling_id"] for c in clamps]
        self.assertIn("risk_surface_floor", ids)
        self.assertEqual(out["surface_weight"], 0.2)
        self.assertEqual(out["risk_weight"], 1.2)

    def test_no_retired_keys_loaded(self):
        for coupling in translation_layer._COUPLINGS:
            for key in coupling["weights"]:
                self.assertNotIn(key, translation_layer.RETIRED_WEIGHT_KEYS)


    def test_fast_signal_calming_clamp_floor(self):
        # signal_calming_rat_run: fast keeps signal; calming clamped to just below 0.75.
        w = self._zero_weights()
        w["signal_weight"] = 1.2
        w["calming_weight"] = 1.2
        out, clamps = translation_layer.apply_preset_clamps(w, "fast")
        ids = [c["coupling_id"] for c in clamps]
        self.assertIn("signal_calming_rat_run", ids)
        self.assertAlmostEqual(out["calming_weight"], 0.7499, places=4)
        self.assertEqual(out["signal_weight"], 1.2)


class RouteTimeEstimateTest(unittest.TestCase):
    def test_fast_multiplier(self):
        from route_time_estimate import (
            FAST_PRESET_DURATION_SPEED_MULTIPLIER,
            cruise_duration_min,
            duration_speed_multiplier_for_preset,
        )

        self.assertEqual(duration_speed_multiplier_for_preset("fast"), 1.35)
        self.assertEqual(duration_speed_multiplier_for_preset("safe"), 1.0)
        base = cruise_duration_min(6000.0, 15.0, 1.0)
        fast = cruise_duration_min(6000.0, 15.0, FAST_PRESET_DURATION_SPEED_MULTIPLIER)
        self.assertLess(fast, base)
        self.assertAlmostEqual(fast, base / 1.35, places=4)


class RewardLerpTest(unittest.TestCase):
    def test_rewards_are_one_at_zero(self):
        self.assertEqual(tfl_network_reward(0.0), 1.0)
        self.assertEqual(green_reward(0.0), 1.0)
        self.assertEqual(vehicular_free_reward(0.0), 1.0)

    def test_saturation_floors_at_cap_and_beyond(self):
        self.assertAlmostEqual(tfl_network_reward(1.0), TFL_NETWORK_REWARD_FLOOR)
        self.assertAlmostEqual(tfl_network_reward(5.0), TFL_NETWORK_REWARD_FLOOR)
        self.assertAlmostEqual(green_reward(1.0), GREEN_REWARD_FLOOR)
        self.assertAlmostEqual(green_reward(5.0), GREEN_REWARD_FLOOR)
        self.assertAlmostEqual(vehicular_free_reward(3.0), VEHICULAR_FREE_REWARD_FLOOR)
        self.assertAlmostEqual(vehicular_free_reward(9.0), VEHICULAR_FREE_REWARD_FLOOR)

    def test_heuristic_lower_bound_is_admissible(self):
        """h scale must never exceed the deepest possible per-metre cost (M=1 edge
        with every reward active at the given weights)."""
        vectors = [
            {"tfl_cycleway_weight": 0.5, "green_weight": 0.6, "vehicular_free_weight": 2.5},
            {"tfl_cycleway_weight": 1.0, "green_weight": 1.0, "vehicular_free_weight": 3.0},
            {"tfl_cycleway_weight": 0.3},
            {},
        ]
        for w in vectors:
            scale = compute_optimized_cost_per_metre_lower_bound(w)
            deepest_r = 1.0
            if w.get("tfl_cycleway_weight", 0) > 0:
                deepest_r *= tfl_network_reward(w["tfl_cycleway_weight"])
            if w.get("green_weight", 0) > 0:
                deepest_r *= green_reward(w["green_weight"])
            if w.get("vehicular_free_weight", 0) > 0:
                deepest_r *= vehicular_free_reward(w["vehicular_free_weight"])
            self.assertLessEqual(scale, deepest_r + 1e-12, w)


class SchemaV2Test(unittest.TestCase):
    def _full_weights(self, **overrides):
        w = {k: 0.1 for k in user_profiles.ROUTING_WEIGHT_KEYS}
        w.update(overrides)
        return w

    def test_valid_weights_accepted(self):
        ok, err = user_profiles.validate_weights(self._full_weights())
        self.assertTrue(ok, err)

    def test_sweep_scale_values_accepted(self):
        ok, err = user_profiles.validate_weights(
            self._full_weights(hill_weight=3.0, junction_weight=3.0, vehicular_free_weight=2.5)
        )
        self.assertTrue(ok, err)

    def test_over_cap_rejected(self):
        ok, err = user_profiles.validate_weights(self._full_weights(signal_weight=2.5))
        self.assertFalse(ok)
        self.assertIn("signal_weight", err)

    def test_retired_keys_rejected(self):
        ok, err = user_profiles.validate_weights(self._full_weights(width_weight=0.5))
        self.assertFalse(ok)
        self.assertIn("width_weight", err)

    def test_missing_vehicular_free_rejected(self):
        w = self._full_weights()
        del w["vehicular_free_weight"]
        ok, err = user_profiles.validate_weights(w)
        self.assertFalse(ok)
        self.assertIn("vehicular_free_weight", err)

    def test_toggles_normalized(self):
        t = user_profiles._normalize_toggles({"light_night": 1, "vf_infrastructure": {"bus_lane": False}})
        self.assertIs(t["light_night"], True)
        self.assertIs(t["jam_comfort"], True)
        self.assertIs(t["vf_infrastructure"]["shared_path"], True)
        self.assertIs(t["vf_infrastructure"]["bus_lane"], False)

    def test_bike_type_normalized(self):
        self.assertEqual(user_profiles._normalize_bike_type("CARGO"), "cargo")
        self.assertEqual(user_profiles._normalize_bike_type("unicycle"), "standard")
        self.assertEqual(user_profiles._normalize_bike_type(None), "standard")


if __name__ == "__main__":
    unittest.main()
