# Feature request: CSR A* (+ optional Numba) for dynamic array costs

**Status:** Phase A/B/C **shipped** (11 Jul 2026) — Numba ~11× vs CSR-py, 44/44 parity  
**Depends on:** Array costs v4 live ([`edge_cost_arrays.py`](../../4_backend_engine/edge_cost_arrays.py)) — **done**  
**Related:** [`routing_performance_master.md`](routing_performance_master.md) (full baseline ladder), [`route_generation_performance.md`](../route_generation_performance.md), phase A/B/C reports  
**Owner:** routing performance  
**Code:** [`graph_csr.py`](../../4_backend_engine/graph_csr.py), [`pathfinding.py`](../../4_backend_engine/pathfinding.py), [`pathfinding_numba.py`](../../4_backend_engine/pathfinding_numba.py). Kill-switches: `CSR_ASTAR=0`, `NUMBA_ASTAR=0`. Benches: `benchmark_csr_astar.py`, `benchmark_csr_phase_b.py`, `benchmark_csr_numba.py`.

---

## 1. Problem

After array-backed edge costs, `/route` A* is still dominated by **Python search overhead**, not by the cost formula:

| Slice (route 2 Safe, instrumented, post-v3) | Share of opt A* |
|---------------------------------------------|-----------------|
| Weight / array formula | ~50–55% |
| Heap + `G.succ` + `G[u][v]` + heuristic dicts | ~40–50% |

Arrays made each expansion cheaper; they did **not** remove NetworkX neighbor walks, dict edge attrs, or `G.nodes[u]` haversine lookups. On long hops (Bromley↔Ealing) that still means:

- Fastest (exact, simple cost): ~9–15 s, ~290k expansions  
- Optimized (ε=0.75): ~16–18 s, ~480k expansions  

ε cannot fix fastest without changing the path (exact-match sweep failed at ε≥0.5). Next wins must cut **work per expansion** and/or **Python interpreter tax** on the search loop itself.

---

## 2. Why this works with our dynamic functions (certainty)

We are **sure** this architecture is compatible with today’s dynamic routing, because dynamics are already factored into **arrays + scalars** prepared in Python. CSR/Numba only change *how* we walk the graph and evaluate the same formula — not *what* the formula is.

### 2.1 What is already “static enough” for a compiled loop

| Input | Cadence | Where it lives today | Inside CSR / Numba loop? |
|-------|---------|----------------------|---------------------------|
| Topology (neighbors) | Graph load | NetworkX `G.succ` | → CSR `indptr` / `indices` / `eid` once at bootstrap |
| `length`, `risk`, `m_highway`, VF flags, hill/barrier bases, … | Graph load | `EdgeCostTables` | Yes — array loads by `eid` |
| Hard static / cargo | Graph load | `hard_static`, `hard_cargo` | Yes |
| Park open bits | Startup + live refresh (~5–10 min) | `SharedOverlays.park_*` | Yes — `if is_park[i] and not park_open[pid]: hard` |
| Live closed + soft coeffs | Same timer | `live_closed`, `live_add_*`, … | Yes — bake after fetch; scale soft by `w_live` scalar |
| Continuous weights (`risk_weight`, …) | Per `/route` | Python dict `w` | Yes — **scalars** copied into locals before search |
| VF toggles (3 bools) | Per `/route` | → `vf_mask`, `vf_reward` ints | Yes — `bool(vf_flags[i] & mask)` |
| ε / heuristic scale | Per `/route` | `scale`, `scale_fast` | Yes — scalar × haversine(lat[u], lon[u], …) |
| `opening-hours-py`, TfL/TomTom HTTP, NetworkX load | Outside A* | Python | **No** — stay in Python |

Rider choice does **not** require precomputing one float per edge per profile. Same design as v3/v4:  
`cost = f(edge_row[eid], scalars, overlay_row[eid])`.

### 2.2 What must stay outside Numba (and already does)

- Parsing OSM / building the graph  
- Evaluating opening-hours strings → `park_open[]`  
- Fetching/merging live disruptions → `MASTER_LIVE_LOOKUP` → overlay bake  
- Profile store, clamps, light gating, auth  
- Path geometry / stats / overlays (can stay NetworkX on the **path only**)

