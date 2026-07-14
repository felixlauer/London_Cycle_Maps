# CSR A* Phase C (Numba) report

Generated: 2026-07-11T12:15:28.004362+00:00
Repeats (median): 1
Numba available: True
Warmup: 0.00s
CSR build: 41.49s (1,924,143 nodes, 4,061,447 arcs)
ε optimized: 0.75 | ε fastest: 0.0
Parity OK: 44/44

## Summary speedups (csr_py / numba)

- Fastest legs mean: **12.542×**
- Optimized legs mean: **9.760×**
- All legs mean: **11.151×**

## Per-route

| Preset | Route | Leg | CSR-py s | Numba s | Speedup | Exp py | Exp nb | Path | Cost | OK |
|--------|-------|-----|----------|---------|---------|--------|--------|------|------|----|
| fast | route 1: Imperial to Kings Cross | fastest | 0.458 | 0.030 | 15.037× | 28160 | 28160 | Y | Y | Y |
| fast | route 1: Imperial to Kings Cross | optimized | 2.238 | 0.104 | 21.553× | 59802 | 59802 | Y | Y | Y |
| fast | route 2: Imperial to Greenwich | fastest | 1.069 | 0.059 | 18.121× | 88187 | 88187 | Y | Y | Y |
| fast | route 2: Imperial to Greenwich | optimized | 2.997 | 0.260 | 11.545× | 138623 | 138623 | Y | Y | Y |
| fast | route 3: Imperial to New Spitalfields Market | fastest | 0.876 | 0.071 | 12.259× | 96319 | 96319 | Y | Y | Y |
| fast | route 3: Imperial to New Spitalfields Market | optimized | 4.325 | 0.456 | 9.491× | 250522 | 250522 | Y | Y | Y |
| fast | route 4: Twickenham Stadium to St. Pauls | fastest | 0.449 | 0.037 | 12.160× | 54897 | 54897 | Y | Y | Y |
| fast | route 4: Twickenham Stadium to St. Pauls | optimized | 3.767 | 0.413 | 9.121× | 223381 | 223381 | Y | Y | Y |
| fast | route 5: Wembley Stadium to Kings College Hospital | fastest | 0.691 | 0.055 | 12.531× | 79576 | 79576 | Y | Y | Y |
| fast | route 5: Wembley Stadium to Kings College Hospital | optimized | 4.955 | 0.590 | 8.397× | 296174 | 296174 | Y | Y | Y |
| fast | route 6: Battersea Park to Temple | fastest | 0.058 | 0.004 | 13.447× | 7439 | 7439 | Y | Y | Y |
| fast | route 6: Battersea Park to Temple | optimized | 0.888 | 0.081 | 10.969× | 49596 | 49596 | Y | Y | Y |
| fast | route 7: Putney bridge to Notting Hill | fastest | 0.128 | 0.009 | 14.155× | 17782 | 17782 | Y | Y | Y |
| fast | route 7: Putney bridge to Notting Hill | optimized | 0.418 | 0.049 | 8.520× | 28615 | 28615 | Y | Y | Y |
| fast | route 8: Tottenham Stadium to Hampstead | fastest | 0.327 | 0.022 | 14.774× | 40338 | 40338 | Y | Y | Y |
| fast | route 8: Tottenham Stadium to Hampstead | optimized | 2.339 | 0.253 | 9.240× | 142124 | 142124 | Y | Y | Y |
| fast | route 9: Earls court to Piccadilly | fastest | 0.010 | 0.001 | 7.111× | 1481 | 1481 | Y | Y | Y |
| fast | route 9: Earls court to Piccadilly | optimized | 0.367 | 0.043 | 8.539× | 24848 | 24848 | Y | Y | Y |
| fast | route 10: Bromley to Ealing | fastest | 2.763 | 0.244 | 11.331× | 290225 | 290225 | Y | Y | Y |
| fast | route 10: Bromley to Ealing | optimized | 11.151 | 1.219 | 9.145× | 621901 | 621901 | Y | Y | Y |
| fast | route 11: Hill route, Elmers End to Streatham | fastest | 0.107 | 0.009 | 11.852× | 16307 | 16307 | Y | Y | Y |
| fast | route 11: Hill route, Elmers End to Streatham | optimized | 0.337 | 0.037 | 9.075× | 23869 | 23869 | Y | Y | Y |
| safe | route 1: Imperial to Kings Cross | fastest | 0.246 | 0.018 | 13.283× | 28160 | 28160 | Y | Y | Y |
| safe | route 1: Imperial to Kings Cross | optimized | 0.857 | 0.095 | 9.022× | 52192 | 52192 | Y | Y | Y |
| safe | route 2: Imperial to Greenwich | fastest | 0.783 | 0.057 | 13.709× | 88187 | 88187 | Y | Y | Y |
| safe | route 2: Imperial to Greenwich | optimized | 1.751 | 0.210 | 8.337× | 103392 | 103392 | Y | Y | Y |
| safe | route 3: Imperial to New Spitalfields Market | fastest | 0.831 | 0.066 | 12.626× | 96319 | 96319 | Y | Y | Y |
| safe | route 3: Imperial to New Spitalfields Market | optimized | 4.051 | 0.444 | 9.132× | 226185 | 226185 | Y | Y | Y |
| safe | route 4: Twickenham Stadium to St. Pauls | fastest | 0.446 | 0.033 | 13.378× | 54897 | 54897 | Y | Y | Y |
| safe | route 4: Twickenham Stadium to St. Pauls | optimized | 2.133 | 0.228 | 9.364× | 128110 | 128110 | Y | Y | Y |
| safe | route 5: Wembley Stadium to Kings College Hospital | fastest | 0.671 | 0.058 | 11.622× | 79576 | 79576 | Y | Y | Y |
| safe | route 5: Wembley Stadium to Kings College Hospital | optimized | 2.606 | 0.278 | 9.381× | 159197 | 159197 | Y | Y | Y |
| safe | route 6: Battersea Park to Temple | fastest | 0.047 | 0.004 | 10.302× | 7439 | 7439 | Y | Y | Y |
| safe | route 6: Battersea Park to Temple | optimized | 0.076 | 0.009 | 8.439× | 6078 | 6078 | Y | Y | Y |
| safe | route 7: Putney bridge to Notting Hill | fastest | 0.118 | 0.009 | 12.619× | 17782 | 17782 | Y | Y | Y |
| safe | route 7: Putney bridge to Notting Hill | optimized | 0.417 | 0.045 | 9.169× | 27670 | 27670 | Y | Y | Y |
| safe | route 8: Tottenham Stadium to Hampstead | fastest | 0.338 | 0.027 | 12.705× | 40338 | 40338 | Y | Y | Y |
| safe | route 8: Tottenham Stadium to Hampstead | optimized | 1.163 | 0.132 | 8.819× | 73084 | 73084 | Y | Y | Y |
| safe | route 9: Earls court to Piccadilly | fastest | 0.009 | 0.001 | 9.124× | 1481 | 1481 | Y | Y | Y |
| safe | route 9: Earls court to Piccadilly | optimized | 0.184 | 0.020 | 9.065× | 13348 | 13348 | Y | Y | Y |
| safe | route 10: Bromley to Ealing | fastest | 2.546 | 0.204 | 12.445× | 290225 | 290225 | Y | Y | Y |
| safe | route 10: Bromley to Ealing | optimized | 9.404 | 1.087 | 8.652× | 541202 | 541202 | Y | Y | Y |
| safe | route 11: Hill route, Elmers End to Streatham | fastest | 0.104 | 0.009 | 11.337× | 16307 | 16307 | Y | Y | Y |
| safe | route 11: Hill route, Elmers End to Streatham | optimized | 0.785 | 0.081 | 9.738× | 54447 | 54447 | Y | Y | Y |

