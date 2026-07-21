# Frontend functionality checklist — Tuned Cycling

**Purpose:** Exhaustive inventory of every behaviour in the legacy UI (`5_frontend/src/App.js` and dependencies).  
**Rebuild target:** `5_frontend/src/v2/` — tick `[x]` only when behaviour is **wired and working** in v2 (not placeholder chrome alone).

**Legend:** `—` not started · `shell` empty zone only · `partial` UI without logic · `done` full parity · `n/a` out of v2 / superseded

**Last audit:** 2026-07-21 (v2 codebase; P-15 edit confirmed)

---

## v2 rebuild progress (shell)

| Zone / layer | v2 status | Notes |
|--------------|-----------|-------|
| Map layer (Mapbox GL, quota gate) | `done` | Quota, routes, markers, Santander, Beeline casing, typed overlays, locate |
| Top-left Routing Core | `done` | Mode/bike/Santander, waypoints, vias, depart, Get Route, long-route labels, prefetch/commit |
| Top-right Profile | `done` | Pill + sidebar (auth, profiles, wizard, account, system prefs) |
| Top-center Alert Pill | `done` | Priority queue, sticky confirms, Santander/traffic/errors |
| Bottom-center Dynamic Island | `done` | Collapse/expand, metrics, elevation, charts, weather, legs, hire |
| Bottom-right Overlays + map controls | `done` | Mode rail + zoom/locate; traffic always-on |
| All routing logic | `done` | Prefetch/commit + bike_type + overlays on reveal + island analysis (minus S-11) |

**Remaining work:** AU-12 session-expired pill · optional R-18/D-04 status hints · S-11 Santander vias (known gap)

---

## 1. Routing — waypoints & flow

- [x] **R-01** Start point state `[lat, lon]` + label (`v2/App.jsx`)
- [x] **R-02** End point state `[lat, lon]` + label (`v2/App.jsx`)
- [x] **R-03** Up to 3 vias (`MAX_VIAS = 3`) (`WaypointFields.jsx`, `v2/App.jsx`)
- [x] **R-04** Map click placement cycle: start → empty via slots → end → reset (`applyMapPoint`, `handleMapClick`)
- [x] **R-05** New start clears end + vias (`v2/App.jsx`)
- [x] **R-06** Add via button (`WaypointFields.jsx`)
- [x] **R-07** Remove via (`WaypointFields.jsx`, `v2/App.jsx`)
- [x] **R-08** Drag-and-drop reorder waypoints (start/end pinned) (`WaypointFields.jsx`)
- [x] **R-09** Swap start ↔ end — v2: drag the permanent grab bars (Apple Maps structure); works with or without vias
- [x] **R-10** Location search per waypoint (`LocationSearchInput` in `WaypointFields.jsx`)
- [x] **R-11** Fly map to search selection (`v2/App.jsx` handlers)
- [x] **R-12** **Prefetch** route on waypoint/profile/weight/depart change (`purpose=prefetch`, not rate-limited) (`v2/App.jsx`)
- [x] **R-13** **Get Route** commit (`purpose=commit`, rate-limited) (`v2/App.jsx`)
- [x] **R-14** Route reveal gate — map/stats hidden until Get Route (`routeRevealed`) (`v2/App.jsx`)
- [x] **R-15** Abort in-flight route requests (`AbortController`, `routeRequestIdRef`) (`v2/App.jsx`)
- [x] **R-16** 429 rate-limit error surfacing on route (`v2/App.jsx` → alert pill)
- [x] **R-17** Long-route loading UX (>10 km) — v2: rotating copy on `GetRouteButton` (`useLongRouteButtonLabel.js`), not full-screen `RouteLoadingBike`
- [ ] **R-18** Status line (min weight, timing, profile, depart hint) (`formatRouteStatus`) — **partial:** alerts cover some cases; no dedicated status strip
- [x] **R-19** Fastest route (grey baseline on map) (`map/RouteLayers.jsx`)
- [x] **R-20** Optimized route (“safest” path, colored) (`map/RouteLayers.jsx`)
- [x] **R-21** Multi-leg routes when vias present (`legs[]`, `IslandLegPager.jsx`)
- [x] **R-22** Per-leg stats pager (swipe/arrows/dots) (`IslandLegPager.jsx` in collapsed + expanded island)
- [x] **R-23** Route query: `start_lat`, `start_lon`, `end_lat`, `end_lon`, `vias`, `purpose`, `profile_id` or weights, `depart_at` (`v2/App.jsx`) + **`bike_type` session override**

