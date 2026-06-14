$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path "$PSScriptRoot\.."
. (Join-Path $repoRoot "packaging\installer-smoke-lib.ps1")

$localAppData = "C:\Users\runneradmin\AppData\Local"
$programFiles = "C:\Program Files"
$programFilesX86 = "C:\Program Files (x86)"

$fixedRoots = @(Get-CentsmithFixedInstallRoots `
    -LocalAppData $localAppData `
    -ProgramFiles $programFiles `
    -ProgramFilesX86 $programFilesX86)

if ($fixedRoots -notcontains "C:\Users\runneradmin\AppData\Local\Centsmith") {
  throw "Expected current-user NSIS root under LOCALAPPDATA to be included."
}

if ($fixedRoots -notcontains "C:\Users\runneradmin\AppData\Local\Programs\Centsmith") {
  throw "Expected legacy current-user Programs root to remain included."
}

$normalized = Normalize-CentsmithInstallRoot '"C:\Users\runneradmin\AppData\Local\Centsmith\"'
if ($normalized -ne "C:\Users\runneradmin\AppData\Local\Centsmith") {
  throw "Expected registry InstallLocation quotes and trailing slash to be stripped; got '$normalized'."
}

$deduped = @(@(
  "C:\Users\runneradmin\AppData\Local\Centsmith"
  '"C:\Users\runneradmin\AppData\Local\Centsmith"'
  " "
) | Normalize-CentsmithInstallRoots)

if ($deduped.Count -ne 1 -or $deduped[0] -ne "C:\Users\runneradmin\AppData\Local\Centsmith") {
  throw "Expected normalized install roots to be de-duplicated; got '$($deduped -join "', '")'."
}

# --- Phase 2 helpers (P5.1) ----------------------------------------------------

# Test-CentsmithShellExeName: the shell exe is Centsmith*.exe but not the backend
# or an uninstaller (paths exercised so leaf extraction is covered too).
if (-not (Test-CentsmithShellExeName "Centsmith.exe")) {
  throw "Expected Centsmith.exe to be recognized as the shell exe."
}
if (-not (Test-CentsmithShellExeName "C:\Program Files\Centsmith\Centsmith.exe")) {
  throw "Expected a full path to Centsmith.exe to be recognized as the shell exe."
}
if (Test-CentsmithShellExeName "centsmith-backend.exe") {
  throw "Expected centsmith-backend.exe to be rejected (it is the backend, not the shell)."
}
if (Test-CentsmithShellExeName "C:\Program Files\Centsmith\resources\backend\centsmith-backend.exe") {
  throw "Expected the bundled backend path to be rejected."
}
if (Test-CentsmithShellExeName "uninstall.exe") {
  throw "Expected uninstall.exe to be rejected."
}
if (Test-CentsmithShellExeName "Centsmith-uninstaller.exe") {
  throw "Expected a Centsmith-branded uninstaller to be rejected."
}
if (Test-CentsmithShellExeName "notepad.exe") {
  throw "Expected an unrelated exe to be rejected."
}
if (Test-CentsmithShellExeName "") {
  throw "Expected an empty name to be rejected."
}

# Get-PortFromShellLog: extracts the port from the 'port N is open' breadcrumb.
$port = Get-PortFromShellLog "[3] port 51234 is open"
if ($port -ne 51234) {
  throw "Expected port 51234 to be extracted; got '$port'."
}
$multiline = "[1] navigate thread started`n[2] read runtime metadata for port 8088`n[3] port 8088 is open"
if ((Get-PortFromShellLog $multiline) -ne 8088) {
  throw "Expected port 8088 from a multi-line log; got '$(Get-PortFromShellLog $multiline)'."
}
if ($null -ne (Get-PortFromShellLog "no port breadcrumb here")) {
  throw "Expected `$null when no port breadcrumb is present."
}
if ($null -ne (Get-PortFromShellLog "")) {
  throw "Expected `$null for empty log text."
}

Write-Host "Installer smoke helper tests passed."
