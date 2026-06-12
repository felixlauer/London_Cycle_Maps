# Solve Tasks — Brainstorming Notes

**Purpose:** Design notes for open performance, coverage, routing, and green-mode work. Not a task list — see [`TASKS.md`](TASKS.md) for actionable items.

**Related:** [`GRAPH.md`](GRAPH.md), [`APP_MAIN.md`](APP_MAIN.md), [`3_pipeline/build_graph.py`](../3_pipeline/build_graph.py), [`4_backend_engine/app.py`](../4_backend_engine/app.py).

---

## 1. Bad graph coverage (missing roads in some areas)

### Symptoms

- Main app and debug app cannot snap to or inspect roads that appear on the basemap.
- Problem is **patchy** — some boroughs/quarters much worse than others (e.g. areas south of Battersea Park noted in development protocols).

### What the pipeline actually removes or hides

#### A. Largest weakly connected component only

After building the directed graph, [`build_graph.py`](../3_pipeline/build_graph.py) keeps **only the largest weakly connected component** and deletes all other nodes/edges (“islands”).

Example from a successful build (see [`GRAPH.md`](GRAPH.md) §6):

- Before cleanup: ~717k nodes
- Islands removed: ~542k nodes
- Kept: ~175k nodes, ~350k edges

Anything not in that main component is **gone from the graph**, not merely hard to route. This is the single biggest structural cause of “holes.”

**Why certain areas are hit harder:**

- Housing estates, campuses, industrial sites with **gaps in OSM** (missing links, wrong `bicycle=*`, private roads not mapped).
- **Parks and paths** that exist in OSM but connect to the car network only through one weak link — if that link is missing or filtered, the whole subgraph is an island.
- **New developments** with sparse or newly drawn geometry not yet topologically tied to main London.
- **River paths, canals, cycle-only networks** that form separate components from the main road mesh.

#### B. Segment filters (before island cleanup)

Each OSM line is skipped if:

- `bicycle=no`
- `highway` contains `motorway` unless `bicycle` is `yes`, `designated`, or `permissive`

Areas can look empty if the only connectors are tagged forbidden for cyclists or are motorway-class.

#### C. Data source / DB mismatch

- **Graph build** reads **`planet_osm_line`** (full OSM line features with `highway`).
- **`import_roads.py`** loads a **roads-only Geofabrik shapefile** into table **`ways`** for accident matching ([`calculate_risk.py`](../3_pipeline/calculate_risk.py)).

Coverage problems are often **OSM import quality or extent** for `planet_osm_line`, not the graph script alone. The roads shapefile does not replace a full osm2pgsql-style import for line topology.

#### D. Snap and inspect behaviour

**Status: improved (global edge snap).** [`tfl_live.snap_to_edge`](../4_backend_engine/tfl_live.py) queries the shared startup STRtree, projects the click onto the closest edge geometry, and picks the nearer terminal as the routing anchor. [`GET /route`](../4_backend_engine/app.py) prepends/appends snap coordinates as visual stubs; A\* remains node-to-node. [`GET /inspect`](../4_backend_engine/app.py) uses the same global snap.

**Remaining gaps:** stats distance excludes stub segments; routing cost is optimal for anchor nodes, not exact click points; clicks **>50 m** from any edge return 400/404. Sparse graph holes are still possible where OSM has no geometry.

#### E. Node coordinate rounding

Endpoints are rounded to 6 decimals when used as node IDs. Ways that should meet but are digitised slightly apart may not share a node → small disconnected fragments → dropped at island cleanup.

### Diagnostic ideas

| Check | What it tells you |
|--------|-------------------|
| Compare click location to OSM | Way missing in OSM vs only in our graph |
| `1_data/graph_debug_reports/` after build | Island stats, highway type counts (compare dated files over time) |
| Visualise second-largest WCCs | Often maps to “hole” neighbourhoods |
| PostGIS query at lat/lon on `planet_osm_line` | Present? `bicycle=no`? |
| Node/edge density overlay in debug app | Sparse patches = poor snap |

### Mitigation directions

- **Topology repair (implemented):** [`noded_network.py`](../3_pipeline/noded_network.py) splits `planet_osm_line` at intersections into `planet_osm_line_noded_enriched`; [`build_graph.py`](../3_pipeline/build_graph.py) reads that view by default. Re-run [`run_graph_pipeline.py`](../3_pipeline/run_graph_pipeline.py) after OSM updates.
- **Relax island policy (not implemented):** keep top-N components or components above a size threshold, not only the largest.
- **Endpoint snap (not implemented):** merge endpoints within 1–2 m in PostGIS before graph build.
- **Regional graphs** with boundary connectors (heavier architecture).
- ~~**Nearest-edge snap**~~ — **Done:** `snap_to_edge` on shared STRtree; visual stubs for `/route`.
- Ensure **full OSM line import** for London into `planet_osm_line`, not roads-only shapefile alone.

