"""
Access-rule tests for the Supabase integration (no graph or Flask app load).

Covers: LocalJsonStore CRUD, SupabaseStore tenancy (user A cannot read user B;
regression check that every user-row query carries .eq('user_id', ...)),
create_profile sanitization (is_system / user_id hardcoded server-side), guest
access to custom profiles, and the test-mode localhost gate.

Run from 4_backend_engine:
  python -m unittest test_profile_store -v
"""
import os
import tempfile
import unittest
import uuid
from unittest import mock

import auth_middleware
import user_profiles
from profile_store import LocalJsonStore, SupabaseStore

VALID_WEIGHTS = {k: 0.5 for k in user_profiles.ROUTING_WEIGHT_KEYS}

USER_A = str(uuid.uuid4())
USER_B = str(uuid.uuid4())
PROFILE_A = str(uuid.uuid4())
PROFILE_B = str(uuid.uuid4())


def _row(profile_id, user_id, name, is_system=False, slug=None):
    return {
        "id": profile_id,
        "slug": slug,
        "user_id": user_id,
        "name": name,
        "preset": None,
        "bike_type": "standard",
        "toggles": {},
        "weights": dict(VALID_WEIGHTS),
        "is_system": is_system,
    }


FIXTURE_ROWS = [
    _row(str(uuid.uuid4()), None, "Fast", is_system=True, slug="preset_fast"),
    _row(PROFILE_A, USER_A, "A custom"),
    _row(PROFILE_B, USER_B, "B custom"),
]


class FakeQuery:
    """Mimics the supabase-py query builder; records .eq() filters."""

    def __init__(self, rows, log):
        self._rows = rows
        self._log = log
        self.filters = []
        self.inserted = None

    def select(self, _cols):
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def insert(self, row):
        self.inserted = row
        return self

    def upsert(self, rows, **_kw):
        self.inserted = rows
        return self

    def execute(self):
        self._log.append(self)
        if self.inserted is not None:
            # Real Supabase returns the row with generated defaults (id, ...).
            data = [self.inserted] if isinstance(self.inserted, dict) else self.inserted
            data = [{"id": r.get("id", str(uuid.uuid4())), **r} for r in data]
            return mock.Mock(data=data)
        data = [
            r for r in self._rows
            if all(r.get(col) == val for col, val in self.filters)
        ]
        return mock.Mock(data=data)


class FakeClient:
    def __init__(self, rows):
        self._rows = rows
        self.queries = []

    def table(self, _name):
        return FakeQuery(self._rows, self.queries)


class LocalJsonStoreTest(unittest.TestCase):
    """CRUD against a temp JSON file; user_id is ignored (local dev store)."""

    def setUp(self):
        fd, self._tmp = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self._tmp)  # start from "no file" state
        self._orig_path = user_profiles._PROFILES_PATH
        user_profiles._PROFILES_PATH = self._tmp
        self.store = LocalJsonStore()

    def tearDown(self):
        user_profiles._PROFILES_PATH = self._orig_path
        if os.path.isfile(self._tmp):
            os.remove(self._tmp)

    def test_create_and_get_roundtrip(self):
        profile, err = self.store.create_profile(None, "My ride", VALID_WEIGHTS)
        self.assertIsNone(err)
        fetched = self.store.get_profile(profile["id"], user_id=None)
        self.assertEqual(fetched["name"], "My ride")
        self.assertEqual(fetched["weights"], VALID_WEIGHTS)

    def test_list_contains_created(self):
        self.store.create_profile(None, "My ride", VALID_WEIGHTS)
        ids = [p["id"] for p in self.store.list_profiles(user_id=None)]
        self.assertIn("my_ride", ids)

    def test_invalid_weights_rejected(self):
        bad = dict(VALID_WEIGHTS, risk_weight=99.0)
        profile, err = self.store.create_profile(None, "Bad", bad)
        self.assertIsNone(profile)
        self.assertIsNotNone(err)


