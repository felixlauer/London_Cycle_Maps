# London Cycle Maps — Graph Documentation

This document describes **what data is parsed**, **how the routing graph is built**, and **how it is processed** end-to-end. Keep this file up to date whenever you change the pipeline or add/remove tags.

**Related docs:** `0_documentation/TASKS.md` (task list), `0_documentation/APP_MAIN.md` (main app), `0_documentation/APP_DEBUG.md` (debug app).

---

## 1. Pipeline Overview

The graph is produced by a multi-stage pipeline. Order matters.

| Step | Script | Input | Output | Purpose |
|------|--------|--------|--------|---------|
| 1 | `import_roads.py` | OSM shapefile | PostgreSQL `planet_osm_*` (or `ways`) | Load road network |
| 2 | `preprocess_data.py` + `import_data.py` | UK accident CSVs | PostgreSQL `accidents` | Load cyclist collisions |
| 3 | `calculate_risk.py` | DB: ways + accidents | DB: `accident_count` on `ways` + sync to `planet_osm_line` | Match accidents to segments (e.g. within 15 m) |
| 3b | **`noded_network.py`** | `planet_osm_line` (highways) | **`planet_osm_line_noded_enriched`** (materialized view) | Split lines at intersections; preserve parent `osm_id` and tags |
| 4 | **`build_graph.py`** | `planet_osm_line_noded_enriched` + points | **`london.graphml`** + **`london.gpickle`** | Build directed graph + intersections |
| 5 | `Add_elevation_raster.py` | `london.gpickle` (or `.graphml`) + LIDAR VRT | **`london_elev_raw.gpickle`** | Add node elevation + edge `grade` |
| 6 | `elevation_processing_aggressive.py` | `london_elev_raw.gpickle` | **`london_elev_final.gpickle`** | DEM smooth (optional), hill-length filter, cap grades |
| 6b | **`fetch_osm_park_polygons.py`** *(manual, once)* | Local **`1_data/*.osm.pbf`** (preferred) or Overpass | **`1_data/osm_park_polygons.geojson`** | `leisure=park` + `landuse=recreation_ground` polygons (not gardens) |
| 6c | **`tag_attractions_osm.py`** | `london_elev_final.gpickle` + park GeoJSON | same path (in-place) | `is_park=yes` where edge ≥50% inside OSM park polygon |
| 7 | **`tag_tfl_routes.py`** *(optional)* | `london_elev_final.gpickle` + TfL GeoJSON | `london_elev_final_tfl.*` | Geometry-based TfL tags; skip with `--skip-tagging` when export JSON is ground truth |
| 7b | **`apply_tfl_export.py`** | `tfl_edges_from_graph.json` + legacy graph | **`london_elev_final_tfl.gpickle`** (+ `.graphml`) | Restore master export via `osm_id` fan-out (`--legacy-graph`) |
| 7c | **`apply_tfl_manual_edits.py`** | `tfl_manual_edits.json` + legacy graph | same final graph | Layer debug-app add/remove deltas via `osm_id` |
| 7d | **`apply_attraction_manual.py`** | `attraction_manual_regions.json` | same final graph | Manual park/river/sight regions → `is_*` flags + `attraction_name` |

**Fast I/O (`3_pipeline/graph_io.py`):** Pipeline scripts and backends load via `load_graph()` — prefer a companion **`.gpickle`** when present. GraphML newer than pickle by less than **24 hours** still loads pickle (dual-save writes pickle before GraphML). Larger gaps fall back to GraphML (manual external edit). Intermediate steps (5–6) write **pickle only**. GraphML is written at **build** and **final TfL tag** for external compatibility.

**Resume:** `python run_graph_pipeline.py --start-at Add_elevation_raster.py` skips earlier steps; requires upstream `.gpickle` files in `1_data/`.

**The backend and debug app load `london_elev_final_tfl.gpickle` at startup** (fallback: `london_elev_final_tfl.graphml`). Produced by the TfL final stage below. All attributes from `build_graph.py` are preserved through elevation; elevation scripts only add/change `elevation` (nodes) and `grade` (edges).

**Current runtime graph (noded mesh, June 2026):** ~**1.92M** nodes, ~**4.06M** directed edges, ~**70 100 km** network length (sum of edge lengths). Pre-noding baseline was ~175k nodes / ~350k edges (~28 000 km). Keep a backup of the pre-noding graph at **`1_data/legacy_graph.graphml`** for TfL export/manual migration (`--legacy-graph`).

**One command (recommended):**
```text
python run_graph_pipeline.py
python run_graph_pipeline.py --skip-tagging --pickle-only
```
Default flow: **`tag_attractions_osm.py`** (needs `osm_park_polygons.geojson`) → optional TfL: `tag_tfl_routes.py` → **`apply_tfl_export.py`** (ground truth) → **`apply_tfl_manual_edits.py`** → **`apply_attraction_manual.py`**. Use **`--skip-tagging`** when the export JSON is authoritative. **`--skip-osm-attractions`** / **`--skip-attraction-manual`** skip attraction steps. **`--legacy-graph`** (default `1_data/legacy_graph.graphml` if present) maps old `(source,target)` node ids to **`osm_id`** and fans out tags on the noded mesh. Also: `--from-db`, `--start-at SCRIPT`, `--skip-export`, `--skip-manual`, `--pickle-only`.

**Manual pipeline commands (`3_pipeline/`):**
```text
python fetch_osm_park_polygons.py           # once: cache OSM parks (auto-uses local .pbf if present)
python fetch_osm_park_polygons.py --source overpass   # optional: remote Overpass (can 504)
python tag_attractions_osm.py               # OSM parks → is_park on london_elev_final
python elevation_processing_aggressive.py --skip-dem   # fast: hill filter only (see §7)
python elevation_processing_aggressive.py              # full: DEM smooth + hill filter (slow at 4M edges)
python tag_tfl_routes.py                    # optional geometry tags → london_elev_final_tfl
python apply_tfl_export.py --legacy-graph ../1_data/legacy_graph.graphml
python apply_tfl_manual_edits.py --legacy-graph ../1_data/legacy_graph.graphml
python apply_attraction_manual.py --pickle-only
```

