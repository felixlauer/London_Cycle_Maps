# Weight dependency matrix

Phase 2 dependency logic for Tuned Cycling routing profiles. Authored from the 2026-06-19 parameter sweep (`6_verification/parameter_sweeps/2026-06-19/*/slider_analysis.md`).

## Files

| File | Purpose | Consumers |
|------|---------|-----------|
| `weight_stat_effects.json` | Level A — what each weight does to route stats when raised in isolation | Preset design, UI tooltips, coupling inference |
| `weight_couplings.json` | Level B — weight ↔ weight antagonism, synergy, merge rules | UI warnings, Phase 5 translation layer |
| `mechanisms.json` | Named routing escape patterns (why routes go wrong) | Integration tests (Phase 4), preset bundling |

## Stat → weight map

`dist_km` and `duration_min` are route meta-stats (`null` weight). All other stats map to the weight that optimises them — see `stat_to_weight` in `weight_stat_effects.json`.

## Strength rules

An effect is `strong` if any of:

- ≥40% relative swing on ≥3 routes
- Map-breaking artefact (zig-zag, U-turn, pedestrian shortcut)
- `dist_km` Δ ≥ +1.5 km on any route, or avg Δ ≥ +0.8 km
- `duration_min` Δ ≥ +6 min on any route, or avg Δ ≥ +3 min

Conversion: `duration_min ≈ dist_km × 3.75` at 16 km/h.

## Preset modes and `mode_dominant`

Three routing personas: **`fast`**, **`safe`**, **`leisure`** (see `modes` and `mode_labels` in `weight_couplings.json`).

On every `type: antagonistic` or `type: floor` coupling, `mode_dominant` names which weight wins when both conflict **for that mode**:

```json
"mode_dominant": {
  "fast": "signal_weight",
  "safe": "risk_weight",
  "leisure": "risk_weight"
},
"tie_break_reason": "Shared rationale for why this pair fights."
```

The translation layer reads the active preset mode, looks up `mode_dominant[mode]`, and caps or counterweights the other weight.

**Scope:** `mode_dominant` applies to **non-binary sliders** only. Binary toggles (e.g. `light_weight`) are resolved outside this matrix — see `tie_break_note` in `weight_couplings.json`.

## Phase 3 — Presets

Read `weight_couplings.json` synergistic entries and `mechanisms.json` `preset_guidance` before drafting persona JSON. Do not combine high antagonistic pairs without bundling rules.

**Visualizations:** [`visualizations/`](visualizations/) — network graph (per mode), distance cost matrix, mechanism flow (`python visualizations/generate_plots.py`).

**Mode tie-break review:** [`dominant_weight_review.md`](dominant_weight_review.md) — applied fast/safe/leisure winners per coupling.

## Phase 5 — Translation layer

1. Load `weight_couplings.json` and the active preset `mode` (`fast` | `safe` | `leisure`)
2. For each antagonistic coupling where `trigger` matches user weights, apply `guardrail.priority` in order
3. On tug-of-war, honour `mode_dominant[mode]` — reduce or cap the non-dominant weight
4. Reference `effect_ids` for logging/debug only

**Not implemented yet** — no Python loader in this folder.

## Weight universe

15 swept weights including `vehicular_free_weight` (active in `app.py` routing, not yet in `ROUTING_WEIGHT_KEYS`). `width_weight` is documented as inert — do not ship UI.
