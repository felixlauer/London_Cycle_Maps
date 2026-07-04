# Mode tie-break review

Verification table for `weight_couplings.json` **antagonistic** and **floor** couplings. Tie-breakers are **per preset mode** (`fast`, `safe`, `leisure`) — not a single global winner.

**Status:** Manual corrections from 2026-07-03 applied to `mode_dominant` in JSON.

## Schema

Each coupling row in JSON:

```json
"mode_dominant": {
  "fast": "signal_weight",
  "safe": "risk_weight",
  "leisure": "risk_weight"
},
"tie_break_reason": "Why this pair conflicts (shared across modes)."
```

**Phase 5 note:** `mode_dominant` applies to **non-binary sliders** only. Binary toggles (e.g. `light_weight`) are resolved outside this matrix in the translation layer.

## Applied tie-breakers

| ID | Type | Weight A | Weight B | Fast | Safe | Leisure | Tie-break reason |
|----|------|----------|----------|------|------|---------|------------------|
| `signal_risk_arterial` | antagonistic | `signal_weight` | `risk_weight` | `signal_weight` | `risk_weight` | `risk_weight` | Safety is non-negotiable; signal avoidance via arterial bypass spikes accidents (Putney +94% @0.6). Translation layer preserves risk intent and caps or counterweights signal. |
| `signal_calming_rat_run` | antagonistic | `signal_weight` | `calming_weight` | `signal_weight` | `signal_weight` | `calming_weight` | Rat-run speed bumps are false economy for fewer lights — Comfort Flow caps signal at 0.4 when calming is non-zero (signal §6.3). |
| `signal_light_night` | antagonistic | `signal_weight` | `light_weight` | `signal_weight` | `light_weight` | `light_weight` | Night corridors need lit routing; arterial bypass from signal avoidance drops illumination (Putney 90%→60% @0.6). |
| `speed_risk_twickenham` | antagonistic | `speed_weight` | `risk_weight` | `risk_weight` | `risk_weight` | `speed_weight` | Twickenham accidents +171% @speed 1.0 — low stress does not imply safe alignment. Fast mode still prioritises risk over speed (residential detours cost time). |
| `speed_calming_rat_run` | antagonistic | `speed_weight` | `calming_weight` | `calming_weight` | `speed_weight` | `speed_weight` | Wembley/Bromley/Hill calming storms (+700% Wembley @3.0) on stress-avoidance rat runs. |
| `junction_risk_arterial` | antagonistic | `junction_weight` | `risk_weight` | `junction_weight` | `risk_weight` | `junction_weight` | Kings Cross accidents +133% @junction 2.0 — arterial road warning; mitigate via risk, not lower junction cap. |
| `hill_green_preset` | antagonistic | `hill_weight` | `green_weight` | `hill_weight` | `green_weight` | `green_weight` | Thames flat path vs heath scenic pull — mode-dependent tug-of-war. |
| `hill_risk_valley` | antagonistic | `hill_weight` | `risk_weight` | `hill_weight` | `risk_weight` | `hill_weight` | Valley-trap routing @hill 3.0 spikes accidents on Greenwich (+155%), Bromley (+72%), Wembley (+76%). |
| `hill_calming_tottenham` | antagonistic | `hill_weight` | `calming_weight` | `hill_weight` | `hill_weight` | `hill_weight` | Tottenham calming 17→67 @hill 0.2 on flat bypass — bumpier than hill climb. |
| `barrier_risk_greenwich` | antagonistic | `barrier_weight` | `risk_weight` | `barrier_weight` | `risk_weight` | `barrier_weight` | Greenwich accidents +53% @barrier 0.6 when dodging gates. |
| `calming_risk_arterial` | antagonistic | `calming_weight` | `risk_weight` | `calming_weight` | `risk_weight` | `calming_weight` | Tottenham/Bromley accident rises @calming 1.5 when avoiding bumps via arterials. |
| `green_barrier_twickenham` | antagonistic | `green_weight` | `barrier_weight` | `barrier_weight` | `green_weight` | `green_weight` | Twickenham scenic detour adds 8 barriers @green 0.2 — physical gates block cargo/wide bikes. |
| `surface_green_parks` | antagonistic | `surface_weight` | `green_weight` | `surface_weight` | `green_weight` | `green_weight` | Paved-only preference beats park gravel — road bike hardware override in Phase 3. |
| `surface_speed_tottenham` | antagonistic | `surface_weight` | `speed_weight` | `surface_weight` | `speed_weight` | `speed_weight` | Tottenham paved detour accepts +36% speed_stress to stay on smooth surfaces. |
| `surface_risk_tottenham` | antagonistic | `surface_weight` | `risk_weight` | `surface_weight` | `risk_weight` | `risk_weight` | Tottenham accidents +28% on paved detour @surface 0.2. |
| `tfl_cycleway_calming_bromley` | antagonistic | `tfl_cycleway_weight` | `calming_weight` | `tfl_cycleway_weight` | `tfl_cycleway_weight` | `tfl_cycleway_weight` | Infrastructure reward beats Bromley calming side-effect (+84% @0.2) — CS network priority for Commuter. |
| `tfl_live_risk_kings_cross` | antagonistic | `tfl_live_weight` | `risk_weight` | `tfl_live_weight` | `risk_weight` | `tfl_live_weight` | Kings Cross accidents +68% @tfl_live 0.2 on closure bypass. |
| `tfl_live_surface_earls` | antagonistic | `tfl_live_weight` | `surface_weight` | `tfl_live_weight` | `tfl_live_weight` | `tfl_live_weight` | Earls Court rough 15% @tfl_live 0.2 on unpaved bypass. |
| `tfl_live_calming_wembley` | antagonistic | `tfl_live_weight` | `calming_weight` | `tfl_live_weight` | `tfl_live_weight` | `tfl_live_weight` | Wembley +411% calming @tfl_live 0.2 — residential closure dodge. |
| `tfl_quietway_risk_bromley` | antagonistic | `tfl_quietway_weight` | `risk_weight` | `tfl_quietway_weight` | `risk_weight` | `tfl_quietway_weight` | Bromley accident +5% on quietway-only detour. |
| `vehicular_free_risk_accidents` | antagonistic | `vehicular_free_weight` | `risk_weight` | `vehicular_free_weight` | `vehicular_free_weight` | `vehicular_free_weight` | Tottenham +45% and Bromley +20% accidents on segregated pulls — car-free assumed to mask accident risk in all modes. |
| `risk_light_floor` | floor | `risk_weight` | `light_weight` | `risk_weight` | `risk_weight` | `risk_weight` | Risk floor bundles with light for night — light treated as binary toggle in Phase 5. |
| `risk_surface_floor` | floor | `risk_weight` | `surface_weight` | `surface_weight` | `risk_weight` | `risk_weight` | Paved floor when risk pushes rough park/path shortcuts (Putney rough 27% @risk 0.8). |
| `signal_junction_paradox` | antagonistic | `signal_weight` | `junction_weight` | `signal_weight` | `junction_weight` | `junction_weight` | Same paradox family — junction flow vs signal avoidance; junction cap 3.0 already pairs with risk. |

**Summary:** 24 rows — 22 antagonistic, 2 floor.

## Excluded (no mode tie-break)

| ID | Type | Weights |
|----|------|---------|
| `light_risk_night_bundle` | synergistic | `light_weight`, `risk_weight` |
| `vehicular_free_tfl_cycleway_bundle` | synergistic | `vehicular_free_weight`, `tfl_cycleway_weight` |
| `signal_daytime_flow_bundle` | synergistic | `signal_weight`, `risk_weight` |
| `tfl_quietway_merged_into_cycleway` | ui_merge | `tfl_cycleway_weight`, `tfl_quietway_weight` |

## Visualizations

Network graph arrows point to `mode_dominant[mode]` — see `network_graph.png` (3 panels) or `network_graph.html` (mode dropdown).
