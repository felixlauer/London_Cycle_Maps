# Routing performance master report (v0 → Numba)

**Date:** 11 Jul 2026  
**Scope:** A* wall time on the London cycle graph (~1.92M nodes, ~4.06M edges), dual legs (fastest + optimized) unless noted.  
**Status:** Array costs v4 + CSR A/B + **Numba Phase C** + **geometry Phase D** shipped (default ON). Path/cost parity held through A–C; path geom ~37× once warm.

This is the single overview of what we tried, what shipped, what failed, and how today’s stack compares to the original Python baseline.

---

## 1. Verdict

**Yes — this is a major win.** Phase C alone is **~11× mean** vs pure-Python CSR A* (fastest **~12.5×**, optimized **~9.8×**), with **44/44** exact path + expansion + cost parity.

Chained against the **original Python weight functions** (v0 / “prod” in the v4 bench), long-route A* walls are roughly **~20–30×** faster on the same corridors — well past the informal **10×** goal for search.

**Nothing else is required for the CSR/Numba A* + path-geometry program.** Optional: live soak, UI loading polish, GIL-free parallel legs.

---

## 2. Baseline ladder (what “v0” means)

| Label | Meaning | Where measured |
|-------|---------|----------------|
| **v0 / prod** | NetworkX uni A* + **Python** `make_weight_fastest` / `make_weight_optimized` | [`array_costs_v4_report.md`](array_costs_v4_report.md) |
| **v3** | Python fastest + **array** optimized | same |
| **v4** | **Array** fastest + array optimized (shipped) | same |
| **NX array** | v4-style array costs, still NetworkX neighbor walk | [`csr_astar_phase_a_report.md`](csr_astar_phase_a_report.md) |
| **CSR-py (A/B)** | CSR neighbors + array `cost_by_eid` + radian heuristic | Phase A/B/C reports |
| **Numba (C)** | Same CSR + costs, `@njit` heap/search | [`csr_astar_phase_c_report.md`](csr_astar_phase_c_report.md) |

**Caveats when chaining across reports**

- v4 bench used **`ε_opt=0.5`**; CSR/Numba benches used production **`ε_opt=0.75`** (fewer opt expansions → faster opt legs). Fastest ε stayed **0**.
- Different process runs / machine load → treat cross-report ratios as **order-of-magnitude**, not bit-identical.
- Numbers below are **A* only** (snap + WKT geometry excluded). End-to-end `/route` still pays snap (~tens–hundreds ms) + path geometry (~100–200+ ms).

---

## 3. Headline multipliers

### 3.1 Incremental (same-bench, clean)

| Step | Baseline → | Mean speedup | Parity | Ship? |
|------|------------|--------------|--------|-------|
| Array v3 vs Python opt | Python weights | ~2.2–3.7× fast / ~1.7–2.4× safe (full A*) | 22/22 | Yes (into v4) |
| Array v4 wall vs v0 | Python both legs | **~2.41×** fast / **~2.03×** safe (median wall) | 22/22 | Yes |
| CSR Phase A vs NX array | Array + NX | **~1.67×** all legs (~1.90× fast / ~1.43× opt) | 44/44 | Yes |
| CSR Phase B vs Phase A | CSR lon/lat → radians | **~1.05×** | 88/88 | Yes (hygiene) |
| **Numba Phase C vs CSR-py** | CSR-py Phase B | **~11.2×** all (~12.5× fast / ~9.8× opt) | **44/44** | **Yes** |
| **Geometry Phase D** | Cold WKT path reconstruct | **~37×** mean (0.14 → 0.004 s); full parse ~221 s background | n/a (same coords) | **Yes** |

### 3.2 Cumulative vs v0 (illustrative chain)

Rough product on A* wall (order-of-magnitude):

```text
v0 ──~2×──► v4 arrays ──~1.7×──► CSR-py ──~11×──► Numba
         ≈  ~35–40× theoretical product on some legs;
         measured corridor walls ≈ 20–30× (ε / mix effects)
```

| Corridor (safe, dual-leg A* sum) | v0 prod (ε≈0.5) | v4 seq | CSR-py (ε=0.75) | Numba | ≈ vs v0 |
|----------------------------------|-----------------|--------|-----------------|-------|---------|
| **Bromley ↔ Ealing** | **32.0 s** | 17.0 s | ~12.0 s | **~1.29 s** | **~25×** |
| **Imperial → King’s Cross** | **2.92 s** | 1.44 s | ~1.1 s | **~0.11 s** | **~25×** |

