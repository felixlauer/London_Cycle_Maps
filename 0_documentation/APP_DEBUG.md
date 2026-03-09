# London Cycle Maps — Debug App

Documentation for the **data-debugging / visualization app**: frontend (`8_debug/5_frontend`) and backend (`4_backend_engine/app_debug.py`). **When you add or change modes, endpoints, or architecture, update this file.**

---

## 1. Purpose

The debug app is for inspecting and validating graph data (elevation, surfaces, lighting, accidents, intersections, cycleway infra, HGV bans, traffic calming, junctions, live TfL and TomTom disruptions). It does **not** do routing. It provides overlay “modes” (uphill, accidents, surfaces, unlit, cycleway, HGV banned, traffic calming points, junction points) and a segment inspector, all backed by the same graph as the main app (`london_elev_final_tfl.graphml`) plus live accident points from PostgreSQL.

---

## 2. Architecture

### 2.1 Stack

| Layer | Tech | Location |
|-------|------|----------|
| Frontend | React 19, Leaflet, react-leaflet | `8_debug/5_frontend/src/` |
| Backend | Flask, NetworkX, Shapely, SQLAlchemy | `4_backend_engine/app_debug.py` |
| Data | GraphML + PostgreSQL (accidents) | `1_data/london_elev_final_tfl.graphml`, DB `accidents` |

### 2.2 Data flow

1. **Graph:** Loaded once at startup; pre-processed into in-memory caches (steep segments, bad-surface segments, unlit segments) for fast viewport queries. The `tfl_live` module is initialized at startup (builds STRtree edge spatial index). **Live disruption data (TfL and TomTom)** is populated via `POST /admin/update_tfl` and `POST /admin/update_tomtom` (each source refreshed independently); stored in a merged in-memory lookup and source-specific caches for overlays (not as a graph cache). See `0_documentation/GRAPH.md` §9.
2. **Overlays:** User toggles modes. Segment-based (Uphill, Surfaces, Unlit, Cycleway, HGV banned): frontend sends map bounds; backend returns segments with 20k limit when needed; Surfaces and Unlit have **subtoggles** for “no data” / “unknown” and show a 20k-limit message when truncated. Point-based: **Edge tags** — Traffic calming, Junction type (edge): points from edge midpoints, color-coded by type; left-click shows type. **Node tags** — Barriers (color-coded: cycling-relevant types, others grey), Traffic signals, Mini roundabouts, Crossing, Give way, Stop: each has its own toggle and endpoint; left-click shows type/label. Accidents: loaded once from `/accidents`; left-click shows nothing.
3. **Inspector:** Right-click → `GET /inspect` → popup + red segment overlay. Disabled when **Modify TfL** mode is on.
4. **Modify suite (bottom-left):** One mode, **Modify TfL cycle routes**. When active, the Debug panel collapses and is deactivated. Same TfL overlay (color-coded). Left click = add segment to TfL (tag), right click = remove tag. Programme (cycleway / quietway / superhighway) selected via buttons; route shortcode from closest TfL segment. Added segments drawn in yellow, removed in black. Edits saved to `3_pipeline/tfl_manual_edits.json`; apply with `3_pipeline/apply_tfl_manual_edits.py`.
5. **No routing:** No start/end, no `/route`; only visualization and inspection.

### 2.3 Backend (app_debug.py)

