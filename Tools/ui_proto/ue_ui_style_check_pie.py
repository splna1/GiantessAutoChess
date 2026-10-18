"""UI style acceptance (host-side, document/157 section 6): the front-end states of the HTML prototype shots
(Saved/UIPrototype/shots, defined in Tools/ui_proto/shoot.py) plus four HUD phases, shot in PIE and copied next to
them for a side by side review. Drives Tools/ui_proto/ue_ui_style_check.py (editor-side) phase by phase.

    python Tools/ui_proto/ue_ui_style_check_pie.py                   # all shots, HighResShot 1920x1080
    python Tools/ui_proto/ue_ui_style_check_pie.py --seed-progress   # stages 1-5 cleared like the HTML prototype
    python Tools/ui_proto/ue_ui_style_check_pie.py --only 05,07,hud_bp
    python Tools/ui_proto/ue_ui_style_check_pie.py --no-hud          # front end only
    python Tools/ui_proto/ue_ui_style_check_pie.py --no-front        # HUD only
    python Tools/ui_proto/ue_ui_style_check_pie.py --capture showui  # see "Capture" below

Needs a TreadEditor build with UTreadFrontEndWidget's test hooks (ue_ui_style_check.py check fails fast otherwise) and
the editor window visible (not minimised). Keep the mouse pointer out of the PIE viewport while it runs: a real hover
would add to the forced one.

Capture. The default is "HighResShot 1920x1080" (never "shot showui" while the game is frozen, memory
tread-shot-showui-crash). WARNING: HighResShot reads the game viewport render target only (UGameViewportClient::
ProcessScreenShots: bShowUI=false skips Slate), so UMG widgets are NOT in it, and the front end plus the match HUD are
UMG. The first thing the run does is a probe: two different front-end screens must not come out as the same picture;
if they do, the run stops and says so. --capture showui then sends "shot showui" instead: editor-viewport sized
(not 1920x1080), never combined with slomo 0.0001, refused while the editor is minimised, never re-sent.

Campaign progress. The HTML prototype shows stages 1-5 cleared, 6 at the front, 7+ blocked. The only way to get that is
ATreadM1MatchController::SetCampaignProgressForTest, which WRITES Saved/SaveGames/TreadCampaign.sav. Without
--seed-progress nothing is written and the select-screen shots show the real progress (see PROGRESS_DEPENDENT). The save
file is snapshotted at the start and put back at the end whatever happens (same as Tools/m4/m4_selftest_pie.py).

Output: Saved/Reports/UI_Style_Check.json, Saved/UIPrototype/ue_shots/<name>.png (names = HTML shot names, hud_*.png).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "Tools"))
from ue_mcp import UeMcp  # noqa: E402

try:
    from PIL import Image, ImageChops, ImageStat
except ImportError:  # the probe and the HTML diff are then skipped
    Image = None

EDITOR_TOOLSET = "EditorToolset.EditorAppToolset"
PY = sys.executable
RUN = os.path.join(ROOT, "Tools", "ue_run.py")
TEST = os.path.join(ROOT, "Tools", "ui_proto", "ue_ui_style_check.py")
SHOT_DIR = os.path.join(ROOT, "Saved", "Screenshots", "WindowsEditor")
OUT_DIR = os.path.join(ROOT, "Saved", "UIPrototype", "ue_shots")
HTML_DIR = os.path.join(ROOT, "Saved", "UIPrototype", "shots")
STATE = os.path.join(ROOT, "Saved", "Reports", "UI_Style_Check_state.json")
REPORT = os.path.join(ROOT, "Saved", "Reports", "UI_Style_Check.json")
SAVE = os.path.join(ROOT, "Saved", "SaveGames", "TreadCampaign.sav")
SAVE_BACKUP = os.path.join(ROOT, "Saved", "Reports", "UI_Style_Check_TreadCampaign.sav.bak")

CAPTURE_COMMANDS = {"highres": "HighResShot 1920x1080", "showui": "shot showui"}
SLOW = "slomo 0.3"       # battle pace of the HUD run (same as the battle presentation check's evidence run)
FREEZE = "slomo 0.0001"

# (name, settle seconds between setting the state and the shot). Names and order follow Tools/ui_proto/shoot.py SHOTS
# without 11 (HTML-only annotation layer). Frozen states need ~0.5 s (1-2 frames); the others let real-time animation end:
# login focus bar (0.9 s delay + 0.42 s), the login success sequence (2.05 s), the dossier / tooltip reveals.
FRONT_STATES = [
    ("01_loading_mid", 0.8), ("02_loading_done", 0.8), ("03_login", 2.0), ("04_login_success", 3.2),
    ("05_select", 1.2), ("06_select_hover", 1.6), ("07_select_detail", 1.8), ("08_select_cleared", 1.6),
    ("09_select_locked", 1.6), ("10_sortie", 1.2), ("12_trans_scan", 0.6), ("13_trans_slab_in", 0.6),
    ("14_trans_slab_mid", 0.6), ("15_trans_blinds", 0.6), ("16_trans_slab_out", 0.6),
]
HUD_SHOTS = ("hud_bp", "hud_prep", "hud_battle", "hud_result")
HUD_PHASE = {"hud_bp": ("PRE_MATCH_BP",), "hud_prep": ("PREPARATION",), "hud_battle": ("BATTLE",),
             "hud_result": ("SETTLEMENT", "GAME_OVER")}
# Select-screen content depends on the campaign progress (HTML: 5 cleared). 15 shows the first front stage on its sortie page.
PROGRESS_DEPENDENT = {"05_select", "06_select_hover", "07_select_detail", "08_select_cleared", "09_select_locked",
                      "14_trans_slab_mid", "15_trans_blinds", "16_trans_slab_out"}
UI_PROBE_MIN_DIFF = 0.03   # mean abs difference of two 64x36 thumbnails; two board-only shots differ by ~0, two screens by 0.2+
HTML_PROGRESS = 5


def rel(path):
    return os.path.relpath(path, ROOT).replace("\\", "/")


def ue(*args, timeout=600):
    """One editor-side phase. The last 'UISTYLE <phase> <json>' line of its output comes back as a dict."""
    proc = subprocess.run([PY, RUN, TEST] + [str(a) for a in args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError("ui style check %s failed (exit %d)\n%s\n%s"
                           % (args, proc.returncode, (proc.stdout or "")[-2000:], (proc.stderr or "")[-800:]))
    rows = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip().startswith("UISTYLE ")]
    if not rows:
        return {}
    return json.loads(rows[-1].split(" ", 2)[2])


def screenshots():
    if not os.path.isdir(SHOT_DIR):
        return set()
    return {f for f in os.listdir(SHOT_DIR) if f.lower().endswith(".png")}


def wait_shot(before, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        new = screenshots() - before
        if new:
            path = os.path.join(SHOT_DIR, max(new, key=lambda f: os.path.getmtime(os.path.join(SHOT_DIR, f))))
            size = os.path.getsize(path)
            time.sleep(1.5)
            if size > 0 and os.path.getsize(path) == size:
                return path
        time.sleep(1.0)
    raise RuntimeError("no new screenshot in " + SHOT_DIR)


def editor_minimised():
    """True when the Unreal Editor main window is minimised: it then renders ~3 fps whatever the throttle setting."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    found = []

    def visit(hwnd, _):
        length = user32.GetWindowTextLengthW(hwnd)
        if length and user32.IsWindowVisible(hwnd):
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            if buffer.value.endswith(("Unreal Editor", "虚幻编辑器")):
                found.append(bool(user32.IsIconic(hwnd)))
        return True

    user32.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(visit), 0)
    # A locked workstation (no input desktop) stops presenting as well.
    desktop = user32.OpenInputDesktop(0, False, 0x0100)
    if desktop:
        user32.CloseDesktop(desktop)
    return any(found) or not desktop


