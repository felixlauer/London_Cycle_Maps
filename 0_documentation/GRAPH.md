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
| 3 | `calculate_risk.py` | DB: ways + accidents | DB: `accident_count` on roads | Match accidents to segments (e.g. within 15 m) |
| 4 | **`build_graph.py`** | `planet_osm_line` + points | **`1_data/london.graphml`** | Build directed graph + intersections |
| 5 | `Add_elevation_raster.py` | `london.graphml` + LIDAR VRT | `1_data/london_elev_raw.graphml` | Add node elevation + edge `grade` |
| 6 | `elevation_processing_aggressive.py` | `london_elev_raw.graphml` | **`1_data/london_elev_final.graphml`** | Smooth/correct elevation, cap grades |
| 7 | **`tag_tfl_routes.py`** | `london_elev_final.graphml` + `1_data/tfl_raw/routes/Cycle_routes.json` | **`1_data/london_elev_final_tfl.graphml`** | Tag edges with TfL Cycleways / Quietways / Cycle Superhighways |

**The backend and debug app use `london_elev_final_tfl.graphml`** (elevation + TfL). That file is produced **only by step 7** (`tag_tfl_routes.py`). If you run steps 4–6 but skip step 7, the app keeps using the old `london_elev_final_tfl.graphml` and will not show barrier/give_way/stop (or other new edge data) until you run step 7. All attributes from `build_graph.py` are preserved through the elevation steps; elevation scripts only add/change `elevation` (nodes) and `grade` (edges).

**Full pipeline commands (run from `3_pipeline/`):**
```text
python build_graph.py
python Add_elevation_raster.py
python elevation_processing_aggressive.py
python tag_tfl_routes.py                    # required — creates london_elev_final_tfl.graphml
python apply_tfl_export.py                  # optional — restore TfL from tfl_edges_from_graph.json
python apply_tfl_manual_edits.py            # optional — apply manual TfL edits
```

---

## 2. Data Sources

### 2.1 Line data: `planet_osm_line`

- **Filter:** `WHERE highway IS NOT NULL`
- **Geometry:** WGS84 (SRID 4326), length in meters via `ST_Length(geography)`.
- **Risk:** Column `accident_count` (e.g. from `calculate_risk.py` or equivalent) is read as `risk` on each edge.

### 2.2 Point data: `planet_osm_point`

- **Filter:**  
  `highway IN ('traffic_signals','mini_roundabout','crossing','give_way','stop')` **OR** `barrier IS NOT NULL`
- **Node snap:** **Traffic_signals**, **mini_roundabout**, and **crossing** points are snapped to the **nearest graph node** (KD-tree). If distance &gt; `SNAP_THRESHOLD` (~20 m), the point is discarded. Attributes are stored on the node (see Section 4).
- **Edge snap:** **Barrier**, **give_way**, and **stop** points are snapped to the **nearest edge** (STRtree over edge geometry). The **original OSM position** is stored on the edge so overlays plot a **point at that location**, not the whole segment. **Barrier:** both directions (u,v) and (v,u) get the same barrier and position. **Kerb** barriers are assigned **only to pedestrian ways** (footway, pedestrian, path, steps); if no such edge is within the snap threshold, the kerb is skipped. Other barriers get a **barrier_confidence** (0–1): straight segments use orthogonal distance (linear scale, 4 m threshold); curved segments get 0.5. **Give_way / stop:** only the edge that **ends** at the sign is tagged (direction rule), with a stricter threshold (`SNAP_THRESHOLD_SIGN`) so the sign hits the correct road. See Section 3.6.
- **Traffic calming (points):** **planet_osm_point** rows with non-empty `traffic_calming` are loaded in a separate query and snapped to edges in **step 4c**. Car-allowed edges are preferred; fallback to any edge within the same snap threshold. Stored in **separate** edge fields: `traffic_calming_point`, `traffic_calming_point_lat`, `traffic_calming_point_lon` (way-based `traffic_calming` is unchanged). See Section 3.5.

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

**Source:** **Way-based:** `traffic_calming` is read from **planet_osm_line** and copied onto graph edges. **Point-based:** In step 4c, **planet_osm_point** rows with non-empty `traffic_calming` are snapped to the nearest edge (STRtree); car-allowed edges are preferred, then fallback to any edge within threshold. Point data is written only to `traffic_calming_point` and the lat/lon fields so way-based calming is not overwritten.

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

**Export and re-apply (after re-running build/elevation):** Re-running `build_graph.py` (and elevation) loses TfL tags. To preserve the current TfL state (algorithm + manual edits) before a rebuild, run **`python extract_tfl_from_graph.py`** — it writes every edge that has `tfl_cycle_programme` or `tfl_cycle_route` to **`3_pipeline/tfl_edges_from_graph.json`** (source, target, programme, route). After a fresh build and **`tag_tfl_routes.py`**, run **`python apply_tfl_export.py`** to re-apply those tags from the JSON; then optionally run **`apply_tfl_manual_edits.py`** again if you have further manual add/remove edits. Export format: `{ "source_graph", "exported_at", "edges": [ { "source", "target", "tfl_cycle_programme", "tfl_cycle_route" }, ... ] }`.

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

