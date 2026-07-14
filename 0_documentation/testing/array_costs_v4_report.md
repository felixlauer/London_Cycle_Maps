# Array costs v4 — fastest + parallel + shared bake

Generated: 2026-07-10T14:52:38.687835+00:00
Graph: 1,924,143 nodes, 4,061,447 edges
Table build: **104.18 s** | Shared bake mean: **44.5 ms** (live=False)
Heuristic epsilon: 0.5

Full /route-shaped A* pair (fastest + optimized). Snap excluded from wall.

| Mode | Meaning |
|------|---------|
| **prod** | python fastest + python optimized, sequential |
| **v3** | python fastest + array v3 optimized, sequential |
| **v4 seq** | array fastest + array v3 optimized, sequential |
| **v4 par** | same weights, ThreadPoolExecutor (2 workers) |
| **v4 theo** | `max(fast, opt)` — ideal if both run truly concurrent |

## Shared overlay bake (item 3)

Rebuild `SharedOverlays` (parks + live coeffs + impassable): **44.5 ms** mean (54.3, 38.6, 40.6 ms).
Cheap enough to run after every live disruption refresh (~5–10 min).

## Preset: fast — wall clock

| Route | Prod (s) | v3 (s) | v4 seq (s) | v4 par (s) | v4 theo (s) | v4seq× | v4par× | theo× | Opt | Fast | Cost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| route 1: Imperial to Kings Cross | 6.02 | 1.82 | 1.52 | 1.56 | 1.20 | 3.97x | 3.87x | 5.03x | exact | exact | ok |
| route 2: Imperial to Greenwich | 10.78 | 5.14 | 4.47 | 4.66 | 3.47 | 2.41x | 2.31x | 3.11x | exact | exact | ok |
| route 3: Imperial to New Spitalfields Market | 18.10 | 8.03 | 6.90 | 7.02 | 5.76 | 2.62x | 2.58x | 3.14x | exact | exact | ok |
| route 4: Twickenham Stadium to St. Pauls | 16.01 | 6.49 | 5.96 | 6.02 | 5.34 | 2.69x | 2.66x | 3.00x | exact | exact | ok |
| route 5: Wembley Stadium to Kings College Hospital | 17.90 | 8.37 | 7.72 | 7.80 | 6.81 | 2.32x | 2.30x | 2.63x | exact | exact | ok |
| route 6: Battersea Park to Temple | 2.29 | 1.12 | 1.10 | 1.13 | 1.02 | 2.08x | 2.02x | 2.24x | exact | exact | ok |
| route 7: Putney bridge to Notting Hill | 1.69 | 0.99 | 0.83 | 0.83 | 0.64 | 2.04x | 2.03x | 2.64x | exact | exact | ok |
| route 8: Tottenham Stadium to Hampstead | 11.07 | 3.88 | 3.46 | 3.46 | 3.00 | 3.20x | 3.20x | 3.69x | exact | exact | ok |
| route 9: Earls court to Piccadilly | 1.17 | 0.55 | 0.53 | 0.55 | 0.51 | 2.22x | 2.15x | 2.29x | exact | exact | ok |
| route 10: Bromley to Ealing | 47.59 | 21.55 | 18.93 | 19.04 | 15.34 | 2.51x | 2.50x | 3.10x | exact | exact | ok |
| route 11: Hill route, Elmers End to Streatham | 1.44 | 0.78 | 0.70 | 0.71 | 0.54 | 2.07x | 2.03x | 2.69x | exact | exact | ok |

## Preset: safe — wall clock

