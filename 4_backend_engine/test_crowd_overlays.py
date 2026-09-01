"""
Unit tests for the rider-feedback routing overlay.

The load-bearing property here is that reports never touch shared state: the
global cost arrays and the OSM tags on the graph must be identical before and
after a report is applied.
"""
from __future__ import annotations

import os
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from unittest import mock

import numpy as np

import crowd_overlays
from crowd_overlays import CrowdEffects


@dataclass
class FakeTables:
    """Only the arrays crowd effects can touch."""

    risk: np.ndarray
    unlit_base: np.ndarray
    bad_surf_base: np.ndarray
    speed_stress: np.ndarray
    length: np.ndarray


@dataclass
class FakeShared:
    impassable: np.ndarray
    bake_s: float = 0.0


def tables(n: int = 8) -> FakeTables:
    return FakeTables(
        risk=np.zeros(n, dtype=np.float32),
        unlit_base=np.zeros(n, dtype=np.float32),
        bad_surf_base=np.zeros(n, dtype=np.float32),
        speed_stress=np.zeros(n, dtype=np.float32),
        length=np.ones(n, dtype=np.float32),
    )


def shared(n: int = 8) -> FakeShared:
    return FakeShared(impassable=np.zeros(n, dtype=np.uint8))


class ApplyEffectsTests(unittest.TestCase):
    def test_no_effects_returns_the_same_objects(self):
        t, s = tables(), shared()
        t2, s2 = crowd_overlays.apply_effects(t, s, CrowdEffects())
        self.assertIs(t2, t)
        self.assertIs(s2, s)

    def test_patched_arrays_are_copies_and_the_originals_are_untouched(self):
        t, s = tables(), shared()
        risk_before = t.risk.copy()

        t2, _ = crowd_overlays.apply_effects(t, s, CrowdEffects(risk={3: 1.0}))

        self.assertIsNot(t2.risk, t.risk)
        self.assertEqual(t2.risk[3], 1.0)
        np.testing.assert_array_equal(t.risk, risk_before)

    def test_untouched_arrays_are_shared_by_reference(self):
        t, s = tables(), shared()
        t2, _ = crowd_overlays.apply_effects(t, s, CrowdEffects(surf={1}))

        self.assertIsNot(t2.bad_surf_base, t.bad_surf_base)
        # A surface-only rider pays one copy, not five.
        self.assertIs(t2.risk, t.risk)
        self.assertIs(t2.speed_stress, t.speed_stress)
        self.assertIs(t2.unlit_base, t.unlit_base)

    def test_each_category_lands_on_its_own_array(self):
        t, s = tables(), shared()
        eff = CrowdEffects(
            closed={0},
            unlit={1},
            surf={2},
            risk={3: 1.0},
            speed={4: 0.15},
        )
        t2, s2 = crowd_overlays.apply_effects(t, s, eff)

        self.assertEqual(s2.impassable[0], 1)
        self.assertAlmostEqual(float(t2.unlit_base[1]), 0.5)
        self.assertAlmostEqual(float(t2.bad_surf_base[2]), 3.0)
        self.assertAlmostEqual(float(t2.risk[3]), 1.0)
        self.assertAlmostEqual(float(t2.speed_stress[4]), 0.15, places=5)
        np.testing.assert_array_equal(s.impassable, np.zeros(8, dtype=np.uint8))

    def test_speed_stress_never_lowers_an_existing_value(self):
        t, s = tables(), shared()
        t.speed_stress[4] = 0.8
        t2, _ = crowd_overlays.apply_effects(t, s, CrowdEffects(speed={4: 0.15}))
        self.assertAlmostEqual(float(t2.speed_stress[4]), 0.8)

    def test_risk_adds_rather_than_replaces(self):
        t, s = tables(), shared()
        t.risk[3] = 2.0
        t2, _ = crowd_overlays.apply_effects(t, s, CrowdEffects(risk={3: 1.0}))
        self.assertAlmostEqual(float(t2.risk[3]), 3.0)

    def test_out_of_range_edge_ids_are_ignored(self):
        t, s = tables(4), shared(4)
        t2, s2 = crowd_overlays.apply_effects(
            t, s, CrowdEffects(closed={99}, risk={-1: 1.0})
        )
        # Nothing in range was touched, so nothing was copied.
        self.assertIs(t2.risk, t.risk)
        self.assertIs(s2, s)


class EffectsMergeTests(unittest.TestCase):
    def test_risk_accumulates_and_speed_takes_the_max(self):
        a = CrowdEffects(risk={1: 1.0}, speed={2: 0.1})
        b = CrowdEffects(risk={1: 1.0}, speed={2: 0.3})
        merged = a.merged_with(b)
        self.assertAlmostEqual(merged.risk[1], 2.0)
        self.assertAlmostEqual(merged.speed[2], 0.3)

    def test_merge_does_not_mutate_either_side(self):
        a = CrowdEffects(risk={1: 1.0})
        b = CrowdEffects(risk={1: 1.0})
        a.merged_with(b)
        self.assertAlmostEqual(a.risk[1], 1.0)
        self.assertAlmostEqual(b.risk[1], 1.0)


