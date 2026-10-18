# -*- coding: utf-8 -*-
"""Export every landmark .blend to FBX (UE-ready, metres -> centimetres)."""
import bpy
import os
import json

LM_DIR = r"E:\AI\Tread\Tread\model\warsaw\landmarks"
FILES = ["Warsaw_01_Rynek.blend", "Warsaw_02_Zamek.blend", "Warsaw_03_Barbakan.blend",
         "Warsaw_04_Lazienki.blend", "Warsaw_05_Stadion.blend", "Warsaw_06_PKin.blend"]

out = []
for f in FILES:
    src = os.path.join(LM_DIR, f)
    if not os.path.exists(src):
        out.append({"file": f, "error": "missing"})
        continue
    bpy.ops.wm.open_mainfile(filepath=src)
    dst = os.path.splitext(src)[0] + ".fbx"
    bad = os.path.splitext(src)[0] + "..fbx"
    if os.path.exists(bad):
        os.remove(bad)
    bpy.ops.object.select_all(action="DESELECT")
    for ob in bpy.data.objects:
        if ob.type == "MESH":
            ob.select_set(True)
    try:
        bpy.ops.export_scene.fbx(
            filepath=dst, use_selection=True, object_types={"MESH"},
            apply_unit_scale=True, apply_scale_options="FBX_SCALE_ALL",
            bake_space_transform=False, mesh_smooth_type="FACE",
            use_mesh_modifiers=True, add_leaf_bones=False, path_mode="AUTO",
            embed_textures=False,
        )
        out.append({"file": f, "fbx": dst, "bytes": os.path.getsize(dst)})
    except Exception as e:
        out.append({"file": f, "error": "%s: %s" % (type(e).__name__, e)})

print("HEADLESS " + json.dumps({"exports": out}, ensure_ascii=False))