---

## 2. Data Sources

### 2.1 Line data: `planet_osm_line` → `planet_osm_line_noded_enriched`

- **Raw OSM:** `planet_osm_line` (osm2pgsql import) is **not** modified. Highways: `WHERE highway IS NOT NULL`.
- **Noding:** [`noded_network.py`](../3_pipeline/noded_network.py) builds `planet_osm_line_noded` (split segments at intersections) and materialized view **`planet_osm_line_noded_enriched`**, joining parent tags by `osm_id`. Uses **pgRouting 4** `pgr_separateCrossing` + `pgr_separateTouching` when available (auto-`CREATE EXTENSION pgrouting`); otherwise **PostGIS** per-vertex split (`--postgis-only` to skip pgRouting).
- **Graph build:** [`build_graph.py`](../3_pipeline/build_graph.py) reads **`planet_osm_line_noded_enriched`** by default (`--source planet_osm_line` for A/B comparison).
- **Geometry:** WGS84 (SRID 4326), length in meters via `ST_Length(geography)`.
- **Risk:** `COALESCE(ways.accident_count, planet_osm_line.accident_count, 0)` on enriched segments (`calculate_risk.py` updates `ways` and syncs to `planet_osm_line`; `noded_network.py` refreshes propagation before the materialized view is built).

### 2.2 Point data: `planet_osm_point`

- **Filter:**  
  `highway IN ('traffic_signals','mini_roundabout','crossing','give_way','stop')` **OR** `barrier IS NOT NULL`
- **Node snap:** **Traffic_signals**, **mini_roundabout**, and **crossing** points are snapped to the **nearest graph node** (KD-tree). If distance &gt; `SNAP_THRESHOLD` (~20 m), the point is discarded. Attributes are stored on the node (see Section 4).
- **Edge snap:** **Barrier**, **give_way**, and **stop** points are snapped to the **nearest edge** (STRtree over edge geometry). The **original OSM position** is stored on the edge so overlays plot a **point at that location**, not the whole segment. **Barrier:** both directions (u,v) and (v,u) get the same barrier and position. **Kerb** barriers are assigned **only to pedestrian ways** (footway, pedestrian, path, steps); if no such edge is within the snap threshold, the kerb is skipped. Other barriers get a **barrier_confidence** (0–1): straight segments use orthogonal distance (linear scale, 4 m threshold); curved segments get 0.5. **Give_way / stop:** only the edge that **ends** at the sign is tagged (direction rule), with a stricter threshold (`SNAP_THRESHOLD_SIGN`) so the sign hits the correct road. See Section 3.6.
- **Traffic calming (points):** **planet_osm_point** rows with non-empty `traffic_calming` are loaded in a separate query and snapped to edges in **step 4c**. Car-allowed edges are preferred; if a cycleway is within 1.15× the distance of the nearest car-allowed edge, the cycleway is used. Fallback to any edge within threshold. Stored in **separate** edge fields: `traffic_calming_point`, `traffic_calming_point_lat`, `traffic_calming_point_lon`. **Way relay (step 4d):** `table`/`cushion`/etc. on footway/pedestrian ways are copied to **all** crossing car-allowed and cycleway edges, then cleared on the footway. See Section 3.5.

---

## 3. Edge Attributes (Segments)

All of the following are stored on **every edge** in the graph produced by `build_graph.py`. Empty/missing DB values are stored as empty string `""`.

### 3.1 Identity & geometry

| Tag | Type | Description |
|-----|------|-------------|
| `osm_id` | string | OSM way id |
| `name` | string | Street name |
| `type` | string | OSM `highway` value (e.g. primary, cycleway) |
| `length` | float | Length in meters |
| `risk` | float | Accident count for segment (from DB) |
| `geometry` | string | WKT linestring (WGS84) |

### 3.2 Physical & road

| Tag | Description |
|-----|-------------|
| `surface` | Road surface (e.g. asphalt, gravel) |
| `lit` | Lighting: yes / no / 24/7 etc. |
| `maxspeed` | Speed limit (as in OSM, e.g. "20 mph") |
| `width` | Width (OSM value) |
| `bridge` | Bridge tag |
| `tunnel` | Tunnel tag |
| `junction` | Junction type (e.g. roundabout) |
| `smoothness` | Smoothness (e.g. excellent, good, bad) |

### 3.3 Cycleway infrastructure (side-specific)

| Tag | Description |
|-----|-------------|
| `cycleway` | General cycleway (e.g. lane, track) |
| `cycleway_left` | Left side: track, lane, share_busway, shoulder |
| `cycleway_right` | Right side |
| `cycleway_both` | When both sides are the same |
| `segregated` | yes / no — physical separation from traffic |
| `cycleway_separation` | General: bollard, kerb, planter, flex_post |
| `cycleway_left_separation` | Left side separation |
| `cycleway_right_separation` | Right side separation |
| `cycleway_buffer` | Painted buffer: yes, marking, or width |
| `cycleway_width` | Width of cycle facility |
| `cycleway_surface` | Surface of cycle facility |
| `cycleway_smoothness` | Smoothness of cycle facility |

### 3.4 Strategic cycling networks

| Tag | Description |
|-----|-------------|
| `lcn_ref` | Local Cycle Network (e.g. Q1, C4 — Quietway/Cycleway) |
| `rcn_ref` | Regional Cycle Network (orbital routes) |
| `ncn_ref` | National Cycle Network (e.g. NCN 1) |
| `cycle_network` | Network name (e.g. London Cycle Grid) |

### 3.5 Traffic & stress

| Tag | Description |
|-----|-------------|
| `hgv` | HGV access (e.g. no, designated) |
| `traffic_calming` | From **planet_osm_line** (way tag): e.g. bump, hump, cushion, choker |
| `traffic_calming_point` | From **planet_osm_point** (step 4c): value from point tag when snapped to this edge |
| `traffic_calming_point_lat`, `traffic_calming_point_lon` | Original OSM position of the calming point (for plotting) |

