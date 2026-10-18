param(
    [string]$Map = '/Game/Tread/Maps/M3_Paris_Match',
    [string]$Prefix = 'Saved\Screenshots\Esc_185'
)
$project = 'E:\AI\Tread\Tread'
$exe = 'G:\epicgame\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WIn {
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr d, uint f);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint x, uint y, uint d, IntPtr e);
    [DllImport("user32.dll")] public static extern void keybd_event(byte k, byte s, uint f, IntPtr e);
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
function Shot([IntPtr]$h, [string]$path) {
    $r = New-Object WIn+RECT
    [WIn]::GetWindowRect($h, [ref]$r) | Out-Null
    $w = $r.Right - $r.Left; $hh = $r.Bottom - $r.Top
    $bmp = New-Object System.Drawing.Bitmap $w, $hh
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $dc = $g.GetHdc(); [WIn]::PrintWindow($h, $dc, 2) | Out-Null; $g.ReleaseHdc($dc); $g.Dispose()
    $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
    "SHOT $path"
}
$p = Start-Process -FilePath $exe -ArgumentList @((Join-Path $project 'Tread.uproject'), $Map, '-game', '-windowed', '-ResX=1280', '-ResY=720', '-NoSplash') -WorkingDirectory $project -PassThru
$h = [IntPtr]::Zero
for ($i = 0; $i -lt 120; $i++) {
    Start-Sleep -Seconds 1
    $q = Get-Process UnrealEditor -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if ($q) { $h = $q.MainWindowHandle; break }
}
Start-Sleep -Seconds 40
[WIn]::SetForegroundWindow($h) | Out-Null
Start-Sleep -Seconds 1
Shot $h (Join-Path $project "$Prefix`_login.png")
# Click the login button: window pixels (the 1280x720 window is ~1296x759 with frame).
$r = New-Object WIn+RECT; [WIn]::GetWindowRect($h, [ref]$r) | Out-Null
[WIn]::SetCursorPos($r.Left + 1000, $r.Top + 30 + 540) | Out-Null
Start-Sleep -Milliseconds 300
[WIn]::mouse_event(0x0002, 0, 0, 0, [IntPtr]::Zero)
[WIn]::mouse_event(0x0004, 0, 0, 0, [IntPtr]::Zero)
Start-Sleep -Seconds 3
Shot $h (Join-Path $project "$Prefix`_campaign.png")
# Escape -> overlay.
[WIn]::keybd_event(0x1B, 0, 0, [IntPtr]::Zero)
[WIn]::keybd_event(0x1B, 0, 2, [IntPtr]::Zero)
Start-Sleep -Seconds 2
Shot $h (Join-Path $project "$Prefix`_menu.png")
# Escape again -> cancel.
[WIn]::keybd_event(0x1B, 0, 0, [IntPtr]::Zero)
[WIn]::keybd_event(0x1B, 0, 2, [IntPtr]::Zero)
Start-Sleep -Seconds 2
Shot $h (Join-Path $project "$Prefix`_closed.png")
Get-Process UnrealEditor -ErrorAction SilentlyContinue | Stop-Process -Force
