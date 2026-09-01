# Mobile app startup (Android / Expo)

Same role as `[../0_documentation/startup.md](../0_documentation/startup.md)`, but for `9_mobile`.  
Plan / first-time setup: `[../0_documentation/tasks/SETUP_ANDROID.md](../0_documentation/tasks/SETUP_ANDROID.md)` · `[../0_documentation/tasks/MOBILE_RN_PLAN.md](../0_documentation/tasks/MOBILE_RN_PLAN.md)`  
**Handoff / what’s done:** `[../0_documentation/tasks/MOBILE_WORKING_NOTES.md](../0_documentation/tasks/MOBILE_WORKING_NOTES.md)` · MapLibre TBT: `[../0_documentation/tasks/MAPLIBRE_BYOR_PLAN.md](../0_documentation/tasks/MAPLIBRE_BYOR_PLAN.md)`

Use **two PowerShell terminals** for desk work (like Flask + web). Do **not** set `$env:CI=1` — that disables Fast Refresh.

---

## Which install do I need?

| Goal | Command | Cable / laptop on the ride? | GPS |
|------|---------|-----------------------------|-----|
| **Desk / plugged in** (dev, Fast Refresh, optional simulate) | `npm run android:device` + Metro | Stay near PC (USB or same Wi‑Fi) | Real GPS, **or** set `EXPO_PUBLIC_NAV_SIMULATE=1` for replay |
| **Outdoor smoke** (cycle away, no laptop) | `npm run android:outdoor` once at home | Install once over USB, then **unplug** — open Tuned from the **app icon** (not a Metro QR) | **Real GPS** (simulate forced off) |

**MapLibre Navigation:** the **Navigate** circle in the island (slot 4, appears once location services are on) turns the planning screen into navigation in place — a MapLibre map + nav engine behind Tuned's own banner, island and controls. API must return `directions` on `/route?navigate=1` (not only `navigation`). Module: `modules/tuned-maplibre-nav/`; chrome: `src/navigation/`.

**~8 min outdoor build:** Normal the first time (full release + embed JS bundle). Debug `android:device` reuses cache and is much faster. Later outdoor rebuilds are usually shorter.

**Simulate?** Outdoor APK forces `EXPO_PUBLIC_NAV_SIMULATE=0` → real GPS only. Desk: leave unset for real GPS, or set `EXPO_PUBLIC_NAV_SIMULATE=1` for fake replay on emulator.

**Navigate puck:** GPS position, never the drawn line. Fixes go to the arrow *before* the engine may project them for turn progress. Between fixes the LocationComponent interpolates (SDK default 1.1×), so 1 Hz GPS still looks like motion. Stopped: map and chevron follow the compass at sensor rate (`TRACKING_COMPASS`). Moving above 3 m/s: GPS course (`TRACKING_GPS`). Hysteresis holds the previous source between 1.2–3 m/s.

**Voice:** each step gets up to four cues — entry ("Continue for 1.2 kilometres"), ~400 m, ~150 m and the turn itself — all naming the maneuver *ahead*, with the distance spoken in words. Two maneuvers within 120 m are chained ("…, then turn right onto Mill Road") and the second is not repeated. Schedule lives in `4_backend_engine/maneuvers/voice.py`; `python -m unittest test_maneuvers.py` covers it offline. Units follow the sidebar preference via `voice_units`.

**Reroute:** deviation is judged in `RouteDeviationTracker.kt` from the same GPS fix as the puck, not by the SDK: beyond **22 m** starts a candidate, **2.5 s** still out confirms it, beyond **50 m** confirms at once, and back inside **12 m** for **1 s** cancels. After a successful replan there is a **4 s** cooldown (8 s after a failed one). While still off the line, native re-emits every 5 s so JS keeps replanning — `entered` only fires once per episode, which is why a deliberate wrong-street ride used to get stuck. While replanning the banner says "Reconnecting…", maneuver cues are silenced, the line greys, TTS says **"Rerouting"** then immediately the new next-turn (Google / Apple / Waze), and Flask replans from the live position. Rejoining the line before it lands (1 s inside 12 m) abandons the replan. Native + JS changes need `npm run android:outdoor`.

**Cold start:** if location was granted on an earlier run the app locates silently on launch, centres on you and soft-fills the start field. Outside Greater London it stays on the London default without a warning.