---

## 2. Depart at

- [x] **D-01** Leave now vs Depart at toggle (`v2/routing/DepartAtControl.jsx`)
- [x] **D-02** London TZ ISO `depart_at` query param (`DepartAtControl.jsx`, `v2/App.jsx`)
- [x] **D-03** Future depart banner (“Live traffic not applied…”) (`isFutureDepartAt`, `v2/App.jsx`) — via alert pill
- [ ] **D-04** Depart status hint (`formatDepartStatusHint` exported) — **partial:** helper unused; future-depart alert + trigger label only

---

## 3. Profiles & riding modes

- [x] **P-01** Load profile list `GET /profiles` (`v2/App.jsx`)
- [x] **P-02** Active profile `GET /profiles/:id` (`v2/App.jsx`)
- [x] **P-03** Persist `localStorage.activeProfileId` (default `preset_safe`) (`v2/App.jsx`)
- [x] **P-04** Profile picker — system presets + favourites in Routing Core (`ModeBikeSantanderRow.jsx`); customs in `ProfilesSection.jsx`
- [x] **P-05** Guest: presets only; wizard gated (`ProfilesSection.jsx` — sign in to create)
- [x] **P-06** Create profile wizard — 4 steps (`v2/wizard/PresetWizardShell.jsx` reuses `wizard/*` steps)
- [x] **P-07** Wizard step: Bike type (`wizard/BikeTypeStep.js`)
- [x] **P-08** Wizard step: Style preset fast/safe/leisure (`wizard/PresetStep.js`)
- [x] **P-09** Wizard step: Advanced tuning (detour budget, anchored sliders) (`wizard/AdvancedStep.js`, `wizard/budget.js`)
- [x] **P-10** Wizard step: Questions (night, surface, jam, VF checkboxes) (`wizard/QuestionsStep.js`)
- [x] **P-11** Save profile `POST /profiles` (`PresetWizardShell.jsx`)
- [x] **P-12** Load preset config `GET /preset_config` (`PresetWizardShell.jsx`)
- [x] **P-13** Routing weights via saved profile + `profile_id` on `/route` (`v2/App.jsx`); session `bike_type` override
- [x] **P-14** Profile drives routing / light gating / bike type (`profileWantsLight`, session bike) — not legacy text metadata rows
- [x] **P-15** Profile **edit** — `openWizard({ profileId })` → `PresetWizardShell` loads `GET /profiles/:id`, saves `PUT /profiles/:id` (`ProfilesSection.jsx`, `SidebarContext.jsx`)
- [x] **P-16** Profile **delete** (`DELETE /profiles/:id` in `v2/App.jsx` + `ProfilesSection.jsx`)

---

## 4. Bike types & Santander hire

- [x] **B-01** Bike types: standard, road, ebike, cargo (wizard + session override in Routing Core) (`BikeTypeStep.js`, `ModeBikeSantanderRow.jsx`)
- [x] **B-02** E-bike hill rule in wizard (`AdvancedStep.js`)
- [x] **B-03** Road bike surface auto/hidden in questions (`QuestionsStep.js`)
- [x] **S-01** Santander mode toggle (mutually exclusive with vias + depart_at) (`RoutingCoreZone.jsx`, `v2/App.jsx`)
- [x] **S-02** Hire flow: idle → pickup → dropoff → routing → done (`v2/App.jsx`)
- [x] **S-03** Station candidates `GET /santander/candidates` (`v2/App.jsx`)
- [x] **S-04** Pickup/dropoff guide pill — via alert pill
- [x] **S-05** Soft banner (low availability) — via alert pill
- [x] **S-06** Station map pins + expandable cards (`SantanderStationsLayer.jsx`) — primary/grey availability
- [x] **S-07** Unsuitable station — v2: alert confirm (not legacy modal)
- [x] **S-08** Walk legs `POST /santander/walk` + dashed paths (`v2/App.jsx`, `RouteLayers.jsx`)
- [x] **S-09** Combined walk+cycle hero stats (`hireWalkStats` → `ExpandedIsland` / `formatWalkParts`)
- [x] **S-10** Fly-to on Santander steps (`v2/App.jsx`, `MapFlyTo.jsx`)
- [ ] **S-11** **Known gap:** vias on Santander bike leg not implemented (modes mutually exclusive)

