# London Cycle Maps — Main App

Documentation for the **user-facing routing app**: frontend (`5_frontend`) and backend (`4_backend_engine/app.py`). **When you add or change features, API, or architecture, update this file.**

---

## 1. Purpose

The main app (**Tuned Cycling**) is the production cycling route planner for London. Users select a **routing profile** (or use **Test Mode** to override routing weights), set start and end on the map, and get two routes (fastest vs profile-optimized). A **Route overlays** picker (bottom-right) lets users choose which edge and point layers to draw on the optimized route after **Get Route** — independent of profile weights. No full-map data exploration — that stays in the debug app.

---

## 2. Architecture

### 2.1 Stack

| Layer | Tech | Location |
|-------|------|----------|
| Frontend | React 19, Leaflet, react-leaflet | `5_frontend/src/` |
| Backend | Flask, NetworkX, Shapely | `4_backend_engine/app.py` |
| Data | NetworkX graph (post-elevation + TfL tags) | `1_data/london_elev_final_tfl.gpickle` (`.graphml` export/fallback) |

### 2.2 Data flow

1. On load, frontend fetches `GET /profiles` and loads the active profile (`GET /profiles/:id`); selection persisted in `localStorage`.
2. User sets **start** and **end** via map click **or** Mapbox text search (profile panel); both update the same `[lat, lon]` state. Search selection flies the map to the chosen place; map clicks do not.
3. When both points exist, frontend prefetches routes in the background; user clicks **Get Route** to reveal results.
4. **Profile mode (default):** frontend calls `GET /route` with coordinates and `profile_id`; backend loads weights from `user_profiles.json`.
5. **Test Mode:** header toggle exposes legacy 0/1 toggles; frontend sends explicit weight query params (no `profile_id`).
6. Backend loads graph once at startup; builds STRtree for edge snap; for each request parses **request-scoped weights**, sets `calming_source='both'` (hardcoded), runs **A\*** twice (fastest and optimized), returns paths, stats, overlay chunks, and **node_highlights**.
7. Frontend draws two polylines, overlays gated by active weights (&gt; 0), condensed stats panel (all metrics with Δ vs fastest).
8. Right-click on map → `GET /inspect` → segment inspector popup and red segment overlay.

### 2.3 Backend (app.py)

