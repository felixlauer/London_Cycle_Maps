# London Cycle Maps — Main App

Documentation for the **user-facing routing app**: frontend (`5_frontend`) and backend (`4_backend_engine/app.py`). **When you add or change features, API, or architecture, update this file.**

---

## 1. Purpose

The main app is the production cycling route planner for London. Users set start and end on the map and get two routes (fastest vs optimized), with grouped toggles for **Safety** (accidents, night mode, TfL Cycleways, narrow facility, speed stress, signals, barriers, junction danger, live TfL disruptions), **Comfort** (road bike, flat route, traffic calming), and **Scenery** (TfL Quietways, green/scenic). Optional overlays highlight lit, steep, TfL, green, and narrow segments on the optimized route. **Node-based modes** (signals, barriers, junctions, calming) show as coloured circle icons on the map; left-click an icon opens a popup with details (e.g. barrier type). No data-exploration overlays (accidents heatmap, etc.) — those live in the debug app.

---

## 2. Architecture

### 2.1 Stack

| Layer | Tech | Location |
|-------|------|----------|
| Frontend | React 19, Leaflet, react-leaflet | `5_frontend/src/` |
| Backend | Flask, NetworkX, Shapely | `4_backend_engine/app.py` |
| Data | GraphML graph (post-elevation + TfL tags) | `1_data/london_elev_final_tfl.graphml` |

### 2.2 Data flow

1. User clicks map → start then end (or resets with a third click).
2. Frontend calls `GET /route` with coordinates and all active weight parameters (0 or 1 per toggle).
3. Backend loads graph once at startup; also loads `tfl_live` module at startup (builds STRtree edge spatial index); live disruption data populated via `POST /admin/update_tfl`. For each request it parses **request-scoped weights** (no globals), builds an optimized weight function via closure, runs A* twice (fastest and optimized), returns paths, stats, chunk arrays (lit, steep, TfL, green, narrow), and **node_highlights** (barrier/signal/junction/calming points for map icons).
4. Frontend draws two polylines (fastest grey, optimized coloured), overlays for lit/steep/TfL/green/narrow segments when toggles are on, and **circle markers** for node-based features (colour by type); left-click a marker opens a popup with details. Stats panel shows conditional rows including **Speed stress** as a percentage of route length.
5. Right-click on map → `GET /inspect` → segment inspector popup and red segment overlay.

### 2.3 Backend (app.py)

- **Port:** 5000
- **Graph:** `1_data/london_elev_final_tfl.graphml` (directed, node id = (lon, lat), includes TfL and node point-features).
- **No DB in main app:** Routing uses only the graph; no PostgreSQL in this process.
- **Cost functions:** See **Section 5** for full mathematical formulation, preset constants, and per-mode formulas.
- **Optimized weight** is built per request via `make_weight_optimized(w)` (no global weights; safe for concurrent users). Formula: **Weight = (Length × M_total × R) + A_total + H**

### 2.4 Frontend (5_frontend)

- Single-page React app; main UI in `App.js` (no routing library; one component tree).
- Map: Leaflet via react-leaflet; center London, OSM tiles.
- State: `useState` for start/end, route results, toggles, inspector; `useEffect` for daylight check and re-fetch when toggles change.
- Theming: light/dark theme object (colors, tile filter) derived from Night Mode toggle; applied to header, panels, toggles, and map tiles.

---

## 3. Features

### 3.1 Routing

- **Click to set start** → then **click to set end** → backend returns fastest and optimized routes.
- **Third click** clears end and sets a new start (cycle repeats).
- **Optimization toggles** (all optional, 0 or 1): **Safety** — Avoid Accidents, Night Mode, TfL Cycleways, Narrow facility, Speed stress, Traffic signals, Barriers, Junction danger, Live TfL Disruptions. **Comfort** — Road Bike, Flat Route, Traffic calming. **Scenery** — TfL Quietways, Green/scenic. See API section for weight param names.

### 3.2 Display

