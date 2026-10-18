"""Remove the placeholder Local Fog Volume smoke from M3_Paris_Match (owner request, 2026-10-17).

The battlefield smoke is stacked LocalFogVolume ellipsoids (Tools/paris/07_fx.py, 07_fx_industrial.py)
that read as a few big flat circles and occlude the units on the board (Battle_Run.png etc.). Real
smoke replaces them later; until then the battle map carries no LFV smoke at all. Fire (flame cards,
ember beds, fire lights) and scorch decals stay - they sit on roofs and rubble, they do not cover units.

Editor side, PIE must be stopped; run once:
    python Tools/ue_run.py Tools/battle/remove_board_smoke.py

Writes Saved/Reports/Battle_Smoke_Removal.json with the removed actor labels.
"""
import json
import os

import unreal

MAP = "/Game/Tread/Maps/M3_Paris_Match"
REPORT = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()),
                      "Saved", "Reports", "Battle_Smoke_Removal.json")


def main():
    if unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world():
        raise RuntimeError("stop PIE before editing the map")
    dirty = (unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
             + unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    if dirty:
        raise RuntimeError("dirty packages present: %s" % [p.get_name() for p in dirty][:10])
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not unreal.EditorLevelLibrary.get_editor_world().get_path_name().startswith(MAP):
        if not les.load_level(MAP):
            raise RuntimeError("failed to load " + MAP)
    removed = []
    for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
        if a.get_class().get_name() != "LocalFogVolume":
            continue
        removed.append(a.get_actor_label())
        a.destroy_actor()
    if not les.save_current_level():
        raise RuntimeError("failed to save " + MAP)
    with open(REPORT, "w", encoding="utf-8") as handle:
        json.dump({"map": MAP, "removedLocalFogVolumes": sorted(removed), "count": len(removed)}, handle,
                  ensure_ascii=False, indent=1)
    print("SMOKE removed %d local fog volumes -> %s" % (len(removed), REPORT))


main()
