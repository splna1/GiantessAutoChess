"""N2 render truth check: does the PIE renderer itself actually draw the presenter's units?

Every earlier N2 shot went through a capture path (a SceneCapture2D, then an editor-viewport
capture), and both paths have lied before, so this script stops asking the capture tool and asks
the renderer:

  * WasRecentlyRendered() on every component the presenter owns -- that flag is written by the
    real game viewport's visibility pass, so a capture component cannot influence it.
  * a census of every skeletal mesh the PIE world renders, to name the one figure that did show up
  * HighResShot, which comes out of the game viewport itself rather than the editor capture
  * a count of the city's own static meshes as a control: if nothing renders, the measurement
    is void (an unfocused editor stops drawing) rather than a statement about the units

`stock` and `measure` are separate calls on purpose.  The presenter builds its components from
Tick(), and remote execution runs Python on the game thread, so a single call sees the world in the
frame before the components exist.

    python Tools/ue_run.py Tools/m4/n2_render_truth.py load     # map switch, its own call
    # MCP: EditorToolset.EditorAppToolset StartPIE   (immediately, the match auto-advances)
    python Tools/ue_run.py Tools/m4/n2_render_truth.py stock
    python Tools/ue_run.py Tools/m4/n2_render_truth.py measure
    # MCP: EditorToolset.EditorAppToolset StopPIE
    python Tools/ue_run.py Tools/m4/n2_render_truth.py restore  # map switch, its own call

Report: Saved/Reports/N2_RenderTruth.json
Shot:   Saved/Screenshots/**/  (HighResShot, written by the game viewport itself)
"""
import json
import os
import sys

import unreal

PROJECT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
REPORTS = os.path.join(PROJECT, "Saved", "Reports")
STATE = os.path.join(REPORTS, "N2_PieBoard_state.json")
REPORT = os.path.join(REPORTS, "N2_RenderTruth.json")

M3_MAP = "/Game/Tread/Maps/M3_Paris_Match"
HUMAN = "P0"
CHECK_CHARACTERS = (["char_%03d" % n for n in range(101, 113)] + ["char_001", "char_050", "char_100"])
# --set vrm (M4): sixteen roster VRMs spread over the id range, incl. the D-leg, no-chest and 112-submesh cases,
# with the hero char_001 as control; the "set" bodies are then the /VRM/ meshes.
VRM_CHARACTERS = ["char_001", "char_002", "char_009", "char_016", "char_030", "char_040", "char_046", "char_047",
                  "char_053", "char_057", "char_063", "char_071", "char_080", "char_085", "char_087", "char_100"]
SET_TAG = "MMD"
if "--set" in sys.argv and sys.argv[sys.argv.index("--set") + 1] == "vrm":
    CHECK_CHARACTERS, SET_TAG = VRM_CHARACTERS, "VRM"
    REPORT = os.path.join(REPORTS, "M4_RenderTruth.json")
PHASES = ("load", "stock", "census", "shoot", "shoot_hidden", "measure", "unfreeze", "restore")
# WasRecentlyRendered takes a tolerance in seconds; 0.0 means "in the frame being built right now",
# which is too tight to read reliably from Python, so ask about the last half second.
RENDER_TOLERANCE = 0.5


def write(path, doc):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, ensure_ascii=False, indent=1)