- **Port:** 5001 (so it can run alongside main app on 5000).
- **Graph:** Same file as main app: `1_data/london_elev_final_tfl.graphml`.
- **Caches (built at startup):**
  - **STEEP_CACHE** — edges with grade ≥ 3.3% (for uphill heatmap).
  - **SURFACE_CACHE** — segments with surface/quality issues or no surface data (see Surfaces below). When returning surfaces, **no_data** segments are limited to 20k per request (by distance from bbox centre); response includes `limit_reached` when truncated.
  - **UNLIT_CACHE** — edges whose `lit` is not in LIT_VALUES; each entry has type `"no"` or `"unknown"`. Response limited to 20k (unknown capped by centre); `include_unknown` param; frontend subtoggle and 20k message.
  - **CYCLEWAY_GENERAL** — edges with `cycleway` / `cycleway_left` / `cycleway_right` / `cycleway_both` (non-empty).
  - **CYCLEWAY_SEGREGATED** — edges with `segregated=yes`.
  - **HGV_BANNED_CACHE** — edges with `hgv=no`.
  - **TRAFFIC_CALMING_POINTS** — way-based: list of `{lat, lon, type, source: 'way'}` from edge midpoints where `traffic_calming` is set.
  - **TRAFFIC_CALMING_POINT_POINTS** — point-based: list of `{lat, lon, type, source: 'point'}` from edges with `traffic_calming_point` and stored lat/lon.
  - **JUNCTION_POINTS** — list of `{lat, lon, type}` from edge midpoints where `junction` is set (roundabout, circular, etc.).
  - **Node point caches** (from graph nodes / edges): **BARRIER_POINTS** `{lat, lon, type, details}` where `details` includes `barrier` and optionally `barrier_confidence`; **TRAFFIC_SIGNALS_POINTS**, **MINI_ROUNDABOUT_POINTS**, **CROSSING_POINTS**, **GIVE_WAY_POINTS**, **STOP_POINTS** (each `{lat, lon}`).
- **Live disruptions (TfL and TomTom)** — not a graph cache; uses shared `tfl_live`, `tomtom_live`, and `live_disruptions` modules. STRtree built at startup from graph edge geometries; data populated via `POST /admin/update_tfl` and `POST /admin/update_tomtom` (independent refresh per source). Merged lookup used for routing in main app; debug app exposes separate TfL and TomTom overlay toggles and status endpoints.
- **Segment/point limits:** Surfaces, Unlit, cycleway layers, HGV banned, and all point endpoints apply a **20k limit** (prioritised by distance from viewport centre) when the result set exceeds 20k.
- **PostgreSQL:** Used only for `GET /accidents` (all accident points).
- **Inspector:** Same logic as main app: nearest node → nearest edge → tags + geometry; response includes `source` and `target` (node ids). No routing.
- **Modify TfL:** `GET /modify/tfl_edits` returns current edits with geometry. `POST /modify/tfl_add` and `POST /modify/tfl_remove` persist to `3_pipeline/tfl_manual_edits.json`. `POST /modify/tfl_undo` pops the last operation from a history stack and updates the file; returns new `added`/`removed` with geometry (back arrow and Ctrl+Z in the UI).

### 2.4 Frontend (8_debug/5_frontend)

- Separate React app (copy of CRA structure); main UI in `App.js`.
- Collapsible **Debug panel** (top-right): toggles for Uphill, Accidents, Surfaces, Unlit, Cycleway, HGV banned, TfL cycle routes, **TfL Live Disruptions**, **TomTom Live Disruptions**, Traffic calming, Junction type, **Node tags** (Barriers, Traffic signals, etc.). Left-click on point overlays shows type; right-click opens segment inspector. When **Modify TfL** is on, the Debug panel is forced collapsed and inspector is disabled.
- **Modify suite** (bottom-left): collapsible panel; one mode **Modify TfL cycle routes**. When on: TfL overlay is shown; left click = add segment (yellow), right click = remove (black). **Undo:** back arrow button or **Ctrl+Z** / Cmd+Z; removes last operation from the map and from the edits file. Programme chosen via Cycleway / Quietway / Superhighway buttons; route from closest TfL segment. Edits saved to file automatically.
- No start/end markers, no route polylines — only overlay polylines, point markers, inspector, and modify overlays.

---

## 3. Features (modes and inspector)

### 3.1 Uphill

