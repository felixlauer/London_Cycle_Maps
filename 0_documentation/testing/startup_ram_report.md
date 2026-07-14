# Startup + RAM report

Generated: `2026-07-13T17:19:46.472883+00:00`  
Platform: `win32` · Python `3.11.14`  
GEOM_PREPARSE skipped (lazy `EdgeGeomStore`) · live_fetch=`False`  
Kill-switches: ARRAY_COSTS=`True` · CSR_ASTAR=`True` · NUMBA_ASTAR=`True`  
**Routing cache:** hit, format v2 (lazy geom, no per-edge `_coords` stamp)

> Compare: cold ready **506.8 s** / geom **815 s**; v1 cache-hit ready **502 s**; **v2 ready 151.5 s**.

## Graph

- Nodes: **1924143** · edges: **4061447**
- CSR: 1924143 nodes / 4061447 arcs
- Cost table edges: 4061447

## Startup wall time

| Milestone | Time |
|-----------|------|
| Import → engine ready (serve-capable) | **151.5s (2.5 min)** |
| Process wall → ready | 151.5s (2.5 min) |
| Process wall → geom warm ready | 151.5s (2.5 min) |
| Geom wait after ready | 0.00s |

### Phase breakdown (from app.py log lines)

| Phase | Seconds | Share of ready |
|-------|---------|----------------|
| Graph load (pickle) | 36.30 | 24.0% |
| Node KD-tree | 5.50 | 3.6% |
| Live disruption STRtree (+ optional fetch kickoff) | — | — |
| Node XY stamps | 0.50 | 0.3% |
| Junction danger flags | — | — |
| Heuristic penalty floors | — | — |
| Junction cluster dedup | — | — |
| Edge cost arrays (VF + tables + _eid) | — | — |
| Shared overlays bake | 0.07 | 0.0% |
| CSR build | — | — |
| Numba A* warmup | 2.10 | 1.4% |
| Geometry preparse (sync only) | — | — |
| **Sum of exclusive phases** | **44.473** | — |
| Unaccounted (import overhead / other) | 107.006 | — |

Notes:

- `bootstrap_early` in logs is the early block only (graph → XY stamps), not full engine ready.
- With `GEOM_PREPARSE=background`, geom warm runs **after** ready and is reported under geom wait / geom_preparse state (not in the ready sum).
- With `GEOM_PREPARSE=sync`, geom time appears in the phase table and is included in ready.

## RAM (process working set / RSS)

| Point | RSS |
|-------|-----|
| Before import | 19.30 MiB |
| Engine ready | **5.91 GiB** |
| Geom warm ready | 5.91 GiB |
| End of idle hold (30.0s) | **3.52 GiB** |
| After route smoke | 3.59 GiB |

| Peak window | RSS |
|-------------|-----|
| Startup → ready | 8.02 GiB |
| Ready → geom ready | n/a |
| Idle hold (hosting) | 5.91 GiB |
| Route smoke | n/a |
| Overall | **8.02 GiB** |

## Geometry preparse

- State: `ready`
- Parsed: 0 / 4061447 (already cached 4061447)
- Elapsed: 0.00s

## Route smoke

- Route: route 1: Imperial to Kings Cross
- OK: True · engine: `numba`
- A* wall: 0.80s · nodes=458 · expansions=28156

## Artifacts

- JSON (full RSS series, 492 samples): [`startup_ram_report.json`](startup_ram_report.json)
- Re-run: `python 4_backend_engine/benchmark_startup_ram.py`

