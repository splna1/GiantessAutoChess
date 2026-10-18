"""Read-only M0 technical validation: bounds, rendering switches, assets, tags and frozen-board hash."""
import hashlib
import json
import os
import sys

import unreal
import paris_common as pc


def asset_bounds(path):
    asset = pc.load(path)
    if isinstance(asset, unreal.StaticMesh):
        box = asset.get_bounding_box()
        tris = [asset.get_num_triangles(i) for i in range(asset.get_num_lods())]
        return {"path": path, "type": "StaticMesh", "bounds_cm": [[box.min.x, box.min.y, box.min.z], [box.max.x, box.max.y, box.max.z]],
                "lods": tris, "nanite": bool(asset.get_editor_property("nanite_settings").enabled)}
    if isinstance(asset, unreal.SkeletalMesh):
        bounds = asset.get_bounds()
        origin = bounds.get_editor_property("origin")
        extent = bounds.get_editor_property("box_extent")
        box = (origin - extent, origin + extent)
        return {"path": path, "type": "SkeletalMesh", "bounds_cm": [[box[0].x, box[0].y, box[0].z], [box[1].x, box[1].y, box[1].z]],
                "lods": "unreal_python_api_not_exposed"}
    return {"path": path, "type": asset.get_class().get_name() if asset else None}


def console_int(name):
    try:
        return unreal.SystemLibrary.get_console_variable_int_value(name)
    except Exception:
        return None


def main(argv):
    pc.ensure_map_loaded()
    actors = pc.actor_sub().get_all_level_actors()
    labels = {a.get_actor_label(): a for a in actors}
    hero = labels.get("Char_Clukay416")
    hero_box = None
    if hero:
        hero_component = hero.get_editor_property("skeletal_mesh_component")
        hero_asset = hero_component.get_editor_property("skeletal_mesh")
        if hero_asset:
            hero_bounds = hero_asset.get_bounds()
            origin = hero_bounds.get_editor_property("origin")
            extent = hero_bounds.get_editor_property("box_extent")
            hero_box = (origin - extent, origin + extent)
    report = {"map": pc.world().get_path_name(), "ok": True, "rendering": {
        "nanite": console_int("r.Nanite"), "virtual_shadow_maps": console_int("r.Shadow.Virtual.Enable"),
        "lumen_gi": console_int("r.DynamicGlobalIlluminationMethod"), "lumen_reflections": console_int("r.ReflectionMethod")},
        "actors": {"hero": bool(hero), "hero_selectable_tag": bool(hero and hero.actor_has_tag("M0Selectable")),
                   "blue_ring": bool(labels.get("Ring_Blue_Clukay")), "red_ring": bool(labels.get("Ring_Red_Enemy")),
                   "board_camera": bool(labels.get("Board_Camera"))},
        "hero_asset_bounds_m": ([[hero_box[0].x / 100.0, hero_box[0].y / 100.0, hero_box[0].z / 100.0],
                                  [hero_box[1].x / 100.0, hero_box[1].y / 100.0, hero_box[1].z / 100.0]] if hero_box else None),
        "assets": [], "idle": pc.EAL.does_asset_exist(pc.CHAR + "/Clukay416/Anim/GP/A_GP_Idle"),
        "frozen_board_sha256": hashlib.sha256(open(os.path.join(os.path.dirname(__file__), "board_frozen.json"), "rb").read()).hexdigest()}
    asset_paths = [pc.CHAR + "/Clukay416/SK_Clukay416", pc.CHAR + "/Clukay416/416/SkeletalMeshes/U_Char_1",
                   pc.CITY + "/Landmarks/SM_EiffelTower", pc.CITY + "/Meshes/Ruins/SM_CollapsedBuilding_Scan"]
    for path in asset_paths:
        try:
            report["assets"].append(asset_bounds(path))
        except Exception as exc:
            report["ok"] = False
            report["assets"].append({"path": path, "error": repr(exc)})
    report["ok"] = report["ok"] and all(report["actors"].values()) and report["idle"]
    pc.write_json(pc.REPORT_DIR + "/M0_Technical_Validation.json", report)
    pc.log("M0 technical validation", report)


main(sys.argv[1:])
