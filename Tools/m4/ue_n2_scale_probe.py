"""N2 (editor-side, Tools/ue_run.py): import each FBX scale variant and measure what UE makes of it.

Companion to Tools/m4/n2_fbx_scale_probe.py.  For every variant under Saved/Staging/n2_scaleprobe/
this imports the FBX into the scratch folder /Game/Tread/Characters/_N2ScaleProbe/<variant> with the
same import options the real pipeline uses, then reports the two numbers that decide the matter:

  * heightCm -- the mesh bounds.  Must stay ~160 for char_101.  A factor of 100 out either way
    (1.6 or 16000) means the unit conversion went somewhere UE does not expect it.
  * reference root bone scale and bone extent -- the same measurement n2_anim_pose_probe.py takes on
    the imported asset.  Scale 100 here is the bug: a retargeted clip writes scale 1 on that bone and
    collapses the mesh to 1 % of its size.

    python Tools/ue_run.py Tools/m4/ue_n2_scale_probe.py measure
    python Tools/ue_run.py Tools/m4/ue_n2_scale_probe.py cleanup

Report: Saved/Reports/N2_FbxScaleProbeUE.json  (the host-side half writes N2_FbxScaleProbe.json;
these used to share one name, so this one silently overwrote the Blender-side record)
"""
import json
import math
import os
import sys

import unreal

PROJECT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
SRC = os.path.join(PROJECT, "Saved", "Staging", "n2_scaleprobe")
REPORT = os.path.join(PROJECT, "Saved", "Reports", "N2_FbxScaleProbeUE.json")
DEST = "/Game/Tread/Characters/_N2ScaleProbe"
EAL = unreal.EditorAssetLibrary
APE = unreal.AnimPoseExtensions
SPACE = unreal.AnimPoseSpaces.WORLD


def import_one(variant, fbx, name):
    folder = "%s/%s" % (DEST, variant)
    if EAL.does_directory_exist(folder):
        EAL.delete_directory(folder)
    task = unreal.AssetImportTask()
    task.filename = fbx
    task.destination_path = folder
    task.destination_name = name
    task.automated = True
    task.replace_existing = True
    task.save = False
    opt = unreal.FbxImportUI()
    opt.import_mesh = True
    opt.import_as_skeletal = True
    opt.import_animations = False
    opt.import_materials = False
    opt.import_textures = False
    opt.create_physics_asset = False
    opt.mesh_type_to_import = unreal.FBXImportType.FBXIT_SKELETAL_MESH
    sk = opt.skeletal_mesh_import_data
    sk.convert_scene = True
    sk.import_uniform_scale = 1.0
    task.options = opt
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    return unreal.EditorAssetLibrary.load_asset("%s/%s" % (folder, name))


def reference_of(skeleton):
    pose = APE.get_reference_pose(skeleton)
    names = list(APE.get_bone_names(pose))
    lo, hi = [math.inf] * 3, [-math.inf] * 3
    for name in names:
        p = APE.get_bone_pose(pose, name, SPACE).translation.to_tuple()
        for i in range(3):
            lo[i] = min(lo[i], p[i])
            hi[i] = max(hi[i], p[i])
    root = APE.get_bone_pose(pose, names[0], SPACE) if names else None
    return {
        "bones": len(names),
        "rootBone": str(names[0]) if names else None,
        "rootScale": None if root is None else [round(v, 4) for v in root.scale3d.to_tuple()],
        "extentCm": [round(hi[i] - lo[i], 2) for i in range(3)],
    }


def phase_measure():
    rows = []
    for variant in sorted(os.listdir(SRC)) if os.path.isdir(SRC) else []:
        folder = os.path.join(SRC, variant)
        fbx = [f for f in os.listdir(folder) if f.lower().endswith(".fbx")] if os.path.isdir(folder) else []
        if not fbx:
            continue
        name = os.path.splitext(fbx[0])[0]
        mesh = import_one(variant, os.path.join(folder, fbx[0]), name)
        if mesh is None:
            rows.append({"variant": variant, "error": "import failed"})
            print("SCALEUE", variant, "import failed")
            continue
        bounds = mesh.get_bounds()
        skeleton = mesh.get_editor_property("skeleton")
        row = {"variant": variant, "asset": mesh.get_path_name(),
               "heightCm": round(bounds.box_extent.z * 2, 2),
               "minCm": [round(v, 2) for v in bounds.origin.to_tuple()],
               "skeleton": skeleton.get_path_name() if skeleton else None}
        row.update(reference_of(skeleton) if skeleton else {})
        rows.append(row)
        print("SCALEUE %-8s height=%-9s root=%-24s rootScale=%s extent=%s" % (
            variant, row["heightCm"], row.get("rootBone"), row.get("rootScale"), row.get("extentCm")))
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump({"schema": "Tread.N2.FbxScaleProbeUE.v1", "rows": rows}, f, ensure_ascii=False, indent=1)


def phase_cleanup():
    if EAL.does_directory_exist(DEST):
        EAL.delete_directory(DEST)
    print("SCALEUE cleaned", DEST)


PHASES = {"measure": phase_measure, "cleanup": phase_cleanup}
phase = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in PHASES else ""
if not phase:
    raise RuntimeError("phase must be one of %s" % sorted(PHASES))
PHASES[phase]()
