[CmdletBinding()]
param(
    [string]$EngineRoot = $env:UE_ENGINE_ROOT,
    [ValidateRange(30, 7200)][int]$BuildTimeoutSeconds = 1800,
    [ValidateRange(15, 1800)][int]$TestTimeoutSeconds = 600,
    [switch]$SkipBuild
)

# M2 regression: regenerate pact/trait data, validate it, build TreadEditor, run the native
# -TreadM2SelfTest and gate on the produced report. The report's ok flag is authoritative:
# UnrealEditor-Cmd does not always propagate RequestExitWithStatus to the process exit code.

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$projectFile = Join-Path $projectRoot 'Tread.uproject'
$reports = Join-Path $projectRoot 'Saved/Reports'
$nativeReport = Join-Path $reports 'M2_Pact_SelfTest.json'
$runReport = Join-Path $reports 'M2_Pact_Run.json'
$runId = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$runDirectory = Join-Path $reports "M2_Runs/$runId"
New-Item -ItemType Directory -Path $runDirectory -Force | Out-Null
$result = [ordered]@{
    schema = 'Tread.M2.PactRun.v1'
    ok = $false
    runId = $runId
    startedUtc = [DateTime]::UtcNow.ToString('o')
    project = $projectFile
    nativeReport = $nativeReport
    checks = [ordered]@{}
    logs = $runDirectory
}

function Quote-Argument([string]$Value) {
    if ($Value -match '["%\r\n]') { throw "Unsupported command-line character in: $Value" }
    return '"' + $Value + '"'
}

function Wait-BoundedProcess($Process, [int]$Seconds, [string]$Label) {
    $watch = [Diagnostics.Stopwatch]::StartNew()
    while (-not $Process.WaitForExit(1000)) {
        if ($watch.Elapsed.TotalSeconds -ge $Seconds) {
            & taskkill.exe /PID $Process.Id /T /F | Out-Null
            throw "$Label exceeded ${Seconds}s; logs retained in $runDirectory"
        }
    }
    $Process.WaitForExit()
    $Process.Refresh()
    return $Process.ExitCode
}