- **Toggle:** “Uphill”
- **Backend:** `GET /debug/heatmap?min_lat=&max_lat=&min_lon=&max_lon=` returns steep segments (grade ≥ 3.3%) in view.
- **Display:** Polylines coloured by grade: purple (≥40%, artifact), red (&gt;7.5%), gold (3.3–7.5%).
- **Legend:** Artifact / Steep / Moderate; “Descents & Flat hidden.”

### 3.2 Accidents

- **Toggle:** “Accidents”
- **Backend:** `GET /accidents` returns all accident points `[[lat, lon], ...]` from PostgreSQL (no limit).
- **Display:** Red circle markers at each point; loaded once when toggle is first turned on.
- **Legend:** “Cyclist collision location”.

### 3.3 Surfaces

- **Toggle:** “Surfaces”. **Subtoggle:** “No surface data” — when off, no-data segments are not requested (backend param `include_no_data=0`) and not drawn; when on, they are included and limited to 20k (centre-prioritised); if truncated, the UI shows “20k limit — zoom in to see areas with no tags”.
- **Backend:** `GET /debug/surfaces?min_lat=&max_lat=&min_lon=&max_lon=&include_no_data=0|1` returns `{ "segments": [...], "limit_reached": boolean }`. Segments have `{ id, t, s, p }` where `t` is `"surface"` | `"cycleway_surface"` | `"smoothness"` | `"no_data"`.
- **Display:** Polylines coloured by value. **No surface data** uses blue-grey `#546E7A` (more visible than grey).
- **Legend (8 options):** Cobblestone/Sett, Gravel/Grit, Grass, Dirt/Earth/Mud, Sand/Wood, Other unpaved, Bad smoothness, No surface data.

### 3.4 Unlit

- **Toggle:** “Unlit”. **Subtoggle:** “No data (unknown)” — when off, only confirmed unlit (`t=no`) segments are drawn; when on, both “no” and “unknown” are drawn.
- **Backend:** `GET /debug/unlit?min_lat=&max_lat=&min_lon=&max_lon=` returns segments not confirmed lit.
- **Display:** Dark blue = confirmed unlit, light blue = no data (unknown).

### 3.5 Cycleway

- **Toggle:** “Cycleway”. **Subtoggles:** General (lane/track etc), Segregated only. Each requests `GET /debug/cycleway?layer=general|segregated&min_lat=...` and draws segments (green shades). 20k limit per layer when truncated.

### 3.6 HGV banned

- **Toggle:** “HGV banned”
- **Backend:** `GET /debug/hgv_banned?min_lat=&max_lat=&min_lon=&max_lon=` returns segments where `hgv=no`. 20k limit when truncated.
- **Display:** Polylines in dark red/orange.

### 3.7 Traffic calming (points)

- **Toggle:** “Traffic calming (points)”. **Source dropdown:** Way (OSM ways), Point (OSM nodes), Both — refetches with `source=way|point|both`.
- **Backend:** `GET /debug/traffic_calming_points?min_lat=&max_lat=&min_lon=&max_lon=&source=way|point|both` returns `[{ lat, lon, type, source }, ...]` (way = edge midpoints with `traffic_calming`; point = edges with `traffic_calming_point` at stored position; both = merged list). 20k limit when truncated.
- **Display:** Circle markers **color-coded by type** (e.g. table, cushion, choker, hump). **Left-click** on a point shows the calming type and source (way/point) in a small popup.

### 3.8 Junction type (edge)

- **Toggle:** “Junction type (edge)”
- **Backend:** `GET /debug/junction_points?min_lat=&max_lat=&min_lon=&max_lon=` returns `[{ lat, lon, type }, ...]` (edge midpoints with `junction` tag: roundabout, circular, etc.). 20k limit when truncated.
- **Display:** Circle markers **color-coded by type** (roundabout, circular, approach, etc.). **Left-click** on a point shows the junction type in a small popup.

### 3.9 Node tags (point overlays)

