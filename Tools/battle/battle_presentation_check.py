"""Battle presentation acceptance (editor-side, Tools/ue_run.py), phase by phase; driven by
Tools/battle/battle_presentation_check_pie.py (document/12 §9).

  load            guard dirty packages, remember the current map, load M3_Paris_Match
  start <tag>     (PIE) fixed-seed free match in preparation: a mixed board of 6 units for the human and one
                  for every AI (the pairing shuffle, not the fixture, decides which AI P0 meets)
  deploy <tag>    (PIE) DeployAndStartBattle; also records the opponent the shuffle picked
  guards <tag>    (PIE) during the held Battle phase: purchase / sell / bench / refresh / deploy must be rejected
  poll <tag>      (PIE) one JSON line: phase, awaiting flag, presenter report; the first poll with an active
                  presentation stores the timeline digest and the battle event stream under <tag>
  console <cmd>   (PIE) run a console command (slomo, HighResShot, shot showui)
  audience <0|1>  (PIE) Board_Camera / Audience_Camera; 1 also writes M1_Audience_Camera.json
  cleanup         (PIE) back to a free match, audio on
  restore         reload the map that load remembered

Every phase is its own remote call (memory: tread-editor-python-map-switch).
"""
import json
import os
import sys

import unreal

PROJECT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
REPORTS = os.path.join(PROJECT, "Saved", "Reports")
STATE = os.path.join(REPORTS, "Battle_Presentation_state.json")
ROSTER = os.path.join(PROJECT, "Content", "Data", "Generated", "CharacterRosterMap.json")
CAMERA_JSON = os.path.join(REPORTS, "M1_Audience_Camera.json")
M3_MAP = "/Game/Tread/Maps/M3_Paris_Match"
HUMAN = "P0"
AI_PLAYERS = ("P1", "P2", "P3")
SEED = 20261014
# Opponent board for the evidence: melee and ranged / heal, so both sides visibly close in (document/158).
MIXED_WANT = ("melee", "melee", "ranged", "melee", "heal", "ranged")
# Melee stands on row 2 (it visibly charges), ranged / heal keeps back on row 0. Columns 4-6 dodge the AI
# graybox cells (cols 0-2, rows 0-2, BuildAIPlaceholderRosters) so no two rosters share a cell.
MIXED_CELLS = ((4, 2), (5, 2), (4, 0), (6, 2), (5, 0), (6, 0))


def read(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def write(path, doc):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, ensure_ascii=False, indent=1)


def game_world():
    sub = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    world = sub.get_game_world() if sub else None
    if world:
        return world
    for world in unreal.EditorLevelLibrary.get_pie_worlds(False) or []:
        if world:
            return world
    return None


def pie():
    world = game_world()
    if not world:
        raise RuntimeError("no PIE world; start PIE first")
    found = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.TreadM1MatchController)
    if not found:
        raise RuntimeError("no TreadM1MatchController")
    presenters = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.TreadM3BoardPresenter)
    return world, found[0], (presenters[0] if presenters else None)


def phase(c):
    return c.get_phase().name


def human(c):
    for p in c.match_state.players:
        if str(p.player_id) == HUMAN:
            return p
    raise RuntimeError("no human player")


def player(c, pid):
    for p in c.match_state.players:
        if str(p.player_id) == pid:
            return p
    raise RuntimeError("no player " + pid)


def finish_bp(c, tag):
    if phase(c).endswith("R0_BRIEFING"):
        c.begin_pre_match_bp(tag + "-bp")
    if phase(c).endswith("PRE_MATCH_BP"):
        available = [str(s) for s in c.match_state.bp.available_strategy_ids]
        if available:
            c.choose_player_strategy(available[0], tag + "-strategy")
        for pick in range(3):
            c.run_next_ai_pick("%s-ai-%d" % (tag, pick))
        c.confirm_pre_match_bp(tag + "-confirm")
    if not phase(c).endswith("PREPARATION"):
        c.begin_preparation(tag + "-prep")


