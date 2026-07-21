# Frontend design hub — Tuned Cycling

**Purpose:** Single place for agents (and you) during the frontend overhaul. Skills live in [`.agents/skills/`](../../.agents/skills/); competitor notes and brief go here.

**Approach (locked):** **Complete visual rebuild** — new UI shell/components/styling. Keep **behaviour and wiring** (state, Flask contracts, map/route/auth flows). Do not evolve the current look; treat today’s chrome as disposable.

**Implementation gate:** Do **not** start rebuilding UI until the user provides detailed instructions per core element.

---

## Read order (before any UI work)

1. [`BRIEF.md`](BRIEF.md) — brand, palette, layout blueprint, dials  
2. [`competitor_benchmarks/SYNTHESIS.md`](competitor_benchmarks/SYNTHESIS.md)  
3. [`ARCHITECTURE_DIRECTION.md`](ARCHITECTURE_DIRECTION.md) — zones, strip/keep, open questions  
4. Per-app: [`competitor_benchmarks/google_maps.md`](competitor_benchmarks/google_maps.md), [`apple_maps.md`](competitor_benchmarks/apple_maps.md), [`beeline.md`](competitor_benchmarks/beeline.md)  
5. [`brainstorming.md`](brainstorming.md) — raw archive only  
6. Skills: `design-taste-frontend`, `high-end-visual-design`, `emil-design-eng`

**Logo default:** [`logo_assets/logo_transparent_bg_noshadow.svg`](logo_assets/logo_transparent_bg_noshadow.svg)  
**Icons (when building):** `lucide-react` — draft map in [`ARCHITECTURE_DIRECTION.md`](ARCHITECTURE_DIRECTION.md)

---

## Parallel or only one?

**Use Taste + Emil together** — different jobs. Do **not** enable every Taste *variant* at once.

| Source | Role |
|--------|------|
| **Leonxlnx / Taste** | New visual language, anti-generic layout/type/colour |
| **Emil Kowalski** | Motion craft, springs, micro-interactions, polish |

| Avoid loading together | Why |
|------------------------|-----|
| `minimalist-ui` + `industrial-brutalist-ui` + `high-end-visual-design` | Conflicting visual dialects |
| All Taste imagegen skills as always-on | Noise; use when generating comps only |

### Recommended stack (complete overhaul)

1. **`design-taste-frontend`** — **primary** for inventing the new look (anti-slop, dials, pre-flight)  
2. **`high-end-visual-design`** — premium / sleek direction  
3. **`emil-design-eng`** (+ **`improve-animations`** / **`review-animations`** when motion is in scope)  

**`redesign-existing-projects`** stays installed but is **secondary / optional** — use only if you explicitly want an audit-of-current-UI pass. For a full swap, do **not** make it the lead skill (it biases toward incremental restyle of what exists).

Optional: **`apple-design`** for sheets / gestures / materials.

Note: Taste’s own blurb is landing/portfolio-heavy; for the **map product shell**, still lead with it for craft rules, but let [`BRIEF.md`](BRIEF.md) + competitor notes override any “marketing landing only” bias. Preserve dense planner affordances (panels, overlays, map).

---

## Agent instructions (copy into a task)

When implementing frontend design work:

1. Read this hub first.  
2. Follow `.agents/skills/<name>/SKILL.md` for **design-taste-frontend**, **high-end-visual-design**, **emil-design-eng**.  
3. Read [`BRIEF.md`](BRIEF.md), [`ARCHITECTURE_DIRECTION.md`](ARCHITECTURE_DIRECTION.md), and [`competitor_benchmarks/`](competitor_benchmarks/).  
4. **Keep logic:** route state, vias, profiles, auth, geocode, Santander, Depart at, overlay behaviour, Mapbox map module APIs.  
5. **Replace chrome:** layout, CSS, component structure, visual hierarchy — greenfield UI OK; extract shared hooks/api clients rather than copying old JSX styling.  
6. Use **`lucide-react`** for icons unless user specifies otherwise.  
7. Default logo: `logo_assets/logo_transparent_bg_noshadow.svg`.  
8. Declare the new system in BRIEF (tokens, type, surfaces) as you lock it.

Suggested prompt opener:

> Follow `0_documentation/design/README.md`. Complete frontend UI overhaul: new design via design-taste-frontend + high-end-visual-design + emil-design-eng. Preserve all routing/auth/map functioning and Flask contracts; discard current visual structure.

---

## Folder map

```text
0_documentation/design/
  README.md                 ← this file (hub)
  BRIEF.md                  ← brand words, audience, must-keep function
  ARCHITECTURE_DIRECTION.md ← zones, strip/keep, open questions (from brainstorm)
  FUNCTIONALITY_CHECKLIST.md← every legacy feature + v2 tick-off
  brainstorming.md          ← raw ideation archive
  competitor_benchmarks/    ← screenshots + per-app notes + SYNTHESIS.md
  logo_assets/              ← logo_transparent_bg_noshadow.svg (default), README
  references/               ← optional moodboards / URLs

5_frontend/src/
  App.js                    ← legacy (unchanged)
  v2/                       ← visual rebuild (npm start -- --v2)
```

---

## Installed skills (lockfile: `skills-lock.json`)

### Taste (Leonxlnx)

| Folder | Role now |
|--------|----------|
| `design-taste-frontend` | **Primary** — new visual language |
| `high-end-visual-design` | Premium / expensive look |
| `redesign-existing-projects` | Optional audit only — not lead for full swap |

### Emil (emilkowalski)

| Folder | When to invoke |
|--------|----------------|
| `emil-design-eng` | Polish, component feel |
| `apple-design` | Gesture / spring / material language |
| `improve-animations` | Motion audit + plans |
| `review-animations` | Review motion diffs |

```powershell
cd c:\London_Cycle_Maps
npx skills update -p -y
```

---

## Status

- [x] BRIEF filled (user)  
- [x] Competitor screenshots + structured notes  
- [x] Architecture direction from brainstorming  
- [x] Logo assets documented  
- [x] **Functionality checklist** — [`FUNCTIONALITY_CHECKLIST.md`](FUNCTIONALITY_CHECKLIST.md)  
- [x] **v2 parallel frontend** — `5_frontend/src/v2/` (`npm start -- --v2`)  
- [ ] Per-element UI build specs (user, next)  
- [ ] Frontend rebuild (in progress — shell only)