**Source:** **Way-based:** `traffic_calming` is read from **planet_osm_line** and copied onto graph edges; step **4d** relocates table/cushion tags from pedestrian ways onto every crossing carriageway/cycleway. **Point-based:** Step 4c snaps **planet_osm_point** rows to edges (car-allowed preferred, cycleway when closer); written only to `traffic_calming_point` and lat/lon fields.

**OSM density (output of `python 6_verification/check_traffic_calming_density.py`):**

| Source | Total | With traffic_calming | % |
|--------|-------|----------------------|---|
| planet_osm_line (highway IS NOT NULL) | 545,811 | 2,416 | 0.44% |
| planet_osm_point | 805,480 | 50,430 | 6.26% |

So most calming in OSM is tagged on **points** (nodes); the pipeline currently uses only the line data.

**All values — planet_osm_line (ways):**

| Value | Count |
|-------|-------|
| table | 1,534 |
| cushion | 613 |
| choker | 112 |
| hump | 50 |
| yes | 42 |
| bump | 25 |
| chicane | 12 |
| rumble_strip | 12 |
| none | 5 |
| island | 4 |
| no | 4 |
| planter | 2 |
| choker;table | 1 |

**All values — planet_osm_point (nodes):**

| Value | Count |
|-------|-------|
| hump | 26,923 |
| cushion | 10,867 |
| table | 7,049 |
| bump | 2,331 |
| island | 1,671 |
| choker | 1,059 |
| yes | 373 |
| rumble_strip | 50 |
| chicane | 48 |
| no | 19 |
| choked_table | 8 |
| hump;cushion | 6 |
| table;choker | 4 |
| choker;hump | 3 |
| table;hump | 2 |
| choked_cushion | 2 |
| mini_bumps | 2 |
| painted_table | 2 |
| painted_island | 1 |
| hump;table | 1 |
| cushion;choker | 1 |
| bump;choker | 1 |
| choked_island | 1 |
| hump;bump | 1 |
| bump;cushion | 1 |
| cushion;hump | 1 |
| choker;island | 1 |
| hump;choker | 1 |
| cushion; choker | 1 |

To re-run the check or get highway-type breakdown on lines: **`python 6_verification/check_traffic_calming_density.py`** (optionally `--breakdown`).

### 3.6 Point-derived (edge-snapped): barrier, give_way, stop_sign

| Tag | Description |
|-----|-------------|
| `barrier` | Barrier type (e.g. bollard, gate) from planet_osm_point snapped to this edge |
| `barrier_lat`, `barrier_lon` | **Original OSM position** of the barrier (for plotting a point only, not the segment) |
| `barrier_confidence` | Float 0–1. Kerbs on pedestrian ways: 1.0. Other barriers: straight segments use orthogonal distance (4 m threshold, linear 1→0); curved (length/straight_line &gt; 1.05) → 0.5. Used to scale barrier penalty in routing. |
| `give_way` | `"yes"` only on the edge that **ends** at the give-way sign |
| `give_way_lat`, `give_way_lon` | Original OSM position of the sign |
| `stop_sign` | `"yes"` only on the edge that **ends** at the stop sign |
| `stop_sign_lat`, `stop_sign_lon` | Original OSM position of the sign |

**Source:** `build_graph.py` snaps barrier/give_way/stop points to the nearest edge (Shapely STRtree + point-to-line distance). **Barrier rules:** **Kerb** is assigned only to edges whose `type` is in pedestrian highway types (footway, pedestrian, path, steps); if none within threshold, the kerb is not assigned. **Other barriers:** closest edge (any type); confidence is computed from segment straightness and orthogonal distance (metres). Overlays and routing use the stored position to draw a single point at the barrier/sign location.

### 3.7 TfL cycle routes (added by `tag_tfl_routes.py`)

| Tag | Description |
|-----|-------------|
| `tfl_cycle_programme` | Programme category: `cycleway`, `quietway`, `superhighway` (semicolon-separated if multiple) |
| `tfl_cycle_route` | Short route name/label (e.g. C1, CS7, Q15); semicolon-separated if edge is on multiple routes |

**Source:** TfL GeoJSON `1_data/tfl_raw/routes/Cycle_routes.json` (Cycleways, Quietways, Cycle Superhighways). **Pass 1:** cycle-infrastructure only (excluding footway/pedestrian/steps); alignment ≥50%; **angularity only for edges &lt;20 m** (longer edges skip angular check). **Coverage:** target matched length ≥1.8× segment length (one-way); cap at 3×. **Iterative relaxed pass:** while any segment is under 1.8×, match against relaxed edge set (excluding motorway/trunk/footway/pedestrian/steps), same alignment and angular-only-if-short, without exceeding 3× per segment. Debug output: TfL network length vs matched length and ratio vs 2× one-way. Run after elevation: `python tag_tfl_routes.py --input ../1_data/london_elev_final.graphml`. Manual edits from the debug app (Modify TfL mode) are stored in **`3_pipeline/tfl_manual_edits.json`** (includes a `history` array for undo). Apply them with **`python apply_tfl_manual_edits.py`**; that script tags both edge directions (u,v) and (v,u) when the reverse edge exists in the directed graph.

**Export and re-apply (after re-running build/elevation):** Re-running the graph build loses TfL tags. **`3_pipeline/tfl_edges_from_graph.json`** is the **master export / ground truth** (create with **`extract_tfl_from_graph.py`**). After a fresh build, run **`apply_tfl_export.py`** with **`--legacy-graph`** pointing at the pre-noding graph backup (e.g. `1_data/legacy_graph.graphml`). The script resolves each export `(source, target)` to parent **`osm_id`** via the legacy graph and applies merged tags to **all** split sub-edges on the new mesh (`tfl_osm_translate.py`). Then run **`apply_tfl_manual_edits.py`** (same legacy lookup) for add/remove deltas from the debug app.

**TfL pipeline tradeoffs (ground truth = export JSON):**

