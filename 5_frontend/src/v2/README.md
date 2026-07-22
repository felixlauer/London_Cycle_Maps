# v2 — Customer-facing frontend (Tuned Cycling)

Parallel UI under `5_frontend/src/v2/`. Legacy `src/App.js` remains for Test Mode / inspector.

**Docs:** protocol [`0_documentation/development_protocols/V2_FRONTEND_REMODEL.md`](../../../0_documentation/development_protocols/V2_FRONTEND_REMODEL.md) · working notes [`WORKING_NOTES_JUL2026.md`](../../../0_documentation/design/WORKING_NOTES_JUL2026.md) · checklist [`FUNCTIONALITY_CHECKLIST.md`](../../../0_documentation/design/FUNCTIONALITY_CHECKLIST.md) · APP [`APP_MAIN.md`](../../../0_documentation/APP_MAIN.md)

## Run

```powershell
cd c:\London_Cycle_Maps\5_frontend
npm start -- --v2
```

Or `REACT_APP_UI_VERSION=v2` in `.env`. Optional: `--day` / `--night` → `REACT_APP_FORCE_MODE`.

Default `npm start` still loads **legacy** `App.js`.

## Structure

```text
v2/
  App.jsx                 # Root state — waypoints, route, hire, overlays, island
  units.js                # metric / imperial formatting
  tailwind.css            # Tailwind layers (preflight OFF)
  hooks/useMediaQuery.js  # useIsMobile (≤767px)
  theme/resolveAppearance.js
  alerts/                 # Priority alert pill
  routing/                # Mode·bike·Santander, waypoints, depart, Get Route
  map/                    # PlanningMap, V2 overlays, geolocation, theme
  island/                 # Collapsed / expanded analysis + weather/
  shell/                  # MapShell, SidebarContext, zones/, sidebar/
  wizard/                 # PresetWizardShell (shared steps in src/wizard/)
  assets/                 # Logo + icons
```

Shared (imported from parent `src/`): `map/CycleMap.jsx`, `RouteLayers.jsx`, `auth/`, `api/flaskClient.js`, `wizard/*` steps, `components/santander/SantanderStationsLayer.jsx`, geocode.

## Zones

| Zone | Component |
|------|-----------|
| Top-left | `RoutingCoreZone` |
| Top-center | `AlertPillZone` |
| Top-right | `ProfileZone` → `ProfileSidebar` |
| Bottom-center | `DynamicIslandZone` |
| Bottom-right | `MapControlsZone` + `OverlayModeRail` |
| Mobile weather | `WeatherControlZone` (extremes only) |

## Design refs

- [`BRIEF.md`](../../../0_documentation/design/BRIEF.md)
- [`ARCHITECTURE_DIRECTION.md`](../../../0_documentation/design/ARCHITECTURE_DIRECTION.md)
- Skills: `design-taste-frontend`, `emil-design-eng`, `high-end-visual-design`
