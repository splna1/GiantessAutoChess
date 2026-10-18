"""UI style acceptance (editor-side, Tools/ue_run.py), phase by phase; driven by Tools/ui_proto/ue_ui_style_check_pie.py
(document/157 section 6). Every output line is "UISTYLE <phase> <json>" and ASCII only.

  check             the running editor has the front end test hooks; guard dirty packages; remember the map; CPU throttle off
  load              load M3_Paris_Match (nothing else happens in this call: memory tread-editor-python-map-switch)
  restore           reload the map that check remembered, put the CPU throttle setting back
  probe             (PIE) world / controller / front end widget found, hooks present, current screen, campaign progress
  seed <n>          (PIE) SetCampaignProgressForTest(n): the HTML prototype shows stages 1-5 cleared. That test hook
                    WRITES the campaign save slot, so the host driver only asks for it with --seed-progress and puts the
                    save file back afterwards.
  state <name>      (PIE) put the front end into the state of one HTML shot (table FRONT_STATES)
  screen            (PIE) the front end's current screen name
  hud bp|prep|deploy  (PIE) push the match to PreMatchBP / Preparation (shop + bench + board) / Battle
  poll              (PIE) phase + battle presenter report; the first active poll stores the timeline digest
  console <cmd>     (PIE) run a console command (slomo, HighResShot, shot showui)
  cleanup           (PIE) back to a free match, audio on, slomo 1

Every phase is its own remote call. No time.sleep here: the host driver does all the waiting.
"""
import json
import os
import sys

import unreal

PROJECT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
REPORTS = os.path.join(PROJECT, "Saved", "Reports")
STATE = os.path.join(REPORTS, "UI_Style_Check_state.json")
ROSTER = os.path.join(PROJECT, "Content", "Data", "Generated", "CharacterRosterMap.json")
M3_MAP = "/Game/Tread/Maps/M3_Paris_Match"
HUMAN = "P0"
SEED = 20261014
# The commander name of HTML shot 04_login_success; escaped so this file and every output line stay ASCII.
CALLSIGN = u"\u4f0a\u4e07\u8bfa\u5a03"

HOOKS = ("jump_to_screen_for_test", "set_loading_progress_for_test", "submit_login_for_test",
         "hover_stage_for_test", "select_stage_for_test", "freeze_transition_for_test", "get_screen_name")

# name -> (screen names that count as "state set", hook steps), after Tools/ui_proto/shoot.py SHOTS (11 is HTML-only).
# Every state starts with a jump: it resets the flow, so the states do not depend on each other.
FRONT_STATES = {
    "01_loading_mid": ({"loading"}, [("jump", "loading"), ("progress", 0.62)]),
    "02_loading_done": ({"loading"}, [("jump", "loading"), ("progress", 1.0)]),
    "03_login": ({"login"}, [("jump", "login")]),
    "04_login_success": ({"login"}, [("jump", "login"), ("submit", CALLSIGN)]),
    "05_select": ({"select"}, [("jump", "select")]),
    "06_select_hover": ({"select"}, [("jump", "select"), ("hover", 7)]),
    "07_select_detail": ({"select"}, [("jump", "select"), ("select", 6), ("hover", 10)]),
    "08_select_cleared": ({"select"}, [("jump", "select"), ("select", 3)]),
    "09_select_locked": ({"select"}, [("jump", "select"), ("select", 12)]),
    # The sortie page takes the selected stage (SelIdx) when no stage was handed over yet (SortieStage <= 0).
    "10_sortie": ({"sortie"}, [("jump", "select"), ("select", 6), ("jump", "sortie")]),
    "12_trans_scan": ({"loading", "login"}, [("jump", "loading"), ("freeze", "scan", 0.55)]),
    "13_trans_slab_in": ({"login", "select"}, [("jump", "login"), ("freeze", "slab", 0.22)]),
    "14_trans_slab_mid": ({"login", "select"}, [("jump", "login"), ("freeze", "slab", 0.5)]),
    # The blinds hook jumps to the select screen itself and sortie-stages the first front stage (stage 6 with 5 cleared).
    "15_trans_blinds": ({"select", "sortie"}, [("freeze", "blinds", 0.55)]),
    "16_trans_slab_out": ({"login", "select"}, [("jump", "login"), ("freeze", "slab", 0.8)]),
}


