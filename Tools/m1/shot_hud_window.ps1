# Standalone HUD capture (document/168) - PrintWindow variant so the game window does not need to be on top.
#
#   pwsh -File Tools/m1/shot_hud_window.ps1 [-Capture BATTLE] [-Seconds 30] [-Out Saved/Screenshots/HUD_Squad.png]
param(
    [string]$Capture = 'BATTLE',
    [int]$Seconds = 30,
    [string]$Out = 'Saved\Screenshots\HUD_Squad.png',
    [string]$Map = 'M3_Paris_Match',
    [string]$FlagName = 'TreadM2Capture'
)

$project = 'E:\AI\Tread\Tread'
$exe = 'G:\epicgame\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$outPath = Join-Path $project $Out
New-Item -ItemType Directory -Path (Split-Path -Parent $outPath) -Force | Out-Null

Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32Cap {
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdcBlt, uint nFlags);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
}
"@

$args = @(
    "$project\Tread.uproject", $Map, '-game', "-$FlagName=$Capture", '-TreadSkipFrontEnd',
    '-ResX=1600', '-ResY=900', '-windowed', '-NoSplash'
)
$p = Start-Process -FilePath $exe -ArgumentList $args -WorkingDirectory $project -PassThru
Start-Sleep -Seconds $Seconds
$p.Refresh()

$handle = $p.MainWindowHandle
if ($handle -eq [IntPtr]::Zero) {
    # window handle not published yet: look it up by process id
    for ($i = 0; $i -lt 20 -and $handle -eq [IntPtr]::Zero; $i++) {
        Start-Sleep -Seconds 1
        $proc = Get-Process -Id $p.Id -ErrorAction SilentlyContinue
        if ($proc) { $handle = $proc.MainWindowHandle }
    }
}

$shot = $false
if ($handle -ne [IntPtr]::Zero) {
    [Win32Cap]::SetForegroundWindow($handle) | Out-Null
    Start-Sleep -Milliseconds 600
    $rect = New-Object Win32Cap+RECT
    if ([Win32Cap]::GetWindowRect($handle, [ref]$rect)) {
        $w = $rect.Right - $rect.Left
        $h = $rect.Bottom - $rect.Top
        if ($w -gt 200 -and $h -gt 200) {
            $bmp = New-Object System.Drawing.Bitmap $w, $h
            $g = [System.Drawing.Graphics]::FromImage($bmp)
            $hdc = $g.GetHdc()
            $ok = [Win32Cap]::PrintWindow($handle, $hdc, 2)
            $g.ReleaseHdc($hdc)
            $g.Dispose()
            if ($ok) { $bmp.Save($outPath, [System.Drawing.Imaging.ImageFormat]::Png); $shot = $true }
            $bmp.Dispose()
        }
    }
}

if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force; Start-Sleep -Seconds 2 }
"HUD_SHOT=$shot path=$outPath exists=$(Test-Path $outPath)"
