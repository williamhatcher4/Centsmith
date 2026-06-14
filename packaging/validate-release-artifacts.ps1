[CmdletBinding()]
param(
    [string]$Path = (Join-Path (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)) "desktop\src-tauri\resources\backend"),
    # Optional: a generated Tauri updater manifest (updater.json) to validate
    # against the schema the in-app updater requires. The release workflow
    # passes this before uploading the manifest to R2.
    [string]$UpdaterJsonPath
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

if ($UpdaterJsonPath) {
    if (-not (Test-Path -LiteralPath $UpdaterJsonPath)) {
        throw "Updater manifest does not exist: $UpdaterJsonPath"
    }

    try {
        $updater = Get-Content -Raw -LiteralPath $UpdaterJsonPath | ConvertFrom-Json
    } catch {
        throw "Updater manifest is not valid JSON: $UpdaterJsonPath ($($_.Exception.Message))"
    }

    $problems = @()

    # Tauri expects a bare semver, no leading "v".
    if ($null -eq $updater.version -or $updater.version -notmatch '^\d+\.\d+\.\d+$') {
        $problems += "version must be plain semver (x.y.z); got '$($updater.version)'"
    }

    $parsedDate = [DateTimeOffset]::MinValue
    if ($null -eq $updater.pub_date -or -not [DateTimeOffset]::TryParse($updater.pub_date, [ref]$parsedDate)) {
        $problems += "pub_date must be an RFC 3339 timestamp; got '$($updater.pub_date)'"
    }

    $windows = $null
    if ($null -ne $updater.platforms) {
        $windows = $updater.platforms.'windows-x86_64'
    }
    if ($null -eq $windows) {
        $problems += "platforms.'windows-x86_64' entry is missing"
    } else {
        if ([string]::IsNullOrWhiteSpace($windows.signature)) {
            $problems += "platforms.'windows-x86_64'.signature is missing or blank (is createUpdaterArtifacts enabled and TAURI_SIGNING_PRIVATE_KEY set?)"
        }
        if ($null -eq $windows.url -or $windows.url -notmatch '^https://') {
            $problems += "platforms.'windows-x86_64'.url must be an https URL; got '$($windows.url)'"
        }
    }

    if ($problems.Count -gt 0) {
        throw "Updater manifest failed Tauri schema validation ($UpdaterJsonPath):`n" + ($problems -join "`n")
    }

    Write-Host "Updater manifest validation passed: $UpdaterJsonPath" -ForegroundColor Green
}