| Topic | Behaviour |
|-------|-----------|
| **Export vs geometry tagging** | When `tfl_edges_from_graph.json` exists, use **`--skip-tagging`** in `run_graph_pipeline.py`. Export **zeros all** TfL tags then restores from JSON — any tags from `tag_tfl_routes.py` in the same run are discarded. |
| **osm_id fan-out** | One old coarse edge → all directed sub-edges with the same `osm_id`. Coarser than per-segment restore; consistent with manual edit migration. |
| **Removals not in export** | Export only lists edges **with** TfL tags. Tags removed in the debug app (right-click remove) are **not** stored as “negative” records in the JSON — only **`tfl_manual_edits.json`** `removed` list captures those. After rebuild, removals are re-applied via **`apply_tfl_manual_edits.py`**, not the export file. |
| **Legacy graph** | Required after noded rebuild: must be the graph whose node ids match the export / manual JSON (backup before re-noding). |

Export format: `{ "source_graph", "exported_at", "edges": [ { "source", "target", "tfl_cycle_programme", "tfl_cycle_route" }, ... ] }`. Future exports may add `osm_id` per record to drop the legacy dependency.

### 3.8 Scenic / attraction zones (green mode)

| Tag | Description |
|-----|-------------|
| `is_park` | `yes` if ≥50% of edge length lies inside an OSM park polygon (`leisure=park`, `landuse=recreation_ground`; not `leisure=garden`) or a manual park polygon. Private/restricted polygons excluded at fetch (`access=private/no/customers`). |
| `is_river` | `yes` if edge ≥50% inside a manual river polygon (drawn in debug app, same workflow as park) |
| `is_sight` | `yes` if edge intersects a manual sight circle (point + radius in metres, default 200) |
| `attraction_name` | Semicolon-separated names from matching OSM/manual regions (may list multiple) |

**Source:** **`fetch_osm_park_polygons.py`** (Overpass → `1_data/osm_park_polygons.geojson`) then **`tag_attractions_osm.py`** on `london_elev_final` (clears `is_park`, re-tags from cache). **`attraction_manual_regions.json`** from debug **Modify attractions** mode; apply with **`apply_attraction_manual.py`** on the final graph (adds flags, does not clear OSM `is_park`). Spatial matching: [`attraction_spatial.py`](../3_pipeline/attraction_spatial.py) (STRtree + length ratio, EPSG:27700 for buffers). Main app **Green/scenic** toggle uses any of `is_park` / `is_river` / `is_sight` (`_has_attraction_edge` in `app.py`).

**Manual edit apply run totals** (graph 175 490 nodes, 350 283 edges):

| Session | Runs | Edges cleared | Edges set/merged |
|---------|------|----------------|------------------|
| 17.02.2026 | 11 | 871 | 2 856 |
| 18.02.2026 | 12 | 1 323 | 1 846 |
| **Cumulative** | **23** | **2 194** | **4 702** |

*Note: Each row is the sum of “Cleared TfL tags on X edge(s)” and “Set/merged TfL tags on X edge(s)” over that session's runs. The same edge can be modified in more than one run (e.g. cleared then re-added), so the totals count edge-modification events, not unique edges.*

**TfL tagging effectiveness (algorithm vs manual):**

| Input | Value |
|-------|-------|
| Edges tagged by algorithm (`tag_tfl_routes.py`) | 18 578 |
| Total graph edges | 350 283 |
| Manual: edge-modification events (add + remove), cumulative | 6 896 (4 702 set/merged, 2 194 cleared) |

- **Manual operations per 1 000 algorithm-tagged edges:** 6 896 ÷ 18 578 ≈ **371** — for every 1 000 edges the algorithm tagged, about 371 manual add/remove events were applied across the documented sessions (so manual correction touched a substantial minority of the algorithm output).
- **Add/remove ratio:** 4 702 ÷ 2 194 ≈ **2.14** — about 2.1× as many "set/merged" events as "cleared" events, which suggests the algorithm tended to under-tag or miss routes more than to over-tag.
- **Net manual "add" events:** 4 702 − 2 194 = **2 508** — a rough indication of how many edge-updates were net additions of TfL (vs removals). This is not a unique edge count (the same edge can be updated in multiple runs).

*All manual totals above are event counts over 23 apply runs; they do not give a unique final TfL edge count.*

**Sample run results** (graph: 175 490 nodes, 350 283 edges; 222 TfL segment lines):

| Stage | TfL network (one-way) | Matched length | Ratio matched/one-way | Ratio matched/(2×one-way) |
|-------|------------------------|----------------|------------------------|----------------------------|
| After Pass 1 (cycle-infra only) | 572.68 km | 858.98 km | 1.50 | 0.75 |
| After relaxed pass(es) (2 iterations) | 572.68 km | 1168.04 km | 2.04 | 1.02 |

- Cycle-infrastructure edges indexed: 109 266 (of 350 283 total); relaxed set: 225 879 edges.
- Segments under 1.8× after Pass 1: 146; still under after 2 relaxed iterations: 53.
- **Tagged edges:** 18 578.

### 3.9 Added by elevation pipeline (not by `build_graph.py`)

| Tag | Set by | Description |
|-----|--------|-------------|
| `grade` | Elevation scripts | Slope (rise/run) for the edge; used for hill routing and debug uphill overlay |

See **Section 7** for how `grade` is computed and filtered on the noded mesh.

---

## 4. Node Attributes (Intersections)

Nodes are **coordinates** `(lon, lat)` rounded to 6 decimals. Every node has at least:

| Tag | Description |
|-----|-------------|
| `x` | Longitude (same as node key first element) |
| `y` | Latitude (same as node key second element) |

**Intersection attributes** are added when a point from `planet_osm_point` snaps to that **node**. Only traffic_signals, mini_roundabout, and crossing are node-snapped. **Barrier, give_way, and stop_sign** are snapped to **edges** (see Section 3.6).

| Tag | Source | Description |
|-----|--------|-------------|
| `traffic_signals` | highway=traffic_signals | `"yes"` |
| `mini_roundabout` | highway=mini_roundabout | `"yes"` |
| `crossing` | highway=crossing | `"yes"` |
| `crossing_type` | crossing=* | e.g. traffic_signals, zebra, toucan |
| `elevation` | Elevation pipeline | Metres (from LIDAR); added later, not by build_graph |

---

## 5. Graph Build Rules (`build_graph.py`)

