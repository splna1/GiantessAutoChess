param([string]$Map = '/Game/Tread/Maps/M3_Paris_Match', [string]$Name = 'M3_Paris')
# Same sampler as Tools/run_m0_perf.ps1 (-TreadM0Perf, 1920x1080) but on an explicit map; the controller writes
# Saved/Reports/M0_Paris_Render_Baseline.json, which is backed up first, copied to Saved/Reports/<Name>_Perf.json
# and then restored so the M0 evidence file is never replaced.
$project = 'E:\AI\Tread\Tread'
$report = Join-Path $project 'Saved\Reports\M0_Paris_Render_Baseline.json'
$backup = Join-Path $project 'Saved\Reports\M0_Paris_Render_Baseline.json.m3bak'
$out = Join-Path $project ("Saved\Reports\" + $Name + "_Perf.json")
$log = Join-Path $project ("Saved\Logs\" + $Name + "_Perf_game.log")
if (Test-Path $report) { Move-Item $report $backup -Force }
try {
    $exe = 'G:\epicgame\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
    $p = Start-Process -FilePath $exe -ArgumentList ($project + '\Tread.uproject'), $Map, '-game', '-ResX=1920', '-ResY=1080', '-TreadM0Perf', '-NoSplash', '-nosound', ('-abslog=' + $log) -WorkingDirectory $project -PassThru
    for ($i = 0; $i -lt 150; $i++) { Start-Sleep -Seconds 1; if (Test-Path $report) { Start-Sleep -Seconds 1; break }; if ($p.HasExited) { break } }
    if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force }
    if (-not (Test-Path $report)) { throw "no perf report; see $log" }
    Move-Item $report $out -Force
    Get-Content -Raw $out
} finally {
    if (Test-Path $backup) { Move-Item $backup $report -Force }
}