def read(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def write(path, doc):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, ensure_ascii=False, indent=1)


def emit(phase_name, doc):
    print("UISTYLE %s %s" % (phase_name, json.dumps(doc, sort_keys=True, default=str)))


def attr(obj, *names):
    """First attribute that exists (Python strips the leading b of bool properties: bConquered -> conquered)."""
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    raise AttributeError(names[0])


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


def front_end(world):
    """The PIE world's UTreadFrontEndWidget: ATreadM1GameMode.FrontEndWidget, else a widget search; None when absent."""
    gm = unreal.GameplayStatics.get_game_mode(world)
    if gm is not None:
        for getter in (lambda: gm.front_end_widget, lambda: gm.get_editor_property("front_end_widget")):
            try:
                widget = getter()
            except Exception:  # noqa: BLE001
                continue
            if widget:
                return widget
    cls = getattr(unreal, "TreadFrontEndWidget", None)
    if cls is None:
        return None
    # UE 5.8 renamed WidgetBlueprintLibrary to WidgetLibrary.
    lib = getattr(unreal, "WidgetLibrary", None) or getattr(unreal, "WidgetBlueprintLibrary")
    found = lib.get_all_widgets_of_class(world, cls, False)
    return found[0] if found else None


def phase(c):
    return c.get_phase().name


def human(c):
    for p in c.match_state.players:
        if str(p.player_id) == HUMAN:
            return p
    raise RuntimeError("no human player")


def stage_summary(c):
    rows = list(c.get_campaign_stages())
    return {"count": len(rows),
            "conquered": [int(attr(r, "index")) for r in rows if attr(r, "conquered", "b_conquered")],
            "unlocked": [int(attr(r, "index")) for r in rows if attr(r, "unlocked", "b_unlocked")]}


def board_ids():
    """Six units over the presentation branches: melee and ranged / heal, mid to high tier, fixed order."""
    rows = read(ROSTER).get("characters", [])
    tiers = {"III": 3, "IV": 4, "V": 5, "VI": 6}
    pick, seen = [], set()
    for want in ("melee", "ranged", "melee", "heal", "melee", "ranged", "melee", "none"):
        for row in rows:
            if row["characterId"] in seen or row.get("attackKind") != want or row.get("operatorTier") not in tiers:
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