| Corridor (fast preset, dual-leg sum) | v0 prod | v4 seq | Numba | ≈ vs v0 |
|--------------------------------------|---------|--------|-------|---------|
| **Bromley ↔ Ealing** | **47.6 s** | 18.9 s | **~1.46 s** | **~33×** |
| **Imperial → King’s Cross** | **6.02 s** | 1.52 s | **~0.13 s** | **~45×** |

Phase C detail (Bromley safe): CSR-py **2.55 + 9.40 s** → Numba **0.21 + 1.09 s**.

---

## 4. What worked (shipped)

### 4.1 Heuristic ε = 0.75 (optimized only)

- Bounded-suboptimal A*; exact path match vs 0.5 on tested Safe routes; large opt expansion cut on long hops.
- Fastest ε &gt; 0 **rejected** (path divergence on Bromley / Imperial).
- Doc: [`ROUTE_HEURISTIC_EPSILON.md`](../ROUTE_HEURISTIC_EPSILON.md)

### 4.2 Array-backed edge costs (v1→v4)

- Load-time numeric tables + `_eid`; shared park/live overlays (~45 ms bake).
- Microbench ~**13×** per-edge; full A* ~**2×** wall vs Python weights.
- Kill-switch: `ARRAY_COSTS=0`.
- Docs: [`array_costs_report.md`](array_costs_report.md), [`array_costs_v4_report.md`](array_costs_v4_report.md)

### 4.3 CSR Phase A (pure Python)

- Replace `G.succ` / `G[u][v]` with `indptr` / `indices` / `eid`; lat/lon arrays for h.
- **~1.67×** vs NX array; Bromley fastest **6.7→2.5 s**.
- Kill-switch: `CSR_ASTAR=0` (search only).
- Doc: [`csr_astar_phase_a_report.md`](csr_astar_phase_a_report.md)

### 4.4 CSR Phase B (radians + NX heuristic wiring)

- Precompute `lat_rad` / `lon_rad` / `cos_lat`; NX/bi heuristics use CSR arrays.
- True A→B delta only **~5%**; still ship (cheap, correct place for Numba too).
- Doc: [`csr_astar_phase_b_report.md`](csr_astar_phase_b_report.md)

### 4.5 Numba Phase C (compiled A*)

- Entire hot loop in `@njit`: heap, neighbors, cost, heuristic.
- **~11×** vs CSR-py; **44/44** parity; bootstrap warmup ~**19 s** once.
- Kill-switch: `NUMBA_ASTAR=0`.
- Doc: [`csr_astar_phase_c_report.md`](csr_astar_phase_c_report.md)

---

## 5. What did not work (do not ship / reverted)

| Approach | Result | Why |
|----------|--------|-----|
| **Bidirectional A* as default** | ~**2× slower** wall + expansions | Extra work; uni already guided well | [`routing_performance_report.md`](routing_performance_report.md) |
| **Ellipse filter + eager weight precompute** | **0/11** faster in total | Filter + precompute dominate; short hops regress hard | [`ellipse_precompute_report.md`](ellipse_precompute_report.md) |
| **Thread-parallel fast∥opt (CPython)** | ≈ sequential (sometimes worse) | GIL serializes pure-Python A* | [`array_costs_v4_report.md`](array_costs_v4_report.md) |
| **Fastest-leg ε ≥ 0.5** | Path mismatch on long corridors | Exact fastest required | `bench_fastest_heuristic_epsilon` |
| **Precompute one float cost per edge per profile** | Rejected by design | Dynamic weights / live / parks | FR non-goal |

---

## 6. Phase C result snapshot (11 Jul 2026)

From [`csr_astar_phase_c_report.md`](csr_astar_phase_c_report.md):

| Metric | Value |
|--------|-------|
| Parity | **44/44** OK |
| Mean CSR-py → Numba (all) | **11.15×** |
| Mean fastest | **12.54×** |
| Mean optimized | **9.76×** |
| Bromley fast (fastest leg) | 2.76 → **0.24 s** (11.3×) |
| Bromley fast (opt leg) | 11.15 → **1.22 s** (9.1×) |
| Bromley safe (opt leg) | 9.40 → **1.09 s** (8.7×) |
| Imperial→KX safe (both legs) | ~1.1 → **~0.11 s** |

