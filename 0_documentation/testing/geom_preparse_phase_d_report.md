# Geometry preparse Phase D report

Generated: 2026-07-11T18:18:10.929070+00:00
Repeats (median): 1
Full-graph preparse: **221.3 s** (4,061,447 edges, 18,356 edges/s)

## Summary (path reconstruct wall)

- Mean cold (WKT) fastest+opt sum: **0.139 s**
- Mean warm (`_coords`) fastest+opt sum: **0.004 s**
- Mean speedup (cold/warm): **36.60×**

## Per-route

| Preset | Route | Cold sum s | Warm sum s | Speedup | Cold fast | Warm fast | Cold opt | Warm opt | Path edges |
|--------|-------|------------|------------|---------|-----------|-----------|----------|----------|------------|
| fast | route 1: Imperial to Kings Cross | 0.112 | 0.002 | 60.41× | 0.071 | 0.001 | 0.041 | 0.001 | 457+435 |
| fast | route 2: Imperial to Greenwich | 0.231 | 0.003 | 69.69× | 0.121 | 0.002 | 0.111 | 0.002 | 974+1177 |
| fast | route 3: Imperial to New Spitalfields Market | 0.367 | 0.006 | 58.23× | 0.196 | 0.003 | 0.171 | 0.003 | 1155+1118 |
| fast | route 4: Twickenham Stadium to St. Pauls | 0.182 | 0.005 | 37.63× | 0.090 | 0.003 | 0.092 | 0.002 | 965+1065 |
| fast | route 5: Wembley Stadium to Kings College Hospital | 0.232 | 0.005 | 44.73× | 0.130 | 0.003 | 0.102 | 0.002 | 1264+1283 |
| fast | route 6: Battersea Park to Temple | 0.068 | 0.002 | 42.21× | 0.028 | 0.001 | 0.041 | 0.001 | 330+516 |
| fast | route 7: Putney bridge to Notting Hill | 0.056 | 0.001 | 39.53× | 0.033 | 0.001 | 0.023 | 0.001 | 421+453 |
| fast | route 8: Tottenham Stadium to Hampstead | 0.121 | 0.003 | 40.52× | 0.049 | 0.001 | 0.072 | 0.002 | 581+956 |
| fast | route 9: Earls court to Piccadilly | 0.024 | 0.001 | 26.18× | 0.013 | 0.001 | 0.011 | 0.000 | 270+270 |
| fast | route 10: Bromley to Ealing | 0.334 | 0.008 | 43.99× | 0.167 | 0.003 | 0.167 | 0.004 | 1672+1716 |
| fast | route 11: Hill route, Elmers End to Streatham | 0.108 | 0.002 | 46.48× | 0.057 | 0.001 | 0.051 | 0.001 | 479+449 |
| safe | route 1: Imperial to Kings Cross | 0.065 | 0.003 | 26.01× | 0.026 | 0.001 | 0.040 | 0.001 | 457+470 |
| safe | route 2: Imperial to Greenwich | 0.145 | 0.005 | 28.82× | 0.051 | 0.002 | 0.094 | 0.003 | 974+1120 |
| safe | route 3: Imperial to New Spitalfields Market | 0.160 | 0.006 | 28.00× | 0.065 | 0.003 | 0.095 | 0.003 | 1155+1143 |
| safe | route 4: Twickenham Stadium to St. Pauls | 0.155 | 0.005 | 33.04× | 0.056 | 0.002 | 0.100 | 0.003 | 965+1358 |
| safe | route 5: Wembley Stadium to Kings College Hospital | 0.167 | 0.006 | 27.39× | 0.069 | 0.003 | 0.098 | 0.003 | 1264+1294 |
| safe | route 6: Battersea Park to Temple | 0.036 | 0.002 | 19.67× | 0.021 | 0.001 | 0.015 | 0.001 | 330+377 |
| safe | route 7: Putney bridge to Notting Hill | 0.050 | 0.001 | 35.89× | 0.019 | 0.001 | 0.030 | 0.001 | 421+438 |
| safe | route 8: Tottenham Stadium to Hampstead | 0.089 | 0.004 | 19.78× | 0.025 | 0.002 | 0.064 | 0.003 | 581+1004 |
| safe | route 9: Earls court to Piccadilly | 0.033 | 0.001 | 25.64× | 0.011 | 0.001 | 0.022 | 0.001 | 270+296 |
| safe | route 10: Bromley to Ealing | 0.270 | 0.010 | 27.01× | 0.099 | 0.005 | 0.171 | 0.005 | 1672+2068 |
| safe | route 11: Hill route, Elmers End to Streatham | 0.045 | 0.002 | 24.31× | 0.025 | 0.001 | 0.020 | 0.001 | 479+453 |

JSON: `0_documentation/testing/geom_preparse_phase_d_report.json`

---

## Analysis (11 Jul 2026) — Phase D

**Decision:** **Ship / keep default `GEOM_PREPARSE=background`.** Path reconstruct goes from a meaningful TTF slice to noise once `_coords` are warm.

### Headline

| Layer | Result |
|-------|--------|
| Full-graph preparse (once) | **221 s** / 4.06M edges (~18k edges/s) — background at bootstrap |
| Mean cold path geom (fast+opt) | **0.139 s** |
| Mean warm path geom (fast+opt) | **0.004 s** |
| Mean reconstruct speedup | **~37×** |
| Bromley safe cold → warm | **0.270 → 0.010 s** |

### Influence on **total** `/route` time

Phase D does **not** speed A*. After Numba, A* is already ~0.2–2 s on long hops; geometry was the next visible slice.

| Slice (illustrative, `--no-live`, Safe) | Before Phase D (lazy WKT) | After warm preparse |
|-----------------------------------------|---------------------------|---------------------|
| A* (Numba, Bromley-class) | ~1–2 s | ~1–2 s (unchanged) |
| Path geometry (fast+opt) | ~0.15–0.35 s | **~0.01 s** |
| Snap + overlays/stats | ~0.05–0.3 s | same |
| **User-felt total** | often **~1–4 s** long; geom noticeable on short | **geom negligible**; total dominated by A*+snap |

On short hops (Imperial→KX), Numba A* is ~0.1 s; cold geom (~0.07–0.11 s) was a large *fraction* of TTF — Phase D removes that. On Bromley, geom was ~0.3 s of ~1–2 s (~15–25%); warm drops it to ~1%.

**Ops note:** First requests after boot may still hit cold geom until the background thread finishes (~3–4 min). Prefer waiting for `meta.geom_preparse.state=ready`, or use `GEOM_PREPARSE=sync` for benches.

**Open review:** Whether to **keep** background full-graph preparse as the default. It costs ~**4 minutes** of background CPU/RAM after every process start for ~0.13 s mean path-geom savings once warm. Alternatives: `GEOM_PREPARSE=0` (lazy), warm only recent/path edges, or sync only in prod workers that stay up long-lived. Track in next-session open items.
