# London Cycle Maps — Main App

Documentation for the **user-facing routing app**: frontend (`5_frontend`) and backend (`4_backend_engine/app.py`). **When you add or change features, API, or architecture, update this file.**

---

## 1. Purpose

The main app (**Tuned Cycling**) is the production cycling route planner for London. Users select a **routing profile**, set start / vias / end on the map, and get two routes (fastest vs profile-optimized). After **Get Route**, a bottom-right **overlay mode rail** shows typed analysis layers on the optimized path (independent of profile weights). Trip analysis lives in a bottom **Dynamic Island**. No full-map data exploration — that stays in the debug app.

**Customer-facing UI (Jul 2026+):** `5_frontend/src/v2/` — run `npm start -- --v2`. Legacy `App.js` remains for Test Mode / segment inspector. Full remodel notes: [`design/WORKING_NOTES_JUL2026.md`](design/WORKING_NOTES_JUL2026.md), protocol: [`development_protocols/V2_FRONTEND_REMODEL.md`](development_protocols/V2_FRONTEND_REMODEL.md).

---

## 2. Architecture

### 2.1 Stack

| Layer | Tech | Location |
|-------|------|----------|
| Frontend | React 19, Mapbox GL JS (`react-map-gl`) | `5_frontend/src/` |
| Backend | Flask, NetworkX, Shapely | `4_backend_engine/app.py` |
| Data | NetworkX graph (post-elevation + TfL tags) | `1_data/london_elev_final_tfl.gpickle` (`.graphml` export/fallback) |

### 2.2 Data flow

1. On load, frontend restores the Supabase session (`AuthProvider`), then fetches `GET /profiles` and the active profile (`GET /profiles/:id`) through `flaskClient` (fresh JWT per request); selection persisted in `localStorage`. Profile fetches are deferred until the session check resolves (no guest flash / double fetch).
2. User sets **start**, optional **vias**, and **end** via map click **or** Mapbox text search (Routing Core in v2 / left panel in legacy); both update the same `[lat, lon]` state. Search selection flies the map to the chosen place; map clicks do not.
3. When both points exist, frontend prefetches routes in the background; user clicks **Get Route** to reveal results (`routeRevealed` in v2).
4. **Profile mode (default):** frontend calls `GET /route` with coordinates and `profile_id` (plus optional session `bike_type` override in v2); backend loads weights via the active `ProfileStore` (Supabase in production, local JSON otherwise — see §2.5).
5. **Test Mode (legacy only):** top-bar master toggle bypasses Supabase — no JWT is sent, requests carry `X-Tuned-Test-Mode: 1`, and Flask uses `LocalJsonStore`. Profiles still work normally (system + local custom via `user_profiles.json`; wizard enabled without login). **Manual weights (level 2):** a nested sub-toggle inside the Test panel hides profile selection and sends raw weight query params (no `profile_id`). **Not exposed in v2.**
6. Backend loads graph once at startup; builds STRtree for edge snap; for each request parses **request-scoped weights**, sets `calming_source='both'` (hardcoded), runs **A\*** twice (fastest and optimized), returns paths, stats, overlay chunks (incl. **v2 typed runs** + **elevation_profile**), and **node_highlights**.
7. Frontend draws two polylines (Beeline casing in v2), overlays via mode rail (v2) or FAB (legacy), analysis in Dynamic Island (v2) or condensed stats panel (legacy).
8. **Legacy only:** right-click on map → `GET /inspect` → segment inspector popup and red segment overlay.

### 2.3 Backend (app.py)