- **Port:** 5000
- **Graph:** Loaded via `3_pipeline/graph_io.load_graph` from `1_data/london_elev_final_tfl.graphml` (prefers companion `.gpickle`). Directed; node id = (lon, lat); includes TfL and node point-features.
- **No DB in main app:** Routing uses only the graph; no PostgreSQL in this process.
- **Dynamic API data:** Live disruptions come from two sources—**TfL** (Road Disruptions) and **TomTom** (Traffic Incidents v5). Both are refreshed independently via `POST /admin/update_tfl` and `POST /admin/update_tomtom`; the backend merges them into a single lookup used for routing and the “Live TfL Disruptions” overlay (see Section 4.1).
- **Cost functions:** See **Section 5** for full mathematical formulation, preset constants, and per-mode formulas.
- **Optimized weight** is built per request via `make_weight_optimized(w)` (no global weights; safe for concurrent users). Formula: **Weight = (Length × M_total × M_highway × R) + A_total + H**. **M_highway** (always on): `steps` → ×50; `footway` / `pedestrian` / `path` without dedicated cycle infrastructure → ×4; `service` alley → ×4; other `service` → ×50; else ×1. `service` with denied `access` → hard block. **Fastest** uses `Length × M_highway` only. **Penalty masks** (`cost_masks.py`): vehicular-free edges skip risk/speed/calming; steps and non-alley service skip surface/hill (see §5.9).
- **Edge snap:** `tfl_live.snap_to_edge` uses the startup **STRtree** (shared with live disruptions; built in `live_disruptions.init`) to find the globally closest point on any edge (`line.project` + `interpolate`). Max orthogonal distance **50 m** (default). **Routing:** A\* runs from the **closer terminal node** (anchor) of each snapped edge; returned `path` coordinates prepend/append the exact snap points as **visual stubs** (stats/cost exclude stub segments). **Inspector:** same global snap (not node-local candidates). A legacy **cKDTree** on nodes remains at bootstrap but is unused by `/route` and `/inspect`.
- **A\* heuristics** (`routing_heuristic.py`):
  - **Fastest:** `h(u, goal) = haversine_m(u, goal)` — straight-line metres (admissible for length-minimizing routes).
  - **Optimized:** `h(u, goal) = haversine_m(u, goal) × cost_per_m_lb`, where `cost_per_m_lb = m_lb × r_lb`. **`r_lb`:** product of enabled reward factors (TfL cycleway ×0.75, TfL quietway ×0.75, green ×0.8), floored at `R_MIN`. **`m_lb`:** `max(M_MIN, 1.0 + Σ w_k × floor_k)` for enabled length multipliers (`risk`, `light`, `surface`, `speed`, `width`); each `floor_k` is computed once at startup from the graph (0 if any edge has zero penalty for that type — admissible). Additives (signals, junctions, hills) and live closures are omitted from `h`. Reward constants are shared with `make_weight_optimized`.
  - **Note (penalty floors vs earlier design):** The explicit `m_lb` term generalises an earlier formulation that hardcoded `m_lb = 1.0` and omitted length penalties from `h` for the same admissibility reason. On the current London graph, every `floor_k` is 0 (lit, good-surface, zero-risk, etc. edges exist), so **`cost_per_m_lb` is unchanged in practice** — still `1.0 × r_lb` for Safe Commuter. The structure is ready if a future graph has no zero-penalty edges for a type; tighter bounds would still require other admissible techniques (e.g. precomputed weights) because additives remain excluded from `h`.
  - **Junction cache:** at startup, each node gets `is_dangerous_junction` and `car_physical_road_count` (O(1) in A\* weight fn).
- **Dev timing:** set `ROUTE_BENCHMARK=1` to log snap + A\* wall times per `/route` request. Run `python 4_backend_engine/route_benchmark.py` (optional `--quick`) to compare path **costs** with `h=0` vs the new heuristic (must match).

### 2.4 Frontend (5_frontend)

- Single-page React app; main UI in `App.js`.
- **Profile panel** (top-left): dropdown of seed + custom profiles, **Route points** (Start/End Mapbox autocomplete), Create Profile modal, Get Route button.
- **Route overlay picker** (bottom-right): hideable **Layers** FAB — edge overlays (lit, steep, TfL, green, narrow, disruptions) and point overlays (barriers, signals, junctions, calming) on the **optimized route only**. On **Get Route**, only **TfL cycleways** is on by default; other overlays are off until toggled. Display-only (routing unchanged). Catalog: `GET /overlay_catalog`.
- **Test Mode** toggle in header (top-right); when on, legacy grouped toggles appear mid-right (**routing** overrides only, not map overlays).
- Map: Leaflet via react-leaflet; center London, OSM tiles; `MapFlyTo` on search selection.
- State: profiles, active profile, test mode, start/end (+ labels), route results, inspector.
- **Env:** `REACT_APP_MAPBOX_API_KEY` in `5_frontend/.env` (see `5_frontend/.env.example`); required for location search. CRA reads env at startup only — restart `npm start` after changes.
- Theming: light/dark from Night Mode toggle (Test Mode only for UI theme; `light_weight` in profile affects routing cost, not theme).

---

## 3. Features

### 3.1 Profile-driven routing

- **Active profile** selects all 14 routing weights simultaneously (continuous values in `[0.0, 1.0]`).
- **Seed personas:** Safe Commuter (infrastructure + safety), Fast & Direct (minimal penalties), Tourist / Explorer (green + quietways).
- **Create Profile:** modal form with numeric inputs (`min=0`, `max=1`, `step=0.05`); `POST /profiles` persists to `user_profiles.json`.
- **Test Mode:** reveals manual 0/1 toggles that override the active profile for debugging.

