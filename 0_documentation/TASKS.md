# London Cycle Maps — Task List

Prioritised list of work items. **Keep this file up to date:** when you complete, add, or deprioritise tasks, update the list and move items between sections as needed.

---

## How to maintain this list

- **Done:** Move completed items to the "Completed" section (with optional one-line note), or remove them.
- **New work:** Add under "To do" or "In progress" with a short, actionable line.
- **Order:** Keep "In progress" for what you’re doing now; order "To do" by priority (top = next).
- **Scope:** One line per task; add a sub-bullet only if a task has a clear, fixed subtask.

---

## In progress

*(Nothing currently in progress.)*

---

## To do

- [ ] **TfL disruptions: too many roads selected** — For line/polygon disruptions, matching currently selects too many edges; tighten alignment/buffer or filters. See Development_Protocol_2026-03-01 §8.1.
- [ ] **TfL disruptions: motorway vs pedestrian/cycle logic** — Work out road-type-aware matching (e.g. exclude motorway, prioritise cycle/pedestrian). See Development_Protocol_2026-03-01 §8.2.
- [ ] **TfL cycleway cancel-out in main app** — When a segment has a live disruption (or other conditions), reduce or cancel the TfL cycleway/quietway bonus so preference does not dominate. See Development_Protocol_2026-03-01 §8.3.

- [ ] **Adjust routing to use intersection data** — Extend the routing cost function (e.g. in `4_backend_engine/app.py`) to use node attributes from the graph (e.g. `traffic_signals`, `mini_roundabout`, `crossing`, `barrier`) so that traffic lights, roundabouts, and barriers affect route choice. See `0_documentation/GRAPH.md` Section 4 (node attributes) and Section 7 (routing use).

### To do — High priority

- [ ] **Barrier snap: avoid mapping gates on passenger ways onto streets** — Gates on edges to passenger ways (e.g. housing access) are often snapped to a nearby street edge. Prefer snapping to access/footway-type edges or add post-processing so barriers on access ways are not tagged on main streets. See Development_Protocol_2026-02-19 §7.5.

### To do — Low priority

- [ ] **Big junctions: multiple junction penalties in short time** — At large junctions the route can get several junction/junction_danger penalties in quick succession. May be acceptable (big junctions are more dangerous); optional: add cluster/cap rule. See Development_Protocol_2026-02-19 §7.1.
- [ ] **Traffic calming tables/cushions on pedestrian crossing** — Tables or cushions are often mapped in OSM on the pedestrian crossing rather than the road; consider edge-type or snapping adjustments so they appear on the correct carriageway. See Development_Protocol_2026-02-19 §7.2.
- [ ] **Battersea Park area: sparse edges and steep segments** — Certain quarters below Battersea Park have very few edges and lack steep segments; check OSM and elevation data coverage. See Development_Protocol_2026-02-19 §7.3.
- [ ] **Implement heuristic for A\*** — Add an admissible heuristic (e.g. Euclidean distance / cyclist speed) to A* in the main app so routing scales better on large graphs.
- [ ] **Adjust green mode, maybe new manual mode** — Refine green/scenic detection (e.g. park paths, natural surface) or add a manual override mode for “green” segments.
- [ ] **Add new data from TfL sets** — Ingest additional TfL datasets (e.g. line infrastructure, other route types) and integrate with tagging or overlays.
- [x] **Add dynamic data from APIs** — ~~Integrate live or periodic data from external APIs.~~ Done: TfL + TomTom via `live_disruptions.py` (safe update, MASTER_LIVE_LOOKUP merge). TfL: `tfl_live.py`; TomTom: `tomtom_live.py` (Traffic Incident Details v5, cluster A–D). Main app: single O(1) lookup, combined overlay, `POST /admin/update_tfl`, `POST /admin/update_tomtom`. Debug app: separate TfL and TomTom toggles, `/debug/tomtom_disruptions`, inspector iconCategory/magnitudeOfDelay. See feature request `tomtom.md`.
- [ ] **Improve frontend** — UX, accessibility, performance, or layout improvements for the main and/or debug app.
- [ ] **Improve data handling to reduce load up time and runtimes** — Optimise graph load, caching, spatial indexes, or backend response times.

---

## Completed

- **TfL apply: zero all TfL tags first, then apply only export** — Done: `apply_tfl_export.py` now clears `tfl_cycle_programme` and `tfl_cycle_route` on every edge, then applies only the export. See Development_Protocol_2026-02-19 §7.4.
- **Barrier confidence and point-based traffic calming** — Done: Kerb only on pedestrian ways; other barriers get barrier_confidence (0–1) from orthogonal distance; traffic_calming from planet_osm_point snapped to edges in separate columns (prefer car-allowed); calming_source (way/point/both) in backend and debug overlay. See Development_Protocol_2026-02-23.