Numba never calls NetworkX or `opening-hours-py`. Python prepares; Numba searches.

### 2.3 Correctness contract

1. **Same formula** as `make_array_weight_fn_fastest` / `_optimized` (bit-close float parity within existing atol).  
2. **Same impassable semantics** as `SharedOverlays.impassable`.  
3. **Same heuristic** as `make_heuristic` with stamped lat/lon arrays.  
4. Kill-switches: fall back to current `pathfinding.astar_unidirectional` + array weight fns if CSR/Numba disabled or fails to compile.

If those hold, paths and costs match today’s array path — only wall time changes.

---

## 3. Proposed work (phased)

### Phase A — Pure-Python CSR A* (no Numba) — **shipped (11 Jul 2026)**

**Goal:** Replace `for neighbor in G.succ[current]` + `G[u][v]` with typed neighbor lists; keep weight fn as today’s array closures **or** inline the same arithmetic in Python over `eid`.

**Shipped:**

- Bootstrap builds CSR after edge tables (`graph_csr.build_csr`); uni `/route` uses `astar_csr_unidirectional` when `CSR_ASTAR` is on (default) and arrays are available; `?alg=bi` stays on NetworkX.
- Cost via `make_array_cost_by_eid_fastest` / `_optimized` (same formula as weight fns).
- Kill-switch: `CSR_ASTAR=0|false|no|off`.
- Lat/lon arrays already used inside CSR A* (Phase B precursor).

**Result:** See [`csr_astar_phase_a_report.md`](csr_astar_phase_a_report.md) — **44/44** parity; mean **1.665×** vs NX array; Bromley fastest **2.66×** (6.73→2.53 s).

**Build once at bootstrap (after edge tables):**

```text
node_id → dense index 0..N-1
indptr[N+1], indices[E], eid[E]   # CSR of successors
lat[N], lon[N]                    # heuristic (no G.nodes dict)
```

**Search:** same uni A* as [`pathfinding.py`](../../4_backend_engine/pathfinding.py), but:

- neighbors via `indices[indptr[u]:indptr[u+1]]`
- cost via `eid[k]` into existing `EdgeCostTables` + `SharedOverlays`
- heuristic via `lat[u], lon[u]`

**Acceptance:** ✅ met (path + expansions + cost atol; wall reported).

**Expected improvement (Phase A only):**  
Roughly **~1.2–1.5×** on A* wall — **observed ~1.4–1.9× mean** (faster on fastest legs). Still valuable and de-risks Phase B/C.

### Phase B — Hotter lat/lon heuristic (radians + NX wiring) — **shipped (11 Jul 2026)**

Phase A already removed `G.nodes[u]` inside CSR A*. Phase B finished the FR item:

1. **Precompute** `lat_rad`, `lon_rad`, `cos_lat` on the CSR for cheaper haversine (production `heuristic_mode=phase_b`).
2. **Wire** NetworkX / bidirectional heuristics to the same arrays (`make_heuristic(..., csr=)`).
3. CSR is **always built** after edge tables; `CSR_ASTAR` only gates CSR **search**.

**Result:** See [`csr_astar_phase_b_report.md`](csr_astar_phase_b_report.md) — **88/88** parity; mean **A→B ~1.05×**; nodes→B **~1.35×** (mostly Phase A lat/lon); NX heuristic **~1.14×**.

**Acceptance:** ✅ met. Small incremental win; keep on.
### Phase C — Numba `@njit` uni A* over the same CSR — **shipped (11 Jul 2026)**

**Goal:** Entire hot loop (heap + neighbors + cost + heuristic) in compiled code; **no Python objects** on the path.

**Shipped:**

- [`pathfinding_numba.py`](../../4_backend_engine/pathfinding_numba.py) — `@njit` fastest + optimized cost + uni A*; scratch buffers; bootstrap warmup.
- `/route` prefers Numba → CSR py → NX when `NUMBA_ASTAR` on (default) and `numba` installed.
- Kill-switch: `NUMBA_ASTAR=0|false|no|off`. Response `meta.numba_astar`.
- Dependency: `numba>=0.59.0` in `requirements.txt`.