**JDK 24+ / AGP:** if Gradle fails with `WARNING: A restricted method in java.lang.System has been called`:

```powershell
$env:JAVA_TOOL_OPTIONS = '--enable-native-access=ALL-UNNAMED'
$env:GRADLE_USER_HOME = "$env:USERPROFILE\.gradle"
```

---

### A — Desk (plugged in / Wi‑Fi)

```powershell
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
$env:Path = "$env:ANDROID_HOME\platform-tools;$env:ANDROID_HOME\emulator;$env:JAVA_HOME\bin;$env:Path"
$env:JAVA_TOOL_OPTIONS = '--enable-native-access=ALL-UNNAMED'

cd c:\London_Cycle_Maps\9_mobile
npm run android:device
```

- Needs Metro (`expo start` / the run script starts it). Phone on USB or same Wi‑Fi as the PC.
- For **fake GPS along the route** on desk/emulator, add to `.env` then restart Metro:

```env
EXPO_PUBLIC_NAV_SIMULATE=1
```

- Default without that flag = **real GPS** even in debug.

---

### B — Outdoor smoke (leave the house)

Phone needs **mobile data** and an API that serves `directions` on `navigate=1` (usually prod).

```powershell
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
$env:Path = "$env:ANDROID_HOME\platform-tools;$env:JAVA_HOME\bin;$env:Path"

cd c:\London_Cycle_Maps\9_mobile
# USB plugged for install only:
npm run android:outdoor
```

That builds a **release** APK with the JS **embedded** and `EXPO_PUBLIC_NAV_SIMULATE=0`. After install:

1. Unplug the phone.  
2. Leave laptop Wi‑Fi — no Metro, no adb required.  
3. Open **Tuned** like a normal app → plan → Navigate.  
4. Allow location if prompted.

Rebuild outdoor after JS or native nav changes. Desktop `android:device` and outdoor release can both sit on the phone; outdoor is the one to use for rides.

---



## 0. One-time checks

- `9_mobile/.env` exists (copy from `.env.example` if missing).
- Default API (no local Flask needed):

```env
EXPO_PUBLIC_API_BASE=https://app.tunedcycling.online/api
```

- Mapbox public token (same `pk.` as web). Sync from frontend:

```powershell
powershell -File c:\London_Cycle_Maps\9_mobile\scripts\sync-mapbox-token.ps1
```

Or paste into `.env`:

```env
EXPO_PUBLIC_MAPBOX_TOKEN=pk.your_token_here
```

- If `adb` / `emulator` are not found in a **new** terminal, run this once per session:

```powershell
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
$env:Path = "$env:ANDROID_HOME\platform-tools;$env:ANDROID_HOME\emulator;$env:JAVA_HOME\bin;$env:Path"

adb version
emulator -list-avds
```

You should see AVDs such as `Pixel_9` / `Pixel_9a`.

---



## 1. Terminal A — Android emulator

**This PC:** hardware GPU often fails; use software rendering.

```powershell
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
$env:Path = "$env:ANDROID_HOME\platform-tools;$env:ANDROID_HOME\emulator;$env:Path"

emulator -avd Pixel_9a -gpu swiftshader_indirect -no-snapshot-load
```

Leave this window open. Wait until the emulator home screen appears (can take 1–2 minutes; System UI glitches are emulator noise, not Tuned).

```powershell
adb devices
```

Expect `emulator-5554    device` (not `offline`).

### Why not the RTX?

This PC is **dual-GPU**: AMD Radeon (integrated) + **NVIDIA GeForce RTX 3050 Laptop**. When we first launched the AVD, the emulator bound to **AMD**, then OpenGL ES init failed, so we fell back to **swiftshader** (CPU software rendering). Windows laptop Optimus setups often do this — the Android emulator is bad at reliably using the discrete RTX.

**Optional (try later; not required if you use a phone):**

1. Windows **Settings → System → Display → Graphics** → add
  `%LOCALAPPDATA%\Android\Sdk\emulator\qemu-system-x86_64.exe`  
   (and/or `emulator.exe`) → **High performance** (NVIDIA).
2. NVIDIA Control Panel → Manage 3D settings → Program Settings → same EXE → **High-performance NVIDIA**.
3. Cold-boot the AVD with host GPU instead of swiftshader:

```powershell
emulator -avd Pixel_9a -gpu host -no-snapshot-load
```

