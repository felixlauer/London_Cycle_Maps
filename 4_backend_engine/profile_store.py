"""
Repository layer for routing profiles: LocalJsonStore (user_profiles.json) and
SupabaseStore (profiles table via service role).

SECURITY — SupabaseStore uses the SERVICE ROLE key, which bypasses RLS.
Tenancy MUST therefore be enforced here at the application layer: every query
touching user-owned rows includes .eq("user_id", user_id). System presets
(is_system = true) use a separate code path filtered on .eq("is_system", True).
user_id and is_system are function arguments only — never read from request
payloads.

Store selection (get_store): PROFILE_STORE env = auto | local | supabase.
"auto" picks Supabase when SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY are set,
else falls back to local JSON for dev.

When changing schema or API, update 0_documentation/APP_MAIN.md.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any

import user_profiles

# Slugs of the seed presets; kept stable so frontend localStorage ids work.
SYSTEM_SLUGS = ("preset_fast", "preset_safe", "preset_leisure")

_PROFILE_COLUMNS = "id, slug, user_id, name, preset, bike_type, toggles, weights, is_system"


class ProfileStore(ABC):
    """CRUD for routing profiles. user_id comes from the verified JWT (or None)."""

    @abstractmethod
    def list_profiles(self, user_id: str | None) -> list[dict[str, Any]]:
        """System presets plus (when user_id) the user's own profiles."""

    @abstractmethod
    def get_profile(self, profile_id: str, user_id: str | None) -> dict[str, Any] | None:
        """Single profile if it is a system preset or owned by user_id."""

    @abstractmethod
    def create_profile(
        self,
        user_id: str | None,
        name: str,
        weights: dict,
        bike_type: str | None = None,
        preset: str | None = None,
        toggles: dict | None = None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Create a non-system profile owned by user_id. Returns (profile, error)."""


class LocalJsonStore(ProfileStore):
    """Dev / test-mode store backed by user_profiles.json. No ownership checks —
    every profile in the file is visible (single-operator local file)."""

    def list_profiles(self, user_id: str | None) -> list[dict[str, Any]]:
        return user_profiles.list_profiles()

    def get_profile(self, profile_id: str, user_id: str | None) -> dict[str, Any] | None:
        return user_profiles.get_profile(profile_id)

    def create_profile(
        self,
        user_id: str | None,
        name: str,
        weights: dict,
        bike_type: str | None = None,
        preset: str | None = None,
        toggles: dict | None = None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        return user_profiles.create_profile(
            name, weights, bike_type=bike_type, preset=preset, toggles=toggles
        )


def _row_to_profile(row: dict) -> dict[str, Any]:
    """Supabase row -> API profile dict. System rows expose slug as their id so
    the frontend's stored ids (preset_fast, ...) stay valid."""
    profile_id = row.get("slug") if row.get("is_system") and row.get("slug") else row["id"]
    return {
        "id": profile_id,
        "name": row.get("name", profile_id),
        "preset": row.get("preset"),
        "bike_type": user_profiles._normalize_bike_type(row.get("bike_type")),
        "toggles": user_profiles._normalize_toggles(row.get("toggles")),
        "weights": user_profiles.clamp_weights(row.get("weights") or {}),
        "is_system": bool(row.get("is_system")),
    }


class SupabaseStore(ProfileStore):
    """Production store. Uses the service role client — RLS is bypassed, so every
    user-row query below MUST carry .eq('user_id', user_id)."""

    def __init__(self, client=None):
        if client is None:
            from supabase import create_client

            url = os.environ.get("SUPABASE_URL", "")
            key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            if not url or not key:
                raise RuntimeError(
                    "SupabaseStore requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY"
                )
            client = create_client(url, key)
        self._client = client

    def list_profiles(self, user_id: str | None) -> list[dict[str, Any]]:
        rows = (
            self._client.table("profiles")
            .select(_PROFILE_COLUMNS)
            .eq("is_system", True)
            .execute()
            .data
            or []
        )
        if user_id:
            own = (
                self._client.table("profiles")
                .select(_PROFILE_COLUMNS)
                .eq("user_id", user_id)  # tenancy filter — required (service role)
                .execute()
                .data
                or []
            )
            rows = rows + own
        return [
            {
                "id": p["id"],
                "name": p["name"],
                "preset": p["preset"],
                "bike_type": p["bike_type"],
                "is_system": p["is_system"],
            }
            for p in (_row_to_profile(r) for r in rows)
        ]

    def get_profile(self, profile_id: str, user_id: str | None) -> dict[str, Any] | None:
        # System preset by slug (preset_fast, ...) — no ownership needed.
        rows = (
            self._client.table("profiles")
            .select(_PROFILE_COLUMNS)
            .eq("is_system", True)
            .eq("slug", profile_id)
            .execute()
            .data
            or []
        )
        if rows:
            return _row_to_profile(rows[0])

        if not _looks_like_uuid(profile_id):
            return None

        # System preset addressed by uuid.
        rows = (
            self._client.table("profiles")
            .select(_PROFILE_COLUMNS)
            .eq("is_system", True)
            .eq("id", profile_id)
            .execute()
            .data
            or []
        )
        if rows:
            return _row_to_profile(rows[0])

        # User-owned row — MUST filter by user_id (service role bypasses RLS).
        if user_id is None:
            return None
        rows = (
            self._client.table("profiles")
            .select(_PROFILE_COLUMNS)
            .eq("id", profile_id)
            .eq("user_id", user_id)  # tenancy filter — required (service role)
            .execute()
            .data
            or []
        )
        return _row_to_profile(rows[0]) if rows else None

    def create_profile(
        self,
        user_id: str | None,
        name: str,
        weights: dict,
        bike_type: str | None = None,
        preset: str | None = None,
        toggles: dict | None = None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        if not user_id:
            return None, "authentication required"
        name = (name or "").strip()
        if not name:
            return None, "name is required"
        ok, err = user_profiles.validate_weights(weights)
        if not ok:
            return None, err

        insert = {
            # user_id / is_system are hardcoded here — never from client payload.
            "user_id": user_id,
            "is_system": False,
            "name": name,
            "preset": (str(preset).strip().lower() or None) if preset else None,
            "bike_type": user_profiles._normalize_bike_type(bike_type),
            "toggles": user_profiles._normalize_toggles(toggles),
            "weights": {k: float(weights[k]) for k in user_profiles.ROUTING_WEIGHT_KEYS},
        }
        rows = self._client.table("profiles").insert(insert).execute().data or []
        if not rows:
            return None, "insert failed"
        return _row_to_profile(rows[0]), None


def _looks_like_uuid(value: str) -> bool:
    import uuid

    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def supabase_configured() -> bool:
    return bool(
        os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    )


_local_store: LocalJsonStore | None = None
_supabase_store: SupabaseStore | None = None


def get_local_store() -> LocalJsonStore:
    global _local_store
    if _local_store is None:
        _local_store = LocalJsonStore()
    return _local_store


def get_store() -> ProfileStore:
    """Store per PROFILE_STORE env: auto (default) | local | supabase."""
    global _supabase_store
    mode = os.environ.get("PROFILE_STORE", "auto").strip().lower()
    if mode == "local":
        return get_local_store()
    if mode == "supabase" or (mode == "auto" and supabase_configured()):
        if _supabase_store is None:
            _supabase_store = SupabaseStore()
        return _supabase_store
    return get_local_store()
