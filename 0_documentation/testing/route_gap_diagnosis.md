# Route gap diagnosis — prod vs v4 bench

Generated: 2026-07-10T16:45:43.400023+00:00
Route: **route 10: Bromley to Ealing** (safe optimized leg)
Park hours at: `2026-07-10T17:39:45.670209+01:00` | fallback_open=True
Impassable: prod=201,629 bac=201,629 (bench ref 199,189)
length|prod−bac|max = 0.000e+00

## Codified prod vs bench input diffs

| Factor | v4 bench (`benchmark_array_v4.py`) | Production `/route` |
|--------|-------------------------------------|---------------------|
| Coords | `6_verification/test_routes.txt` | Map click / geocode |
| Weights | Raw `user_profiles.json` | Profile store (+ optional Supabase) |
| Clamps | None | `translation_layer.apply_preset_clamps` |
| Light | `light_weight` kept (safe=0.6) | Daytime: forced to 0 |
| ε | Report used **0.5** | Default **0.75** |
| Arrays | `bac` tables + `make_array_weight_fn_v3` | `edge_cost_arrays` |
| Parks | Shared bake once at bench `london_now()` | Shared bake at startup / live refresh (not per request on array path) |
| Live | `SKIP_DISRUPTION_FETCH=1` | Default fetch on (`--no-live` to match) |
| A* | `astar_unidirectional` | `run_astar(..., uni)` — same core |

## Results

| Variant | Backend | ε | scale | exp | s | ms/exp | exp÷ref | s÷ref |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `bench_like` | bac | 0.5 | 0.683 | 674,062 | 38.112 | 0.0565 | 1.0 | 2.844 |
| `prod_arrays_same_inputs` | prod | 0.5 | 0.683 | 674,062 | 18.578 | 0.0276 | 1.0 | 1.386 |
| `+eps_0.75` | prod | 0.75 | 0.7968 | 541,202 | 12.055 | 0.0223 | 0.803 | 0.9 |
| `+light_gate` | prod | 0.5 | 0.683 | 614,032 | 13.316 | 0.0217 | 0.911 | 0.994 |
| `+clamps` | prod | 0.5 | 0.683 | 669,135 | 15.478 | 0.0231 | 0.993 | 1.155 |
| `+clamps+light_gate` | prod | 0.75 | 0.7968 | 476,931 | 9.979 | 0.0209 | 0.707 | 0.745 |
| `profile_store_day` | prod | 0.75 | 0.7968 | 476,931 | 9.996 | 0.0210 | 0.707 | 0.746 |

Bench ref: **674,123** exp / **13.401s** / ~0.0199 ms/exp
App `--no-live` target: **~937,387** opt expansions

## Movers vs `bench_like` (by Δ expansions)

| Variant | Δ exp | Δ s | expansions |
|---|---:|---:|---:|
| `prod_arrays_same_inputs` | +0 | -19.534 | 674,062 |
| `+clamps` | -4,927 | -22.634 | 669,135 |
| `+light_gate` | -60,030 | -24.796 | 614,032 |
| `+eps_0.75` | -132,860 | -26.057 | 541,202 |
| `+clamps+light_gate` | -197,131 | -28.133 | 476,931 |
| `profile_store_day` | -197,131 | -28.116 | 476,931 |

## Verdict

- `bench_like` reproduces the bench search size (**674,062 ≈ 674,123**). Park bake drift is small (impassable 201,629 vs ref 199,189) and does **not** explain the app’s ~937k expansions.
- **None of the prod weight toggles increase expansions** — they shrink the search:
  - `+light_gate` → 614k (−60k)
  - `+eps_0.75` → 541k (−133k)
  - `+clamps+light_gate` / `profile_store_day` → **477k / ~10s** (faster than the v4 bench opt leg)
- **bac vs prod arrays (same inputs):** identical expansions; prod was **faster** per expansion in this run (0.028 vs 0.057 ms/exp — bac was the first/cold A*). Arrays are not the regression.
- **App `--no-live` ~937k was not reproduced** by any weight/ε variant on exact bench coords. That spike was from **different map-click endpoints**, not light/clamps/ε/arrays.

## Confirm against `/route` (exact bench coords, `--no-live`)

| Field | `/route` meta | Closest diagnose variant |
|-------|---------------|--------------------------|
| `heuristic_epsilon` | **0.5** (from `.env`, not code default 0.75) | `+light_gate` uses ε=0.5 |
| `light_gated_off` | true | yes |
| `light_weight` | 0.0 | yes |
| `optimized_expansions` | **609,549** | `+light_gate` 614,032 |
| `optimized_astar` | **27.9s** | diagnose 13.3s (same ballpark of search; wall slower under Flask/load) |
| `array_costs` | true | — |

**Root causes of the “missing 3×” confusion:**

1. **Live disruptions** (earlier): ~80s → ~44s with `--no-live`.
2. **Map snaps ≠ bench coords**: ~937k vs ~610–674k expansions on the same corridor.
3. **`.env` pins `ROUTE_HEURISTIC_EPSILON=0.5`**, so daytime prod never got the ε=0.75 win (~477k / ~10s in diagnose). Code default is 0.75; env overrides it via `load_dotenv` in `tfl_live` / auth.
4. Benches reported **relative** array vs Python speedup under clean inputs — not a promise that map-click + live + ε=0.5 would hit ~17s wall.

To match the fastest diagnose daytime path: set `ROUTE_HEURISTIC_EPSILON=0.75` in `.env` (or remove the line), restart with `--no-live`, and use the exact test-route coords below.

```
GET /route?start_lat=51.405560084506675&start_lon=0.01867568474303856&end_lat=51.513518324696115&end_lon=-0.3037784031742642&profile_id=preset_safe
```

Re-run: `python 4_backend_engine/diagnose_route_gap.py`
