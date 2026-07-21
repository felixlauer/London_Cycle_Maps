# UI architecture direction (draft)

**Source:** User [`brainstorming.md`](brainstorming.md) + filled [`BRIEF.md`](BRIEF.md).  
**Status:** Directional — many items are **options**, not decisions. User will specify each core element before build.

---

## Prime directive

| Layer | Treatment |
|-------|-----------|
| **Functional** | Sacred — Flask auth, `/route`, geocode, Mapbox, state hooks, routing flows |
| **Visual (JSX/CSS)** | Greenfield — discard current chrome structure |

---

## Screen zones (target layout)

```text
┌─────────────────────────────────────────────────────────────┐
│  [Routing panel TL]     [Comm pill TC]      [Profile TR]    │
│                                                             │
│                        MAP (Mapbox GL)                      │
│                                                             │
│              [Dynamic Island / analysis BC]                 │
│                                    [Overlay pill │ Map ctl] │
└─────────────────────────────────────────────────────────────┘
```

| Zone | Role | Status |
|------|------|--------|
| **Top-left** | Start/end/vias, Depart at, Get Route, mode + bike pills, Santander affordance | Direction locked |
| **Top-center** | Communication pill — routing status, errors, Santander copy, optional segment info | Direction locked |
| **Top-right** | Profile avatar/pill → **drawer** (settings, account, profile CRUD) | Direction locked |
| **Bottom-center** | Dynamic Island: time, distance, micro-sparkline; expand → bottom sheet tabs | Direction locked; chart types TBD |
| **Bottom-right** | Vertical overlay category pill + map controls (zoom, locate, north) | Direction locked; overlay UX detailed below |

**No** full-width top bar.

---

## Strip vs keep (function vs chrome)

### Keep (behaviour)

- Map click / search for start, end, vias  
- Get Route, prefetch, fastest vs optimized reveal  
- Depart at  
- Profile weights via **user mode** (presets + custom)  
- Bike type affects routing (cargo, e-bike, road, regular)  
- Santander hire flow (dock-to-dock) — logic only until re-specified  
- Overlay data on map (categories collapse to preset-driven sets)  
- Auth, Test Mode (dev), Flask proxies  

### Strip / replace (chrome only)

- Current top bar layout  
- Left **stats panel** (move to Dynamic Island / bottom sheet)  
- Profile menu housing **mode selection** (move to routing panel)  
- Current bottom-right overlay FAB/panel UX (replace with vertical pill + hover expand)  
- Leaflet-era styling; ad-hoc `ui.css` look (tokens replaced in rebuild)  

### Keep layout feel (user liked)

- Start/end + Depart at + Get Route **interaction layout** (can restyle, same flow)  
- **Floating pill** pattern for commands (Santander guide, warnings)  

---

## Mode & bike type (brainstorm — not all decided)

**Problem today:** User **mode** (presets/custom) lives in profile; **bike type** lives in profile weights. User switches mode more often than bike type.

**Direction:**

- **User mode** — quick selector in **top-left routing panel** (icon + label, dropdown).
- **Bike type** — second selector (4 types: cargo, e-bike, road, regular); defaults from mode but **overridable**.
- **Santander** — open options (brainstorm):
  - Toggle in routing row with wobble when it forces bike type change  
  - Inside bike dropdown as option or sub-toggle  
  - Third toggle separate from bike type  
  - **Decision deferred** — user will specify in element instructions  

**Mobile later:** pre-map mode/bike picker; **web:** inline in routing panel.

---

## Overlay selector (direction)

- **Not** free multi-toggle of every layer — tied to **preset/mode** hierarchies where possible.
- **UI:** Vertical pill (like Google Maps floor picker), icons only at rest.
- **Hover:** Horizontal **droplet / morphing expansion** from icon — reveals label (“Safety”, “Hills”, …). Proper names: contextual expand, tooltip rail, or morphing pill.
- **Categories (draft):** hill, safety, green, speed — each maps to bundled overlay types.
- **Expanded analysis** switching category can sync map overlays + chart tab (brainstorm).

**Open:** Overlays only in bottom-right vs only in expanded analysis — **leaning bottom-right** with optional sync in sheet.

---

## Dynamic Island / analysis (direction)

**Collapsed pill (bottom-center):**

- Large **time** + **distance**  
- Secondary grey line: delta vs fastest (subtle, not hero)  
- **Microchart** (pick one primary): elevation sparkline | segmented safety bar | vibe ring (see brainstorming)

**Expanded bottom sheet:**

- Beeline-like elevation profile for **Hills**  
- Category tabs (swipe L/R): Hills, Safety, Green, Speed — charts + metrics TBD  
- Full stats currently in left panel migrate here  

**Reject for v1:** Showing 3+ route alternatives like Google/Beeline cards.

---

## Route line & segment inspect (open)

- **Beeline:** coloured segments + **white stroke** on active route; grey alternate.  
- **Hover/click overlay segment:** show detail — either  
  - **A)** Top-center comm pill (unified messaging), or  
  - **B)** Small on-map pill attached to route (prettier, less unified)  
- **Decision deferred.**

---

## Profile drawer (direction)

**Top-right pill** → **sidebar drawer** (not centered modal).

**Contents (draft):**

- Account: email, change password, delete account  
- Profiles: list/edit **custom** profiles (quick mode picker stays in routing panel)  
- Settings (bottom): light/dark, future prefs  
- **Future slots:** notifications, units, language  

---

## Communication pill uses (top-center)

- Routing: “Calculating…”, errors, rate limits  
- Santander: “Select drop-off station”, “No bikes in area”  
- Live disruption / depart-at warnings  
- Optional: unified segment inspect copy (if not on-map pill)  
- **Motion:** subtle attention animation on errors (Emil-style springs, restrained)

---

## Icons (implementation default)

**Library:** [`lucide-react`](https://lucide-react.dev/) — install when build starts; best-guess icons until user corrects.

| Affordance | Lucide (draft) |
|------------|----------------|
| Start / end | `MapPin`, `Flag` |
| Via | `CircleDot` |
| Get Route | `Navigation` or `Route` |
| Swap start/end | `ArrowUpDown` |
| Depart at | `Clock` |
| User mode | `SlidersHorizontal` or `UserCog` |
| Bike types | `Bike`, `Zap`, `Package`, `Circle` |
| Santander | `Bike` + badge or custom |
| Overlays | `Shield`, `Mountain`, `Trees`, `Gauge` |
| Map zoom | `Plus`, `Minus` |
| Locate | `LocateFixed` |
| North | `Compass` |
| Profile | `UserCircle` |
| Layers/overlays | `Layers` |
| Expand analysis | `ChevronUp` |

---

## Logo

Default: [`logo_assets/logo_transparent_bg_noshadow.svg`](logo_assets/logo_transparent_bg_noshadow.svg)

---

## Next step (user-driven)

User will provide **detailed instructions per core UI element**. Agents read this doc + BRIEF + competitor folder; **no rebuild until those land.**