### 3.2 Routing interaction

- **Map click:** set start → set end → third click resets (new start, end cleared). Labels show “Map location”.
- **Text search:** Start/End fields in profile panel use **Mapbox Search Box API v1** (`mapboxGeocoding.js`, `LocationSearchInput.js`). Session UUID is created on input **focus** and reused for all `suggest` calls until selection (`retrieve`) or blur — one billing session per focus, not per keystroke. London bbox bias (`country=GB`). Selecting a result sets coordinates, updates the label, places the marker, and **flies** the map to the point.
- Start/end from map and search are interchangeable; background prefetch runs when both exist; **Get Route** reveals prefetched results.

### 3.3 Park opening hours (hard constraint)

- **Closed parks are impassable** — edges with `is_park=yes` that are closed at request time receive cost `1e9` in **both** fastest and optimized routing, regardless of profile or `green_weight`.
- **Evaluation time:** `Europe/London` local time (`datetime.now(ZoneInfo("Europe/London"))`), automatic GMT/BST from the request date.
- **OSM hours:** graph edges store `opening_hours` from the highest-overlap park polygon; unique strings are pre-compiled in `G.graph["park_opening_hours_unique"]`.
- **Pre-eval per request:** [`park_opening_hours.py`](4_backend_engine/park_opening_hours.py) parses each unique string once via `opening-hours-py` (solar events use London coordinates); A* only does O(1) dict lookup.
- **Fallback:** park edges without valid OSM hours default to **dawn-dusk** (astronomical, London coords).
- **Dependency:** `pip install -r 4_backend_engine/requirements.txt` (`opening-hours-py`).
- **`/route` meta:** `park_hours_at` (ISO-8601 London), `park_fallback_open`, `park_hours_map_size`.
- **Verification (17 Jun 2026):** four-slot audit with edge/polygon counts — [`verification/park_hours_verification.md`](verification/park_hours_verification.md). Re-run: `python 4_backend_engine/park_hours_audit.py`.

### 3.4 Location search (Mapbox)

- **Frontend-only** geocoding — backend unchanged.
- **Files:** `5_frontend/src/mapboxGeocoding.js` (suggest/retrieve), `LocationSearchInput.js` (debounced dropdown), `MapFlyTo.js` (viewport fly on search select).
- **Token:** public Mapbox token in `REACT_APP_MAPBOX_API_KEY`; restrict by URL in Mapbox dashboard. If unset, inputs are disabled with placeholder “Mapbox key not configured”.

### 3.5 Display

- **Two routes:** Fastest (grey) and optimized (red light / cyan dark) — always shown after **Get Route**.
- **Stats panel** (bottom-left): hero Time + Distance rows; condensed table of all 15 secondary metrics with optimized value and Δ vs fastest.
- **Route overlays:** user-selected via bottom-right **Layers** picker (edge polylines + point markers along optimized path). Backend returns all overlay chunks on every `/route`; `node_highlights` uses `overlay_mode=True` (full path features). Visibility is client-side only.
- **Header:** “Tuned Cycling” + status line with timing and active profile name.

### 3.6 Segment inspector

- **Right-click** on map → request to `GET /inspect?lat=…&lon=…` → backend returns nearest edge’s tags + geometry.
- **Inspector window** (offset from click so segment stays visible): core tags (name, surface, maxspeed, grade, length, elevation_start, elevation_end); when edge is affected by a live disruption (TfL or TomTom), also shows `tfl_live_category`, `tfl_live_severity`, `tfl_live_description` (and for TomTom: `tfl_live_iconCategory`, `tfl_live_magnitudeOfDelay`); “Show All Tags” expands to full edge attributes.
- **Red polyline** overlay on the inspected segment; left-click elsewhere or close button dismisses.

