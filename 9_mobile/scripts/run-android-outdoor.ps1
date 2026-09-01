# Outdoor / ride smoke test - installs a release APK with JS embedded.
# No Metro/laptop needed after install. Real GPS (no route simulation).
#
# Usage (USB once to install):
#   npm run android:outdoor
#
# Then unplug, leave Wi-Fi, open Tuned from the app drawer (mobile data + prod API).

$ErrorActionPreference = "Stop"

$env:ANDROID_HOME = if ($env:ANDROID_HOME) { $env:ANDROID_HOME } else { "$env:LOCALAPPDATA\Android\Sdk" }
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
if (-not $env:JAVA_HOME) {
  $env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
}
$env:Path = "$env:ANDROID_HOME\platform-tools;$env:ANDROID_HOME\emulator;$env:JAVA_HOME\bin;$env:Path"
$env:JAVA_TOOL_OPTIONS = "--enable-native-access=ALL-UNNAMED"
$env:GRADLE_USER_HOME = Join-Path $env:USERPROFILE ".gradle"

# Bake real-GPS into the JS bundle (EXPO_PUBLIC_* is inlined at build time).
$env:EXPO_PUBLIC_NAV_SIMULATE = "0"

# Ride feedback test build: set to "1" so this phone's reports steer only your
# own routes and never enter the global crowd overlay. "0" = normal rider build.
$env:EXPO_PUBLIC_RIDE_REPORT_PERSONAL_ONLY = "0"

Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "Building/installing Tuned release (embedded JS, real GPS)..." -ForegroundColor Cyan
Write-Host "Phone must be connected via USB (or wireless adb) for this install step only." -ForegroundColor Yellow

# --no-bundler: do NOT open Metro deep-link (that dies when you leave Wi-Fi).
npx expo run:android --variant release --no-bundler

Write-Host "Launching installed app (launcher Activity, not Metro)..." -ForegroundColor Cyan
adb shell am start -n "online.tunedcycling.app/.MainActivity" | Out-Null

Write-Host ""
Write-Host "Install done. Unplug the phone, open Tuned from the app icon if needed." -ForegroundColor Green
Write-Host "No laptop required on the ride. API must serve directions on navigate=1." -ForegroundColor Green
