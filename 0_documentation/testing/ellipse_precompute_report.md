# Ellipse + precompute benchmark

Generated: 2026-07-10T09:34:31.796519+00:00
Graph: 1,924,143 nodes, 4,061,447 edges
Preset: **safe** | ε = 0.5 | `DETOUR_MULTIPLIER` = 1.5

Pipeline per route: elliptical node filter → precompute `make_weight_optimized` on local edges → unidirectional A* with dict lookup.

Spec: [`route_generation_performance.md`](../route_generation_performance.md)

| Route | Global nodes | Ellipse nodes | Reduction % | Precompute (s) | A* (s) | Total (s) | Expansions | Length (m) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| route 1: Imperial to Kings Cross | 1,924,143 | 98,023 | 94.9% | 2.87 | 0.61 | 8.86 | 60,025 | 6657 |
| route 2: Imperial to Greenwich | 1,924,143 | 434,659 | 77.4% | 12.81 | 1.58 | 19.57 | 143,833 | 13935 |
| route 3: Imperial to New Spitalfields Market | 1,924,143 | 497,151 | 74.2% | 16.68 | 3.40 | 25.64 | 274,920 | 17711 |
| route 4: Twickenham Stadium to St. Pauls | 1,924,143 | 721,167 | 62.5% | 23.34 | 2.18 | 31.35 | 184,083 | 21583 |
| route 5: Wembley Stadium to Kings College Hospital | 1,924,143 | 609,292 | 68.3% | 19.68 | 2.40 | 28.51 | 203,888 | 22188 |
| route 6: Battersea Park to Temple | 1,924,143 | 78,096 | 95.9% | 2.47 | 0.11 | 7.99 | 10,853 | 5673 |
| route 7: Putney bridge to Notting Hill | 1,924,143 | 73,433 | 96.2% | 2.18 | 0.34 | 7.77 | 33,548 | 7672 |
| route 8: Tottenham Stadium to Hampstead | 1,924,143 | 175,344 | 90.9% | 5.40 | 0.89 | 11.54 | 87,805 | 13222 |
| route 9: Earls court to Piccadilly | 1,924,143 | 70,745 | 96.3% | 2.14 | 0.26 | 7.49 | 16,394 | 5660 |
| route 10: Bromley to Ealing | 1,924,143 | 1,262,663 | 34.4% | 48.21 | 8.31 | 61.98 | 673,615 | 33729 |
| route 11: Hill route, Elmers End to Streatham | 1,924,143 | 86,130 | 95.5% | 3.27 | 0.62 | 9.54 | 45,767 | 9636 |

## Notes

- `filter_s` (ellipse scan) is included in `total_s` but not shown in table columns; see JSON.
- Compare `total_s` to full-graph uni A* in [`routing_performance_report.md`](routing_performance_report.md).

Re-run: `python 4_backend_engine/benchmark_ellipse_precompute.py`

---

## Analysis vs unidirectional baseline (10 Jul 2026)

**Baseline:** safe-preset uni optimized A* from [`routing_performance_report.md`](routing_performance_report.md) (ε=0.5, 9 Jul).  
**Decision:** Do **not** ship eager ellipse + full-subgraph precompute as designed. Keep the insight that dict-lookup A* is fast; change *when* weights are paid for.

### Cost breakdown (means over 11 routes)

| Cost | Mean | Role |
|------|-----:|------|
| Ellipse filter | **5.50 s** | Fixed tax — hurts short hops most |
| Precompute | **12.64 s** | Scales with ellipse size — kills long hops |
| A* (dict lookup) | **1.88 s** | Actually good (max **8.31 s** on route 10) |
| **Total** | **20.02 s** | vs uni mean **6.61 s** |

### Per-route delta (ellipse total − uni)

