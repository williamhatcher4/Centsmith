# Builds the full Credit Tracker Windows installer.
#
# Pipeline:
#   1. npm run build                       -> frontend/dist
#   2. pyinstaller packaging/backend.spec  -> packaging/dist/credit-tracker-backend/
#   3. copy backend bundle into            -> desktop/src-tauri/resources/backend/
#   4. cargo tauri build                   -> desktop/src-tauri/target/release/bundle/app/
#   5. iscc packaging/installer.iss        -> packaging/dist/CreditTracker-Setup-*.exe
#
# Required dev tools (one-time install):
#   - Node.js LTS                (frontend build)
#   - Python 3.10+ with venv     (backend + PyInstaller)
#   - Rust + cargo               (Tauri shell)
#   - Tauri CLI:  cargo install tauri-cli --version "^2.0"
#   - VS Build Tools (C++)       (Rust on Windows)
#   - Inno Setup 6 (`iscc` on PATH)  (final installer)
#
# Usage:
#   ./packaging/build.ps1
#   ./packaging/build.ps1 -SkipInstaller   # stop after Tauri bundle

[CmdletBinding()]
param(
    [switch]$SkipInstaller,
    [switch]$SkipTauri
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$Packaging = Join-Path $Root "packaging"
$Desktop = Join-Path $Root "desktop"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"
$BackendOut = Join-Path $Packaging "dist\credit-tracker-backend"
$ResourceTarget = Join-Path $Desktop "src-tauri\resources\backend"

function Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

if (-not (Test-Path $Python)) {
    throw "Backend venv missing. Run ./start.ps1 once to bootstrap it, then re-run this script."
}

Step "1/5  Frontend build (npm run build)"
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

Step "2/5  PyInstaller (backend sidecar)"
& $Python -m pip show pyinstaller > $null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing PyInstaller into backend venv..." -ForegroundColor Yellow
    & $Python -m pip install "pyinstaller>=6.6"
}
$BuildDir = Join-Path $Packaging "build"
$DistDir = Join-Path $Packaging "dist"
& $Python -m PyInstaller (Join-Path $Packaging "backend.spec") `
    --distpath $DistDir --workpath $BuildDir --noconfirm
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

Step "3/5  Stage backend bundle into Tauri resources/"
if (Test-Path $ResourceTarget) { Remove-Item -Recurse -Force $ResourceTarget }
New-Item -ItemType Directory -Force -Path $ResourceTarget | Out-Null
Copy-Item -Recurse -Force -Path (Join-Path $BackendOut "*") -Destination $ResourceTarget

if ($SkipTauri) {
    Write-Host "Skipping Tauri build (-SkipTauri). Backend staged at $ResourceTarget" -ForegroundColor Yellow
    exit 0
}

Step "4/5  Tauri build (cargo tauri build)"
$TauriCmd = Get-Command cargo -ErrorAction SilentlyContinue
if (-not $TauriCmd) { throw "cargo not found. Install Rust from https://rustup.rs." }
Push-Location (Join-Path $Desktop "src-tauri")
try {
    & cargo tauri build
    if ($LASTEXITCODE -ne 0) { throw "Tauri build failed" }
} finally { Pop-Location }

if ($SkipInstaller) {
    Write-Host "Skipping Inno Setup (-SkipInstaller)." -ForegroundColor Yellow
    exit 0
}

Step "5/5  Inno Setup installer (iscc)"
$Iscc = Get-Command iscc -ErrorAction SilentlyContinue
if (-not $Iscc) { throw "iscc not found. Install Inno Setup 6 and add it to PATH." }
& iscc (Join-Path $Packaging "installer.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup build failed" }

Write-Host ""
Write-Host "Done. Installer is in: $DistDir" -ForegroundColor Green
