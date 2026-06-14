$ErrorActionPreference = 'Stop'

# Unit tests for validate-release-artifacts.ps1: the secret scan and the Tauri
# updater-manifest validation (-UpdaterJsonPath). Run directly:
#   powershell -File packaging\test-validate-release-artifacts.ps1

$script = Join-Path $PSScriptRoot "validate-release-artifacts.ps1"
$work = Join-Path ([IO.Path]::GetTempPath()) ("centsmith-validate-test-" + [Guid]::NewGuid())
New-Item -ItemType Directory -Path $work | Out-Null

function Expect-Throw([scriptblock]$Block, [string]$PatternInMessage, [string]$Why) {
    $threw = $false
    try { & $Block | Out-Null } catch {
        $threw = $true
        if ($PatternInMessage -and $_.Exception.Message -notmatch $PatternInMessage) {
            throw "Expected failure message matching '$PatternInMessage' for: $Why; got: $($_.Exception.Message)"
        }
    }
    if (-not $threw) { throw "Expected a validation failure: $Why" }
}

function Write-Manifest([hashtable]$Overrides) {
    $manifest = @{
        version  = "0.1.7"
        notes    = "Release notes"
        pub_date = "2026-06-09T12:00:00.0000000Z"
        platforms = @{
            "windows-x86_64" = @{
                signature = "dGVzdC1zaWduYXR1cmU="
                url       = "https://centsmith.ca/api/updates/download/Centsmith_0.1.7_x64-setup.exe"
            }
        }
    }
    foreach ($key in $Overrides.Keys) { $manifest[$key] = $Overrides[$key] }
    $path = Join-Path $work ("updater-" + [Guid]::NewGuid() + ".json")
    $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $path -Encoding utf8
    return $path
}

try {
    $cleanResources = Join-Path $work "resources"
    New-Item -ItemType Directory -Path $cleanResources | Out-Null
    Set-Content -LiteralPath (Join-Path $cleanResources "app.dll") -Value "binary"

    # A clean resource dir plus a schema-correct manifest passes.
    & $script -Path $cleanResources -UpdaterJsonPath (Write-Manifest @{}) | Out-Null

    # The secret scan still rejects key material (regression).
    $dirtyResources = Join-Path $work "resources-dirty"
    New-Item -ItemType Directory -Path $dirtyResources | Out-Null
    Set-Content -LiteralPath (Join-Path $dirtyResources "signing.pem") -Value "key"
    Expect-Throw { & $script -Path $dirtyResources } "secret-like" "a .pem file in the staged resources"

    # Manifest schema failures.
    Expect-Throw { & $script -Path $cleanResources -UpdaterJsonPath (Join-Path $work "missing.json") } `
        "does not exist" "a missing manifest path"

    $notJson = Join-Path $work "bad.json"
    Set-Content -LiteralPath $notJson -Value "{ not json"
    Expect-Throw { & $script -Path $cleanResources -UpdaterJsonPath $notJson } `
        "not valid JSON" "a malformed manifest"

    Expect-Throw { & $script -Path $cleanResources -UpdaterJsonPath (Write-Manifest @{ version = "v0.1.7" }) } `
        "plain semver" "a version with a leading v"

    Expect-Throw { & $script -Path $cleanResources -UpdaterJsonPath (Write-Manifest @{ pub_date = "yesterday" }) } `
        "RFC 3339" "an unparseable pub_date"

    Expect-Throw { & $script -Path $cleanResources -UpdaterJsonPath (Write-Manifest @{ platforms = @{} }) } `
        "windows-x86_64" "a manifest without the windows platform entry"

    Expect-Throw {
        & $script -Path $cleanResources -UpdaterJsonPath (Write-Manifest @{
            platforms = @{ "windows-x86_64" = @{ signature = ""; url = "https://centsmith.ca/x.exe" } }
        })
    } "signature" "a blank updater signature"

    Expect-Throw {
        & $script -Path $cleanResources -UpdaterJsonPath (Write-Manifest @{
            platforms = @{ "windows-x86_64" = @{ signature = "sig"; url = "http://centsmith.ca/x.exe" } }
        })
    } "https" "a non-https download url"

    Write-Host "Release artifact validation tests passed."
} finally {
    Remove-Item -Recurse -Force -LiteralPath $work -ErrorAction SilentlyContinue
}