def board_ids(exclude=(), want=("melee", "ranged", "melee", "heal", "melee", "ranged", "melee", "none")):
    """Units over the presentation branches: melee and ranged / heal, mid to high tier, fixed order.

    `exclude` keeps the two sides off the same characters so the shared pool is not drained by one board.
    """
    rows = read(ROSTER).get("characters", [])
    tiers = {"III": 3, "IV": 4, "V": 5, "VI": 6}
    skip = set(exclude)
    pick, seen = [], set()
    for w in want:
        for row in rows:
            if row["characterId"] in seen or row["characterId"] in skip or row.get("attackKind") != w or row.get("operatorTier") not in tiers:
                continue
            if row.get("profession") in {r[1] for r in pick} and len(pick) < 5:
                continue
            pick.append((row["characterId"], row.get("profession")))
            seen.add(row["characterId"])
            break
        if len(pick) == 6:
            break
    return [cid for cid, _ in pick]


def editor_perf():
    return unreal.get_default_object(unreal.load_class(None, "/Script/UnrealEd.EditorPerformanceSettings"))


# ------------------------------------------------------------------------------------------------ load / restore
def phase_load():
    if game_world():
        raise RuntimeError("a PIE session is already running")
    dirty = (unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
             + unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    if dirty:
        raise RuntimeError("dirty packages present, refusing to switch map: %s" % [p.get_name() for p in dirty][:10])
    # The editor drops to ~3 fps while it is not the foreground app ("Use Less CPU when in Background"), which would make
    # the fps check measure the throttle: switch it off for the test, restore restores the owner's value.
    perf = editor_perf()
    throttle = bool(perf.get_editor_property("bThrottleCPUWhenNotForeground"))
    perf.set_editor_property("bThrottleCPUWhenNotForeground", False)
    write(STATE, {"previousMap": unreal.EditorLevelLibrary.get_editor_world().get_path_name().split(".")[0], "runs": {},
                  "throttleCpu": throttle})
    if not unreal.EditorLoadingAndSavingUtils.load_map(M3_MAP):
        raise RuntimeError("failed to load " + M3_MAP)
    print("BATTLE load ok")


def phase_restore():
    editor_perf().set_editor_property("bThrottleCPUWhenNotForeground", bool(read(STATE).get("throttleCpu", True)))
    previous = read(STATE).get("previousMap", "")
    if not previous:
        raise RuntimeError("no remembered map")
    if game_world():
        raise RuntimeError("stop PIE before restoring the map")
    if not unreal.EditorLoadingAndSavingUtils.load_map(previous):
        raise RuntimeError("failed to restore " + previous)
    print("BATTLE restore %s" % previous)


# ------------------------------------------------------------------------------------------------ PIE phases
def phase_start(tag):
    world, c, presenter = pie()
    if not presenter:
        raise RuntimeError("no TreadM3BoardPresenter in the PIE world")
    unreal.SystemLibrary.execute_console_command(world, "Tread.Audio 0")
    unreal.SystemLibrary.execute_console_command(world, "slomo 1")
    presenter.set_audience_camera_for_test(False)
    c.initialize_match(SEED)
    c.select_campaign_stage(0, tag + "-free")
    finish_bp(c, tag)
    ids = board_ids()
    # Every AI gets the mixed board instead of one guessed opponent: BuildPairings shuffles at deploy time and
    # stocking a board itself consumes the shared RandomStream (TreadM2PactRuntime.cpp GrantUnitToPlayer), so
    # "stock P1 and expect P0 to meet P1" drifted to P3 and the shots showed a graybox roster. Mixing all three
    # makes the opponent mixed whoever the shuffle picks; the deployed pairing is recorded by phase_deploy.
    used = list(ids)
    enemies, enemies_ok = {}, True
    for pid in AI_PLAYERS:
        enemy_ids = board_ids(exclude=used, want=MIXED_WANT)
        used.extend(enemy_ids)
        enemy_stocked = c.stock_board_for_fixture(pid, enemy_ids)
        moved = 0
        for slot, (unit, cell) in enumerate(zip(player(c, pid).board_units, MIXED_CELLS)):
            # Each move needs its own request id: the controller dedupes repeated ids.
            if c.move_unit_to_board(pid, str(unit.unit_instance_id), unreal.IntPoint(*cell),
                                    "%s-%s-%d" % (tag, pid.lower(), slot)).accepted:
                moved += 1
        enemies[pid] = [str(u.character_id) for u in player(c, pid).board_units]
        enemies_ok = enemies_ok and bool(enemy_stocked) and moved == len(MIXED_CELLS)
    stocked = c.stock_board_for_fixture(HUMAN, ids)
    board = [str(u.character_id) for u in human(c).board_units]
    state = read(STATE)
    state.setdefault("runs", {})[tag] = {"board": board, "boardEnemies": enemies, "stocked": bool(stocked) and enemies_ok}
    write(STATE, state)
    print("BATTLE start %s board=%s enemies=%s phase=%s" % (tag, board, enemies, phase(c)))


def opponent_of(c):
    """The player P0 is paired with this round; the pairings are fixed when the battle starts."""
    for pair in c.match_state.last_battle_result.pairings:
        if str(pair.player_id) == HUMAN:
            return str(pair.opponent_id)
        if str(pair.opponent_id) == HUMAN:
            return str(pair.player_id)
    return ""


def phase_deploy(tag):
    # A separate call after start: the presenter must tick once outside the Battle phase to drop the previous replay.
    world, c, presenter = pie()
    result = c.deploy_and_start_battle(tag + "-deploy")
    state = read(STATE)
    state["runs"].setdefault(tag, {}).update({"deployAccepted": bool(result.accepted), "phaseAfterDeploy": phase(c),
                                              "opponent": opponent_of(c)})
    write(STATE, state)
    print("BATTLE deploy %s accepted=%s opponent=%s phase=%s" % (tag, result.accepted, opponent_of(c), phase(c)))


def phase_guards(tag):
    world, c, presenter = pie()
    p = human(c)
    board = list(p.board_units)
    uid = str(board[0].unit_instance_id) if board else ""
    tries = {
        "purchase": c.purchase_shop_slot(HUMAN, 0, tag + "-g-buy"),
        "refresh": c.refresh_shop(HUMAN, tag + "-g-refresh"),
        "sell": c.sell_unit(HUMAN, uid, tag + "-g-sell"),
        "toBench": c.move_unit_to_bench(HUMAN, uid, tag + "-g-bench"),
        "toBoard": c.move_unit_to_board(HUMAN, uid, unreal.IntPoint(0, 7), tag + "-g-board"),
        "buyExp": c.buy_experience(HUMAN, tag + "-g-exp"),
        "deployAgain": c.deploy_and_start_battle(tag + "-g-deploy"),
    }
    rows = {k: {"accepted": bool(v.accepted), "reason": str(v.reason_code)} for k, v in tries.items()}
    state = read(STATE)
    state["runs"].setdefault(tag, {})["guards"] = {"phase": phase(c), "awaiting": bool(c.match_state.battle_awaiting_presentation),
                                                  "tries": rows}
    write(STATE, state)
    print("BATTLE guards %s phase=%s accepted=%s" % (tag, phase(c), [k for k, v in rows.items() if v["accepted"]]))


def camera_of(world):
    cam = unreal.GameplayStatics.get_player_camera_manager(world, 0)
    loc = cam.get_camera_location()
    target = unreal.GameplayStatics.get_player_controller(world, 0).get_view_target()
    return {"m": [round(loc.x / 100, 1), round(loc.y / 100, 1), round(loc.z / 100, 1)], "fov": round(cam.get_fov_angle(), 1),
            "target": target.get_name() if target else ""}


def phase_poll(tag):
    world, c, presenter = pie()
    report = json.loads(str(presenter.get_battle_presentation_report())) if presenter else {}
    st = c.match_state
    line = {"phase": phase(c), "awaiting": bool(st.battle_awaiting_presentation), "timer": round(st.phase_time_remaining_sec, 2),
            "active": report.get("active"), "finished": report.get("finished"), "clock": round(report.get("clock", -1), 2),
            "victoryAt": report.get("victoryAt"), "endAt": report.get("endAt"), "winner": report.get("winner"),
            "dead": sum(1 for u in report.get("units", []) if u.get("dead")), "avgFps": round(report.get("avgFps", 0), 1),
            "worstFrameMs": round(report.get("worstFrameMs", 0), 1), "audienceView": report.get("audienceView"),
            "cameraSwitches": report.get("cameraSwitches"), "camera": camera_of(world)}
    state = read(STATE)
    run = state["runs"].setdefault(tag, {})
    if report.get("active") and "digest" not in run:
        run["digest"] = str(presenter.get_battle_timeline_digest())
        run["events"] = ["%d|%s|%s>%s|%d|%d|%.3f" % (e.sequence, e.event_type.name, e.source_unit_instance_id,
                                                    e.target_unit_instance_id, e.amount, e.target_health_after, e.time_sec)
                         for e in st.battle_events]
        run["outcomes"] = [[str(o.player_id), str(o.outcome), o.health_before, o.health_after] for o in st.last_battle_result.outcomes]
    run["lastReport"] = report
    write(STATE, state)
    print("BATTLE poll " + json.dumps(line))


def phase_console(command):
    world, c, presenter = pie()
    unreal.SystemLibrary.execute_console_command(world, command)
    print("BATTLE console %s" % command)


def audience_actor(world, presenter):
    """The audience camera actor itself. Reading the player camera right after SetViewTargetWithBlend still
    returns the outgoing camera (the blend takes ~0.6 s), which is how M1_Audience_Camera.json ended up
    recording the board camera (-1729, 0, 1202) instead of the street camera until 2026-10-17."""
    camera = getattr(presenter, "audience_camera", None)
    if camera:
        return camera
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.CameraActor) or []:
        try:
            if "Audience_Camera" in str(actor.get_actor_label()):
                return actor
        except Exception:
            continue
    raise RuntimeError("no audience camera actor on the presenter")