def read(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def game_world():
    sub = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    world = sub.get_game_world() if sub else None
    if world:
        return world
    if hasattr(unreal.EditorLevelLibrary, "get_pie_worlds"):
        for world in unreal.EditorLevelLibrary.get_pie_worlds(False) or []:
            if world:
                return world
    return None


def phase_load():
    """Switch to the match map.  Must be its own call: a world reference held in this frame makes the
    GC leak check abort the editor (see the map-switch note in memory)."""
    if game_world():
        raise RuntimeError("a PIE session is already running")
    dirty = (unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
             + unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    if dirty:
        raise RuntimeError("dirty packages present, refusing to switch map: %s" % [p.get_name() for p in dirty])
    write(STATE, {"previousMap": unreal.EditorLevelLibrary.get_editor_world().get_path_name().split(".")[0]})
    if not unreal.EditorLoadingAndSavingUtils.load_map(M3_MAP):
        raise RuntimeError("failed to load " + M3_MAP)


def phase_restore():
    previous = read(STATE).get("previousMap", "")
    if not previous:
        raise RuntimeError("no remembered map")
    if game_world():
        raise RuntimeError("stop PIE before restoring the map")
    if not unreal.EditorLoadingAndSavingUtils.load_map(previous):
        raise RuntimeError("failed to restore " + previous)


def controller_of(world):
    found = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.TreadM1MatchController)
    if not found:
        raise RuntimeError("no TreadM1MatchController")
    return found[0]


def phase_name(controller):
    return controller.get_phase().name


def drive_to_preparation(controller):
    """Walk the match to Preparation.  A PIE session left running drifts through Battle and
    Settlement on its own, so this has to come back from anywhere rather than assume a fresh match."""
    for _ in range(12):
        phase = phase_name(controller)
        if phase.endswith("PREPARATION"):
            return phase
        if phase.endswith("MAIN_MENU") or phase.endswith("R0_BRIEFING"):
            controller.begin_pre_match_bp("n2truth-bp")
        elif phase.endswith("PRE_MATCH_BP"):
            available = [str(s) for s in controller.match_state.bp.available_strategy_ids]
            if available:
                controller.choose_player_strategy(available[0], "n2truth-strategy")
            for pick in range(3):
                controller.run_next_ai_pick("n2truth-ai-%d" % pick)
            controller.confirm_pre_match_bp("n2truth-confirm")
        elif phase.endswith("BATTLE"):
            controller.resolve_battle("n2truth-resolve")
        elif phase.endswith("SETTLEMENT"):
            controller.settle_round("n2truth-settle")
            controller.advance_to_next_round("n2truth-round")
        else:
            raise RuntimeError("no route to Preparation from %s" % phase)
        print("   step %s -> %s" % (phase, phase_name(controller)))
    return phase_name(controller)


def actor_flag(actor, name):
    try:
        return bool(actor.get_editor_property(name))
    except Exception:
        return None


def rendered(component):
    if not hasattr(component, "was_recently_rendered"):
        return None
    try:
        return bool(component.was_recently_rendered(RENDER_TOLERANCE))
    except Exception:
        return None


def describe(component):
    mesh = None
    if isinstance(component, unreal.SkeletalMeshComponent):
        asset = component.get_skeletal_mesh_asset()
        mesh = asset.get_name() if asset else None
    else:
        asset = component.get_editor_property("static_mesh")
        mesh = asset.get_name() if asset else None
    owner = component.get_owner()
    parent = component.get_attach_parent()
    location = component.get_world_location()
    return {
        "name": component.get_name(),
        "owner": owner.get_actor_label() if owner else None,
        "mesh": mesh,
        "visible": bool(component.is_visible()),
        "hiddenInGame": actor_flag(component, "hidden_in_game"),
        "rendered": rendered(component),
        "worldLocation": [round(v, 1) for v in location.to_tuple()],
        "attachParent": parent.get_name() if parent else None,
    }


def phase_stock():
    world = game_world()
    if not world:
        raise RuntimeError("no PIE world; start PIE first")
    print("TRUTH world %s" % world.get_path_name())
    controller = controller_of(world)
    phase = drive_to_preparation(controller)
    if not phase.endswith("PREPARATION"):
        raise RuntimeError("the fixture needs Preparation, got %s" % phase)
    controller.stock_board_for_fixture(HUMAN, CHECK_CHARACTERS)
    placed = []
    for player in controller.match_state.players:
        if str(player.player_id) != HUMAN:
            continue
        for unit in player.board_units:
            cell = unit.get_editor_property("board_cell")
            placed.append({"character": str(unit.get_editor_property("character_id")),
                           "cell": [int(cell.x), int(cell.y)]})
    state = read(STATE)
    state.update({"phase": phase, "placed": placed, "requested": CHECK_CHARACTERS})
    write(STATE, state)
    print("TRUTH stocked placed=%d" % len(placed))


def phase_measure():
    world = game_world()
    if not world:
        raise RuntimeError("no PIE world; start PIE first")
    print("TRUTH world %s phase=%s" % (world.get_path_name(),
                                       phase_name(controller_of(world))))
    presenters = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.TreadM3BoardPresenter)
    if not presenters:
        raise RuntimeError("no presenter")
    presenter = presenters[0]

    doc = read(REPORT)
    doc.update({"schema": "Tread.N2.RenderTruth.v1", "world": world.get_path_name(),
                "presenterLocation": [round(v, 1) for v in presenter.get_actor_location().to_tuple()]})

    bodies, rings = [], []
    for component in presenter.get_components_by_class(unreal.SkeletalMeshComponent):
        if component.get_skeletal_mesh_asset():
            bodies.append(describe(component))
    for component in presenter.get_components_by_class(unreal.StaticMeshComponent):
        if component.get_editor_property("static_mesh"):
            rings.append(describe(component))
    bodies.sort(key=lambda row: (row["mesh"] or "", row["name"]))
    doc["presenterBodies"] = bodies
    doc["presenterRings"] = rings
    print("TRUTH presenter bodies=%d rendered=%d | rings=%d rendered=%d" % (
        len(bodies), sum(1 for r in bodies if r["rendered"]), len(rings),
        sum(1 for r in rings if r["rendered"])))
    for row in bodies:
        print("   body mesh=%-22s vis=%-5s hidden=%-5s rendered=%-5s loc=%s parent=%s" % (
            row["mesh"], row["visible"], row["hiddenInGame"], row["rendered"],
            row["worldLocation"], row["attachParent"]))
    for row in rings:
        print("   ring mesh=%-22s vis=%-5s rendered=%-5s loc=%s" % (
            row["mesh"], row["visible"], row["rendered"], row["worldLocation"]))

    # ---- every skeletal mesh actor the world has, and whether it drew --------------------
    census = []
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.SkeletalMeshActor):
        component = actor.get_component_by_class(unreal.SkeletalMeshComponent)
        if not component:
            continue
        row = describe(component)
        row["actor"] = actor.get_actor_label()
        row["actorHidden"] = actor_flag(actor, "hidden")
        row["actorHiddenEd"] = bool(actor.is_hidden_ed()) if hasattr(actor, "is_hidden_ed") else None
        census.append(row)
    doc["worldSkeletalActors"] = census
    print("TRUTH world skeletal actors=%d rendered=%d" % (
        len(census), sum(1 for r in census if r["rendered"])))
    for row in census:
        print("   actor=%-28s mesh=%-22s hidden=%-5s rendered=%-5s loc=%s" % (
            row["actor"], row["mesh"], row["actorHidden"], row["rendered"], row["worldLocation"]))

    # ---- control: is the viewport drawing at all? ----------------------------------------
    static_total = static_rendered = 0
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.StaticMeshActor):
        component = actor.get_component_by_class(unreal.StaticMeshComponent)
        if not component or not component.get_editor_property("static_mesh"):
            continue
        static_total += 1
        if rendered(component):
            static_rendered += 1
    doc["worldStaticMeshControl"] = {"total": static_total, "rendered": static_rendered}
    write(REPORT, doc)
    print("TRUTH control: world static meshes %d/%d rendered" % (static_rendered, static_total))

    unreal.SystemLibrary.execute_console_command(world, "DisplayAll USkeletalMeshComponent Bounds")
    unreal.SystemLibrary.execute_console_command(world, "HighResShot 1")
    print("TRUTH HighResShot requested")


