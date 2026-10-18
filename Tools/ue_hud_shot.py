"""Copy the Unreal Editor window, HUD included, straight from the desktop into a PNG.

The HUD is Slate, so HighResShot never contains it, and `shot showui` goes through FScreenshotRequest / Slate's
window screenshot, which crashed the editor twice (2026-10-14 with the game frozen, 2026-10-17 with the window
minimised / just restored). This takes a plain desktop copy of the editor window: no UE code involved, nothing
queued inside the engine.

    python Tools/ue_hud_shot.py Saved/Screenshots/HUD_Battle.png [--hwnd 1234] [--no-raise]

The editor window must be visible and not minimised. It is matched by window class ("UnrealWindow", largest one -
the editor also owns small popups of the same class) instead of by title, which is localised.

Why Python and not the earlier .ps1: this host's pwsh sees a different window rect for the same handle (DPI
virtualisation) and cannot enumerate the editor window at all, while ctypes here gets the physical rect.
"""
import ctypes
import struct
import sys
import time
import zlib
from ctypes import wintypes

SRCCOPY = 0x00CC0020
DIB_RGB_COLORS = 0


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


def find_editor():
    """Largest visible, non-minimised window of class UnrealWindow."""
    user32 = ctypes.windll.user32
    found = {"hwnd": 0, "area": 0}

    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        name = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, name, 256)
        if name.value != "UnrealWindow":
            return True
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        area = (rect.right - rect.left) * (rect.bottom - rect.top)
        if area > found["area"]:
            found["hwnd"], found["area"] = hwnd, area
        return True

    user32.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(visit), 0)
    return found["hwnd"]


def write_png(path, width, height, bgra):
    """bgra: raw top-down 32-bit pixels from GetDIBits (biHeight negative), BGRA order."""
    stride = width * 4
    rows = []
    for y in range(height):
        row = bgra[y * stride:(y + 1) * stride]
        rgb = bytearray(width * 3)
        rgb[0::3] = row[2::4]   # R
        rgb[1::3] = row[1::4]   # G
        rgb[2::3] = row[0::4]   # B
        rows.append(b"\x00" + bytes(rgb))
    raw = b"".join(rows)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
           + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))
    with open(path, "wb") as handle:
        handle.write(png)


def capture(hwnd, out, raise_window=True):
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    if raise_window:
        # Only un-minimise. SW_RESTORE also UN-MAXIMISES a maximised window (it shrinks back to the normal size),
        # so it must never be sent to a window that is simply maximised.
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)          # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.9)
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError("GetWindowRect failed")
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width < 320 or height < 240:
        raise RuntimeError("editor window too small: %dx%d" % (width, height))

    screen = user32.GetDC(0)
    memory = gdi32.CreateCompatibleDC(screen)
    bitmap = gdi32.CreateCompatibleBitmap(screen, width, height)
    gdi32.SelectObject(memory, bitmap)
    if not gdi32.BitBlt(memory, 0, 0, width, height, screen, rect.left, rect.top, SRCCOPY):
        raise RuntimeError("BitBlt failed")
    info = BITMAPINFO()
    info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    info.bmiHeader.biWidth = width
    info.bmiHeader.biHeight = -height          # top-down
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    info.bmiHeader.biCompression = 0
    buffer = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(memory, bitmap, 0, height, buffer, ctypes.byref(info), DIB_RGB_COLORS)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(memory)
    user32.ReleaseDC(0, screen)
    write_png(out, width, height, buffer.raw)
    return width, height


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    out = argv[1]
    hwnd = 0
    if "--hwnd" in argv:
        hwnd = int(argv[argv.index("--hwnd") + 1])
    if not hwnd:
        hwnd = find_editor()
    if not hwnd:
        print("no visible, restored Unreal Editor window: restore it (not minimised) and retry, or pass --hwnd")
        return 2
    width, height = capture(hwnd, out, raise_window="--no-raise" not in argv)
    print("saved %s (%dx%d)" % (out, width, height))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
