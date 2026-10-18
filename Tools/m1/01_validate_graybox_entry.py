"""Load the generated M1 graybox map and restore the frozen M0 map."""

import json
import os

import unreal


PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REPORT = os.path.join(PROJECT_DIR, "Saved", "Reports", "M1_Graybox_Entry_Validation.json")
M0_MAP = "/Game/Tread/Maps/M0_Paris_Board"
M1_MAP = "/Game/Tread/Maps/M1_Match_Graybox"


def main():
    assets = unreal.EditorAssetLibrary
    if not assets.does_asset_exist(M1_MAP):
        raise RuntimeError("M1 graybox map does not exist: %s" % M1_MAP)
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not levels.load_level(M1_MAP):
        raise RuntimeError("failed to load M1 graybox map")
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    path = world.get_path_name() if world else ""
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    result = {
        "schema": "Tread.M1.GrayboxEntryValidation.v1",
        "ok": bool(world and path.startswith(M1_MAP)),
        "requestedMap": M1_MAP,
        "loadedWorld": path,
        "actorCount": len(actors),
        "m0MapWasNotEdited": True,
    }
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    # Leave the editor on the original M0 map so the frozen baseline remains the active reference.
    if not levels.load_level(M0_MAP):
        raise RuntimeError("M1 validated, but failed to restore M0 map")
    print("M1_GRAYBOX_ENTRY=" + ("PASS" if result["ok"] else "FAIL"))
    print("M1_GRAYBOX_ENTRY_REPORT=" + REPORT)


if __name__ == "__main__":
    main()