class ScopeAndCacheTests(unittest.TestCase):
    def setUp(self):
        crowd_overlays.reset_for_tests()
        self.tables = tables()
        self.shared = shared()
        # apply() consults the live shared object to decide cacheability.
        self.patch = mock.patch(
            "edge_cost_arrays.get_shared_overlays", return_value=self.shared
        )
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        crowd_overlays.reset_for_tests()

    def test_anonymous_request_is_unaffected_by_a_personal_report(self):
        crowd_overlays.set_effects(personal={"u1": CrowdEffects(surf={2})})

        t_anon, _, meta_anon = crowd_overlays.apply(self.tables, self.shared, None)
        t_user, _, meta_user = crowd_overlays.apply(self.tables, self.shared, "u1")

        self.assertIs(t_anon, self.tables)
        self.assertEqual(meta_anon["personal_edges"], 0)
        self.assertAlmostEqual(float(t_user.bad_surf_base[2]), 3.0)
        self.assertEqual(meta_user["personal_edges"], 1)

    def test_a_second_identical_request_is_served_from_the_cache(self):
        crowd_overlays.set_effects(personal={"u1": CrowdEffects(surf={2})})

        first, _, meta1 = crowd_overlays.apply(self.tables, self.shared, "u1")
        second, _, meta2 = crowd_overlays.apply(self.tables, self.shared, "u1")

        self.assertFalse(meta1["cached"])
        self.assertTrue(meta2["cached"])
        self.assertIs(first, second)

    def test_a_version_bump_invalidates_the_cache(self):
        crowd_overlays.set_effects(personal={"u1": CrowdEffects(surf={2})})
        first, _, _ = crowd_overlays.apply(self.tables, self.shared, "u1")

        crowd_overlays.bump_version()
        second, _, meta = crowd_overlays.apply(self.tables, self.shared, "u1")

        self.assertFalse(meta["cached"])
        self.assertIsNot(first, second)

    def test_a_throwaway_shared_is_never_cached(self):
        """The future-depart_at branch builds its own shared object."""
        crowd_overlays.set_effects(personal={"u1": CrowdEffects(surf={2})})
        throwaway = shared()

        crowd_overlays.apply(self.tables, throwaway, "u1")
        _, _, meta = crowd_overlays.apply(self.tables, throwaway, "u1")
        self.assertFalse(meta["cached"])

    def test_avoid_points_block_without_polluting_the_cache(self):
        _, s2, meta = crowd_overlays.apply(
            self.tables, self.shared, "u1", avoid_eids=[5]
        )
        self.assertEqual(s2.impassable[5], 1)
        self.assertEqual(meta["avoid_points"], 1)
        self.assertFalse(meta["cached"])

        # The next plain request must not inherit the block.
        _, s3, _ = crowd_overlays.apply(self.tables, self.shared, "u1")
        self.assertIs(s3, self.shared)

    def test_kill_switch_disables_every_effect(self):
        crowd_overlays.set_effects(
            global_eff=CrowdEffects(closed={1}),
            personal={"u1": CrowdEffects(surf={2})},
        )
        with mock.patch.dict(os.environ, {"CROWD_OVERLAYS": "0"}):
            t2, s2, meta = crowd_overlays.apply(self.tables, self.shared, "u1")
        self.assertIs(t2, self.tables)
        self.assertIs(s2, self.shared)
        self.assertFalse(meta["enabled"])

    def test_global_kill_switch_leaves_personal_working(self):
        crowd_overlays.set_effects(
            global_eff=CrowdEffects(closed={1}),
            personal={"u1": CrowdEffects(surf={2})},
        )
        with mock.patch.dict(os.environ, {"CROWD_GLOBAL": "0"}):
            t2, s2, _ = crowd_overlays.apply(self.tables, self.shared, "u1")
        self.assertIs(s2, self.shared)
        self.assertAlmostEqual(float(t2.bad_surf_base[2]), 3.0)


