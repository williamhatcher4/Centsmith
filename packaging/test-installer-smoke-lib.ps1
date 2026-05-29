$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path "$PSScriptRoot\.."
. (Join-Path $repoRoot "packaging\installer-smoke-lib.ps1")

$localAppData = "C:\Users\runneradmin\AppData\Local"
$programFiles = "C:\Program Files"
$programFilesX86 = "C:\Program Files (x86)"

$fixedRoots = @(Get-CentsmithFixedInstallRoots `
    -LocalAppData $localAppData `
    -ProgramFiles $programFiles `
    -ProgramFilesX86 $programFilesX86)

if ($fixedRoots -notcontains "C:\Users\runneradmin\AppData\Local\Centsmith") {
  throw "Expected current-user NSIS root under LOCALAPPDATA to be included."
}

if ($fixedRoots -notcontains "C:\Users\runneradmin\AppData\Local\Programs\Centsmith") {
  throw "Expected legacy current-user Programs root to remain included."
}

$normalized = Normalize-CentsmithInstallRoot '"C:\Users\runneradmin\AppData\Local\Centsmith\"'
if ($normalized -ne "C:\Users\runneradmin\AppData\Local\Centsmith") {
  throw "Expected registry InstallLocation quotes and trailing slash to be stripped; got '$normalized'."
}

$deduped = @(@(
  "C:\Users\runneradmin\AppData\Local\Centsmith"
  '"C:\Users\runneradmin\AppData\Local\Centsmith"'
  " "
) | Normalize-CentsmithInstallRoots)

if ($deduped.Count -ne 1 -or $deduped[0] -ne "C:\Users\runneradmin\AppData\Local\Centsmith") {
  throw "Expected normalized install roots to be de-duplicated; got '$($deduped -join "', '")'."
}

Write-Host "Installer smoke helper tests passed."
