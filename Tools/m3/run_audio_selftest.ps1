[CmdletBinding()]
param(
    [string]$EngineRoot = $env:UE_ENGINE_ROOT,
    [ValidateRange(30, 1800)][int]$BuildTimeoutSeconds = 1200,
    [ValidateRange(15, 600)][int]$TestTimeoutSeconds = 240,
    [switch]$SkipBuild
)

# Audio acceptance (document/177): runs the game without -nosound / -nullrhi so the audio device and the
# BGM / SFX / voice / footstep catalogue are actually exercised. The report's ok flag is authoritative.

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$projectFile = Join-Path $projectRoot 'Tread.uproject'
$reports = Join-Path $projectRoot 'Saved/Reports'
$nativeReport = Join-Path $reports 'Audio_SelfTest.json'
$runReport = Join-Path $reports 'Audio_Run.json'
$runId = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$runDirectory = Join-Path $reports "Audio_Runs/$runId"
New-Item -ItemType Directory -Path $runDirectory -Force | Out-Null
$result = [ordered]@{
    schema = 'Tread.Audio.Run.v1'
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

    if (-not $SkipBuild) {
        $buildCommand = (Quote-Argument $buildBat) + ' TreadEditor Win64 Development ' +
            (Quote-Argument "-Project=$projectFile") + ' -WaitMutex -NoHotReloadFromIDE -NoLiveCoding'
        $result.buildCommand = $buildCommand
        $build = Start-Process -FilePath $env:ComSpec -ArgumentList ('/d /s /c "' + $buildCommand + '"') `
            -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $runDirectory 'build.stdout.log') `
            -RedirectStandardError (Join-Path $runDirectory 'build.stderr.log')
        $result.buildExitCode = Wait-BoundedProcess $build $BuildTimeoutSeconds 'TreadEditor build'
        $result.checks.buildExitZero = $result.buildExitCode -eq 0
        if (-not $result.checks.buildExitZero) { throw "TreadEditor build failed ($($result.buildExitCode))" }
    }

    if (Test-Path -LiteralPath $nativeReport) { Remove-Item -LiteralPath $nativeReport -Force }
    $nativeStartedUtc = [DateTime]::UtcNow
    $result.nativeStartedUtc = $nativeStartedUtc.ToString('o')
    $ueLog = Join-Path $runDirectory 'UnrealEditor-Cmd.log'
    $nativeArguments = @(
        (Quote-Argument $projectFile), '/Game/Tread/Maps/M1_Match_Graybox',
        '-game', '-TreadAudioSelfTest', '-TreadSkipFrontEnd', '-unattended', '-nosplash',
        '-NoLiveCoding', '-stdout', '-FullStdOutLogOutput', (Quote-Argument "-abslog=$ueLog")
    )
    $result.nativeCommand = (Quote-Argument $editorCmd) + ' ' + ($nativeArguments -join ' ')
    $native = Start-Process -FilePath $editorCmd -ArgumentList $nativeArguments `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $runDirectory 'native.stdout.log') `
        -RedirectStandardError (Join-Path $runDirectory 'native.stderr.log')
    $result.nativeExitCode = Wait-BoundedProcess $native $TestTimeoutSeconds 'Audio self-test'
    $result.checks.reportExists = Test-Path -LiteralPath $nativeReport -PathType Leaf
    if (-not $result.checks.reportExists) { throw 'The audio self-test did not produce Audio_SelfTest.json.' }
    $report = Get-Content -LiteralPath $nativeReport -Raw -Encoding utf8 | ConvertFrom-Json
    $result.checks.nativeSchema = $report.schema -ceq 'Tread.Audio.SelfTest.v1'
    $failedNamed = @($report.namedChecks.PSObject.Properties | Where-Object { $_.Value -isnot [bool] -or -not $_.Value } | ForEach-Object { $_.Name })
    $result.failedNamedChecks = $failedNamed
    $result.namedCheckCount = @($report.namedChecks.PSObject.Properties).Count
    $result.checks.allNamedChecksPassed = $result.namedCheckCount -gt 0 -and $failedNamed.Count -eq 0
    $result.checks.reportOk = $report.ok -is [bool] -and $report.ok
    $result.bgm = "$($report.bgmPlayed)/$($report.bgmTotal)"
    $result.sfx = "$($report.sfxPlayed)/$($report.sfxTotal)"
    $result.voiceCharacter = $report.voiceCharacter
    Copy-Item -LiteralPath $nativeReport -Destination (Join-Path $runDirectory 'native-report.json')
    $failed = @($result.checks.GetEnumerator() | Where-Object { -not $_.Value } | ForEach-Object { $_.Key })
    $result.ok = $failed.Count -eq 0
    if (-not $result.ok) { throw ('Audio acceptance failed: ' + ($failed -join ', ') + ' ' + ($failedNamed -join ', ')) }
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
Write-Host ('AUDIO_NATIVE_SELFTEST=' + $(if ($result.ok) { 'PASS' } else { 'FAIL' }))
Write-Host "AUDIO_RUN_REPORT=$runReport"
if (-not $result.ok) { exit 1 }
exit 0
