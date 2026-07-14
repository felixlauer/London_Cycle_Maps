"""Unit tests for auth_rate_limit (no Flask / graph)."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))

import auth_rate_limit as rl


class AuthRateLimitTests(unittest.TestCase):
    def setUp(self):
        rl.reset_for_tests()

    def test_ip_budget_blocks_after_max(self):
        ip = "203.0.113.1"
        for _ in range(rl.IP_MAX_REQUESTS):
            self.assertTrue(rl.check_ip_auth_budget(ip).allowed)
        blocked = rl.check_ip_auth_budget(ip)
        self.assertFalse(blocked.allowed)
        self.assertGreaterEqual(blocked.retry_after_s, 1)

    def test_login_lockout_after_failures(self):
        email = "target@example.com"
        ip = "203.0.113.2"
        self.assertTrue(rl.check_login_allowed(ip, email).allowed)
        for _ in range(rl.EMAIL_MAX_FAILURES - 1):
            self.assertIsNone(rl.record_login_failure(email))
        lock = rl.record_login_failure(email)
        self.assertIsNotNone(lock)
        self.assertFalse(lock.allowed)
        blocked = rl.check_login_allowed(ip, email)
        self.assertFalse(blocked.allowed)

    def test_clear_login_failures(self):
        email = "ok@example.com"
        for _ in range(rl.EMAIL_MAX_FAILURES):
            rl.record_login_failure(email)
        rl.clear_login_failures(email)
        self.assertTrue(rl.check_login_allowed("203.0.113.3", email).allowed)

    def test_reset_email_cap(self):
        email = "reset@example.com"
        ip = "203.0.113.4"
        for _ in range(rl.RESET_EMAIL_MAX):
            self.assertTrue(rl.check_reset_allowed(ip, email).allowed)
        self.assertFalse(rl.check_reset_allowed(ip, email).allowed)

    def test_signup_ip_cap(self):
        ip = "203.0.113.5"
        for _ in range(rl.SIGNUP_IP_MAX):
            self.assertTrue(rl.check_signup_allowed(ip).allowed)
        self.assertFalse(rl.check_signup_allowed(ip).allowed)

    def test_route_commit_ip_cap(self):
        ip = "203.0.113.6"
        for _ in range(rl.ROUTE_COMMIT_IP_MAX):
            self.assertTrue(rl.check_route_commit_allowed(ip).allowed)
        blocked = rl.check_route_commit_allowed(ip)
        self.assertFalse(blocked.allowed)
        self.assertGreaterEqual(blocked.retry_after_s, 1)
        # Prefetch does not call check_route_commit_allowed — separate IP still free.
        self.assertTrue(rl.check_route_commit_allowed("203.0.113.7").allowed)


if __name__ == "__main__":
    unittest.main()