---

## 5. Overlays (display-only)

### v2 redesign (mode rail — locked 2026-07-17)

- [x] **O-V2-01** Overlay mode rail above zoom/locate (`OverlayModeRail.jsx`) — Cycleways / Parks / Surface / Hills / Light
- [x] **O-V2-02** One mode at a time; **SVG path-morph** capsule ↔ T (Motion spring 300/24, concave Bezier fillets in one `<path>`)
- [x] **O-V2-03** Default on reveal: Cycleways (`DEFAULT_OVERLAY_MODE`)
- [x] **O-V2-04** Light slot only when dark (`GET /night_status` + `night_time.is_dark`)
- [x] **O-V2-05** Typed subtype chunks from backend (`*_typed` on safest) — **connected runs** (path-adjacent merge)
- [x] **O-V2-06** Traffic always-on (Tiger Orange) with one marker per connected jam
- [x] **O-V2-07** Segment hover chip: swatch + label + connected length (steep includes `+N hm`)
- [x] **O-V2-08** Empty mode → alert pill; inactive rail click → “Get a route first…”; jams → brief alert
- [x] **O-V2-09** Beeline route casing (optimized / fastest / walk) (`RouteLayers.jsx`)
- [x] **O-V2-10** Rail always visible; muted until route revealed

#### Overlay connected-run cost (2026-07-18)

Backend merges path-adjacent typed edges into runs (`_collapse_edge_runs` in `app.py`). Bench: `4_backend_engine/bench_overlay_runs.py`.

| Metric (600-edge synthetic path, 300 repeats) | Value |
|-----------------------------------------------|-------|
| Tagged edges | ~413 |
| Connected runs | ~369 |
| Bare list copy | ~0.001 ms / call |
| Run collapse | ~0.17 ms / call |

**Verdict:** single O(n) pass; sub-millisecond on typical London routes — negligible vs A* / geometry. Keep always on.

### Legacy picker (v1 App.js only — **n/a for v2**)

- [ ] **O-01** ~~Overlay picker FAB~~ — **out of v2** (replaced by O-V2 mode rail)
- [ ] **O-02** ~~Edge overlays catalog UI~~ — **out of v2** (typed mode chunks instead)
- [ ] **O-03** ~~Point overlays catalog UI~~ — **out of v2**
- [ ] **O-04** ~~Default on reveal: TfL infrastructure~~ — **out of v2** (default Cycleways)
- [ ] **O-05** ~~Lit overlay gated in FAB~~ — **out of v2** (O-V2-04)
- [ ] **O-06** ~~Hide all overlays~~ — **out of v2**
- [ ] **O-07** ~~Catalog version `GET /overlay_catalog`~~ — **out of v2**
- [x] **O-08** Map GeoJSON line + circle layers (`map/RouteLayers.jsx` / `V2OverlayLayers.jsx`)
- [x] **O-09** Multi-leg: overlays on active leg only (`PlanningMap` / `V2OverlayLayers`)
- [ ] **O-10** ~~Steep hidden when lit on~~ — **n/a** in v2 modes
- [x] **O-11** Rail muted until route revealed (`OverlayModeRail` / map controls)

---

## 6. Map behaviour