# ------------------------------------------------------------------------------------------------ check / load / restore
def phase_check():
    if game_world():
        raise RuntimeError("a PIE session is already running")
    cls = getattr(unreal, "TreadFrontEndWidget", None)
    hooks = {name: bool(cls is not None and hasattr(cls, name)) for name in HOOKS}
    if cls is None or not all(hooks.values()):
        raise RuntimeError("this editor build has no UTreadFrontEndWidget test hooks (rebuild TreadEditor, reopen the editor): %s"
                           % json.dumps(hooks, sort_keys=True))
    dirty = (unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
             + unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    if dirty:
        raise RuntimeError("dirty packages present, refusing to switch map: %s" % [p.get_name() for p in dirty][:10])
    # The editor drops to ~3 fps while it is not the foreground app ("Use Less CPU when in Background"): switch it off for
    # the run so the UI keeps ticking; restore puts the owner's value back.
    perf = editor_perf()
    throttle = bool(perf.get_editor_property("bThrottleCPUWhenNotForeground"))
    perf.set_editor_property("bThrottleCPUWhenNotForeground", False)
    write(STATE, {"previousMap": unreal.EditorLevelLibrary.get_editor_world().get_path_name().split(".")[0],
                  "throttleCpu": throttle, "states": {}, "hud": {}, "runs": {}})
    mode = getattr(unreal, "TreadM1GameMode", None)
    emit("check", {"hooks": hooks, "gameModeProperty": bool(mode is not None and hasattr(mode, "front_end_widget")),
                   "throttleWas": throttle})


def phase_load():
    if not unreal.EditorLoadingAndSavingUtils.load_map(M3_MAP):
        raise RuntimeError("failed to load " + M3_MAP)
    emit("load", {"map": M3_MAP})


def phase_restore():
    editor_perf().set_editor_property("bThrottleCPUWhenNotForeground", bool(read(STATE).get("throttleCpu", True)))
    previous = read(STATE).get("previousMap", "")
    if not previous:
        raise RuntimeError("no remembered map")
    if game_world():
        raise RuntimeError("stop PIE before restoring the map")
    if not unreal.EditorLoadingAndSavingUtils.load_map(previous):
        raise RuntimeError("failed to restore " + previous)
    emit("restore", {"map": previous})


# ------------------------------------------------------------------------------------------------ PIE: front end
def phase_probe():
    world, c, presenter = pie()
    fe = front_end(world)
    info = {"map": world.get_name(), "phase": phase(c), "presenter": presenter is not None, "frontEnd": fe is not None,
            "stages": stage_summary(c)}
    if fe is not None:
        info["hooks"] = {name: bool(hasattr(fe, name)) for name in HOOKS}
        info["screen"] = str(fe.get_screen_name())
    unreal.SystemLibrary.execute_console_command(world, "Tread.Audio 0")
    unreal.SystemLibrary.execute_console_command(world, "slomo 1")
    emit("probe", info)


def phase_seed(count):
    world, c, presenter = pie()
    c.set_campaign_progress_for_test(int(count))
    emit("seed", dict(stage_summary(c), requested=int(count)))


def run_steps(fe, steps):
    for step in steps:
        op = step[0]
        if op == "jump":
            fe.jump_to_screen_for_test(step[1])
        elif op == "progress":
            fe.set_loading_progress_for_test(step[1])
        elif op == "submit":
            fe.submit_login_for_test(step[1])
        elif op == "hover":
            fe.hover_stage_for_test(step[1])
        elif op == "select":
            fe.select_stage_for_test(step[1])
        elif op == "freeze":
            fe.freeze_transition_for_test(step[1], step[2])
        else:
            raise RuntimeError("bad step " + repr(step))


def phase_state(name):
    if name not in FRONT_STATES:
        raise RuntimeError("unknown front end state %s (known: %s)" % (name, sorted(FRONT_STATES)))
    expected, steps = FRONT_STATES[name]
    world, c, presenter = pie()
    fe = front_end(world)
    if fe is None:
        raise RuntimeError("no front end widget (M3_Paris map only, and no -TreadSkipFrontEnd style flag on the command line)")
    error = ""
    try:
        run_steps(fe, steps)
    except Exception as exc:  # noqa: BLE001
        error = ascii(str(exc))
    screen = str(fe.get_screen_name())
    row = {"expected": sorted(expected), "screen": screen, "error": error, "ok": (not error) and screen in expected}
    state = read(STATE)
    state.setdefault("states", {})[name] = row
    write(STATE, state)
    emit("state", dict(row, name=name))


def phase_screen():
    world, c, presenter = pie()
    fe = front_end(world)
    emit("screen", {"screen": str(fe.get_screen_name()) if fe is not None else "none"})


# ------------------------------------------------------------------------------------------------ PIE: HUD
def phase_hud(step, arg):
    world, c, presenter = pie()
    tag = "uistyle-" + step
    row = {"step": step}
    if step == "bp":
        # Fresh match in the BP phase: strategy chosen, two of the three AI picks done (BP screen with some cards taken).
        unreal.SystemLibrary.execute_console_command(world, "Tread.Audio 0")
        unreal.SystemLibrary.execute_console_command(world, "slomo 0.3")
        if presenter:
            presenter.set_audience_camera_for_test(False)
        c.initialize_match(SEED)
        row["stageAccepted"] = bool(c.select_campaign_stage(int(arg), tag + "-stage").accepted)
        row["bpAccepted"] = bool(c.begin_pre_match_bp(tag + "-bp").accepted)
        available = [str(s) for s in c.match_state.bp.available_strategy_ids]
        if available:
            c.choose_player_strategy(available[0], tag + "-strategy")
        for pick in range(2):
            c.run_next_ai_pick("%s-ai-%d" % (tag, pick))
    elif step == "prep":
        # Last AI pick, confirm, then Preparation with two bought bench units and the six-unit fixture board.
        c.run_next_ai_pick(tag + "-ai-2")
        row["confirmAccepted"] = bool(c.confirm_pre_match_bp(tag + "-confirm").accepted)
        if not phase(c).endswith("PREPARATION"):
            c.begin_preparation(tag + "-prep")
        bought = 0
        for slot in range(5):
            if bought >= 2:
                break
            if c.purchase_shop_slot(HUMAN, slot, "%s-buy-%d" % (tag, slot)).accepted:
                bought += 1
        row["bought"] = bought
        row["stocked"] = bool(c.stock_board_for_fixture(HUMAN, board_ids()))
        row["board"] = len(list(human(c).board_units))
        row["bench"] = len(list(human(c).bench_units))
    elif step == "deploy":
        # A separate call after prep: the presenter must tick once outside the Battle phase to drop the previous replay.
        row["deployAccepted"] = bool(c.deploy_and_start_battle(tag + "-deploy").accepted)
    else:
        raise RuntimeError("hud step must be bp|prep|deploy")
    row["phase"] = phase(c)
    fe = front_end(world)
    row["frontEnd"] = str(fe.get_screen_name()) if fe is not None else "none"
    state = read(STATE)
    state.setdefault("hud", {})[step] = row
    write(STATE, state)
    emit("hud", row)


def phase_poll(tag):
    world, c, presenter = pie()
    report = json.loads(str(presenter.get_battle_presentation_report())) if presenter else {}
    st = c.match_state
    line = {"phase": phase(c), "awaiting": bool(st.battle_awaiting_presentation), "timer": round(st.phase_time_remaining_sec, 2),
            "active": report.get("active"), "finished": report.get("finished"), "clock": round(report.get("clock", -1), 2),
            "victoryAt": report.get("victoryAt"), "winner": report.get("winner")}
    state = read(STATE)
    run = state.setdefault("runs", {}).setdefault(tag, {})
    if report.get("active") and "digest" not in run:
        run["digest"] = str(presenter.get_battle_timeline_digest())
    write(STATE, state)
    emit("poll", line)


def phase_console(command):
    world, c, presenter = pie()
    unreal.SystemLibrary.execute_console_command(world, command)
    emit("console", {"cmd": command})


def phase_cleanup():
    world = game_world()
    if world:
        world, c, presenter = pie()
        if presenter:
            presenter.set_audience_camera_for_test(False)
        unreal.SystemLibrary.execute_console_command(world, "slomo 1")
        c.initialize_match(SEED)
        c.select_campaign_stage(0, "uistyle-cleanup")
        unreal.SystemLibrary.execute_console_command(world, "Tread.Audio 1")
    emit("cleanup", {"pie": world is not None})


def main():
    args = sys.argv[1:]
    name = args[0] if args else ""
    if name == "check":
        phase_check()
    elif name == "load":
        phase_load()
    elif name == "restore":
        phase_restore()
    elif name == "probe":
        phase_probe()
    elif name == "seed":
        phase_seed(args[1])
    elif name == "state":
        phase_state(args[1])
    elif name == "screen":
        phase_screen()
    elif name == "hud":
        phase_hud(args[1], args[2] if len(args) > 2 else "0")
    elif name == "poll":
        phase_poll(args[1] if len(args) > 1 else "hud")
    elif name == "console":
        phase_console(" ".join(args[1:]))
    elif name == "cleanup":
        phase_cleanup()
    else:
        raise RuntimeError("phase must be check|load|restore|probe|seed|state|screen|hud|poll|console|cleanup")


main()