### 3.7 Daylight and theme

- On load, frontend calls sunrise-sunset API (London); if current time is before sunrise or after sunset, Night Mode is turned on automatically and status set to “Night detected. Dark Mode ON.”
- Dark theme: dark background, light text, inverted map tiles, cyan optimized route, yellow lit segments, green steep segments, blue/teal TfL and green overlays.

---

## 4. API (backend)

| Method | Endpoint | Params / body | Response |
|--------|----------|---------------|----------|
| GET | `/profiles` | — | `{ profiles: [{ id, name }, ...] }` |
| GET | `/profiles/<user_id>` | — | `{ id, name, weights: { ...14 keys } }` or 404 |
| POST | `/profiles` | JSON `{ name, weights }` | `{ id, name, weights }` (201) or 400 if weight ∉ `[0.0, 1.0]` |
| GET | `/route` | `start_lat`, `start_lon`, `end_lat`, `end_lon`, **`profile_id`** *or* explicit weight params | See below |
| GET | `/overlay_catalog` | — | `{ version, edge: [...], point: [...] }` — route overlay picker metadata |
| POST | `/admin/update_tfl` | (none) | `{ ok, message, count }` — fetch TfL Road Disruptions, rebuild master lookup |
| POST | `/admin/update_tomtom` | (none) | `{ ok, message, count }` — fetch TomTom Traffic Incidents, rebuild master lookup |
| GET | `/admin/tfl_status` | — | `{ loaded, edge_count, disruption_count, last_update, error }` — TfL live data status |
| GET | `/admin/tomtom_status` | — | `{ loaded, edge_count, last_update, error }` — TomTom live data status |
| GET | `/inspect` | `lat`, `lon` | `{ tags, geometry, snap_point: [lat, lon] }` or `{ error }` |

### 4.1 Dynamic API data (live disruptions)

Live disruption data is **not** in the graph file; it is fetched at runtime from two external APIs and matched to graph edges (see `0_documentation/GRAPH.md` §9).

- **TfL:** Transport for London Road Disruptions API. Refreshed via `POST /admin/update_tfl`. Optional `.env`: **`TFL_APP_KEY`** (recommended for rate limits).
- **TomTom:** TomTom Traffic Incident API v5 (cluster types: closure, roadworks, jam, environmental). Refreshed via `POST /admin/update_tomtom`. Required `.env`: **`TOMTOM_API_KEY`**.
- **Merge:** The backend keeps source-specific state and a merged **MASTER_LIVE_LOOKUP** (worst-case per edge when both sources affect it). Routing uses this merged lookup for the “Live TfL Disruptions” toggle (`tfl_live_weight`); overlay and stats use the same data.
- **Status:** `GET /admin/tfl_status` and `GET /admin/tomtom_status` return whether each source is loaded, edge count, last update time, and any error.
- **Inspector:** When an inspected edge is affected by a live disruption, the response includes `tfl_live_category`, `tfl_live_severity`, `tfl_live_description`; for TomTom-sourced (or merged) records, also `tfl_live_iconCategory` and `tfl_live_magnitudeOfDelay`.

**`/route` response meta** includes `active_profile_id`, resolved `weights`, `calming_source` (`both`), `cost_per_m_lower_bound`, `timing_ms`, `snap`, `park_hours_at`, `park_fallback_open`, `park_hours_map_size`.

**Route weight params** (each **strictly** `0.0`–`1.0` activation scalar): `risk_weight`, `light_weight`, `surface_weight`, `hill_weight`, `tfl_cycleway_weight`, `tfl_quietway_weight`, `speed_weight`, `width_weight`, `green_weight`, `barrier_weight`, `calming_weight`, `junction_weight`, `signal_weight`, `tfl_live_weight`. Values represent % activation of built-in backend penalties — not magnitude multipliers. **`calming_source`** is hardcoded to `both` (way + point calming); not accepted from clients.

