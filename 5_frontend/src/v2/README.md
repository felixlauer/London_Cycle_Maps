# v2 — Visual rebuild (parallel frontend)

Legacy app remains at `src/App.js`. This folder is the **greenfield UI shell**; shared infrastructure is imported from parent `src/`:

- `map/CycleMap.jsx` — Mapbox GL (until v2 owns a thinner wrapper)
- `api/flaskClient.js`, `auth/`, `mapboxGeocoding.js`, etc. — reuse as logic is ported

## Run

```powershell
cd c:\London_Cycle_Maps\5_frontend
npm start -- --v2
```

Or set `REACT_APP_UI_VERSION=v2` in `.env`.

Default `npm start` still loads **legacy** `App.js`.

## Structure

```text
v2/
  App.jsx                 # v2 root — map + shell only (for now)
  README.md
  map/
    PlanningMap.jsx       # Bare CycleMap wrapper (no routes/markers)
    theme.js              # Light/dark theme tokens for map
  shell/
    MapShell.jsx          # Full-viewport layout over map
    shell.css             # Design tokens + zone positioning
    zones/
      RoutingCoreZone.jsx   # Top-left
      ProfileZone.jsx       # Top-right
      AlertPillZone.jsx     # Top-center
      DynamicIslandZone.jsx # Bottom-center
```

## Checklist

Track every legacy feature: [`0_documentation/design/FUNCTIONALITY_CHECKLIST.md`](../../../0_documentation/design/FUNCTIONALITY_CHECKLIST.md)

## Design refs

- [`0_documentation/design/BRIEF.md`](../../../0_documentation/design/BRIEF.md)
- [`0_documentation/design/ARCHITECTURE_DIRECTION.md`](../../../0_documentation/design/ARCHITECTURE_DIRECTION.md)
