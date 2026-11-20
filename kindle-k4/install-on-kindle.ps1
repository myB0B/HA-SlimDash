<#
.SYNOPSIS
  Copies the SlimDash extension to a jailbroken Kindle 4 (with KUAL).

.DESCRIPTION
  The Kindle must be plugged into the PC with USB (it shows up as a USB drive).
  The script:
    1. finds the Kindle (the drive named "Kindle"), or uses -Drive;
    2. creates the "extensions" folder if needed;
    3. copies "extensions\slimdash" (the scripts and the settings);
    4. writes your address into "slimdash.conf" if you give -Url;
    5. reminds you to eject the Kindle.
  If "slimdash.conf" already exists on the Kindle and you do not give -Url, your settings are kept.

.PARAMETER Drive
  Drive letter of the Kindle (e.g. E:) or its root folder. Default: automatic detection.

.PARAMETER Url
  Image address: http://<Home Assistant IP>:8099/<dashboard>.png?view=<number>
  (add &k=<key> if SlimDash has an access key).

.PARAMETER Ntp
  Time server of your local network (for example the Home Assistant IP). Empty: none.

.PARAMETER Interval
  Seconds between two updates (10 at least). Default: 60.

.EXAMPLE
  .\install-on-kindle.ps1 -Url "http://192.168.1.10:8099/kindle.png?view=0"
#>
param(
    [string]$Drive = "",
    [string]$Url = "",
    [string]$Ntp = "",
    [int]$Interval = 60
)

$ErrorActionPreference = "Stop"
$source = Join-Path $PSScriptRoot "copy-to-kindle\extensions\slimdash"
if (-not (Test-Path $source)) { throw "Folder not found: $source" }

# 1. Find the Kindle
if (-not $Drive) {
    $vol = Get-Volume -ErrorAction SilentlyContinue |
        Where-Object { $_.FileSystemLabel -eq "Kindle" -and $_.DriveLetter } | Select-Object -First 1
    if (-not $vol) {
        throw "Kindle not found. Plug it in with USB, or give its drive: -Drive E:"
    }
    $Drive = $vol.DriveLetter + ":"
}
$root = if ($Drive.Length -le 2) { $Drive + "\" } else { $Drive }
if (-not (Test-Path (Join-Path $root "documents"))) {
    throw "$root does not look like a Kindle (no 'documents' folder)."
}
Write-Host "Kindle: $root"

# 2-3. Copy (keeping the slimdash.conf and the log already there)
$target = Join-Path $root "extensions\slimdash"
$existingConf = Join-Path $target "slimdash.conf"
$keepConf = (Test-Path $existingConf) -and (-not $Url)
$backup = $null
if ($keepConf) { $backup = [IO.File]::ReadAllBytes($existingConf) }
New-Item -ItemType Directory -Force -Path $target | Out-Null
Copy-Item -Path (Join-Path $source "*") -Destination $target -Recurse -Force
if ($keepConf) {
    [IO.File]::WriteAllBytes($existingConf, $backup)
    Write-Host "Existing settings kept: $existingConf"
}

# 4. Settings
if ($Url) {
    if ($Interval -lt 10) { $Interval = 10 }
    $lines = Get-Content -Path $existingConf -Encoding UTF8
    $lines = $lines | ForEach-Object {
        if ($_ -match '^URL=') { 'URL="' + $Url + '"' }
        elseif ($_ -match '^NTP=') { 'NTP="' + $Ntp + '"' }
        elseif ($_ -match '^INTERVAL=') { 'INTERVAL=' + $Interval }
        else { $_ }
    }
    # Unix line endings (LF), no BOM: the Kindle script expects them
    [IO.File]::WriteAllText($existingConf, (($lines -join "`n") + "`n"), (New-Object Text.UTF8Encoding($false)))
    Write-Host "Address saved: $Url"
} elseif (-not $keepConf) {
    Write-Host "WARNING: the address is not set. Open $existingConf with a text editor and set URL=..."
}

Write-Host ""
Write-Host "Done. Eject the Kindle (right-click the drive, Eject), unplug it,"
Write-Host "plug it into a wall charger, then: Kindle Launcher > SlimDash > Start display."