- **Two routes:** Fastest (grey, semi-transparent) and optimized (solid colour: red in light theme, cyan in dark).
- **Stats panel** (bottom-left): Time, Distance, and conditional rows per active mode (Accidents, Lit %, Rough %, Elevation, Steep seg., TfL km, Speed stress %, Narrow km, Green km, Barriers, Calming, Signals, Junctions, Disruptions). “Diff” column shows optimized − fastest.
- **Control panel** (bottom-right): grouped toggles (Safety, Comfort, Scenery); scrollable. **Overlays:** lit, steep, TfL cycleway, TfL quietway, green, narrow when toggles on. **Node icons:** circle markers for barrier/signal/junction/calming; left-click opens popup with details.
- **Header:** App title + status line (e.g. “Set Destination.”, “Route Calculated.”, “Night detected. Dark Mode ON.”).

### 3.3 Segment inspector

- **Right-click** on map → request to `GET /inspect?lat=…&lon=…` → backend returns nearest edge’s tags + geometry.
- **Inspector window** (offset from click so segment stays visible): core tags (name, surface, maxspeed, grade, length, elevation_start, elevation_end); when edge is affected by a live TfL disruption, also shows `tfl_live_category`, `tfl_live_severity`, `tfl_live_description`; “Show All Tags” expands to full edge attributes.
- **Red polyline** overlay on the inspected segment; left-click elsewhere or close button dismisses.

### 3.4 Daylight and theme

- On load, frontend calls sunrise-sunset API (London); if current time is before sunrise or after sunset, Night Mode is turned on automatically and status set to “Night detected. Dark Mode ON.”
- Dark theme: dark background, light text, inverted map tiles, cyan optimized route, yellow lit segments, green steep segments, blue/teal TfL and green overlays.

---

## 4. API (backend)

| Method | Endpoint | Query params | Response |
|--------|----------|--------------|----------|
| GET | `/route` | `start_lat`, `start_lon`, `end_lat`, `end_lon`, plus weight params below | `{ status, fastest: { path, stats }, safest: { path, stats, lit_chunks, steep_chunks, tfl_cycleway_chunks, tfl_quietway_chunks, green_chunks, narrow_chunks, disruption_chunks, node_highlights } }` |
| POST | `/admin/update_tfl` | (none) | `{ ok, message, count }` — fetch TfL, rebuild master lookup |
| POST | `/admin/update_tomtom` | (none) | `{ ok, message, count }` — fetch TomTom, rebuild master lookup |
| GET | `/inspect` | `lat`, `lon` | `{ tags, geometry }` or `{ error }` |

**Route weight params** (each 0.0–1.0, typically 0 or 1): `risk_weight`, `light_weight`, `surface_weight`, `hill_weight`, `tfl_cycleway_weight`, `tfl_quietway_weight`, `speed_weight`, `width_weight`, `green_weight`, `barrier_weight`, `calming_weight`, `junction_weight`, `signal_weight`, `tfl_live_weight`. **Optional:** `calming_source` = `way` \| `point` \| `both` (default `way`) — which calming data to use for the calming additive and highlights (way = OSM way tag only; point = snapped OSM nodes only; both = max of the two).

- **Stats** (per route): `length_m`, `accidents`, `duration_min`, `illumination_pct`, `rough_pct`, `elevation_gain`, `steep_count`, `tfl_cycleway_pct`, `tfl_quietway_pct`, `speed_stress_km`, **`speed_stress_pct`**, `narrow_km`, `green_km`, `barrier_count`, `give_way_count`, `stop_sign_count` (edge-based), `calming_count` (according to `calming_source`), `signal_count`, `junction_count`, `disruption_count`.
- **Paths / geometry:** arrays of `[lat, lon]` (WGS84). Chunk arrays are lists of segment geometries for the optimized route only. **node_highlights** is a list of `{ lat, lon, type, details }` where `type` is `barrier`, `signal`, `junction`, `junction_danger`, or `calming` and `details` holds e.g. `{ barrier: "gate" }`, `{ traffic_calming: "hump", source: "way" }` or `"point"`, `{ degree: 5 }`. Calming highlights use the chosen `calming_source`; point-based calming uses stored `traffic_calming_point_lat/lon`. **Inspector tags:** when edge is affected by live disruption (TfL or TomTom), includes `tfl_live_category`, `tfl_live_severity`, `tfl_live_description`; for TomTom also `tfl_live_iconCategory`, `tfl_live_magnitudeOfDelay`. **Live disruptions** combine TfL and TomTom via `live_disruptions`; routing uses `MASTER_LIVE_LOOKUP` (O(1)). **.env:** `TFL_APP_KEY`, `TOMTOM_API_KEY`.