- **Profile mode:** send `profile_id` only (plus coordinates).
- **Test mode / explicit:** send individual weight params; each clamped server-side to `[0.0, 1.0]`; defaults `0.0` when omitted.

- **Stats** (per route): `length_m`, `accidents`, `duration_min`, `illumination_pct`, `rough_pct`, `elevation_gain`, `steep_count`, `tfl_cycleway_pct`, `tfl_quietway_pct`, `speed_stress_km`, **`speed_stress_pct`**, `narrow_km`, `green_km`, `barrier_count`, `give_way_count`, `stop_sign_count` (edge-based), `calming_count` (according to `calming_source`), `signal_count`, `junction_count`, `disruption_count`.
- **Paths / geometry:** arrays of `[lat, lon]` (WGS84). Chunk arrays are lists of segment geometries for the optimized route only. **node_highlights** is a list of `{ lat, lon, type, details }` where `type` is `barrier`, `signal`, `junction`, `junction_danger`, or `calming` and `details` holds e.g. `{ barrier: "gate" }`, `{ traffic_calming: "hump", source: "way" }` or `"point"`, `{ degree: 5 }`. Calming highlights use the chosen `calming_source`; point-based calming uses stored `traffic_calming_point_lat/lon`. **Inspector:** when an edge is affected by a live disruption, tags include `tfl_live_category`, `tfl_live_severity`, `tfl_live_description` (and for TomTom: `tfl_live_iconCategory`, `tfl_live_magnitudeOfDelay`). Routing uses the merged live lookup (Section 4.1) for the “Live TfL Disruptions” weight.

---

## 5. Cost functions — mathematical reference

All formulas and preset values below are implemented in `4_backend_engine/app.py`. Request weights \(w\) are in \([0,1]\) (typically 0 or 1 per toggle).

### 5.1 Main formula

\[
\text{Weight}(u,v) = (\text{Length} \times M_{\text{total}} \times M_{\text{highway}} \times R) + A_{\text{total}} + H
\]

- **Length:** edge length in metres (`d['length']`).
- **M_highway:** always-on highway-type multiplier on length (`steps` ×50; plain footway/pedestrian/path ×4; `service` alley ×4; other `service` ×50; dedicated cycle infrastructure ×1). `service` with denied `access` (after `bicycle=yes/designated/permissive` override) is hard-blocked (§5.5).
- **M_total:** toggle-based length multiplier (penalties only); clamped so \(M_{\text{total}} \geq 0.1\).
- **R:** reward multiplier for preferred edges; \(R \in [0.1, 1]\) so cost stays positive.
- **A_total:** sum of fixed additive costs (metres or virtual metres).
- **H:** hill cost (metres).

### 5.2 Preset constants

| Constant | Value | Meaning |
|----------|--------|--------|
| `CYCLIST_SPEED_MPS` | \(16/3.6 \approx 4.44\) | Cyclist speed (m/s) for virtual distance. |
| `SIGNAL_WAIT_SECONDS` | 20 | Assumed wait at traffic signal (s). |
| `WIDTH_STD_M` | 1.5 | Width ≥ this: no width penalty. |
| `WIDTH_MIN_M` | 1.25 | Width &lt; this: moderate penalty. |
| `SPEED_DIFF_NEGLIGIBLE_KMH` | 20 | Speed difference &lt; 20 km/h: no speed-stress penalty. |
| `SPEED_DIFF_LOW_KMH` | 30 | 20–30 km/h: low penalty; &gt;30: moderate. |
| `M_MIN` | 0.1 | Minimum length multiplier. |
| `PEDESTRIAN_HIGHWAY_M` | 4.0 | `M_highway` for footway/pedestrian/path without cycle infrastructure. |
| `STEPS_HIGHWAY_M` | 50.0 | `M_highway` for `steps` (surface/hill masked — §5.9). |
| `R_MIN` | 0.1 | Minimum reward multiplier. |
| `BARRIER_HARD_COST` | 1e9 | Impassable edges (barriers, live closures, **closed parks**). |
| `UP_THRESH` | 0.033 | Steep ascent threshold (3.3%). |
| `DOWN_THRESH` | -0.033 | Steep descent threshold (-3.3%). |
| `JUNCTION_DANGER_MIN_CAR_ROADS` | 4 | Junction danger only if ≥ 4 car-allowed physical roads. |

