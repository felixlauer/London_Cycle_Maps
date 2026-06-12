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

*(No active high-priority items.)*

### To do — Low priority

- [ ] **TfL export: persist negative removals in ground-truth state** — `tfl_edges_from_graph.json` only stores tagged edges (positive state). Debug-app **removals** live in `tfl_manual_edits.json` only; after a rebuild they depend on a separate manual-apply pass. Consider a unified TfL state file (or export format) that records explicit untagged osm_ids / ways so export-alone restore matches full curated state without relying on manual JSON. See GRAPH.md §3.7 tradeoffs.
- [ ] **TfL disruptions: motorway vs pedestrian/cycle logic** — TfL geometry does not say which carriageway or cycle track is closed. Reliable automatic mapping likely needs richer data or ML/heuristics beyond highway type alone (motorways are already excluded from the cycling graph). See Development_Protocol_2026-03-01 §8.2.
- [ ] **TfL cycleway cancel-out in main app** — When a segment has a live disruption, reduce or cancel the TfL cycleway/quietway bonus so preference does not dominate. See Development_Protocol_2026-03-01 §8.3.
- [x] **Battersea Park area: sparse edges and steep segments** — Certain quarters below Battersea Park have very few edges and lack steep segments; check OSM and elevation data coverage. See Development_Protocol_2026-02-19 §7.3.
- [ ] **Add new data from TfL sets** — Ingest additional TfL datasets (e.g. line infrastructure, other route types) and integrate with tagging or overlays.
- [ ] **Improve frontend** — UX, accessibility, performance, or layout improvements for the main and/or debug app.
- [ ] **Improve data handling to reduce load up time and runtimes** — Optimise graph load, caching, spatial indexes, or backend response times.

---

## Completed

- **TfL apply: zero all TfL tags first, then apply only export** — Done: `apply_tfl_export.py` now clears `tfl_cycle_programme` and `tfl_cycle_route` on every edge, then applies only the export. See Development_Protocol_2026-02-19 §7.4.
- **Barrier confidence and point-based traffic calming** — Done: Kerb only on pedestrian ways; other barriers get `barrier_confidence` (0–1) from orthogonal distance; traffic_calming from planet_osm_point snapped to edges in separate columns (prefer car-allowed); calming_source (way/point/both) in backend and debug overlay. See Development_Protocol_2026-02-23.
- **Gates on passenger ways snapped onto streets (§7.5)** — Mitigated via `barrier_confidence` (penalty scaling); kerb uses pedestrian-only snap.
- **Adjust routing to use intersection data** — Done: signals, zebra/uncontrolled, junction danger, edge barriers/give_way/stop, traffic calming (way/point/both). Mini-roundabout added separately (not in `_node_intersection_penalty`, which remains crossing-only).
- **TfL disruptions: too many roads (polygons)** — Done: polygon matching uses MRR longest-axis + parallel filter (`tfl_live.py`). Adjacent parallel carriageways inside a TfL box remain tagged on purpose (cyclists on those arms are still affected); sharp clip-only edges are dropped.
- **Mini-roundabout routing penalty** — Done: `_node_mini_roundabout_penalty` in `app.py` (~44 m, same as zebra/give_way; not merged into crossing penalty).
- **Big junctions: multiple junction penalties** — Done: startup grid union-find within 35 m; one representative node per cluster pays junction_weight penalties (`JUNCTION_CLUSTER_SUPPRESSED`).
- **Traffic calming tables/cushions on pedestrian crossing** — Done: step 4d relays way-based table/cushion from footway to all crossing carriageways/cycleways; point snap prefers nearby cycleway when ≤1.15× car-allowed distance. Rebuild graph to apply. Debug report tracks before/relocated/added/after counts.
- **Add dynamic data from APIs** — Done: TfL + TomTom via `live_disruptions.py` (safe update, `MASTER_LIVE_LOOKUP`). Main/debug admin refresh, routing, overlays, inspector.
- **Green / attraction mode** — Done: OSM park polygons (`fetch_osm_park_polygons.py`, `tag_attractions_osm.py`); edge flags `is_park`, `is_river`, `is_sight`, `attraction_name`; debug **Modify attractions** + `apply_attraction_manual.py`; main app `_has_attraction_edge` + green_weight reward. See GRAPH.md §3.8.
- **A heuristic + KD-tree snap** — Done: `routing_heuristic.py` (haversine `h_fast`, per-request `r_lb` for `h_opt`); cKDTree snap at bootstrap; `route_benchmark.py` + `ROUTE_BENCHMARK=1` for dev checks. See APP_MAIN.md §2.3.
- **Global edge snap (STRtree + visual stub)** — Done: `tfl_live.snap_to_edge`; `/route` anchor-node A\* + endpoint stubs; `/inspect` global nearest edge. See APP_MAIN.md §2.3.
- **Pedestrian way length multiplier** — Done: `M_highway` ×4 on footway/pedestrian/path without dedicated cycle infrastructure; ×10 on `steps`; fastest and optimized paths. See APP_MAIN.md §5.
- **Barrier routing clusters** — Done: `barrier_clusters.py` (5 groups, hard block 1e9, additive 0/15/35/90 m); debug overlay colours by cluster. See APP_MAIN.md §5.5, Development_Protocol_2026_06_08.md §9.

