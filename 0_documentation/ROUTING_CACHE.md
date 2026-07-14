# Routing cache (static startup sidecars)

Precomputes derived routing structures **once** after the final graph is built, so `app.py` does not recompute them on every process start.

**Format version 2:** path/inspect polylines live in a lazy **`EdgeGeomStore`** (`geom_offsets.npy` + `geom_flat.npy`, mmap-friendly). Startup stamps only `_eid` / `_vf` on NetworkX edges — **not** per-edge `_coords` lists. Request paths never mutate the graph (thread-safe).

## Build

```text
cd 3_pipeline
python prebuild_routing_cache.py
python prebuild_routing_cache.py --parity   # optional slow correctness rebuild
```

Also runs automatically as the last step of `run_graph_pipeline.py` (skip with `--skip-routing-cache`).

**After any graph rebuild you must re-run prebuild.** A new gpickle with a stale cache is refused at boot (fingerprint and/or alignment).

## Output

`1_data/london_elev_final_tfl.routing_cache/`

| File | Contents |
|------|----------|
| `meta.json` | `cache_format_version` (2), `formula_id`, graph fingerprint, timings |
| `tables.npz` | `EdgeCostTables` columns |
| `park_oh_exprs.json` | park opening-hours catalog |
| `floors.json` | heuristic penalty floors |
| `csr.npz` | CSR + `idx_to_node` |
| `nodes.npz` | junction flags / cluster mask |
| `edges.npz` | `edge_u` / `edge_v` endpoints aligned with table rows |
| `geom_offsets.npy` | int64 offsets (standalone `.npy` for mmap) |
| `geom_flat.npy` | float32 `(n_pts, 2)` lat/lon |
| `geom_wkb.npz` | WKB blob for STRtree |

## Lazy geometry store

Module: [`4_backend_engine/edge_geom_store.py`](../4_backend_engine/edge_geom_store.py).

Resolution in `coords_for_edge` / `extract_segment_geometry`:

1. `EdgeGeomStore` by `d['_eid']`
2. Read-only `d.get('_coords')` if already present (bootstrap legacy only)
3. WKT parse via cached pure helper — **return only; never write `d['_coords']` on the request path**

## Fail-closed alignment

On every cache load / apply:

1. Meta: format version, `formula_id`, graph size/mtime, node/edge counts
2. Refuse **MultiDiGraph** (production is `DiGraph`; parallel edges would need keys in the sidecar)
3. Sampled (or `ROUTING_CACHE_ALIGN=full`) check: endpoints in `G`, geom first/last ≈ `u`/`v` with **`abs_tol=1e-5` degrees** (~1.1 m) to avoid float32 false rejects

Mismatch → cache refused → cold rebuild (or hard fail if you set a strict ops policy later).

## Measured prebuild (13 Jul 2026, v2)

Prebuild **16.9 min**, alignment OK (512 edges), reload verify OK. `formula_id=2026-07-13-v1`, format **2**.

## Improvements measured (cold → v1 → v2)

Same machine, `benchmark_startup_ram.py`, live fetch off. Latest: [`testing/startup_ram_report.md`](testing/startup_ram_report.md).

| Metric | Cold | Cache v1 (lists) | **Cache v2 (lazy)** |
|--------|-----:|-----------------:|--------------------:|
| **Ready to serve** | 506.8 s (8.4 min) | 502.2 s (8.4 min) | **151.5 s (2.5 min)** |
| Geom wait after ready | 308.5 s | 0 | **0** |
| Time to geom-ready | 815.2 s (13.6 min) | 502.3 s | **151.5 s** |
| Cache apply | — | 441.2 s | **98.4 s** (stamps 52.4 s) |
| RSS at ready | 7.65 GiB | 5.73 GiB | 5.91 GiB |
| RSS idle hosting | 8.04 GiB | 5.46 GiB | **3.52 GiB** |
| Peak RSS | 8.45 GiB | 8.71 GiB | 8.02 GiB |
| Route smoke A* | 1.55 s | 0.94 s | 0.80 s |

**v2 vs cold:** ready **−70%**; geom-ready **−81%**; idle RSS **−56%**.  
**v2 vs v1:** ready **−70%** by dropping 4M `_coords` list materialization.

### Where v2’s 2.5 min goes

| Piece | ≈ s |
|-------|----:|
| Graph `.gpickle` load | 36 |
| Cache apply (align + `_eid`/`_vf` stamp + load arrays/WKB STRtree) | 98 |
| KD-tree | 5.5 |
| Numba warmup | 2 |
| Overlays / misc | few |

### Ceiling?

**Not a hard ceiling** — the 8.4 min plateau is gone. Soft floor with “full NetworkX + stamp every edge” is about **pickle + apply ≈ 1.5–2.5 min**. Next levers (diminishing / harder): skip unused KD-tree; avoid stamping `_eid` on all NX edges; leaner graph format / less resident NX.

## Server load

| Env | Effect |
|-----|--------|
| `ROUTING_CACHE=0` | Ignore cache; full cold rebuild |
| `ROUTING_CACHE_BUILD=1` | Prebuild script (skip auto-bootstrap when importing `app`) |
| `ROUTING_CACHE_ALIGN=full` | Audit all edges (slower; good for prebuild) |

## Invalidation

Rebuild cache when:

- Final `.gpickle` rewritten (size/mtime)
- Cost / junction / floor formulas change → bump `FORMULA_ID`
- Layout / lazy-store contract → bump `CACHE_FORMAT_VERSION` (currently **2**)

## Correctness / tests

```text
python 4_backend_engine/test_edge_geom_store.py -v
```

Prebuild: reload table/CSR compare + alignment audit + optional `--parity`.
