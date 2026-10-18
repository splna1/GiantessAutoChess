"""Editor-side M2 cross-check (run via Tools/ue_run.py inside the live editor, PIE started through Unreal MCP).

Phase "start": load the M1 graybox map (refuses if anything is dirty).
Phase "run":   find the PIE ATreadM1MatchController and call RunM2PactSelfTest -> Saved/Reports/M2_Pact_SelfTest_PIE.json.
Phase "restore": reload the M0 map that the editor started on.
Usage: python Tools/ue_run.py Tools/m2/editor_pie_m2_selftest.py <start|run|restore>
"""
import os
import sys

import unreal

PHASE = sys.argv[1] if len(sys.argv) > 1 else "run"
PROJECT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
OUT = os.path.join(PROJECT, "Saved", "Reports", "M2_Pact_SelfTest_PIE.json")

if PHASE == "start":
    dirty = unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages() + unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
    if dirty:
        raise RuntimeError("dirty packages present, refusing to switch map: %s" % [p.get_name() for p in dirty])
    unreal.EditorLoadingAndSavingUtils.load_map("/Game/Tread/Maps/M1_Match_Graybox")
    print("LOADED", unreal.EditorLevelLibrary.get_editor_world().get_path_name())
elif PHASE == "run":
    worlds = unreal.EditorLevelLibrary.get_pie_worlds(False) if hasattr(unreal.EditorLevelLibrary, "get_pie_worlds") else []
    if not worlds:
        worlds = [unreal.UnrealEditorSubsystem().get_game_world()] if hasattr(unreal, "UnrealEditorSubsystem") else []
    worlds = [w for w in worlds if w]
    if not worlds:
        raise RuntimeError("no PIE world; start PIE first")
    controllers = unreal.GameplayStatics.get_all_actors_of_class(worlds[0], unreal.TreadM1MatchController)
    if not controllers:
        raise RuntimeError("no TreadM1MatchController in PIE world %s" % worlds[0].get_path_name())
    ok = controllers[0].run_m2_pact_self_test(OUT)
    print("PIE_WORLD", worlds[0].get_path_name())
    print("M2_PIE_SELFTEST", "PASS" if ok else "FAIL", OUT)
elif PHASE == "restore":
    unreal.EditorLoadingAndSavingUtils.load_map("/Game/Tread/Maps/M0_Paris_Board")
    print("RESTORED", unreal.EditorLevelLibrary.get_editor_world().get_path_name())
