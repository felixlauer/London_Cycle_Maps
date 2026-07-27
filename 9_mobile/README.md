# Tuned Cycling — mobile (`9_mobile`)

Expo / React Native app. **Primary product client** (full native UI rewrite of web v2 — not a WebView).

**Status:** Folder scaffold only. Run `create-expo-app` here when ready (see plan).

**Plan & software list:** [`../0_documentation/tasks/MOBILE_RN_PLAN.md`](../0_documentation/tasks/MOBILE_RN_PLAN.md)  
**Turn-by-turn / maneuvers:** [`../0_documentation/tasks/navigation_SKDs.md`](../0_documentation/tasks/navigation_SKDs.md)  
**Mapbox BYOR / phases:** [`../0_documentation/PRODUCTION_MOBILE_MAPBOX.md`](../0_documentation/PRODUCTION_MOBILE_MAPBOX.md)  
**Web port reference:** [`../5_frontend/src/v2/`](../5_frontend/src/v2/)  
**API:** [`../4_backend_engine/`](../4_backend_engine/) (unchanged)

## Layout

| Path | Purpose |
|------|---------|
| `app/` | Expo Router screens (after init) |
| `assets/` | Icons, splash |
| `src/api/` | Flask client |
| `src/auth/` | Session / secure storage |
| `src/map/` | Mapbox Maps RN + route layers |
| `src/navigation/` | Turn-by-turn / BYOR |
| `src/ui/` | Shells mimicking v2 |
| `src/lib/` | Pure helpers |

## First commands (when starting)

```powershell
cd c:\London_Cycle_Maps\9_mobile
# copy .env.example → .env and set EXPO_PUBLIC_API_BASE
npx create-expo-app@latest . --template tabs
npx expo run:android
```

Phone → local Flask: use your PC LAN IP, not `127.0.0.1`.
