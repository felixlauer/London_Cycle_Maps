# Competitor benchmark — Google Maps (web)

**Screenshot:** [`google_maps.png`](google_maps.png)  
**Context:** Cycling route, London (desktop web, German UI).  
**Status:** Directional reference — not a pixel target.

---

## Layout

| Zone | What they do |
|------|----------------|
| **Left column (fixed)** | Full-height sidebar: mode icons, start/end, route list, elevation mini-chart |
| **Map** | Dominant; route lines + POI clutter |
| **Top of map** | Search-along-route + category filter chips |
| **Bottom-left** | Layers (satellite thumbnail) |
| **Bottom-right** | Zoom, Street View pegman, scale |

Routing core is **top-left in a fixed panel**, not floating.

---

## What works (borrow)

- **Mode icons above routing** — clear transport/mode affordance (we adapt for *bike type* + *user mode*, not car/transit).
- **Elevation profile** tied to route card — good precedent for expanded analysis / Beeline-style bottom sheet.

---

## What to avoid

- **Fixed full-height left column** — eats map; conflicts with map-centric Tuned direction.
- **Dense POI pins** on planning view — noise for route planning.
- **Split layers bottom-left + controls bottom-right** — we prefer **clustering map controls bottom-right** only (no satellite/layers v1).

---

## Maps to Tuned (planned)

| Google pattern | Tuned direction |
|----------------|-----------------|
| Left routing panel | **Floating top-left panel** (same job, different chrome) |
| Mode icon row | **Mode + bike type pills** in routing panel (see [`../ARCHITECTURE_DIRECTION.md`](../ARCHITECTURE_DIRECTION.md)) |
| Elevation in sidebar | **Expanded Dynamic Island / bottom sheet** |
| Profile / account | **Top-right profile pill → drawer** (Google uses account elsewhere on web) |

---

## Lucide hints (when building)

- Modes: `Bike`, `Zap` (e-bike), `Package` (cargo), `Circle` (regular) — refine with user.
- Routing: `MapPin`, `Navigation`, `ArrowLeftRight` (swap).
