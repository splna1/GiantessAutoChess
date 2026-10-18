"""M4 acceptance (host-side): run Tools/m4/m4_selftest.py in PIE and capture the evidence shots.

    load -> StartPIE -> run (M4_SelfTest.json) -> for each evidence stage: stage + "shot showui"
    -> cleanup -> StopPIE -> restore the previous map

The campaign save (Saved/SaveGames/TreadCampaign.sav) is backed up first and put back afterwards, so the
owner's campaign progress survives the test hooks that overwrite it.

    python Tools/m4/m4_selftest_pie.py              # self-test + all evidence shots
    python Tools/m4/m4_selftest_pie.py --no-shots   # self-test only
    python Tools/m4/m4_selftest_pie.py --only campaign,world

Output: Saved/Reports/M4_SelfTest.json, Saved/Screenshots/M4_*.png (names in EVIDENCE).
"""
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "Tools"))
from ue_mcp import UeMcp  # noqa: E402

EDITOR_TOOLSET = "EditorToolset.EditorAppToolset"
PY = sys.executable
RUN = os.path.join(ROOT, "Tools", "ue_run.py")
TEST = os.path.join(ROOT, "Tools", "m4", "m4_selftest.py")
SHOT_DIR = os.path.join(ROOT, "Saved", "Screenshots", "WindowsEditor")
SHOTS = os.path.join(ROOT, "Saved", "Screenshots")
REPORT = os.path.join(ROOT, "Saved", "Reports", "M4_SelfTest.json")
SAVE = os.path.join(ROOT, "Saved", "SaveGames", "TreadCampaign.sav")
SAVE_BACKUP = os.path.join(ROOT, "Saved", "Reports", "M4_SelfTest_TreadCampaign.sav.bak")

EVIDENCE = [
    ("campaign", "M4_Campaign_Map_16Stages.png"),
    ("roster", "M4_Roster_100Card_Audit.png"),
    ("items", "M4_ItemCatalog_And_Clone.png"),
    ("tooltip", "M4_CardTooltip_EliteTraits.png"),
    ("world", "M4_WorldDomination.png"),
]


def ue(*args, timeout=900):
    proc = subprocess.run([PY, RUN, TEST] + list(args), capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)
    tail = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip().startswith("M4TEST")]
    print("  %s -> %s" % (" ".join(args), "; ".join(tail) or "no M4TEST output"))
    if proc.returncode != 0:
        raise RuntimeError("m4_selftest %s failed (exit %d)\n%s\n%s"
                           % (args, proc.returncode, proc.stdout[-2000:], proc.stderr[-800:]))
    return proc.stdout


def screenshots():
    if not os.path.isdir(SHOT_DIR):
        return set()
    return {f for f in os.listdir(SHOT_DIR) if f.lower().endswith(".png")}


def wait_shot(before, timeout=90):
    """Return the path of the screenshot that appeared since `before` (and finished writing)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        new = screenshots() - before
        if new:
            path = os.path.join(SHOT_DIR, max(new, key=lambda f: os.path.getmtime(os.path.join(SHOT_DIR, f))))
            size = os.path.getsize(path)
            time.sleep(1.5)
            if size > 0 and os.path.getsize(path) == size:
                return path
        time.sleep(1.5)
    raise RuntimeError("no new screenshot in " + SHOT_DIR)


def main():
    args = sys.argv[1:]
    shots = "--no-shots" not in args
    only = args[args.index("--only") + 1].split(",") if "--only" in args else [name for name, _ in EVIDENCE]
    had_save = os.path.exists(SAVE)
    if had_save:
        shutil.copyfile(SAVE, SAVE_BACKUP)
    ue("load")
    client = UeMcp(timeout=600)
    client.call("StartPIE", {"options": {"bSimulate": False, "playMode": "PlayMode_InViewPort", "warmupSeconds": 2}},
                toolset=EDITOR_TOOLSET)
    print("  PIE started")
    captured = {}
    try:
        time.sleep(5)
        if "--shots-only" not in args:
            ue("run", timeout=1800)
        if shots:
            for name, file_name in EVIDENCE:
                if name not in only:
                    continue
                ue("stage", name)
                time.sleep(3)  # let the HUD repaint and the board presenter rebuild
                before = screenshots()
                ue("shoot")
                shot = wait_shot(before)
                target = os.path.join(SHOTS, file_name)
                shutil.copyfile(shot, target)
                captured[name] = target
                print("  shot %s -> %s" % (os.path.basename(shot), file_name))
        ue("cleanup")
    finally:
        client.call("StopPIE", {}, toolset=EDITOR_TOOLSET)
        print("  PIE stopped")
        time.sleep(3)
        if had_save:
            shutil.copyfile(SAVE_BACKUP, SAVE)
        elif os.path.exists(SAVE):
            os.remove(SAVE)
        ue("restore")
    report = json.load(open(REPORT, encoding="utf-8")) if os.path.exists(REPORT) else {}
    print("M4 selftest ok=%s failed=%s shots=%s" % (report.get("ok"), [k for k, v in report.get("checks", {}).items() if not v],
                                                   sorted(captured)))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
