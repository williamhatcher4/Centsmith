<#
.SYNOPSIS
  Fail unless every given file carries a valid Authenticode signature from the
  expected signer.

.DESCRIPTION
  Release builds are signed by SignPath with the SignPath Foundation
  certificate. Windows Smart App Control refuses to start unsigned, unknown
  binaries, so an unsigned centsmith.exe, centsmith-backend.exe or installer
  must never reach the update feed. The release workflow runs this after each
  signing step and before anything is uploaded.

  A missing timestamp only warns: without one the signature stops validating
  when the certificate expires, which is worth knowing but is not a reason to
  block a release that is otherwise signed correctly.

.NOTES
  Windows only (Get-AuthenticodeSignature).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string[]]$Path,
    # Substring expected in the signing certificate's subject.
    [string]$ExpectedSigner = "SignPath Foundation"
)

$ErrorActionPreference = "Stop"
$failures = @()

foreach ($file in $Path) {
    if (-not (Test-Path -LiteralPath $file)) {
        $failures += "${file}: file not found"
        continue
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $file
    if ($signature.Status -ne "Valid") {
        $failures += "${file}: signature status is $($signature.Status) ($($signature.StatusMessage))"
        continue
    }
    $subject = $signature.SignerCertificate.Subject
    if (-not [string]::IsNullOrWhiteSpace($ExpectedSigner) -and $subject -notlike "*$ExpectedSigner*") {
        $failures += "${file}: signed by '$subject', expected a signer containing '$ExpectedSigner'"
        continue
    }
    if ($null -eq $signature.TimeStamperCertificate) {
        Write-Warning "${file}: signature has no timestamp; it will stop validating when the certificate expires."
    }
    Write-Host "OK: $file is signed by $subject"
}

if ($failures.Count -gt 0) {
    throw "Authenticode verification FAILED:`n  - " + ($failures -join "`n  - ")
}
