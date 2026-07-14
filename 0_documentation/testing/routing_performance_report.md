# Routing performance report

Generated: 2026-07-09T19:12:56.723803+00:00
Graph: 1,924,143 nodes, 4,061,447 edges
Heuristic epsilon: 0.5

Optimized A* only (single search per run). Compares unidirectional (`alg=uni`, **production default**) vs bidirectional (`alg=bi`, experimental).

## Preset: fast

| Route | Uni (s) | Bi (s) | Speedup | Uni expansions | Bi expansions | Length delta (m) | Path match |
|---|---:|---:|---:|---:|---:|---:|---|
| route 1: Imperial to Kings Cross | 3.90 | 7.14 | 0.55x | 68830 | 148283 | +0 | exact |
| route 2: Imperial to Greenwich | 9.46 | 18.88 | 0.50x | 186659 | 374797 | +0 | exact |
| route 3: Imperial to New Spitalfields Market | 15.59 | 33.95 | 0.46x | 308901 | 653931 | +0 | exact |
| route 4: Twickenham Stadium to St. Pauls | 15.83 | 28.00 | 0.57x | 277664 | 586459 | +6 | jaccard 0.90 |
| route 5: Wembley Stadium to Kings College Hospital | 18.32 | 40.81 | 0.45x | 353653 | 834055 | +0 | exact |
| route 6: Battersea Park to Temple | 2.56 | 5.74 | 0.45x | 58790 | 123897 | +0 | exact |
| route 7: Putney bridge to Notting Hill | 1.74 | 3.21 | 0.54x | 36164 | 67806 | +0 | exact |
| route 8: Tottenham Stadium to Hampstead | 8.96 | 12.20 | 0.73x | 167666 | 262383 | +0 | exact |
| route 9: Earls court to Piccadilly | 1.17 | 2.89 | 0.41x | 30743 | 69716 | +0 | exact |
| route 10: Bromley to Ealing | 45.76 | 86.42 | 0.53x | 774067 | 1683789 | +0 | exact |
| route 11: Hill route, Elmers End to Streatham | 1.25 | 3.60 | 0.35x | 32209 | 86133 | +0 | exact |

## Preset: safe

| Route | Uni (s) | Bi (s) | Speedup | Uni expansions | Bi expansions | Length delta (m) | Path match |
|---|---:|---:|---:|---:|---:|---:|---|
| route 1: Imperial to Kings Cross | 2.48 | 5.86 | 0.42x | 62853 | 138679 | +0 | exact |
| route 2: Imperial to Greenwich | 5.62 | 10.74 | 0.52x | 143768 | 254591 | +0 | exact |
| route 3: Imperial to New Spitalfields Market | 11.93 | 23.63 | 0.50x | 274796 | 492479 | +0 | exact |
| route 4: Twickenham Stadium to St. Pauls | 7.51 | 26.97 | 0.28x | 184073 | 631382 | +0 | exact |
| route 5: Wembley Stadium to Kings College Hospital | 7.99 | 29.62 | 0.27x | 203906 | 694026 | +0 | exact |
| route 6: Battersea Park to Temple | 0.42 | 1.17 | 0.36x | 10853 | 27519 | +0 | exact |
| route 7: Putney bridge to Notting Hill | 1.40 | 2.88 | 0.49x | 36305 | 70213 | +0 | exact |
| route 8: Tottenham Stadium to Hampstead | 4.01 | 6.49 | 0.62x | 90283 | 154352 | +0 | exact |
| route 9: Earls court to Piccadilly | 0.60 | 2.47 | 0.24x | 16394 | 59889 | +0 | exact |
| route 10: Bromley to Ealing | 28.20 | 69.11 | 0.41x | 674028 | 1539998 | +0 | exact |
| route 11: Hill route, Elmers End to Streatham | 2.58 | 7.87 | 0.33x | 66095 | 193273 | +0 | exact |

## Summary

- **fast** mean speedup (uni/bi): **0.5x**
- **safe** mean speedup (uni/bi): **0.4x**

Re-run: `python 4_backend_engine/benchmark_routing.py`

---

## Post-mortem: why bidirectional A* failed (9 Jul 2026)

**Decision:** Production default reverted to **unidirectional** (`ROUTE_ALGORITHM=uni`). Bidirectional code kept in `pathfinding.py` for future experiments (`?alg=bi`).

### What the benchmark proved

Bidirectional was not slightly slower — it did **~2× the work**:

| Metric | Pattern |
|--------|---------|
| Node expansions | Bi ≈ **2.1–2.3×** uni on every route (e.g. route 1 safe: 62k → 139k; route 10 safe: 674k → 1.54M) |
| Edge relaxations | Same ~2× ratio |
| Wall-clock | Bi **~2× slower** (report “speedup” 0.4–0.5× = uni wins) |
| Route quality | Paths still matched uni (20/22 exact) — correctness OK, performance bad |

So this was not Python constant overhead; both frontiers each explored roughly a **full unidirectional search** before stopping.

### Root causes (ranked)

1. **Termination rule mismatched to our cost model** — Stop when `max(top_f, top_b) >= mu` is valid for standard shortest-path A* with admissible consistent heuristics. Our optimized search uses `length × M × R + A + H` with **node penalties** (signals, junctions) while the heuristic is only `haversine × cost_per_m_lb × (1+ε)`. Heap keys and meeting cost `mu` sit on different scales, so both frontiers keep expanding long after a good meeting is known.

2. **Overlapping frontiers on dense London mesh** — Start/end in the same component; forward and backward teardrops overlap heavily in central corridors, so many nodes are expanded from both sides.

3. **Directed graph backward expansion** — Backward walk uses `G.pred` on a 4M-edge directed mesh (one-ways, service links); frontier shape differs from a single goal-directed teardrop.

4. **Heavy per-edge Python cost fn** — Each relaxation runs full `make_weight_optimized` (park hours, disruptions, rewards). Bi doubles relaxations → doubles CPU with no rescue.

### What it was not

- Not a path correctness bug (routes matched).
- Not threads/GIL (single-threaded alternating was correct for Python).
- Not “bi is theoretically always slower” — it failed with **this** termination + **this** heuristic + **this** weight function on **this** graph.

### Options for a future retry

| Option | Notes |
|--------|-------|
| **A. Keep uni default** | Current production choice; benchmark-backed. |
| **B. Fix bi termination** | Goldberg–Harrelson-style bounds, or stopping rules proven for ε-scaled / inconsistent heuristics; re-benchmark with `benchmark_routing.py`. |
| **C. Hybrid by hop length** | Uni for short hops (haversine &lt; ~8 km), bi only when fixed and only on long cross-city routes. |
| **D. Precomputed edge weights** | Per-request weight cache so A* does O(1) lookup — helps uni and bi; likely highest ROI on 2M-node mesh. |
| **E. Structural** | Contraction hierarchies, C++/Rust core, or corridor subgraph — needed for ms-level cross-London if Python+A* remains the architecture. |

### Re-enable bi for testing

```text
GET /route?...&alg=bi
# or in 4_backend_engine/.env:
ROUTE_ALGORITHM=bi
```
