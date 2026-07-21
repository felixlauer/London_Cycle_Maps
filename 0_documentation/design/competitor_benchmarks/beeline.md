# Competitor benchmark — Beeline (web planner)

**Screenshot:** [`beeline.png`](beeline.png)  
**Context:** Cycling route, London; Mapbox basemap.  
**Status:** **Strongest visual reference** for route line treatment and bottom analysis.

---

## Layout

| Zone | What they do |
|------|----------------|
| **Left** | Narrow nav (Plan, Saved, Account) + **fixed** planning column (start/end, Cycling dropdown, route cards) |
| **Map** | Segmented colour route (path types); undo/redo top-left of map |
| **Bottom overlay** | Large white card: distance, uphill/downhill, time, surface bar, **full elevation profile** |
| **Right** | Vertical 3D / zoom controls |

Has a **top bar** (logo + Shop) — user prefers **no** global top bar for Tuned.

---

## What works (borrow)

- **Route line aesthetics** — colour segments with **white halo/stroke** on map; grey for non-selected routes. **Adopt for Tuned overlays + optimized path.**
- **Bottom analysis sheet** — metrics row + charts; expands analysis without permanent left column.
- **Elevation profile** — full width in expanded analysis; category tabs can switch chart type (brainstorm).
- **Cycling + Preferences** row — analogous to **mode + bike type** selectors.
- **Yellow accent discipline** — parallel: Tuned uses **fuchsia `#FF0061`** as single primary action colour.

---

## What to avoid

- **Fixed left planning column** — keep Beeline's *information architecture*, not its docked layout.
- **Global header bar** — replace with floating zones + logo in profile/routing context only if needed.
- **Three route philosophies** — product is two-route compare, not Fast/Balanced/Quiet trio.

---

## Maps to Tuned (planned)

| Beeline pattern | Tuned direction |
|-----------------|-----------------|
| Bottom stats + elevation | **Dynamic Island** collapsed → **bottom sheet** expanded |
| Segmented route colours | Map overlay layers + optimized polyline styling |
| White-bordered route | Implement on Mapbox GL layers (stroke + fill) |
| Hover segment detail | Open question: top-center **comm pill** vs **on-map pill** (see architecture doc) |

---

## Lucide hints

- Beeline-style prefs: `SlidersHorizontal`
- Save/GPX (future): `Download`, `Bookmark`
- Elevation: `Mountain`, `TrendingUp`
