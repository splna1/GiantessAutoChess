param(
    [int]$Warmup = 6,
    [int]$Count = 5,
    [int]$Interval = 4,
    [string]$Prefix = 'Saved\Screenshots\Audience_179'
)
$project = 'E:\AI\Tread\Tread'
$exe = 'G:\epicgame\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32Aud {
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdcBlt, uint nFlags);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
$args = @(
    (Join-Path $project 'Tread.uproject'), '/Game/Tread/Maps/M3_Paris_Match', '-game',
    '-TreadSkipFrontEnd', '-TreadM2Capture=BATTLE', '-TreadAudienceView',
    '-ResX=1600', '-ResY=900', '-windowed', '-NoSplash'
)
$p = Start-Process -FilePath $exe -ArgumentList $args -WorkingDirectory $project -PassThru
Start-Sleep -Seconds $Warmup
$handle = [IntPtr]::Zero
for ($i = 0; $i -lt 20 -and $handle -eq [IntPtr]::Zero; $i++) {
    Start-Sleep -Seconds 1
    $proc = Get-Process -Id $p.Id -ErrorAction SilentlyContinue
    if ($proc) { $handle = $proc.MainWindowHandle }
}
for ($shot = 0; $shot -lt $Count -and $handle -ne [IntPtr]::Zero; $shot++) {
    [Win32Aud]::SetForegroundWindow($handle) | Out-Null
    Start-Sleep -Milliseconds 500
    $rect = New-Object Win32Aud+RECT
    if ([Win32Aud]::GetWindowRect($handle, [ref]$rect)) {
        $w = $rect.Right - $rect.Left; $h = $rect.Bottom - $rect.Top
        if ($w -gt 200 -and $h -gt 200) {
            $bmp = New-Object System.Drawing.Bitmap $w, $h
            $g = [System.Drawing.Graphics]::FromImage($bmp)
            $hdc = $g.GetHdc()
            $ok = [Win32Aud]::PrintWindow($handle, $hdc, 2)
            $g.ReleaseHdc($hdc); $g.Dispose()
            if ($ok) {
                $path = Join-Path $project ("$Prefix" + "_$shot.png")
                $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
                "SHOT $path"
            }
            $bmp.Dispose()
        }
    }
    Start-Sleep -Seconds $Interval
}
if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force }
"DONE"