If it crashes or goes black again, stick with swiftshader or (better) a **physical phone**.

---



## 1b. Physical Android phone (recommended for Mapbox)

Much smoother maps/GPS than the soft-GPU emulator. Same Tuned **dev client**; install over USB.

### Risks (read once)


| Risk                        | Reality                                                                                                                                   | Mitigation                                                                                                                                          |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| **USB debugging**           | Lets this PC install apps / read logs while connected. Anyone with physical access + unlocked phone could abuse it if debugging stays on. | Turn **USB debugging off** when not developing. Don’t accept “allow debugging” on untrusted PCs.                                                    |
| **Debug / “unknown” app**   | You’re installing a **dev build** of Tuned (not Play Store). It can talk to your prod API with your account.                              | Only install builds you produce from this repo. Sign out when done testing.                                                                         |
| **Mapbox token in the app** | Public `pk.` token is inside the APK (normal for Mapbox). URL restrictions often **don’t** apply to the mobile SDK.                       | Use a **separate mobile** `pk.` **token** (no URL allowlist). Don’t put `sk.` secret tokens in the app. Rotate the mobile token if it leaks widely. |
| **Prod API**                | Phone hits `https://app.tunedcycling.online/api` with your real login.                                                                    | Fine for you as the developer; don’t share the APK widely.                                                                                          |
| **Data / battery**          | Map tiles + Metro over Wi‑Fi use data/battery.                                                                                            | Prefer Wi‑Fi; disconnect USB when idle.                                                                                                             |
| **Bricking**                | Normal USB debug + sideload **will not brick** the phone.                                                                                 | You’re not unlocking bootloader or flashing firmware.                                                                                               |
| **Work/school phone MDM**   | Some policies block USB install.                                                                                                          | Use a personal phone if install is blocked.                                                                                                         |


**Bottom line:** Safe for day-to-day solo dev if you only enable debugging while working and use your own Mapbox mobile token.

### Phone setup (one-time)

1. **Cable:** use a data USB-C cable (charge-only cables won’t work).
2. On the phone: **Settings → About phone → tap Build number 7 times** → unlock Developer options.
3. **Settings → System → Developer options** (path varies by OEM):
  - **USB debugging** → ON  
  - Optional: **Install via USB** / **USB debugging (Security settings)** if your phone has it (Xiaomi/Huawei often need this)
4. Plug into the PC. On the phone, accept **Allow USB debugging?** → tick **Always allow from this computer** → OK.
5. In PowerShell:

```powershell
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
$env:Path = "$env:ANDROID_HOME\platform-tools;$env:Path"
adb devices
```

You want a line like `XXXXXXXX    device` (not `unauthorized` or `offline`).

- `unauthorized`**:** unlock phone and accept the RSA prompt; `adb kill-server` then `adb devices` again.  
- **Empty list:** try another cable/port; install OEM USB driver if Windows shows a yellow bang in Device Manager.  
- **Emulator also listed:** unplug isn’t required — Expo installs to a device you select, or shut down the emulator so only the phone remains.



### Install Tuned on the phone

**Close or ignore the emulator.** Prefer only the phone in `adb devices`.

```powershell
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
$env:Path = "$env:ANDROID_HOME\platform-tools;$env:ANDROID_HOME\emulator;$env:JAVA_HOME\bin;$env:Path"

cd c:\London_Cycle_Maps\9_mobile
npm run android:device
```

Gradle may take a few minutes again the first time it targets the phone’s CPU arch (`arm64-v8a`). After that it’s faster.

Metro must reach the phone:

- Phone and PC on the **same Wi‑Fi** (or USB with Expo’s defaults).  
- Windows Firewall: allow Node when prompted.  
- If the app opens but can’t load JS over USB, forward Metro once per session: `adb reverse tcp:8081 tcp:8081` (then reopen the app).  
- Still stuck: in Metro terminal note the `exp://…` / LAN IP; on awkward LANs use `npx expo start --dev-client --tunnel` (slower).

**Success:** Tuned opens on the phone → sign in → map should pan/zoom far more smoothly than the emulator.

### Daily phone loop

1. USB debugging on, cable plugged (or wireless debugging after you’ve paired once).
2. `adb devices` shows the phone.
3. `cd c:\London_Cycle_Maps\9_mobile` → `npm run android:device` **or**, if the app is already installed:
  `npx expo start --dev-client` then open the Tuned app on the phone.
