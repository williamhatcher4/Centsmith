<#
.SYNOPSIS
  Live contract test for the license-gated auto-update Worker (plan item P5.3).

.DESCRIPTION
  The Worker lives in the separate Centsmith_website repo; a regression there
  silently breaks the updater for every installed app and nothing in this repo
  would notice (the 2026-06-03 dead-feed incident, but cross-repo). This script
  asserts the Worker's contract (docs/auto-update-worker-contract.md) against the
  LIVE endpoint:

    1. GET <base>/latest.json with no Authorization  -> 204 (401 accepted) + empty body
    2. GET <base>/latest.json with a bogus bearer     -> same
    3. GET <base>/download/<installer> with no token  -> 401/403 (never 200, never a redirect)
    4. (with -License) GET latest.json + bearer        -> 200 application/json, valid Tauri
       updater manifest whose windows url is under <base>/download/ (and == -ExpectedVersion)
    5. (with -License and -ExpectedInstallerSha256) download the manifest url with
       the bearer and assert SHA256 == the built installer's hash (byte-identical).

  Run rejection-only (steps 1-3) without a license; the licensed steps need a
  real, long-expiry CI license token (CENTSMITH_TEST_LICENSE secret).

.NOTES
  Targets PowerShell 7 (the CI shell): uses Invoke-WebRequest -SkipHttpErrorCheck.
  Never echoes the token. Run from anywhere; resolves sibling scripts via $PSScriptRoot.
#>
[CmdletBinding()]
param(
    [string]$BaseUrl = "https://centsmith.ca/api/updates",
    [string]$License,
    [string]$ExpectedVersion,
    [string]$ExpectedInstallerSha256,
    # The dummy installer name probed in the unauthenticated download check.
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
    if ($OutFile) { $args.OutFile = $OutFile }
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

# --- Steps 1 & 2: latest.json rejects no/bad tokens with 204 (or 401) ----------
foreach ($case in @(
        @{ Name = "no Authorization header"; Headers = @{} },
        @{ Name = "bogus bearer token"; Headers = @{ Authorization = "Bearer not-a-real-token" } }
    )) {
    $result = Get-HttpStatus -Uri "$BaseUrl/latest.json" -Headers $case.Headers
    if ($result.StatusCode -notin 204, 401) {
        $failures += "latest.json with $($case.Name): expected 204 (or 401), got $($result.StatusCode)"
    } elseif ($result.StatusCode -eq 204 -and -not [string]::IsNullOrEmpty($result.Content)) {
        $failures += "latest.json 204 with $($case.Name) should have an empty body"
    } else {
        Write-Host "OK: latest.json with $($case.Name) -> $($result.StatusCode)"
    }
}

# --- Step 3: download route never serves bytes without a token -----------------
$dl = Get-HttpStatus -Uri "$BaseUrl/download/$DownloadProbeName"
if ($dl.StatusCode -notin 401, 403) {
    $failures += "download/* with no token: expected 401/403, got $($dl.StatusCode) (must never be 200 or a redirect)"
} else {
    Write-Host "OK: download/$DownloadProbeName with no token -> $($dl.StatusCode)"
}

# --- Step 4: licensed manifest fetch + schema validation ----------------------
if (-not [string]::IsNullOrWhiteSpace($License)) {
    $authHeaders = @{ Authorization = "Bearer $License" }
    $manifest = Get-HttpStatus -Uri "$BaseUrl/latest.json" -Headers $authHeaders
    if ($manifest.StatusCode -ne 200) {
        $failures += "latest.json with a valid license: expected 200, got $($manifest.StatusCode)"
    } else {
        if ($manifest.ContentType -and $manifest.ContentType -notmatch "application/json") {
            $failures += "latest.json with a valid license: expected JSON content-type, got '$($manifest.ContentType)'"
        }
        $manifestPath = Join-Path ([System.IO.Path]::GetTempPath()) "centsmith-published-updater.json"
        Set-Content -LiteralPath $manifestPath -Value $manifest.Content -Encoding utf8

        # Validate the Tauri schema (semver version, RFC 3339 pub_date, non-blank
        # signature, https url) via the shared helper. We deliberately do NOT call
        # validate-release-artifacts.ps1 here: that script also scans the staged
        # backend-resources folder, which doesn't exist on the contract-test runner.
        . (Join-Path $PSScriptRoot "updater-manifest-lib.ps1")
        $published = Test-UpdaterManifestSchema -Path $manifestPath
        $url = $published.platforms."windows-x86_64".url
        if ($null -eq $url -or -not $url.StartsWith("$BaseUrl/download/")) {
            $failures += "published windows url must start with $BaseUrl/download/; got '$url'"
        } else {
            Write-Host "OK: licensed manifest served version $($published.version), url $url"
        }
        if (-not [string]::IsNullOrWhiteSpace($ExpectedVersion) -and $published.version -ne $ExpectedVersion) {
            $failures += "published manifest version '$($published.version)' != expected '$ExpectedVersion'"
        }

        # --- Step 5: gated download is byte-identical to the built installer ----
        if (-not [string]::IsNullOrWhiteSpace($ExpectedInstallerSha256) -and $url) {
            $installerPath = Join-Path ([System.IO.Path]::GetTempPath()) "centsmith-gated-installer.bin"
            $download = Get-HttpStatus -Uri $url -Headers $authHeaders -OutFile $installerPath
            if ($download.StatusCode -ne 200 -or -not (Test-Path -LiteralPath $installerPath)) {
                $failures += "gated installer download: expected 200 with a file, got $($download.StatusCode)"
            } else {
                $actual = (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash.ToLowerInvariant()
                if ($actual -ne $ExpectedInstallerSha256.ToLowerInvariant()) {
                    $failures += "gated installer sha256 '$actual' != built installer '$($ExpectedInstallerSha256.ToLowerInvariant())'"
                } else {
                    Write-Host "OK: gated installer download is byte-identical to the built installer"
                }
                Remove-Item -LiteralPath $installerPath -ErrorAction SilentlyContinue
            }
        }
        Remove-Item -LiteralPath $manifestPath -ErrorAction SilentlyContinue
    }
} else {
    Write-Host "No -License provided; ran rejection-only checks (steps 1-3)."
}

if ($failures.Count -gt 0) {
    throw "Update Worker contract test FAILED:`n  - " + ($failures -join "`n  - ")
}
Write-Host "Update Worker contract test passed." -ForegroundColor Green