| Route | Prod (s) | v3 (s) | v4 seq (s) | v4 par (s) | v4 theo (s) | v4seq× | v4par× | theo× | Opt | Fast | Cost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| route 1: Imperial to Kings Cross | 2.92 | 1.66 | 1.44 | 1.54 | 1.14 | 2.03x | 1.90x | 2.56x | exact | exact | ok |
| route 2: Imperial to Greenwich | 7.10 | 4.29 | 3.74 | 3.83 | 2.72 | 1.90x | 1.85x | 2.61x | exact | exact | ok |
| route 3: Imperial to New Spitalfields Market | 13.23 | 7.04 | 6.51 | 6.58 | 5.39 | 2.03x | 2.01x | 2.45x | exact | exact | ok |
| route 4: Twickenham Stadium to St. Pauls | 8.37 | 4.43 | 4.07 | 4.17 | 3.45 | 2.06x | 2.01x | 2.43x | exact | exact | ok |
| route 5: Wembley Stadium to Kings College Hospital | 9.44 | 5.30 | 4.80 | 4.80 | 3.87 | 1.97x | 1.97x | 2.44x | exact | exact | ok |
| route 6: Battersea Park to Temple | 0.51 | 0.29 | 0.25 | 0.25 | 0.18 | 2.01x | 2.00x | 2.84x | exact | exact | ok |
| route 7: Putney bridge to Notting Hill | 1.64 | 0.92 | 0.81 | 0.82 | 0.63 | 2.02x | 2.00x | 2.58x | exact | exact | ok |
| route 8: Tottenham Stadium to Hampstead | 4.22 | 2.27 | 2.04 | 2.10 | 1.61 | 2.07x | 2.01x | 2.62x | exact | exact | ok |
| route 9: Earls court to Piccadilly | 0.63 | 0.29 | 0.28 | 0.28 | 0.27 | 2.22x | 2.23x | 2.35x | exact | exact | ok |
| route 10: Bromley to Ealing | 32.02 | 19.29 | 17.02 | 17.22 | 13.40 | 1.88x | 1.86x | 2.39x | exact | exact | ok |
| route 11: Hill route, Elmers End to Streatham | 2.71 | 1.38 | 1.29 | 1.31 | 1.12 | 2.11x | 2.07x | 2.43x | exact | exact | ok |

## Preset: fast — leg breakdown

| Route | Prod fast | Prod opt | v4 fast | v4 opt | fast array× | par/seq |
|---|---:|---:|---:|---:|---:|---:|
| route 1: Imperial to Kings Cross | 2.72 | 3.29 | 0.32 | 1.20 | 8.58x | 0.98x |
| route 2: Imperial to Greenwich | 2.22 | 8.53 | 1.00 | 3.47 | 2.23x | 0.96x |
| route 3: Imperial to New Spitalfields Market | 2.92 | 15.16 | 1.13 | 5.76 | 2.59x | 0.98x |
| route 4: Twickenham Stadium to St. Pauls | 1.62 | 14.37 | 0.61 | 5.34 | 2.67x | 0.99x |
| route 5: Wembley Stadium to Kings College Hospital | 1.98 | 15.90 | 0.90 | 6.81 | 2.20x | 0.99x |
| route 6: Battersea Park to Temple | 0.11 | 2.17 | 0.07 | 1.02 | 1.56x | 0.97x |
| route 7: Putney bridge to Notting Hill | 0.28 | 1.40 | 0.19 | 0.64 | 1.49x | 1.00x |
| route 8: Tottenham Stadium to Hampstead | 1.87 | 9.18 | 0.45 | 3.00 | 4.16x | 1.00x |
| route 9: Earls court to Piccadilly | 0.02 | 1.15 | 0.01 | 0.51 | 1.55x | 0.97x |
| route 10: Bromley to Ealing | 7.89 | 39.66 | 3.57 | 15.34 | 2.21x | 0.99x |
| route 11: Hill route, Elmers End to Streatham | 0.24 | 1.19 | 0.16 | 0.54 | 1.54x | 0.98x |

## Preset: safe — leg breakdown

