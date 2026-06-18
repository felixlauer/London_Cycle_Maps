# Route Generation — Performance Improvement Ideas

**Purpose:** Research notes on further speeding up route generation. No implementation yet — options ranked by likely ROI.

**Related:** [`TASKS.md`](TASKS.md), [`solve_tasks_brainstorming.md`](solve_tasks_brainstorming.md), [`../APP_MAIN.md`](../APP_MAIN.md) §2.3, [`../GRAPH.md`](../GRAPH.md) §1.

---

## Project structure (brief)

| Layer | Path | Role |
|-------|------|------|
| Documentation | `0_documentation/` | Living specs (`APP_MAIN.md`, `GRAPH.md`, `tasks/`, `verification/`) + gitignored `summary_files/` progress summaries |
| Data | `1_data/` | Graph artifacts (`london_elev_final_tfl.gpickle`, ~4M edges on noded mesh) |
| Pipeline | `3_pipeline/` | OSM → PostGIS → graph build → elevation → TfL/attraction tagging |
| Backend | `4_backend_engine/` | Flask routing (`app.py`), heuristics, live disruptions, profiles |
| Frontend | `5_frontend/` | React/Leaflet main app |
| Debug | `8_debug/` | Validation overlays, manual TfL/attraction edits |

**Route flow today:** snap to edge (STRtree) → build request-scoped weights → **two** NetworkX A* runs (fastest + optimized) → reconstruct geometry, stats, overlay chunks.

**Already done for performance:** `.gpickle` load, haversine A* heuristic, global edge snap, park-hours pre-eval, junction cluster dedup, `ROUTE_BENCHMARK=1` / `route_benchmark.py`.

---

## Why route generation is slow now

The biggest change since the summary docs were written is **graph scale**. Pre-noding was ~350k directed edges; the current noded mesh is **~4.06M edges** (~1.92M nodes). That alone can make routing an order of magnitude slower even with a good heuristic.

Per `/route` request, the hot path looks like this:

```python
weight_fastest = make_weight_fastest(hours_map, fallback_open)
h_fast = make_heuristic(end_node, G, cost_per_m=1.0)
path_fastest = nx.astar_path(G, start_node, end_node, heuristic=h_fast, weight=weight_fastest)
# ...
weight_optimized = make_weight_optimized(w, hours_map, fallback_open)
path_optimized = nx.astar_path(G, start_node, end_node, heuristic=h_opt, weight=weight_optimized)
```

Remaining bottlenecks:

1. **Two full graph searches** on a 4M-edge graph.
2. **NetworkX A* in pure Python** — every relaxed edge invokes a Python callable.
3. **`make_weight_optimized` is expensive per edge** — string parsing, multipliers, and especially `_junction_danger_penalty` → `_count_car_physical_roads_at_node`, which scans all predecessors/successors at every visited head node when `junction_weight > 0`.
4. **Loose optimized heuristic** — `h = haversine × r_lb` ignores penalties, additives, hills, and live disruptions, so A* explores more nodes when safety toggles are on.
5. **Post-A* work** — WKT parsing in `extract_segment_geometry`, stats, and 7 separate overlay passes over the path.

---

## Improvement ideas (no implementation — ranked by likely ROI)

### Tier 1 — High impact, stays in current architecture

**1. Precompute per-edge costs for each request profile (biggest win)**  
For a fixed weight dict `w`, almost the entire cost function is deterministic per edge/node. You can compute once per request:

```text
weight[u→v] = f(edge_attrs, head_node_attrs, w, park_open?, live_disruption?)
```

Then A* reads from a `float32` array instead of calling Python. Same for fastest path + park blocks. This removes string parsing and junction re-counting from the search loop.

**2. Precompute junction danger at startup**  
`_count_car_physical_roads_at_node` depends only on static topology. Cache a boolean or fixed penalty on each node at bootstrap (like `JUNCTION_CLUSTER_SUPPRESSED`). Avoids O(degree) work on every A* edge relaxation.

**3. Materialize numeric edge layers at load time**  
At bootstrap, parse once into arrays: `length`, `grade`, `risk`, `is_lit`, `is_bad_surface`, `maxspeed_kmh`, `width_m`, TfL/green flags, pre-parsed barrier/additive costs, etc. The weight function becomes arithmetic on numbers, not dict/string lookups.

**4. Tighter admissible heuristic for optimized routing**  
Extend `compute_optimized_cost_per_metre_lower_bound` to include enabled penalty weights, e.g.:

```text
h(n) = haversine(n, goal) × max(R_MIN, r_lb) × max(M_MIN, 1 + sum of enabled penalty lower bounds)
```

Additives/hills can add a per-node lower bound (precomputed). Tighter `h` → fewer nodes expanded, still optimal.

**5. Merge post-route passes**  
One loop over path edges can produce stats + all overlay chunks; geometry can be fetched from precomputed coordinate arrays instead of re-parsing WKT per segment.

**6. Precompute edge geometries as coordinate lists at pipeline/bootstrap**  
Store `[lat, lon][]` per directed edge during graph build or first load. Removes Shapely WKT parsing from the request path entirely.