def cue_times(digest):
    """Digest: 'winner=..;' then 'kind:unit>target@time/amount/hp[S];' (kind 0 attack, 1 died, 2 frozen, 3 victory)."""
    attacks, deaths = [], []
    for part in digest.split(";"):
        if ":" not in part or "@" not in part:
            continue
        kind = part.split(":", 1)[0]
        t = float(part.split("@", 1)[1].split("/", 1)[0])
        (attacks if kind == "0" else deaths if kind == "1" else []).append(t)
    return sorted(attacks), sorted(deaths)


# ------------------------------------------------------------------------------------------------ images
def image_size(path):
    if Image is None:
        return None
    with Image.open(path) as img:
        return list(img.size)


def coarse(path):
    with Image.open(path) as img:
        return img.convert("RGB").resize((64, 36), Image.BILINEAR)


def coarse_diff(path_a, path_b):
    """Mean abs difference (0..1) of two 64x36 thumbnails; None without Pillow or a missing file."""
    if Image is None or not (os.path.exists(path_a) and os.path.exists(path_b)):
        return None
    diff = ImageChops.difference(coarse(path_a), coarse(path_b))
    return round(sum(ImageStat.Stat(diff).mean) / (3 * 255.0), 3)


# ------------------------------------------------------------------------------------------------ save file guard
class SaveGuard:
    """Snapshot of the campaign save slot. SetCampaignProgressForTest and a won campaign stage write it; restore()
    puts the file back exactly as it was (or removes it when there was none). With backup=True the original also goes
    to Saved/Reports so a killed driver does not lose it."""

    def __init__(self, backup):
        self.original = None
        if os.path.exists(SAVE):
            with open(SAVE, "rb") as handle:
                self.original = handle.read()
            if backup:
                os.makedirs(os.path.dirname(SAVE_BACKUP), exist_ok=True)
                with open(SAVE_BACKUP, "wb") as handle:
                    handle.write(self.original)

    def restore(self):
        now = None
        if os.path.exists(SAVE):
            with open(SAVE, "rb") as handle:
                now = handle.read()
        if now == self.original:
            return "unchanged"
        if self.original is None:
            os.remove(SAVE)
            return "removed"
        with open(SAVE, "wb") as handle:
            handle.write(self.original)
        return "restored"


