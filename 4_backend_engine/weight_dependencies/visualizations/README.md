# Dependency matrix visualizations

Static and interactive plots derived from the Phase 2 JSON files in the parent folder (`weight_stat_effects.json`, `weight_couplings.json`, `mechanisms.json`). Use these when designing presets, the Detour Budget Bar, and translation-layer guardrails.

## Generate plots

From repo root:

```powershell
cd c:\London_Cycle_Maps
python 4_backend_engine/weight_dependencies/visualizations/generate_plots.py
```

**Dependencies:** `matplotlib`, `networkx`, `plotly` (see `4_backend_engine/requirements.txt`).

**Outputs** (written into this folder):

| File | Format | Source JSON |
|------|--------|-------------|
| `network_graph.png` | Static | `weight_couplings.json` |
| `network_graph.html` | Interactive | `weight_couplings.json` |
| `distance_cost_matrix.png` | Static | `weight_stat_effects.json` |
| `distance_cost_matrix.html` | Interactive | `weight_stat_effects.json` |
| `mechanism_flow.png` | Static | `mechanisms.json` |
| `mechanism_flow.html` | Interactive (Sankey) | `mechanisms.json` |

Open the `.html` files in a browser for pan/zoom and hover tooltips. HTML files load Plotly from CDN (internet required on first open).

Re-run the script after editing any dependency JSON.

---

## 1. Network graph — Web of conflict

**Files:** `network_graph.png` (3 panels: fast \| safe \| leisure) · `network_graph.html` (interactive — mode dropdown, pan/zoom)  
**Source:** `weight_couplings.json`

### What it shows

The architecture of weight interactions in your routing profiles — which sliders fight each other and which bundle safely.

### How to read it

| Element | Meaning |
|---------|---------|
| **Blue circles (nodes)** | One of the 15 swept routing weights (short labels, e.g. "Traffic lights" = `signal_weight`) |
| **Node size** | Number of antagonistic/floor couplings touching that weight — larger = more conflicts (`risk_weight` is typically largest) |
| **Red arrows** | Antagonistic or floor coupling — **arrow points to `mode_dominant[mode]`** (who wins for the active fast/safe/leisure preset) |
| **Green connections** | Synergistic pairs (e.g. Light + Safety for Night Ride) — bidirectional, no dominant side |
| **Purple dashed** | UI merge (`tfl_quietway_weight` co-set with `tfl_cycleway_weight`) |

### Why you need it

When building a **preset JSON**, turn up weights that are green-connected or non-conflicting. Red arrows are **mode-specific** — check the panel for your persona (Fast / Safe / Leisure) before pairing antagonistic sliders.

**Example:** In **Safe** mode, Signal ↔ Safety arrow points to Safety — maxing "fewer lights" without enough Safety risks arterial bypass; bundle `risk_weight >= 0.5`. In **Fast** mode the same pair points to Signal.

---

## 2. Distance cost matrix — Budget chart

**Files:** `distance_cost_matrix.png` (static) · `distance_cost_matrix.html` (interactive — hover bars for per-route detail)  
**Source:** `weight_stat_effects.json` → `distance_effects` and `distance_explosion_routes`

### What it shows

How expensive each weight is in **extra kilometres** when pushed hard — the raw numbers behind the **Detour Budget Bar** (Option A UX).

### How to read it

| Element | Meaning |
|---------|---------|
| **Y-axis** | Routing weights (hidden `width_weight` omitted) |
| **X-axis** | Extra distance vs baseline (km) |
| **Blue bars** | Max detour at **shipped product cap** (or average aggressive if no single-route explosion) |
| **Red extension** | Additional km from **rejected** sweep multipliers (e.g. @5.0) — not exposed in UI but shows worst-case toxicity |
| **Orange dots** | Average aggressive detour across qualifying test routes |
| **Red dashed line (+1.5 km)** | "Distance explosion" threshold from the dependency schema |
| **Orange dotted line (+0.8 km)** | Strong average detour threshold |

### Why you need it

Instantly answers: *"Can I afford to max this slider on the Commuter preset?"*

- **Hill** and **Car-free** show the largest max detours (Bromley +4 km class) — budget-hungry; use moderate steps on long commutes.
- **Traffic lights** aggressive is costly on cross-city routes but moderate step (+0.6 km avg) is affordable.
- **Junction / calming / barrier** bars stay small — cheap "flow" tweaks.

Use blue bar + orange dot together: blue = worst case on one route; orange = typical cost.

---

## 3. Mechanism flow — Escape routes

**Files:** `mechanism_flow.png` (static) · `mechanism_flow.html` (interactive Sankey — hover bands, highlight signal paths)  
**Source:** `mechanisms.json`

### What it shows

The gap between **what the user asks for** (raise a weight) and **what the algorithm actually does** (escape mechanism) and **which route stats move** (consequences).

### How to read it

Three columns, left → right:

| Column | Content |
|--------|---------|
| **Left — User raises weight** | Trigger weights from each mechanism (`trigger_weights`) |
| **Middle — Routing mechanism** | Named escape pattern (e.g. "Arterial bypass", "Residential rat run") |
| **Right — Route stat consequence** | Stats that move (↑ increase, ↓ decrease) from `stat_signature` |
| **Green boxes** | Desirable or neutral-positive side effect |
| **Red boxes** | Undesirable side effect — accidents ↑, illumination ↓, vehicular free ↓, calming count ↑, dist km ↑, green ↓, rough ↑, barrier ↑, speed stress ↑, elevation gain ↑ |

**Red flows** highlight paths starting from `signal_weight` — the canonical "arterial vs rat run" split:

- Signal ↑ → **Arterial bypass** → accidents ↑, lighting ↓  
- Signal ↑ → **Rat run** → calming count ↑, distance ↑  

**Gray flows** — all other weight → mechanism → stat paths (lower opacity to reduce clutter).

### Why you need it

Safe presets must account for **mechanism**, not just weight values. If Commuter enables high `signal_weight`, expect either arterial exposure (pair Safety) or rat runs (pair Calming / cap signal). The flow diagram makes that implicit trade-off visible for PM and frontend copy.

---

## Data lineage

```
6_verification/parameter_sweeps/2026-06-19/*/slider_analysis.md
        ↓ (manual Phase 2 authoring)
4_backend_engine/weight_dependencies/*.json
        ↓ (generate_plots.py)
4_backend_engine/weight_dependencies/visualizations/*.png
```

---

## Customization

Edit `generate_plots.py` to:

- Change colour palette or figure size
- Filter mechanism flow to a single weight (e.g. only `signal_weight`)
- Export SVG/PDF by changing `savefig` format
- Set `include_plotlyjs=True` in `_write_html()` for fully offline HTML (larger files)