- [x] **M-01** Mapbox GL via `react-map-gl` (`map/CycleMap.jsx` via `PlanningMap.jsx`)
- [x] **M-02** Day/night map appearance — v2: Mapbox Standard + `lightPreset` (`map/styles.js`, `MapLightPreset.jsx`), not classic streets/dark styles
- [x] **M-03** Default London view (`map/styles.js` `DEFAULT_VIEW`)
- [x] **M-04** Map load quota `POST /mapbox/map_load` before init (`map/CycleMap.jsx`)
- [x] **M-05** StrictMode dedup for quota reserve (`map/CycleMap.jsx`)
- [x] **M-06** Missing `REACT_APP_MAPBOX_TOKEN` banner (`map/CycleMap.jsx`)
- [x] **M-07** Quota exceeded denied state (`map/CycleMap.jsx`)
- [x] **M-08** Navigation control (zoom) — v2: custom +/−/locate (`MapControlsZone.jsx`)
- [x] **M-09** MapFlyTo on search / Santander (`map/MapFlyTo.jsx`)
- [x] **M-10** Markers: A start, B end, via dots (`map/PointMarkers.jsx`)
- [x] **M-11** `reuseMaps` enabled (`map/CycleMap.jsx`)
- [x] **M-12** Coord conversion `[lat,lon]` ↔ `[lng,lat]` (`map/coords.js`)
- [x] **M-13** Left click: waypoints (+ multi-leg pick when revealed) — disruption lookup / inspector dismiss **out of v2**
- [ ] **M-14** ~~Right click: segment inspector~~ — **out of v2** (legacy only)
- [ ] **M-15** ~~Disruption click-through~~ — **out of v2** (hover chip instead)
- [ ] **M-16** ~~Inspector highlight segment~~ — **out of v2**
- [x] **M-17** Walk paths dashed with primary casing (Beeline style)
- [x] **M-18** Locate control + Blue Bell disc (`useGeolocation`, `UserLocationMarker`)
- [x] **M-19** Beeline route casing on optimized / fastest (`RouteLayers.jsx`)

---

## 7. Route analysis & metrics UI

- [x] **A-01** Analysis UI when revealed — v2: Dynamic Island (`DynamicIslandZone.jsx`), not bottom-left panel
- [x] **A-02** Time/distance hero metrics (`MetricCell` in collapsed + expanded island)
- [ ] **A-03** 14 metric rows vs fastest baseline — **partial / redesigned:** ModeDonut + ModeBarCharts + elevation, not `CondensedStatRow`
- [ ] **A-04** Full legacy metric set (accidents, speed stress, junction %, etc.) — **partial:** charts cover mode-linked stats; some legacy rows not ported 1:1
- [x] **A-05** Santander combined walk+cycle in hero metrics (`IslandHireStations` / walk parts)
- [x] **A-06** Leg pager for multi-leg (`IslandLegPager.jsx`)

---

## 8. Geocoding & search

- [x] **G-01** `GET /geocode/suggest?q&session_token` (`mapboxGeocoding.js` via `WaypointFields`)
- [x] **G-02** `GET /geocode/retrieve/:id` (`mapboxGeocoding.js`)
- [x] **G-03** Mapbox session tokens (UUID per focus) (`mapboxGeocoding.js`)
- [x] **G-04** 300 ms debounce, min 2 chars (`LocationSearchInput.js`)
- [x] **G-05** Keyboard: arrows, Enter, Escape (`LocationSearchInput.js`)
- [x] **G-06** 429 monthly limit message (`mapboxGeocoding.js`)
- [x] **G-07** No client Mapbox secret — server-proxied (`mapboxGeocoding.js`)

---

## 9. Auth & account

- [x] **AU-01** AuthProvider context (`auth/AuthProvider.jsx` wraps `v2/App.jsx`)
- [x] **AU-02** Session in `localStorage` `tuned_auth_session` (`auth/sessionStore.js`)
- [x] **AU-03** Hash recovery `#access_token&refresh_token&type=recovery` (`sessionStore.js`)
- [x] **AU-04** Login `POST /auth/login` (`AuthProvider` + sidebar `AuthPanel`)
- [x] **AU-05** Signup `POST /auth/signup` (`AuthProvider` + sidebar `AuthPanel`)
- [x] **AU-06** Forgot password `POST /auth/password-reset` (`AuthProvider`)
- [x] **AU-07** Password recovery modal `POST /auth/set-password` (`PasswordRecoveryModal.jsx`)
- [x] **AU-08** Change password `POST /auth/change-password` (`AccountManageSection.jsx`)
- [x] **AU-09** Delete account (re-login + `DELETE /auth/account`) (`AccountManageSection.jsx`)
- [x] **AU-10** Sign out (`AuthProvider`, `AccountStrip.jsx`)
- [x] **AU-11** Token refresh on 401 `POST /auth/refresh` (`api/flaskClient.js`)
- [ ] **AU-12** Session expired notice — **partial:** `authNotice` set in `AuthProvider` but v2 does not surface it in the alert pill
- [x] **AU-13** Profile pill loading state (no Guest flash) (`ProfileZone.jsx`)
- [x] **AU-14** Password min length 6 (client validation)
- [x] **AU-15** Deprecated `supabaseClient.js` stub (no anon key in bundle)

