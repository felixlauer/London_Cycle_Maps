"""Tunable constants for the Option B maneuver engine (MANEUVER_ENGINE_SPEC §7)."""

# Bearing arms / angle buckets
ARM_M = 12.0
STRAIGHT_DEG = 20.0
NAME_CHANGE_DEG = 15.0
TURN_SPEAK_DEG = 45.0
UTURN_DEG = 160.0
MEDIUM_BEND_SUPPRESS_DEG = 70.0

# Anti-spam / noise
# Q3/Q4 disabled in speak_policy for v1 (recall-first). Kept here for later:
# - MIN_SPEAK_GAP_M → voice-only spacing (Q4-B) without dropping steps
# - MIN_EDGE_SPEAK_M → softened micro-edge rule after audit
MIN_EDGE_SPEAK_M = 8.0
MIN_SPEAK_GAP_M = 25.0
UTURN_ARTEFACT_M = 25.0
SMOOTH_WINDOW_M = 40.0

# Voice announcement schedule (see maneuvers/voice.py).
# Tier distances are seconds-of-travel converted with the step's own speed, so a
# 15 km/h cycleway and a 30 km/h descent get different lead-ins.
VOICE_SPEED_MIN_MS = 2.5
VOICE_SPEED_MAX_MS = 8.0
VOICE_SPEED_DEFAULT_MS = 4.2

# "Continue for 1.2 kilometres" on entering a long step.
VOICE_CONTINUE_MIN_M = 800.0

# Far cue: "In 400 metres, turn left onto High Street".
VOICE_PREPARE_SECONDS = 90.0
VOICE_PREPARE_MIN_M = 300.0
VOICE_PREPARE_MAX_M = 800.0
VOICE_PREPARE_HEADROOM_M = 250.0

# Approach cue: "In 150 metres, turn left onto High Street". Bounds sit on the 50 m
# grid that speech rounds to, so the number spoken is the distance it fires at.
VOICE_ALERT_SECONDS = 35.0
VOICE_ALERT_MIN_M = 150.0
VOICE_ALERT_MAX_M = 250.0
VOICE_ALERT_HEADROOM_M = 100.0

# Final cue at the maneuver itself.
VOICE_EXECUTE_SECONDS = 7.0
VOICE_EXECUTE_MIN_M = 20.0
VOICE_EXECUTE_MAX_M = 45.0
VOICE_ARRIVE_EXECUTE_M = 20.0

# Two maneuvers closer than this are spoken as one chained cue.
VOICE_CHAIN_M = 120.0
# Tiers closer together than this collapse to the lower one.
VOICE_TIER_MIN_GAP_M = 60.0