| Route | Prod fast | Prod opt | v4 fast | v4 opt | fast array× | par/seq |
|---|---:|---:|---:|---:|---:|---:|
| route 1: Imperial to Kings Cross | 0.49 | 2.42 | 0.30 | 1.14 | 1.63x | 0.94x |
| route 2: Imperial to Greenwich | 1.52 | 5.55 | 1.02 | 2.72 | 1.50x | 0.98x |
| route 3: Imperial to New Spitalfields Market | 1.73 | 11.48 | 1.10 | 5.39 | 1.57x | 0.99x |
| route 4: Twickenham Stadium to St. Pauls | 0.95 | 7.40 | 0.61 | 3.45 | 1.57x | 0.98x |
| route 5: Wembley Stadium to Kings College Hospital | 1.41 | 8.01 | 0.91 | 3.87 | 1.55x | 1.00x |
| route 6: Battersea Park to Temple | 0.12 | 0.38 | 0.07 | 0.18 | 1.65x | 0.99x |
| route 7: Putney bridge to Notting Hill | 0.27 | 1.36 | 0.17 | 0.63 | 1.58x | 0.99x |
| route 8: Tottenham Stadium to Hampstead | 0.73 | 3.47 | 0.43 | 1.61 | 1.71x | 0.97x |
| route 9: Earls court to Piccadilly | 0.02 | 0.60 | 0.01 | 0.27 | 1.54x | 1.01x |
| route 10: Bromley to Ealing | 5.15 | 26.83 | 3.60 | 13.40 | 1.43x | 0.99x |
| route 11: Hill route, Elmers End to Streatham | 0.24 | 2.46 | 0.16 | 1.12 | 1.49x | 0.98x |

## How to read

- **v4seq× / v4par× / theo×** = speedup vs prod wall.
- **par/seq** ≈ 1.0 under CPython GIL for pure-Python A*; theo shows headroom if search is GIL-free later.
- **Opt / Fast / Cost** = path match and v3 cost on python opt path.

Re-run: `python 4_backend_engine/benchmark_array_v4.py`

## Analysis (10 Jul 2026)

**Decision:** Ship **v4 sequential** (array fastest + array v3 optimized + shared bake on refresh). **Do not ship thread-parallel** on CPython — it does not beat sequential and is sometimes slightly slower.

### Headline (median vs prod wall)

| Mode | Fast preset | Safe preset |
|------|-------------|-------------|
| v3 (py fast + v3 opt) | **2.14×** | **1.78×** |
| **v4 seq** (array both) | **2.41×** | **2.03×** |
| v4 par (threads) | 2.31× | 2.00× |
| v4 theo (`max(fast,opt)`) | 3.00× | 2.45× |
| Array fastest alone | **2.21×** vs py fast | **1.57×** vs py fast |
| Shared bake | **45 ms** | — |
| Path / cost | Exact + parity **22/22** | same |

v4 seq vs v3: extra **~0.2–0.3×** from arraying the fastest leg (e.g. route 10 fast: prod 47.6 → v3 21.6 → v4seq 18.9 s).

### Parallel vs theo — what you measured

```text
v4 seq wall = fast_time + opt_time     (run one after the other)
v4 par wall = ThreadPool(fast, opt)    (try to overlap)
v4 theo     = max(fast_time, opt_time) (ideal overlap — NOT a real run)
```

**par/seq ≈ 0.94–1.01** everywhere — threads do not overlap pure-Python A* under the **GIL**. Overhead sometimes makes par *worse* than seq.

**theo** is the *hypothetical* wall if both legs could use two cores at once. It is **not** something ThreadPoolExecutor delivers today. Example route 10 fast:

| | Time |
|--|------|
| fast | 3.57 s |
| opt | 15.34 s |
| seq | 18.93 s |
| theo | **15.34 s** (= opt only; fast “hides” under opt) |
| measured par | 19.04 s ≈ seq |

So theo looks better (~3× vs prod) because it **assumes** free concurrency. Until search is native/GIL-free (Numba/C++/free-threaded CPython), that number is aspirational only.

When opt ≫ fast (most long routes), even perfect parallel only saves the **shorter** leg — still useful later, but not available via threads now.

### Ship set

1. Array optimized (v3) + **array fastest** — sequential  
2. Shared overlay bake after live refresh (~45 ms)  
3. Skip thread-parallel until a non-GIL search core exists  

### Related

- v1–v3: [`array_costs_report.md`](array_costs_report.md)
- Backlog: [`route_generation_performance.md`](../route_generation_performance.md)
