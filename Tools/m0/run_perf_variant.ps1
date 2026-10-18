param(
    [string]$Label = 'baseline',
    [string]$ExecCmds = '',
    [string]$Map = '/Game/Tread/Maps/M0_Paris_Board',
    [string]$OutReport = 'Saved\Reports\M0_Variant.json'
)
$ErrorActionPreference = 'Stop'
$project = 'E:\AI\Tread\Tread'
$exe = 'G:\epicgame\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$report = Join-Path $project $OutReport
$fullReport = Join-Path $project 'Saved\Reports\M0_Paris_Render_Baseline.json'
Remove-Item $fullReport -Force -ErrorAction SilentlyContinue

$argString = '"{0}" "{1}" -game -ResX=1920 -ResY=1080 -TreadM0Perf -NoSplash -log' -f (Join-Path $project 'Tread.uproject'), $Map
if ($ExecCmds) { $argString += ' -ExecCmds="{0}"' -f $ExecCmds }

$p = Start-Process -FilePath $exe -ArgumentList $argString -WorkingDirectory $project -PassThru
for ($i = 0; $i -lt 150; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Path $fullReport) { break }
    if (-not (Get-Process -Id $p.Id -ErrorAction SilentlyContinue)) { break }
}
if (Get-Process -Id $p.Id -ErrorAction SilentlyContinue) { Stop-Process -Id $p.Id -Force }
if (-not (Test-Path $fullReport)) { "$Label NO_REPORT"; exit 1 }
Copy-Item $fullReport $report -Force
$doc = Get-Content -Raw $fullReport | ConvertFrom-Json
"{0} avg_fps={1:N2} 1pct_low={2:N2} avg_gpu={3:N2} p99={4:N2} over20={5} draws={6:N0} prims={7:N0}" -f `
    $Label, $doc.average_fps, $doc.one_percent_low_fps, $doc.average_gpu_ms, $doc.p99_frame_ms, $doc.frames_over_20ms, $doc.average_draw_calls, $doc.average_primitives