---

## 10. Theme & day/night

- [x] **T-01** `data-theme` on shell + CSS variables (`MapShell.jsx`, `shell.css`, zone CSS)
- [x] **T-02** Auto night via `GET /night_status` (London sunrise/sunset) (`v2/App.jsx`, `resolveAppearance.js`)
- [x] **T-03** `REACT_APP_FORCE_MODE=day|night` (`start.js`, appearance resolution)
- [x] **T-04** Map style / light preset follows theme (`map/styles.js`, `MapLightPreset.jsx`)
- [x] **T-05** Route/overlay colors follow theme object (`v2/map/theme.js`)

---

## 11. UI chrome (legacy — replaced in v2)

- [x] **UI-01** Top bar → **v2 zones** (Routing Core + Profile + Alert Pill)
- [x] **UI-02** Route points panel → **v2 Routing Core**
- [x] **UI-03** Route analysis → **v2 Dynamic Island**
- [x] **UI-04** Overlay FAB → **v2 OverlayModeRail**
- [ ] **UI-05** ~~TfL disruption detail popup~~ — **out of v2** (hover chip + alerts)
- [ ] **UI-06** ~~TomTom disruption detail popup~~ — **out of v2**
- [ ] **UI-07** ~~Segment inspector popup~~ — **out of v2**
- [x] **UI-08** Modals/flows: wizard (sidebar morph), auth (sidebar), account manage, Santander unsuitable (alert), password recovery

---

## 12. Dev / test / hidden features

- [ ] **DEV-01** ~~Test Mode master toggle~~ — **out of v2** (legacy only)
- [ ] **DEV-02** ~~`X-Tuned-Test-Mode: 1`~~ — **out of v2**
- [ ] **DEV-03** ~~Manual weight overrides~~ — **out of v2**
- [ ] **DEV-04** ~~Admin refresh TfL~~ — **out of v2** (was Test Mode only; see note below)
- [ ] **DEV-05** ~~Admin refresh TomTom~~ — **out of v2**
- [ ] **DEV-06** ~~Admin status endpoints~~ — **out of v2**
- [ ] **DEV-07** ~~Segment inspector (right-click)~~ — **out of v2**
- [x] **DEV-08** Prefetch before Get Route — invisible to user (`v2/App.jsx`)
- [x] **DEV-09** Commit vs prefetch rate limit distinction (`v2/App.jsx`)
- [x] **DEV-10** `npm start -- --day|--night` (`start.js`)
- [x] **DEV-11** `npm start -- --v2` for rebuild shell (`start.js`)
- [x] **DEV-12** `REACT_APP_UI_VERSION=v2` entry switch (`index.js`)
- [x] **DEV-13** `reportWebVitals` wired (`index.js`) — default no-op
- [ ] **DEV-14** Stale `App.test.js` (“learn react”) — known broken (legacy)

---

## 13. Security & sensitive behaviour

| ID | Item | Legacy | v2 |
|----|------|--------|-----|
| **SEC-01** | JWT access + refresh in `localStorage` | `sessionStore.js` | ✓ shared |
| **SEC-02** | Bearer on `apiFetch` when not test mode | `flaskClient.js` | ✓ (`testMode: false`) |
| **SEC-03** | Test mode bypasses auth header | `flaskClient.js` | n/a (out of v2) |
| **SEC-04** | No Mapbox secret in client bundle | `mapboxGeocoding.js` | ✓ |
| **SEC-05** | Public `pk.` token only for map | `map/styles.js` | ✓ |
| **SEC-06** | Hash token stripped after recovery | `sessionStore.js` | ✓ |
| **SEC-07** | Delete account requires password re-verify | `AuthProvider.jsx` | ✓ |
| **SEC-08** | Admin/inspect/disruption `fetch` without auth headers — **backend must enforce** | `App.js` | n/a (endpoints unused) |

---

## 14. API endpoints (Flask `http://127.0.0.1:5000`)

