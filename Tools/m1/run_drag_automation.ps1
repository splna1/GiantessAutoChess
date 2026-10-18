[CmdletBinding()]
param(
    [string]$EngineRoot = 'G:/epicgame/UE_5.8',
    [ValidateRange(30, 1800)][int]$TimeoutSeconds = 240
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$projectFile = Join-Path $projectRoot 'Tread.uproject'
$editorCmd = Join-Path $EngineRoot 'Engine/Binaries/Win64/UnrealEditor-Cmd.exe'
$testName = 'Tread.M1.Drag.ReleaseAndTargets'
$runId = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$runDirectory = Join-Path $projectRoot "Saved/Reports/M1_Drag_Runs/$runId"
$exportDirectory = Join-Path $runDirectory 'AutomationReport'
$ueLog = Join-Path $runDirectory 'UnrealEditor-Cmd.log'
$summaryFile = Join-Path $projectRoot 'Saved/Reports/M1_Drag_Automation_Run.json'
New-Item -ItemType Directory -Path $runDirectory -Force | Out-Null

foreach ($required in @($projectFile, $editorCmd)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required file: $required" }
}

function Quote-Argument([string]$Value) {
    if ($Value -match '["\r\n]') { throw "Unsupported command-line character in: $Value" }
    return '"' + $Value + '"'
}

$arguments = @(
    (Quote-Argument $projectFile),
    '-unattended', '-nop4', '-nosplash', '-nosound', '-nullrhi', '-NoLiveCoding',
    '-stdout', '-FullStdOutLogOutput',
    (Quote-Argument "-ExecCmds=Automation RunTests $testName"),
    (Quote-Argument '-TestExit=Automation Test Queue Empty'),
    (Quote-Argument "-ReportExportPath=$exportDirectory"),
    (Quote-Argument "-abslog=$ueLog")
)
$summary = [ordered]@{
    schema = 'Tread.M1.DragAutomationRun.v1'
    test = $testName
    runId = $runId
    startedUtc = [DateTime]::UtcNow.ToString('o')
    command = (Quote-Argument $editorCmd) + ' ' + ($arguments -join ' ')
    log = $ueLog
    automationReport = Join-Path $exportDirectory 'index.json'
    stdout = Join-Path $runDirectory 'stdout.log'
    stderr = Join-Path $runDirectory 'stderr.log'
    passed = $false
}

try {
    Write-Host "Running $testName through UnrealEditor-Cmd..."
    $process = Start-Process -FilePath $editorCmd -ArgumentList $arguments `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $summary.stdout -RedirectStandardError $summary.stderr
    $summary.pid = $process.Id
    $watch = [Diagnostics.Stopwatch]::StartNew()
    while (-not $process.WaitForExit(1000)) {
        if ($watch.Elapsed.TotalSeconds -ge $TimeoutSeconds) {
            & taskkill.exe /PID $process.Id /T /F | Out-Null
            throw "Automation exceeded ${TimeoutSeconds}s; inspect $runDirectory"
        }
    }
    $process.WaitForExit()
    $process.Refresh()
    $summary.exitCode = $process.ExitCode
    $summary.elapsedSeconds = [math]::Round($watch.Elapsed.TotalSeconds, 2)

    if (-not (Test-Path -LiteralPath $ueLog -PathType Leaf)) { throw 'Editor log was not written.' }
    $logText = Get-Content -LiteralPath $ueLog -Raw
    $summary.testStarted = $logText.Contains("Test Started. Name={ReleaseAndTargets} Path={$testName}")
    $summary.testSucceeded = $logText.Contains("Test Completed. Result={Success} Name={ReleaseAndTargets} Path={$testName}")
    $summary.queueEmpty = $logText -match 'Automation Test Queue Empty [1-9][0-9]* tests performed'
    $summary.reportExists = Test-Path -LiteralPath $summary.automationReport -PathType Leaf
    $summary.reportSucceeded = $false
    if ($summary.reportExists) {
        $engineReport = Get-Content -LiteralPath $summary.automationReport -Raw | ConvertFrom-Json
        $matchingTests = @($engineReport.tests | Where-Object { $_.fullTestPath -ceq $testName })
        $summary.reportSucceeded = $engineReport.succeeded -eq 1 -and $engineReport.failed -eq 0 -and `
            $matchingTests.Count -eq 1 -and $matchingTests[0].state -ceq 'Success' -and `
            $matchingTests[0].errors -eq 0
    }
    $summary.passed = $summary.exitCode -eq 0 -and $summary.testStarted -and $summary.testSucceeded -and `
        $summary.queueEmpty -and $summary.reportSucceeded
    if (-not $summary.passed) { throw "Automation did not pass all evidence checks; inspect $runDirectory" }
}
catch {
    $summary.error = $_.Exception.Message
}
finally {
    $summary.finishedUtc = [DateTime]::UtcNow.ToString('o')
    $summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $summaryFile -Encoding utf8
    Write-Host "Result: $($summary.passed); report: $summaryFile"
    Write-Host "Engine log: $ueLog"
}

if (-not $summary.passed) { exit 1 }
