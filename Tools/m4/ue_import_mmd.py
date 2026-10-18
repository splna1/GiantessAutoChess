"""N2 (editor-side, Tools/ue_run.py): import the 12 converted MMD models as skeletal meshes.

Source: Saved/Staging/mmd_fbx/<char_1xx>/SK_MMD_<char_1xx>.fbx (blender_mmd_to_fbx.py, textures embedded).
Target: /Game/Tread/Characters/MMD/<char_1xx>/SK_MMD_<char_1xx> (+ its skeleton, physics asset, materials, textures).
Each model keeps its own skeleton (MMD bone sets differ per model); retargeting the GP animations onto them is a
separate step. Writes Saved/Reports/N2_MMD_Import.json. Idempotent: existing meshes are kept unless --rebuild.

    python Tools/ue_run.py Tools/m4/ue_import_mmd.py [--rebuild | --reimport] [--only char_1xx]

--reimport imports the FBX over the existing mesh in place (same asset, same skeleton, skeleton reference
pose updated) and leaves the character's Retarget/ and Anim/ folders alone.  Use it after a re-export:
--rebuild deletes the character folder, and deleting an IK Rig an IK Retargeter still references
crashes the editor (2026-10-11).  Afterwards rerun ue_mmd_materials.py and n2_build_retarget.py.
"""
import json
import os
import sys

import unreal

PROJECT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
SRC = os.path.join(PROJECT, "Saved", "Staging", "mmd_fbx")
DEST = "/Game/Tread/Characters/MMD"
REPORT = os.path.join(PROJECT, "Saved", "Reports", "N2_MMD_Import.json")
EAL = unreal.EditorAssetLibrary


def import_one(cid, rebuild, reimport=False):
    folder = "%s/%s" % (DEST, cid)
    name = "SK_MMD_" + cid
    path = "%s/%s" % (folder, name)
    if rebuild and EAL.does_directory_exist(folder):
        # DeleteDirectory() quietly keeps any asset this editor process holds loaded, and AssetTools
        # then refuses to create the same name, so a rebuild can silently import nothing.  The mesh is
        # what decides that, so check it and refuse; leftover side folders (Retarget/) only warn.
        EAL.delete_directory(folder)
        if EAL.does_asset_exist(path):
            raise RuntimeError("--rebuild could not remove %s; close the editor or rename the asset first" % path)
        leftovers = EAL.list_assets(folder, recursive=True, include_folder=False)
        if leftovers:
            print("MMD_IMPORT warning: %d assets survived the rebuild under %s: %s"
                  % (len(leftovers), folder, leftovers[:4]))
    existing = EAL.load_asset(path) if reimport else None
    if reimport and existing is None:
        raise RuntimeError("--reimport: %s does not exist yet; import it first" % path)
    if existing is not None or not EAL.does_asset_exist(path):
        task = unreal.AssetImportTask()
        task.filename = os.path.join(SRC, cid, name + ".fbx")
        task.destination_path = folder
        task.destination_name = name
        task.automated = True
        task.replace_existing = True
        task.save = True
        opt = unreal.FbxImportUI()
        opt.import_mesh = True
        opt.import_as_skeletal = True
        opt.import_animations = False
        opt.import_materials = True
        opt.import_textures = True
        opt.create_physics_asset = True
        opt.mesh_type_to_import = unreal.FBXImportType.FBXIT_SKELETAL_MESH
        sk = opt.skeletal_mesh_import_data
        try:
            sk.set_editor_property("import_morph_targets", True)
        except Exception:
            pass  # UE 5.8 Python does not expose it; the FBX importer imports morph targets by default
        sk.convert_scene = True
        if existing is not None:
            # Same skeleton, new rest pose: the bones keep their names but every rest transform moved.
            opt.skeleton = existing.get_editor_property("skeleton")
            opt.create_physics_asset = False
            opt.import_materials = False
            opt.import_textures = False
            sk.set_editor_property("update_skeleton_reference_pose", True)
        sk.import_uniform_scale = 1.0
        opt.texture_import_data.material_search_location = unreal.MaterialSearchLocation.LOCAL
        task.options = opt
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    mesh = EAL.load_asset(path)
    if mesh is None:
        return {"characterId": cid, "ok": False, "error": "import failed"}
    bounds = mesh.get_bounds()
    skeleton = mesh.get_editor_property("skeleton")
    mats = mesh.get_editor_property("materials")
    textures = [a for a in EAL.list_assets(folder, recursive=True) if "Texture" in str(EAL.find_asset_data(a).asset_class_path.asset_name)]
    return {"characterId": cid, "ok": True, "asset": path, "skeleton": skeleton.get_path_name() if skeleton else None,
            "heightCm": round(bounds.box_extent.z * 2, 1), "materials": len(mats), "textures": len(textures),
            "morphTargets": len(mesh.get_editor_property("morph_targets"))}


def main():
    rebuild = "--rebuild" in sys.argv
    reimport = "--reimport" in sys.argv
    if rebuild and reimport:
        raise RuntimeError("--rebuild and --reimport are exclusive")
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else ""
    ids = sorted(d for d in os.listdir(SRC) if d.startswith("char_") and (not only or d == only))
    results = []
    for cid in ids:
        results.append(import_one(cid, rebuild, reimport))
        unreal.SystemLibrary.execute_console_command(None, "obj gc")
        print("MMD_IMPORT", json.dumps(results[-1], ensure_ascii=False))
    old = json.load(open(REPORT, encoding="utf-8")) if only and os.path.exists(REPORT) else {"models": []}
    merged = {r["characterId"]: r for r in old.get("models", [])}
    merged.update({r["characterId"]: r for r in results})
    report = {"schema": "Tread.N2.MmdImport.v1", "ok": all(r["ok"] for r in merged.values()) and len(merged) == 12,
              "models": [merged[k] for k in sorted(merged)]}
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("N2_MMD_IMPORT", "PASS" if report["ok"] else "PARTIAL", len(merged))


main()
