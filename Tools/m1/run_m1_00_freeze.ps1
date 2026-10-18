param(
    [switch]$Verify
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$runner = Join-Path $projectRoot 'Tools\ue_run.py'
$script = Join-Path $projectRoot 'Tools\m1\00_freeze_m0_baseline.py'
$args = @($runner, $script)
if ($Verify) { $args += '--verify' }
& python @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not $Verify) {
    & python (Join-Path $projectRoot 'Tools\ue_run.py') (Join-Path $projectRoot 'Tools\m1\01_validate_graybox_entry.py')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