### 3.7 Added by elevation pipeline (not by `build_graph.py`)

| Tag | Set by | Description |
|-----|--------|-------------|
| `grade` | Elevation scripts | Slope (rise/run) for the edge; used for hill routing |

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

### 5.4 Debug output

- **`1_data/graph_debug_report.txt`** — Generated every run. Contains:
  - Total nodes, edges, raw segments, banned motorways, one-ways, contraflows, islands removed.
  - Per-edge-tag: non-empty count, total, coverage %.
  - Value distributions for categorical edge tags.
  - Per-node-tag: count of nodes with that tag.
  - Risk (accident count) distribution.
  - Strategic network refs (lcn_ref, rcn_ref, ncn_ref) with edge counts.

---

## 6. Example build output and report interpretation

### 6.1 Example terminal output (successful run)

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
6. Generating debug report -> ..\1_data\graph_debug_report.txt
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
| Report | Tag coverage and value distributions written to `1_data/graph_debug_report.txt`. |

### 6.2 Interpreting the debug report (`graph_debug_report.txt`)

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

- ~175k nodes, ~350k edges after cleanup — one large connected component.
- ~102k of 172k points snapped — many intersections attached to the graph; the rest are off-network or beyond 20 m.
- Core tags (name, surface, lit, type) have good coverage; optional tags (cycleway details, strategic refs) are sparse — expected for OSM.
- Risk on ~9% of edges, mean ~1.3 — reasonable for accident-based weighting.

**When to re-run or investigate:**

- Script hangs (e.g. at point snapping) → see Section 5.4 / spatial index (KD-tree) in `build_graph.py`.
- Zero nodes or edges after cleanup → check DB and highway filter.
- No intersections snapped → check SNAP_THRESHOLD and that `planet_osm_point` has data in your area.
- Report file missing or empty → check write permissions and REPORT_PATH.

### 6.4 Example: was this build successful?

For the run that produced the terminal output and report above:

- **Yes — the build completed successfully.** The script exited with `SUCCESS!`, wrote `london.graphml`, and generated the debug report.
- **Graph:** 175,490 nodes and 350,283 edges form one connected component; 542,273 island nodes were removed. This is a single, routable Greater London graph.
- **Intersections:** 102,118 of 172,744 point features snapped to nodes (~59%). The 70,626 missed points are mostly off the road network or &gt; ~20 m from any segment end; the snapped set gives ~10k traffic signals, ~34k crossings, ~28k barriers — enough to use intersection data in routing later.
- **Tags:** Core routing tags are present: name (53%), surface (70%), lit (57%), type (100%), risk (9% with accidents). Strategic refs (lcn_ref, ncn_ref) are empty in this extract; rcn_ref and cycle_network have small coverage — routing can still use them where present.
- **Risk:** 30,729 edges with risk &gt; 0, max 24, mean ~1.3 — plausible for accident-based safety weighting.

So the pipeline ran correctly and the resulting graph is suitable for routing and for adding intersection-based penalties when you implement that (see `TASKS.md`).

---

## 7. Elevation processing (after build)

1. **`Add_elevation_raster.py`**  
   Reads `london.graphml`, samples LIDAR at each node, sets `elevation`; computes `grade` per edge. Writes **`london_elev_raw.graphml`**.

2. **`elevation_processing_aggressive.py`**  
   Reads `london_elev_raw.graphml`. Applies 5×5 median smoothing on suspicious nodes, recalculates grades, applies cluster logic (flatten noise, preserve real steep chains), caps extreme grades (e.g. 20%). Writes **`london_elev_final.graphml`**.  
   All non-elevation attributes from the graph are unchanged; only `elevation` and `grade` are modified.

---

## 8. Routing use

- **File used:** `1_data/london_elev_final_tfl.graphml` (elevation + TfL cycle routes; see pipeline step 7).
- **Graph type:** `networkx.DiGraph`; node id = `(lon, lat)` tuple.
- **Cost function:** Currently uses edge attributes only (e.g. `length`, `risk`, `lit`, `surface`, `grade`). Node attributes (e.g. `traffic_signals`, `barrier`) are **not** used in routing yet; they are available for future cost/penalty logic.

---

## 9. Dynamic API data (live disruptions)

Live road disruption data (**TfL** and **TomTom**) is **not** stored in the graph file. It is fetched at runtime by the backend and matched to the same graph edges. This section explains why it is handled outside the graph pipeline and how the API system works.

### 9.1 Why it is outsourced from the graph pipeline

- The graph pipeline (steps 1–7) produces a **static** snapshot: OSM roads, elevation, and TfL cycle route tags. The output file (`london_elev_final_tfl.graphml`) is written once and reused.
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
