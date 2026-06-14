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

# --- Phase 2 helpers (P5.1: launch the installed shell, follow its breadcrumbs) ---

function Test-CentsmithShellExeName {
  # The installed shell exe is Centsmith*.exe but NOT the bundled backend
  # (centsmith-backend.exe also starts with "centsmith") and NOT an uninstaller.
  param([AllowNull()][string]$Name)

  if ([string]::IsNullOrWhiteSpace($Name)) {
    return $false
  }
  $leaf = Split-Path -Leaf $Name
  if ($leaf -notlike "Centsmith*.exe") {
    return $false
  }
  if ($leaf -eq "centsmith-backend.exe") {
    return $false
  }
  if ($leaf -like "*uninstall*") {
    return $false
  }
  return $true
}

function Find-CentsmithShellExe {
  # Locate the installed Tauri shell exe under the same roots used to find the
  # backend, excluding the backend exe and any uninstaller.
  param([string[]]$InstallRoots)

  foreach ($root in $InstallRoots) {
    if ([string]::IsNullOrWhiteSpace($root) -or -not (Test-Path -LiteralPath $root)) {
      continue
    }
    $candidates = Get-ChildItem -Path $root -Filter "Centsmith*.exe" -Recurse -ErrorAction SilentlyContinue
    foreach ($candidate in $candidates) {
      if (Test-CentsmithShellExeName $candidate.Name) {
        return $candidate
      }
    }
  }
  return $null
}

function Get-PortFromShellLog {
  # The shell logs "port {N} is open" once the backend's port is reachable.
  param([AllowNull()][string]$LogText)

  if ([string]::IsNullOrWhiteSpace($LogText)) {
    return $null
  }
  $match = [regex]::Match($LogText, 'port (\d+) is open')
  if ($match.Success) {
    return [int]$match.Groups[1].Value
  }
  return $null
}

function Wait-ShellLogLine {
  # Poll a log file until a line matches $Pattern; return the matching line, or
  # $null on timeout. Tolerant of transient read locks (the shell appends live).
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$Pattern,
    [int]$TimeoutSeconds = 60,
    [int]$PollMilliseconds = 500
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    if (Test-Path -LiteralPath $Path) {
      try {
        $line = Select-String -LiteralPath $Path -Pattern $Pattern -ErrorAction Stop |
          Select-Object -First 1
        if ($line) {
          return $line.Line
        }
      } catch {
        # File momentarily locked by the writer -- retry.
      }
    }
    Start-Sleep -Milliseconds $PollMilliseconds
  }
  return $null
}

function Wait-ProcessGone {
  # Poll until no process named $Name remains; return $true if gone within the
  # deadline, else $false.
  param(
    [Parameter(Mandatory = $true)][string]$Name,
    [int]$TimeoutSeconds = 10,
    [int]$PollMilliseconds = 500
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    if (-not (Get-Process -Name $Name -ErrorAction SilentlyContinue)) {
      return $true
    }
    Start-Sleep -Milliseconds $PollMilliseconds
  }
  return -not (Get-Process -Name $Name -ErrorAction SilentlyContinue)
}