---

## 5. Cost functions — mathematical reference

All formulas and preset values below are implemented in `4_backend_engine/app.py`. Request weights \(w\) are in \([0,1]\) (typically 0 or 1 per toggle).

### 5.1 Main formula

\[
\text{Weight}(u,v) = (\text{Length} \times M_{\text{total}} \times R) + A_{\text{total}} + H
\]

- **Length:** edge length in metres (`d['length']`).
- **M_total:** length multiplier (penalties only); clamped so \(M_{\text{total}} \geq 0.1\).
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
| `R_MIN` | 0.1 | Minimum reward multiplier. |
| `UP_THRESH` | 0.033 | Steep ascent threshold (3.3%). |
| `DOWN_THRESH` | -0.033 | Steep descent threshold (-3.3%). |
| `JUNCTION_DANGER_MIN_CAR_ROADS` | 4 | Junction danger only if ≥ 4 car-allowed physical roads. |

### 5.3 Multipliers M (all non-negative)

- **Risk:** \(\text{risk\_penalty} = \text{risk} \times w_{\text{risk}}\); `risk` = accident count on edge.
- **Light:** \(\text{light\_penalty} = 0.5 \times w_{\text{light}}\) if edge not lit, else 0. Lit = `lit` in `['yes','true','24/7','on','designated']`.
- **Surface:** \(\text{surface\_penalty} = 3.0 \times w_{\text{surface}}\) if surface in `BAD_SURFACES`, else 0. `BAD_SURFACES` = grass, dirt, sand, ground, unpaved, sett, gravel, wood, fine_gravel, earth, mud, woodchips, cobblestone, pebblestone, clay, grit, grass_paver, stone, unhewn_cobblestone, stepping_stones.
- **Speed stress:** \(\text{speed\_m} = m \times w_{\text{speed}}\) where \(m = 0\) if \(\Delta v < 20\) km/h, \(m = 0.15\) if \(20 \leq \Delta v \leq 30\), \(m = 0.35\) if \(\Delta v > 30\) (\(\Delta v = \text{maxspeed} - \text{cyclist speed}\)). Maxspeed parsed from edge or inferred from highway type (e.g. residential 30, primary 50 km/h).
- **Width:** \(\text{width\_m} = p \times w_{\text{width}}\) where \(p = 0\) if width ≥ 1.5 m, \(p = 0.2\) if 1.25 ≤ width &lt; 1.5 m, \(p = 0.5\) if width &lt; 1.25 m. Width from `cycleway_width` or `width`.

\[
M_{\text{total}} = \max\bigl(0.1,\; 1 + \text{risk\_penalty} + \text{light\_penalty} + \text{surface\_penalty} + \text{speed\_m} + \text{width\_m}\bigr)
\]

### 5.4 Reward multiplier R

- Start \(R = 1\). If TfL Cycleway weight &gt; 0 and edge has `cycleway` or `superhighway` in `tfl_cycle_programme`: \(R \leftarrow R \times 0.75\). If TfL Quietway weight &gt; 0 and edge has `quietway`: \(R \leftarrow R \times 0.75\). If green weight &gt; 0 and edge is green (footway/cycleway/path/bridleway plus natural surface or unlit): \(R \leftarrow R \times 0.8\). Then \(R = \max(0.1, R)\).

### 5.5 Additives A (fixed cost per edge/node, in metres)

All A_* values are **added** to the edge cost (they are not multiplied by length). Each penalty has a fixed value in metres; that value is multiplied by the corresponding weight (0 or 1) and added.