### 5.3 Multipliers M (all non-negative)

- **Risk:** \(\text{risk\_penalty} = \text{risk} \times w_{\text{risk}}\); `risk` = accident count on edge.
- **Light:** \(\text{light\_penalty} = 0.5 \times w_{\text{light}}\) if edge not lit, else 0. Lit = `lit` in `['yes','true','24/7','on','designated']`.
- **Surface:** \(\text{surface\_penalty} = 3.0 \times w_{\text{surface}}\) if surface in `BAD_SURFACES`, else 0. `BAD_SURFACES` = grass, dirt, sand, ground, unpaved, sett, gravel, wood, fine_gravel, earth, mud, woodchips, cobblestone, pebblestone, clay, grit, grass_paver, stone, unhewn_cobblestone, stepping_stones.
- **Speed stress:** \(\text{speed\_m} = m \times w_{\text{speed}}\) where \(m = 0\) if \(\Delta v < 20\) km/h, \(m = 0.15\) if \(20 \leq \Delta v \leq 30\), \(m = 0.35\) if \(\Delta v > 30\) (\(\Delta v = \text{maxspeed} - \text{cyclist speed}\)). Maxspeed parsed from edge or inferred from highway type (e.g. residential 30, primary 50 km/h).
- **Width:** \(\text{width\_m} = p \times w_{\text{width}}\) where \(p = 0\) if width ≥ 1.5 m, \(p = 0.2\) if 1.25 ≤ width &lt; 1.5 m, \(p = 0.5\) if width &lt; 1.25 m. Width from `cycleway_width` when set (ignores road `width`); else `width` unless vehicular-free (then \(p = 0\)). See §5.9.

\[
M_{\text{total}} = \max\bigl(0.1,\; 1 + \text{risk\_penalty} + \text{light\_penalty} + \text{surface\_penalty} + \text{speed\_m} + \text{width\_m}\bigr)
\]

### 5.4 Reward multiplier R

- Start \(R = 1\). If TfL Cycleway weight &gt; 0 and edge has `cycleway` or `superhighway` in `tfl_cycle_programme`: \(R \leftarrow R \times 0.75\). If TfL Quietway weight &gt; 0 and edge has `quietway`: \(R \leftarrow R \times 0.75\). If green weight &gt; 0 and edge has any attraction flag (`is_park`, `is_river`, or `is_sight` = yes): \(R \leftarrow R \times 0.8\). Then \(R = \max(0.1, R)\).

### 5.5 Additives A (fixed cost per edge/node, in metres)

All A_* values are **added** to the edge cost (they are not multiplied by length). Each penalty has a fixed value in metres; that value is multiplied by the corresponding weight (0 or 1) and added.

**Exact logic in code:**  
`A_barrier` and `A_give_way`, `A_stop_sign` are read from the **edge** (barrier/give_way/stop are edge-based).  
`A_total = A_intersection + A_mini_roundabout + A_barrier + A_give_way + A_stop_sign + A_signal + A_junction + A_calming`  
Overlays plot **a single point at the stored original position** (barrier_lat/barrier_lon etc.), not the entire segment.

