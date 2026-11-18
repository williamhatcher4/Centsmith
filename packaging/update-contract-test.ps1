<#
.SYNOPSIS
  Live contract test for the public auto-update feed (plan item P5.3).

.DESCRIPTION
  The feed lives in the separate Centsmith_website repo; a regression there
  silently breaks the updater for every installed app and nothing in this repo
  would notice (the 2026-06-03 dead-feed incident, but cross-repo). Centsmith is
  free, so the feed and installer downloads are public. This script asserts the
  contract (auto-update-contract.md in the website repo) against the LIVE endpoint:

    1. GET <base>/latest.json with no Authorization -> 200 application/json, valid
       Tauri updater manifest whose windows url is under <base>/download/
       (and whose version == -ExpectedVersion when given)
    2. GET <base>/latest.json with a stale bearer   -> same 200 (older app versions
       still send their old license token; it must be ignored, not rejected)
    3. GET <base>/download/<missing installer>      -> 404 (never a redirect)
    4. (with -ExpectedInstallerSha256) download the manifest url with no auth and
       assert SHA256 == the built installer's hash (byte-identical).

.NOTES
  Targets PowerShell 7 (the CI shell): uses Invoke-WebRequest -SkipHttpErrorCheck.
  Run from anywhere; resolves sibling scripts via $PSScriptRoot.
#>
[CmdletBinding()]
param(
    [string]$BaseUrl = "https://centsmith.ca/api/updates",
    [string]$ExpectedVersion,
    [string]$ExpectedInstallerSha256,
    # A dummy installer name that must not exist, probed in the 404 check.
    [string]$DownloadProbeName = "Centsmith_0.0.0_x64-setup.exe"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$BaseUrl = $BaseUrl.TrimEnd("/")

function Get-HttpStatus {
    # Issue a request and return @{ StatusCode; ContentType; Content } without
    # throwing on non-2xx (so the status itself is assertable). Redirects are NOT
    # followed, so a gated route that 302s to the artifact is caught as a 3xx.
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [hashtable]$Headers = @{},
        [string]$OutFile
    )
    $args = @{
        Uri                = $Uri
        Headers            = $Headers
        SkipHttpErrorCheck = $true
        MaximumRedirection = 0
        ErrorAction        = "Stop"
    }
    # -OutFile writes the body to disk; without -PassThru, PowerShell 7 returns
    # nothing from Invoke-WebRequest, leaving $resp null (and $resp.Headers a
    # method call on null). -PassThru makes it return the response object too, so
    # the status/headers stay assertable while the body still lands in the file.
    if ($OutFile) {
        $args.OutFile = $OutFile
        $args.PassThru = $true
    }
    try {
        $resp = Invoke-WebRequest @args
        $contentType = $null
        if ($resp.Headers.ContainsKey("Content-Type")) { $contentType = [string]$resp.Headers["Content-Type"] }
        return [pscustomobject]@{
            StatusCode  = [int]$resp.StatusCode
            ContentType = $contentType
            Content     = $resp.Content
        }
    } catch {
        # -SkipHttpErrorCheck handles HTTP error statuses, but redirect-blocking or
        # transport quirks can still surface as exceptions carrying a response.
        $response = $_.Exception.Response
        if ($null -ne $response -and $null -ne $response.StatusCode) {
            return [pscustomobject]@{
                StatusCode  = [int]$response.StatusCode.value__
                ContentType = $null
                Content     = $null
            }
        }
        throw
    }
}

$failures = @()
. (Join-Path $PSScriptRoot "updater-manifest-lib.ps1")

# --- Steps 1 & 2: latest.json is public (and ignores stale bearer tokens) ------
$published = $null
foreach ($case in @(
        @{ Name = "no Authorization header"; Headers = @{} },
        @{ Name = "stale bearer token"; Headers = @{ Authorization = "Bearer not-a-real-token" } }
    )) {
    $manifest = Get-HttpStatus -Uri "$BaseUrl/latest.json" -Headers $case.Headers
    if ($manifest.StatusCode -ne 200) {
        $failures += "latest.json with $($case.Name): expected 200, got $($manifest.StatusCode)"
        continue
    }
    if ($manifest.ContentType -and $manifest.ContentType -notmatch "application/json") {
        $failures += "latest.json with $($case.Name): expected JSON content-type, got '$($manifest.ContentType)'"
    }
    $manifestPath = Join-Path ([System.IO.Path]::GetTempPath()) "centsmith-published-updater.json"
    Set-Content -LiteralPath $manifestPath -Value $manifest.Content -Encoding utf8
    # Validate the Tauri schema (semver version, RFC 3339 pub_date, non-blank
    # signature, https url) via the shared helper. We deliberately do NOT call
    # validate-release-artifacts.ps1 here: that script also scans the staged
    # backend-resources folder, which doesn't exist on the contract-test runner.
    $published = Test-UpdaterManifestSchema -Path $manifestPath
    Remove-Item -LiteralPath $manifestPath -ErrorAction SilentlyContinue
    Write-Host "OK: latest.json with $($case.Name) -> 200, version $($published.version)"
}

$url = $null
if ($null -ne $published) {
    $url = $published.platforms."windows-x86_64".url
    if ($null -eq $url -or -not $url.StartsWith("$BaseUrl/download/")) {
        $failures += "published windows url must start with $BaseUrl/download/; got '$url'"
        $url = $null
    }
    if (-not [string]::IsNullOrWhiteSpace($ExpectedVersion) -and $published.version -ne $ExpectedVersion) {
        $failures += "published manifest version '$($published.version)' != expected '$ExpectedVersion'"
    }
}

# --- Step 3: a missing installer is a clean 404 -------------------------------
$dl = Get-HttpStatus -Uri "$BaseUrl/download/$DownloadProbeName"
if ($dl.StatusCode -ne 404) {
    $failures += "download/$DownloadProbeName (missing): expected 404, got $($dl.StatusCode)"
} else {
    Write-Host "OK: download/$DownloadProbeName (missing) -> 404"
}

# --- Step 4: public download is byte-identical to the built installer ---------
if (-not [string]::IsNullOrWhiteSpace($ExpectedInstallerSha256) -and $url) {
    $installerPath = Join-Path ([System.IO.Path]::GetTempPath()) "centsmith-published-installer.bin"
    $download = Get-HttpStatus -Uri $url -OutFile $installerPath
    if ($download.StatusCode -ne 200 -or -not (Test-Path -LiteralPath $installerPath)) {
        $failures += "installer download: expected 200 with a file, got $($download.StatusCode)"
    } else {
        $actual = (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $ExpectedInstallerSha256.ToLowerInvariant()) {
            $failures += "installer sha256 '$actual' != built installer '$($ExpectedInstallerSha256.ToLowerInvariant())'"
        } else {
            Write-Host "OK: public installer download is byte-identical to the built installer"
        }
        Remove-Item -LiteralPath $installerPath -ErrorAction SilentlyContinue
    }
}

if ($failures.Count -gt 0) {
    throw "Update feed contract test FAILED:`n  - " + ($failures -join "`n  - ")
}
Write-Host "Update feed contract test passed." -ForegroundColor Green