| Route | Filter (s) | Precompute (s) | A* (s) | Total (s) | Uni (s) | Δ (s) | vs uni |
|-------|----------:|---------------:|-------:|----------:|--------:|------:|-------:|
| 1 Imperial→KX | 5.37 | 2.87 | 0.61 | 8.86 | 2.48 | **+6.38** | 3.57× |
| 2 Imperial→Greenwich | 5.17 | 12.81 | 1.58 | 19.57 | 5.62 | **+13.95** | 3.48× |
| 3 Imperial→Spitalfields | 5.56 | 16.68 | 3.40 | 25.64 | 11.93 | **+13.71** | 2.15× |
| 4 Twickenham→St Pauls | 5.84 | 23.34 | 2.18 | 31.35 | 7.51 | **+23.84** | 4.17× |
| 5 Wembley→KCH | 6.43 | 19.68 | 2.40 | 28.51 | 7.99 | **+20.52** | 3.57× |
| 6 Battersea→Temple | 5.42 | 2.47 | 0.11 | 7.99 | 0.42 | **+7.57** | **19.0×** |
| 7 Putney→Notting Hill | 5.25 | 2.18 | 0.34 | 7.77 | 1.40 | **+6.37** | 5.55× |
| 8 Tottenham→Hampstead | 5.26 | 5.40 | 0.89 | 11.54 | 4.01 | **+7.53** | 2.88× |
| 9 Earls Court→Piccadilly | 5.09 | 2.14 | 0.26 | 7.49 | 0.60 | **+6.89** | **12.5×** |
| 10 Bromley→Ealing | 5.46 | 48.21 | 8.31 | 61.98 | 28.20 | **+33.78** | 2.20× |
| 11 Elmers End→Streatham | 5.65 | 3.27 | 0.62 | 9.54 | 2.58 | **+6.96** | 3.70× |

**0/11 faster in total.** Short hops are crushed by the ~5.5 s filter alone. Route 10’s A* is 8.3 s (vs 28 s uni) but precompute is **48 s**.

### Correcting the short-vs-long intuition

- **Short routes got much worse — yes** (filter alone exceeds entire uni search on routes 6/9).
- **Long routes sped up a bit — no.** Route 10 total went **28.2 s → 62.0 s** (worse). Only the **A* leg** sped up (~3–4×); filter + precompute wiped the gain.

### What worked

Dict-lookup A* is ~22–30% of uni wall-clock if weights were free:

| Route | A* / uni |
|------:|---------:|
| 1 | 25% |
| 2 | 28% |
| 3 | 28% |
| 4 | 29% |
| 5 | 30% |
| 6 | 25% |
| 7 | 24% |
| 8 | 22% |
| 9 | 43% |
| 10 | 29% |
| 11 | 24% |

### Why eager precompute loses

Uni A* only evaluates `make_weight_optimized` on **relaxed** edges. Eager precompute evaluates it on **every edge in the ellipse**, including edges never visited. Route 10: ~674k expansions vs **1.26M ellipse nodes** → precompute walks far more work than search needs.

### Options to speed weight evaluation (for a future retry)

| Option | Notes |
|--------|-------|
| **A. Lazy / on-demand cache** | During A*: compute once per `(u,v)`, then dict lookup. No filter tax; only pay for edges actually relaxed. Highest ROI / simplest. |
| **B. Vectorize / strip cost fn** | Numeric edge arrays at load; NumPy/Numba apply profile weights. Helps uni today and any cache path. |
| **C. Parallel eager precompute** | Process pool over edge chunks. Route 10: 48 s → maybe ~12–15 s on 4 cores — still + filter, still likely worse than uni. |
| **D. Cheap spatial filter** | BBox / grid buckets so filter ≪ 0.2 s (current ~5.5 s scan of 1.9M nodes is fatal for short hops). |
| **E. Hybrid by hop length** | Plain uni under ~8 km; ellipse only on long hops — fixes short-route blowups, not route 10’s 48 s precompute. |

### Recommendation

1. Do **not** ship ellipse + eager full-subgraph precompute.
2. Keep the insight: once weights are O(1), A* is fine (≤8.3 s on the longest test route).
3. Next experiments: **lazy edge cache** → **cheap filter** (if still wanted) → **simplify/vectorize `make_weight_optimized`**.

Related: bi A* post-mortem in [`routing_performance_report.md`](routing_performance_report.md); backlog in [`route_generation_performance.md`](../route_generation_performance.md).