**Exact logic in code:**  
`A_barrier` and `A_give_way`, `A_stop_sign` are read from the **edge** (barrier/give_way/stop are edge-based).  
`A_total = A_intersection + A_barrier + A_give_way + A_stop_sign + A_signal + A_junction + A_calming`  
Overlays plot **a single point at the stored original position** (barrier_lat/barrier_lon etc.), not the entire segment.

- **Intersection (zebra/uncontrolled crossing only):** \(\text{INTERSECTION\_PENALTY\_METRES}\) × \(w_{\text{junction}}\); node must have `crossing` or `crossing_type` in `zebra` or `uncontrolled`. Give-way, mini_roundabout, unmarked, and traffic_signals are excluded (give_way/stop are edge-based below).
- **Barrier (edge-based):** Read from current edge’s `barrier`: bollard/cycle_barrier 3, gate/chicane/kerb/etc. 12, stile/steps/etc. 35, other 8; **multiplied by `barrier_confidence`** (0–1, default 1.0 if missing), then by \(w_{\text{barrier}}\). Position for plotting: edge’s `barrier_lat`, `barrier_lon` (original OSM position).
- **Give-way / Stop sign (edge-based):** Only the edge that **ends** at the sign is tagged. Penalty = INTERSECTION_PENALTY_METRES × \(w_{\text{junction}}\). Position: `give_way_lat`/`give_way_lon`, `stop_sign_lat`/`stop_sign_lon`.
- **Traffic signal:** \(20 \times 4.44 \approx 88.8\) m virtual distance × \(w_{\text{signal}}\) if node has `traffic_signals`.
- **Junction danger:** 8 × \(w_{\text{junction}}\) if (a) node has no traffic signals, (b) number of **car-allowed physical roads** at node ≥ 4.
- **Traffic calming:** Depends on **calming_source** (request param, default `way`). **way:** 5 (cushion/choker) or 10 (other) × \(w_{\text{calming}}\) per edge with `traffic_calming`. **point:** same cost mapping using `traffic_calming_point` only. **both:** \(\max(\text{way cost}, \text{point cost})\) per edge (avoids double-count).

\[
A_{\text{total}} = A_{\text{intersection}} + A_{\text{barrier}} + A_{\text{give\_way}} + A_{\text{stop\_sign}} + A_{\text{signal}} + A_{\text{junction}} + A_{\text{calming}}
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

- **WORK_COEFF** = 20.0. If grade \(g > 0\): \(\text{hill\_cost} = L \times \bigl(20g + (20g)^2 \mathbf{1}_{g>0.033}\bigr)\). If grade \(< -0.033\): \(\text{hill\_cost} = L \times 1.5\). Otherwise 0. Then \(H = \text{hill\_cost} \times w_{\text{hill}}\).

### 5.8 Fastest weight

\[
\text{Weight}_{\text{fastest}}(u,v,d) = \text{Length}.
\]

---

## 6. File overview

| Path | Role |
|------|------|
| `4_backend_engine/tfl_live.py` | Shared TfL live disruption module (STRtree, API fetch, spatial matching, lookup table) |
| `5_frontend/src/App.js` | Map, toggles, route display, inspector, stats, theme, API calls |
| `5_frontend/src/index.js` | React root |
| `5_frontend/public/index.html` | HTML shell |
| `4_backend_engine/app.py` | Flask app, graph load, cost functions, `/route`, `/inspect` |

---

## 7. Keeping this document up to date

- **Technical spec for routing modes:** See `0_documentation/implementation.md` (cost factors, maths, frontend requirements).
- **New feature or toggle:** Update Section 3 (Features) and, if the API changes, Section 4 (API).
- **New endpoint or request params:** Update Section 4 and Section 2.2 (data flow).
- **Change of port, graph path, or stack:** Update Section 2.
- **New UI panel or major refactor:** Update Section 3 and Section 5.

A reminder to update this file is in the top comment of `5_frontend/src/App.js` and at the top of `4_backend_engine/app.py`.
