$project = 'E:\AI\Tread\Tread'
$log = Join-Path $project 'Saved\Logs\M0_Perf_game.log'
$err = Join-Path $project 'Saved\Logs\M0_Perf_game.err.log'
$report = Join-Path $project 'Saved\Reports\M0_Paris_Render_Baseline.json'
Remove-Item $log, $err, $report -Force -ErrorAction SilentlyContinue
$exe = 'G:\epicgame\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$p = Start-Process -FilePath $exe -ArgumentList ($project+'\Tread.uproject'),'-game','-ResX=1920','-ResY=1080','-TreadM0Perf','-NoSplash','-log' -WorkingDirectory $project -RedirectStandardOutput $log -RedirectStandardError $err -PassThru
Write-Output ('pid=' + $p.Id)
$done = $false
for ($i = 0; $i -lt 75; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Path $report) { $done = $true; break }
    if (-not (Get-Process -Id $p.Id -ErrorAction SilentlyContinue)) { break }
}
Write-Output ('done=' + $done)
if (Get-Process -Id $p.Id -ErrorAction SilentlyContinue) { Stop-Process -Id $p.Id -Force }
if (Test-Path $report) { Get-Content -Raw $report }
else { Get-Content $err -Tail 80 -ErrorAction SilentlyContinue; Get-Content $log -Tail 80 -ErrorAction SilentlyContinue }
