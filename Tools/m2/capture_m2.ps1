param(
    [ValidateSet('PACTS', 'BATTLE', 'BATTLE2', 'SCOUT')][string]$Stage = 'PACTS',
    [string]$OutputName = 'M2_Pact_Tiers_Stacks',
    [string]$EngineRoot = 'G:/epicgame/UE_5.8',
    [int]$TimeoutSeconds = 240
)

# Launch the M1 graybox map as a standalone 1920x1080 game with the deterministic M2 showcase
# (-TreadM2Capture) and let the controller write Saved/Screenshots/<OutputName>.png, then exit.

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$ue = Join-Path $EngineRoot 'Engine/Binaries/Win64/UnrealEditor.exe'
$uproject = Join-Path $root 'Tread.uproject'
$shot = Join-Path $root "Saved/Screenshots/$OutputName.png"
$log = Join-Path $root "Saved/Reports/M2_Runs/capture_$OutputName.log"
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
if (Test-Path $shot) { Remove-Item $shot -Force }
$started = [DateTime]::UtcNow
$process = Start-Process -FilePath $ue -PassThru -ArgumentList @(
    ('"' + $uproject + '"'), '/Game/Tread/Maps/M1_Match_Graybox', '-game', '-windowed', '-ResX=1920', '-ResY=1080',
    '-TreadSeed=20260926', "-TreadM2Capture=$Stage", "-TreadM2Shot=$OutputName", '-nosplash', '-nosound', '-NoLiveCoding',
    ('"-abslog=' + $log + '"')
)
if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
    & taskkill.exe /PID $process.Id /T /F | Out-Null
    throw "capture timed out; see $log"
}
if (-not (Test-Path $shot)) { throw "screenshot not written: $shot (see $log)" }
Add-Type -AssemblyName System.Drawing
$image = [System.Drawing.Image]::FromFile($shot)
$size = "$($image.Width)x$($image.Height)"
$image.Dispose()
$info = [ordered]@{
    stage = $Stage; path = $shot; size = $size; startedUtc = $started.ToString('o')
    sha256 = (Get-FileHash $shot -Algorithm SHA256).Hash.ToLowerInvariant(); log = $log
}
$info | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $root "Saved/Reports/M2_Runs/capture_$OutputName.json")
Write-Host "M2_CAPTURE=$shot $size"
