"""Unit tests for ride report validation, local persistence and rate limits."""
from __future__ import annotations

import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

import auth_rate_limit
import ride_reports


def _report(**overrides):
    row = {
        "client_event_id": str(uuid.uuid4()),
        "category": "surface",
        "device_id": "dev-1",
        "lat": 51.5074,
        "lon": -0.1278,
        "payload": {"schema": 1, "fix": {"lat": 51.5074, "lon": -0.1278}},
    }
    row.update(overrides)
    return row


class RideReportValidationTests(unittest.TestCase):
    def test_accepts_a_well_formed_report(self):
        row, err = ride_reports.normalize_report(_report(), user_id=None)
        self.assertIsNone(err)
        self.assertEqual(row["category"], "surface")
        self.assertEqual(row["source"], "tbt_island")
        self.assertFalse(row["simulate"])
        self.assertFalse(row["personal_only"])

    def test_user_id_comes_from_the_token_not_the_body(self):
        row, err = ride_reports.normalize_report(
            _report(user_id="attacker-supplied"),
            user_id="verified-user",
        )
        self.assertIsNone(err)
        self.assertEqual(row["user_id"], "verified-user")

    def test_rejects_unknown_category(self):
        _, err = ride_reports.normalize_report(
            _report(category="hostile"), user_id=None
        )
        self.assertIn("category", err)

    def test_rejects_non_uuid_client_event_id(self):
        _, err = ride_reports.normalize_report(
            _report(client_event_id="not-a-uuid"), user_id=None
        )
        self.assertIn("uuid", err)

    def test_rejects_position_outside_london(self):
        _, err = ride_reports.normalize_report(
            _report(lat=48.8566, lon=2.3522), user_id=None
        )
        self.assertIn("outside", err)

    def test_rejects_non_finite_position(self):
        _, err = ride_reports.normalize_report(
            _report(lat=float("nan")), user_id=None
        )
        self.assertIn("lat", err)

    def test_rejects_oversized_payload(self):
        big = {"blob": "x" * (ride_reports.MAX_PAYLOAD_BYTES + 1)}
        _, err = ride_reports.normalize_report(_report(payload=big), user_id=None)
        self.assertIn("bytes", err)

    def test_flags_coerce_from_strings(self):
        row, err = ride_reports.normalize_report(
            _report(simulate="true", personal_only=1), user_id=None
        )
        self.assertIsNone(err)
        self.assertTrue(row["simulate"])
        self.assertTrue(row["personal_only"])


class RideReportLocalStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        ride_reports._path_override = Path(self._tmpdir.name) / "ride_reports.json"
        self.env = mock.patch.dict(
            os.environ,
            {"SUPABASE_URL": "", "SUPABASE_SERVICE_ROLE_KEY": ""},
            clear=False,
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        ride_reports._path_override = None
        self._tmpdir.cleanup()

    def test_round_trip(self):
        rows = [_report(), _report(category="impassable")]
        result, err = ride_reports.submit_ride_reports(rows, user_id="u1")
        self.assertIsNone(err)
        self.assertEqual(len(result["accepted"]), 2)
        self.assertEqual(result["duplicates"], [])

        stored, err = ride_reports.list_ride_reports()
        self.assertIsNone(err)
        self.assertEqual(len(stored), 2)
        self.assertEqual({r["user_id"] for r in stored}, {"u1"})

    def test_replaying_a_batch_inserts_nothing(self):
        rows = [_report(), _report()]
        first, _ = ride_reports.submit_ride_reports(rows, user_id=None)
        second, _ = ride_reports.submit_ride_reports(rows, user_id=None)

        self.assertEqual(len(first["accepted"]), 2)
        self.assertEqual(second["accepted"], [])
        self.assertEqual(len(second["duplicates"]), 2)

        stored, _ = ride_reports.list_ride_reports()
        self.assertEqual(len(stored), 2)

    def test_duplicate_id_within_one_batch_is_an_error_not_a_second_row(self):
        shared = str(uuid.uuid4())
        rows = [_report(client_event_id=shared), _report(client_event_id=shared)]
        result, err = ride_reports.submit_ride_reports(rows, user_id=None)
        self.assertIsNone(err)
        self.assertEqual(len(result["accepted"]), 1)
        self.assertEqual(len(result["errors"]), 1)

    def test_invalid_rows_are_reported_without_dropping_valid_ones(self):
        rows = [_report(), _report(category="nope")]
        result, err = ride_reports.submit_ride_reports(rows, user_id=None)
        self.assertIsNone(err)
        self.assertEqual(len(result["accepted"]), 1)
        self.assertEqual(result["errors"][0]["index"], 1)

    def test_batch_size_is_capped(self):
        rows = [_report() for _ in range(ride_reports.MAX_REPORTS_PER_BATCH + 1)]
        _, err = ride_reports.submit_ride_reports(rows, user_id=None)
        self.assertIn("at most", err)

    def test_mark_snapped_updates_in_place(self):
        row = _report()
        ride_reports.submit_ride_reports([row], user_id=None)
        err = ride_reports.mark_snapped([{
            "client_event_id": row["client_event_id"],
            "snapped_eid": 42,
            "snap_dist_m": 7.5,
            "applied": "personal",
        }])
        self.assertIsNone(err)

        stored, _ = ride_reports.list_ride_reports()
        self.assertEqual(stored[0]["snapped_eid"], 42)
        self.assertEqual(stored[0]["applied"], "personal")


class RideReportRateLimitTests(unittest.TestCase):
    def setUp(self):
        auth_rate_limit.reset_for_tests()

    def tearDown(self):
        auth_rate_limit.reset_for_tests()

    def test_a_batch_costs_its_own_size(self):
        res = auth_rate_limit.check_ride_report_allowed("1.2.3.4", None, count=25)
        self.assertTrue(res.allowed)
        # 25 of the IP budget of 30 are gone, so a second 25 cannot fit.
        res = auth_rate_limit.check_ride_report_allowed("1.2.3.4", None, count=25)
        self.assertFalse(res.allowed)

    def test_user_cap_is_tighter_than_the_ip_cap(self):
        res = auth_rate_limit.check_ride_report_allowed("1.2.3.4", "u1", count=21)
        self.assertFalse(res.allowed)
        # A rejected batch must not have charged the IP bucket either.
        res = auth_rate_limit.check_ride_report_allowed("1.2.3.4", "u1", count=20)
        self.assertTrue(res.allowed)

    def test_separate_ips_have_separate_budgets(self):
        auth_rate_limit.check_ride_report_allowed("1.1.1.1", None, count=30)
        self.assertFalse(
            auth_rate_limit.check_ride_report_allowed("1.1.1.1", None).allowed
        )
        self.assertTrue(
            auth_rate_limit.check_ride_report_allowed("2.2.2.2", None).allowed
        )


if __name__ == "__main__":
    unittest.main()
