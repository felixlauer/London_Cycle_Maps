"""
Voice announcement schedule for the maneuver engine.

Each step carries a descending list of ``voiceInstructions``. MapLibre's
``VoiceInstructionMilestone`` speaks an entry once the distance remaining to the
end of the step drops below its ``distanceAlongGeometry``, so a step gets a
sequence of cues rather than a single one:

    entry (step length)  "Continue for 1.2 kilometres"
    prepare (~400 m)     "In 400 metres, turn left onto High Street"
    alert   (~150 m)     "In 150 metres, turn left onto High Street"
    execute (~30 m)      "Turn left onto High Street"

The maneuver announced on step ``i`` is the one that *ends* step ``i``, i.e. the
maneuver of step ``i + 1`` (OSRM convention). Two maneuvers closer together than
``VOICE_CHAIN_M`` are chained into one cue and the second step's execute cue is
dropped, matching Valhalla's ``verbal_multi_cue``.

Spoken distances spell their units out ("400 metres", not "400 m") because
Android TextToSpeech reads a bare "m" as the letter.
"""
from __future__ import annotations

from typing import Any

from . import constants as C

METRIC = "metric"
IMPERIAL = "imperial"

_FEET_PER_M = 1.0 / 0.3048
_M_PER_MILE = 1609.344
# Below this, imperial speaks feet rather than a fraction of a mile.
_IMPERIAL_FEET_MAX_M = 0.1 * _M_PER_MILE


def normalise_units(value: str | None) -> str:
    """Map a request parameter onto ``metric`` / ``imperial`` (Mapbox aliases included)."""
    raw = (value or "").strip().lower()
    if raw in ("imperial", "british_imperial", "british-imperial", "us", "mi", "ft"):
        return IMPERIAL
    return METRIC


def step_speed_ms(distance_m: float, duration_s: float) -> float:
    """Effective speed for one step, clamped so a bad duration cannot skew the cues."""
    try:
        d = float(distance_m)
        t = float(duration_s)
    except (TypeError, ValueError):
        return C.VOICE_SPEED_DEFAULT_MS
    if d <= 0.0 or t <= 0.0:
        return C.VOICE_SPEED_DEFAULT_MS
    return _clamp(d / t, C.VOICE_SPEED_MIN_MS, C.VOICE_SPEED_MAX_MS)


def speak_distance(metres: float, units: str = METRIC) -> str:
    """Distance as a speech-ready phrase, rounded to values a rider can act on."""
    m = max(0.0, float(metres or 0.0))
    if normalise_units(units) == IMPERIAL:
        if m < _IMPERIAL_FEET_MAX_M:
            raw_feet = m * _FEET_PER_M
            # Round to values a rider can judge: 10 ft steps up close, 50 ft beyond.
            step = 10.0 if raw_feet < 100.0 else 50.0
            feet = max(10, int(round(raw_feet / step) * step))
            return f"{feet} {'foot' if feet == 1 else 'feet'}"
        miles = m / _M_PER_MILE
        return f"{_trim(miles)} {'mile' if _is_one(miles) else 'miles'}"
    if m < 1000.0:
        if m < 100.0:
            whole = max(10, int(round(m / 10.0) * 10))
        else:
            whole = int(round(m / 50.0) * 50)
        return f"{whole} {'metre' if whole == 1 else 'metres'}"
    km = m / 1000.0
    return f"{_trim(km)} {'kilometre' if _is_one(km) else 'kilometres'}"