---

### Tier 2 — Medium effort, substantial speedup

**7. Replace NetworkX search with CSR + native library**  
Export adjacency in compressed sparse row form with integer node indices. Run A* via:

- **igraph** / **graph-tool** (C core, large speedups), or
- **SciPy `csgraph`** for Dijkstra when weights are precomputed arrays, or
- **Numba/Cython** custom A* on CSR arrays.

NetworkX dict-of-dicts overhead alone is significant at 4M edges.

**8. Bidirectional A***  
Search from start and goal simultaneously. Often cuts explored nodes by 50%+ on long London routes. Straightforward once you have CSR + array weights.

**9. Parallelize the two routes**  
Run fastest and optimized A* concurrently (`concurrent.futures`). With precomputed weight arrays and a native backend, this can nearly halve wall-clock A* time on multi-core hosts.

**10. Profile-level weight caching**  
Seed profiles (Safe Commuter, Fast & Direct, etc.) are fixed. Precompute and cache full edge-weight vectors per profile at startup; invalidate on live-disruption refresh or park-hours boundary crossings. Request path becomes: snap → lookup weights → A*.

**11. Lazy / deferred fastest route**  
Frontend already prefetches. Options:

- Return optimized route first; compute fastest asynchronously, or
- Skip fastest when profile is “Fast & Direct” (optimized ≈ fastest), or
- Cache fastest by `(start_cell, end_cell)` grid hash for repeat queries.

**12. Landmark (ALT) preprocessing**  
Precompute distances from ~16–32 landmark nodes across London. Use `max_i |d(L_i, n) − d(L_i, goal)|` as a stronger admissible heuristic. One-time offline cost; helps especially on cross-city queries.

---

### Tier 3 — Graph-level / architectural (larger refactors)

**13. Routing graph simplification (counter the noding blow-up)**  
~52% of edges are <10 m. Merge collinear micro-segments with identical tags back into a **routing supergraph** (~300k–500k edges) while keeping fine geometry only for display/inspect. Routing on the supergraph, geometry refinement on the chosen path — common in production routers.

**14. Contraction Hierarchies (CH) / Hub Labels**  
Preprocess offline on a base metric (length or a default profile). Query times drop to milliseconds. Harder with fully dynamic per-request weights, but workable if:

- CH on base length/fastest metric, dynamic penalties applied as small overlays, or
- CH per discrete profile preset (3–5 profiles), not continuous weights.

**15. External routing engine (GraphHopper already stubbed in `config.yml`)**  
GraphHopper, OSRM, or Valhalla with custom models can reach sub-100 ms queries at city scale. Trade-off: re-express the 14-factor cost model in their custom-weight DSL; live disruptions and park hours need integration hooks. Best if sub-100 ms is a hard product requirement.

**16. Hierarchical / corridor routing**  
Coarse graph (major roads + cycleways) for initial path, then local refinement in bounding corridor. Reduces search space for long trips without full CH infrastructure.

---

### Tier 4 — Smaller but easy wins

| Idea | Benefit |
|------|---------|
| Run under **Gunicorn** with persistent workers (no Flask reloader in prod) | Amortizes 4M-edge load; no cold-start per request |
| **Strip WKT `geometry` from RAM** after precomputing coords | Faster startup, better cache locality during routing |
| **Integer node IDs** instead of `(lon, lat)` tuples | Faster dict/hash lookups in A* |
| **Reach / bounding-box pruning** | Skip edges outside plausible corridor for long routes |
| **Benchmark matrix** with `route_benchmark.py --quick` on noded graph | Establish baseline before/after each optimization |

---

## Suggested investigation order

1. **Profile** with `ROUTE_BENCHMARK=1` on representative pairs (short inner-London, cross-city, heavy safety profile) on the **4M-edge** graph — split snap / fastest A* / optimized A* / post-processing.
2. **Precompute request weights + junction cache** — likely the best effort/reward ratio without leaving Python.
3. **CSR + igraph or Numba A*** — if still >500 ms after (2).
4. **Routing supergraph simplification** — if memory and search space remain problematic.
5. **CH / GraphHopper** — only if you need consistent sub-100 ms at scale with many concurrent users.

---

## Realistic expectations

| Approach | Typical cross-London target |
|----------|----------------------------|
| Current stack (4M edges, NetworkX, Python weights) | Hundreds of ms to several seconds |
| Precomputed weights + junction cache + tighter `h` | Often 2–5× faster |
| CSR + native A* + bidirectional | Often 10–30× faster vs raw NetworkX |
| Supergraph (~400k edges) + above | Approaching 50–200 ms |
| CH / GraphHopper / OSRM | Sub-50–100 ms |

The summary docs and `solve_tasks_brainstorming.md` already pointed at CH and external engines; the **noded mesh growth to 4M edges** makes **precomputed weights** and **graph simplification for routing** the most urgent new levers before a full engine swap.

---

*Research document — update when benchmarks are run or items move to `TASKS.md` / implementation.*
