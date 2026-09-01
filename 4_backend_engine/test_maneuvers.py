"""
Synthetic fixtures for Option B maneuver speak/suppress policy.

No graph load / no map — pure decision-table tests (MANEUVER_ENGINE_SPEC §10).

  cd c:\\London_Cycle_Maps\\4_backend_engine
  python -m unittest test_maneuvers.py -v
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from maneuvers.engine import build_navigation_from_edges, decide_junctions
from maneuvers.facility import facility_class, smooth_facility_classes
from maneuvers.geometry_nav import junction_turn, signed_delta_deg
from maneuvers.naming import continuity_key, meaningful_name_change, normalize_name
from maneuvers.osrm_export import build_osrm_navigation
from maneuvers.voice import (
    build_step_voice,
    normalise_units,
    speak_distance,
    step_speed_ms,
)


# ---------------------------------------------------------------------------
# Geometry helpers — build synthetic edges as short polylines [[lat, lon], ...]
# ---------------------------------------------------------------------------

def _offset(lat: float, lon: float, north_m: float, east_m: float) -> list[float]:
    dlat = north_m / 110540.0
    dlon = east_m / (111320.0 * max(0.2, math.cos(math.radians(lat))))
    return [lat + dlat, lon + dlon]


def _edge(
    coords: list[list[float]],
    *,
    name: str | None = None,
    typ: str = "residential",
    cycleway: str | None = None,
    length: float | None = None,
    junction: str | None = None,
    street_name: str | None = None,
    junction_degree: int | None = None,
) -> dict:
    total = 0.0
    for i in range(1, len(coords)):
        # rough length — engine prefers explicit length
        a, b = coords[i - 1], coords[i]
        # haversine-ish
        from maneuvers.geometry_nav import haversine_m
        total += haversine_m(a[0], a[1], b[0], b[1])
    e = {
        "coords": coords,
        "length": float(length if length is not None else total),
        "name": name if name is not None else "",
        "type": typ,
    }
    if cycleway is not None:
        e["cycleway"] = cycleway
    if junction is not None:
        e["junction"] = junction
    if street_name is not None:
        e["street:name"] = street_name
    if junction_degree is not None:
        e["_junction_degree"] = junction_degree
    return e


def _line(lat0, lon0, bearing_cardinal: str, length_m: float, n: int = 4) -> list[list[float]]:
    """Straight polyline of length_m in N/E/S/W."""
    vec = {
        "N": (length_m, 0.0),
        "E": (0.0, length_m),
        "S": (-length_m, 0.0),
        "W": (0.0, -length_m),
    }[bearing_cardinal]
    coords = [[lat0, lon0]]
    for i in range(1, n + 1):
        frac = i / n
        coords.append(_offset(lat0, lon0, vec[0] * frac, vec[1] * frac))
    return coords


ORIG = (51.50, -0.12)


class TestGeometryLeftRight(unittest.TestCase):
    def test_east_then_north_is_left(self):
        """Travel east, then north → left turn (negative Δθ)."""
        e0 = _edge(_line(*ORIG, "E", 80), name="High St", junction_degree=3)
        # continue from end of e0 north
        end = e0["coords"][-1]
        e1 = _edge(_line(end[0], end[1], "N", 80), name="Side St", junction_degree=3)
        turn = junction_turn(e0, e1)
        self.assertLess(turn["delta_deg"], -40, turn)
        self.assertGreater(turn["delta_deg"], -140, turn)

    def test_east_then_south_is_right(self):
        e0 = _edge(_line(*ORIG, "E", 80), name="High St", junction_degree=3)
        end = e0["coords"][-1]
        e1 = _edge(_line(end[0], end[1], "S", 80), name="Side St", junction_degree=3)
        turn = junction_turn(e0, e1)
        self.assertGreater(turn["delta_deg"], 40, turn)


class TestSyntheticDecisionTable(unittest.TestCase):
    def test_l_turn_name_change_speaks(self):
        e0 = _edge(_line(*ORIG, "E", 100), name="High Holborn", junction_degree=4)
        end = e0["coords"][-1]
        e1 = _edge(_line(end[0], end[1], "N", 100), name="Drake Street", junction_degree=4)
        events = decide_junctions([e0, e1])
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0]["speak"], events[0])
        self.assertIn(events[0]["gate"], ("S7", "S8"), events[0])
        self.assertIn("left", (events[0]["modifier"] or "").lower(), events[0])
        self.assertIn("Drake", events[0]["instruction"] or "", events[0])

    def test_same_name_medium_curve_silent(self):
        """~55° bend, same street name, degree 2 → suppress (Q2)."""
        e0 = _edge(_line(*ORIG, "E", 120), name="Euston Road", junction_degree=2)
        end = e0["coords"][-1]
        # Bear north-east-ish: go N but that is 90°. For ~55° use a two-point diagonal
        # approx NE which is 45° from E... bear more north for ~55-60 from east:
        # heading after ≈ 90-55 = 35° from north = NNE. Build by going mostly N slight E.
        lat, lon = end
        coords = [[lat, lon]]
        for i in range(1, 5):
            coords.append(_offset(lat, lon, 25 * i, 15 * i))  # ~atan(15/25)≈31° from N => from E travel...
        # Wait: inbound bearing is East (~90). Outbound along (N=25,E=15) per step ≈ bearing atan2(E,N)=atan2(15,25)≈31° from north.
        # Δθ = 31 - 90 = -59 ≈ left 59° — good for Q2.
        e1 = _edge(coords, name="Euston Road", length=140, junction_degree=2)
        events = decide_junctions([e0, e1])
        self.assertFalse(events[0]["speak"], events[0])
        self.assertIn(events[0]["gate"], ("Q1", "Q2"), events[0])

    def test_facility_up_shallow_join_track_not_turn(self):
        """Carriageway → segregated cycleway, small angle → S5 facility_up."""
        e0 = _edge(
            _line(*ORIG, "E", 100),
            name="Euston Road",
            typ="primary",
            junction_degree=2,
        )
        end = e0["coords"][-1]
        # Almost straight ahead onto cycleway (tiny left)
        lat, lon = end
        coords = [[lat, lon]]
        for i in range(1, 5):
            coords.append(_offset(lat, lon, 5 * i, 30 * i))  # mostly east, slight north
        e1 = _edge(
            coords,
            name="",
            typ="cycleway",
            street_name="Euston Road",
            length=120,
            junction_degree=2,
        )
        self.assertEqual(facility_class(e0), "carriageway")
        self.assertEqual(facility_class(e1), "segregated")
        events = decide_junctions([e0, e1])
        self.assertTrue(events[0]["speak"], events[0])
        self.assertEqual(events[0]["gate"], "S5", events[0])
        self.assertEqual(events[0]["kind"], "facility_up")
        instr = (events[0]["instruction"] or "").lower()
        self.assertIn("cycle track", instr)
        self.assertNotIn("turn left", instr)
        self.assertNotIn("turn right", instr)

    def test_facility_flicker_smoothed_silent(self):
        """
        Long carriageway, one tiny cycleway-tagged middle edge, then carriageway again.
        After smooth, class is flat → no mid speaks from class change.
        """
        edges = []
        lat, lon = ORIG
        # 3 x ~50 m east carriageway
        for _ in range(3):
            coords = _line(lat, lon, "E", 50)
            edges.append(_edge(coords, name="Park Lane", typ="primary", junction_degree=2))
            lat, lon = coords[-1]
        # 1 x ~10 m flicker as cycleway
        coords = _line(lat, lon, "E", 10)
        edges.append(
            _edge(coords, name="Park Lane", typ="cycleway", length=10.0, junction_degree=2)
        )
        lat, lon = coords[-1]
        # 3 x ~50 m carriageway again
        for _ in range(3):
            coords = _line(lat, lon, "E", 50)
            edges.append(_edge(coords, name="Park Lane", typ="primary", junction_degree=2))
            lat, lon = coords[-1]

        classes = smooth_facility_classes(edges)
        # Flicker should be smoothed away to carriageway
        self.assertTrue(all(c == "carriageway" for c in classes), classes)

        events = decide_junctions(edges)
        spoken = [e for e in events if e["speak"]]
        self.assertEqual(spoken, [], spoken)

    def test_build_navigation_includes_depart_arrive(self):
        e0 = _edge(_line(*ORIG, "E", 100), name="A Street", junction_degree=4)
        end = e0["coords"][-1]
        e1 = _edge(_line(end[0], end[1], "N", 100), name="B Street", junction_degree=4)
        nav = build_navigation_from_edges([e0, e1])
        kinds = [m["kind"] for m in nav["maneuvers"]]
        self.assertEqual(kinds[0], "depart")
        self.assertEqual(kinds[-1], "arrive")
        self.assertGreaterEqual(len(nav["maneuvers"]), 3)  # depart + turn + arrive

    def test_osrm_export_has_steps_and_geometry(self):
        e0 = _edge(_line(*ORIG, "E", 100), name="A Street", junction_degree=4)
        end = e0["coords"][-1]
        e1 = _edge(_line(end[0], end[1], "N", 100), name="B Street", junction_degree=4)
        nav = build_osrm_navigation([e0, e1], duration_min=10.0)
        self.assertIn("legs", nav)
        steps = nav["legs"][0]["steps"]
        self.assertGreaterEqual(len(steps), 3)
        self.assertEqual(steps[0]["maneuver"]["type"], "depart")
        self.assertEqual(steps[-1]["maneuver"]["type"], "arrive")
        for step in steps:
            self.assertIn("geometry", step)
            self.assertIn("instruction", step["maneuver"])
        self.assertAlmostEqual(nav["duration"], 600.0, places=1)
        self.assertGreater(nav["distance"], 0)

    def test_directions_response_polyline6(self):
        from maneuvers.directions_response import to_directions_response
        from maneuvers.polyline import encode_polyline

        e0 = _edge(_line(*ORIG, "E", 100), name="A Street", junction_degree=4)
        end = e0["coords"][-1]
        e1 = _edge(_line(end[0], end[1], "N", 100), name="B Street", junction_degree=4)
        nav = build_osrm_navigation([e0, e1], duration_min=5.0)
        resp = to_directions_response(
            nav,
            origin_latlon=ORIG,
            destination_latlon=e1["coords"][-1],
        )
        self.assertEqual(resp["code"], "Ok")
        route = resp["routes"][0]
        self.assertIsInstance(route["geometry"], str)
        self.assertGreater(len(route["geometry"]), 5)
        self.assertEqual(
            route["geometry"],
            encode_polyline(nav["geometry_latlon"], precision=6),
        )
        self.assertGreaterEqual(len(route["legs"][0]["steps"]), 3)
        self.assertEqual(route["routeOptions"]["geometries"], "polyline6")
        # MapLibre kotlinx SerialName — snake_case required for voice/banner flags
        self.assertTrue(route["routeOptions"]["voice_instructions"])
        self.assertTrue(route["routeOptions"]["banner_instructions"])
        self.assertNotIn("voiceInstructions", route["routeOptions"])
        self.assertIn("access_token", route["routeOptions"])
        self.assertIn("uuid", route["routeOptions"])
        self.assertEqual(resp["routes"][0]["routeOptions"]["voice_instructions"], True)


class TestVoiceDistances(unittest.TestCase):
    def test_metric_spells_units_out(self):
        """Android TTS reads "400 m" as "four hundred em" — units must be words."""
        self.assertEqual(speak_distance(400), "400 metres")
        self.assertEqual(speak_distance(30), "30 metres")
        self.assertEqual(speak_distance(1200), "1.2 kilometres")
        self.assertEqual(speak_distance(2000), "2 kilometres")
        self.assertEqual(speak_distance(1000), "1 kilometre")

    def test_metric_rounds_to_actionable_values(self):
        self.assertEqual(speak_distance(147), "150 metres")
        self.assertEqual(speak_distance(33), "30 metres")

    def test_imperial(self):
        self.assertEqual(speak_distance(150, "imperial"), "500 feet")
        self.assertEqual(speak_distance(500, "imperial"), "0.3 miles")
        self.assertEqual(speak_distance(1609, "imperial"), "1 mile")

    def test_units_aliases(self):
        self.assertEqual(normalise_units("british_imperial"), "imperial")
        self.assertEqual(normalise_units(None), "metric")
        self.assertEqual(normalise_units("nonsense"), "metric")

    def test_step_speed_clamped(self):
        self.assertAlmostEqual(step_speed_ms(1000, 200), 5.0)
        # A duration of zero, or an absurd one, falls back instead of skewing tiers.
        self.assertAlmostEqual(step_speed_ms(1000, 0), 4.2)
        self.assertAlmostEqual(step_speed_ms(1000, 10), 8.0)
        self.assertAlmostEqual(step_speed_ms(10, 1000), 2.5)


class TestVoiceSchedule(unittest.TestCase):
    def _cues(self, **kwargs):
        kwargs.setdefault("step_duration_s", kwargs["step_distance_m"] / 4.2)
        kwargs.setdefault("target_instruction", "Turn left onto High Street")
        return build_step_voice(**kwargs)

    def test_tiers_descend_and_end_at_the_maneuver(self):
        cues = self._cues(step_distance_m=1200.0)
        distances = [c["distanceAlongGeometry"] for c in cues]
        self.assertEqual(distances, sorted(distances, reverse=True))
        self.assertEqual(distances[0], 1200.0)
        self.assertLess(distances[-1], 50.0)
        self.assertEqual(cues[-1]["announcement"], "Turn left onto High Street")

    def test_lead_in_carries_the_distance(self):
        cues = self._cues(step_distance_m=1200.0)
        texts = [c["announcement"] for c in cues]
        self.assertIn("In 400 metres, turn left onto High Street", texts)
        self.assertIn("In 150 metres, turn left onto High Street", texts)

    def test_long_step_announces_the_run(self):
        cues = self._cues(step_distance_m=1200.0)
        self.assertIn("Continue for 1.2 kilometres", cues[0]["announcement"])

    def test_short_step_collapses_to_one_cue(self):
        """No room for a lead-in, so the rider hears the turn once and only once."""
        cues = self._cues(step_distance_m=45.0)
        self.assertEqual(len(cues), 1)
        self.assertEqual(cues[0]["announcement"], "Turn left onto High Street")

    def test_gates_drop_tiers_that_would_not_fit(self):
        # 500 m clears the alert gate (150 + 100) but not prepare (400 + 250).
        texts = [c["announcement"] for c in self._cues(step_distance_m=500.0)]
        self.assertTrue(any(t.startswith("In 150 metres") for t in texts))
        self.assertFalse(any(t.startswith("In 400 metres") for t in texts))

    def test_faster_step_gets_an_earlier_lead_in(self):
        slow = self._cues(step_distance_m=1500.0, step_duration_s=1500.0 / 3.0)
        fast = self._cues(step_distance_m=1500.0, step_duration_s=1500.0 / 7.5)
        self.assertLess(
            max(c["distanceAlongGeometry"] for c in slow if c["distanceAlongGeometry"] < 900),
            max(c["distanceAlongGeometry"] for c in fast if c["distanceAlongGeometry"] < 900),
        )

    def test_depart_leads_the_first_step(self):
        cues = self._cues(
            step_distance_m=1200.0,
            depart_instruction="Head north on Coldharbour Lane",
        )
        self.assertTrue(cues[0]["announcement"].startswith("Head north on Coldharbour Lane"))

    def test_chain_and_suppression(self):
        chained = self._cues(
            step_distance_m=500.0,
            chain_instruction="Turn right onto Mill Road",
        )
        self.assertEqual(
            chained[-1]["announcement"],
            "Turn left onto High Street, then turn right onto Mill Road",
        )
        # The chained maneuver's own step must not repeat it.
        follower = build_step_voice(
            step_distance_m=60.0,
            step_duration_s=60.0 / 4.2,
            target_instruction="Turn right onto Mill Road",
            suppress_execute=True,
        )
        self.assertEqual(follower, [])

    def test_arrival_phrasing(self):
        cues = build_step_voice(
            step_distance_m=400.0,
            step_duration_s=400.0 / 4.2,
            target_instruction="You have arrived at your destination",
            is_arrival=True,
        )
        texts = [c["announcement"] for c in cues]
        self.assertIn("In 150 metres you will arrive at your destination", texts)
        self.assertEqual(texts[-1], "You have arrived at your destination")
        self.assertEqual(cues[-1]["distanceAlongGeometry"], 20.0)

    def test_spoken_distance_matches_the_trigger(self):
        """A cue firing at 200 m must not say "150 metres"; tiers sit on the speech grid."""
        for speed in (2.5, 3.0, 4.2, 5.5, 8.0):
            cues = self._cues(step_distance_m=2000.0, step_duration_s=2000.0 / speed)
            for cue in cues:
                text = cue["announcement"]
                if not text.startswith("In "):
                    continue
                self.assertTrue(
                    text.startswith(f"In {speak_distance(cue['distanceAlongGeometry'])}"),
                    f"{text!r} fires at {cue['distanceAlongGeometry']} m",
                )

    def test_ssml_is_escaped(self):
        cues = build_step_voice(
            step_distance_m=50.0,
            step_duration_s=12.0,
            target_instruction="Turn left onto Bath & Wells Road",
        )
        self.assertIn("Bath &amp; Wells Road", cues[0]["ssmlAnnouncement"])


class TestVoiceStepPairing(unittest.TestCase):
    """
    Step i's cues must name step i+1's maneuver.

    OSRM puts a maneuver at the *start* of its step, while the engine counts down the
    distance remaining on the step being ridden. Pairing index i with index i means
    announcing the turn the rider has already taken.
    """

    def _route(self):
        e0 = _edge(_line(*ORIG, "E", 900), name="High Holborn", junction_degree=4)
        end = e0["coords"][-1]
        e1 = _edge(_line(end[0], end[1], "N", 600), name="Drake Street", junction_degree=4)
        end = e1["coords"][-1]
        e2 = _edge(_line(end[0], end[1], "E", 400), name="Mill Road", junction_degree=4)
        return build_osrm_navigation([e0, e1, e2], duration_min=12.0)

    def test_cues_name_the_next_maneuver(self):
        steps = self._route()["legs"][0]["steps"]
        self.assertGreaterEqual(len(steps), 4)
        for i, step in enumerate(steps[:-1]):
            expected = steps[i + 1]["maneuver"]["instruction"]
            for cue in step.get("voiceInstructions", []):
                text = cue["announcement"].lower()
                if text.startswith("head") or text.startswith("continue for"):
                    continue  # entry cue describes the step, not the turn
                if "destination" in expected.lower():
                    self.assertIn("destination", text)
                    continue
                self.assertIn(
                    expected.lower().split(" onto ")[0],
                    text,
                    f"step {i} cue {text!r} should announce {expected!r}",
                )

    def test_banner_names_the_next_maneuver(self):
        steps = self._route()["legs"][0]["steps"]
        for i, step in enumerate(steps[:-1]):
            banner = step["bannerInstructions"][0]
            self.assertEqual(
                banner["primary"]["text"],
                steps[i + 1]["maneuver"]["instruction"],
            )
            # Shown across the whole step so the countdown has something to sit under.
            self.assertAlmostEqual(banner["distanceAlongGeometry"], step["distance"], places=1)

    def test_last_step_is_silent(self):
        steps = self._route()["legs"][0]["steps"]
        self.assertEqual(steps[-1]["maneuver"]["type"], "arrive")
        self.assertNotIn("voiceInstructions", steps[-1])
        self.assertNotIn("bannerInstructions", steps[-1])

    def test_depart_names_a_compass_direction(self):
        steps = self._route()["legs"][0]["steps"]
        self.assertEqual(steps[0]["maneuver"]["instruction"], "Head east on High Holborn")

    def test_imperial_request_reaches_the_cues(self):
        e0 = _edge(_line(*ORIG, "E", 900), name="High Holborn", junction_degree=4)
        end = e0["coords"][-1]
        e1 = _edge(_line(end[0], end[1], "N", 600), name="Drake Street", junction_degree=4)
        nav = build_osrm_navigation([e0, e1], duration_min=8.0, voice_units="imperial")
        texts = [
            cue["announcement"]
            for step in nav["legs"][0]["steps"]
            for cue in step.get("voiceInstructions", [])
        ]
        self.assertTrue(any("miles" in t or "feet" in t for t in texts), texts)
        self.assertFalse(any("metres" in t for t in texts), texts)


class TestNamingHelpers(unittest.TestCase):
    def test_normalize_rejects_nan(self):
        self.assertIsNone(normalize_name("nan"))
        self.assertIsNone(normalize_name("None"))

    def test_meaningful_name_change(self):
        self.assertTrue(meaningful_name_change("High St", "Drake St"))
        self.assertFalse(meaningful_name_change("High St", "high st"))
        self.assertFalse(meaningful_name_change(None, None))


if __name__ == "__main__":
    unittest.main()