- **Intersection (zebra/uncontrolled crossing only):** \(\text{INTERSECTION\_PENALTY\_METRES}\) × \(w_{\text{junction}}\); node must have `crossing` or `crossing_type` in `zebra` or `uncontrolled`. Give-way, unmarked, and traffic_signals are excluded (give_way/stop are edge-based; mini_roundabout is separate below).
- **Mini-roundabout:** same \(\text{INTERSECTION\_PENALTY\_METRES}\) × \(w_{\text{junction}}\) when node has `mini_roundabout` and no `traffic_signals` (not folded into crossing penalty).
- **Junction cluster dedup:** at startup, nodes within 35 m that share junction_weight penalties are grouped; only the highest-priority node per cluster is charged (others in `JUNCTION_CLUSTER_SUPPRESSED`).
- **Barrier (edge-based):** Five **clusters** in [`barrier_clusters.py`](../4_backend_engine/barrier_clusters.py) (see debug overlay colours). **Impassable** (stile, turnstile, kissing_gate, fence, wall, …): cost \(10^9\) on **all** routes (fastest + optimized), no toggle. **`barrier_access`** in `private` / `no` → same hard block unless **`barrier_bicycle`** is `yes` / `designated` / `permissive` (ignores snap confidence). **Other clusters** apply additive penalty × `barrier_confidence` × \(w_{\text{barrier}}\) when Barriers toggle on: free flow **0 m** (lift_gate, height_restrictor, …); permeable **+15 m** (bollard, kerb, motorcycle_barrier, …); stop/push **+35 m** (gate, cycle_barrier, …); hostile **+90 m** (log, step, spikes, …). **Park waiver:** cluster-3 barriers on edges with `is_park=yes` (and not access-denied) get **0 m** additive penalty. *Future:* bike-type and user barrier-tolerance settings may rescale clusters (see module TODO). Position for plotting: `barrier_lat`, `barrier_lon`.
- **Give-way / Stop sign (edge-based):** Only the edge that **ends** at the sign is tagged. Penalty = INTERSECTION_PENALTY_METRES × \(w_{\text{junction}}\). Position: `give_way_lat`/`give_way_lon`, `stop_sign_lat`/`stop_sign_lon`.
- **Traffic signal:** \(20 \times 4.44 \approx 88.8\) m virtual distance × \(w_{\text{signal}}\) if node has `traffic_signals`.
- **Junction danger:** 8 × \(w_{\text{junction}}\) if (a) node has no traffic signals, (b) number of **car-allowed physical roads** at node ≥ 4.
- **Traffic calming:** **`calming_source` is always `both`:** \(\max(\text{way cost}, \text{point cost})\) per edge.

\[
A_{\text{total}} = A_{\text{intersection}} + A_{\text{mini\_roundabout}} + A_{\text{barrier}} + A_{\text{give\_way}} + A_{\text{stop\_sign}} + A_{\text{signal}} + A_{\text{junction}} + A_{\text{calming}}
\]

### 5.6 Dynamic TfL Disruptions

- Checked only when `tfl_live_weight > 0`.
- Uses O(1) dict lookup in `tfl_live.TFL_LIVE_LOOKUP`.
- **Closures:** return \(10^9\) (blocks edge).
- **Diversions:** \(M_{\text{total}} \mathrel{+}= 5.0 \times w_{\text{tfl\_live}}\).
- **Works category:** \(M_{\text{total}} \mathrel{+}= 3.0 \times w_{\text{tfl\_live}}\).
- **Incident categories:** \(M_{\text{total}} \mathrel{+}= 2.0 \times w_{\text{tfl\_live}}\).
- **Severity multiplier:** \(M_{\text{total}} \mathrel{*}= \text{severity\_multiplier}\) where Minimal = 1.1, Low = 1.15, Moderate = 1.3, Serious = 1.5, Severe = 2.0.

### 5.7 Hill cost H

- **WORK_COEFF** = 20.0. If grade \(g > 0\): \(\text{hill\_cost} = L \times \bigl(20g + (20g)^2 \mathbf{1}_{g>0.033}\bigr)\). If grade \(< -0.033\): \(\text{hill\_cost} = L \times 1.5\). Otherwise 0. Then \(H = \text{hill\_cost} \times w_{\text{hill}}\). **Skipped on `type=steps`** (§5.9).

