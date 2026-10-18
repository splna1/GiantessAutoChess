#!/usr/bin/env python3
"""Host-side driver of Tools/m4/ue_capture_avatars.py: batches, VRAM guard, host-side finishing of the PNGs.

    python Tools/m4/avatar_capture_driver.py capture --batch 0 [--size 10] [--sleep 6]
    python Tools/m4/avatar_capture_driver.py capture --ids char_001,char_002
    python Tools/m4/avatar_capture_driver.py all [--from N]       every batch in turn (stops on a VRAM or phase failure)
    python Tools/m4/avatar_capture_driver.py refine               measure head-top gap / side clipping of every raw shot,
                                                                  write Saved/Reports/M4_Avatar_Overrides.json, list the ids
                                                                  to recapture (uniform head-top margin for all 112)
    python Tools/m4/avatar_capture_driver.py finish               downsample avatars_raw/*.png -> Saved/Staging/avatars/*.png
    python Tools/m4/avatar_capture_driver.py sheet                contact sheet -> Saved/Screenshots/M4_Avatar_ContactSheet.png

A batch is: stage -> sim -> (wait) -> shoot -> endsim -> (wait) -> clear -> FlushThumbnailScenes -> editor_release gc.
The studio / setup / restore phases are run by hand (they switch maps and must be their own calls).
Never closes or restarts the editor.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
RUN = [sys.executable, str(ROOT / "Tools/ue_run.py")]
CAP = str(ROOT / "Tools/m4/ue_capture_avatars.py")
REL = str(ROOT / "Tools/m4/editor_release.py")
RAW = ROOT / "Saved/Staging/avatars_raw"
OUT = ROOT / "Saved/Staging/avatars"
REPORT = ROOT / "Saved/Reports/M4_Avatar_Capture_Report.json"
SHEET = ROOT / "Saved/Screenshots/M4_Avatar_ContactSheet.png"
ROSTER = ROOT / "Content/Data/Generated/CharacterRosterMap.json"
OVERRIDES = ROOT / "Saved/Reports/M4_Avatar_Overrides.json"
TARGET_TOP = 0.075            # the head top should sit this fraction below the top edge (all characters)
TOP_TOLERANCE = 0.025
VRAM_LIMIT = 6300
OUT_SIZE = 256   # avatars are shown at 62-140 px (no mips): 256 px keeps them crisp without aliasing


def ue(script, *args, code=None):
    cmd = RUN + [script] + list(args) if code is None else RUN + ["-c", code]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT))
    ok = p.returncode == 0
    last = [l for l in p.stdout.splitlines() if l.strip()][-3:]
    print("  [%s] rc=%d %s" % (" ".join(a for a in args[:1]) or "-c", p.returncode, " | ".join(last)[:240]))
    return ok, p.stdout


def vram():
    out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader"], capture_output=True, text=True)
    return int(out.stdout.strip().split()[0])


def arg(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def capture(argv):
    wait = float(arg(argv, "--sleep", 6))
    sel = ["--ids", arg(argv, "--ids")] if "--ids" in argv else ["--batch", arg(argv, "--batch"), "--size", arg(argv, "--size", "10")]
    if vram() > VRAM_LIMIT:
        print("VRAM %d MiB above %d: run editor_release.py reload (own call), then gc" % (vram(), VRAM_LIMIT))
        return False
    ok, _ = ue(CAP, "stage", *sel)
    ok = ok and ue(CAP, "sim")[0]
    if ok:
        time.sleep(wait)
        ok = ue(CAP, "shoot")[0]
    ue(CAP, "endsim")
    time.sleep(3)
    ue(CAP, "clear")
    ue(None, code='import unreal; unreal.SystemLibrary.execute_console_command(None, "Tread.FlushThumbnailScenes")')
    ue(REL, "gc")
    print("  VRAM %d MiB" % vram())
    return ok


def content_box(path, thr=40):
    """(top row, left clipped, right clipped) of the model against the flat backdrop colour."""
    im = Image.open(path).convert("RGB")
    w, h = im.size
    bg = im.getpixel((6, 6))
    px = im.load()

    def differs(x, y):
        c = px[x, y]
        return abs(c[0] - bg[0]) + abs(c[1] - bg[1]) + abs(c[2] - bg[2]) > thr

    top = h
    for y in range(h):
        if sum(1 for x in range(0, w, 2) if differs(x, y)) >= 4:
            top = y
            break
    head_rows = range(0, int(h * 0.5), 4)
    left = sum(1 for y in head_rows if differs(0, y))
    right = sum(1 for y in head_rows if differs(w - 1, y))
    return top, left, right, bg


def refine(_argv=None):
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8")) if OVERRIDES.exists() else {}
    redo, notes = [], {}
    for cid, e in sorted(report.items()):
        if e.get("status") != "SHOT":
            redo.append(cid)
            notes[cid] = "status " + str(e.get("status"))
            continue
        top, left, right, bg = content_box(RAW / (cid + ".png"))
        h = 1024
        gap = top / h
        e["measuredTopGap"], e["clippedSideRows"] = round(gap, 3), [left, right]
        ov = overrides.setdefault(cid, {})
        changed = False
        if abs(gap - TARGET_TOP) > TOP_TOLERANCE:
            cm_per_px = e["frameCm"] / h
            span = e["headZ"] - e["chestZ"]
            wanted = e["headTop"] - (top - TARGET_TOP * h) * cm_per_px
            # Tall ears / props / antennae may reach far above the head: never frame more than 1.25 spans above the
            # head bone (they are cropped instead) and never less than 0.35 spans (the face stays whole).
            ov["top"] = round(min(max(wanted, e["headZ"] + 0.35 * span), e["headZ"] + 1.25 * span), 2)
            changed = abs(ov["top"] - e["headTop"]) > 0.4
        if left > 3 or right > 3:
            ov["scale"] = round(min(1.3, float(ov.get("scale", 1.0)) * 1.1), 3)
            changed = changed or float(ov["scale"]) < 1.3
        if changed:
            redo.append(cid)
            notes[cid] = "gap=%.3f clip=%d/%d -> top=%s scale=%s" % (gap, left, right, ov.get("top"), ov.get("scale"))
        else:
            overrides.pop(cid, None) if not ov else None
    REPORT.write_text(json.dumps(report, ensure_ascii=True, indent=1), encoding="utf-8")
    OVERRIDES.write_text(json.dumps(overrides, ensure_ascii=True, indent=1), encoding="utf-8")
    print("refine: recapture %d: %s" % (len(redo), ",".join(redo)))
    for cid in redo:
        print("   ", cid, notes[cid])
    return redo


def finish(_argv=None):
    OUT.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in sorted(RAW.glob("char_*.png")):
        im = Image.open(p).convert("RGB")
        im.resize((OUT_SIZE, OUT_SIZE), Image.LANCZOS).save(OUT / p.name)
        n += 1
    print("finish: %d avatars -> %s" % (n, OUT))


def sheet(_argv=None, cols=14, cell=160):
    rows = json.loads(ROSTER.read_text(encoding="utf-8-sig"))["characters"]
    ids = [r["characterId"] for r in rows]
    rws = (len(ids) + cols - 1) // cols
    img = Image.new("RGB", (cols * cell, rws * (cell + 14)), (20, 20, 20))
    draw = ImageDraw.Draw(img)
    black = []
    for i, cid in enumerate(ids):
        x, y = (i % cols) * cell, (i // cols) * (cell + 14)
        p = OUT / (cid + ".png")
        if p.exists():
            tile = Image.open(p).convert("RGB")
            if sum(tile.resize((1, 1)).getpixel((0, 0))) < 15:
                black.append(cid)
            img.paste(tile.resize((cell, cell), Image.LANCZOS), (x, y + 14))
        draw.text((x + 3, y + 1), cid[5:], fill=(255, 255, 0))
    SHEET.parent.mkdir(parents=True, exist_ok=True)
    img.save(SHEET)
    print("sheet: %s black=%s missing=%s" % (SHEET, black, [c for c in ids if not (OUT / (c + ".png")).exists()]))


def main(argv):
    cmd = argv[0] if argv else ""
    if cmd == "capture":
        return 0 if capture(argv[1:]) else 1
    if cmd == "all":
        size = int(arg(argv, "--size", "10"))
        total = (len(json.loads(ROSTER.read_text(encoding="utf-8-sig"))["characters"]) + size - 1) // size
        for n in range(int(arg(argv, "--from", 0)), total):
            print("batch %d/%d" % (n, total))
            if not capture(["--batch", str(n), "--size", str(size)]):
                return 1
        return 0
    if cmd == "refine":
        refine()
        return 0
    if cmd == "finish":
        return finish() or 0
    if cmd == "sheet":
        return sheet() or 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
