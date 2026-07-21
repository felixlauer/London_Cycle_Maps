# Design brief — Tuned Cycling frontend

**Fill this before / during the overhaul.** Agents should treat this as authoritative tone; skills supply craft rules.

## One-line product read

> Reading this as: **complete visual rebuild** of a London cycling **route planner** (map product UI + auth) — sleek, premium, modern. Keep how it works; throw away how it currently looks.

## Audience

- Urban cyclists planning safe / preferred routes in London  
- Guests using presets; logged-in users with custom profiles  

## Must keep (function / logic)

- **THE PRIME DIRECTIVE:** The visual layer (JSX/Tailwind) is greenfield and will be rebuilt entirely from scratch. The functional layer (Flask auth, `/route` API endpoints, Mapbox tokens, state hooks, and navigation logic) is sacred and must be audited and perfectly preserved.
- Map start / vias / end, Get Route, fastest vs optimized, depart at
- Profiles, overlays, Santander hire toggle (only keep functionality, not ui for all three)  
- Flask auth / geocode proxies; existing `/route` contracts  
- Mapbox GL planning map behaviour (not Leaflet)

## May replace entirely (chrome)

- Top bar, panels, typography, colour system, spacing, motion  
- Component tree / CSS architecture for UI chrome  
- Auth/landing visual presentation  

## Visual direction & Design Tokens

- **Vibe words:** Utilitarian, crisp, tactile, solid, high-contrast, map-centric.  
- **Closer to:** Linear-clean productivity tools / premium consumer maps.  
- **Light + night modes:** Strict solid colors. NO glassmorphism. Light mode uses pure white (`#FFFFFF`) or off-white floating panels. Dark mode uses rich dark gray/black. Use crisp, subtle drop shadows (`shadow-lg shadow-black/5`) and ultra-fine borders (`border-gray-200`) to define floating elements.

**Brand Palette (Strict HEX Codes):**
- **Primary / Brand Action:** Hot Fuchsia (`#FF0061`) — Use for primary buttons, active toggles, and primary route lines.
- **Secondary / Data / Overlays:** Blue Bell (`#4D9DE0`), Violet (`#8717BF`), Jungle Green (`#3BB273`), Banana Cream (`#FDE74C`). Use these for charts, metrics, and map layer indicators.
- **Situational (less preferred — use sparingly):** Tiger Orange (`#F18805`) for live traffic / emergencies; Crimson Violet (`#610345`) and Turquoise (`#13C2A4`) as optional overlay tones when a mode needs an extra hue beyond the core four.

## Layout Architecture (The Blueprint)

- **Top-Left (Routing Core):** Floating solid panel containing Start/End, Get Route, and a clean row of mode/bike selection pills. Include a chained toggle for Santander that visually updates the bike type.
- **Top-Right (Profile):** A floating profile pill that opens into a **Slide-out Sidebar (Drawer)**, not an overlay.
- **Top-Center (Communication):** A small, dynamic alert pill for routing status, errors, or live warnings.
- **Bottom-Right (Map Controls & Overlays):** Vertical pill with icons for the overlay modes that expand horizontally on hover to reveal overlay text like "Safety" or "Hills". Underneeth map controls like zoom, location, northfacing. 
- **Bottom-Center (Dynamic Island):** A floating pill showing core trip metrics (Time, Distance, micro-sparkline). Expandable into a larger solid bottom-sheet for detailed data tabs (Elevation, Safety stats).

## Taste dials (`design-taste-frontend`)

| Dial | 1–10 | Notes |
|------|------|--------|
| DESIGN_VARIANCE | 3 | product map shell: predictable, utility-first UI |
| MOTION_INTENSITY | 3 | restrained; Emil Kowalski spring physics for snappy micro-interactions |
| VISUAL_DENSITY | 7 | planner chrome denser than a landing page, but breathable via modular panels |

## Competitor refs

| App | Notes | Screenshot |
|-----|-------|------------|
| **Cross-app synthesis** | [`competitor_benchmarks/SYNTHESIS.md`](competitor_benchmarks/SYNTHESIS.md) | — |
| Google Maps | [`competitor_benchmarks/google_maps.md`](competitor_benchmarks/google_maps.md) | `google_maps.png` |
| Apple Maps | [`competitor_benchmarks/apple_maps.md`](competitor_benchmarks/apple_maps.md) | `apple_maps.png` |
| Beeline | [`competitor_benchmarks/beeline.md`](competitor_benchmarks/beeline.md) | `beeline.png` |

**Layout / strip-keep draft:** [`ARCHITECTURE_DIRECTION.md`](ARCHITECTURE_DIRECTION.md) (from brainstorming — not all decisions final).

## Logo

**Default mark:** [`logo_assets/logo_transparent_bg_noshadow.svg`](logo_assets/logo_transparent_bg_noshadow.svg) — see [`logo_assets/README.md`](logo_assets/README.md).

## Icons (when building)

Use **`lucide-react`** for UI icons. Best-guess mapping in [`ARCHITECTURE_DIRECTION.md`](ARCHITECTURE_DIRECTION.md); user will correct names as needed.