def build_step_voice(
    *,
    step_distance_m: float,
    step_duration_s: float,
    target_instruction: str,
    is_arrival: bool = False,
    depart_instruction: str | None = None,
    chain_instruction: str | None = None,
    suppress_execute: bool = False,
    units: str = METRIC,
) -> list[dict[str, Any]]:
    """
    Build the descending ``voiceInstructions`` array for one step.

    ``target_instruction`` is the maneuver at the end of this step.
    ``chain_instruction`` is the maneuver after that, when it sits within
    ``VOICE_CHAIN_M`` and should share this cue.
    ``suppress_execute`` drops the final cue because the previous step already
    chained this maneuver.
    """
    units = normalise_units(units)
    target = (target_instruction or "").strip()
    if not target:
        return []

    dist = max(0.0, float(step_distance_m or 0.0))
    speed = step_speed_ms(dist, step_duration_s)

    # Built low-to-high so the execute cue always survives the gap filter.
    tiers: list[tuple[float, str]] = []

    if not suppress_execute:
        if is_arrival:
            execute_at = C.VOICE_ARRIVE_EXECUTE_M
        else:
            execute_at = _clamp(
                speed * C.VOICE_EXECUTE_SECONDS,
                C.VOICE_EXECUTE_MIN_M,
                C.VOICE_EXECUTE_MAX_M,
            )
        text = target
        if chain_instruction:
            text = f"{target}, then {_decapitalise(chain_instruction)}"
        tiers.append((round(execute_at, 1), text))

    alert_at = _round_to(
        _clamp(speed * C.VOICE_ALERT_SECONDS, C.VOICE_ALERT_MIN_M, C.VOICE_ALERT_MAX_M),
        50.0,
    )
    if dist >= alert_at + C.VOICE_ALERT_HEADROOM_M:
        _add_tier(tiers, alert_at, _lead_in(alert_at, target, is_arrival, units))

    prepare_at = _round_to(
        _clamp(
            speed * C.VOICE_PREPARE_SECONDS,
            C.VOICE_PREPARE_MIN_M,
            C.VOICE_PREPARE_MAX_M,
        ),
        100.0,
    )
    if dist >= prepare_at + C.VOICE_PREPARE_HEADROOM_M:
        _add_tier(tiers, prepare_at, _lead_in(prepare_at, target, is_arrival, units))

    entry = _entry_text(dist, depart_instruction, units)
    if entry:
        _add_tier(tiers, dist, entry)

    tiers.reverse()
    return [
        {
            "distanceAlongGeometry": at,
            "announcement": text,
            "ssmlAnnouncement": f"<speak>{_escape(text)}</speak>",
        }
        for at, text in tiers
    ]


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------

def _entry_text(
    step_distance_m: float,
    depart_instruction: str | None,
    units: str,
) -> str | None:
    """Cue spoken on entering the step: departure and/or a long straight run."""
    depart = (depart_instruction or "").strip()
    long_run = step_distance_m >= C.VOICE_CONTINUE_MIN_M
    if depart and long_run:
        return f"{depart}, then continue for {speak_distance(step_distance_m, units)}"
    if depart:
        return depart
    if long_run:
        return f"Continue for {speak_distance(step_distance_m, units)}"
    return None


def _lead_in(at_m: float, target: str, is_arrival: bool, units: str) -> str:
    distance = speak_distance(at_m, units)
    if is_arrival:
        return f"In {distance} you will arrive at your destination"
    return f"In {distance}, {_decapitalise(target)}"


def _add_tier(tiers: list[tuple[float, str]], at: float, text: str) -> None:
    """Append a higher tier only when it is far enough above the last one kept."""
    if tiers and at - tiers[-1][0] < C.VOICE_TIER_MIN_GAP_M:
        return
    tiers.append((round(at, 1), text))


def _decapitalise(text: str) -> str:
    """Lowercase a leading verb so it can follow "In 400 metres, ..." naturally."""
    clean = (text or "").strip()
    if not clean:
        return clean
    head = clean.split(" ", 1)[0]
    # Leave acronyms and proper nouns alone ("A24", "St Paul's").
    if head.isupper() or any(ch.isupper() for ch in head[1:]):
        return clean
    return clean[0].lower() + clean[1:]


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _round_to(value: float, step: float) -> float:
    return round(value / step) * step


def _trim(value: float) -> str:
    """One decimal, without a trailing ".0" the synthesiser would read aloud."""
    text = f"{value:.1f}"
    return text[:-2] if text.endswith(".0") else text


def _is_one(value: float) -> bool:
    return abs(value - 1.0) < 0.05


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
