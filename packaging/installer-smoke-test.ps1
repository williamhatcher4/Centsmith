# Installer smoke test: installs the NSIS bundle silently, launches the bundled
# backend executable directly (bypassing the Tauri shell so runtime.json is not
# consumed before we can read it), probes /health, then uninstalls.
#
# Run from repo root after `tauri-action` has produced the NSIS installer at
# desktop\src-tauri\target\release\bundle\nsis\*.exe.

$ErrorActionPreference = 'Stop'

$RepoRoot = Resolve-Path "$PSScriptRoot\.."
$BundleDir = Join-Path $RepoRoot "desktop\src-tauri\target\release\bundle\nsis"
. (Join-Path $PSScriptRoot "installer-smoke-lib.ps1")

$installer = Get-ChildItem -Path $BundleDir -Filter "*.exe" -ErrorAction Stop | Select-Object -First 1
if (-not $installer) {
  throw "No NSIS installer found in $BundleDir"
}
Write-Host "Installer: $($installer.FullName)"

$runtimeFile = Join-Path $env:APPDATA "Centsmith\runtime.json"
$shellLog = Join-Path $env:APPDATA "Centsmith\shell.log"

function Find-InstalledBackend {
  param([string[]]$InstallRoots)

  foreach ($root in $InstallRoots) {
    if (-not (Test-Path -LiteralPath $root)) {
      Write-Host "Install root candidate not found: $root"
      continue
    }
    Write-Host "Searching install root: $root"
    $backend = Get-ChildItem -Path $root -Filter "centsmith-backend.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($backend) {
      return $backend
    }
  }

  return $null
}

function Write-InstallDiagnostics {
  param([string[]]$InstallRoots)

  Write-Host "Install root candidates checked:"
  foreach ($root in $InstallRoots) {
    Write-Host "  $root exists=$(Test-Path -LiteralPath $root)"
  }

  $programFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
  foreach ($parent in @(
      $env:LOCALAPPDATA,
      (Join-Path $env:LOCALAPPDATA "Programs"),
      $env:ProgramFiles,
      $programFilesX86
    )) {
    if ([string]::IsNullOrWhiteSpace($parent) -or -not (Test-Path -LiteralPath $parent)) {
      continue
    }
    Write-Host "Centsmith-like entries under ${parent}:"
    Get-ChildItem -LiteralPath $parent -Directory -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -like "*Centsmith*" } |
      ForEach-Object { Write-Host "  $($_.FullName)" }
  }
}

# Clear any stale runtime metadata so we wait on this run's signal.
Remove-Item -ErrorAction SilentlyContinue $runtimeFile, $shellLog

# NSIS /S = silent install. /currentuser keeps the CI install under the runner
# profile when the installer supports per-user mode; discovery below still
# handles per-machine fallbacks.
Write-Host "Installing silently..."
$installProc = Start-Process -FilePath $installer.FullName -ArgumentList "/S", "/currentuser" -Wait -PassThru
if ($installProc.ExitCode -ne 0) {
  throw "Installer exited with code $($installProc.ExitCode)"
}

$installRoots = @(Get-CentsmithInstallRoots)
$installedBackend = Find-InstalledBackend -InstallRoots $installRoots
if (-not $installedBackend) {
  Write-InstallDiagnostics -InstallRoots $installRoots
  throw "centsmith-backend.exe not found after install"
}
Write-Host "Bundled backend: $($installedBackend.FullName)"
$installRoot = $installRoots |
  Where-Object { $installedBackend.FullName.StartsWith($_, [System.StringComparison]::OrdinalIgnoreCase) } |
  Sort-Object Length -Descending |
  Select-Object -First 1

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
      $resp = Invoke-RestMethod -Uri "http://127.0.0.1:${port}/health" -TimeoutSec 5
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
$uninstaller = $null
if ($installRoot) {
  $candidate = Join-Path $installRoot "uninstall.exe"
  if (Test-Path -LiteralPath $candidate) {
    $uninstaller = $candidate
  }
}
if (-not $uninstaller -and $installRoot) {
  $uninstallerMatch = Get-ChildItem -Path $installRoot -Filter "uninstall*.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($uninstallerMatch) {
    $uninstaller = $uninstallerMatch.FullName
  }
}
if (-not $uninstaller) {
  Write-Warning "Uninstaller not found after install verified; uninstall not exercised."
  exit 0
}
Write-Host "Uninstalling silently..."
$uninstProc = Start-Process -FilePath $uninstaller -ArgumentList "/S" -Wait -PassThru
if ($uninstProc.ExitCode -ne 0) {
  throw "Uninstaller exited with code $($uninstProc.ExitCode)"
}
Write-Host "Installer smoke test passed."
