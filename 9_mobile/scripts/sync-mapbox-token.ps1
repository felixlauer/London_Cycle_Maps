# Sync Mapbox public token from web frontend into mobile .env
# Usage (from repo root or 9_mobile):
#   powershell -File 9_mobile/scripts/sync-mapbox-token.ps1

$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not (Test-Path (Join-Path $root '5_frontend'))) {
  $root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
}
$feEnv = Join-Path $root '5_frontend\.env'
$mobileEnv = Join-Path $root '9_mobile\.env'

if (-not (Test-Path $feEnv)) { throw "Missing $feEnv — set REACT_APP_MAPBOX_TOKEN there first." }

$fe = Get-Content $feEnv -Raw
if ($fe -notmatch 'REACT_APP_MAPBOX_TOKEN=(pk\.[^\r\n]+)') {
  throw 'REACT_APP_MAPBOX_TOKEN (pk.…) not found in 5_frontend/.env'
}
$token = $Matches[1].Trim()

if (-not (Test-Path $mobileEnv)) {
  Copy-Item (Join-Path $root '9_mobile\.env.example') $mobileEnv
}

$content = Get-Content $mobileEnv -Raw
if ($content -match 'EXPO_PUBLIC_MAPBOX_TOKEN=') {
  $content = $content -replace 'EXPO_PUBLIC_MAPBOX_TOKEN=.*', "EXPO_PUBLIC_MAPBOX_TOKEN=$token"
} else {
  $content = $content.TrimEnd() + "`r`nEXPO_PUBLIC_MAPBOX_TOKEN=$token`r`n"
}
[System.IO.File]::WriteAllText($mobileEnv, $content.TrimEnd() + "`r`n", (New-Object System.Text.UTF8Encoding $false))
Write-Host "Updated 9_mobile/.env EXPO_PUBLIC_MAPBOX_TOKEN (len=$($token.Length))"
