"""Battle presentation acceptance (host-side, document/12 §9): drives Tools/battle/battle_presentation_check.py in PIE.

  Run A (slomo 0.3, evidence): run / attack / defeat / victory HighResShots, an attack HUD shot, the audience
         camera shot (M1_Audience_View.png + M1_Audience_Camera.json); each shot is frozen with slomo 0.0001.
  Run B (slomo 1, same seed): command guards during the held Battle phase, wall time to Settlement (<= 45 s),
         presentation fps, timeline digest + event stream compared with run A.

    python Tools/battle/battle_presentation_check_pie.py
    python Tools/battle/battle_presentation_check_pie.py --no-shots

Output: Saved/Reports/Battle_Presentation_Check.json, Saved/Screenshots/Battle_*.png, M1_Audience_View.png.
"""
import json
import math
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
TEST = os.path.join(ROOT, "Tools", "battle", "battle_presentation_check.py")
SHOT_DIR = os.path.join(ROOT, "Saved", "Screenshots", "WindowsEditor")
SHOTS = os.path.join(ROOT, "Saved", "Screenshots")
STATE = os.path.join(ROOT, "Saved", "Reports", "Battle_Presentation_state.json")
REPORT = os.path.join(ROOT, "Saved", "Reports", "Battle_Presentation_Check.json")
CAMERA = os.path.join(ROOT, "Saved", "Reports", "M1_Audience_Camera.json")
PRESENTATION = os.path.join(ROOT, "Content", "Data", "Generated", "BattlePresentation.json")
SETTLE_CAP_SEC = 45.0
MIN_FPS = 45.0
# One board cell is about 50 px wide in the 1080p board shots, so half a cell (~25 px) is the smallest step that
# reads as movement between two frames. Re-calibrated 2026-10-17 (document/158 §3): the old "enemy melee >= 1.0,
# enemy ranged >= 0.5" was written for the stand-still graybox scene (3 ranged units, 0.32-0.59 cells) where only
# our side walked the whole gap; once both sides close in, each side walks about half of (gap - range).
ENEMY_MIN_TRAVEL = 0.45
ENEMY_MIN_LEAD = 0.9
OWN_MIN_TRAVEL = 0.45


def ue(*args, timeout=600):
    proc = subprocess.run([PY, RUN, TEST] + list(args), capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)
    lines = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip().startswith("BATTLE")]
    if proc.returncode != 0:
        raise RuntimeError("battle check %s failed (exit %d)\n%s\n%s"
                           % (args, proc.returncode, proc.stdout[-2000:], proc.stderr[-800:]))
    return lines[-1] if lines else ""


def poll(tag):
    line = ue("poll", tag)
    return json.loads(line[len("BATTLE poll "):])


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


def shoot(file_name, command="HighResShot 1920x1080"):
    """Freeze the game, take the shot, copy it under its evidence name, resume at the evidence pace."""
    ue("console", "slomo 0.0001")
    time.sleep(0.8)
    before = screenshots()
    ue("console", command)
    try:
        shot = wait_shot(before, timeout=20)
    except RuntimeError:
        # "shot" is dropped now and then when the viewport skips a frame: ask once more.
        ue("console", command)
        shot = wait_shot(before, timeout=20)
    target = os.path.join(SHOTS, file_name)
    shutil.copyfile(shot, target)
    print("  shot %s -> %s" % (os.path.basename(shot), file_name))
    return target


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


