# Array-backed edge costs benchmark

Generated: 2026-07-10T12:08:42.647258+00:00
Graph: 1,924,143 nodes, 4,061,447 edges
Edge tables built once: **4,061,447** edges in **113.4 s** (startup cost, not per request)
Shared overlay bake: **0.034 s** (timer-style; impassable=199,155)
Heuristic epsilon: 0.5
Park hours exprs indexed: 50 | live overlay active: False

Compares **python** vs array **v2** vs **v3** (shared bake + live coeffs × `w_live` + fused impassable). Microbench also includes v1.

## Microbench (edge cost only, 200k edges, safe weights)

| Backend | Time (s) | µs / edge | vs python |
|---|---:|---:|---:|
| python | 19.914 | 99.57 | 1.00x |
| array v1 | 2.644 | 13.22 | 7.53x |
| array v2 | 1.828 | 9.14 | 10.9x |
| array v3 | 1.56 | 7.8 | **12.77x** |

v3 vs v2 microbench: **1.17x**

## Preset: fast

| Route | Python (s) | Array v2 (s) | Array v3 (s) | v2 speedup | v3 speedup | Path | Cost parity |
|---|---:|---:|---:|---:|---:|---|---|
| route 1: Imperial to Kings Cross | 3.46 | 1.50 | 1.33 | 2.31x | 2.60x | exact | ok |
| route 2: Imperial to Greenwich | 8.92 | 3.99 | 3.49 | 2.24x | 2.56x | exact | ok |
| route 3: Imperial to New Spitalfields Market | 16.83 | 6.53 | 5.68 | 2.58x | 2.96x | exact | ok |
| route 4: Twickenham Stadium to St. Pauls | 15.72 | 5.86 | 5.27 | 2.68x | 2.98x | exact | ok |
| route 5: Wembley Stadium to Kings College Hospital | 16.56 | 7.50 | 6.46 | 2.21x | 2.56x | exact | ok |
| route 6: Battersea Park to Temple | 2.17 | 1.14 | 0.97 | 1.89x | 2.22x | exact | ok |
| route 7: Putney bridge to Notting Hill | 1.34 | 0.69 | 0.59 | 1.95x | 2.28x | exact | ok |
| route 8: Tottenham Stadium to Hampstead | 12.48 | 4.33 | 3.38 | 2.88x | 3.70x | exact | ok |
| route 9: Earls court to Piccadilly | 1.24 | 0.65 | 0.56 | 1.90x | 2.22x | exact | ok |
| route 10: Bromley to Ealing | 54.00 | 17.76 | 15.27 | 3.04x | 3.54x | exact | ok |
| route 11: Hill route, Elmers End to Streatham | 1.27 | 0.60 | 0.52 | 2.11x | 2.45x | exact | ok |

## Preset: safe

| Route | Python (s) | Array v2 (s) | Array v3 (s) | v2 speedup | v3 speedup | Path | Cost parity |
|---|---:|---:|---:|---:|---:|---|---|
| route 1: Imperial to Kings Cross | 2.69 | 1.37 | 1.12 | 1.97x | 2.40x | exact | ok |
| route 2: Imperial to Greenwich | 5.86 | 3.21 | 2.76 | 1.83x | 2.12x | exact | ok |
| route 3: Imperial to New Spitalfields Market | 12.94 | 6.58 | 5.63 | 1.97x | 2.30x | exact | ok |
| route 4: Twickenham Stadium to St. Pauls | 8.24 | 4.08 | 3.45 | 2.02x | 2.39x | exact | ok |
| route 5: Wembley Stadium to Kings College Hospital | 8.93 | 4.43 | 4.01 | 2.01x | 2.23x | exact | ok |
| route 6: Battersea Park to Temple | 0.45 | 0.28 | 0.26 | 1.58x | 1.70x | exact | ok |
| route 7: Putney bridge to Notting Hill | 1.54 | 0.72 | 0.64 | 2.12x | 2.40x | exact | ok |
| route 8: Tottenham Stadium to Hampstead | 3.81 | 1.90 | 1.59 | 2.01x | 2.39x | exact | ok |
| route 9: Earls court to Piccadilly | 0.65 | 0.33 | 0.30 | 1.98x | 2.21x | exact | ok |
| route 10: Bromley to Ealing | 28.52 | 14.74 | 12.86 | 1.93x | 2.22x | exact | ok |
| route 11: Hill route, Elmers End to Streatham | 2.59 | 1.23 | 1.09 | 2.12x | 2.37x | exact | ok |

## How to read this

- **Table build** is paid once at process start (like graph load).
- **Shared bake** simulates the every-~5 min refresh (parks + live coeffs + fused `impassable[]`); not paid per `/route`.
- **v2** = `_eid` + park uint8 by id + live arrays scaled by `w_live` per request.
- **v3** = shared bake; jam-comfort is scalar `w_live` × coeffs; one `impassable[i]` check.
- **Cost parity** checks v3 costs on the python path match python costs.

Re-run: `python 4_backend_engine/benchmark_array_costs.py`

Spec: [`route_generation_performance.md`](../route_generation_performance.md)

---

## Analysis (10 Jul 2026) — array v3

