"""Tests for auth_admin helpers (no Flask / graph import)."""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(__file__))

import auth_admin


class AuthAdminTests(unittest.TestCase):
    def test_user_exists_by_email_rpc_bool(self):
        client = MagicMock()
        client.rpc.return_value.execute.return_value = MagicMock(data=True)
        with patch.object(auth_admin, "_service", client):
            self.assertTrue(auth_admin.user_exists_by_email("a@b.com"))

    def test_user_exists_by_email_list_direct(self):
        """supabase-py list_users returns list[User], not a wrapper with .users."""
        client = MagicMock()
        client.rpc.side_effect = Exception("no rpc")
        user = MagicMock(email="User@Example.com")
        client.auth.admin.list_users.return_value = [user]
        with patch.object(auth_admin, "_service", None):
            with patch.object(auth_admin, "_service_client", return_value=client):
                self.assertTrue(auth_admin.user_exists_by_email("user@example.com"))

    def test_user_exists_by_email_not_found(self):
        client = MagicMock()
        client.rpc.side_effect = Exception("no rpc")
        client.auth.admin.list_users.return_value = []
        with patch.object(auth_admin, "_service", None):
            with patch.object(auth_admin, "_service_client", return_value=client):
                self.assertFalse(auth_admin.user_exists_by_email("missing@b.com"))

    def test_delete_user_calls_admin(self):
        client = MagicMock()
        with patch.object(auth_admin, "_service_client", return_value=client):
            auth_admin.delete_user("uid-1")
        client.auth.admin.delete_user.assert_called_once_with("uid-1")


if __name__ == "__main__":
    unittest.main()