- **Barriers** — `GET /debug/barrier_points?min_lat=&max_lat=&min_lon=&max_lon=` returns `[{ lat, lon, type, details }, ...]` from edges with `barrier` (details include `barrier` and optionally `barrier_confidence`). **Display:** Color-coded by type; cycling-relevant types get distinct colours; others in grey. Left-click shows barrier type and confidence (if present).
- **Traffic signals** — `GET /debug/traffic_signals_points` (same bbox). Nodes with `traffic_signals`. Red markers; left-click “Traffic signals”.
- **Mini roundabouts** — `GET /debug/mini_roundabout_points`. Purple markers; left-click “Mini roundabout”.
- **Crossing** — `GET /debug/crossing_points`. Blue markers; left-click “Crossing”.
- **Give way** — `GET /debug/give_way_points`. Orange markers; left-click “Give way”.
- **Stop** — `GET /debug/stop_points`. Dark orange markers; left-click “Stop”.
- All node point endpoints apply 20k limit when truncated.

### 3.10 Segment inspector

- **Trigger:** Right-click on map.
- **Backend:** `GET /inspect?lat=&lon=` (same as main app). Returns all edge tags (including empty); `length` is rounded to the nearest metre. When the edge has live disruption data, response also includes `tfl_live_category`, `tfl_live_severity`, `tfl_live_description` in a "Live disruptions" group.
- **Display:** Inspector window with tags grouped (Identity & geometry, Surface & quality, Cycleway, Strategic networks, Traffic & stress, Elevation, Other). Empty or missing values shown as “—”. When an edge has live disruption data, inspector also shows `tfl_live_category`, `tfl_live_severity`, `tfl_live_description` in a "Live disruptions" group. Multi-column layout (1–3 columns) and dynamic width so the panel stays on screen; max height with scroll so it does not extend below the map. Red segment overlay; position offset so the segment remains visible.
- **Hint in panel:** “Right-click any road to inspect segment tags.”


### 3.11 TfL Live Disruptions

- **Toggle:** "TfL Live Disruptions". **Refresh button** fetches latest data from TfL API via `POST /admin/update_tfl`; status text shows count and last update time.
- **Backend:** `GET /debug/tfl_disruptions?min_lat=&max_lat=&min_lon=&max_lon=` returns segments from the live disruption visualization cache; 20k limit.
- **Display:** Polylines color-coded by disruption type: Red = closure, Orange = incident, Yellow = works, Blue = diversion, Grey = other.
- **Legend:** Closure, Incident, Works, Diversion, Other.
- **Submode — Show TfL ground truth:** When on, displays the **exact geometries from the TfL API** (points, lines, polygons) as overlay: purple circle markers for point locations, dashed purple polylines for line geometries, semi-transparent purple polygons for polygon geometries. Data from `GET /debug/tfl_disruptions_raw` (bbox-filtered). Use to compare matched graph edges with the raw TfL data.
- **Left-click on disruption:** When TfL Live Disruptions is on, **left-click** on a disruption (either the matched segments overlay, or the ground-truth point/line/polygon, with a slightly larger hit margin) opens a **TfL disruption detail window** (inspector-style) showing **all data TfL parses** for that disruption (id, status, category, severity, location, comments, point, geography, geometry, roadDisruptionLines, etc.). Hit-test uses `GET /debug/tfl_disruption_at` (tolerance ~25 m). Closing the window or right-clicking (inspector) clears it.
- **Inspector enrichment:** When right-clicking an affected edge, the inspector shows `tfl_live_category`, `tfl_live_severity`, `tfl_live_description` in a "Live disruptions" group; for TomTom-sourced (or merged) edges, also `tfl_live_iconCategory`, `tfl_live_magnitudeOfDelay`.

### 3.12 TomTom Live Disruptions