**Decision:** v3 is a **clear incremental win** over v2 — exact paths + cost parity on **22/22**, microbench **12.8×** vs python (**1.17×** vs v2), full A* **~2.2–3.7×** (fast, median ~2.56×) / **~1.7–2.4×** (safe, median ~2.30×). Shared bake is **34 ms**. Ship **v3** (not v2) into `/route`. Further weight-callback thinning is low ROI; next wins are outside the cost fn (see substep profile).

### Headline

| Layer | Result |
|-------|--------|
| Microbench py → v3 | **12.77×** (99.6 → 7.8 µs/edge) |
| Microbench v2 → v3 | **1.17×** |
| Full A* fast (v3 vs py) | **2.22–3.70×** (median **2.56×**) |
| Full A* safe (v3 vs py) | **1.70–2.40×** (median **2.30×**) |
| v3 vs v2 full A* | **~1.08–1.28×** (median ~1.15×) |
| Path / cost fidelity | Exact + parity **22/22** |
| Shared bake | **0.034 s** |

### Python vs array — functionality / precision flags

| Area | Same as python? | Notes |
|------|-----------------|-------|
| Core cost formula (risk, hills, rewards, barriers, VF masks) | **Yes** (bench parity) | Same linear combo of bases × request weights |
| Exact path under ε-search | **Yes** on 22/22 | Expansions matched |
| Closures hard-block | **Yes** | In `impassable`, independent of `w_live` |
| Soft live × jam comfort | **Yes if coeffs applied as two mults** | Must use `(1+env×c)×(1+sev×c)`, not summed extras — fixed in script after review |
| Park open/closed (per-request bake) | **Yes** | v2-style expr map |
| Park open/closed (**timer** shared bake) | **Approx** | Can be stale until next refresh (dawn/dusk). Prefer refresh parks with live (~1–5 min) or rebuild `park_open` per request (50 exprs, ~ms) |
| `calming_source` | **Only if `"both"`** | Tables bake `_traffic_calming_additive(d, "both")`. Production hardcodes `CALMING_SOURCE="both"` — OK. `"way"` / `"point"` alone would diverge |
| `pedestrian_highway_m` override | **No** | Python can override highway multiplier per request; arrays bake default at load. Unused in normal UI |
| `bike_type` | **Cargo vs not** | Only cargo adds `hard_cargo`. `road` ≡ `standard` for barriers (same as python) |
| Fastest leg | **Not arrayed yet** | `/route` still uses `make_weight_fastest` (python). Opt-only speedup until fastest is ported |
| Live empty vs loaded | Bench had **live=False** | Soft-coeff path untested under real TfL/TomTom; re-bench with live on before ship |
| Float bit-identity | **Near** | Cost parity within atol; not bitwise identical to every intermediate python float |
| Debug overlays / stats | **Unchanged** | Still read NetworkX edge attrs on the path |

**Bottom line:** For production profiles (calming=`both`, no `pedestrian_highway_m`, parks refreshed often enough), **no user-visible functionality loss**. Timer parks are the only intentional approximation; keep per-request park bits if you want second-level accuracy.

### Substep profile (route 2 Imperial→Greenwich, safe)

Script: `python 4_backend_engine/profile_route_substeps.py` (10 Jul 2026). Times include per-call weight instrumentation (slightly inflated vs bare bench).

| Step | Time | Share of full /route (python opt) |
|------|------|-------------------------------------|
| Snap ×2 | **66 ms** | ~0.6% |
| Park hours context | **2 ms** | — |
| Fastest A* (python) | **1.75 s** | ~17% |
| Optimized A* python | **8.4 s** (weight ~62%, overhead ~38%) | ~80% |
| Optimized A* v3 | **3.7 s** (weight ~52%, overhead ~48%) | — |
| Geometry + stubs | **119 ms** | ~1% |
| Path stats | **17 ms** | — |
| Overlay chunks | **108 ms** | ~1% |
| **Full /route est.** | **~10.5 s** py / **~5.8 s** v3 opt | |

Where time goes after v3:

1. **A* search overhead** (~1.8 s on this route with v3) — heap + `G.succ` + heuristic. Not fixed by thinner weight fns.
2. **Remaining weight cost** (~1.9 s instrumented) — still ~half of opt A*; more array micro-opts help little.
3. **Fastest leg** (~1.75 s) — still python; array-ify or run in parallel with optimized.
4. **Post-search** (~0.25 s) — secondary.

### Non-Numba speedups (ordered)

1. **Ship array v3 for optimized (+ fastest)** — largest proven win.
2. **Parallel fastest ∥ optimized** — wall clock ≈ max(fast, opt) instead of sum (~1.5–2 s off medium routes).
3. **Pure-Python CSR neighbor lists** — replace `G.succ` / `G[u][v]` in A* with `indptr`/`indices`/`eid` arrays (no Numba). Targets the ~40–50% overhead slice.
4. **Higher ε / tighter heuristic** — fewer expansions (quality trade-off; already tuned).
5. **Defer overlays** — geometry/overlays are ~0.25 s; only matters when A* is already fast.
6. **Do not** expect another 2× from weight-callback thinning alone.

### Related

- Bi post-mortem: [`routing_performance_report.md`](routing_performance_report.md)
- Ellipse analysis: [`ellipse_precompute_report.md`](ellipse_precompute_report.md)
- Backlog: [`route_generation_performance.md`](../route_generation_performance.md)
