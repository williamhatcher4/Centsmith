[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$FilePath
)

$ErrorActionPreference = "Stop"

function Write-SignLog([string]$Message) {
    Write-Host "[sign-windows] $Message"
}

function Require-Env([string]$Name) {
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Required environment variable $Name is not set."
    }
    return $value
}

$Required = [Environment]::GetEnvironmentVariable("CI_RELEASE_SIGNING_REQUIRED") -eq "1"
$CertificatePath = [Environment]::GetEnvironmentVariable("WINDOWS_CERTIFICATE_PATH")
$CertificatePassword = [Environment]::GetEnvironmentVariable("WINDOWS_CERTIFICATE_PASSWORD")
$TimestampUrl = [Environment]::GetEnvironmentVariable("WINDOWS_TIMESTAMP_URL")
if ([string]::IsNullOrWhiteSpace($TimestampUrl)) {
    $TimestampUrl = "http://timestamp.digicert.com"
}

if (-not (Test-Path -LiteralPath $FilePath)) {
    throw "File to sign does not exist: $FilePath"
}

if ([string]::IsNullOrWhiteSpace($CertificatePath) -or [string]::IsNullOrWhiteSpace($CertificatePassword)) {
    if ($Required) {
        Require-Env "WINDOWS_CERTIFICATE_PATH" | Out-Null
        Require-Env "WINDOWS_CERTIFICATE_PASSWORD" | Out-Null
    }
    Write-SignLog "Signing secrets not configured; skipping local code signing for $FilePath"
    exit 0
}

if (-not (Test-Path -LiteralPath $CertificatePath)) {
    throw "WINDOWS_CERTIFICATE_PATH does not exist: $CertificatePath"
}

$Signtool = Get-ChildItem -Path "${env:ProgramFiles(x86)}\Windows Kits\10\bin" `
    -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match "\\x64\\signtool\.exe$" } |
    Sort-Object FullName -Descending |
    Select-Object -First 1

if (-not $Signtool) {
    throw "Could not find signtool.exe. Install the Windows SDK on the build machine."
}

# `/p $CertificatePassword` exposes the PFX password on signtool's command
# line for the duration of the call. In CI this runs on an ephemeral runner
# (no other untrusted processes, VM discarded immediately), so the exposure
# is acceptable. For local signing on a developer workstation, prefer
# importing the PFX into the user's cert store once and signing via
# `/sha1 <thumbprint>` instead — no password ever appears in argv.
Write-SignLog "Signing $FilePath"
& $Signtool.FullName sign `
    /f $CertificatePath `
    /p $CertificatePassword `
    /fd SHA256 `
    /tr $TimestampUrl `
    /td SHA256 `
    /v `
    $FilePath

if ($LASTEXITCODE -ne 0) {
    throw "signtool failed with exit code $LASTEXITCODE"
}
