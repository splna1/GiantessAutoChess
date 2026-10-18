# Physics stress trial for plan 126 / document 160.
#
# Runs the game standalone (no editor) on the board map with -TreadDestructionPerf: ATreadDestructionPerfActor drops
# 96 rigid cubes onto a temporary floor over the middle 4x8 band, samples frame times per phase and writes
# Saved/Reports/Destruction_Physics_Trial.json, then quits.
#
#   pwsh Tools/destruction/run_physics_trial.ps1 [-Bodies 96]
param(
    [int]$Bodies = 96,
    [int]$TimeoutSec = 150
)
$project = 'E:\AI\Tread\Tread'
$exe = 'G:\epicgame\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$report = Join-Path $project 'Saved\Reports\Destruction_Physics_Trial.json'
$log = Join-Path $project 'Saved\Logs\Destruction_Physics.log'
$err = Join-Path $project 'Saved\Logs\Destruction_Physics.err.log'
Remove-Item $report, $log, $err -Force -ErrorAction SilentlyContinue

$args = @(
    (Join-Path $project 'Tread.uproject'),
    '/Game/Tread/Maps/M3_Paris_Match',
    '-game',
    '-TreadSkipFrontEnd',
    '-TreadDestructionPerf',
    ('-TreadDestructionPerfBodies=' + $Bodies),
    '-ResX=1920', '-ResY=1080', '-windowed',
    '-NoSplash', '-log'
)
$p = Start-Process -FilePath $exe -ArgumentList $args -WorkingDirectory $project `
    -RedirectStandardOutput $log -RedirectStandardError $err -PassThru
Write-Output ('pid=' + $p.Id + ' bodies=' + $Bodies)

$done = $false
for ($i = 0; $i -lt $TimeoutSec; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Path $report) { $done = $true; break }
    if (-not (Get-Process -Id $p.Id -ErrorAction SilentlyContinue)) { break }
}
Write-Output ('done=' + $done)
if (Get-Process -Id $p.Id -ErrorAction SilentlyContinue) { Stop-Process -Id $p.Id -Force }
if (Test-Path $report) {
    Get-Content -Raw $report
} else {
    Get-Content $err -Tail 40 -ErrorAction SilentlyContinue
    Get-Content $log -Tail 40 -ErrorAction SilentlyContinue
}
