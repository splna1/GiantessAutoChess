"""N2 (b) retarget review (host-side): source vs retargeted clip, side by side, shot in PIE.

Runs Tools/m4/n2_retarget_review.py phase by phase as one repeatable command:

    load map -> stage rows -> StartPIE -> per row: frame, HighResShot -> StopPIE -> cleanup -> restore

then crops the figure band out of every row and stacks the 12 characters of one clip into a sheet,
so a clip can be judged on one image.

    python Tools/m4/n2_retarget_review_pie.py [--chars char_101,char_105]
    python Tools/m4/n2_retarget_review_pie.py --set vrm --chars char_002,char_003   (M4 roster VRMs: M4_Retarget_*)

Output: Saved/Screenshots/N2_Retarget_<Clip>_<NNN>.png per row, N2_Retarget_<Clip>_Sheet.png per clip,
Saved/Reports/N2_Retarget_Review.json.
"""
import json
import os
import shutil
import subprocess
import sys
import time

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "Tools"))
from ue_mcp import UeMcp  # noqa: E402

EDITOR_TOOLSET = "EditorToolset.EditorAppToolset"
PY = sys.executable
RUN = os.path.join(ROOT, "Tools", "ue_run.py")
REVIEW = os.path.join(ROOT, "Tools", "m4", "n2_retarget_review.py")
STATE = os.path.join(ROOT, "Saved", "Reports", "N2_Retarget_Review_state.json")
REPORT = os.path.join(ROOT, "Saved", "Reports", "N2_Retarget_Review.json")
SHOT_DIR = os.path.join(ROOT, "Saved", "Screenshots", "WindowsEditor")
SHOTS = os.path.join(ROOT, "Saved", "Screenshots")
# Vertical band of a 1440-high shot that holds the figures (camera 1 m up, pitch -2, 8.4 m away).
BAND = (0.30, 0.66)
SET = []  # ["--set", "vrm"] for the M4 roster VRMs
PREFIX = "N2_Retarget"
REPORT_NAME = "N2_Retarget_Review.json"


def ue(*args, timeout=900):
    proc = subprocess.run([PY, RUN, REVIEW] + list(args) + SET, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)
    out = proc.stdout or ""
    tail = [line.strip() for line in out.splitlines() if line.strip().startswith("N2_REVIEW")]
    print("  %s -> %s" % (" ".join(args), "; ".join(tail) or "no N2_REVIEW output"))
    # ue_run.py's exit code is unreliable (memory: tread-m2-runtime-notes); its status line is not.
    if proc.returncode != 0 or "status=OK" not in out:
        raise RuntimeError("%s failed (exit %d)\n%s\n%s" % (args, proc.returncode, out[-1500:], (proc.stderr or "")[-800:]))
    return out


def screenshots():
    if not os.path.isdir(SHOT_DIR):
        return set()
    return {f for f in os.listdir(SHOT_DIR) if f.lower().startswith("highresscreenshot") and f.endswith(".png")}


def wait_shot(before, timeout=90):
    """Path of the HighResShot file that appeared since `before`, once it has stopped growing."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        new = screenshots() - before
        if new:
            path = os.path.join(SHOT_DIR, max(new, key=lambda f: os.path.getmtime(os.path.join(SHOT_DIR, f))))
            size = os.path.getsize(path)
            time.sleep(1)
            if size and size == os.path.getsize(path):
                return path
        time.sleep(1)
    raise RuntimeError("HighResShot produced no new file in " + SHOT_DIR)


def row_png(row):
    clip, number = row.rsplit("_", 1)
    return os.path.join(SHOTS, "%s_%s_%s.png" % (PREFIX, clip, number))


def sheet(clip, rows):
    """Stack the figure band of each row of one clip, top to bottom in character order."""
    crops = []
    for row in rows:
        image = Image.open(row_png(row)).convert("RGB")
        w, h = image.size
        crops.append(image.crop((0, int(h * BAND[0]), w, int(h * BAND[1]))))
    out = Image.new("RGB", (crops[0].size[0], sum(c.size[1] for c in crops)))
    y = 0
    for crop in crops:
        out.paste(crop, (0, y))
        y += crop.size[1]
    path = os.path.join(SHOTS, "%s_%s_Sheet.png" % (PREFIX, clip))
    out.save(path)
    return path


def main():
    global SET, PREFIX, REPORT_NAME
    if "--set" in sys.argv and sys.argv[sys.argv.index("--set") + 1] == "vrm":
        SET, PREFIX, REPORT_NAME = ["--set", "vrm"], "M4_Retarget", "M4_Retarget_Review.json"
    if "--front" in sys.argv:
        # Same rows turned to face the camera: faces and fronts, which the default back view hides.
        SET, PREFIX, REPORT_NAME = SET + ["--front"], PREFIX + "Front", REPORT_NAME.replace(".json", "_Front.json")
    chars = []
    if "--chars" in sys.argv:
        chars = ["--chars", sys.argv[sys.argv.index("--chars") + 1]]
    if "--shots" in sys.argv:
        SET = SET + ["--shots", sys.argv[sys.argv.index("--shots") + 1]]
    ue("load")
    shots = {}
    try:
        ue("stage", *chars)
        rows = json.load(open(STATE, encoding="utf-8"))["rows"]
        client = UeMcp(timeout=600)
        client.call("StartPIE", {"options": {"bSimulate": False, "playMode": "PlayMode_InViewPort",
                                             "warmupSeconds": 2}}, toolset=EDITOR_TOOLSET)
        print("  PIE started")
        try:
            time.sleep(5)
            for row in rows:
                ue("frame", row)
                time.sleep(1.5)  # let the view target and the frozen poses reach a rendered frame
                before = screenshots()
                ue("shoot", row)
                shutil.copyfile(wait_shot(before), row_png(row))
                shots[row] = os.path.relpath(row_png(row), ROOT)
        finally:
            try:
                UeMcp(timeout=300).call("StopPIE", {}, toolset=EDITOR_TOOLSET)
                print("  PIE stopped")
            except Exception as error:  # noqa: BLE001
                print("  StopPIE failed: %s" % error)
            time.sleep(3)
        ue("cleanup")
    finally:
        ue("restore")
    by_clip = {}
    for row in shots:
        by_clip.setdefault(row.rsplit("_", 1)[0], []).append(row)
    sheets = {clip: os.path.relpath(sheet(clip, sorted(rows)), ROOT) for clip, rows in by_clip.items()}
    doc = {"schema": "Tread.N2.RetargetReview.v2", "capture": "HighResShot in PIE",
           "layout": "per row: 5 x Clukay416 source (left) | 5 x MMD retargeted (right), same clip times",
           "times": json.load(open(STATE, encoding="utf-8")).get("times"),
           "rows": len(shots), "shots": shots, "sheets": sheets}
    with open(os.path.join(os.path.dirname(REPORT), REPORT_NAME), "w", encoding="utf-8") as handle:
        json.dump(doc, handle, ensure_ascii=False, indent=1)
    print("  %d row shots, sheets %s" % (len(shots), sorted(sheets)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