| Endpoint | Used | v2 |
|----------|------|-----|
| `GET /profiles` | ✓ | ✓ |
| `GET /profiles/:id` | ✓ | ✓ |
| `POST /profiles` | ✓ | ✓ |
| `PUT /profiles/:id` | ✓ | ✓ |
| `DELETE /profiles/:id` | ✓ | ✓ |
| `GET /preset_config` | ✓ | ✓ |
| `GET /route` | ✓ | ✓ |
| `GET /santander/candidates` | ✓ | ✓ |
| `POST /santander/walk` | ✓ | ✓ |
| `GET /geocode/suggest` | ✓ | ✓ |
| `GET /geocode/retrieve/:id` | ✓ | ✓ |
| `POST /mapbox/map_load` | ✓ | ✓ |
| `GET /night_status` | ✓ | ✓ |
| `GET /weather` | ✓ | ✓ **new in v2** |
| `GET /overlay_catalog` | ✓ | — (legacy FAB only) |
| `POST /auth/login` | ✓ | ✓ |
| `POST /auth/signup` | ✓ | ✓ |
| `POST /auth/password-reset` | ✓ | ✓ |
| `POST /auth/refresh` | ✓ | ✓ |
| `POST /auth/set-password` | ✓ | ✓ |
| `POST /auth/change-password` | ✓ | ✓ |
| `DELETE /auth/account` | ✓ | ✓ |
| `GET /inspect` | ✓ | — (out of v2) |
| `GET /tfl_disruption_at` | ✓ | — (out of v2) |
| `GET /tomtom_disruption_at` | ✓ | — (out of v2) |
| `POST /admin/update_tfl` | ✓ | — (out of v2) |
| `POST /admin/update_tomtom` | ✓ | — (out of v2) |
| `GET /admin/tfl_status` | ✓ | — (out of v2) |
| `GET /admin/tomtom_status` | ✓ | — (out of v2) |

**External / proxied:** day/night via backend `GET /night_status` (sunrise-sunset); weather via `GET /weather`.

---

## 15. State management patterns (preserved in v2)

- [x] Monolithic route state in root app component (`v2/App.jsx`)
- [x] Refs: `routeRequestIdRef`, `abortRef`, `routeRevealedRef`, `santanderModeRef`
- [x] `useCallback` / `useEffect` chains for prefetch, profile, daylight
- [x] Auth via React Context only (`AuthProvider`)
- [x] `localStorage`: `activeProfileId`, `tuned_auth_session` (+ sidebar prefs via `SidebarContext`)
- [x] Derived: theme from appearance mode; weights via `profile_id` (no manual weight overrides in v2)
- [x] Map children slot pattern (Santander layers in `PlanningMap`)

---

## 16. New in v2 (not in legacy checklist)

- [x] **N-01** Route weather panel (`useRouteWeather`, `WeatherPanel`, extreme warnings)
- [x] **N-02** Elevation chart + sparkline + scrub ↔ map hover (`ElevationChart.jsx`)
- [x] **N-03** Mode donut / bar charts + `resolveIslandSlots`
- [x] **N-04** Appearance prefs: light / dark / system / auto (`resolveAppearance.js`, `SystemFooter`)
- [x] **N-05** Units: metric / imperial (`units.js`, sidebar)
- [x] **N-06** Favourite profile slots C1–C3 + reorder (`ProfilesSection` / Routing Core)
- [x] **N-07** Collapsed ↔ expanded Dynamic Island
- [x] **N-08** Session `bike_type` override in Routing Core (separate from profile default)

---

## Gaps / decisions for v2

| Item | Decision / status |
|------|-------------------|
| Profile edit (P-15) | **Done** — wizard create/edit via PUT |
| Profile delete (P-16) | **Done** |
| Mode + bike type in Routing Core | **Done** |
| Session-expired notice (AU-12) | **Open** — wire `authNotice` → alert pill |
| Status line (R-18 / D-04) | **Optional** — alerts may be enough |
| Legacy 14 metric rows (A-03/A-04) | **Superseded by design** unless parity rows requested |
| Santander + vias (S-11) | **Known gap** — mutually exclusive for now |
| Test Mode | **Out of v2** — stay in legacy only |
| Segment inspector (right-click) | **Out of v2** |
| Admin TfL/TomTom refresh | **Out of v2** — overlays still *show* server data; no v2 UI to force refresh |

---

## How to update this file

When implementing a feature in v2, change `[ ]` → `[x]` and update the **v2 rebuild progress** table. If you add new behaviour, add a row with a new ID (prefer `N-##` for v2-only) and note it here.