class SupabaseStoreTenancyTest(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient(FIXTURE_ROWS)
        self.store = SupabaseStore(client=self.client)

    def test_user_a_cannot_get_user_b_profile(self):
        self.assertIsNone(self.store.get_profile(PROFILE_B, user_id=USER_A))

    def test_user_a_gets_own_profile(self):
        profile = self.store.get_profile(PROFILE_A, user_id=USER_A)
        self.assertIsNotNone(profile)
        self.assertEqual(profile["name"], "A custom")

    def test_guest_cannot_get_custom_profile(self):
        self.assertIsNone(self.store.get_profile(PROFILE_A, user_id=None))

    def test_guest_gets_system_preset_by_slug(self):
        profile = self.store.get_profile("preset_fast", user_id=None)
        self.assertIsNotNone(profile)
        self.assertTrue(profile["is_system"])
        # System rows expose the slug as their id (frontend localStorage ids).
        self.assertEqual(profile["id"], "preset_fast")

    def test_list_never_returns_other_users_rows(self):
        names = {p["name"] for p in self.store.list_profiles(user_id=USER_A)}
        self.assertIn("A custom", names)
        self.assertIn("Fast", names)
        self.assertNotIn("B custom", names)

    def test_guest_list_is_system_only(self):
        rows = self.store.list_profiles(user_id=None)
        self.assertTrue(all(p["is_system"] for p in rows))

    def test_user_row_queries_always_filter_user_id(self):
        """Regression: service role bypasses RLS, so every non-system query
        MUST carry an explicit ('user_id', <uid>) filter."""
        self.client.queries.clear()
        self.store.get_profile(PROFILE_A, user_id=USER_A)
        self.store.list_profiles(user_id=USER_A)
        user_row_queries = [
            q for q in self.client.queries
            if ("is_system", True) not in q.filters and q.inserted is None
        ]
        self.assertTrue(user_row_queries)
        for q in user_row_queries:
            self.assertIn(("user_id", USER_A), q.filters,
                          f"user-row query missing user_id filter: {q.filters}")


class CreateProfileSanitizationTest(unittest.TestCase):
    """POST /profiles path: is_system and user_id are function arguments set by
    Flask (g.user_id / hardcoded False) — the insert must reflect them
    regardless of anything the client sent in the JSON body."""

    def setUp(self):
        self.client = FakeClient(FIXTURE_ROWS)
        self.store = SupabaseStore(client=self.client)

    def test_insert_hardcodes_ownership_fields(self):
        profile, err = self.store.create_profile(USER_A, "New", VALID_WEIGHTS)
        self.assertIsNone(err)
        inserted = next(q.inserted for q in self.client.queries if q.inserted)
        self.assertEqual(inserted["user_id"], USER_A)
        self.assertIs(inserted["is_system"], False)
        self.assertNotIn("id", inserted)
        self.assertNotIn("slug", inserted)

    def test_endpoint_whitelist_drops_privileged_fields(self):
        # Same whitelist as app.py ALLOWED_CREATE_FIELDS.
        allowed = {"name", "weights", "bike_type", "preset", "toggles"}
        malicious = {
            "name": "Evil", "weights": VALID_WEIGHTS,
            "is_system": True, "user_id": USER_B, "id": PROFILE_B, "slug": "preset_fast",
        }
        body = {k: v for k, v in malicious.items() if k in allowed}
        self.assertEqual(set(body), {"name", "weights"})

    def test_guest_create_rejected(self):
        profile, err = self.store.create_profile(None, "Nope", VALID_WEIGHTS)
        self.assertIsNone(profile)
        self.assertEqual(err, "authentication required")


class FakeRequest:
    def __init__(self, headers=None, remote_addr="127.0.0.1"):
        self.headers = headers or {}
        self.remote_addr = remote_addr


class TestModeGateTest(unittest.TestCase):
    def _req(self, header="1", addr="127.0.0.1"):
        return FakeRequest(headers={"X-Tuned-Test-Mode": header}, remote_addr=addr)

    def test_allowed_only_on_localhost_with_env_and_header(self):
        with mock.patch.dict(os.environ, {"ALLOW_TEST_MODE": "1"}):
            self.assertTrue(auth_middleware.is_test_mode_allowed(self._req()))
            self.assertTrue(auth_middleware.is_test_mode_allowed(self._req(addr="::1")))

    def test_rejected_from_non_localhost_even_with_env(self):
        with mock.patch.dict(os.environ, {"ALLOW_TEST_MODE": "1"}):
            self.assertFalse(
                auth_middleware.is_test_mode_allowed(self._req(addr="203.0.113.7"))
            )

    def test_rejected_without_env_opt_in(self):
        with mock.patch.dict(os.environ, {"ALLOW_TEST_MODE": "0"}):
            self.assertFalse(auth_middleware.is_test_mode_allowed(self._req()))

    def test_rejected_without_header(self):
        with mock.patch.dict(os.environ, {"ALLOW_TEST_MODE": "1"}):
            req = FakeRequest(headers={}, remote_addr="127.0.0.1")
            self.assertFalse(auth_middleware.is_test_mode_allowed(req))


class JwtVerifyTest(unittest.TestCase):
    def setUp(self):
        try:
            import jwt  # noqa: F401
        except ImportError:
            self.skipTest("PyJWT not installed")

    def test_valid_token_returns_sub(self):
        import jwt as pyjwt

        secret = "test-secret"
        token = pyjwt.encode(
            {"sub": USER_A, "aud": "authenticated", "exp": 4102444800},
            secret, algorithm="HS256",
        )
        with mock.patch.dict(os.environ, {"SUPABASE_JWT_SECRET": secret}):
            self.assertEqual(auth_middleware.verify_supabase_jwt(token), USER_A)

    def test_wrong_secret_rejected(self):
        import jwt as pyjwt

        token = pyjwt.encode(
            {"sub": USER_A, "aud": "authenticated", "exp": 4102444800},
            "other-secret", algorithm="HS256",
        )
        with mock.patch.dict(os.environ, {"SUPABASE_JWT_SECRET": "test-secret"}):
            self.assertIsNone(auth_middleware.verify_supabase_jwt(token))


if __name__ == "__main__":
    unittest.main()