---

## 2. Performance: build time, load time, production, mobile

### Build pipeline (~200s+ for `build_graph.py` alone)

For ~500k+ SQL rows, pandas iteration, directed edge doubling, weakly connected component analysis, KD-tree and multiple STRtree passes — **multi-minute builds in pure Python/NetworkX are plausible**.

**Intended cadence:** batch job **at most once per day** (or on OSM update), via [`run_graph_pipeline.py`](../3_pipeline/run_graph_pipeline.py). Not per user request.

**Future build optimisations (if needed):** vectorise instead of row-by-row loops, build topology in PostGIS/pgRouting, reduce in-memory graph copies.

### App startup (dev feels slow)

[`app.py`](../4_backend_engine/app.py) and [`app_debug.py`](../4_backend_engine/app_debug.py) at import:

1. `nx.read_graphml(...)` — full parse, attributes as strings
2. Loop all nodes into `node_data`
3. `live_disruptions.init(G)` — STRtree over every edge
4. Junction cluster union-find (main app)

Flask **debug reloader** often loads **twice**. With ~350k edges and WKT `geometry` on every edge, **tens of seconds to minutes** on a laptop is common.

### Production architecture (standard pattern)

```text
Batch (cron / CI, ~daily)
  run_graph_pipeline.py → london_elev_final_tfl.graphml

Long-running API server (Gunicorn/uvicorn/Docker)
  Worker boot: load graph ONCE into RAM
  Each /route request: reuse in-memory G — no GraphML reload

Clients
  React web → HTTP /route
  Mobile app → same REST API (no embedded graph unless offline product)
```

| | Development | Production |
|---|-------------|------------|
| Graph load | Every restart / hot reload | Once per worker lifetime |
| Pipeline | Manual | Scheduled (e.g. daily) |
| User impact | Slow restarts | Load time amortised |

**Users do not reload the graph per visit.** Each worker process holds one copy → RAM ≈ `workers × graph size`.

### Load-time improvement directions

- Serialize to **pickle**, Parquet, or custom binary (numeric attrs; optional lazy geometry).
- Avoid storing full WKT on every edge in RAM if routing only needs length + tags.
- **KD-tree / BallTree** for nearest-node at startup (today: O(n) per request in `get_nearest_node`).
- Dev: single worker, disable reloader when testing routing performance.

**Bottom line:** long build + long cold start are **normal for this stack**; they should **not** happen per end-user request if the API runs as a persistent service.

---

## 3. Route computation speed and A* heuristic

**Status: implemented** (see `routing_heuristic.py`, KD-tree snap in `app.py` bootstrap).

### Previous behaviour (before heuristic)

[`app.py`](../4_backend_engine/app.py) used `nx.astar_path` with **no custom `heuristic`** → **h = 0** (Dijkstra-style expansion). Snap was **O(n)** per request in `get_nearest_node`.

### Implemented behaviour

```python
h_fast = make_heuristic(end_node, G, cost_per_m=1.0)
h_opt = make_heuristic(end_node, G, cost_per_m=compute_optimized_cost_per_metre_lower_bound(w))
nx.astar_path(..., heuristic=h_fast, weight=weight_fastest)
nx.astar_path(..., heuristic=h_opt, weight=weight_optimized)
```

- **Fastest:** `h = haversine_m(u, goal)`.
- **Optimized:** `h = haversine_m(u, goal) × r_lb` where `r_lb` is the per-request product of enabled reward toggles (0.75 / 0.75 / 0.8), floored at `R_MIN`; `m_lb = 1.0` (penalties only increase M). Additives and hills omitted (admissible).
- **Snap:** cKDTree at bootstrap.
- **Verify:** `route_benchmark.py` or `ROUTE_BENCHMARK=1` on `/route`.

### Why long routes feel slow

1. **h = 0** → explores many nodes across a large geographic search area.
2. **`weight_optimized`** is a Python callable per edge (live disruptions, toggles, additives).
3. **Two** full path queries per `/route` (fastest + optimized).
4. Large graph (~350k edges) with high branching at junctions.

### Heuristic design

#### Fastest path (`weight_fastest` = edge length in metres)

Straight-line distance in metres from current node to goal:

```python
def heuristic(u, target):
    return haversine_m(G.nodes[u]['x'], G.nodes[u]['y'],
                       G.nodes[target]['x'], G.nodes[target]['y'])
```

