"""Tests for auth redirect allowlist + rate-limit helpers (no graph)."""
import os
import unittest
from unittest import mock

import auth_redirect
import auth_rate_limit


class ResetRedirectTests(unittest.TestCase):
    def test_localhost_allowed_when_unset(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AUTH_RESET_REDIRECT_ALLOWLIST", None)
            self.assertTrue(
                auth_redirect.reset_redirect_allowed("http://localhost:3000/")
            )
            self.assertTrue(
                auth_redirect.reset_redirect_allowed("http://127.0.0.1:3000/reset")
            )
            self.assertFalse(
                auth_redirect.reset_redirect_allowed("https://evil.example/phish")
            )

    def test_allowlist_prefix(self):
        with mock.patch.dict(
            os.environ,
            {"AUTH_RESET_REDIRECT_ALLOWLIST": "https://app.tunedcycling.online"},
            clear=False,
        ):
            self.assertTrue(
                auth_redirect.reset_redirect_allowed(
                    "https://app.tunedcycling.online/"
                )
            )
            self.assertTrue(
                auth_redirect.reset_redirect_allowed(
                    "https://app.tunedcycling.online/app"
                )
            )
            self.assertFalse(
                auth_redirect.reset_redirect_allowed("http://localhost:3000/")
            )
            self.assertFalse(
                auth_redirect.reset_redirect_allowed("https://evil.example/")
            )


class PrefetchLimitTests(unittest.TestCase):
    def setUp(self):
        auth_rate_limit.reset_for_tests()

    def test_prefetch_caps_at_30(self):
        ip = "203.0.113.9"
        for _ in range(30):
            self.assertTrue(auth_rate_limit.check_route_prefetch_allowed(ip).allowed)
        denied = auth_rate_limit.check_route_prefetch_allowed(ip)
        self.assertFalse(denied.allowed)


if __name__ == "__main__":
    unittest.main()