def phase_audience(on):
    world, c, presenter = pie()
    presenter.set_audience_camera_for_test(on)
    if on:
        actor = audience_actor(world, presenter)
        loc, rot = actor.get_actor_location(), actor.get_actor_rotation()
        try:
            name = str(actor.get_actor_label())
        except Exception:
            name = str(actor.get_name())
        try:
            fov = round(float(actor.camera_component.field_of_view), 2)
        except Exception:
            fov = None
        # IsAudienceCamera() is not a UFUNCTION, so it is not exposed to Python: the requested flag is the answer.
        probe = getattr(presenter, "is_audience_camera", None)
        audience = bool(probe()) if callable(probe) else bool(on)
        write(CAMERA_JSON, {"schema": "Tread.M1.AudienceCamera.v1", "audienceView": audience,
                            "actor": name,
                            "locationM": [round(loc.x / 100, 2), round(loc.y / 100, 2), round(loc.z / 100, 2)],
                            "rotationDeg": {"pitch": round(rot.pitch, 2), "yaw": round(rot.yaw, 2), "roll": round(rot.roll, 2)},
                            "horizontalFovDeg": fov})
    print("BATTLE audience %s" % on)


def phase_cleanup():
    world = game_world()
    if world:
        world, c, presenter = pie()
        if presenter:
            presenter.set_audience_camera_for_test(False)
        unreal.SystemLibrary.execute_console_command(world, "slomo 1")
        c.initialize_match(SEED)
        c.select_campaign_stage(0, "battle-cleanup")
        unreal.SystemLibrary.execute_console_command(world, "Tread.Audio 1")
    print("BATTLE cleanup")


def main():
    args = sys.argv[1:]
    name = args[0] if args else ""
    if name == "load":
        phase_load()
    elif name == "restore":
        phase_restore()
    elif name == "start":
        phase_start(args[1])
    elif name == "deploy":
        phase_deploy(args[1])
    elif name == "guards":
        phase_guards(args[1])
    elif name == "poll":
        phase_poll(args[1])
    elif name == "console":
        phase_console(" ".join(args[1:]))
    elif name == "audience":
        phase_audience(args[1] == "1")
    elif name == "cleanup":
        phase_cleanup()
    else:
        raise RuntimeError("phase must be load|restore|start|guards|poll|console|audience|cleanup")


main()