JSON: `0_documentation/testing/csr_astar_phase_c_report.json`

---

## Analysis (11 Jul 2026) — CSR Phase C (Numba)

**Decision:** **Ship / keep default ON.** Clear multi-× win with full parity. This is the step that finally delivers the ~10× search speedup (vs CSR-py); chained vs original Python weights it is larger still. See master overview: [`routing_performance_master.md`](routing_performance_master.md).

### Headline

| Layer | Result |
|-------|--------|
| Parity (path / exp / cost) | **44/44** OK |
| Mean CSR-py → Numba (all) | **11.15×** |
| Mean fastest | **12.54×** |
| Mean optimized | **9.76×** |
| Bromley fast dual (approx) | ~13.9 → **~1.46 s** |
| Bromley safe dual (approx) | ~12.0 → **~1.29 s** |
| Warmup (cold compile, once) | **~18.8 s** at first bootstrap |

### Notes

- Baseline is **Phase B CSR-py** (already ~1.7× vs NX array and ~2× vs v0 via arrays) — so cumulative vs original Python is much larger than 11× alone.
- Expansions matched exactly → same search decisions; wall drop is interpreter / heap / attr overhead leaving Python.
- Optimized speedup slightly lower than fastest (heavier cost arithmetic still in the compiled loop) but still ~**9–10×**.
- Bench: `SKIP_DISRUPTION_FETCH=1`, `ε_opt=0.75`, live=False, numba 0.66.

**Bottom line:** Numba Phase C is production-ready. Optional next work is outside A* (geometry cache, live soak), not another search rewrite.