**Admissible** for shortest-distance routing (standard geographic lower bound).

NetworkX signature: `heuristic(current_node, target_node)`.

#### Optimized path (`make_weight_optimized`)

Costs are `length × multipliers + additives`, not pure length. Naive geographic `h` can **overestimate** → A* may return suboptimal paths.

**Implemented lower bound** (tighter than `R_MIN × M_MIN` when rewards are off):

```text
h(n) = haversine(n, goal) × max(R_MIN, product of enabled reward factors)
```

**Alternatives for production scale:** contraction hierarchies, Valhalla, OSRM, GraphHopper — larger refactor.

#### Also fixed

`get_nearest_node` now uses a startup **cKDTree** (O(log n) per snap).

**Expectations:** cross-London in Python with dynamic weights — hundreds of ms to a few seconds is plausible today; sub-100 ms typically needs C++ engines + preprocessing.

---

## 4. Green mode — current logic and manual regions

### Current logic ([`_is_green_edge`](../4_backend_engine/app.py))

Edge is “green” when:

- `type` ∈ `footway`, `cycleway`, `path`, `bridleway`, **and**
- natural surface (`grass`, `ground`, `earth`, …) **or** `lit` is empty / `no`

Reward when `green_weight > 0`: `R *= 0.8`.

### Why coverage is poor

Most real park and scenic riding is **not** tagged that way on OSM **lines**:

- Parks are often `leisure=park` **polygons**, not `highway=*` ways.
- Asphalt footpaths in parks fail the “natural surface” test.
- Lit paths fail the “unlit” branch.

See [`6_verification/green_mode_coverage.py`](../6_verification/green_mode_coverage.py) for measuring match rates on the graph.

### Proposed approach: manual geographic regions

Similar in spirit to TfL live matching and manual TfL edits.

#### Workflow

1. **Authoring (debug app):** draw polygons (parks), polyline + buffer (Thames), optional radii (landmarks).
2. **Storage:** e.g. `3_pipeline/green_regions.json` — GeoJSON features + mode enum (`park` | `river_corridor` | `scenic` | …).
3. **Tagging (pipeline step or startup):**
   - STRtree over edge LineStrings (same pattern as [`tfl_live.py`](../4_backend_engine/tfl_live.py)).
   - If edge geometry intersects polygon (or lies within buffered river line), set e.g. `green_zone` on the edge.
4. **Routing:** when `green_weight > 0`, apply tiered `R` multipliers by `green_zone`.

#### River corridor

Buffer the river centreline (e.g. 30–80 m) in a projected CRS or degree approximation — standard Shapely `buffer`.

#### Overlaps

Edge in park and near river → define priority (max reward, or explicit mode hierarchy).

#### Trade-offs

| Pros | Cons |
|------|------|
| Works without OSM line tag quality | Manual maintenance |
| Control over Hyde Park, Thames, etc. | Re-tag when graph rebuilds change geometry |
| Reuses existing geometric matching patterns | Large polygons tag many edges (often intended) |

#### Alternative data sources

GLA greenspace / landcover datasets as bulk polygons — less manual drawing, less fine-grained “three modes” control.

---

## 5. Cross-topic priority sketch

| Priority | Topic | Quick win | Larger effort |
|----------|--------|-----------|----------------|
| High | Coverage holes | Audit islands + OSM at bad bbox | Noded network (done); optional relax WCC / endpoint snap |
| High | Dev load time | Pickle cache, disable reloader | Strip geometry from RAM |
| Medium | Route time | Heuristic on fastest path | Optimized admissible h or external engine |
| Medium | Snap quality | KD-tree for nearest node | Nearest-edge STRtree |
| Medium | Green mode | — | `green_regions.json` + pipeline step |
| Low | Build time | — | Vectorised build / pgRouting |

---

## 6. References in repo

| File | Relevance |
|------|-----------|
| [`3_pipeline/build_graph.py`](../3_pipeline/build_graph.py) | Filters, island cleanup, step 4d calming relay |
| [`3_pipeline/run_graph_pipeline.py`](../3_pipeline/run_graph_pipeline.py) | Batch pipeline orchestration |
| [`4_backend_engine/app.py`](../4_backend_engine/app.py) | Routing, snap, green logic, load path |
| [`4_backend_engine/tfl_live.py`](../4_backend_engine/tfl_live.py) | Polygon/line geometric edge matching |
| [`0_documentation/TASKS.md`](TASKS.md) | A* heuristic, green mode, Battersea, performance items |
| [`0_documentation/GRAPH.md`](GRAPH.md) | Pipeline order, island cleanup, routing use |

---

*Brainstorming document — update when design decisions are made or items move to TASKS.md / implementation.*
