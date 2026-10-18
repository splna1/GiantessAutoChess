"""M4 (editor-side, Tools/ue_run.py): import the converted roster VRMs as skeletal meshes.

Source: Saved/Staging/vrm_fbx/<char_0xx>/SK_VRM_<char_0xx>.fbx (blender_vrm_to_fbx.py: centimetres, yaw 180).
Target: /Game/Tread/Characters/VRM/<char_0xx>/SK_VRM_<char_0xx> (+ its own skeleton and physics asset; materials are
assigned by ue_vrm_materials.py).  Same contract as ue_import_mmd.py (document/151):

    python Tools/ue_run.py Tools/m4/ue_import_vrm.py [--only char_002,char_003] [--reimport] [--limit N]

Existing meshes are kept unless --reimport, which imports over the existing asset in place (same skeleton, rest
pose updated) and never deletes the character folder: deleting an IK Rig an IK Retargeter still references
crashes the editor (memory: tread-editor-ikrig-crash).  --limit stops after N new imports so a long batch can run
as several remote calls.  Writes Saved/Reports/M4_VRM_Import.json, merged per character.
"""
import json
import os
import sys

import unreal

PROJECT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
SRC = os.path.join(PROJECT, "Saved", "Staging", "vrm_fbx")
DEST = "/Game/Tread/Characters/VRM"
REPORT = os.path.join(PROJECT, "Saved", "Reports", "M4_VRM_Import.json")
EAL = unreal.EditorAssetLibrary


def import_one(cid, reimport):
    folder = "%s/%s" % (DEST, cid)
    name = "SK_VRM_" + cid
    path = "%s/%s" % (folder, name)
    existing = EAL.load_asset(path) if EAL.does_asset_exist(path) else None
    orphan = "%s/%s_Skeleton" % (folder, name)
    if existing is None and EAL.does_asset_exist(orphan):
        # A crash mid-import (2026-10-12: GPU crash on char_054) leaves the new skeleton without its mesh; nothing
        # references it yet, and leaving it would make the importer name the fresh skeleton *_Skeleton1.
        EAL.delete_asset(orphan)
    imported = False
    if existing is None or reimport:
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
        # Materials come from ue_vrm_materials.py; the FBX carries no texture paths (path_mode STRIP).
        opt.import_materials = False
        opt.import_textures = False
        opt.create_physics_asset = existing is None
        opt.mesh_type_to_import = unreal.FBXImportType.FBXIT_SKELETAL_MESH
        sk = opt.skeletal_mesh_import_data
        sk.convert_scene = True
        sk.import_uniform_scale = 1.0
        if existing is not None:
            opt.skeleton = existing.get_editor_property("skeleton")
            sk.set_editor_property("update_skeleton_reference_pose", True)
        task.options = opt
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        imported = True
    mesh = EAL.load_asset(path)
    if mesh is None:
        return {"characterId": cid, "ok": False, "error": "import failed"}, imported
    bounds = mesh.get_bounds()
    skeleton = mesh.get_editor_property("skeleton")
    return {"characterId": cid, "ok": True, "asset": path, "skeleton": skeleton.get_path_name() if skeleton else None,
            "heightCm": round(bounds.box_extent.z * 2, 1), "boundsOriginCm": [round(v, 1) for v in bounds.origin.to_tuple()],
            "materials": len(mesh.get_editor_property("materials")),
            "morphTargets": len(mesh.get_editor_property("morph_targets"))}, imported


def main():
    reimport = "--reimport" in sys.argv
    only = set(sys.argv[sys.argv.index("--only") + 1].split(",")) if "--only" in sys.argv else set()
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 0
    ids = sorted(d for d in os.listdir(SRC) if d.startswith("char_") and (not only or d in only)
                 and os.path.isfile(os.path.join(SRC, d, "SK_VRM_%s.fbx" % d)))
    old = json.load(open(REPORT, encoding="utf-8")) if os.path.exists(REPORT) else {"models": []}
    merged = {r["characterId"]: r for r in old.get("models", [])}
    done = 0
    for cid in ids:
        row, imported = import_one(cid, reimport)
        merged[cid] = row
        print("VRM_IMPORT", json.dumps(row, ensure_ascii=False))
        if imported:
            done += 1
            unreal.SystemLibrary.execute_console_command(None, "Tread.FlushThumbnailScenes")  # TreadEditorThumbnails.cpp
            unreal.SystemLibrary.execute_console_command(None, "obj gc")
            # Write as we go: a 99-model batch runs for hours and the report is the resume point.
            with open(REPORT, "w", encoding="utf-8") as f:
                json.dump({"schema": "Tread.M4.VrmImport.v1", "models": [merged[k] for k in sorted(merged)]},
                          f, ensure_ascii=False, indent=1)
            if limit and done >= limit:
                break
    models = [merged[k] for k in sorted(merged)]
    report = {"schema": "Tread.M4.VrmImport.v1", "ok": bool(models) and all(r["ok"] for r in models),
              "count": len(models), "models": models}
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    remaining = [c for c in ids if c not in merged]
    print("M4_VRM_IMPORT", "PASS" if report["ok"] else "PARTIAL", len(models), "imported_now=%d remaining=%d" % (done, len(remaining)))


main()