### 5.9 Penalty masks (`cost_masks.py`)

Implemented per `0_documentation/tasks/cost_function_brainstorming.md`. Evaluated per edge inside `make_weight_optimized`.

**Vehicular-free** (`is_vehicular_free`): cyclist physically separated from general motor traffic. **True** if any of:

| Trigger | Values / notes |
|---------|----------------|
| `type` | `cycleway`, `path`, `pedestrian`, `footway`, `bridleway` |
| `is_park` | `yes` only — **not** `is_river` (river = green reward only; towpaths may have traffic) |
| `cycleway` / `cycleway_left` / `cycleway_right` / `cycleway_both` | **Whitelist only:** `track`, `separate`, `share_busway`, `exclusive` (not `lane`, `shared_lane`, `shared`, `advisory`, `opposite`, `no`, `segregated`, etc.) |
| `cycleway_separation` (+ left/right) | `bollard`, `kerb` |
| `tfl_cycle_programme` | contains `superhighway` |

When vehicular-free, force to **0**: `risk_weight`, `speed_weight`, `calming_weight` (M and A terms). **Width:** use `cycleway_width` only when set; if missing on vehicular-free edge, `width_weight` penalty = 0 (ignore adjacent car-lane `width`).

**`is_river` excluded:** manual river polygons mark scenic corridors (e.g. towpaths) that may still carry motor traffic. Those edges keep risk/speed/calming penalties; only `green_weight` reward applies (`is_park` / `is_river` / `is_sight` via `_has_attraction_edge`).

**Steps** (`type=steps`) and **non-alley service** (`type=service`, not `service=alley`, access not denied): keep `M_highway` = **×50** for service / **×50** for steps; force **0** for `surface_weight` and `hill_weight`. Service alleys use **×4** and keep surface/hill penalties. Denied service access (`private`/`no`/`customers`) is hard-blocked before multipliers apply.

Route stats (`calculate_path_stats`) use the same masks for accidents, speed stress, calming, rough surface, elevation on steps, and narrow width resolution.

### 5.8 Fastest weight

\[
\text{Weight}_{\text{fastest}}(u,v,d) = \text{Length}.
\]

---

## 6. File overview

| Path | Role |
|------|------|
| `4_backend_engine/user_profiles.py` | Profile CRUD, weight validation `[0.0, 1.0]`, JSON persistence |
| `4_backend_engine/user_profiles.json` | Local mock DB: seed personas + custom profiles |
| `4_backend_engine/tfl_live.py` | Shared TfL live disruption module (STRtree, API fetch, spatial matching, lookup table) |
| `5_frontend/src/App.js` | Map, profile selector, Test Mode, route display, inspector, stats, API calls |
| `5_frontend/src/index.js` | React root |
| `5_frontend/public/index.html` | HTML shell |
| `4_backend_engine/app.py` | Flask app, graph load, cost functions, `/route`, `/inspect` |
| `4_backend_engine/cost_masks.py` | Vehicular-free and steps penalty masks |
| `4_backend_engine/routing_heuristic.py` | Admissible A\* heuristics and shared reward constants |
| `4_backend_engine/barrier_clusters.py` | Barrier tag → cluster, penalties, debug colours |
| `4_backend_engine/route_benchmark.py` | Dev script: optimality check (h=0 vs heuristic costs) |

---

## 7. Keeping this document up to date

- **Technical spec for routing modes:** See `0_documentation/implementation.md` (cost factors, maths, frontend requirements).
- **New feature or toggle:** Update Section 3 (Features) and, if the API changes, Section 4 (API).
- **New endpoint or request params:** Update Section 4 and Section 2.2 (data flow).
- **Change of port, graph path, or stack:** Update Section 2.
- **New UI panel or major refactor:** Update Section 3 and Section 5.

A reminder to update this file is in the top comment of `5_frontend/src/App.js` and at the top of `4_backend_engine/app.py`.
