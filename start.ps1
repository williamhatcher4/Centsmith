$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"

$NpmCmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $NpmCmd) { $NpmCmd = Get-Command npm -ErrorAction SilentlyContinue }
if (-not $NpmCmd) {
  Write-Host "Could not find npm. Install Node.js LTS from https://nodejs.org and re-run this script." -ForegroundColor Red
  exit 1
}
$Npm = $NpmCmd.Source

function Kill-Pid {
  param([int]$ProcessId)
  if (-not $ProcessId -or $ProcessId -eq 0 -or $ProcessId -eq $PID) { return }
  try { Stop-Process -Id $ProcessId -Force -ErrorAction Stop } catch {}
}

function Stop-PortListeners {
  param([int[]]$Ports)
  foreach ($Port in $Ports) {
    $conns = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    foreach ($c in $conns) { Kill-Pid -ProcessId ([int]$c.OwningProcess) }
  }
}

function Stop-ProjectServers {
  $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -and $_.CommandLine -like "*$Root*" -and $_.ProcessId -ne $PID
  }
  foreach ($p in $procs) { Kill-Pid -ProcessId ([int]$p.ProcessId) }
}

$InstallBackend = $false
if (!(Test-Path $Python)) {
  py -3.12 -m venv (Join-Path $Backend ".venv")
  & $Python -m pip install --upgrade pip
  $InstallBackend = $true
} else {
  & $Python -c "import alembic" 2>$null
  if ($LASTEXITCODE -ne 0) { $InstallBackend = $true }
}
if ($InstallBackend) {
  & $Python -m pip install -e "$Backend[dev]"
}

$EnvFile = Join-Path $Backend ".env"
$EnvExample = Join-Path $Backend ".env.example"
if (!(Test-Path $EnvFile)) {
  if (!(Test-Path $EnvExample)) {
    Write-Host "Missing backend/.env.example - cannot bootstrap configuration." -ForegroundColor Red
    exit 1
  }
  $bytes = New-Object byte[] 32
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  $secret = -join ($bytes | ForEach-Object { $_.ToString("x2") })
  (Get-Content $EnvExample) -replace '__AUTO__', $secret | Set-Content -Encoding utf8 $EnvFile

  Write-Host ""
  Write-Host "Created backend/.env. Open it in a text editor, set ADMIN_USERNAME and ADMIN_PASSWORD, then re-run this script." -ForegroundColor Yellow
  Write-Host "File location: $EnvFile" -ForegroundColor Yellow
  exit 0
}

$envText = Get-Content $EnvFile -Raw
if ($envText -match '__AUTO__') {
  $bytes = New-Object byte[] 32
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  $secret = -join ($bytes | ForEach-Object { $_.ToString("x2") })
  ($envText -replace '__AUTO__', $secret) | Set-Content -Encoding utf8 $EnvFile
}

Stop-ProjectServers
Stop-PortListeners -Ports @(8012, 5175)
Start-Sleep -Milliseconds 800

Push-Location $Backend
& $Python scripts\seed_db.py
Pop-Location

if (!(Test-Path (Join-Path $Frontend "node_modules"))) {
  Push-Location $Frontend
  & $Npm install
  Pop-Location
}

Push-Location $Frontend
& $Npm run build
Pop-Location

# Run uvicorn without --reload: on Windows it spawns multiprocessing workers that
# can outlive the parent, hold port 8012, and serve stale code.
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$Backend'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8012"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$Frontend'; & '$Npm' run dev -- --host 127.0.0.1 --port 5175"