# ------------------------------------------------------------------------------------------------ shooting
class Shooter:
    def __init__(self, capture):
        self.capture = capture
        self.command = CAPTURE_COMMANDS[capture]

    def shoot(self, name, freeze_resume=None):
        """One shot of the game viewport copied to Saved/UIPrototype/ue_shots/<name>.png. With freeze_resume (a slomo
        command) the game is frozen for the shot and resumed after it, HighResShot only: a UI shot is never taken
        while frozen."""
        frozen = bool(freeze_resume) and self.capture == "highres"
        if frozen:
            ue("console", FREEZE)
            time.sleep(0.8)
        try:
            before = screenshots()
            ue("console", self.command)
            try:
                shot = wait_shot(before, timeout=20)
            except RuntimeError:
                if self.capture == "showui":
                    raise RuntimeError("no 'shot showui' file after 20 s; not sending it again (memory tread-shot-showui-crash): "
                                       "check the editor window, maybe restart the editor")
                # "shot" is dropped now and then when the viewport skips a frame: ask once more.
                ue("console", self.command)
                shot = wait_shot(before, timeout=20)
        finally:
            if frozen:
                ue("console", freeze_resume)
        os.makedirs(OUT_DIR, exist_ok=True)
        target = os.path.join(OUT_DIR, name + ".png")
        shutil.copyfile(shot, target)
        print("  shot %s -> %s" % (os.path.basename(shot), rel(target)))
        return {"path": target, "source": os.path.basename(shot), "size": image_size(target)}