- **Port:** 5000
- **Graph:** Loaded via `3_pipeline/graph_io.load_graph` from `1_data/london_elev_final_tfl.graphml` (prefers companion `.gpickle`). Directed; node id = (lon, lat); includes TfL and node point-features.
- **No DB in main app:** Routing uses only the graph; no PostgreSQL in this process.
- **Dynamic API data:** Live disruptions come from two sources—**TfL** (Road Disruptions) and **TomTom** (Traffic Incidents v5). Both are refreshed independently via `POST /admin/update_tfl` and `POST /admin/update_tomtom`; the backend merges them into a single lookup used for routing and the “Live TfL Disruptions” overlay (see Section 4.1). Kill-switch for A/B vs clean benches: `python app.py --no-live`, or env `SKIP_DISRUPTION_FETCH=1` / `LIVE_DISRUPTIONS=0` (no fetch/poll; empty live lookup; admin update endpoints no-op).
- **Cost functions:** See **Section 5** for full mathematical formulation, preset constants, and per-mode formulas.
- **Optimized weight** is built per request via `make_weight_optimized(w)` (no global weights; safe for concurrent users). Formula: **Weight = (Length × M_total × M_highway × R) + A_total + H**. **M_highway** (always on): `steps` → ×50; `footway` / `pedestrian` / `path` without dedicated cycle infrastructure → ×4; `service` alley → ×4; other `service` → ×50; else ×1. `service` with denied `access` → hard block. **Fastest** uses `Length × M_highway` only. **Penalty masks** (`cost_masks.py`): vehicular-free edges skip risk/speed/calming; steps and non-alley service skip surface/hill (see §5.9).
- **Array-backed costs (default ON, 10 Jul 2026):** `/route` uses [`edge_cost_arrays.py`](../4_backend_engine/edge_cost_arrays.py) for both fastest and optimized legs (sequential v4). Load-time numeric tables + `_eid` on edges; shared overlays (parks + live coeffs) rebuild after each live disruption refresh (~45 ms). Kill-switch: `ARRAY_COSTS=0` falls back to Python `make_weight_*`. Response `meta.array_costs` is true/false. Heuristic uses stamped node `_x`/`_y`; path geometry lazily caches `_coords` on first WKT parse per edge. See [`route_generation_performance.md`](route_generation_performance.md) and [`testing/array_costs_v4_report.md`](testing/array_costs_v4_report.md).
- **CSR A* Phase A/B + Numba C (default ON, 11 Jul 2026):** Uni `/route` prefers Numba A* ([`pathfinding_numba.py`](../4_backend_engine/pathfinding_numba.py)) over pure-Python CSR ([`graph_csr.py`](../4_backend_engine/graph_csr.py)) over NetworkX. Costs via array tables; heuristic via CSR radian lat/lon. Kill-switches: `CSR_ASTAR=0` (NX search; CSR still built for heuristics), `NUMBA_ASTAR=0` (CSR py search). Response `meta.csr_astar` / `meta.numba_astar`. Phase C ~**11×** vs CSR-py (~**20–30×** vs original Python on long A* walls). Master ladder: [`testing/routing_performance_master.md`](testing/routing_performance_master.md). FR: [`testing/FR_csr_numba_astar.md`](testing/FR_csr_numba_astar.md).
- **Routing cache (format v2, lazy geom):** Pipeline `prebuild_routing_cache.py` writes `1_data/london_elev_final_tfl.routing_cache/` (tables, CSR, junctions, `geom_offsets.npy` / `geom_flat.npy`, WKB). Startup stamps `_eid`/`_vf` only; polylines via `EdgeGeomStore` (no request-path graph mutation). Fail-closed fingerprint + alignment (`1e-5` deg). Kill-switch `ROUTING_CACHE=0`. See [`ROUTING_CACHE.md`](ROUTING_CACHE.md).
- **Startup + RAM:** `python 4_backend_engine/benchmark_startup_ram.py` — after regenerating v2 cache, re-measure ready time.
- **Edge snap:** `tfl_live.snap_to_edge` uses the startup **STRtree** (shared with live disruptions; built in `live_disruptions.init`) to find the globally closest point on any edge (`line.project` + `interpolate`). Soft accuracy threshold **50 m** (`SNAP_SOFT_WARN_M`); hard fail for `/route` is **1000 m** (`SNAP_MAX_DISTANCE_M_ROUTE`) with progressive STRtree buffers. Snaps beyond 50 m still succeed; `meta.snap.{start,end,vias[].far}` is set so the client can warn. Hard fail message: *Could not snap to network — TUNE currently only supports Greater London*. **Inspector** keeps the 50 m default. **Routing:** A\* runs from the **closer terminal node** (anchor) of each snapped edge; returned `path` coordinates prepend/append the exact snap points as **visual stubs** (stats/cost exclude stub segments). A legacy **cKDTree** on nodes remains at bootstrap but is unused by `/route` and `/inspect`.
- **A\* heuristics** (`routing_heuristic.py`):
  - **Fastest:** `h(u, goal) = haversine_m(u, goal)` — straight-line metres (admissible for length-minimizing routes).
  - **Optimized:** `h(u, goal) = haversine_m(u, goal) × cost_per_m_lb`, where `cost_per_m_lb = m_lb × r_lb`. **`r_lb`:** product of enabled reward factors (TfL cycleway ×0.75, TfL quietway ×0.75, green ×0.8), floored at `R_MIN`. **`m_lb`:** `max(M_MIN, 1.0 + Σ w_k × floor_k)` for enabled length multipliers (`risk`, `light`, `surface`, `speed`, `width`); each `floor_k` is computed once at startup from the graph (0 if any edge has zero penalty for that type — admissible). Additives (signals, junctions, hills) and live closures are omitted from `h`. Reward constants are shared with `make_weight_optimized`.
  - **Note (penalty floors vs earlier design):** The explicit `m_lb` term generalises an earlier formulation that hardcoded `m_lb = 1.0` and omitted length penalties from `h` for the same admissibility reason. On the current London graph, every `floor_k` is 0 (lit, good-surface, zero-risk, etc. edges exist), so **`cost_per_m_lb` is unchanged in practice** — still `1.0 × r_lb` for Safe Commuter. The structure is ready if a future graph has no zero-penalty edges for a type; tighter bounds would still require other admissible techniques (e.g. precomputed weights) because additives remain excluded from `h`.
  - **Bounded-suboptimal optimized search:** `ROUTE_HEURISTIC_EPSILON` (default **0.75**) scales the optimized heuristic by `(1+ε)`. See **[`ROUTE_HEURISTIC_EPSILON.md`](ROUTE_HEURISTIC_EPSILON.md)** for the subjective-cost rationale (why ε is fine on Optimized/Safe but not Fastest), benchmark results, and tuning guidance.
  - **Path search (default unidirectional):** `/route` uses **unidirectional A*** (`4_backend_engine/pathfinding.py`) for both fastest and optimized legs. Bidirectional A* remains available for experiments: `?alg=bi` or `ROUTE_ALGORITHM=bi` in `.env` (not exposed in the UI). Reverted 9 Jul 2026 after benchmark showed ~2× slower wall-clock vs uni — see `0_documentation/testing/routing_performance_report.md`. Response `meta.algorithm` is `"unidirectional"` or `"bidirectional"`; `meta.search_stats` reports node expansions per leg.
  - **Junction cache:** at startup, each node gets `is_dangerous_junction` and `car_physical_road_count` (O(1) in A\* weight fn).
- **Dev timing:** set `ROUTE_BENCHMARK=1` to log snap + A\* wall times and expansion counts per `/route` request. Run `python 4_backend_engine/route_benchmark.py` (optional `--quick`) to compare path **costs** with `h=0` vs the new heuristic (must match). Epsilon trade-offs: `python 6_verification/bench_heuristic_epsilon.py`. Uni vs bi comparison: `python 4_backend_engine/benchmark_routing.py` (writes `0_documentation/testing/routing_performance_report.md`). Array costs: `python 4_backend_engine/smoke_array_costs.py` (one-route parity); benches in `benchmark_array_costs.py` / `benchmark_array_v4.py` → `0_documentation/testing/array_costs*.md`.

### 2.4 Frontend (5_frontend)

**Two UIs share one CRA app:**

