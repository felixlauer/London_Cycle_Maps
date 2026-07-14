# CSR A* Phase A report

Generated: 2026-07-11T11:29:51.951175+00:00
Repeats (median): 1
CSR build: 34.43s (1,924,143 nodes, 4,061,447 arcs)
Edge tables: 4,061,447 edges
ε optimized: 0.75 | ε fastest: 0.0
Parity OK: 44/44

## Summary speedups (nx_array / csr, median wall)

- Fastest legs mean speedup: 1.898×
- Optimized (safe) legs mean speedup: 1.433×
- All legs mean speedup: 1.665×

## Per-route

| Preset | Route | Leg | NX s | CSR s | Speedup | Exp NX | Exp CSR | Path | Cost | OK |
|--------|-------|-----|------|-------|---------|--------|---------|------|------|----|
| fast | route 1: Imperial to Kings Cross | fastest | 0.631 | 0.224 | 2.813× | 28160 | 28160 | Y | Y | Y |
| fast | route 1: Imperial to Kings Cross | optimized | 1.571 | 0.900 | 1.744× | 59802 | 59802 | Y | Y | Y |
| fast | route 2: Imperial to Greenwich | fastest | 1.740 | 0.887 | 1.960× | 88187 | 88187 | Y | Y | Y |
| fast | route 2: Imperial to Greenwich | optimized | 3.128 | 2.248 | 1.391× | 138623 | 138623 | Y | Y | Y |
| fast | route 3: Imperial to New Spitalfields Market | fastest | 1.573 | 0.827 | 1.902× | 96319 | 96319 | Y | Y | Y |
| fast | route 3: Imperial to New Spitalfields Market | optimized | 6.134 | 4.283 | 1.432× | 250522 | 250522 | Y | Y | Y |
| fast | route 4: Twickenham Stadium to St. Pauls | fastest | 1.012 | 0.458 | 2.210× | 54897 | 54897 | Y | Y | Y |
| fast | route 4: Twickenham Stadium to St. Pauls | optimized | 5.521 | 3.749 | 1.472× | 223381 | 223381 | Y | Y | Y |
| fast | route 5: Wembley Stadium to Kings College Hospital | fastest | 1.236 | 0.650 | 1.900× | 79576 | 79576 | Y | Y | Y |
| fast | route 5: Wembley Stadium to Kings College Hospital | optimized | 7.378 | 4.973 | 1.484× | 296174 | 296174 | Y | Y | Y |
| fast | route 6: Battersea Park to Temple | fastest | 0.091 | 0.053 | 1.708× | 7439 | 7439 | Y | Y | Y |
| fast | route 6: Battersea Park to Temple | optimized | 1.009 | 0.710 | 1.420× | 49596 | 49596 | Y | Y | Y |
| fast | route 7: Putney bridge to Notting Hill | fastest | 0.208 | 0.126 | 1.656× | 17782 | 17782 | Y | Y | Y |
| fast | route 7: Putney bridge to Notting Hill | optimized | 0.548 | 0.409 | 1.341× | 28615 | 28615 | Y | Y | Y |
| fast | route 8: Tottenham Stadium to Hampstead | fastest | 0.993 | 0.319 | 3.111× | 40338 | 40338 | Y | Y | Y |
| fast | route 8: Tottenham Stadium to Hampstead | optimized | 3.727 | 2.258 | 1.650× | 142124 | 142124 | Y | Y | Y |
| fast | route 9: Earls court to Piccadilly | fastest | 0.017 | 0.010 | 1.736× | 1481 | 1481 | Y | Y | Y |
| fast | route 9: Earls court to Piccadilly | optimized | 0.493 | 0.393 | 1.254× | 24848 | 24848 | Y | Y | Y |
| fast | route 10: Bromley to Ealing | fastest | 6.730 | 2.531 | 2.659× | 290225 | 290225 | Y | Y | Y |
| fast | route 10: Bromley to Ealing | optimized | 17.805 | 12.329 | 1.444× | 621901 | 621901 | Y | Y | Y |
| fast | route 11: Hill route, Elmers End to Streatham | fastest | 0.232 | 0.111 | 2.084× | 16307 | 16307 | Y | Y | Y |
| fast | route 11: Hill route, Elmers End to Streatham | optimized | 0.514 | 0.374 | 1.375× | 23869 | 23869 | Y | Y | Y |
| safe | route 1: Imperial to Kings Cross | fastest | 0.362 | 0.226 | 1.603× | 28160 | 28160 | Y | Y | Y |
| safe | route 1: Imperial to Kings Cross | optimized | 1.101 | 0.747 | 1.474× | 52192 | 52192 | Y | Y | Y |
| safe | route 2: Imperial to Greenwich | fastest | 1.119 | 0.702 | 1.594× | 88187 | 88187 | Y | Y | Y |
| safe | route 2: Imperial to Greenwich | optimized | 2.187 | 1.546 | 1.414× | 103392 | 103392 | Y | Y | Y |
| safe | route 3: Imperial to New Spitalfields Market | fastest | 1.278 | 0.730 | 1.751× | 96319 | 96319 | Y | Y | Y |
| safe | route 3: Imperial to New Spitalfields Market | optimized | 5.076 | 3.524 | 1.440× | 226185 | 226185 | Y | Y | Y |
| safe | route 4: Twickenham Stadium to St. Pauls | fastest | 0.695 | 0.476 | 1.459× | 54897 | 54897 | Y | Y | Y |
| safe | route 4: Twickenham Stadium to St. Pauls | optimized | 2.739 | 1.904 | 1.438× | 128110 | 128110 | Y | Y | Y |
| safe | route 5: Wembley Stadium to Kings College Hospital | fastest | 1.086 | 0.594 | 1.827× | 79576 | 79576 | Y | Y | Y |
| safe | route 5: Wembley Stadium to Kings College Hospital | optimized | 4.047 | 2.520 | 1.606× | 159197 | 159197 | Y | Y | Y |
| safe | route 6: Battersea Park to Temple | fastest | 0.084 | 0.049 | 1.730× | 7439 | 7439 | Y | Y | Y |
| safe | route 6: Battersea Park to Temple | optimized | 0.116 | 0.082 | 1.422× | 6078 | 6078 | Y | Y | Y |
| safe | route 7: Putney bridge to Notting Hill | fastest | 0.226 | 0.125 | 1.815× | 17782 | 17782 | Y | Y | Y |
| safe | route 7: Putney bridge to Notting Hill | optimized | 0.548 | 0.402 | 1.361× | 27670 | 27670 | Y | Y | Y |
| safe | route 8: Tottenham Stadium to Hampstead | fastest | 0.514 | 0.309 | 1.661× | 40338 | 40338 | Y | Y | Y |
| safe | route 8: Tottenham Stadium to Hampstead | optimized | 1.513 | 1.104 | 1.370× | 73084 | 73084 | Y | Y | Y |
| safe | route 9: Earls court to Piccadilly | fastest | 0.015 | 0.010 | 1.466× | 1481 | 1481 | Y | Y | Y |
| safe | route 9: Earls court to Piccadilly | optimized | 0.245 | 0.182 | 1.344× | 13348 | 13348 | Y | Y | Y |
| safe | route 10: Bromley to Ealing | fastest | 4.045 | 2.902 | 1.394× | 290225 | 290225 | Y | Y | Y |
| safe | route 10: Bromley to Ealing | optimized | 12.705 | 9.003 | 1.411× | 541202 | 541202 | Y | Y | Y |
| safe | route 11: Hill route, Elmers End to Streatham | fastest | 0.190 | 0.111 | 1.720× | 16307 | 16307 | Y | Y | Y |
| safe | route 11: Hill route, Elmers End to Streatham | optimized | 1.107 | 0.896 | 1.234× | 54447 | 54447 | Y | Y | Y |