### 5.1 Exclusion

- **Dropped:** Segments with `bicycle=no`.
- **Dropped:** Motorways (highway contains `motorway`) unless `bicycle` is `yes`, `designated`, or `permissive`.

### 5.2 Direction (directed graph)

- **One-way (car):** `oneway` in `yes`, `true`, `1` → forward only; `-1`, `reverse` → backward only.
- **Contraflow:** If `oneway:bicycle` is `no` / `false` / `0`, bicycles are allowed both ways; both edges (u→v and v→u) are added for that segment.
- **Two-way:** Both edges are added.
- Node coordinates `x`, `y` are set for both endpoints of each edge.

### 5.3 Cleanup

- **Largest component only:** After building the graph, only the **largest weakly connected component** is kept. All other nodes/edges (islands) are removed.
- **Topology:** Without noding, many suburbs are falsely disconnected (T-junctions on long OSM ways) and removed as “islands.” After `noded_network.py`, island removal drops sharply.

**Pre-noding vs post-noding (typical successful run):**

| Metric | Pre-noding | Post-noding (noded mesh) |
|--------|------------|---------------------------|
| Raw SQL segments | ~546k | ~2.2M |
| Final nodes | ~175k | ~1.92M |
| Final directed edges | ~350k | ~4.06M |
| Island nodes removed | ~542k | ~30k |
| Median edge length | ~28 m | ~9 m |

Source: pre-noding from §6.1 example; post-noding from `graph_debug_reports/graph_debug_report_2026-06-03.txt` (see Development_Protocol_2026_06_01-03.md §2).

### 5.4 Debug output

- **`1_data/graph_debug_reports/graph_debug_report_YYYY-MM-DD.txt`** — Generated every `build_graph.py` run (time suffix if multiple runs on the same day). Contains:
  - Total nodes, edges, raw segments, banned motorways, one-ways, contraflows, islands removed.
  - Per-edge-tag: non-empty count, total, coverage %.
  - Value distributions for categorical edge tags.
  - Per-node-tag: count of nodes with that tag.
  - Risk (accident count) distribution.
  - Strategic network refs (lcn_ref, rcn_ref, ncn_ref) with edge counts.

---

## 6. Example build output and report interpretation

### 6.1 Pre-noding example (legacy — June 2026 and earlier)

This terminal output is from a **pre-noding** build (`planet_osm_line` endpoint-only graph). It remains useful as a regression reference; **current production uses the noded mesh** (~4M edges — see §1 and §6.1b).

After running `python build_graph.py` from `3_pipeline/`, you should see something like:

```
--- BUILDING DIRECTED ROUTING GRAPH (ENHANCED) ---
1. Fetching road network with all tags...
   -> Loaded 545811 raw segments from planet_osm_line.
2. Building directed graph with direction rules...
   -> Banned 527 motorway segments.
   -> Processed 56564 one-way streets.
   -> Enabled 3565 contraflow cycling exceptions.
   -> Graph before cleanup: 717763 nodes, 1020461 edges
3. Cleaning disconnected 'Islands'...
   -> Removed 542273 island nodes. Kept 175490 nodes, 350283 edges.
4. Fetching intersection data from planet_osm_point...
   -> Loaded 172744 point features.
   -> Snapped 102118 point features to graph nodes.
   -> Missed 70626 features (no node within 0.0002 deg).
5. Saving to ..\1_data\london.graphml...
   -> Graph saved.
6. Generating debug report -> ..\1_data\graph_debug_reports\graph_debug_report_YYYY-MM-DD.txt
   -> Report written: 336 lines.
SUCCESS! Enhanced directed graph built.
```

**What each step means:**

| Step | Meaning |
|------|--------|
| Raw segments | OSM ways with `highway` set; many become two edges (both directions) or one (one-way). |
| Banned motorways | Ways excluded for cycling unless explicitly allowed. |
| One-way / contraflow | Direction rules applied; contraflow = bike both ways on one-way car streets. |
| Graph before cleanup | Total nodes (segment endpoints) and edges before removing islands. |
| Islands removed | Small disconnected components dropped; only the largest connected graph is kept. |
| Point features | Intersection/barrier points from OSM (signals, crossings, barriers, etc.). |
| Snapped / Missed | Points within ~20 m of a graph node get attributes on that node; the rest are discarded (often off-network or duplicate). |
| Report | Tag coverage and value distributions written to `1_data/graph_debug_reports/` (dated filename). |

### 6.2 Interpreting the debug report (`graph_debug_reports/graph_debug_report_*.txt`)

The report has six parts. Use it to check data quality and coverage.

**1. General statistics**  
- **Nodes / edges:** Final graph size after island removal. Expect hundreds of thousands of nodes and a similar or higher number of edges (e.g. ~175k nodes, ~350k edges).  
- **Raw segments:** Should match the “Loaded … raw segments” from the terminal.  
- **Motorway banned, one-way, contraflow, islands removed:** Should match terminal; confirms filters and cleanup ran.

**2. Edge tag coverage**  
- **100%:** Required fields (e.g. `osm_id`, `type`, `length`, `geometry`) — all edges should have these.  
- **High (e.g. 50–70%):** Often name, surface, lit — useful for routing; missing values mean “unknown” in the cost function.  
- **Low (e.g. &lt;10%):** Optional or rare tags (e.g. cycleway separation, strategic refs). Low coverage is normal; routing can still use them when present.

**3. Edge tag value distributions**  
- **type:** Mix of footway, residential, cycleway, primary, etc. — confirms road types are present.  
- **surface:** Dominance of asphalt/paving_stones is expected in London.  
- **lit:** Mostly `yes` with some `no` — night routing can distinguish.  
- **maxspeed:** 20/30 mph dominance is expected for UK.  
- **Strategic / cycleway tags:** If `lcn_ref` / `ncn_ref` are empty but `cycle_network` or `rcn_ref` have values, OSM may use different tagging in your extract; routing can use what’s there.

