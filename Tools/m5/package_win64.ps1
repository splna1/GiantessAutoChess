# M5 (document/165 P0-3): build + cook + stage + pak the Win64 Shipping build and smoke-test it.
#
#   pwsh -File Tools/m5/package_win64.ps1 [-SkipCook] [-SmokeSeconds 25]
#
# Output: Saved/StagedBuilds/Windows/Tread.exe (+ Tread-Windows.pak), Saved/Logs/Package_Win64.log,
#         Saved/Logs/Packaged_SmokeTest.log and Saved/Reports/M5_Package.json.
#
# Notes:
# - The Shipping game target must exist first; the script builds it (TreadEditor.dll is not needed).
# - UE 5.8's "-archive" step talks to ZenServer for the oplog; with no Zen server it fails *after* staging, so the
#   script stages only and reports Saved/StagedBuilds (document/165 section 3).
param(
    [switch]$SkipCook,
    [int]$SmokeSeconds = 25,
    [int]$TimeoutMinutes = 120
)

$project = 'E:\AI\Tread\Tread'
$engine = if ($env:UE_ENGINE_ROOT) { $env:UE_ENGINE_ROOT } else { 'G:\epicgame\UE_5.8' }
$uat = Join-Path $engine 'Engine\Build\BatchFiles\RunUAT.bat'
$build = Join-Path $engine 'Engine\Build\BatchFiles\Build.bat'
$log = Join-Path $project 'Saved\Logs\Package_Win64.log'
$smokeLog = Join-Path $project 'Saved\Logs\Packaged_SmokeTest.log'
$report = Join-Path $project 'Saved\Reports\M5_Package.json'
$staged = Join-Path $project 'Saved\StagedBuilds\Windows'
$exe = Join-Path $staged 'Tread.exe'
$started = Get-Date
$steps = [ordered]@{}

# 1) Shipping game target (the cook/stage step needs Binaries\Win64\Tread-Win64-Shipping.target).
$buildOut = & $build Tread Win64 Shipping "-Project=$project\Tread.uproject" -WaitMutex 2>&1
$steps['build'] = ($buildOut | Select-String -Pattern 'Result: Succeeded').Count -gt 0
$steps['buildTail'] = ($buildOut | Select-Object -Last 3) -join ' / '

# 2) Cook + stage (+pak). -skipbuild: step 1 already produced the binaries.
if (-not $SkipCook) {
    $cookOut = & $uat BuildCookRun "-project=$project\Tread.uproject" -noP4 -platform=Win64 -clientconfig=Shipping `
        -skipbuild -cook -stage -pak -unattended -utf8output 2>&1
    $cookOut | Set-Content -Path $log -Encoding UTF8
    $steps['cook'] = ($cookOut | Select-String -Pattern 'COOK COMMAND COMPLETED').Count -gt 0
    $steps['stage'] = ($cookOut | Select-String -Pattern 'STAGE COMMAND COMPLETED').Count -gt 0
}

$exeExists = Test-Path $exe
$sizeGb = 0
$pakMb = 0
if (Test-Path $staged) {
    $sizeGb = [math]::Round(((Get-ChildItem $staged -Recurse -File | Measure-Object Length -Sum).Sum / 1GB), 2)
    $pak = Get-ChildItem $staged -Filter *.pak -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pak) { $pakMb = [math]::Round($pak.Length / 1MB) }
}

# 3) Smoke test: the packaged exe must reach "Engine is initialized" and stay alive.
$steps['smoke'] = $false
$steps['smokeAlive'] = $false
if ($exeExists) {
    $p = Start-Process -FilePath $exe -WorkingDirectory $staged -PassThru -ArgumentList @(
        '-windowed', '-ResX=1280', '-ResY=720', '-NoSplash', '-log', "-abslog=$smokeLog")
    Start-Sleep -Seconds $SmokeSeconds
    $steps['smokeAlive'] = -not $p.HasExited
    if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force; Start-Sleep -Seconds 2 }
    if (Test-Path $smokeLog) {
        $steps['smoke'] = ((Get-Content $smokeLog -Tail 400) | Select-String -Pattern 'Engine is initialized').Count -gt 0
    }
}

$ok = $exeExists -and $steps['smoke'] -and $steps['smokeAlive'] -and ($SkipCook -or $steps['cook'])
$result = [ordered]@{
    ok = $ok
    exe = $exe
    exeExists = $exeExists
    stagedSizeGb = $sizeGb
    pakMb = $pakMb
    steps = $steps
    minutes = [math]::Round(((Get-Date) - $started).TotalMinutes, 1)
    log = $log
    smokeLog = $smokeLog
    timestamp = (Get-Date).ToString('s')
}
New-Item -ItemType Directory -Path (Split-Path -Parent $report) -Force | Out-Null
$result | ConvertTo-Json -Depth 5 | Set-Content -Path $report -Encoding UTF8

"M5_PACKAGE_OK=$ok exe=$exeExists size=$sizeGb GB pak=$pakMb MB minutes=$($result.minutes)"
$steps.GetEnumerator() | ForEach-Object { "  {0}={1}" -f $_.Key, $_.Value }
