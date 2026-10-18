# P0-1 evidence: run a real preparation with the AI opponents playing and report their summary lines.
#
#   pwsh -File Tools/m1/run_ai_preparation_check.ps1 [-Seconds 40]
#
# Starts M3_Paris_Match in -game, drives the match to PREPARE through the existing M2 capture path (BP -> Confirm ->
# BeginPreparation), lets the AI take its turn, then terminates the process and reports the "Tread AI" log lines.
# The engine truncates Tread.log on every start, so the whole file is read after the run rather than a byte offset.
param(
    [int]$Seconds = 40,
    [string]$OutputJson = ''
)

$project = 'E:\AI\Tread\Tread'
$exe = 'G:\epicgame\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$log = Join-Path $project 'Saved\Logs\Tread.log'
if (-not $OutputJson) { $OutputJson = Join-Path $project 'Saved\Reports\M1_AI_Preparation.json' }

$args = @(
    'E:\AI\Tread\Tread\Tread.uproject',
    'M3_Paris_Match',
    '-game',
    '-TreadM2Capture=PREPARE',
    '-TreadSkipFrontEnd',
    '-ResX=1280', '-ResY=720', '-windowed', '-NoSplash', '-log'
)

$p = Start-Process -FilePath $exe -ArgumentList $args -WorkingDirectory $project -PassThru
Start-Sleep -Seconds $Seconds
if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force; Start-Sleep -Seconds 2 }

$lines = @()
if (Test-Path $log) {
    $lines = Get-Content $log -Tail 20000 | Where-Object { $_ -match 'Tread AI ' } | Select-Object -Last 12
}

$report = [ordered]@{
    ok = ($lines.Count -ge 3)
    aiLines = $lines
    seconds = $Seconds
    timestamp = (Get-Date).ToString('s')
}
$dir = Split-Path -Parent $OutputJson
if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
$report | ConvertTo-Json -Depth 5 | Set-Content -Path $OutputJson -Encoding UTF8

"ai_preparation_lines=$($lines.Count)"
$lines | ForEach-Object { $_.Trim() } | Select-Object -First 12
