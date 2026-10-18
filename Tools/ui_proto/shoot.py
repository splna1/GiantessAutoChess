"""Headless-Chrome review shots of the UI prototype (files only; review them with a Sonnet sub-agent).

Usage: python Tools/ui_proto/shoot.py [name ...]
Writes Saved/UIPrototype/shots/<name>.png and prints console errors per shot.
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HTML = os.path.join(ROOT, "Saved", "UIPrototype", "Tread_UI_Prototype.html")
OUT = os.path.join(ROOT, "Saved", "UIPrototype", "shots")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

SHOTS = {
    "01_loading_mid": ("s=loading&prog=0.62&still=1", 4000),
    "02_loading_done": ("s=loading&prog=1&hold=1&still=1", 5000),
    "03_login": ("s=login&still=1&hold=1", 3000),
    "04_login_success": ("s=login&still=1&hold=1&user=%E4%BC%8A%E4%B8%87%E8%AF%BA%E5%A8%83&login=success", 6000),
    "05_select": ("s=select&still=1&hold=1", 3000),
    "06_select_hover": ("s=select&still=1&hold=1&hover=7", 3500),
    "07_select_detail": ("s=select&still=1&hold=1&sel=6&hover=10", 4000),
    "08_select_cleared": ("s=select&still=1&hold=1&sel=3", 4000),
    "09_select_locked": ("s=select&still=1&hold=1&sel=12", 4000),
    "10_sortie": ("s=sortie&still=1&hold=1&sel=6", 14000),
    "11_ue_overlay": ("s=login&still=1&hold=1&ue=1", 4000),
    "12_trans_scan": ("s=login&from=loading&trans=scan&tp=0.55&still=1&hold=1&prog=1", 3000),
    "13_trans_slab_in": ("s=select&from=login&trans=slab&tp=0.22&still=1&hold=1", 3000),
    "14_trans_slab_mid": ("s=select&from=login&trans=slab&tp=0.5&still=1&hold=1", 3000),
    "15_trans_blinds": ("s=sortie&from=select&trans=blinds&tp=0.55&still=1&hold=1&sel=6", 3000),
    "16_trans_slab_out": ("s=select&from=login&trans=slab&tp=0.8&still=1&hold=1", 3000),
}


def shoot(name, frag, budget):
    url = "file:///" + HTML.replace("\\", "/") + "#" + frag
    png = os.path.join(OUT, name + ".png")
    with tempfile.TemporaryDirectory() as prof:
        cmd = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--mute-audio",
               "--user-data-dir=" + prof, "--window-size=1920,1080", "--force-device-scale-factor=1",
               "--virtual-time-budget=%d" % budget, "--enable-logging=stderr", "--v=0",
               "--screenshot=" + png, url]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    errs = [l for l in r.stderr.splitlines() if "CONSOLE" in l or "Uncaught" in l]
    print(name, "ok" if os.path.exists(png) else "MISSING", *errs[:6], sep="\n  " if errs else " ")


def main():
    os.makedirs(OUT, exist_ok=True)
    names = sys.argv[1:] or list(SHOTS)
    for n in names:
        shoot(n, *SHOTS[n])


if __name__ == "__main__":
    main()