JSON: `0_documentation/testing/csr_astar_phase_a_report.json`

---

## Analysis (11 Jul 2026) — CSR Phase A

**Decision:** Phase A is a **clear win** — exact path + expansion + cost parity on **44/44**, mean A* wall **~1.67×** vs NetworkX array uni (fastest legs **~1.90×**, optimized **~1.43×**). Ahead of the FR’s ~1.2–1.5× band. **Ship / keep default ON** (`CSR_ASTAR=1`). Next: Phase B (hotter heuristic) then Numba (Phase C).

### Headline

| Layer | Result |
|-------|--------|
| Parity (path / exp / cost) | **44/44** OK |
| Mean speedup all legs | **1.665×** |
| Mean speedup fastest | **1.898×** (up to **3.11×** route 8 fast) |
| Mean speedup optimized | **1.433×** |
| Bromley fast (route 10) | **6.73 → 2.53 s** (**2.66×**) |
| Bromley safe opt (route 10) | **12.71 → 9.00 s** (**1.41×**) |
| Imperial→KX safe (fast+opt sum) | **~1.46 → ~0.97 s** |
| CSR build (once) | **34.4 s** @ bootstrap (1.92M nodes / 4.06M arcs) |

### Notes

- Baseline is **array-backed NX A\*** (not python weights) — speedup is pure search-structure win.
- Expansions matched exactly → same search decisions; wall drop is neighbor / attr / heuristic overhead.
- Lat/lon arrays already live inside CSR A* (FR Phase B precursor). Phase B remaining work: radian precompute + NX/bi heuristics on the same arrays.
- Bench: `SKIP_DISRUPTION_FETCH=1`, `ε_opt=0.75`, `ε_fast=0.0`, live=False.

**Bottom line:** Keep CSR Phase A default on. Optional real-app smoke only; this bench is the acceptance gate.
