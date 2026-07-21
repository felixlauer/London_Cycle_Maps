# Competitor benchmark — Apple Maps (web beta)

**Screenshot:** [`apple_maps.png`](apple_maps.png)  
**Context:** Cycling route, London, dark mode (German UI).  
**Status:** Premium reference for **card hierarchy** and **elevation sparkline** — not full layout copy.

---

## Layout

| Zone | What they do |
|------|----------------|
| **Far-left rail** | App nav: Search, Guides, Route, Recents |
| **Route panel** | Fixed column: mode segmented control, start/end, route cards |
| **Map** | Dark basemap; thick blue active route, grey alts |
| **Bottom-right** | Compact zoom / locate / 3D stack |

No global top bar on map. Route planning is **left-docked**, not floating.

---

## What works (borrow)

- **Premium dark cartography** — parks/water/roads read clearly; aligns with Tuned dark mode (solid surfaces, no glass).
- **Route cards** — active card in brand blue, alts recessed; clear hierarchy.
- **Elevation sparkline inside route card** — strong candidate for **collapsed Dynamic Island** microchart.
- **Segmented mode control** — clean; we use **pills/dropdowns** instead (more modes than 3 transport types).
- **Rounded corners + airy padding** — matches BRIEF solid floating panels.

---

## What to avoid

- **Persistent far-left app rail** — too much chrome for a single-purpose planner.
- **Full-width fixed route column** — same issue as Google; prefer **floating** routing core.

---

## Maps to Tuned (planned)

| Apple pattern | Tuned direction |
|---------------|-----------------|
| Route card + sparkline | Bottom-center **Dynamic Island** collapsed state |
| Active vs alt route styling | Optimized = fuchsia `#FF0061`; fastest = grey + lower opacity |
| Dark map + solid panels | BRIEF: rich dark gray panels, crisp borders |
| Bottom-right controls | **Stack:** overlay pill + zoom + locate + north (see architecture doc) |

---

## Lucide hints

- Profile: `User`, `UserCircle`
- Share (future): `Share2`
- Route: `Route`, `TrendingUp` (elevation sparkline metaphor)
