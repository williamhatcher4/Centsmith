# Installer smoke test: installs the NSIS bundle silently, launches the bundled
# backend executable directly (bypassing the Tauri shell so runtime.json is not
# consumed before we can read it), probes /health, then uninstalls.
#
# Run from repo root after `tauri-action` has produced the NSIS installer at
# desktop\src-tauri\target\release\bundle\nsis\*.exe.

$ErrorActionPreference = 'Stop'

$RepoRoot = Resolve-Path "$PSScriptRoot\.."
$BundleDir = Join-Path $RepoRoot "desktop\src-tauri\target\release\bundle\nsis"

$installer = Get-ChildItem -Path $BundleDir -Filter "*.exe" -ErrorAction Stop | Select-Object -First 1
if (-not $installer) {
  throw "No NSIS installer found in $BundleDir"
}
Write-Host "Installer: $($installer.FullName)"

$installRoot = Join-Path $env:LOCALAPPDATA "Programs\Centsmith"
$runtimeFile = Join-Path $env:APPDATA "Centsmith\runtime.json"
$shellLog = Join-Path $env:APPDATA "Centsmith\shell.log"

# Clear any stale runtime metadata so we wait on this run's signal.
Remove-Item -ErrorAction SilentlyContinue $runtimeFile, $shellLog

# NSIS /S = silent install. /currentuser scope used by Tauri's default config
# places the install under %LOCALAPPDATA%\Programs.
Write-Host "Installing silently..."
$installProc = Start-Process -FilePath $installer.FullName -ArgumentList "/S" -Wait -PassThru
if ($installProc.ExitCode -ne 0) {
  throw "Installer exited with code $($installProc.ExitCode)"
}

$installedBackend = Get-ChildItem -Path $installRoot -Filter "centsmith-backend.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $installedBackend) {
  throw "centsmith-backend.exe not found under $installRoot after install"
}
Write-Host "Bundled backend: $($installedBackend.FullName)"

# Launch the backend directly so the Tauri shell does not race us to read
# (and then delete) runtime.json.
$backendProc = Start-Process -FilePath $installedBackend.FullName -PassThru -WindowStyle Hidden
Write-Host "Backend pid: $($backendProc.Id)"

try {
  $deadline = (Get-Date).AddSeconds(30)
  while ((Get-Date) -lt $deadline -and -not (Test-Path $runtimeFile)) {
    Start-Sleep -Milliseconds 200
  }
  if (-not (Test-Path $runtimeFile)) {
    throw "runtime.json was not written within 30s"
  }

  $metadata = Get-Content -Raw -LiteralPath $runtimeFile | ConvertFrom-Json
  $port = [int]$metadata.port
  Write-Host "Backend reports port $port"

  $healthDeadline = (Get-Date).AddSeconds(15)
  $healthy = $false
  while ((Get-Date) -lt $healthDeadline) {
    try {
      $resp = Invoke-RestMethod -Uri "http://127.0.0.1:$port/health" -TimeoutSec 5
      if ($resp.status -eq "ok") {
        $healthy = $true
        break
      }
    } catch {
      Start-Sleep -Milliseconds 500
    }
  }
  if (-not $healthy) {
    throw "Backend /health did not return status=ok on port $port"
  }
  Write-Host "Health probe OK"
} finally {
  Write-Host "Stopping backend pid $($backendProc.Id)"
  Stop-Process -Id $backendProc.Id -Force -ErrorAction SilentlyContinue
}

# Find and run the uninstaller. Tauri's NSIS template installs Uninstall.exe
# at the install root.
$uninstaller = Join-Path $installRoot "uninstall.exe"
if (-not (Test-Path $uninstaller)) {
  $uninstaller = (Get-ChildItem -Path $installRoot -Filter "uninstall*.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1)?.FullName
}
if (-not $uninstaller) {
  Write-Warning "Uninstaller not found under $installRoot — install verified but uninstall not exercised."
  exit 0
}
Write-Host "Uninstalling silently..."
$uninstProc = Start-Process -FilePath $uninstaller -ArgumentList "/S" -Wait -PassThru
if ($uninstProc.ExitCode -ne 0) {
  throw "Uninstaller exited with code $($uninstProc.ExitCode)"
}
Write-Host "Installer smoke test passed."
