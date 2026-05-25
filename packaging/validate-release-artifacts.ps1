[CmdletBinding()]
param(
    [string]$Path = (Join-Path (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)) "desktop\src-tauri\resources\backend")
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $Path)) {
    throw "Release artifact path does not exist: $Path"
}

$BlockedExtensions = @(
    ".env",
    ".key",
    ".pem",
    ".pfx",
    ".p12"
)

$BlockedNamePatterns = @(
    "private",
    "credential",
    "password",
    "signing-key",
    "signing_key"
)

$Findings = @()
Get-ChildItem -LiteralPath $Path -Recurse -Force -File | ForEach-Object {
    $name = $_.Name.ToLowerInvariant()
    $extension = $_.Extension.ToLowerInvariant()

    if ($BlockedExtensions -contains $extension -or $name -eq ".env") {
        $Findings += $_.FullName
        return
    }

    foreach ($pattern in $BlockedNamePatterns) {
        if ($name.Contains($pattern)) {
            $Findings += $_.FullName
            return
        }
    }
}

if ($Findings.Count -gt 0) {
    $message = "Blocked secret-like files found in staged release resources:`n" + ($Findings -join "`n")
    throw $message
}

Write-Host "Release resource validation passed: $Path" -ForegroundColor Green
