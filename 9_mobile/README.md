# Tuned Cycling — mobile (`9_mobile`)

Expo / React Native app. **Primary product client** (full native UI rewrite of web v2 — not a WebView).

**Start the app (copy-paste):** [`startup.md`](startup.md) — you run emulator + `npm run android:device` yourself.  
**Working notes / handoff (detailed):** [`../0_documentation/tasks/MOBILE_WORKING_NOTES.md`](../0_documentation/tasks/MOBILE_WORKING_NOTES.md)  
**Android setup / troubleshooting:** [`../0_documentation/tasks/SETUP_ANDROID.md`](../0_documentation/tasks/SETUP_ANDROID.md)  
**Plan:** [`../0_documentation/tasks/MOBILE_RN_PLAN.md`](../0_documentation/tasks/MOBILE_RN_PLAN.md)  
**UI port waves:** [`../0_documentation/tasks/MOBILE_UI_PORT.md`](../0_documentation/tasks/MOBILE_UI_PORT.md)  
**Turn-by-turn:** [`../0_documentation/tasks/MAPLIBRE_BYOR_PLAN.md`](../0_documentation/tasks/MAPLIBRE_BYOR_PLAN.md) · background [`navigation_SKDs.md`](../0_documentation/tasks/navigation_SKDs.md)  
**Web port reference:** [`../5_frontend/src/v2/`](../5_frontend/src/v2/)  
**API:** same Flask as web (prod or local)

## Run (Android) — short form

Full steps: [`startup.md`](startup.md). After Mapbox (P2c), use the **dev build** (not Expo Go):

```powershell
# Terminal A — emulator
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
$env:Path = "$env:ANDROID_HOME\platform-tools;$env:ANDROID_HOME\emulator;$env:Path"
emulator -avd Pixel_9a -gpu swiftshader_indirect -no-snapshot-load

# Terminal B — after adb devices shows "device"
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
$env:Path = "$env:ANDROID_HOME\platform-tools;$env:JAVA_HOME\bin;$env:Path"
cd c:\London_Cycle_Maps\9_mobile
npm run android:device
```

Expect sign-in screen → after login, home with **Backend reachable** + profile list.

## Layout

| Path | Purpose |
|------|---------|
| `App.tsx` | Auth gate → `PlanMapScreen` or `AuthScreen` |
| `src/api/` | Flask client (`apiFetch`, route, geocode, santander) |
| `src/auth/` | SecureStore session + sign-in/up UI |
| `src/map/` | PlanMapScreen, overlays, hire stations, Mapbox |
| `src/ui/` | MapShell, RoutingCore, island, controls, pills |
| `src/navigation/` | Turn-by-turn: nav session + reroute, instruction banner, maneuver icons, controls |
| `src/lib/` | Coords, safe area helpers |