class IngestTests(unittest.TestCase):
    def setUp(self):
        crowd_overlays.reset_for_tests()

    def tearDown(self):
        crowd_overlays._G = None
        crowd_overlays.reset_for_tests()

    def test_simulate_and_general_rows_never_become_effects(self):
        rows = [
            {"client_event_id": "a", "category": "general", "lat": 51.5, "lon": -0.1},
            {
                "client_event_id": "b",
                "category": "surface",
                "lat": 51.5,
                "lon": -0.1,
                "simulate": True,
            },
        ]
        snapped, writeback = crowd_overlays.ingest_rows(rows)
        self.assertEqual(snapped, [])
        self.assertEqual(writeback, [])

    def test_a_snap_miss_stores_the_row_but_produces_no_effect(self):
        rows = [{
            "client_event_id": "c",
            "category": "surface",
            "lat": 51.5,
            "lon": -0.1,
        }]
        with mock.patch.object(crowd_overlays, "snap_report", return_value=None):
            snapped, writeback = crowd_overlays.ingest_rows(rows)

        self.assertEqual(snapped, [])
        self.assertEqual(len(writeback), 1)
        self.assertEqual(writeback[0]["applied"], "none")
        self.assertFalse(crowd_overlays.effects_from_rows(snapped))

    def test_impassable_blocks_both_directions(self):
        graph = _two_node_graph()
        crowd_overlays._G = graph
        rows = [{
            "category": "impassable",
            "snapped_u": "A",
            "snapped_v": "B",
            "snap_dist_m": 5.0,
        }]
        eff = crowd_overlays.effects_from_rows(rows)
        self.assertEqual(eff.closed, {0, 1})

    def test_general_rows_are_skipped_by_effects_too(self):
        crowd_overlays._G = _two_node_graph()
        eff = crowd_overlays.effects_from_rows([{
            "category": "general",
            "snapped_u": "A",
            "snapped_v": "B",
        }])
        self.assertFalse(eff)

    def test_ingest_never_writes_to_the_graph(self):
        graph = _two_node_graph()
        crowd_overlays._G = graph
        before = dict(graph["A"]["B"])

        crowd_overlays.effects_from_rows([{
            "category": "unlit",
            "snapped_u": "A",
            "snapped_v": "B",
        }])
        self.assertEqual(dict(graph["A"]["B"]), before)


def _two_node_graph():
    import networkx as nx

    g = nx.DiGraph()
    g.add_node("A", x=-0.1, y=51.5)
    g.add_node("B", x=-0.101, y=51.5)
    g.add_edge("A", "B", _eid=0, lit="yes", osmid="123", barrier=None)
    g.add_edge("B", "A", _eid=1, lit="yes", osmid="123", barrier=None)
    return g


def _street_graph(
    node_count: int = 8,
    *,
    edge_length_m: float = 20.0,
    lit_from: int | None = None,
    junction_at: int | None = None,
):
    """
    A chain N0 - N1 - ... along one named way, for the unlit BFS.
    `lit_from` marks every edge at or beyond that index as already unlit.
    """
    import networkx as nx

    g = nx.DiGraph()
    for i in range(node_count):
        g.add_node(f"N{i}", x=-0.1 + i * 0.0002, y=51.5, car_physical_road_count=2)
    if junction_at is not None:
        g.nodes[f"N{junction_at}"]["car_physical_road_count"] = 4

    eid = 0
    for i in range(node_count - 1):
        lit = "no" if lit_from is not None and i >= lit_from else "yes"
        for a, b in ((f"N{i}", f"N{i+1}"), (f"N{i+1}", f"N{i}")):
            g.add_edge(
                a, b, _eid=eid, lit=lit, osmid="w1", name="Test Road",
                length=edge_length_m,
            )
            eid += 1
    return g


