# Runtime destruction trial (plan 126 stage B + gameplay layer / document 160, 161).
#
# Runs the game standalone (no editor) on the board map with -TreadDestructionTest and lets
# ATreadBuildingDestructionManager register the middle 4x8 band and run one automated pass:
#
#   -Mode band      destroy every building in one pass (render/perf regression, document 160 section 3.5)
#   -Mode cascade   fire a few area hits and let the health / load-bearing cascade do the rest (document 161)
#
# Both modes sample frame times before/after, save a screenshot and write Saved/Reports/Destruction_Runtime.json,
# then quit.
#
#   pwsh Tools/destruction/run_destruction_runtime.ps1 [-Mode band|cascade] [-TimeoutSec 150]
param(
    [ValidateSet('band', 'cascade', 'trample')]
    [string]$Mode = 'band',
    [int]$TimeoutSec = 150
)
$project = 'E:\AI\Tread\Tread'
$exe = 'G:\epicgame\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$report = Join-Path $project 'Saved\Reports\Destruction_Runtime.json'
$screenshot = Join-Path $project 'Saved\Screenshots\Destruction_Runtime.png'
$log = Join-Path $project ('Saved\Logs\Destruction_Runtime_' + $Mode + '.log')
$err = Join-Path $project ('Saved\Logs\Destruction_Runtime_' + $Mode + '.err.log')
Remove-Item $report, $log, $err -Force -ErrorAction SilentlyContinue

$args = @(
    (Join-Path $project 'Tread.uproject'),
    '/Game/Tread/Maps/M3_Paris_Match',
    '-game',
    '-TreadSkipFrontEnd',
    '-TreadDestructionTest'
)
# A separate plain flag instead of -Key=Value: Start-Process splits on '=' in a way the map parser mistakes for a map.
if ($Mode -eq 'cascade') { $args += '-TreadDestructionCascade' }
if ($Mode -eq 'trample') { $args += '-TreadDestructionTrample' }
$args += @('-ResX=1920', '-ResY=1080', '-windowed', '-NoSplash', '-log')
$p = Start-Process -FilePath $exe -ArgumentList $args -WorkingDirectory $project `
    -RedirectStandardOutput $log -RedirectStandardError $err -PassThru
Write-Output ('pid=' + $p.Id + ' mode=' + $Mode)

$done = $false
$reportSeen = 0
for ($i = 0; $i -lt $TimeoutSec; $i++) {
    Start-Sleep -Seconds 1
    if (-not (Get-Process -Id $p.Id -ErrorAction SilentlyContinue)) { $done = $true; break }
    # The report lands a second before the game asks to exit; give it a grace period, then stop it (QuitGame does not
    # always terminate a -game process when a Live Coding server is attached).
    if (Test-Path $report) {
        $reportSeen++
        if ($reportSeen -ge 5) { $done = $true; break }
    }
}
Write-Output ('done=' + $done)
if (Get-Process -Id $p.Id -ErrorAction SilentlyContinue) { Stop-Process -Id $p.Id -Force }
if (Test-Path $report) {
    Get-Content -Raw $report
    if (Test-Path $screenshot) {
        Copy-Item $screenshot (Join-Path $project ('Saved\Screenshots\Destruction_Runtime_' + $Mode + '.png')) -Force
    }
} else {
    Get-Content $err -Tail 30 -ErrorAction SilentlyContinue
    Get-Content $log -Tail 30 -ErrorAction SilentlyContinue
}