**4. Intersection / node tag coverage**  
- **Snapped vs missed:** Aligns with terminal (e.g. ~102k snapped, ~70k missed).  
- **Count per node tag:** e.g. traffic_signals, crossing, barrier — gives how many nodes get each attribute. Percent of total nodes (e.g. ~6% signals, ~19% crossing, ~16% barrier) indicates how much intersection data is available for future routing penalties.

**5. Risk distribution**  
- **Edges with risk &gt; 0:** Segments that had at least one matched accident.  
- **Min/max/mean:** Sanity check (e.g. mean ~1.3) — no extreme outliers suggests risk matching is plausible.

**6. Strategic cycling network summary**  
- Lists which routes appear (e.g. rcn_ref, cycle_network). Empty `lcn_ref` / `ncn_ref` with some `cycle_network` is a known OSM tagging variation.

### 6.3 Build success checklist

A run is **successful** if:

- [ ] Script finishes with **`SUCCESS! Enhanced directed graph built.`**
- [ ] **`1_data/london.graphml`** exists and was just written.
- [ ] **General stats:** Final node count &gt; 0, edge count &gt; 0, islands removed &lt; total nodes (so the main component was kept).
- [ ] **Edge coverage:** `osm_id`, `type`, `length`, `geometry` at 100%; `surface` and/or `lit` at reasonable coverage (e.g. &gt; 50%) for routing.
- [ ] **Intersections:** At least some points snapped (e.g. tens of thousands); node tag counts for traffic_signals / crossing / barrier are non-zero if you plan to use them in routing.
- [ ] **Risk:** If you use accident-aware routing, “Edges with risk &gt; 0” should be non-zero and the distribution plausible.

**Typical “healthy” signs from a report like the example:**

- **Pre-noding:** ~175k nodes, ~350k edges after cleanup — one large connected component (§6.1).
- **Post-noding:** ~1.9M nodes, ~4M edges; ~30k islands removed — see §6.1b.
- ~102k of 172k points snapped — many intersections attached to the graph; the rest are off-network or beyond 20 m.
- Core tags (name, surface, lit, type) have good coverage; optional tags (cycleway details, strategic refs) are sparse — expected for OSM.
- Risk on ~9% of edges, mean ~1.3 — reasonable for accident-based weighting.

**When to re-run or investigate:**

- Script hangs (e.g. at point snapping) → see Section 5.4 / spatial index (KD-tree) in `build_graph.py`.
- Zero nodes or edges after cleanup → check DB and highway filter.
- No intersections snapped → check SNAP_THRESHOLD and that `planet_osm_point` has data in your area.
- Report file missing or empty → check write permissions and `1_data/graph_debug_reports/`.

### 6.4 Example: was this build successful?

For the run that produced the terminal output and report above:

- **Yes — the build completed successfully.** The script exited with `SUCCESS!`, wrote `london.graphml`, and generated the debug report.
- **Graph:** 175,490 nodes and 350,283 edges form one connected component; 542,273 island nodes were removed. This is a single, routable Greater London graph.
- **Intersections:** 102,118 of 172,744 point features snapped to nodes (~59%). The 70,626 missed points are mostly off the road network or &gt; ~20 m from any segment end; the snapped set gives ~10k traffic signals, ~34k crossings, ~28k barriers — enough to use intersection data in routing later.
- **Tags:** Core routing tags are present: name (53%), surface (70%), lit (57%), type (100%), risk (9% with accidents). Strategic refs (lcn_ref, ncn_ref) are empty in this extract; rcn_ref and cycle_network have small coverage — routing can still use them where present.
- **Risk:** 30,729 edges with risk &gt; 0, max 24, mean ~1.3 — plausible for accident-based safety weighting.

So the pipeline ran correctly and the resulting graph is suitable for routing and for adding intersection-based penalties when you implement that (see `TASKS.md`).

### 6.1b Post-noding runtime graph (current)

After **`noded_network.py`** + default **`build_graph.py`** (June 2026):

| Metric | Typical value |
|--------|----------------|
| Nodes | ~1,924,143 |
| Directed edges | ~4,061,445 |
| Network length (sum of edge lengths) | ~70,111 km |
| Island nodes removed | ~30,327 |
| Edges &lt;10 m | ~52% |
| Debug report | `1_data/graph_debug_reports/graph_debug_report_2026-06-03.txt` |

**Healthy signs:** island removal &lt;&lt; pre-noding (~542k); outer-borough coverage fills former “holes” (verify with debug **Graph network** overlay). Startup and cold-load times increase with graph size — use **`.gpickle`** (see §1).

### 6.5 Tag coverage (verification script)

**Legacy snapshot (pre-noding mesh):** Output from **`python 6_verification/verify_tag_coverage.py`** on **`london_elev_final_tfl.graphml`** (**175,490** nodes, **350,283** edges). Re-run the script on the current **`london_elev_final_tfl.gpickle`** after major rebuilds; percentages shift with mesh scale (e.g. barrier tags fan out to more directed edges per OSM way).

**Edge tag coverage**