def census(world):
    presenters = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.TreadM3BoardPresenter)
    if not presenters:
        raise RuntimeError("no presenter")
    presenter = presenters[0]
    bodies = [c for c in presenter.get_components_by_class(unreal.SkeletalMeshComponent)
              if c.get_skeletal_mesh_asset()]
    mmd = [c for c in bodies if "/%s/" % SET_TAG in c.get_skeletal_mesh_asset().get_path_name()]
    return presenter, {
        "bodies": len(bodies), "mmdBodies": len(mmd), "heroBodies": len(bodies) - len(mmd),
        "visible": sum(1 for c in bodies if c.is_visible()),
        "meshes": sorted({c.get_skeletal_mesh_asset().get_name() for c in bodies}),
    }


def phase_census():
    """Just report what the presenter has built this frame; the caller polls it.

    The presenter builds its components from Tick(), so a fresh PIE session has none until the game
    has run for a few frames and the board is stocked.  A host-side poll is the only way to wait for
    that: Python remote execution runs on the game thread, so this process cannot sleep.
    """
    world = game_world()
    if not world:
        raise RuntimeError("no PIE world; start PIE first")
    _, counts = census(world)
    print("TRUTH census bodies=%d mmd=%d hero=%d visible=%d" % (
        counts["bodies"], counts["mmdBodies"], counts["heroBodies"], counts["visible"]))
    print("TRUTH meshes %s" % counts["meshes"])


