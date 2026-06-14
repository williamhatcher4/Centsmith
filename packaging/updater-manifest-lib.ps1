# Shared Tauri updater-manifest schema validation.
#
# Used by both validate-release-artifacts.ps1 (alongside the staged-resources
# secret scan, at release time) and update-contract-test.ps1 (P5.3, which has no
# staged resources to scan). Keeping the schema check here lets the contract test
# validate a published manifest without dragging in the resource-folder check.

function Test-UpdaterManifestSchema {
  # Validate a Tauri updater manifest against the schema the in-app updater
  # requires. Throws on any problem; returns the parsed object on success.
  param([Parameter(Mandatory = $true)][string]$Path)

  if (-not (Test-Path -LiteralPath $Path)) {
    throw "Updater manifest does not exist: $Path"
  }

  try {
    $updater = Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
  } catch {
    throw "Updater manifest is not valid JSON: $Path ($($_.Exception.Message))"
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
    throw "Updater manifest failed Tauri schema validation ($Path):`n" + ($problems -join "`n")
  }

  return $updater
}
