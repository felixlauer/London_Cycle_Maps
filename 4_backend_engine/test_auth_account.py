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

    def test_normalize_display_name(self):
        self.assertEqual(auth_admin.normalize_display_name("  Ada  "), ("Ada", None))
        self.assertEqual(auth_admin.normalize_display_name(""), (None, None))
        self.assertEqual(auth_admin.normalize_display_name("   "), (None, None))
        too_long = "x" * (auth_admin.MAX_DISPLAY_NAME_LEN + 1)
        name, err = auth_admin.normalize_display_name(too_long)
        self.assertIsNone(name)
        self.assertIn("at most", err)

    def test_session_dict_includes_display_name(self):
        session = {
            "access_token": "a",
            "refresh_token": "r",
            "expires_at": 1,
            "expires_in": 2,
            "user": {
                "id": "uid",
                "email": "a@b.com",
                "user_metadata": {"display_name": "Ada"},
            },
        }
        payload = auth_admin._session_dict(session)
        self.assertEqual(payload["user"]["display_name"], "Ada")

    def test_session_dict_missing_display_name_is_none(self):
        session = {
            "access_token": "a",
            "refresh_token": "r",
            "user": {"id": "uid", "email": "a@b.com", "user_metadata": {}},
        }
        payload = auth_admin._session_dict(session)
        self.assertIsNone(payload["user"]["display_name"])

    def test_sign_up_passes_display_name_metadata(self):
        client = MagicMock()
        user = {"id": "uid", "email": "a@b.com", "user_metadata": {"display_name": "Ada"}}
        resp = MagicMock(session={"access_token": "a", "refresh_token": "r", "user": user}, user=user, error=None)
        client.auth.sign_up.return_value = resp
        with patch.object(auth_admin, "_anon_client", return_value=client):
            payload, err, needs = auth_admin.sign_up("a@b.com", "secret1", "Ada")
        self.assertIsNone(err)
        self.assertFalse(needs)
        self.assertEqual(payload["user"]["display_name"], "Ada")
        kwargs = client.auth.sign_up.call_args[0][0]
        self.assertEqual(kwargs["options"]["data"]["display_name"], "Ada")

    def test_sign_up_omits_metadata_when_name_empty(self):
        client = MagicMock()
        user = {"id": "uid", "email": "a@b.com", "user_metadata": {}}
        resp = MagicMock(session={"access_token": "a", "refresh_token": "r", "user": user}, user=user, error=None)
        client.auth.sign_up.return_value = resp
        with patch.object(auth_admin, "_anon_client", return_value=client):
            payload, err, needs = auth_admin.sign_up("a@b.com", "secret1", "")
        self.assertIsNone(err)
        self.assertFalse(needs)
        self.assertIsNone(payload["user"]["display_name"])
        kwargs = client.auth.sign_up.call_args[0][0]
        self.assertNotIn("options", kwargs)

    def test_update_display_name_calls_admin(self):
        client = MagicMock()
        with patch.object(auth_admin, "_service_client", return_value=client):
            name, err = auth_admin.update_display_name("uid-1", "  Ada  ")
        self.assertIsNone(err)
        self.assertEqual(name, "Ada")
        client.auth.admin.update_user_by_id.assert_called_once_with(
            "uid-1",
            {"user_metadata": {"display_name": "Ada"}},
        )

    def test_update_display_name_can_clear(self):
        client = MagicMock()
        with patch.object(auth_admin, "_service_client", return_value=client):
            name, err = auth_admin.update_display_name("uid-1", "  ")
        self.assertIsNone(err)
        self.assertIsNone(name)
        client.auth.admin.update_user_by_id.assert_called_once_with(
            "uid-1",
            {"user_metadata": {"display_name": ""}},
        )


if __name__ == "__main__":
    unittest.main()