def shot_row(name, kind, shot):
    row = {"name": name, "kind": kind, "file": rel(shot["path"]), "size": shot["size"], "source": shot["source"]}
    html = os.path.join(HTML_DIR, name + ".png")
    if kind == "frontend":
        row["htmlRef"] = rel(html) if os.path.exists(html) else None
        row["htmlDiff"] = coarse_diff(shot["path"], html)
    return row


# ------------------------------------------------------------------------------------------------ front end
def check_capture_shows_ui(shooter, report):
    """Two different front-end screens must give two different pictures; if not, this capture command has no UI in it."""
    ue("state", "01_loading_mid")
    time.sleep(1.0)
    a = shooter.shoot("_probe_loading")
    ue("state", "03_login")
    time.sleep(1.5)
    b = shooter.shoot("_probe_login")
    diff = coarse_diff(a["path"], b["path"])
    probe = {"diff": diff, "minDiff": UI_PROBE_MIN_DIFF, "capture": shooter.capture,
             "uiVisible": None if diff is None else diff >= UI_PROBE_MIN_DIFF,
             "files": [rel(a["path"]), rel(b["path"])]}
    report["uiProbe"] = probe
    if diff is None:
        report["warnings"].append("UI probe skipped: Pillow is not installed, cannot tell whether the shots contain the UI")
    elif not probe["uiVisible"]:
        raise RuntimeError(
            "capture command %r shows no UI: the loading screen and the login screen came out as the same picture "
            "(thumbnail diff %.3f < %.2f, see %s). HighResShot renders the 3D scene only, UMG is not in it. "
            "Re-run with --capture showui (normal speed, editor window in front)."
            % (shooter.command, diff, UI_PROBE_MIN_DIFF, probe["files"]))


def run_front(report, shooter, wanted, probe_first):
    if probe_first:
        check_capture_shows_ui(shooter, report)
    for name, settle in FRONT_STATES:
        if not wanted(name):
            continue
        state = ue("state", name)
        row = {"name": name, "kind": "frontend", "expected": state.get("expected"), "screen": state.get("screen"),
               "hookError": state.get("error", ""), "stateOk": bool(state.get("ok"))}
        time.sleep(settle)
        after = ue("screen").get("screen")
        row["screenAtShot"] = after
        row["stateOk"] = row["stateOk"] and after in (state.get("expected") or [])
        if state.get("error"):
            print("  %s: hook failed: %s" % (name, state["error"]))
        else:
            row.update(shot_row(name, "frontend", shooter.shoot(name)))
        if name in PROGRESS_DEPENDENT and not report["progress"]["seeded"]:
            row["note"] = "real campaign progress, not the HTML's %d cleared stages (rerun with --seed-progress)" % HTML_PROGRESS
        report["shots"].append(row)
        print("  %s screen=%s ok=%s" % (name, after, row["stateOk"]))


# ------------------------------------------------------------------------------------------------ HUD
def poll(tag="hud"):
    return ue("poll", tag)


