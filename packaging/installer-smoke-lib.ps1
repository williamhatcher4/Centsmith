function Normalize-CentsmithInstallRoot {
  param([AllowNull()][string]$Root)

  if ([string]::IsNullOrWhiteSpace($Root)) {
    return $null
  }

  $normalized = $Root.Trim().Trim('"')
  while ($normalized.Length -gt 3 -and ($normalized.EndsWith("\") -or $normalized.EndsWith("/"))) {
    $normalized = $normalized.Substring(0, $normalized.Length - 1)
  }
  if ([string]::IsNullOrWhiteSpace($normalized)) {
    return $null
  }

  $normalized
}

function Normalize-CentsmithInstallRoots {
  [CmdletBinding()]
  param(
    [Parameter(ValueFromPipeline = $true)]
    [AllowNull()]
    [string]$Root
  )

  begin {
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
  }

  process {
    $normalized = Normalize-CentsmithInstallRoot $Root
    if ($normalized -and $seen.Add($normalized)) {
      $normalized
    }
  }
}

function Get-CentsmithFixedInstallRoots {
  param(
    [string]$LocalAppData = $env:LOCALAPPDATA,
    [string]$ProgramFiles = $env:ProgramFiles,
    [string]$ProgramFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)"),
    [string]$ProgramW6432 = [Environment]::GetEnvironmentVariable("ProgramW6432")
  )

  @(
    $(if ($LocalAppData) { Join-Path $LocalAppData "Centsmith" })
    $(if ($LocalAppData) { Join-Path $LocalAppData "Programs\Centsmith" })
    $(if ($ProgramFiles) { Join-Path $ProgramFiles "Centsmith" })
    $(if ($ProgramW6432) { Join-Path $ProgramW6432 "Centsmith" })
    $(if ($ProgramFilesX86) { Join-Path $ProgramFilesX86 "Centsmith" })
  ) | Normalize-CentsmithInstallRoots
}

function Get-CentsmithInstallRoots {
  $roots = New-Object System.Collections.Generic.List[string]

  Get-CentsmithFixedInstallRoots | ForEach-Object { $roots.Add($_) }

  foreach ($registryRoot in @(
      "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
      "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
      "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )) {
    Get-ItemProperty -Path $registryRoot -ErrorAction SilentlyContinue |
      Where-Object { $_.DisplayName -eq "Centsmith" -and -not [string]::IsNullOrWhiteSpace($_.InstallLocation) } |
      ForEach-Object { $roots.Add($_.InstallLocation) }
  }

  $roots | Normalize-CentsmithInstallRoots
}