- **Toggle:** "TomTom Live Disruptions". **Refresh button** fetches latest data from TomTom Traffic Incident API v5 via `POST /admin/update_tomtom`; status text shows count and last update time (from `GET /admin/tomtom_status`).
- **Backend:** `GET /debug/tomtom_disruptions?min_lat=&max_lat=&min_lon=&max_lon=` returns segments from the TomTom visualization list (matched to graph edges via the same STRtree as TfL); 20k limit. Segments include `source: "tomtom"`, `iconCategory`, `magnitudeOfDelay`, `description`.
- **Display:** Polylines color-coded by TomTom cluster: Red = closure (A), Orange = roadworks (B), Yellow = jam (C), Blue/dashed = environmental (D), Grey = other.
- **Left-click on disruption:** When TomTom Live Disruptions is on, **left-click** on a TomTom segment opens a **TomTom disruption detail window** with the full incident payload. Hit-test uses `GET /debug/tomtom_disruption_at` (lat, lon, optional tolerance).
- **Inspector enrichment:** Same as TfL (Section 3.10): when an edge is affected by TomTom (or merged) data, inspector shows the same "Live disruptions" group including `tfl_live_iconCategory` and `tfl_live_magnitudeOfDelay` where present.

---

## 4. API (backend)

| Method | Endpoint | Query params | Response |
|--------|----------|--------------|----------|
| GET | `/debug/heatmap` | `min_lat`, `max_lat`, `min_lon`, `max_lon` | Array of `{ id, g, p }` |
| GET | `/debug/surfaces` | same + `include_no_data` (0\|1) | `{ segments: [{ id, t, s, p }], limit_reached }` — `t`: surface \| cycleway_surface \| smoothness \| no_data |
| GET | `/debug/unlit` | same + `include_unknown` (0\|1) | `{ segments: [...], limit_reached }` — segments have `id`, `t`, `p` |
| GET | `/debug/cycleway` | same + `layer` (general\|segregated) | `{ segments: [...], limit_reached }` — segments have `id`, `p`, optional `v` |
| GET | `/debug/hgv_banned` | min_lat, max_lat, min_lon, max_lon | `{ segments: [{ id, p }], limit_reached }` |
| GET | `/debug/traffic_calming_points` | min_lat, max_lat, min_lon, max_lon, **source** (way \| point \| both) | Array of `{ lat, lon, type, source }` (20k limit) |
| GET | `/debug/junction_points` | same | Array of `{ lat, lon, type }` (20k limit) |
| GET | `/debug/barrier_points` | same | Array of `{ lat, lon, type, details }` (details: barrier, optional barrier_confidence; 20k limit) |
| GET | `/debug/traffic_signals_points` | same | Array of `{ lat, lon }` (20k limit) |
| GET | `/debug/mini_roundabout_points` | same | Array of `{ lat, lon }` (20k limit) |
| GET | `/debug/crossing_points` | same | Array of `{ lat, lon }` (20k limit) |
| GET | `/debug/give_way_points` | same | Array of `{ lat, lon }` (20k limit) |
| GET | `/debug/stop_points` | same | Array of `{ lat, lon }` (20k limit) |
| GET | `/accidents` | — | Array of `[lat, lon]` (all accidents) |
| GET | `/inspect` | `lat`, `lon` | `{ tags, geometry, source, target }` or `{ error }`; when edge has live disruption: `tfl_live_category`, `tfl_live_severity`, `tfl_live_description`; for TomTom also `tfl_live_iconCategory`, `tfl_live_magnitudeOfDelay` |
| POST | `/admin/update_tfl` | — | `{ ok, message, count }` — fetch TfL Road Disruptions, rebuild master lookup |
| POST | `/admin/update_tomtom` | — | `{ ok, message, count }` — fetch TomTom Traffic Incidents, rebuild master lookup |
| GET | `/admin/tfl_status` | — | `{ loaded, edge_count, disruption_count, last_update, error }` (TfL only) |
| GET | `/admin/tomtom_status` | — | `{ loaded, edge_count, last_update, error }` (TomTom only) |
| GET | `/debug/tfl_disruptions` | min_lat, max_lat, min_lon, max_lon | `{ segments: [{ id, p, type, severity, category, description }], limit_reached }` |
| GET | `/debug/tomtom_disruptions` | min_lat, max_lat, min_lon, max_lon | `{ segments: [{ id, p, type, source: "tomtom", iconCategory, magnitudeOfDelay, description }], limit_reached }` |
| GET | `/debug/tfl_disruptions_raw` | min_lat, max_lat, min_lon, max_lon | `{ points: [{ type, coordinates: [lat,lon], ... }], lines: [{ type, coordinates: [[lat,lon],...], ... }], polygons: [...], limit_reached }` — TfL ground-truth geometries |
| GET | `/debug/tfl_disruption_at` | lat, lon, optional tolerance | `{ disruptions: [ ...full TfL API objects... ] }` — disruptions at click (raw geometry + matched segments hit-test) |
| GET | `/debug/tomtom_disruption_at` | lat, lon, optional tolerance | `{ disruptions: [ ...TomTom incident objects... ] }` — TomTom disruptions at click |
| GET | `/modify/tfl_edits` | — | `{ added: [{ source, target, programme, route, geometry }], removed: [{ source, target, geometry }] }` |
| POST | `/modify/tfl_add` | JSON: `lat`, `lon`, `programme` | `{ source, target, programme, route, geometry }` or `{ error }`; appends to file |
| POST | `/modify/tfl_remove` | JSON: `lat`, `lon` | `{ source, target, geometry }` or `{ error }`; appends to file |
| POST | `/modify/tfl_undo` | — | `{ ok, undone, added, removed }` or `{ error }` (400 if nothing to undo); removes last add/remove from file |