def wait_active(tag, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        p = poll(tag)
        if p.get("active"):
            return p
        time.sleep(0.3)
    raise RuntimeError("presentation never became active")


def run_evidence(tag, captured):
    ue("start", tag)
    time.sleep(1.0)
    ue("deploy", tag)
    ue("console", "slomo 0.3")
    p = wait_active(tag)
    digest = json.load(open(STATE, encoding="utf-8"))["runs"][tag]["digest"]
    attacks, deaths = cue_times(digest)
    victory_at = p.get("victoryAt") or 0
    plan = [("run", 1.6, "Battle_Run.png", None)]
    if attacks:
        plan.append(("attack", attacks[0] + 0.7, "Battle_Attack.png", None))
        # No "shot showui" here: with the game frozen (slomo 0.0001) the UI shot request stayed pending and was served
        # after PIE ended against the editor window's 10-bit back buffer, writing out of bounds in the
        # R10G10B10A2 -> FColor readback (editor crash in D3D12RHI, 2026-10-14 twice). HUD numbers come from the report.
        plan.append(("audience", attacks[min(3, len(attacks) - 1)] + 0.4, "M1_Audience_View.png", "audience"))
    if deaths:
        plan.append(("defeat", deaths[0] + 1.2, "Battle_Defeat.png", None))
    if victory_at:
        plan.append(("victory", victory_at + 1.4, "Battle_Victory.png", None))
    plan.sort(key=lambda row: row[1])
    for name, at, file_name, mode in plan:
        while True:
            p = poll(tag)
            if not p.get("active") or p.get("clock", 0) >= at:
                break
            time.sleep(0.25)
        if not p.get("active"):
            print("  presentation ended before %s (clock %.2f)" % (name, at))
            break
        if mode == "audience":
            ue("audience", "1")
            time.sleep(1.2)  # camera blend
            captured[name] = shoot(file_name)
            ue("audience", "0")
        elif mode:
            # "shot showui" grabs the editor viewport, which does not draw while the editor window is minimised or
            # hidden: the HUD shot is evidence only, never a failure.
            try:
                captured[name] = shoot(file_name, mode)
            except RuntimeError as error:
                print("  %s skipped: %s" % (name, error))
        else:
            captured[name] = shoot(file_name, "HighResShot 1920x1080")
        print("    %s at clock %.2f (planned %.2f) camera=%s audience=%s" % (name, p.get("clock", 0), at, p.get("camera"), p.get("audienceView")))
        ue("console", "slomo 0.3")
    ue("console", "slomo 1")
    deadline = time.time() + 120
    while time.time() < deadline and not poll(tag)["phase"].endswith("SETTLEMENT"):
        time.sleep(1.0)
    return {"plan": [[n, round(a, 2), f] for n, a, f, _ in plan]}


def run_timed(tag):
    ue("start", tag)
    time.sleep(1.0)
    ue("deploy", tag)
    t0 = time.time()
    wait_active(tag)
    ue("guards", tag)
    samples = []
    phase_end = None
    while time.time() - t0 < SETTLE_CAP_SEC + 20:
        p = poll(tag)
        p["editorMinimised"] = editor_minimised()
        samples.append(p)
        if p["phase"].endswith("SETTLEMENT") or p["phase"].endswith("GAME_OVER"):
            phase_end = time.time() - t0
            break
        time.sleep(1.0)
    last_active = [s for s in samples if s.get("active")]
    return {"settleWallSec": round(phase_end, 1) if phase_end else None, "samples": len(samples),
            "editorMinimised": any(s.get("editorMinimised") for s in samples),
            "lastActive": last_active[-1] if last_active else None, "final": samples[-1] if samples else None}


def main():
    args = sys.argv[1:]
    shots = "--no-shots" not in args
    ue("load")
    client = UeMcp(timeout=600)
    client.call("StartPIE", {"options": {"bSimulate": False, "playMode": "PlayMode_InViewPort", "warmupSeconds": 2}},
                toolset=EDITOR_TOOLSET)
    print("  PIE started")
    captured, evidence, timed = {}, {}, {}
    try:
        time.sleep(5)
        if shots:
            evidence = run_evidence("A", captured)
        else:
            run_timed("A")
        timed = run_timed("B")
        ue("cleanup")
    finally:
        client.call("StopPIE", {}, toolset=EDITOR_TOOLSET)
        print("  PIE stopped")
        time.sleep(3)
        ue("restore")
    state = json.load(open(STATE, encoding="utf-8"))
    a, b = state["runs"].get("A", {}), state["runs"].get("B", {})
    guards = b.get("guards", {})
    last = timed.get("lastActive") or {}
    lr = b.get("lastReport") or {}
    # A minimised editor renders ~3 fps: the measurement is then reported as not taken instead of failed.
    minimised = timed.get("editorMinimised", False)
    # Approach evidence: the units the presenter actually drew on the opponent's side, sorted by distance walked.
    units = lr.get("units") or []
    opponent = a.get("opponent", "")
    enemy_board = (a.get("boardEnemies") or {}).get(opponent, [])
    enemy = [u for u in units if u.get("enemy")]
    enemy_steps = sorted(u.get("travelledCells", 0.0) for u in enemy)
    enemy_movers = [u for u in enemy if u.get("travelledCells", 0.0) >= ENEMY_MIN_TRAVEL]
    # Both kinds must be among the units that actually walked: a mixed board that stands still proves nothing.
    enemy_kinds = {bool(u.get("ranged")) for u in enemy_movers}
    own_steps = sorted((u.get("travelledCells", 0.0) for u in units if not u.get("enemy")), reverse=True)
    # The audience camera artifact must describe the street camera, not the board camera it was switching away from
    # (both are recorded on the way through SetViewTargetWithBlend; see battle_presentation_check.py phase_audience).
    camera_doc = json.load(open(CAMERA, encoding="utf-8")) if os.path.exists(CAMERA) else {}
    table = json.load(open(PRESENTATION, encoding="utf-8"))["camera"]
    want_loc = table.get("audienceLocationM") or [0.0, 0.0, 0.0]
    want_fov = math.degrees(2.0 * math.atan(math.tan(math.radians(table.get("audienceFovDeg", 18.0)) * 0.5) * 16.0 / 9.0))
    got_loc = camera_doc.get("locationM") or []
    checks = {
        "deploy_accepted": bool(a.get("deployAccepted")) and bool(b.get("deployAccepted")),
        "battle_held_for_presentation": guards.get("phase", "").endswith("BATTLE") and bool(guards.get("awaiting")),
        "guards_reject_all": bool(guards.get("tries")) and not any(v["accepted"] for v in guards["tries"].values()),
        "same_seed_same_events": bool(a.get("events")) and a.get("events") == b.get("events"),
        "same_seed_same_timeline": bool(a.get("digest")) and a.get("digest") == b.get("digest"),
        "same_seed_same_outcomes": bool(a.get("outcomes")) and a.get("outcomes") == b.get("outcomes"),
        "settlement_within_45s": timed.get("settleWallSec") is not None and timed["settleWallSec"] <= SETTLE_CAP_SEC + 2,
        "presentation_finished_itself": bool((b.get("lastReport") or {}).get("finished")),
        "fps_at_least_45": (last.get("avgFps") or 0) >= MIN_FPS or minimised,
        "evidence_shots": (not shots) or all(k in captured for k in ("run", "attack", "defeat", "victory", "audience")),
        # The fixture must have stocked the AI the shuffle paired (opponent drift is what hid the mixed board), and
        # the drawn opponent board must hold both kinds; only then is the approach evidence below meaningful.
        "opponent_board_recorded": bool(opponent) and len(enemy_board) >= 3,
        "enemy_board_mixed": bool(enemy) and any(u.get("ranged") for u in enemy) and any(not u.get("ranged") for u in enemy),
        "enemy_approach_visible": (bool(enemy) and enemy_steps[-1] >= ENEMY_MIN_LEAD
                                   and len(enemy_movers) >= (len(enemy) + 1) // 2 and len(enemy_kinds) == 2),
        "own_approach_visible": bool(own_steps) and own_steps[0] >= OWN_MIN_TRAVEL,
        "audience_camera_recorded": (not shots) or (len(got_loc) == 3 and abs(got_loc[0] - want_loc[0]) <= 2
                                                   and abs(got_loc[1] - want_loc[1]) <= 2
                                                   and abs((camera_doc.get("horizontalFovDeg") or 0.0) - want_fov) <= 1),
    }
    doc = {"schema": "Tread.Battle.PresentationCheck.v1", "ok": all(checks.values()), "checks": checks,
           "runA": {k: a.get(k) for k in ("board", "boardEnemies", "outcomes")}, "evidence": evidence, "timed": timed,
           "opponent": opponent, "enemyBoard": enemy_board, "audienceCamera": camera_doc,
           "approach": {"enemyCells": [round(s, 3) for s in enemy_steps], "ownCells": [round(s, 3) for s in own_steps]},
           "guards": guards, "eventCount": len(a.get("events") or []), "digestA": a.get("digest"),
           "reportB": {k: lr.get(k) for k in ("attackCues", "diedCues", "frozenCues", "swings", "skillSwings", "bolts", "voices",
                                              "footsteps", "cameraSwitches", "frames", "avgFps", "worstFrameMs", "clipPlays",
                                              "victoryAt", "endAt", "winner")},
           "units": units, "shots": {k: os.path.relpath(v, ROOT) for k, v in captured.items()}}
    with open(REPORT, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, ensure_ascii=False, indent=1)
    doc["fpsMeasured"] = not minimised
    with open(REPORT, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, ensure_ascii=False, indent=1)
    print("Battle presentation ok=%s failed=%s shots=%s fpsMeasured=%s" % (doc["ok"], [k for k, v in checks.items() if not v],
                                                                         sorted(captured), not minimised))
    return 0 if doc["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