| UI | Entry | Role |
|----|-------|------|
| **v2 (default for product work)** | `npm start -- --v2` or `REACT_APP_UI_VERSION=v2` → `src/v2/App.jsx` | Customer-facing shell — zones, island, mode rail, sidebar |
| **Legacy** | `npm start` → `src/App.js` | Test Mode, segment inspector, old overlay FAB |

Shared infrastructure (both UIs): `src/map/` (Mapbox GL), `src/auth/`, `src/api/flaskClient.js`, `src/wizard/` steps, `src/components/santander/SantanderStationsLayer.jsx`, geocode helpers.

#### 2.4.1 v2 shell (Jul 2026 remodel)

- **Layout:** five floating solid zones over a full-bleed map — **no** full-width top bar. See [`design/BRIEF.md`](design/BRIEF.md) + protocol [`development_protocols/V2_FRONTEND_REMODEL.md`](development_protocols/V2_FRONTEND_REMODEL.md).
  - **Top-left Routing Core** (`shell/zones/RoutingCoreZone.jsx`): Mode · Bike · Santander row, waypoints (≤3 vias), Depart at, Get Route.
  - **Top-center Alert Pill** (`alerts/useAlertPill.js`): ephemeral priority queue (errors, Santander guide, bike coerce, sticky hire confirms).
  - **Top-right Profile pill** → **slide-out sidebar** (`ProfileSidebar`): auth, profile CRUD/wizard, favourites C1–C3, appearance, units. Mobile: avatar moves into Routing Core; sidebar goes near-fullscreen.
  - **Bottom-center Dynamic Island**: collapsed metrics → expanded Beeline-like sheet (elevation, mode donuts/bars, extreme weather, multi-leg latch, Santander hire cards).
  - **Bottom-right:** overlay **mode rail** (SVG path-morph capsule↔T) + zoom / locate / north. Traffic always-on (not a rail slot).
- **Map:** Mapbox GL via `react-map-gl` (`src/map/CycleMap.jsx` + `v2/map/PlanningMap.jsx`). **Standard** style + night `lightPreset` (not deprecated standalone dark style). Beeline-cased routes (pink `#FF0061` + white casing; grey shortest; dashed walk). Quota gate `POST /mapbox/map_load` before init.
- **Overlays (v2):** one mode at a time — Cycleways (default) · Attractions · Surface · Hills · Light (night only). Typed connected runs from `/route` (`*_typed`); hover chips; VF > TfL. Legacy free FAB / `GET /overlay_catalog` not used.
- **State:** monolithic in `v2/App.jsx` — waypoints, profiles, session `bike_type`, Santander hire steps, depart, prefetch/commit, `routeRevealed`, overlay mode, island expand, `routeHover` bridge. Client prefs (appearance / units / favourite order) in `SidebarContext` **localStorage** — not Flask profile rows.
- **Auth:** same `AuthProvider` + Flask `/auth/*`. Auth UI embeds in sidebar (`AuthPanel`); password recovery modal at root. **Test Mode UI is out of v2** (legacy only).
- **Theming:** appearance `light | dark | system | auto` (`resolveAppearance.js`); auto uses `GET /night_status`. Profile `light_weight` still affects **routing cost**, not UI theme.
- **Units:** metric / imperial frontend formatting (`v2/units.js`).
- **Weather:** `GET /weather` (Open-Meteo proxy). Extreme warnings only steal island layout / mobile weather control. QA: `python app.py --weather-test`.
- **Motion / icons:** `motion` (`motion/react`), `lucide-react`, Meteocons for weather. Tailwind 3 optional utilities (`src/v2/**`, preflight off).
- **Parity tracker:** [`design/FUNCTIONALITY_CHECKLIST.md`](design/FUNCTIONALITY_CHECKLIST.md).

#### 2.4.2 Legacy UI (still shipped)

- Top bar + ProfileMenu + Test Mode + manual weights; left route points panel; bottom-left condensed stats; bottom-right Layers FAB; right-click segment inspector.
- Map day/night may still use classic style paths in older code paths — prefer v2 Standard + lightPreset for product work.
- Test mode: `X-Tuned-Test-Mode: 1` when allowed (localhost + `ALLOW_TEST_MODE=1`).

#### 2.4.3 Env & Mapbox billing (both UIs)

- Frontend: **`REACT_APP_MAPBOX_TOKEN`** (public `pk.…`, URL-restricted). No Supabase secrets in CRA.
- Backend `.env`: `SUPABASE_*`, `MAPBOX_API_KEY` (Search proxy), TfL/TomTom/ORS, Mapbox quota caps.
- **Mapbox billing guard:** `4_backend_engine/mapbox_usage.json` (UTC month). Search sessions hard-cut **450**/mo; map loads **45 000**/mo. Over-limit → **429**. `GET /mapbox/quota`. Seed with `MAPBOX_SEARCH_SESSIONS_USED` / `MAPBOX_MAP_LOADS_USED` to match dashboard.

### 2.5 Auth + profile storage (Supabase)

