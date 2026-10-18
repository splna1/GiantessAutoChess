"""N2 (a) acceptance: stand tier-VI and fallback characters on the 3D board in PIE and check the models.

The fixture lives in the controller (ATreadM1MatchController::StockBoardForFixture) because Python
cannot write MatchState -- it is BlueprintReadOnly -- and cannot spawn actors into a PIE world.  The
match itself is driven with the public commands a UI would use.

    python Tools/ue_run.py Tools/m4/n2_pie_board_check.py prepare
    # MCP: EditorToolset.EditorAppToolset StartPIE
    python Tools/ue_run.py Tools/m4/n2_pie_board_check.py stock
    # MCP: EditorToolset.EditorAppToolset CaptureViewport (Tools/ue_shot.py) for the screenshot
    # MCP: EditorToolset.EditorAppToolset StopPIE
    python Tools/ue_run.py Tools/m4/n2_pie_board_check.py restore

  prepare  guard against dirty packages, remember the open map, load M3_Paris_Match
  stock    drive the match to Preparation, stock the board, report the meshes the presenter attached
  restore  reload the map that "prepare" remembered

Report: Saved/Reports/N2_PieBoardCheck.json
"""
import json
import os
import sys

import unreal

PROJECT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
REPORTS = os.path.join(PROJECT, "Saved", "Reports")
STATE = os.path.join(REPORTS, "N2_PieBoard_state.json")
REPORT = os.path.join(REPORTS, "N2_PieBoardCheck.json")

M3_MAP = "/Game/Tread/Maps/M3_Paris_Match"
HUMAN = "P0"
# char_101..112 are the twelve MMD characters; char_001/char_050 must keep the M1 hero, and char_100 is
# the trap case (its VRM id sits inside the char_1xx range but it has no MMD model).
CHECK_CHARACTERS = (["char_%03d" % n for n in range(101, 113)] + ["char_001", "char_050", "char_100"])
PHASES = ("prepare", "stock", "restore")


def write(path, doc):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, ensure_ascii=False, indent=1)


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


def controller_of(world):
    found = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.TreadM1MatchController)
    if not found:
        raise RuntimeError("no TreadM1MatchController in %s" % world.get_path_name())
    return found[0]


def presenter_of(world):
    found = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.TreadM3BoardPresenter)
    return found[0] if found else None


def phase_name(controller):
    # str() renders as "<TreadM1Phase.R0_BRIEFING: 1>"; the enum's own name is what the checks below want
    return controller.get_phase().name


def drive_to_preparation(controller):
    phase = phase_name(controller)
    print("PHASE_START %s" % phase)
    if phase.endswith("MAIN_MENU") or phase.endswith("R0_BRIEFING"):
        controller.begin_pre_match_bp("n2chk-bp")
        phase = phase_name(controller)
        print("PHASE_AFTER_BP %s" % phase)
    if phase.endswith("PRE_MATCH_BP"):
        available = [str(s) for s in controller.match_state.bp.available_strategy_ids]
        if available:
            controller.choose_player_strategy(available[0], "n2chk-strategy")
        for pick in range(3):
            controller.run_next_ai_pick("n2chk-ai-%d" % pick)
        controller.confirm_pre_match_bp("n2chk-confirm")
        phase = phase_name(controller)
        print("PHASE_AFTER_CONFIRM %s" % phase)
    if not (phase.endswith("PREPARATION") or phase.endswith("BATTLE") or phase.endswith("SETTLEMENT")):
        controller.begin_preparation("n2chk-prep")
        phase = phase_name(controller)
    print("PHASE_READY %s" % phase)
    return phase


def phase_prepare():
    if game_world():
        raise RuntimeError("a PIE session is already running")
    dirty = unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages() + unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
    if dirty:
        raise RuntimeError("dirty packages present, refusing to switch map: %s" % [p.get_name() for p in dirty])
    previous = unreal.EditorLevelLibrary.get_editor_world().get_path_name().split(".")[0]
    write(STATE, {"previousMap": previous})
    if not unreal.EditorLoadingAndSavingUtils.load_map(M3_MAP):
        raise RuntimeError("failed to load " + M3_MAP)
    print("N2_PREPARED map=%s previous=%s" % (unreal.EditorLevelLibrary.get_editor_world().get_path_name(), previous))


def phase_restore():
    previous = ""
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as handle:
            previous = json.load(handle).get("previousMap", "")
    if not previous:
        raise RuntimeError("no remembered map; run prepare first")
    if game_world():
        raise RuntimeError("stop PIE before restoring the map")
    if not unreal.EditorLoadingAndSavingUtils.load_map(previous):
        raise RuntimeError("failed to restore " + previous)
    print("N2_RESTORED %s" % unreal.EditorLevelLibrary.get_editor_world().get_path_name())


def phase_stock():
    world = game_world()
    if not world:
        raise RuntimeError("no PIE world; start PIE first")
    controller = controller_of(world)
    phase = drive_to_preparation(controller)
    if not phase.endswith("PREPARATION"):
        raise RuntimeError("the fixture needs the Preparation phase, got %s" % phase)
    controller.stock_board_for_fixture(HUMAN, CHECK_CHARACTERS)

    presenter = presenter_of(world)
    if not presenter:
        raise RuntimeError("no TreadM3BoardPresenter in %s" % world.get_path_name())
    installed = []
    for component in presenter.get_components_by_class(unreal.SkeletalMeshComponent):
        mesh = component.get_skeletal_mesh_asset()
        if mesh:
            installed.append({"mesh": mesh.get_name(), "visible": component.is_visible()})
    installed.sort(key=lambda row: row["mesh"])
    # the presenter's GetAnchors() takes an output array and is not a UFUNCTION, so read the board back
    # off the match state instead
    placed = []
    for player in controller.match_state.players:
        if str(player.player_id) != HUMAN:
            continue
        for unit in player.board_units:
            cell = unit.get_editor_property("board_cell")
            placed.append({"character": str(unit.get_editor_property("character_id")),
                           "cell": [int(cell.x), int(cell.y)]})
    placed.sort(key=lambda row: (row["cell"][1], row["cell"][0]))

    counts = {}
    for row in installed:
        counts[row["mesh"]] = counts.get(row["mesh"], 0) + 1
    doc = {"schema": "Tread.N2.PieBoardCheck.v1", "phase": phase, "requested": CHECK_CHARACTERS,
           "placed": placed, "placedCount": len(placed), "meshCounts": counts, "meshes": installed}
    write(REPORT, doc)
    print("N2_STOCK placed=%d meshes=%s" % (len(placed), counts))
    missing = [c for c in CHECK_CHARACTERS if c not in [row["character"] for row in placed]]
    print("N2_STOCK missing=%s" % missing)
    for row in installed:
        print("   %-24s visible=%s" % (row["mesh"], row["visible"]))


def main():
    phase = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in PHASES else ""
    if not phase:
        raise RuntimeError("phase must be one of %s" % sorted(PHASES))
    {"prepare": phase_prepare, "stock": phase_stock, "restore": phase_restore}[phase]()


main()