try {
    if (-not $EngineRoot) {
        $association = (Get-Content -LiteralPath $projectFile -Raw | ConvertFrom-Json).EngineAssociation
        $installation = Get-ItemProperty -LiteralPath "HKLM:/SOFTWARE/EpicGames/Unreal Engine/$association" -ErrorAction SilentlyContinue
        if ($installation) { $EngineRoot = $installation.InstalledDirectory }
    }
    if (-not $EngineRoot) { throw 'Pass -EngineRoot <UE_5.8 directory> or set UE_ENGINE_ROOT.' }
    $EngineRoot = (Resolve-Path -LiteralPath $EngineRoot).Path
    $buildBat = Join-Path $EngineRoot 'Engine/Build/BatchFiles/Build.bat'
    $editorCmd = Join-Path $EngineRoot 'Engine/Binaries/Win64/UnrealEditor-Cmd.exe'

    Write-Host 'Generating and validating M2 pact/trait data...'
    & python (Join-Path $projectRoot 'Tools/m4/import_stronghold_data.py') *> (Join-Path $runDirectory 'generate.log')
    $result.checks.dataGenerated = $LASTEXITCODE -eq 0
    & python (Join-Path $projectRoot 'Tools/m4/validate_n1_data.py') *> (Join-Path $runDirectory 'validate.log')
    $result.checks.dataValidated = $LASTEXITCODE -eq 0
    if (-not ($result.checks.dataGenerated -and $result.checks.dataValidated)) { throw "M2 data generation/validation failed; see $runDirectory" }

    # document/175-176: the on-equip ops and the per-item combat procs are post-processing stages; run them
    # after the importer so a regenerated ItemCatalog keeps the runtime wiring.
    & python (Join-Path $projectRoot 'Tools/m4/wire_item_ops.py') *> (Join-Path $runDirectory 'wire_ops.log')
    $result.checks.itemOpsWired = $LASTEXITCODE -eq 0
    & python (Join-Path $projectRoot 'Tools/m4/wire_item_procs.py') *> (Join-Path $runDirectory 'wire_procs.log')
    $result.checks.itemProcsWired = $LASTEXITCODE -eq 0
    if (-not ($result.checks.itemOpsWired -and $result.checks.itemProcsWired)) { throw "Item wiring failed; see $runDirectory" }

    if (-not $SkipBuild) {
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
    }

    $previousWriteUtc = $null
    if (Test-Path -LiteralPath $nativeReport) { $previousWriteUtc = (Get-Item -LiteralPath $nativeReport).LastWriteTimeUtc }
    $nativeStartedUtc = [DateTime]::UtcNow
    $result.nativeStartedUtc = $nativeStartedUtc.ToString('o')
    $ueLog = Join-Path $runDirectory 'UnrealEditor-Cmd.log'
    $nativeArguments = @(
        (Quote-Argument $projectFile), '/Game/Tread/Maps/M1_Match_Graybox',
        '-game', '-TreadM2SelfTest', '-TreadSeed=20260926', '-nullrhi', '-unattended',
        '-nosplash', '-nosound', '-NoLiveCoding', '-stdout', '-FullStdOutLogOutput',
        (Quote-Argument "-abslog=$ueLog")
    )
    $result.nativeCommand = (Quote-Argument $editorCmd) + ' ' + ($nativeArguments -join ' ')
    Write-Host 'Running native M2 pact self-test...'
    $native = Start-Process -FilePath $editorCmd -ArgumentList $nativeArguments `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $runDirectory 'native.stdout.log') `
        -RedirectStandardError (Join-Path $runDirectory 'native.stderr.log')
    $result.nativeExitCode = Wait-BoundedProcess $native $TestTimeoutSeconds 'Native M2 self-test'
    $result.checks.reportExists = Test-Path -LiteralPath $nativeReport -PathType Leaf
    if (-not $result.checks.reportExists) { throw 'Native process did not produce M2_Pact_SelfTest.json.' }
    $reportInfo = Get-Item -LiteralPath $nativeReport
    $result.nativeReportSha256 = (Get-FileHash -LiteralPath $nativeReport -Algorithm SHA256).Hash.ToLowerInvariant()
    $result.checks.freshReport = $reportInfo.LastWriteTimeUtc -ge $nativeStartedUtc.AddSeconds(-2) -and
        ($null -eq $previousWriteUtc -or $reportInfo.LastWriteTimeUtc -gt $previousWriteUtc)
    $report = Get-Content -LiteralPath $nativeReport -Raw -Encoding utf8 | ConvertFrom-Json
    $result.checks.nativeSchema = $report.schema -ceq 'Tread.M2.PactSelfTest.v1' -and $report.producer -ceq 'Tread C++ RunM2PactSelfTest'
    $failedNamed = @($report.namedChecks.PSObject.Properties | Where-Object { $_.Value -isnot [bool] -or -not $_.Value } | ForEach-Object { $_.Name })
    $result.failedNamedChecks = $failedNamed
    $result.namedCheckCount = @($report.namedChecks.PSObject.Properties).Count
    $result.checks.allNamedChecksPassed = $result.namedCheckCount -gt 0 -and $failedNamed.Count -eq 0
    $result.checks.reportOk = $report.ok -is [bool] -and $report.ok
    Copy-Item -LiteralPath $nativeReport -Destination (Join-Path $runDirectory 'native-report.json')
    $failed = @($result.checks.GetEnumerator() | Where-Object { -not $_.Value } | ForEach-Object { $_.Key })
    $result.ok = $failed.Count -eq 0
    if (-not $result.ok) { throw ('M2 regression failed: ' + ($failed -join ', ') + ' ' + ($failedNamed -join ', ')) }
}
catch {
    $result.error = $_.Exception.Message
    Write-Warning $result.error
}
finally {
    $result.finishedUtc = [DateTime]::UtcNow.ToString('o')
    $result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $runDirectory 'run.json') -Encoding utf8
    $result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $runReport -Encoding utf8
}
Write-Host ('M2_PACT_NATIVE_SELFTEST=' + $(if ($result.ok) { 'PASS' } else { 'FAIL' }))
Write-Host "M2_PACT_RUN_REPORT=$runReport"
if (-not $result.ok) { exit 1 }
exit 0