def wait_active(timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        p = poll()
        if p.get("active"):
            return p
        time.sleep(0.3)
    raise RuntimeError("presentation never became active")


def run_hud(report, shooter, wanted, stage):
    def hud_row(name, step_row, phase_now):
        row = {"name": name, "kind": "hud", "phase": phase_now, "frontEnd": step_row.get("frontEnd"),
               "step": step_row}
        row["phaseOk"] = any(str(phase_now).endswith(p) for p in HUD_PHASE[name])
        # Leaving R0 must have put the front end away (doc 157 4.1).
        row["frontEndHidden"] = step_row.get("frontEnd") in ("hidden", "none")
        return row

    def hud_shot(name, step_row, phase_now, freeze_resume):
        row = hud_row(name, step_row, phase_now)
        if wanted(name):
            row.update(shot_row(name, "hud", shooter.shoot(name, freeze_resume)))
            report["shots"].append(row)
            print("  %s phase=%s ok=%s" % (name, phase_now, row["phaseOk"]))

    step = ue("hud", "bp", stage)
    report["hudSteps"]["bp"] = step
    if not step.get("stageAccepted"):
        report["warnings"].append("campaign stage %s was not accepted (locked?): the HUD run is a free match" % stage)
    time.sleep(1.5)
    hud_shot("hud_bp", step, step.get("phase"), SLOW)

    step = ue("hud", "prep")
    report["hudSteps"]["prep"] = step
    time.sleep(1.5)
    hud_shot("hud_prep", step, step.get("phase"), SLOW)

    step = ue("hud", "deploy")
    report["hudSteps"]["deploy"] = step
    time.sleep(1.0)
    p = wait_active()
    with open(STATE, encoding="utf-8") as handle:
        digest = json.load(handle)["runs"]["hud"]["digest"]
    attacks, _ = cue_times(digest)
    at = (attacks[min(2, len(attacks) - 1)] + 0.4) if attacks else 2.5
    while True:
        p = poll()
        if not p.get("active") or p.get("clock", 0) >= at:
            break
        time.sleep(0.25)
    hud_shot("hud_battle", step, p.get("phase"), SLOW)

    ue("console", "slomo 1")
    deadline = time.time() + 120
    p = poll()
    while time.time() < deadline and not p["phase"].endswith(("SETTLEMENT", "GAME_OVER")):
        time.sleep(1.0)
        p = poll()
    time.sleep(1.5)
    hud_shot("hud_result", step, p.get("phase"), None)
    report["hudSteps"]["battle"] = {"clockTarget": round(at, 2), "digestAttacks": len(attacks)}


# ------------------------------------------------------------------------------------------------ main
def parse_args():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--capture", choices=sorted(CAPTURE_COMMANDS), default="highres")
    ap.add_argument("--only", default="", help="comma list of state names / number prefixes / hud_* names (default: all)")
    ap.add_argument("--no-front", action="store_true", help="skip the front-end shots")
    ap.add_argument("--no-hud", action="store_true", help="skip the HUD shots")
    ap.add_argument("--no-probe", action="store_true", help="skip the 'does the capture contain the UI' probe")
    ap.add_argument("--seed-progress", nargs="?", const=HTML_PROGRESS, type=int, default=None, metavar="N",
                    help="SetCampaignProgressForTest(N) (default %d) before the shots; writes the campaign save, restored at the end" % HTML_PROGRESS)
    ap.add_argument("--hud-stage", type=int, default=0, help="campaign stage of the HUD run (0 = free match; must be unlocked)")
    return ap.parse_args()


def main():
    args = parse_args()
    only = [o.strip() for o in args.only.split(",") if o.strip()]

    def wanted(name):
        return not only or any(name == o or name.startswith(o) for o in only)

    front_wanted = not args.no_front and any(wanted(n) for n, _ in FRONT_STATES)
    hud_wanted = not args.no_hud and any(wanted(n) for n in HUD_SHOTS)
    if not (front_wanted or hud_wanted):
        print("nothing to shoot (check --only / --no-front / --no-hud)")
        return 1
    minimised = editor_minimised()
    if minimised and args.capture == "showui":
        print("The Unreal Editor window is minimised: 'shot showui' needs it drawn. Restore the window and retry.")
        return 1
    seeded = args.seed_progress is not None
    report = {"schema": "Tread.UI.StyleCheck.v1", "ok": False, "capture": args.capture,
              "captureCommand": CAPTURE_COMMANDS[args.capture], "editorMinimised": minimised,
              "progress": {"seeded": seeded, "requested": args.seed_progress, "htmlExpects": "stages 1-%d cleared, %d at the front, rest blocked"
                           % (HTML_PROGRESS, HTML_PROGRESS + 1)},
              "hudStage": args.hud_stage, "uiProbe": {"skipped": True}, "shots": [], "hudSteps": {}, "warnings": [], "error": ""}
    if minimised:
        report["warnings"].append("editor window was minimised at the start: it renders ~3 fps, shots may lag the state")
    if front_wanted and not seeded:
        report["warnings"].append(
            "campaign progress is the real one (no --seed-progress): select-screen shots %s differ from the HTML by design"
            % sorted(PROGRESS_DEPENDENT))

    guard = SaveGuard(backup=seeded or args.hud_stage != 0)
    shooter = Shooter(args.capture)
    checked = pie_started = False
    client = None
    try:
        ue("check")
        checked = True
        ue("load")
        client = UeMcp(timeout=600)
        client.call("StartPIE", {"options": {"bSimulate": False, "playMode": "PlayMode_InViewPort", "warmupSeconds": 2}},
                    toolset=EDITOR_TOOLSET)
        pie_started = True
        print("  PIE started")
        time.sleep(5)
        probe = ue("probe")
        report["probe"] = probe
        if front_wanted and (not probe.get("frontEnd") or probe.get("screen") == "hidden"):
            raise RuntimeError("no visible front end widget in PIE (%s): it exists on the M3_Paris map only, and not when the "
                               "editor command line has -TreadSkipFrontEnd / -TreadM1SelfTest / -TreadM1UITest / "
                               "-TreadM1Capture= / -TreadCampaign= ..." % json.dumps(probe, sort_keys=True))
        report["progress"]["conqueredBefore"] = (probe.get("stages") or {}).get("conquered")
        if seeded:
            seed = ue("seed", args.seed_progress)
            report["progress"]["conqueredAfterSeed"] = seed.get("conquered")
            report["progress"]["frontStage"] = next((i for i in seed.get("unlocked", []) if i not in seed.get("conquered", [])), None)
        if front_wanted:
            run_front(report, shooter, wanted, probe_first=not args.no_probe)
        if hud_wanted:
            run_hud(report, shooter, wanted, args.hud_stage)
    except Exception as exc:  # noqa: BLE001
        report["error"] = "%s: %s" % (type(exc).__name__, exc)
        print("  FAILED: " + report["error"])
    finally:
        if pie_started:
            try:
                ue("cleanup")
            except Exception as exc:  # noqa: BLE001
                print("  cleanup skipped: %s" % str(exc)[:200])
            try:
                client.call("StopPIE", {}, toolset=EDITOR_TOOLSET)
                print("  PIE stopped")
            except Exception as exc:  # noqa: BLE001
                print("  StopPIE failed: %s" % str(exc)[:200])
            time.sleep(3)
        report["saveGame"] = guard.restore()
        if checked:
            try:
                ue("restore")
            except Exception as exc:  # noqa: BLE001
                print("  restore failed: %s" % str(exc)[:200])
    finish(report, front_wanted, hud_wanted, wanted)
    return 0 if report["ok"] else 1


def finish(report, front_wanted, hud_wanted, wanted):
    shots = {row["name"]: row for row in report["shots"]}
    want_front = [n for n, _ in FRONT_STATES if front_wanted and wanted(n)]
    want_hud = [n for n in HUD_SHOTS if hud_wanted and wanted(n)]
    probe = report.get("uiProbe", {})
    checks = {
        "front_states_set": all(shots.get(n, {}).get("stateOk") for n in want_front),
        "front_shots_captured": all(shots.get(n, {}).get("file") for n in want_front),
        "capture_contains_ui": probe.get("uiVisible") is not False,
        "hud_phases_reached": all(shots.get(n, {}).get("phaseOk") for n in want_hud),
        "hud_shots_captured": all(shots.get(n, {}).get("file") for n in want_hud),
        "front_end_hidden_in_hud": all(shots.get(n, {}).get("frontEndHidden") for n in want_hud),
    }
    report["checks"] = checks
    report["ok"] = all(checks.values()) and not report["error"]
    with open(REPORT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=1)
    print("UI style check ok=%s failed=%s shots=%d report=%s" % (report["ok"], [k for k, v in checks.items() if not v],
                                                                  sum(1 for r in report["shots"] if r.get("file")), rel(REPORT)))
    for warning in report["warnings"]:
        print("  warning: " + warning)


if __name__ == "__main__":
    sys.exit(main())
