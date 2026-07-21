# Competitor synthesis — Tuned Cycling

**Purpose:** Cross-app patterns from Google Maps, Apple Maps, and Beeline.  
**Not gospel** — prioritization for the greenfield UI rebuild. Detail per app: [`google_maps.md`](google_maps.md), [`apple_maps.md`](apple_maps.md), [`beeline.md`](beeline.md).

**Screenshots:** `google_maps.png`, `apple_maps.png`, `beeline.png`

---

## Shared pattern (all three)

| Pattern | All three | Tuned choice |
|---------|-----------|--------------|
| Routing core **top-left** | Yes | **Yes** — but **floating panel**, not fixed sidebar (differentiator) |
| Map is hero | Yes | Yes |
| Mode / vehicle selection near route | Yes (icons or dropdown) | **User mode + bike type** near routing (move out of profile drawer) |
| Multiple route options | Yes (3+) | **No** — only **fastest** + **optimized** |
| Elevation / stats | Sidebar or bottom | **Bottom Dynamic Island** → expanded sheet (Beeline + Apple sparkline) |

---

## Tuned differentiators (from brief + brainstorm)

1. **Floating solid panels** instead of fixed left columns (Google/Apple/Beeline all dock panels).
2. **No global top bar** — use **top-center communication pill** for status, errors, Santander guidance, segment inspect.
3. **Profile top-right** → **slide-out drawer** (not modal overlay).
4. **Overlay selector** — vertical icon pill bottom-right; **horizontal droplet expand on hover** (contextual morph / tooltip rail — not full permanent labels).
5. **Preset-driven overlays** — user does not freely toggle every layer; modes define hierarchy.
6. **Lucide React** for icons (best-guess mapping; user may correct).

---

## Visual borrow matrix

| Element | Primary inspiration | Secondary |
|---------|---------------------|-----------|
| Route polyline + halo | **Beeline** | — |
| Collapsed trip metrics + microchart | **Apple** (sparkline) | Beeline (segment bar) |
| Expanded analysis / elevation | **Beeline** | Google (sidebar chart) |
| Dark map + solid cards | **Apple** | — |
| Floating pill commands | **Tuned current** (keep pattern) | — |
| Map controls cluster | **Google/Apple** bottom-right | Beeline right rail |

---

## Explicit rejects (for this overhaul)

- Full-height fixed left sidebar (Google/Apple/Beeline)
- Global marketing-style top bar (Beeline)
- Glassmorphism / frosted panels (BRIEF)
- Three+ alternative routes in UI
- Satellite / map-type picker v1
- Moving **user mode** selection into profile-only (current mistake)

---

## Read order for agents

1. [`../BRIEF.md`](../BRIEF.md) — tokens, layout blueprint, dials  
2. This file — cross-app intent  
3. Per-app notes above  
4. [`../ARCHITECTURE_DIRECTION.md`](../ARCHITECTURE_DIRECTION.md) — strip/keep, open questions  
5. [`../brainstorming.md`](../brainstorming.md) — raw ideation archive  

**Do not start implementation** until user provides per-element build instructions.
