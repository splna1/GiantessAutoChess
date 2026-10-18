[CmdletBinding()]
param(
    [string]$EngineRoot = $env:UE_ENGINE_ROOT,
    [ValidateRange(30, 7200)][int]$BuildTimeoutSeconds = 1800,
    [ValidateRange(15, 1800)][int]$TestTimeoutSeconds = 180
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$projectFile = Join-Path $projectRoot 'Tread.uproject'
$reports = Join-Path $projectRoot 'Saved/Reports'
$nativeReport = Join-Path $reports 'M1_Match_SelfTest.json'
$runReport = Join-Path $reports 'M1_Match_Run.json'
$runId = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$runDirectory = Join-Path $reports "M1_Runs/$runId"
New-Item -ItemType Directory -Path $runDirectory -Force | Out-Null
$result = [ordered]@{
    schema = 'Tread.M1.MatchRun.v1'
    ok = $false
    runId = $runId
    startedUtc = [DateTime]::UtcNow.ToString('o')
    project = $projectFile
    nativeReport = $nativeReport
    evidenceSource = 'compiled TreadEditor + UnrealEditor-Cmd -game'
    checks = [ordered]@{}
    logs = $runDirectory
}

function Quote-Argument([string]$Value) {
    # These paths also pass through cmd.exe when invoking Build.bat.
    if ($Value -match '["%\r\n]') { throw "Unsupported command-line character in: $Value" }
    return '"' + $Value + '"'
}

function Wait-BoundedProcess($Process, [int]$Seconds, [string]$Label) {
    $watch = [Diagnostics.Stopwatch]::StartNew()
    while (-not $Process.WaitForExit(1000)) {
        if ($watch.Elapsed.TotalSeconds -ge $Seconds) {
            # Only terminate the process tree created by this runner.
            & taskkill.exe /PID $Process.Id /T /F | Out-Null
            throw "$Label exceeded ${Seconds}s; logs retained in $runDirectory"
        }
    }
    $Process.WaitForExit()
    $Process.Refresh()
    return $Process.ExitCode
}

$runMutex = [Threading.Mutex]::new($false, 'Local\Tread_M1_Match_SelfTest_Runner')
$ownsMutex = $false
try {
    $ownsMutex = $runMutex.WaitOne(0)
    if (-not $ownsMutex) { throw 'Another M1 regression runner is already active.' }
    if (-not $EngineRoot) {
        $association = (Get-Content -LiteralPath $projectFile -Raw | ConvertFrom-Json).EngineAssociation
        $installation = Get-ItemProperty -LiteralPath "HKLM:/SOFTWARE/EpicGames/Unreal Engine/$association" -ErrorAction SilentlyContinue
        if ($installation) { $EngineRoot = $installation.InstalledDirectory }
    }
    if (-not $EngineRoot) { throw 'Pass -EngineRoot <UE_5.8 directory> or set UE_ENGINE_ROOT.' }
    $EngineRoot = (Resolve-Path -LiteralPath $EngineRoot).Path
    $buildBat = Join-Path $EngineRoot 'Engine/Build/BatchFiles/Build.bat'
    $editorCmd = Join-Path $EngineRoot 'Engine/Binaries/Win64/UnrealEditor-Cmd.exe'
    foreach ($required in @($projectFile, $buildBat, $editorCmd)) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required file: $required" }
    }
    $buildCommand = (Quote-Argument $buildBat) + ' TreadEditor Win64 Development ' +
        (Quote-Argument "-Project=$projectFile") + ' -WaitMutex -NoHotReloadFromIDE -NoLiveCoding'
    $result.buildCommand = $buildCommand
    Write-Host 'Building TreadEditor Win64 Development...'
    $build = Start-Process -FilePath $env:ComSpec -ArgumentList ('/d /s /c "' + $buildCommand + '"') `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $runDirectory 'build.stdout.log') `
        -RedirectStandardError (Join-Path $runDirectory 'build.stderr.log')
    $result.buildExitCode = Wait-BoundedProcess $build $BuildTimeoutSeconds 'TreadEditor build'
    $result.checks.buildExitZero = $result.buildExitCode -eq 0
    if (-not $result.checks.buildExitZero) { throw "TreadEditor build failed ($($result.buildExitCode)); see $runDirectory" }

    $previousWriteUtc = $null
    if (Test-Path -LiteralPath $nativeReport) {
        $previousWriteUtc = (Get-Item -LiteralPath $nativeReport).LastWriteTimeUtc
        Copy-Item -LiteralPath $nativeReport -Destination (Join-Path $runDirectory 'previous-native-report.json')
    }
    $result.nativeStartedUtc = [DateTime]::UtcNow.ToString('o')
    $nativeStartedUtc = [DateTime]::Parse($result.nativeStartedUtc).ToUniversalTime()
    $ueLog = Join-Path $runDirectory 'UnrealEditor-Cmd.log'
    $nativeArguments = @(
        (Quote-Argument $projectFile), '/Game/Tread/Maps/M1_Match_Graybox',
        '-game', '-TreadM1SelfTest', '-TreadSeed=20260926', '-nullrhi', '-unattended',
        '-nosplash', '-nosound', '-NoLiveCoding', '-stdout', '-FullStdOutLogOutput',
        (Quote-Argument "-abslog=$ueLog")
    )
    $result.nativeCommand = (Quote-Argument $editorCmd) + ' ' + ($nativeArguments -join ' ')
    Write-Host 'Running native R1-R12 self-test without a game/editor window...'
    $native = Start-Process -FilePath $editorCmd -ArgumentList $nativeArguments `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $runDirectory 'native.stdout.log') `
        -RedirectStandardError (Join-Path $runDirectory 'native.stderr.log')
    $result.nativePid = $native.Id
    $result.nativeExitCode = Wait-BoundedProcess $native $TestTimeoutSeconds 'Native M1 self-test'
    $result.checks.nativeExitZero = $result.nativeExitCode -eq 0
    $result.checks.reportExists = Test-Path -LiteralPath $nativeReport -PathType Leaf
    if (-not $result.checks.reportExists) { throw 'Native process did not produce M1_Match_SelfTest.json.' }
    $reportInfo = Get-Item -LiteralPath $nativeReport
    $result.nativeReportMtimeUtc = $reportInfo.LastWriteTimeUtc.ToString('o')
    $result.nativeReportSha256 = (Get-FileHash -LiteralPath $nativeReport -Algorithm SHA256).Hash.ToLowerInvariant()
    $result.checks.freshReport = $reportInfo.LastWriteTimeUtc -ge $nativeStartedUtc -and
        ($null -eq $previousWriteUtc -or $reportInfo.LastWriteTimeUtc -gt $previousWriteUtc)
    $report = Get-Content -LiteralPath $nativeReport -Raw | ConvertFrom-Json
    $result.checks.nativeSchema = $report.schema -ceq 'Tread.M1.MatchSelfTest.v2' -and
        $report.producer -ceq 'Tread C++ RunDeterministicSelfTest'
    $result.checks.ok = $report.ok -is [bool] -and $report.ok
    $result.checks.twelveAcceptedRounds = @($report.acceptedRounds).Count -eq 12 -and
        (@($report.acceptedRounds) -join ',') -ceq ((1..12) -join ',')
    $result.checks.canonicalRoundTypes = (@($report.acceptedRoundTypes) -join ',') -ceq
        'PvE,PvE,PvP,PvP,PvP,PvP,PvP,PvP,PvP,PvP,PvP,Leader'
    $result.checks.gameOver = $report.gameOver -is [bool] -and $report.gameOver
    $result.checks.idempotency = $report.requestIdempotency -is [bool] -and $report.requestIdempotency -and
        $report.processedRequestCount -gt 0
    $result.checks.replay = $report.sameSeedReplayEqual -is [bool] -and $report.sameSeedReplayEqual -and
        $report.replaySignatureCrc32 -cmatch '^[0-9a-fA-F]{8}$'
    $result.checks.fourParticipants = $report.players -eq 4
    $result.checks.settledTwelveRounds = $report.roundsCompleted -eq 12
    $result.checks.allNamedChecksPassed = @($report.namedChecks.PSObject.Properties).Count -gt 0 -and
        @($report.namedChecks.PSObject.Properties | Where-Object { $_.Value -isnot [bool] -or -not $_.Value }).Count -eq 0
    $result.checks.allNativeStepsPassed = @($report.stepResults).Count -gt 0 -and
        @($report.stepResults | Where-Object { $_ -isnot [bool] -or -not $_ }).Count -eq 0
    $failed = @($result.checks.GetEnumerator() | Where-Object { -not $_.Value } | ForEach-Object { $_.Key })
    $result.ok = $failed.Count -eq 0
    if (-not $result.ok) { throw ('M1 regression failed: ' + ($failed -join ', ')) }
    Copy-Item -LiteralPath $nativeReport -Destination (Join-Path $runDirectory 'native-report.json')
}
catch {
    $result.error = $_.Exception.Message
    Write-Warning $result.error
}
finally {
    $result.finishedUtc = [DateTime]::UtcNow.ToString('o')
    $result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $runDirectory 'run.json') -Encoding utf8
    if ($ownsMutex) {
        $result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $runReport -Encoding utf8
        $runMutex.ReleaseMutex()
    }
    $runMutex.Dispose()
}
Write-Host ('M1_MATCH_NATIVE_SELFTEST=' + $(if ($result.ok) { 'PASS' } else { 'FAIL' }))
Write-Host "M1_MATCH_RUN_REPORT=$runReport"
if (-not $result.ok) { exit 1 }
exit 0