| TAG | NON-EMPTY | TOTAL | COVERAGE |
|-----|-----------|-------|----------|
| `osm_id` | 350,283 | 350,283 | 100.0% |
| `name` | 187,019 | 350,283 | 53.4% |
| `type` | 350,283 | 350,283 | 100.0% |
| `length` | 350,283 | 350,283 | 100.0% |
| `risk` | 30,729 | 350,283 | 8.8% |
| `geometry` | 350,283 | 350,283 | 100.0% |
| `surface` | 246,652 | 350,283 | 70.4% |
| `lit` | 200,314 | 350,283 | 57.2% |
| `maxspeed` | 139,317 | 350,283 | 39.8% |
| `width` | 4,952 | 350,283 | 1.4% |
| `bridge` | 9,146 | 350,283 | 2.6% |
| `tunnel` | 3,105 | 350,283 | 0.9% |
| `junction` | 3,655 | 350,283 | 1.0% |
| `smoothness` | 11,511 | 350,283 | 3.3% |
| `cycleway` | 23,900 | 350,283 | 6.8% |
| `cycleway_left` | 22,058 | 350,283 | 6.3% |
| `cycleway_right` | 16,643 | 350,283 | 4.8% |
| `cycleway_both` | 24,309 | 350,283 | 6.9% |
| `segregated` | 40,307 | 350,283 | 11.5% |
| `cycleway_separation` | 16 | 350,283 | 0.0% |
| `cycleway_left_separation` | 0 | 350,283 | 0.0% |
| `cycleway_right_separation` | 2 | 350,283 | 0.0% |
| `cycleway_buffer` | 8 | 350,283 | 0.0% |
| `cycleway_width` | 283 | 350,283 | 0.1% |
| `cycleway_surface` | 2,698 | 350,283 | 0.8% |
| `cycleway_smoothness` | 0 | 350,283 | 0.0% |
| `lcn_ref` | 0 | 350,283 | 0.0% |
| `rcn_ref` | 25 | 350,283 | 0.0% |
| `ncn_ref` | 0 | 350,283 | 0.0% |
| `cycle_network` | 244 | 350,283 | 0.1% |
| `hgv` | 1,474 | 350,283 | 0.4% |
| `traffic_calming` | 3,180 | 350,283 | 0.9% |
| `traffic_calming_point` | 29,702 | 350,283 | 8.5% |
| `traffic_calming_point_lat` | 29,702 | 350,283 | 8.5% |
| `traffic_calming_point_lon` | 29,702 | 350,283 | 8.5% |
| `barrier` | 61,067 | 350,283 | 17.4% |
| `barrier_lat` | 61,067 | 350,283 | 17.4% |
| `barrier_lon` | 61,067 | 350,283 | 17.4% |
| `barrier_confidence` | 41,586 | 350,283 | 11.9% |
| `give_way` | 13,394 | 350,283 | 3.8% |
| `give_way_lat` | 13,394 | 350,283 | 3.8% |
| `give_way_lon` | 13,394 | 350,283 | 3.8% |
| `stop_sign` | 197 | 350,283 | 0.1% |
| `stop_sign_lat` | 197 | 350,283 | 0.1% |
| `stop_sign_lon` | 197 | 350,283 | 0.1% |
| `tfl_cycle_programme` | 21,586 | 350,283 | 6.2% |
| `tfl_cycle_route` | 21,586 | 350,283 | 6.2% |
| `grade` | 199,744 | 350,283 | 57.0% |

**Node tag coverage**

| TAG | NON-EMPTY | TOTAL | COVERAGE |
|-----|-----------|-------|----------|
| `x` | 175,489 | 175,490 | 100.0% |
| `y` | 175,490 | 175,490 | 100.0% |
| `traffic_signals` | 10,815 | 175,490 | 6.2% |
| `mini_roundabout` | 1,072 | 175,490 | 0.6% |
| `crossing` | 34,095 | 175,490 | 19.4% |
| `crossing_type` | 31,682 | 175,490 | 18.1% |
| `elevation` | 175,350 | 175,490 | 99.9% |

---

## 7. Elevation processing (after build)

Noding splits OSM ways into many **short edges** (~9 m median). Raw LIDAR grades on micro-segments over-count steep climbs. Step 6 applies a **connected hill-length filter** so only sustained ascents survive.

### 7.1 Scripts

1. **`Add_elevation_raster.py`**  
   Loads `london` via `graph_io` (pickle preferred). Samples LIDAR at each node, sets `elevation`; computes `grade` per edge (`(ele_v − ele_u) / length`). Writes **`london_elev_raw.gpickle`** only.

2. **`elevation_processing_aggressive.py`**  
   Loads `london_elev_raw.gpickle`. Processing order:

   | Step | What |
   |------|------|
   | Optional DEM | 5×5 median on nodes at endpoints of short (&lt;50 m) steep edges; recalculate grades |
   | Pre-filters | Grade → 0 on edges &lt;5 m; grade → 0 on pedestrian/motorway types in `FLATTEN_CLASSES` |
   | **Hill-length filter** | Union-find on **ascent-steep** edges (`grade > 3.3%`) sharing a node; component length = sum of member edge lengths |
   | Cap | Clamp \|grade\| to **20%** |

   **Hill-length thresholds** (constants `HILL_HALF_M`, `HILL_KEEP_M` in script):

   | Connected steep chain length | Action |
   |------------------------------|--------|
   | **&lt; 50 m** | Flatten (grade → 0) |
   | **50–100 m** | Halve grade (×0.5) |
   | **≥ 100 m** | Keep full grade |

   Reverse edges (`v→u`) are **not** chained to `u→v` when measuring components (each direction evaluated separately for ascents). Descents are unchanged by the hill filter except the ±20% cap.

   **Usage:**
   ```text
   python elevation_processing_aggressive.py              # full (DEM + hill); very slow at ~4M edges
   python elevation_processing_aggressive.py --skip-dem   # hill filter only; typical dev re-run
   ```

   Writes **`london_elev_final.gpickle`** only. Node `elevation` may change when DEM smoothing runs; otherwise only `grade` is modified.

### 7.2 Elevation metrics (reference runs)

Ascent-steep = directed edges with `grade > 3.3%`. **Steep / 100 km** = ascent-steep count ÷ network km × 100 (primary sanity metric on noded mesh).

| Graph | Edges | Network km | Ascent-steep | Steep / 100 km | Total ascent km |
|-------|------:|-----------:|-------------:|---------------:|----------------:|
| Old mesh (`london_elev.graphml`, pre-noding) | 350,283 | ~28,033 | 34,211 | **122** | ~239 |
| New RAW (`london_elev_raw.gpickle`) | 4,061,445 | ~70,111 | 535,815 | 764 | ~848 |
| New final — **previous cluster logic** (Jun 2026) | 4,061,445 | ~70,111 | 173,842 | 248 | ~487 |
| New final — **hill-length 50/100 m** (Jun 2026) | 4,061,445 | ~70,111 | **77,688** | **111** | **~371** |

Hill-length run ( `--skip-dem` ): ~133k ascent edges flattened (&lt;50 m chains), ~41k halved (50–100 m), ~60k kept (≥100 m).

### 7.3 After re-running elevation

Rebuilding **`london_elev_final.gpickle`** does **not** automatically update TfL/attraction tags on **`london_elev_final_tfl.gpickle`**. Either:

- Re-run from **`tag_attractions_osm.py`** onward via `run_graph_pipeline.py --start-at tag_attractions_osm.py` (with `--skip-tagging` / `--legacy-graph` as usual), **or**
- Copy updated `grade` onto the existing `_tfl` graph (same topology) and restart backends.

Restart **`app.py`** and **`app_debug.py`** after any runtime pickle change.

---

## 8. Routing use

- **File used:** `1_data/london_elev_final_tfl.gpickle` at runtime (canonical path `london_elev_final_tfl.graphml` for `graph_io` fallback; see pipeline step 7).
- **Graph type:** `networkx.DiGraph`; node id = `(lon, lat)` tuple.
- **Scale (current noded mesh):** ~1.92M nodes, ~4.06M directed edges — see §1.
- **Cost function:** Edge attributes (`length`, `risk`, `lit`, `surface`, `grade`, barriers, calming, etc.) plus **node** penalties at the head of each edge (`traffic_signals`, zebra/uncontrolled `crossing`, `mini_roundabout`, junction danger). See `0_documentation/APP_MAIN.md` §5.5. Junction cluster dedup (35 m) limits stacked penalties at one physical junction.

---

## 9. Dynamic API data (live disruptions)

Live road disruption data (**TfL** and **TomTom**) is **not** stored in the graph file. It is fetched at runtime by the backend and matched to the same graph edges. This section explains why it is handled outside the graph pipeline and how the API system works.

### 9.1 Why it is outsourced from the graph pipeline

- The graph pipeline (steps 1–7) produces a **static** snapshot: OSM roads, elevation, and TfL cycle route tags. The runtime artifact (`london_elev_final_tfl.gpickle`; plus `.graphml` export) is written once and reused.
- Live disruptions (road closures, works, incidents, diversions) change constantly and come from **external APIs**. They do not belong in a static GraphML build; they belong in the **runtime** layer that already loads that graph for routing.
- So disruption data is **logistically outsourced**: the same graph is loaded by the backend; a spatial index over edge geometries is built once at startup; APIs are called on demand (e.g. via `POST /admin/update_tfl` and `POST /admin/update_tomtom`); matches are stored in in-memory lookups. Routing and overlays then use this dynamic data alongside the static graph. Conceptually, “what affects routing” still includes these disruptions—they are just supplied by a separate system that consumes the graph rather than being part of the graph file.

### 9.2 How the API system works

**Two API modes:**

1. **TfL (Transport for London)** — `4_backend_engine/tfl_live.py`
   - **Endpoint:** `https://api.tfl.gov.uk/Road/all/Disruption` (optional `TFL_APP_KEY` in `.env` for rate limits).
   - **Data:** Closures, diversions, works, incidents; each disruption can have point, line (MultiLineString WKT), or polygon geometry.
   - **Matching:** At startup, `tfl_live.init(G)` builds an STRtree from all graph edge geometries. When disruptions are fetched, each disruption geometry is matched to edges: for an edge to be tagged, a sufficient fraction of its length (e.g. ≥50% alignment threshold) must lie inside the disruption zone; for short edges, angularity (roughly parallel to disruption line) is also used. Matched edges are stored in `TFL_LIVE_LOOKUP` and a visualization cache.
   - **Penalties:** Used by the cost function when “Live TfL Disruptions” is on: closures block the edge; diversions/works/incidents add multipliers; severity (minimal → severe) scales the penalty.

2. **TomTom** — `4_backend_engine/tomtom_live.py`
   - **Endpoint:** TomTom Traffic Incident API v5 (incidentDetails); requires `TOMTOM_API_KEY` in `.env`.
   - **Data:** Incidents with cluster types (e.g. A = closure, B = roadworks, C = jam, D = environmental). Geometry from API is matched to the graph using the **same** STRtree built by `tfl_live.init(G)` (TomTom has no separate init; it reuses the graph and index).
   - **Matching:** Incident geometry is passed to `tfl_live.match_geometry_to_edges`; matched edges are stored in `TOMTOM_EDGES` and a visualization list. Optional fields such as `iconCategory` and `magnitudeOfDelay` are kept for the inspector and debug overlays.

**Unified layer** — `4_backend_engine/live_disruptions.py`:
- **Initialization:** `live_disruptions.init(G)` calls `tfl_live.init(G)` once; no separate TomTom init.
- **Updates:** `POST /admin/update_tfl` fetches TfL and updates TfL state; `POST /admin/update_tomtom` fetches TomTom and updates TomTom state. Updating one source **never** clears the other (safe update pattern).
- **Merge:** After any update, `_rebuild_master_lookup()` merges TfL and TomTom into **`MASTER_LIVE_LOOKUP`**: for each edge key `(u, v)`, if both sources have a disruption, the merged record takes the worst-case penalty (e.g. max severity multiplier, closure if either has closure). Routing uses **O(1)** lookup via `get_edge_disruption(u, v)`.

**Summary:** The graph file stays static. The backend loads it, builds one STRtree over edges, and uses it for both TfL and TomTom. Each API mode is refreshed independently; the merged lookup drives routing and combined overlays; inspector and debug app can show source-specific fields (e.g. TomTom `iconCategory`, `magnitudeOfDelay`). Environment variables: **`TFL_APP_KEY`** (optional), **`TOMTOM_API_KEY`** (required for TomTom).

---

## 10. Keeping this document up to date

- **Adding/removing tags in `build_graph.py`:** Update Section 3 (edge attributes) and/or Section 4 (node attributes). If the SQL or snap logic changes, update Section 2.
- **Changing direction or exclusion rules:** Update Section 5.
- **Adding a new pipeline script or changing order:** Update Section 1 and any affected sections.
- **Changing elevation behaviour or outputs:** Update Section 7.
- **Using new attributes in the backend:** Update Section 8; consider adding or updating a task in `0_documentation/TASKS.md`.
- **Changing live disruption APIs or merge logic:** Update Section 9; sync with `0_documentation/APP_MAIN.md` and `APP_DEBUG.md`.

A reminder to update this file is at the top of `3_pipeline/build_graph.py`.
