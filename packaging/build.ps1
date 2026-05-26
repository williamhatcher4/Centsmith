# Builds the full Centsmith Windows installer.
#
# Pipeline:
#   1. npm run build                       -> frontend/dist
#   2. pyinstaller packaging/backend.spec  -> packaging/dist/centsmith-backend/
#      optional: -ObfuscateBackend routes this through PyArmor for release builds
#   3. copy backend bundle into            -> desktop/src-tauri/resources/backend/
#   4. cargo tauri build                   -> desktop/src-tauri/target/release/bundle/nsis/
#
# Required dev tools (one-time install):
#   - Node.js LTS                (frontend build)
#   - Python 3.10+ with venv     (backend + PyInstaller)
#   - Rust + cargo               (Tauri shell)
#   - Tauri CLI:  cargo install tauri-cli --version "^2.0"
#   - VS Build Tools (C++)       (Rust on Windows)
#
# Usage:
#   ./packaging/build.ps1
#   ./packaging/build.ps1 -SkipTauri -ObfuscateBackend

[CmdletBinding()]
param(
    [switch]$SkipTauri,
    [switch]$ObfuscateBackend
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$Packaging = Join-Path $Root "packaging"
$Desktop = Join-Path $Root "desktop"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"
$PyArmor = Join-Path $Backend ".venv\Scripts\pyarmor.exe"
$BackendOut = Join-Path $Packaging "dist\centsmith-backend"
$PyArmorDefaultBackendOut = Join-Path $Root "dist\centsmith-backend"
$ResourceTarget = Join-Path $Desktop "src-tauri\resources\backend"

function Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

if (-not (Test-Path $Python)) {
    throw "Backend venv missing. Run ./start.ps1 once to bootstrap it, then re-run this script."
}

Step "0/4  Backend dependencies"
& $Python -m pip install -e "$Backend[packaging]"

Step "1/4  Frontend build (npm run build)"
$NpmCmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $NpmCmd) { $NpmCmd = Get-Command npm -ErrorAction SilentlyContinue }
if (-not $NpmCmd) { throw "npm not found. Install Node.js LTS from https://nodejs.org." }
$Npm = $NpmCmd.Source
Push-Location $Frontend
try {
    if (-not (Test-Path (Join-Path $Frontend "node_modules"))) { & $Npm install }
    & $Npm run build
    if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
} finally { Pop-Location }

Step "2/4  PyInstaller (backend sidecar)"
# Force-remove stale dist output first — OneDrive marks some files read-only
# which causes PyInstaller's own cleanup to fail with PermissionError.
foreach ($OutputPath in @($BackendOut, $PyArmorDefaultBackendOut)) {
    if (Test-Path $OutputPath) {
        Get-ChildItem -Recurse $OutputPath | ForEach-Object { $_.Attributes = "Normal" }
        Remove-Item -Recurse -Force $OutputPath
    }
}
& $Python -m pip show pyinstaller > $null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing PyInstaller into backend venv..." -ForegroundColor Yellow
    & $Python -m pip install "pyinstaller>=6.6"
}
$BuildDir = Join-Path $Packaging "build"
$DistDir = Join-Path $Packaging "dist"
if ($ObfuscateBackend) {
    & $Python -m pip show pyarmor > $null 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installing PyArmor into backend venv..." -ForegroundColor Yellow
        & $Python -m pip install "pyarmor>=9.0"
    }

    $PyiOptions = "--distpath `"$DistDir`" --workpath `"$BuildDir`" --noconfirm"
    if (-not (Test-Path $PyArmor)) {
        throw "PyArmor executable not found at $PyArmor"
    }

    # PyArmor's `cfg` parses three positional tokens after the subcommand:
    # <key> <op> <value>. PowerShell tokenizes the bare `=` as its own arg,
    # which matches that grammar — do NOT collapse to "key=value".
    & $PyArmor cfg pack:pyi_options = $PyiOptions
    if ($LASTEXITCODE -ne 0) { throw "PyArmor config failed" }

    & $PyArmor gen --pack (Join-Path $Packaging "backend.spec") `
        -r (Join-Path $Packaging "backend_entry.py") (Join-Path $Backend "app")
    if ($LASTEXITCODE -ne 0) { throw "PyArmor/PyInstaller build failed" }
} else {
    & $Python -m PyInstaller (Join-Path $Packaging "backend.spec") `
        --distpath $DistDir --workpath $BuildDir --noconfirm
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }
}

Step "3/4  Stage backend bundle into Tauri resources/"
$BackendOutCandidates = @($BackendOut)
if ($ObfuscateBackend) {
    # PyArmor's pack mode may invoke PyInstaller without honoring pack:pyi_options
    # on some CI versions, leaving the bundle in PyInstaller's default root dist/.
    $BackendOutCandidates += $PyArmorDefaultBackendOut
}
$ActualBackendOut = $BackendOutCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $ActualBackendOut) {
    throw "Backend bundle output not found. Checked: $($BackendOutCandidates -join ', ')"
}
if (Test-Path $ResourceTarget) { Remove-Item -Recurse -Force $ResourceTarget }
New-Item -ItemType Directory -Force -Path $ResourceTarget | Out-Null
Write-Host "Staging backend bundle from $ActualBackendOut" -ForegroundColor DarkGray
Copy-Item -Recurse -Force -Path (Join-Path $ActualBackendOut "*") -Destination $ResourceTarget
& (Join-Path $Packaging "validate-release-artifacts.ps1") -Path $ResourceTarget

if ($SkipTauri) {
    Write-Host "Skipping Tauri build (-SkipTauri). Backend staged at $ResourceTarget" -ForegroundColor Yellow
    exit 0
}

Step "4/4  Tauri build (cargo tauri build)"
$TauriCmd = Get-Command cargo -ErrorAction SilentlyContinue
if (-not $TauriCmd) { throw "cargo not found. Install Rust from https://rustup.rs." }
Push-Location (Join-Path $Desktop "src-tauri")
try {
    & cargo tauri build
    if ($LASTEXITCODE -ne 0) { throw "Tauri build failed" }
} finally { Pop-Location }

$NsisOut = Join-Path $Desktop "src-tauri\target\release\bundle\nsis"
Write-Host ""
Write-Host "Done. Installer is in: $NsisOut" -ForegroundColor Green