4. Edit JS → save → Fast Refresh on the phone.
5. When finished: unplug, turn **USB debugging OFF**.



### Local Flask from the phone

Emulator uses `10.0.2.2`. A **real phone cannot**. Use your PC’s LAN IP:

```env
EXPO_PUBLIC_API_BASE=http://192.168.x.x:5000
```

Flask must listen on `0.0.0.0`, and the phone must be on the same Wi‑Fi. Restart Metro after changing `.env`. Prod API needs no change.

### Wireless debugging (optional, Android 11+)

Developer options → **Wireless debugging** → pair with pairing code → `adb pair IP:PORT` then `adb connect IP:PORT`. Same `npm run android:device` once connected. Still enable only while developing.

## 2. Terminal B — native app (Mapbox / P2c)

First build after installing Mapbox is **slow** (several minutes). Later launches are faster.

```powershell
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
$env:Path = "$env:ANDROID_HOME\platform-tools;$env:ANDROID_HOME\emulator;$env:JAVA_HOME\bin;$env:Path"

cd c:\London_Cycle_Maps\9_mobile
npm run android:device
```

This runs `expo run:android`: generates `android/`, compiles, installs the **Tuned** dev client on the emulator, starts Metro.

**Do not use Expo Go** for the map — it will crash or fail to load `@rnmapbox/maps`.

**Success (P2c):**

1. Sign in
2. London street map
3. Tap map → set **start** (green) → tap → set **end** (pink) → route draws (pink = profile, grey = fastest)
4. Or use **Get Route** after both points are set

JS-only edits still Fast Refresh. Changing native plugins / `app.config.js` requires another `npm run android:device`.

If Metro shows **Unable to resolve … RNMBXSnowNativeComponent** (or other `specs/RNMBX`*), stop Metro and restart with a clean cache:

```powershell
cd c:\London_Cycle_Maps\9_mobile
npx expo start --dev-client --clear
```

Then reopen the Tuned **dev client** app on the emulator (not Expo Go). `metro.config.js` is set up so `@rnmapbox/maps` resolves correctly.

If **Gradle** fails with `Unresolved reference 'DistanceUnits'` / `lineElevationGroundScale` on `:rnmapbox_maps:compileDebugKotlin`, the native Mapbox SDK pin is too old. Confirm `android/gradle.properties` has `expoRNMapboxMapsVersion=11.23.1` (same as `app.config.js`), then rebuild. After changing that version, prefer:

```powershell
npx expo prebuild --platform android --clean
npm run android:device
```

---



## 3. Optional — local Flask instead of prod

**Emulator → host PC loopback** is `10.0.2.2`, not `127.0.0.1`.

1. Start Flask (`[../0_documentation/startup.md](../0_documentation/startup.md)`):

```powershell
cd c:\London_Cycle_Maps\4_backend_engine
python app.py
```

1. In `9_mobile/.env`:

```env
EXPO_PUBLIC_API_BASE=http://10.0.2.2:5000
```

1. Restart Metro / rebuild so env is picked up.

**Physical phone:** use your PC LAN IP, e.g. `http://192.168.1.42:5000`, Flask on `0.0.0.0`.

---



## 4. Stop / restart cleanly


| Stop                            | How                                                                   |
| ------------------------------- | --------------------------------------------------------------------- |
| App / Metro                     | Terminal B: `Ctrl+C`                                                  |
| Emulator                        | Close the emulator window                                             |
| Stale JS bundle                 | In Metro terminal press `r`, or `npx expo start --dev-client --clear` |
| Native / Mapbox / plugin change | `npm run android:device` again                                        |


---



## 5. Copy-paste daily (prod API + map)

**Terminal A**

```powershell
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
$env:Path = "$env:ANDROID_HOME\platform-tools;$env:ANDROID_HOME\emulator;$env:Path"
emulator -avd Pixel_9a -gpu swiftshader_indirect -no-snapshot-load
```

**Terminal B** (after `adb devices` shows `device`)

```powershell
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
$env:Path = "$env:ANDROID_HOME\platform-tools;$env:ANDROID_HOME\emulator;$env:JAVA_HOME\bin;$env:Path"

cd c:\London_Cycle_Maps\9_mobile
npm run android:device
```