- **Architecture:** Browser never holds the Supabase anon key or Mapbox key. Password operations are **proxied and rate-limited** by Flask (`auth_rate_limit.py`): login lockout after 5 failures / 15 min, IP caps, reset/signup throttles. **Committed Get Route** (`purpose=commit`) is capped at **5 / IP / minute**; background `purpose=prefetch` is **not** counted (see §3.2a). Flask verifies JWTs in `auth_middleware.py`. `g.user_id` comes from the token `sub` claim **only**.
- **Endpoints:** `POST /auth/login|signup|password-reset|refresh|change-password|set-password`, `DELETE /auth/account`, `POST /auth/check-email`. Geocoding: `GET /geocode/suggest`, `GET /geocode/retrieve/<id>`.
- **Repository pattern** (`profile_store.py`): `ProfileStore` ABC with `LocalJsonStore` (`user_profiles.json`) and `SupabaseStore` (Supabase `profiles` table). Selection via `PROFILE_STORE` env (`auto | local | supabase`; auto = Supabase when configured). Validation/clamping stays in `user_profiles.py`.
- **Tenancy:** `SupabaseStore` uses the **service role key, which bypasses RLS** — every user-row query therefore explicitly filters `.eq('user_id', user_id)` at the application layer. RLS policies (see `4_backend_engine/supabase_sql/migrations/001_profiles.sql`) remain as defense-in-depth against direct Supabase access.
- **Access rules:** Guest — system presets only; `POST /profiles` returns 401. Authenticated — system + own profiles; `/route` with another user's profile id returns 404 (store-scoped lookup). `POST /profiles` whitelists body fields (`name, weights, bike_type, preset, toggles`) and hardcodes `is_system=False`, `user_id=g.user_id` — client-sent `is_system` / `user_id` / `id` / `slug` are dropped.
- **Test-mode bypass:** requests with `X-Tuned-Test-Mode: 1` skip JWT and use `LocalJsonStore`, but **only** when `ALLOW_TEST_MODE=1` **and** the request comes from localhost (`127.0.0.1` / `::1`) — a mis-set env var cannot open the bypass in production.
- **Ride reports:** `005_ride_reports.sql` adds `public.ride_reports` — `client_event_id` unique (idempotent retries), nullable `user_id` (guests report via `device_id`), `personal_only` / `simulate` flags, and snap columns the backend writes back. RLS denies everything; only the service role reads or writes. See §5.6a for how rows become routing effects.
- **Setup:** run `001_profiles.sql` (+ optional `002_user_email_lookup.sql`, `005_ride_reports.sql`), enable Email auth, seed presets, fill `4_backend_engine/.env` (`SUPABASE_URL`, `SUPABASE_JWT_SECRET`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`, `MAPBOX_API_KEY`). Also enable **Auth rate limits** in the Supabase dashboard (defence if GoTrue is hit directly).
- **Debug:** `/route` meta includes `auth: { mode: guest|user|test, user_id }`.
- **Tests:** `python -m unittest test_profile_store test_auth_rate_limit test_auth_account test_route_vias -v`.

---

## 3. Features

### 3.1 Profile-driven routing

- **Active profile** selects all 14 routing weights simultaneously (continuous values in `[0.0, 1.0]`).
- **Seed personas:** Safe Commuter (infrastructure + safety), Fast & Direct (minimal penalties), Tourist / Explorer (green + quietways).
- **Create Profile:** modal form with numeric inputs (`min=0`, `max=1`, `step=0.05`); `POST /profiles` persists to `user_profiles.json`.
- **Test Mode:** reveals manual 0/1 toggles that override the active profile for debugging.

### 3.2 Routing interaction

- **Map click:** fill start → empty vias in order → end → further click resets (new start; end + vias cleared). Labels show “Map location”.
- **Text search:** Start / Via / End fields use **Mapbox Search Box API v1** via Flask geocode proxy (`mapboxGeocoding.js`, `LocationSearchInput.js`). Session UUID is created on input **focus** and reused for all `suggest` calls until selection (`retrieve`) or blur — one billing session per focus, not per keystroke. London bbox bias (`country=GB`). Selecting a result sets coordinates, updates the label, places the marker, and **flies** the map to the point.
- Start/end/vias from map and search are interchangeable; background prefetch runs when start, end, and all vias are filled; **Get Route** reveals results (`purpose=commit`).

### 3.2a Via stops (multi-leg routing)

- **UI:** up to **3** intermediate stops ([`RoutePointsPanel.jsx`](../5_frontend/src/components/RoutePointsPanel.jsx)). Swap ⇅ only when there are no vias. Drag ≡ reorders the full list (a via can become start/end).
- **API:** `GET /route?vias=lat1,lon1;lat2,lon2` (max 3; 400 if more). Backend snaps `[start, …vias, end]` and runs the same fastest + optimized A* **per consecutive pair**. Response includes `legs[]` plus aggregated top-level `fastest` / `safest` (concat path + summed stats). Helpers: [`route_vias.py`](../4_backend_engine/route_vias.py).
- **Display:** full multi-leg route always drawn; **active leg emphasized** (others dimmed). Edge/point **overlays follow the active analysis leg only** (not merged onto the full path). Stats panel uses [`LegAnalysisPager.jsx`](../5_frontend/src/components/LegAnalysisPager.jsx) (chevrons + swipe) with per-leg metrics.
- **Race safety:** each fetch bumps `routeRequestId` + optional `AbortController`; obsolete HTTP responses are discarded. Mid-flight Numba A* is not abortable — worker may finish unused.
- **Santander:** mutual exclusion with vias (same pattern as Depart-at). Turning Santander on clears vias; adding a via forces Santander off. **TODO(later):** allow vias on the station→station bike leg.
- **Get Route rate limit:** `purpose=commit` (default if omitted) → **5 requests / client IP / minute** (`check_route_commit_allowed`). `purpose=prefetch` does **not** count — background calc stays uncapped so the UI feels snappy; scripted prefetch abuse is an accepted risk for now.

### 3.3 Park opening hours (hard constraint)

- **Closed parks are impassable** — edges with `is_park=yes` that are closed at request time receive cost `1e9` in **both** fastest and optimized routing, regardless of profile or `green_weight`.
- **Evaluation time:** by default `Europe/London` “now”. Optional `/route?depart_at=<ISO8601>` evaluates hours at that London datetime (naive strings → London TZ).
- **Leave now / Depart at (v1):** UI under Get Route. When `depart_at` is more than **30 minutes** ahead of London now: parks evaluated at that clock via a **request-local** `SharedOverlays` bake (parks only); soft live jams and hard live closures are **not** applied (`meta.live_applied=false`). Leave now / near-now uses the global overlay + live as today. Arrival-by and planned-closure enrichment are deferred.
- **OSM hours:** graph edges store `opening_hours` from the highest-overlap park polygon; unique strings are pre-compiled in `G.graph["park_opening_hours_unique"]`.
- **Pre-eval per request:** [`park_opening_hours.py`](4_backend_engine/park_opening_hours.py) parses each unique string once via `opening-hours-py` (solar events use London coordinates); A* only does O(1) dict lookup.
- **Fallback:** park edges without valid OSM hours default to **dawn-dusk** (astronomical, London coords).
- **Dependency:** `pip install -r 4_backend_engine/requirements.txt` (`opening-hours-py`).
- **`/route` meta:** `park_hours_at` (ISO-8601 London), `park_fallback_open`, `park_hours_map_size`, `depart_mode` (`now`|`depart_at`), `live_applied` (bool).
- **Verification (17 Jun 2026):** four-slot audit with edge/polygon counts — [`verification/park_hours_verification.md`](verification/park_hours_verification.md). Re-run: `python 4_backend_engine/park_hours_audit.py`.

### 3.4 Location search (Mapbox)

- Geocoding is **proxied by Flask** (`GET /geocode/suggest`, `GET /geocode/retrieve/<id>`) so `MAPBOX_API_KEY` stays in `4_backend_engine/.env` and never reaches the browser.
- **Files:** `5_frontend/src/mapboxGeocoding.js` (suggest/retrieve via Flask), `LocationSearchInput.js`, `MapFlyTo.js`.
- Session UUID is created on input **focus** and reused until selection or blur. London bbox bias (`country=GB`).

### 3.5 Display

- **Two routes:** Fastest (grey, Beeline casing) and optimized/tuned (fuchsia `#FF0061` + white casing) — shown after **Get Route**. Multi-leg: full path drawn; inactive legs dimmed; click inactive leg to switch analysis.
- **v2 Dynamic Island** (bottom-center): collapsed time/distance + microcharts; expand → elevation profile, mode donuts/bars, extreme weather slot, leg latch, Santander walk+cycle heroes. Deltas labeled **vs shortest**.
- **v2 overlay mode rail** (bottom-right): Cycleways (default on reveal) · Attractions · Surface · Hills · Light (night). Traffic always-on (Tiger Orange). Typed connected runs + hover chips. Display-only.
- **Legacy:** bottom-left condensed stats table + Layers FAB (`GET /overlay_catalog`) — still in `App.js` only.
- Brand / status: v2 uses zone chrome (no legacy top-bar status strip); optional status hints still partial (see checklist R-18).

### 3.5a Santander Cycles hire mode

- Toggle in the **Routing Core** (v2) or Route points panel (legacy). **Incompatible with via stops** and **Depart-at** for now. **TODO:** vias on the hire bike leg (checklist S-11).
- **Get Route** enters guided pickup → dropoff selection with map pins; bike A* runs station→station; walk legs dashed with primary casing (ORS via backend). Soft-fail 1.5 km / 3 suitable — see §4.2.
- **v2 chrome:** guide / soft banners / unsuitable confirm via **alert pill**; hire cards + walk stats in expanded island.

### 3.5b Leave now / Depart at

- Control under waypoints in Routing Core ([`v2/routing/DepartAtControl.jsx`](../5_frontend/src/v2/routing/DepartAtControl.jsx); legacy twin under Route points): Leave now (default) or Depart at (next 7 London weekdays, 15-min steps).
- Sends `GET /route?depart_at=…` when Depart at is selected. Future (&gt;30 min): parks @ that time; live traffic off — **alert pill** “Live traffic not applied for future departures.” See §3.3.

### 3.5c Route weather (v2)

- Flask `GET /weather?lat&lon&at?` proxies Open-Meteo (`weather_proxy.py`); ~12 min cache by rounded location + hour.
- Frontend resolves extreme conditions (`resolveExtreme.js`); only extremes reshape the expanded island metrics quarter (desktop) or show `WeatherControlZone` (mobile).
- QA: `python app.py --weather-test` — synthetic extremes rotate each UTC minute (`startup.md`).

### 3.6 Segment inspector

- **Legacy only:** right-click → `GET /inspect` → popup + red segment overlay.
- **Out of v2** — replaced by overlay hover chips + alerts. Do not port without an explicit product decision.

### 3.7 Daylight, appearance, and theme

- **v2 appearance prefs:** light / dark / system / **auto** (London sunrise/sunset via `GET /night_status`). Force via `npm start -- --day|--night` → `REACT_APP_FORCE_MODE`.
- Map follows effective theme through Mapbox Standard **lightPreset** (`MapLightPreset.jsx`).
- Profile `light_weight` / night illumination still gates **routing** and can auto-select the Light overlay mode when dark outside — separate from UI appearance unless appearance=`auto`.
- Legacy Night Mode toggle behaviour remains in `App.js` only.

---

## 4. API (backend)

| Method | Endpoint | Params / body | Response |
|--------|----------|---------------|----------|
| GET | `/profiles` | optional `Authorization: Bearer <jwt>` | `{ profiles: [...] }` — system presets + (when authenticated) own profiles |
| GET | `/profiles/<profile_id>` | optional `Authorization` | `{ id, name, weights, ... }` or 404; custom profiles require ownership |
| POST | `/profiles` | `Authorization` required (or test mode); JSON `{ name, weights, bike_type, preset, toggles }` — other fields dropped | profile (201), 400 invalid, 401 guest |
| GET | `/route` | `start_lat`, `start_lon`, `end_lat`, `end_lon`, optional **`vias`** (`lat,lon;…` max 3), optional **`avoid_points`** (`lat,lon;…` max 5 — hard-blocked for this request only), optional **`purpose`** (`commit`\|`prefetch`, default `commit`), **`profile_id`** *or* explicit weight params; optional **`depart_at`** (ISO-8601 London) | See below — `legs[]` + aggregated `fastest`/`safest`; commit → 429 if IP over 5/min |
| GET | `/overlay_catalog` | — | `{ version, edge: [...], point: [...] }` — **legacy** Layers FAB only (not used by v2 mode rail) |
| GET | `/night_status` | — | London day/night / sunrise-sunset payload for appearance + light overlay gating |
| GET | `/weather` | `lat`, `lon`, optional `at` (ISO) | Open-Meteo proxy: temp, WMO code, wind, UV, etc. Test mode: synthetic extremes (`--weather-test`) |
| GET | `/mapbox/quota` | — | Mapbox monthly usage / limits |
| POST | `/mapbox/map_load` | — | Reserve one map-load unit before Mapbox GL init (429 if over cap) |
| POST | `/admin/update_tfl` | (none) | `{ ok, message, count }` — fetch TfL Road Disruptions, rebuild master lookup |
| POST | `/admin/update_tomtom` | (none) | `{ ok, message, count }` — fetch TomTom Traffic Incidents, rebuild master lookup |
| GET | `/admin/tfl_status` | — | `{ loaded, edge_count, disruption_count, last_update, error }` — TfL live data status |
| GET | `/admin/tomtom_status` | — | `{ loaded, edge_count, last_update, error }` — TomTom live data status |
| GET | `/inspect` | `lat`, `lon` | `{ tags, geometry, snap_point: [lat, lon] }` or `{ error }` |
| GET | `/santander/candidates` | `lat`, `lon`, `need=bikes\|docks`, optional `radius_m` (default 1500) | Soft-fail 1B candidate set — see §4.2 |
| POST | `/santander/walk` | JSON `{ from:[lat,lon], to:[lat,lon] }` | `{ path, duration_s, distance_m, duration_min }` — ORS foot-walking; 503 if `ORS_API_KEY` missing |
| GET | `/admin/santander_status` | — | `{ loaded, station_count, last_update, last_error, fetch_enabled, ors_configured }` |
| POST | `/admin/update_santander` | (none) | `{ ok, message, count }` — refresh BikePoint cache now |
| POST | `/feedback/ride-reports` | optional `Authorization`; JSON `{ reports: [...] }` max 25. Each: `client_event_id` (uuid), `category`, `lat`, `lon`, `payload`, optional `device_id`, `simulate`, `personal_only` | `{ ok, accepted: [...], duplicates: [...], errors: [...] }` — in-ride route feedback, see §5.6a. Guests allowed; `user_id` always from the JWT. 20/user/hour, 30/IP/hour, charged per report |

### 4.1 Dynamic API data (live disruptions)

Live disruption data is **not** in the graph file; it is fetched at runtime from two external APIs and matched to graph edges (see `0_documentation/GRAPH.md` §9).

- **TfL:** Transport for London Road Disruptions API. Refreshed via `POST /admin/update_tfl`. Optional `.env`: **`TFL_APP_KEY`** (recommended for rate limits).
- **TomTom:** TomTom Traffic Incident API v5 (cluster types: closure, roadworks, jam, environmental). Refreshed via `POST /admin/update_tomtom`. Required `.env`: **`TOMTOM_API_KEY`**.
- **Merge:** The backend keeps source-specific state and a merged **MASTER_LIVE_LOOKUP** (worst-case per edge when both sources affect it). Routing uses this merged lookup for the “Live TfL Disruptions” toggle (`tfl_live_weight`); overlay and stats use the same data.
- **Status:** `GET /admin/tfl_status` and `GET /admin/tomtom_status` return whether each source is loaded, edge count, last update time, and any error.
- **Inspector:** When an inspected edge is affected by a live disruption, the response includes `tfl_live_category`, `tfl_live_severity`, `tfl_live_description`; for TomTom-sourced (or merged) records, also `tfl_live_iconCategory` and `tfl_live_magnitudeOfDelay`.

### 4.2 Santander Cycles hire mode (BikePoint)

Independent of riding profiles. Module: [`4_backend_engine/santander_live.py`](../4_backend_engine/santander_live.py). **Not** wired into edge costs / A*.

- **Source:** TfL Unified API `GET /BikePoint` (~798 docking stations). Reuses **`TFL_APP_KEY`**. Background poll default **45 s** (`BIKEPOINT_POLL_INTERVAL_S`). Kill-switch: `SKIP_BIKEPOINT_FETCH=1` or `BIKEPOINT_FETCH=0`.
- **Candidates (soft-fail 1B):** Sort stations within `radius_m` (default **1500**) by haversine; include every station until **3 suitable** are collected (or range exhausted). Suitable: `need=bikes` → `nb_bikes > 0`; `need=docks` → `nb_empty > 0`. Response: `{ shown, suitable_count, total_in_radius, need, radius_m, origin, last_update }`. Each shown station includes `walk_estimate_min = max(1, round(distance_m × 1.2 / 80))` (~4.8 km/h + 20% detour).
- **Frontend rules:** If `suitable_count == 0` → banner, **no pins** (greys hidden). If `1–2` → banner + show full `shown` (including empty greys). Pin colour: grey iff `nb_bikes == 0`, else red; compact text always `nb_bikes | nb_docks`.
- **Walk geometry:** After pickup + dropoff chosen, frontend calls `POST /santander/walk` twice (start→pickup, dropoff→end) in parallel with `GET /route` between stations. Requires **`ORS_API_KEY`** (OpenRouteService `foot-walking`). If walk fails, bike route still reveals; UI falls back to a dashed straight line.
- **UX:** Route-points panel toggle “Santander Cycles” → Get Route flies to start → pick pickup → fly to end → pick dropoff → dashed grey walk legs + normal bike route. Unsuitable click shows confirm (Proceed still selects). Same optional `depart_at` applies to the bike `/route` leg; dock availability remains live-now (no forecast).

**`/route` response meta** includes `active_profile_id`, resolved `weights`, `calming_source` (`both`), `cost_per_m_lower_bound`, `timing_ms` (with per-leg breakdown), `leg_count`, `snap` (`start`/`end`/`vias[]` each with `distance_m`, `anchor`, `far`), `park_hours_at`, `park_fallback_open`, `park_hours_map_size`, `depart_mode`, `live_applied`. Top-level `legs[]` holds per-segment `fastest`/`safest` (path + stats + overlays on safest); top-level `fastest`/`safest` are concatenated aggregates for backward-compatible map draw.

**Route weight params** (each **strictly** `0.0`–`1.0` activation scalar): `risk_weight`, `light_weight`, `surface_weight`, `hill_weight`, `tfl_cycleway_weight`, `tfl_quietway_weight`, `speed_weight`, `width_weight`, `green_weight`, `barrier_weight`, `calming_weight`, `junction_weight`, `signal_weight`, `tfl_live_weight`. Values represent % activation of built-in backend penalties — not magnitude multipliers. **`calming_source`** is hardcoded to `both` (way + point calming); not accepted from clients.

- **Profile mode:** send `profile_id` only (plus coordinates).
- **Test mode / explicit:** send individual weight params; each clamped server-side to `[0.0, 1.0]`; defaults `0.0` when omitted.

- **Stats** (per route): `length_m`, `accidents`, `duration_min`, `illumination_pct`, `rough_pct`, `elevation_gain`, `steep_count`, `tfl_cycleway_pct`, `tfl_quietway_pct`, `speed_stress_km`, **`speed_stress_pct`**, `narrow_km`, `green_km`, `barrier_count`, `give_way_count`, `stop_sign_count` (edge-based), `calming_count` (according to `calming_source`), `signal_count`, `junction_count`, `disruption_count`.
- **Elevation profile** (Dynamic Island): `safest.elevation_profile` is a list of `{ d_m, elev_m }` samples along the optimized path (distance from start in metres, node elevation), downsampled to ≤120 points keeping first/last. Present per leg and merged at top level with per-leg distance offsets.
- **v2 typed overlays:** on each safest (and per-leg safest), `build_v2_overlay_bundle` adds connected-run arrays: `green_typed`, `cycle_typed`, `surface_typed`, `hill_typed`, `light_typed`, `disruption_typed` — each feature `{ path, kind, length_m, run_id, … }` after `_collapse_edge_runs` (path-adjacent merge). Traffic (`disruption_typed`) is always drawn in v2; other modes are selected via the mode rail.
- **Paths / geometry:** arrays of `[lat, lon]` (WGS84). Legacy chunk arrays still returned for the old FAB. **node_highlights** is a list of `{ lat, lon, type, details }` where `type` is `barrier`, `signal`, `junction`, `junction_danger`, or `calming` and `details` holds e.g. `{ barrier: "gate" }`, `{ traffic_calming: "hump", source: "way" }` or `"point"`, `{ degree: 5 }`. Calming highlights use the chosen `calming_source`; point-based calming uses stored `traffic_calming_point_lat/lon`. **Inspector (legacy):** when an edge is affected by a live disruption, tags include `tfl_live_category`, `tfl_live_severity`, `tfl_live_description` (and for TomTom: `tfl_live_iconCategory`, `tfl_live_magnitudeOfDelay`). Routing uses the merged live lookup (Section 4.1) for the live-disruption weight.

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

### 5.6a Rider feedback overlay (crowd_overlays.py)

In-ride reports from the TBT **Report** flag (`ride_reports` table) become additive
effects on the cost arrays. Two invariants hold the design together:

- **The graph is never written.** Reports patch *copies* of the arrays, so OSM tags on
  the pickle are exactly what the pipeline produced. Delete a bad report and the effect
  vanishes on the next rebuild.
- **The Numba kernel never changes.** Each category maps onto an array A\* already reads,
  so `_cost_optimized` keeps its frozen signature.

| Category | Effect | Scope notes |
|----------|--------|-------------|
| `impassable` | `shared.impassable = 1` both directions | Same path as a live closure |
| `unlit` | `tables.unlit_base = 0.5` | Global apply also BFS-expands along the lit run (stops at an already-unlit edge, a node with `car_physical_road_count ≥ 3`, 150 m, or 12 edges) |
| `surface` | `tables.bad_surf_base = 3.0` | Extends to same-`osm_id` edges within 40 m |
| `dangerous` | `tables.risk += 1.0` | Snapped edge only, or all incident car-allowed edges when within 12 m of an `is_dangerous_junction` node |
| `speeding` | `tables.speed_stress = max(cur, 0.15)` | The `SPEED_DIFF_LOW_KMH` band; extends like `surface` |
| `general` | none | Picker timeout — stored for review only |

- **Snapping** uses `tfl_live.snap_to_edge` at **40 m** (far tighter than the 1000 m route
  snap). A miss is recorded on the row and produces no effect.
- **Personal scope:** a signed-in rider's own reports, no corroboration needed. **Global
  scope:** 2 distinct contributors within 90 days and 30 m (25 m for `dangerous`), or 1
  for `impassable` when that fix was stationary (`speed_mps < 0.8`, `h_acc_m < 15`). A
  contributor is `user_id`, or `dev:{device_id}` for guests. Rows older than 180 days
  decay out. `simulate` and `personal_only` rows never enter a global aggregate.
- **Patching** is `dataclasses.replace` over copy-on-write arrays, cached per
  `(scope, version)` with an LRU of 8 — but only when `shared` is the live object, since
  the future-`depart_at` branch builds a throwaway one. Per-request `avoid_points` are
  never cached.
- **Caveat:** `_cost_optimized` zeroes risk and speed stress on vehicular-free edges and
  surface penalties on steps, so `dangerous` / `speeding` on a segregated cycleway store
  and display but change no cost. Intended — the traffic cannot reach the rider.
- Kill-switches: `CROWD_OVERLAYS=0` (all apply off, POSTs keep working), `CROWD_GLOBAL=0`
  (global off, personal still works), `CROWD_REFRESH_INTERVAL_S` (default 600).
- Tests: `python -m unittest test_crowd_overlays test_ride_reports`.

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
| `4_backend_engine/user_profiles.py` | Weight validation/clamping + local JSON persistence (used by `LocalJsonStore`) |
| `4_backend_engine/user_profiles.json` | Local store: seed personas + custom profiles (test mode / dev fallback) |
| `4_backend_engine/profile_store.py` | `ProfileStore` ABC, `LocalJsonStore`, `SupabaseStore` (service role + app-layer tenancy) |
| `4_backend_engine/auth_middleware.py` | Supabase JWT verification, test-mode localhost gate, `g.user_id` / `g.profile_store` |
| `4_backend_engine/supabase_sql/migrations/001_profiles.sql` | Supabase `profiles` table + RLS policies |
| `4_backend_engine/supabase_sql/migrations/005_ride_reports.sql` | Supabase `ride_reports` table (service-role-only RLS) |
| `4_backend_engine/ride_reports.py` | Ride-report validation, idempotent upsert, local JSON fallback, snap write-back |
| `4_backend_engine/crowd_overlays.py` | Rider feedback → copy-on-write cost-array patches, global aggregation, refresh loop (§5.6a) |
| `9_mobile/src/feedback/` | Report picker categories, payload builder, offline JSONL queue, `useRideReport` |
| `4_backend_engine/test_profile_store.py` | Tenancy, sanitization, and test-mode gate tests |
| `6_verification/migrate_profiles_to_supabase.py` | Seeds system presets into Supabase |
| `5_frontend/src/auth/` | `AuthProvider`, `AuthPanel` (v2 sidebar), `AuthModal` (legacy), recovery, `auth.css` |
| `5_frontend/src/api/flaskClient.js` | `apiFetch` — fresh JWT per request, test-mode header, 401 handling |
| `5_frontend/src/map/` | Shared Mapbox GL: `CycleMap`, Beeline `RouteLayers`, markers, fly-to, light preset |
| `5_frontend/src/v2/` | **Customer UI** — `App.jsx`, shell zones, island, routing chrome, overlays, sidebar (see `v2/README.md`) |
| `5_frontend/src/components/` | Legacy: `TopBar`, `ProfileMenu`, `TestModePanel`, `RoutePointsPanel`, `LegAnalysisPager`; shared Santander layer |
| `4_backend_engine/tfl_live.py` | Shared TfL live disruption module (STRtree, API fetch, spatial matching, lookup table) |
| `4_backend_engine/weather_proxy.py` | Open-Meteo proxy + weather-test extremes for `/weather` |
| `4_backend_engine/mapbox_usage.py` | Monthly Mapbox search/map-load hard-cuts |
| `5_frontend/src/App.js` | Legacy UI: Test Mode, inspector, old overlay FAB |
| `5_frontend/src/index.js` | React root — switches legacy vs v2 via `REACT_APP_UI_VERSION` |
| `5_frontend/public/index.html` | HTML shell |
| `4_backend_engine/app.py` | Flask app, graph load, cost functions, `/route` (typed overlays + elevation), `/weather`, `/inspect` |
| `0_documentation/development_protocols/V2_FRONTEND_REMODEL.md` | v2 remodel protocol (locked decisions + agent workflow) |
| `0_documentation/design/WORKING_NOTES_JUL2026.md` | Chronological remodel working notes |
| `4_backend_engine/route_vias.py` | Parse `vias=` param, concatenate paths, aggregate multi-leg stats |
| `4_backend_engine/auth_rate_limit.py` | Auth/geocode/route-commit IP budgets + login lockout |
| `4_backend_engine/cost_masks.py` | Vehicular-free and steps penalty masks |
| `4_backend_engine/routing_heuristic.py` | Admissible A\* heuristics and shared reward constants |
| `4_backend_engine/pathfinding.py` | Unidirectional + bidirectional A\* (production default: uni); CSR uni Phase A |
| `4_backend_engine/graph_csr.py` | Bootstrap CSR + lat/lon for Phase A A\* (`CSR_ASTAR` kill-switch) |
| `4_backend_engine/benchmark_routing.py` | Dev script: uni vs bi on 11 routes x fast/safe presets |
| `4_backend_engine/benchmark_ellipse_precompute.py` | Dev script: ellipse filter + precompute bench (safe, 11 routes) |
| `0_documentation/route_generation_performance.md` | Route perf backlog, ellipse/precompute spec, experiment links |
| `4_backend_engine/barrier_clusters.py` | Barrier tag → cluster, penalties, debug colours |
| `4_backend_engine/route_benchmark.py` | Dev script: optimality check (h=0 vs heuristic costs) |

---

## 7. Keeping this document up to date

- **Technical spec for routing modes:** See `0_documentation/implementation.md` (cost factors, maths, frontend requirements).
- **New feature or toggle:** Update Section 3 (Features) and, if the API changes, Section 4 (API).
- **New endpoint or request params:** Update Section 4 and Section 2.2 (data flow).
- **Change of port, graph path, or stack:** Update Section 2.
- **v2 UI change:** Update §2.4, tick [`design/FUNCTIONALITY_CHECKLIST.md`](design/FUNCTIONALITY_CHECKLIST.md), append [`design/WORKING_NOTES_JUL2026.md`](design/WORKING_NOTES_JUL2026.md), and update locked decisions in [`development_protocols/V2_FRONTEND_REMODEL.md`](development_protocols/V2_FRONTEND_REMODEL.md) when a product decision changes.
- **In-ride ride feedback (TBT Report flag):** Update §4 / §5.6a and [`development_protocols/Development_Protocol_2026_08_27.md`](development_protocols/Development_Protocol_2026_08_27.md). Product spec: [`feature_requests/tbt_ride_feedback.md`](feature_requests/tbt_ride_feedback.md).

A reminder to update this file is in the top comment of `5_frontend/src/App.js` / `src/v2/App.jsx` and at the top of `4_backend_engine/app.py`.
