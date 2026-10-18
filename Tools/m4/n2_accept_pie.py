"""N2 acceptance (host-side): drive the match to Preparation in PIE and shoot the board.

Runs the whole sequence as one repeatable command instead of six by hand:

    load map -> StartPIE -> stock the board with the 12 MMD characters -> freeze and HighResShot
    -> StopPIE -> restore the previous map

The shot has to come from the game viewport: the editor viewport capture that the older N2 checks used
does not draw PIE runtime actors at all (memory: tread-viewport-capture-lies), which is why the board
looked empty for a whole debugging round.  Two shots are taken at the same frozen frame and camera,
the second with every MMD body hidden, so their difference is exactly what the MMD units draw.

    python Tools/m4/n2_accept_pie.py

Output: Saved/Screenshots/N2_Accept_Board.png, N2_Accept_Board_NoMMD.png, N2_Accept_DiffMask.png,
Saved/Reports/N2_Accept_Diff.json and the census in Saved/Reports/N2_RenderTruth.json.

    python Tools/m4/n2_accept_pie.py --set vrm   (M4: sixteen roster VRMs, outputs M4_Accept_*, M4_RenderTruth.json)
"""
import json
import os
import shutil
import subprocess
import sys
import time

from PIL import Image, ImageChops

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "Tools"))
from ue_mcp import UeMcp  # noqa: E402

EDITOR_TOOLSET = "EditorToolset.EditorAppToolset"
PY = sys.executable
RUN = os.path.join(ROOT, "Tools", "ue_run.py")
TRUTH = os.path.join(ROOT, "Tools", "m4", "n2_render_truth.py")
SHOT_DIR = os.path.join(ROOT, "Saved", "Screenshots", "WindowsEditor")
SHOTS = os.path.join(ROOT, "Saved", "Screenshots")


SET = ["--set", "vrm"] if "--set" in sys.argv and sys.argv[sys.argv.index("--set") + 1] == "vrm" else []
NAME = "M4_Accept" if SET else "N2_Accept"


def out_png():
    return os.path.join(SHOTS, NAME + "_Board.png")


def hidden_png():
    return os.path.join(SHOTS, NAME + ("_Board_NoVRM.png" if SET else "_Board_NoMMD.png"))


def diff_png():
    return os.path.join(SHOTS, NAME + "_DiffMask.png")


def ue(script, *args, timeout=900):
    cmd = [PY, RUN, script] + list(args) + SET
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    tail = [line for line in (proc.stdout or "").splitlines() if line.strip().startswith("TRUTH")]
    print("  %s %s -> %s" % (os.path.basename(script), " ".join(args), "; ".join(tail) or "no TRUTH output"))
    if proc.returncode != 0:
        raise RuntimeError("%s %s failed (exit %d)\n%s\n%s"
                           % (script, args, proc.returncode, proc.stdout[-1500:], proc.stderr[-800:]))
    return proc.stdout


def screenshots():
    if not os.path.isdir(SHOT_DIR):
        return set()
    return {f for f in os.listdir(SHOT_DIR) if f.lower().startswith("highresscreenshot") and f.endswith(".png")}


def wait_shot(before, timeout=90):
    """Return the path of the HighResShot file that appeared since `before`."""
    deadline = time.time() + timeout
    new = screenshots() - before
    while not new and time.time() < deadline:
        time.sleep(2)
        new = screenshots() - before
    if not new:
        raise RuntimeError("HighResShot produced no new file in " + SHOT_DIR)
    newest = max(new, key=lambda f: os.path.getmtime(os.path.join(SHOT_DIR, f)))
    return os.path.join(SHOT_DIR, newest)


def main():
    before = screenshots()
    # slomo is a console variable: a previous run that froze the match for its shot leaves the next
    # session with a zero time dilation, in which the presenter never ticks and never builds anything.
    ue(TRUTH, "unfreeze")
    ue(TRUTH, "load")
    client = UeMcp(timeout=600)
    client.call("StartPIE", {"options": {"bSimulate": False, "playMode": "PlayMode_InViewPort", "warmupSeconds": 2}},
                toolset=EDITOR_TOOLSET)
    print("  PIE started")
    try:
        time.sleep(5)
        ue(TRUTH, "stock")
        # The presenter builds its components from Tick(), so poll the host side until the board is
        # actually populated.  Python remote execution runs on the game thread and cannot sleep.
        deadline = time.time() + 90
        while True:
            out = ue(TRUTH, "census")
            line = next((l for l in out.splitlines() if l.startswith("TRUTH census")), "")
            bodies = int(line.split("bodies=")[1].split()[0]) if "bodies=" in line else 0
            if bodies > 0 or time.time() > deadline:
                break
            time.sleep(3)
        ue(TRUTH, "shoot")
        board = wait_shot(before)
        already = screenshots()
        ue(TRUTH, "shoot_hidden")
        hidden = wait_shot(already)
        os.makedirs(SHOTS, exist_ok=True)
        shutil.copyfile(board, out_png())
        shutil.copyfile(hidden, hidden_png())
        print("  shots %s -> %s, %s -> %s" % (os.path.basename(board), out_png(),
                                              os.path.basename(hidden), hidden_png()))
        # Same frame, same camera: everything that differs is what the MMD bodies draw.
        a = Image.open(out_png()).convert("RGB")
        b = Image.open(hidden_png()).convert("RGB")
        diff = ImageChops.difference(a, b).convert("L")
        mask = diff.point(lambda v: 255 if v > 8 else 0)
        changed = sum(mask.histogram()[255:])
        os.makedirs(os.path.dirname(diff_png()), exist_ok=True)
        mask.save(diff_png())
        json.dump({"schema": "Tread.N2.AcceptDiff.v1", "size": list(a.size), "changedPixels": changed,
                   "changedFraction": round(changed / float(a.size[0] * a.size[1]), 5)},
                  open(os.path.join(ROOT, "Saved", "Reports", NAME + "_Diff.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("  MMD bodies account for %d changed pixels (%.2f%% of frame)"
              % (changed, 100.0 * changed / (a.size[0] * a.size[1])))
    finally:
        ue(TRUTH, "unfreeze")
        try:
            UeMcp(timeout=300).call("StopPIE", {}, toolset=EDITOR_TOOLSET)
            print("  PIE stopped")
        except Exception as error:  # noqa: BLE001
            print("  StopPIE failed: %s" % error)
        time.sleep(3)
        ue(TRUTH, "restore")
    report = json.load(open(os.path.join(ROOT, "Saved", "Reports", "M4_RenderTruth.json" if SET else "N2_RenderTruth.json"), encoding="utf-8"))
    print(json.dumps(report.get("acceptShot", {}), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
