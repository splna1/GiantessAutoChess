param(
    [Parameter(Mandatory=$true)][ValidateSet('BP','SCOUT','PREPARE','BATTLE','RESULT')][string]$Stage,
    [Parameter(Mandatory=$true)][string]$OutputName
)

$ErrorActionPreference = 'Stop'
$root = 'E:\AI\Tread\Tread'
$ue = 'G:\epicgame\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$uproject = Join-Path $root 'Tread.uproject'
$python = 'python'

$running = Get-Process UnrealEditor -ErrorAction SilentlyContinue
if ($running) {
    $running | Stop-Process -Force
    Start-Sleep -Seconds 3
}

Start-Process -FilePath $ue -ArgumentList @(
    $uproject,
    '/Game/Tread/Maps/M1_Match_Graybox',
    '-TreadSeed=20260926',
    "-TreadM1Capture=$Stage",
    '-ResX=1920',
    '-ResY=1080'
) | Out-Null

$editor = $null
for ($i = 0; $i -lt 45; $i++) {
    Start-Sleep -Seconds 1
    $editor = Get-Process UnrealEditor -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($editor -and $editor.MainWindowHandle -ne 0) { break }
}
if (-not $editor) { throw 'UnrealEditor did not start' }
Start-Sleep -Seconds 8

& $python (Join-Path $root 'Tools/ue_mcp.py') call EditorToolset.EditorAppToolset StartPIE '{"options":{"bSimulate":false,"playMode":"PlayMode_InViewPort","warmupSeconds":2}}'
Start-Sleep -Seconds 3

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Win32CaptureStage {
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
}
"@
[Win32CaptureStage]::ShowWindow([IntPtr]$editor.MainWindowHandle, 3) | Out-Null
[Win32CaptureStage]::SetForegroundWindow([IntPtr]$editor.MainWindowHandle) | Out-Null
Start-Sleep -Seconds 2

& $python (Join-Path $root 'Tools/ue_mcp.py') call SlateInspectorToolset.SlateInspectorToolset Windows '{"action":"list"}'
& $python (Join-Path $root 'Tools/ue_mcp.py') call SlateInspectorToolset.SlateInspectorToolset Windows '{"action":"select","index":1}'
& $python (Join-Path $root 'Tools/ue_mcp.py') call SlateInspectorToolset.SlateInspectorToolset Observe '{"ref":"w1","maxDepth":5}'
& $python (Join-Path $root 'Tools/m1/capture_slate_screenshot.py') (Join-Path $root "Saved/Screenshots/$OutputName") w1

& $python (Join-Path $root 'Tools/ue_mcp.py') call EditorToolset.EditorAppToolset StopPIE '{}'
Start-Sleep -Seconds 2
Get-Process UnrealEditor -ErrorAction SilentlyContinue | Stop-Process -Force
