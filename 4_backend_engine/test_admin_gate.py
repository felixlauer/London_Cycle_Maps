"""Unit tests for admin gate + trusted proxy IP (no graph load)."""
import os
import unittest
from unittest import mock

from flask import Flask

import auth_middleware
from auth_rate_limit import client_ip_from_request


class RequireAdminTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)

        @self.app.route("/admin/update_x", methods=["POST"])
        @auth_middleware.require_admin
        def _ok():
            return {"ok": True}

        self.client = self.app.test_client()

    def test_localhost_allowed_when_no_key(self):
        with mock.patch.dict(os.environ, {"ADMIN_API_KEY": ""}, clear=False):
            os.environ.pop("ADMIN_API_KEY", None)
            rv = self.client.post(
                "/admin/update_x",
                environ_base={"REMOTE_ADDR": "127.0.0.1"},
            )
            self.assertEqual(rv.status_code, 200)

    def test_non_localhost_blocked_when_no_key(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ADMIN_API_KEY", None)
            rv = self.client.post(
                "/admin/update_x",
                environ_base={"REMOTE_ADDR": "203.0.113.10"},
            )
            self.assertEqual(rv.status_code, 403)

    def test_admin_key_required_when_set(self):
        with mock.patch.dict(os.environ, {"ADMIN_API_KEY": "secret-admin"}, clear=False):
            bad = self.client.post(
                "/admin/update_x",
                environ_base={"REMOTE_ADDR": "127.0.0.1"},
            )
            self.assertEqual(bad.status_code, 403)
            good = self.client.post(
                "/admin/update_x",
                headers={"X-Admin-Key": "secret-admin"},
                environ_base={"REMOTE_ADDR": "203.0.113.10"},
            )
            self.assertEqual(good.status_code, 200)


class ClientIpTests(unittest.TestCase):
    def test_ignores_xff_without_trust_proxy(self):
        with mock.patch.dict(os.environ, {"TRUST_PROXY": "0"}, clear=False):
            req = mock.Mock(remote_addr="10.0.0.1", headers={"X-Forwarded-For": "1.2.3.4"})
            self.assertEqual(client_ip_from_request(req), "10.0.0.1")

    def test_uses_xff_with_trust_proxy(self):
        with mock.patch.dict(os.environ, {"TRUST_PROXY": "1"}, clear=False):
            req = mock.Mock(remote_addr="10.0.0.1", headers={"X-Forwarded-For": "1.2.3.4, 10.0.0.1"})
            self.assertEqual(client_ip_from_request(req), "1.2.3.4")


if __name__ == "__main__":
    unittest.main()