**Result:** See [`csr_astar_phase_c_report.md`](csr_astar_phase_c_report.md) — **44/44** parity; mean **11.15×** vs CSR-py (**12.54×** fastest / **9.76×** optimized). Master ladder vs v0: [`routing_performance_master.md`](routing_performance_master.md).

**Acceptance:** ✅ met.
### Phase D — Pre-parse / cache path geometries — **implemented (11 Jul 2026)**

`reconstruct_path_geometry` → `load_wkt` per path edge (~100+ ms cold). Phase D parses every edge WKT once into `d['_coords']`.

**Shipped:**

- `edge_cost_arrays.preparse_edge_geometries` + background/sync modes
- Default **`GEOM_PREPARSE=background`** (daemon after bootstrap; does not block serve)
- `GEOM_PREPARSE=sync` blocks until ready; `GEOM_PREPARSE=0` keeps lazy-on-first-use
- Response `meta.geom_preparse` reports `{state, n_parsed, elapsed_s, ...}`
- Bench: `python 4_backend_engine/benchmark_geom_preparse.py` → [`geom_preparse_phase_d_report.md`](geom_preparse_phase_d_report.md)

**Helps TTF, not A*.** Full-graph parse takes ~**4 min** (~221 s) once. Background is the production default so serve is not blocked.

**Open review:** Whether to **keep** full-graph `GEOM_PREPARSE=background` given that ~4 min warm cost after every process start. Alternatives: `GEOM_PREPARSE=0` (lazy), narrower warm set, or sync only on long-lived workers.

---

## 4. Explicit non-goals

- Precomputing one float cost per edge per custom profile  
- Putting opening-hours or HTTP inside Numba  
- Thread-parallel fast∥opt under CPython GIL (revisit on free-threaded CPython / after Numba releases GIL)  
- Shipping ε on fastest after failed exact-match sweeps  
- Replacing the graph file format (NetworkX remains source of truth at load)

---

## 5. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Node key type (tuple osm ids) → dense index bugs | Bijection tests; path remap round-trip |
| Numba compile failure / version skew | Kill-switch; CI smoke with/without Numba |
| Float drift vs Python weight fn | Same atol as array v3/v4 benches |
| Park/live staleness | Unchanged — same `SharedOverlays` bake cadence |
| Heap performance in pure Python CSR | Phase A may be modest; Phase C is the big win — don’t abandon after A alone |
| Memory | CSR ~O(E) int32 + lat/lon; fine next to existing tables |

---

## 6. Implementation sketch (files)

| Piece | Likely location |
|-------|-----------------|
| CSR build from `G` + `_eid` | `edge_cost_arrays.py` or new `graph_csr.py` |
| Pure-Python CSR A* | `pathfinding.py` or `pathfinding_csr.py` |
| Numba A* | `pathfinding_numba.py` (`@njit`) |
| Wire `/route` | `app.py` — prefer Numba → CSR py → current |
| Bench | `benchmark_csr_astar.py` → `0_documentation/testing/csr_astar_report.md` |

---

## 7. Success metrics

1. **Parity:** 11 routes × {fastest, safe optimized} exact path (or documented ε policy) + cost atol.  
2. **Speed:** median A* wall vs current array baseline on routes 1 and 10; publish Phase A and Phase C separately.  
3. **Ops:** `ARRAY_COSTS` / `CSR_ASTAR` / `NUMBA_ASTAR` kill-switches documented in `startup.md` / `APP_MAIN.md`.  
4. **No regression** on Imperial→KX short-hop UX (&lt;2 s total preferred after Phase C).

---

## 8. Recommendation

**Proceed.** Dynamics are already array/scalar-shaped; CSR+Numba is the standard next step and does not fight park hours, live closures, VF masks, or continuous weights.  

**Order:** Phase A (CSR Python) → measure → Phase C (Numba) → Phase D (geometry) as polish. Do not jump to Numba without CSR + dense node ids; that is the hard prerequisite either way.