---

## 5. Constants (backend)

- **BAD_SURFACES:** Same list as main app (surfaces penalised for “Road Bike”); used for road `surface` and `cycleway_surface` in the surfaces overlay.
- **BAD_SMOOTHNESS:** `['bad', 'very_bad', 'horrible', 'impassable']` — used for the surfaces overlay when `smoothness` is tagged.
- **LIT_VALUES:** `['yes', 'true', '24/7', 'on', 'designated']` — only these count as lit; everything else is cached for Unlit (and optionally typed as `no` vs `unknown`).

---

## 6. File overview

| Path | Role |
|------|------|
| `8_debug/5_frontend/src/App.js` | Map, debug panel, **ModifyPanel** (bottom-left), toggles, layers, MapEvents, PointPopup, inspector, modify TfL add/remove |
| `4_backend_engine/app_debug.py` | Flask app, graph load, caches, debug endpoints, `/inspect` (with source/target), `/modify/tfl_edits`, `/modify/tfl_add`, `/modify/tfl_remove`, `/accidents` |
| `4_backend_engine/tfl_live.py` | TfL live disruption module (STRtree, API fetch, spatial matching); used by live_disruptions |
| `4_backend_engine/tomtom_live.py` | TomTom Traffic Incident API v5 (fetch, cluster mapping, spatial match via tfl_live STRtree) |
| `4_backend_engine/live_disruptions.py` | Unified live disruptions: safe update (TfL + TomTom), MASTER_LIVE_LOOKUP merge, O(1) get_edge_disruption |

---

## 7. Keeping this document up to date

- **New overlay mode:** Add subsection under Section 3, document endpoint in Section 4, update Section 2.2 and 2.3 (caches if applicable).
- **New endpoint or cache:** Update Section 4 and Section 2.3.
- **Change of port or graph path:** Update Section 2.
- **Change of BAD_SURFACES / BAD_SMOOTHNESS / LIT_VALUES or overlay logic:** Update Section 3 and Section 5.
- **Change of live disruption APIs (TfL / TomTom):** Update Section 3.11–3.12 and Section 4; sync with `0_documentation/GRAPH.md` §9 and `APP_MAIN.md` §4.1.

A reminder to update this file is in the top comment of `8_debug/5_frontend/src/App.js` and at the top of `4_backend_engine/app_debug.py`.