def phase_shoot():
    """Freeze the match and take the acceptance shot from the game viewport itself.

    HighResShot is the only capture path that draws what the game actually renders; the editor
    viewport capture (Tools/ue_shot.py) does not draw PIE runtime actors at all.  slomo 0 first,
    so a drifting round cannot walk into the frame between the census and the shot.
    """
    world = game_world()
    if not world:
        raise RuntimeError("no PIE world; start PIE first")
    _, counts = census(world)
    unreal.SystemLibrary.execute_console_command(world, "slomo 0")
    doc = read(REPORT)
    doc["acceptShot"] = dict(counts, world=world.get_path_name())
    write(REPORT, doc)
    print("TRUTH shoot bodies=%d mmd=%d hero=%d visible=%d" % (
        counts["bodies"], counts["mmdBodies"], counts["heroBodies"], counts["visible"]))
    print("TRUTH meshes %s" % counts["meshes"])
    unreal.SystemLibrary.execute_console_command(world, "HighResShot 2560x1440")
    print("TRUTH HighResShot requested")


def phase_shoot_hidden():
    """The A/B half of the acceptance pair: same frame, same camera, every MMD body hidden.

    set_hidden_in_game, not set_visibility: Place() re-applies visibility on every tick, so a
    component-level visibility toggle does nothing, while hidden-in-game survives it.
    """
    world = game_world()
    if not world:
        raise RuntimeError("no PIE world; start PIE first")
    presenter, counts = census(world)
    hidden = 0
    for component in presenter.get_components_by_class(unreal.SkeletalMeshComponent):
        asset = component.get_skeletal_mesh_asset()
        if asset and "/%s/" % SET_TAG in asset.get_path_name():
            component.set_hidden_in_game(True)
            hidden += 1
    print("TRUTH shoot_hidden hid=%d of %d bodies" % (hidden, counts["bodies"]))
    unreal.SystemLibrary.execute_console_command(world, "HighResShot 2560x1440")
    print("TRUTH HighResShot requested")


def phase_unfreeze():
    """Put time dilation back; slomo is a console variable and outlives the PIE session."""
    unreal.SystemLibrary.execute_console_command(None, "slomo 1")
    print("TRUTH slomo reset")


PHASES = {"load": phase_load, "stock": phase_stock, "measure": phase_measure, "census": phase_census,
          "shoot": phase_shoot, "shoot_hidden": phase_shoot_hidden,
          "unfreeze": phase_unfreeze, "restore": phase_restore}

phase = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in PHASES else ""
if not phase:
    raise RuntimeError("phase must be one of %s" % sorted(PHASES))
PHASES[phase]()
