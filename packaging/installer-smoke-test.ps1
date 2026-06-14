# Installer smoke test.
#
# Phase 1 (unchanged): installs the NSIS bundle silently, launches the bundled
# backend executable *directly* (bypassing the Tauri shell so runtime.json is not
# consumed before we can read it), probes /health.
#
# Phase 2 (P5.1): launches the installed Tauri shell exe -- the chain users
# actually run -- follows its shell.log breadcrumbs (navigate thread -> runtime
# metadata -> port open -> navigate), health-probes the shell-spawned backend on
# the port it reports, then force-kills the shell (the Task-Manager-style kill
# that bypasses RunEvent::ExitRequested) and proves the Windows Job Object tears
# the backend down within 10s. Then uninstalls.
#
# Run from repo root after `tauri-action` has produced the NSIS installer at
# desktop\src-tauri\target\release\bundle\nsis\*.exe.

[CmdletBinding()]
param(
  # Gate the "navigate() succeeded" assertion in phase 2. WebView2 window
  # creation is expected to work on windows-latest (interactive session, runtime
  # preinstalled); if a release runner proves otherwise, pass
  # -RequireNavigation:$false from release.yml -- steps 1-5 minus the navigate
  # line still cover spawn/handoff/port/teardown.
  [bool]$RequireNavigation = $true
)

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

# ---------------------------------------------------------------------------
# Phase 2 (P5.1): exercise the real shell-launch chain.
# ---------------------------------------------------------------------------
Write-Host "`n=== Phase 2: shell-launch chain ==="
$shellProc = $null
try {
  # 1. Quiesce phase 1: wait until the direct-launched backend is fully gone,
  #    then clear its breadcrumbs so phase 2 observes only its own.
  if (-not (Wait-ProcessGone -Name "centsmith-backend" -TimeoutSeconds 10)) {
    throw "Phase 1 backend did not exit within 10s; cannot start phase 2 cleanly."
  }
  Remove-Item -ErrorAction SilentlyContinue $runtimeFile, $shellLog

  # 2. Launch the installed Tauri shell exe.
  $shellExe = Find-CentsmithShellExe -InstallRoots $installRoots
  if (-not $shellExe) {
    throw "Installed Centsmith shell exe not found under: $($installRoots -join ', ')"
  }
  Write-Host "Shell exe: $($shellExe.FullName)"
  $shellProc = Start-Process -FilePath $shellExe.FullName -PassThru
  Write-Host "Shell pid: $($shellProc.Id)"

  # 3. Follow the shell.log breadcrumbs in order (debug_log writes these).
  $startCrumb = Wait-ShellLogLine -Path $shellLog -Pattern 'navigate thread started' -TimeoutSeconds 60
  if (-not $startCrumb) {
    throw "shell.log did not record 'navigate thread started' within 60s."
  }
  $metaCrumb = Wait-ShellLogLine -Path $shellLog -Pattern 'read runtime metadata for port \d+' -TimeoutSeconds 60
  if (-not $metaCrumb) {
    throw "shell.log did not record 'read runtime metadata for port N' within 60s."
  }
  $portCrumb = Wait-ShellLogLine -Path $shellLog -Pattern 'port \d+ is open' -TimeoutSeconds 60
  if (-not $portCrumb) {
    throw "shell.log did not record 'port N is open' within 60s."
  }
  $shellPort = Get-PortFromShellLog -LogText $portCrumb
  if (-not $shellPort) {
    throw "Could not extract the port from shell.log line: $portCrumb"
  }
  Write-Host "Shell-spawned backend reports port $shellPort"

  if ($RequireNavigation) {
    $navCrumb = Wait-ShellLogLine -Path $shellLog -Pattern 'navigate\(\) succeeded' -TimeoutSeconds 60
    if (-not $navCrumb) {
      throw "shell.log did not record 'navigate() succeeded' within 60s (pass -RequireNavigation:`$false if WebView2 is unavailable on this runner)."
    }
    Write-Host "Webview navigate() succeeded"
  } else {
    Write-Host "Navigation assertion skipped (-RequireNavigation:`$false)"
  }

  # 4. Probe the shell-spawned backend: proves resolve -> spawn -> handoff.
  $healthDeadline = (Get-Date).AddSeconds(15)
  $shellHealthy = $false
  while ((Get-Date) -lt $healthDeadline) {
    try {
      $resp = Invoke-RestMethod -Uri "http://127.0.0.1:${shellPort}/health" -TimeoutSec 5
      if ($resp.status -eq "ok") {
        $shellHealthy = $true
        break
      }
    } catch {
      Start-Sleep -Milliseconds 500
    }
  }
  if (-not $shellHealthy) {
    throw "Shell-spawned backend /health did not return status=ok on port $shellPort"
  }
  Write-Host "Shell-spawned backend health probe OK"

  # 5. Force-kill the shell (Task-Manager-style; bypasses ExitRequested) and
  #    prove the Job Object kills the backend. The only automated check of
  #    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, whose failure mode is orphaned
  #    backends holding DLL locks that brick the NSIS updater.
  Write-Host "Force-killing shell pid $($shellProc.Id)"
  Stop-Process -Id $shellProc.Id -Force -ErrorAction SilentlyContinue
  if (-not (Wait-ProcessGone -Name "centsmith-backend" -TimeoutSeconds 10)) {
    throw "Backend still running 10s after the shell was force-killed -- Job Object teardown FAILED."
  }
  Write-Host "Job Object teardown OK: backend gone after shell kill"
  $shellProc = $null
  Write-Host "Phase 2 passed."
} catch {
  # shell.log is the only diagnostic artifact -- echo it before failing.
  Write-Host "`n--- Phase 2 FAILED; shell.log contents: ---"
  if (Test-Path -LiteralPath $shellLog) {
    Get-Content -LiteralPath $shellLog | ForEach-Object { Write-Host "  $_" }
  } else {
    Write-Host "  (shell.log not found at $shellLog)"
  }
  throw
} finally {
  if ($shellProc) {
    Stop-Process -Id $shellProc.Id -Force -ErrorAction SilentlyContinue
    Wait-ProcessGone -Name "centsmith-backend" -TimeoutSeconds 10 | Out-Null
  }
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