**Analysis:** Numba delivers the FR’s “another large cut” and exceeds the ~3–8× vs array+NX band when measured vs CSR-py (~11×). Combined with arrays + CSR, search is no longer the multi-ten-second problem it was on Bromley.

---

## 7. Is there anything else to implement?

### Required for the A* program: **No**

Ship/keep current defaults (`ARRAY_COSTS`, `CSR_ASTAR`, `NUMBA_ASTAR` on). Kill-switches remain for A/B.

### Optional / parallel (not blockers)

| Item | Why | Priority |
|------|-----|----------|
| **Review keep `GEOM_PREPARSE`** | Full warm ~**4 min** after boot; decide keep / lazy (`0`) / narrower set | Open — see Phase D report |
| **Startup + RAM bench** | Phase wall + RSS ready/geom/idle — run locally | `python 4_backend_engine/benchmark_startup_ram.py` → [`startup_ram_report.md`](startup_ram_report.md) |
| **Routing cache prebuild** | Static tables/CSR/junctions/geom next to graph | [`ROUTING_CACHE.md`](../ROUTING_CACHE.md); measured: geom wait **0** (was 5.1 min), idle RSS **5.46 GiB** (was 8.04); ready still ~8.4 min (apply 441 s) |
| **Live soak with Numba** | Soft live coeffs path under real TfL/TomTom | Medium |
| **Real-app smoke** | Confirm `meta.numba_astar`, warm compile, Bromley &lt;~2–3 s A* | Medium (quick) |
| **Parallel fast∥opt** | Numba can release GIL — theo overlap may finally pay | Low (opt dominates; modest win) |
| **UI loading animation** | Product polish while waiting | Separate track |
| **C++/Rust search core** | Unlikely needed after Numba | Skip unless Numba regresses |

---

## 8. Production stack (today)

```text
Bootstrap
  NetworkX load → edge tables + _eid → SharedOverlays → CSR (+ radians) → Numba warmup

/route (uni, default)
  snap → pack scalars → Numba A* (fastest) → Numba A* (optimized)
       → reconstruct geometry / stats / overlays (Python + NX on path only)

Fallbacks
  NUMBA_ASTAR=0 → CSR-py A*
  CSR_ASTAR=0   → NX uni A* (arrays + CSR heuristics still available)
  ARRAY_COSTS=0 → Python weight fns + NX A*
```

---

## 9. Source index

| Topic | Doc / script |
|-------|----------------|
| Backlog / FR | [`route_generation_performance.md`](../route_generation_performance.md), [`FR_csr_numba_astar.md`](FR_csr_numba_astar.md) |
| ε | [`ROUTE_HEURISTIC_EPSILON.md`](../ROUTE_HEURISTIC_EPSILON.md) |
| Bi A* post-mortem | [`routing_performance_report.md`](routing_performance_report.md) |
| Ellipse fail | [`ellipse_precompute_report.md`](ellipse_precompute_report.md) |
| Arrays v1–v4 | [`array_costs_report.md`](array_costs_report.md), [`array_costs_v4_report.md`](array_costs_v4_report.md) |
| CSR A / B / C | [`csr_astar_phase_a_report.md`](csr_astar_phase_a_report.md), [`csr_astar_phase_b_report.md`](csr_astar_phase_b_report.md), [`csr_astar_phase_c_report.md`](csr_astar_phase_c_report.md) |
| Benches | `benchmark_array_v4.py`, `benchmark_csr_astar.py`, `benchmark_csr_phase_b.py`, `benchmark_csr_numba.py` |

---

## 10. Bottom line

| Question | Answer |
|----------|--------|
| Did we hit ~10×? | **Yes** — Phase C alone ~**11×** vs CSR-py; vs v0 Python often **~20–30×+** on A* wall |
| Correctness? | **Exact path + expansions + cost** through Numba (44/44) |
| More CSR/Numba work needed? | **No** for search; optional geometry / live soak / UI |
| Biggest remaining TTF slice? | Snap + **path geometry**, not A* on most routes |
