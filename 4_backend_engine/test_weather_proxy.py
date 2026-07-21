"""Unit tests for weather_proxy helpers."""
from datetime import datetime, timezone

import weather_proxy as wp


def test_parse_at_zulu():
    dt = wp._parse_at("2026-07-20T14:30:00Z")
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.hour == 14
    assert dt.minute == 30


def test_nearest_hourly_index():
    times = [
        "2026-07-20T12:00",
        "2026-07-20T13:00",
        "2026-07-20T14:00",
    ]
    # 13:40 → closer to 14:00 (20 min) than 13:00 (40 min)
    target = datetime(2026, 7, 20, 13, 40, tzinfo=timezone.utc)
    assert wp._nearest_hourly_index(times, target) == 2


def test_nearest_hourly_prefers_closer():
    times = [
        "2026-07-20T12:00",
        "2026-07-20T13:00",
        "2026-07-20T14:00",
    ]
    target = datetime(2026, 7, 20, 13, 10, tzinfo=timezone.utc)
    assert wp._nearest_hourly_index(times, target) == 1


def test_cache_key_rounds():
    a = wp._cache_key(51.507351, -0.127758, "current")
    b = wp._cache_key(51.507399, -0.127701, "current")
    assert a == b


def test_test_mode_scenario_stable_within_minute(monkeypatch):
    monkeypatch.setenv("WEATHER_TEST_MODE", "1")
    monkeypatch.setattr(wp.time, "time", lambda: 1_700_000_000.0)
    wp._TEST_SLOT = None
    wp._TEST_SCENARIO_ID = None
    a = wp.fetch_weather(51.5, -0.12)
    b = wp.fetch_weather(51.5, -0.12)
    assert a["weather_test"] is True
    assert a["weather_test_scenario"] == b["weather_test_scenario"]


def test_test_mode_scenario_changes_next_minute(monkeypatch):
    monkeypatch.setenv("WEATHER_TEST_MODE", "1")
    seen = set()
    for minute in range(120):
        monkeypatch.setattr(wp.time, "time", lambda m=minute: m * 60.0)
        wp._TEST_SLOT = None
        wp._TEST_SCENARIO_ID = None
        payload = wp.fetch_weather(51.5, -0.12)
        seen.add(payload["weather_test_scenario"])
    assert len(seen) > 1


def test_test_mode_skips_open_meteo(monkeypatch):
    monkeypatch.setenv("WEATHER_TEST_MODE", "1")
    monkeypatch.setattr(wp.time, "time", lambda: 1_700_000_060.0)
    wp._TEST_SLOT = None
    wp._TEST_SCENARIO_ID = None

    def boom(*_a, **_k):
        raise AssertionError("Open-Meteo should not be called in test mode")

    monkeypatch.setattr(wp.urllib.request, "urlopen", boom)
    payload = wp.fetch_weather(51.5, -0.12)
    assert payload["weather_test_scenario"] in {s["id"] for s in wp.EXTREME_TEST_SCENARIOS}