def _row(**overrides):
    row = {
        "client_event_id": "id-1",
        "category": "surface",
        "user_id": "u1",
        "device_id": None,
        "lat": 51.5,
        "lon": -0.1,
        "snapped_u": "A",
        "snapped_v": "B",
        "snap_dist_m": 4.0,
        "osm_id": "123",
        "payload": {},
        "applied": "none",
        "simulate": False,
        "personal_only": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    row.update(overrides)
    return row


class GlobalThresholdTests(unittest.TestCase):
    def setUp(self):
        crowd_overlays.reset_for_tests()
        crowd_overlays._G = _two_node_graph()

    def tearDown(self):
        crowd_overlays._G = None
        crowd_overlays.reset_for_tests()

    def test_one_contributor_does_not_apply(self):
        eff, writeback = crowd_overlays.build_global_effects([_row()])
        self.assertFalse(eff)
        self.assertEqual(writeback, [])

    def test_two_distinct_contributors_apply(self):
        rows = [_row(client_event_id="a"), _row(client_event_id="b", user_id="u2")]
        eff, writeback = crowd_overlays.build_global_effects(rows)
        self.assertIn(0, eff.surf)
        self.assertEqual(len(writeback), 2)

    def test_the_same_person_twice_is_still_one_contributor(self):
        rows = [_row(client_event_id="a"), _row(client_event_id="b")]
        eff, _ = crowd_overlays.build_global_effects(rows)
        self.assertFalse(eff)

    def test_a_guest_device_counts_as_a_distinct_contributor(self):
        rows = [
            _row(client_event_id="a"),
            _row(client_event_id="b", user_id=None, device_id="phone-9"),
        ]
        eff, _ = crowd_overlays.build_global_effects(rows)
        self.assertIn(0, eff.surf)

    def test_two_guests_on_one_device_are_one_contributor(self):
        rows = [
            _row(client_event_id="a", user_id=None, device_id="phone-9"),
            _row(client_event_id="b", user_id=None, device_id="phone-9"),
        ]
        eff, _ = crowd_overlays.build_global_effects(rows)
        self.assertFalse(eff)

    def test_personal_only_never_reaches_the_global_overlay(self):
        rows = [
            _row(client_event_id="a", personal_only=True),
            _row(client_event_id="b", user_id="u2", personal_only=True),
        ]
        eff, _ = crowd_overlays.build_global_effects(rows)
        self.assertFalse(eff)

    def test_personal_only_still_drives_that_users_own_overlay(self):
        personal = crowd_overlays.build_personal_effects(
            [_row(personal_only=True)]
        )
        self.assertIn(0, personal["u1"].surf)

    def test_simulate_rows_are_excluded_from_both_scopes(self):
        rows = [
            _row(client_event_id="a", simulate=True),
            _row(client_event_id="b", user_id="u2", simulate=True),
        ]
        eff, _ = crowd_overlays.build_global_effects(rows)
        self.assertFalse(eff)
        self.assertEqual(crowd_overlays.build_personal_effects(rows), {})

    def test_reports_older_than_the_retention_window_decay_out(self):
        old = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
        rows = [
            _row(client_event_id="a", created_at=old),
            _row(client_event_id="b", user_id="u2", created_at=old),
        ]
        eff, _ = crowd_overlays.build_global_effects(rows)
        self.assertFalse(eff)

    def test_reports_outside_the_corroboration_window_do_not_corroborate(self):
        stale = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
        rows = [
            _row(client_event_id="a"),
            _row(client_event_id="b", user_id="u2", created_at=stale),
        ]
        eff, _ = crowd_overlays.build_global_effects(rows)
        self.assertFalse(eff)

    def test_a_stationary_accurate_impassable_report_applies_alone(self):
        row = _row(
            category="impassable",
            payload={"fix": {"speed_mps": 0.2, "h_acc_m": 6.0}},
        )
        eff, _ = crowd_overlays.build_global_effects([row])
        self.assertEqual(eff.closed, {0, 1})

    def test_a_moving_impassable_report_still_needs_corroboration(self):
        row = _row(
            category="impassable",
            payload={"fix": {"speed_mps": 5.0, "h_acc_m": 6.0}},
        )
        eff, _ = crowd_overlays.build_global_effects([row])
        self.assertFalse(eff)

    def test_far_apart_reports_are_separate_clusters(self):
        rows = [
            _row(client_event_id="a"),
            # ~1 km east: a different pothole.
            _row(client_event_id="b", user_id="u2", lon=-0.086),
        ]
        eff, _ = crowd_overlays.build_global_effects(rows)
        self.assertFalse(eff)

    def test_unsnapped_rows_are_not_eligible(self):
        row = _row(snapped_u=None, snapped_v=None)
        self.assertFalse(crowd_overlays.eligible_for_global(row))


class UnlitExpansionTests(unittest.TestCase):
    def tearDown(self):
        crowd_overlays._G = None

    def test_an_already_unlit_edge_expands_to_nothing(self):
        crowd_overlays._G = _street_graph(lit_from=0)
        eids = crowd_overlays.expand_unlit("N0", "N1")
        self.assertEqual(len(eids), 1)

    def test_expansion_stops_at_an_edge_osm_already_calls_unlit(self):
        crowd_overlays._G = _street_graph(node_count=8, lit_from=3)
        eids = crowd_overlays.expand_unlit("N0", "N1")
        # N0-N1, N1-N2, N2-N3 are lit; N3 onward is mapped dark.
        self.assertLessEqual(len(eids), 6)
        self.assertGreater(len(eids), 1)

    def test_expansion_stops_at_a_real_junction(self):
        crowd_overlays._G = _street_graph(node_count=8, junction_at=2)
        eids = crowd_overlays.expand_unlit("N0", "N1")
        self.assertLess(len(eids), 12)

    def test_expansion_stops_at_the_length_cap(self):
        crowd_overlays._G = _street_graph(node_count=40, edge_length_m=60.0)
        eids = crowd_overlays.expand_unlit("N0", "N1")
        self.assertLessEqual(len(eids), 4)

    def test_expansion_stops_at_the_edge_count_cap(self):
        crowd_overlays._G = _street_graph(node_count=40, edge_length_m=0.5)
        eids = crowd_overlays.expand_unlit("N0", "N1")
        self.assertLessEqual(len(eids), crowd_overlays.UNLIT_BFS_MAX_EDGES)


if __name__ == "__main__":
    unittest.main()
