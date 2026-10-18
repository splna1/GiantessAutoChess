"""M3 asset import (editor-side, run through Tools/ue_run.py inside the open Tread editor).

Imports the Blender outputs into /Game/Tread/City/Paris/Meshes/M3 with Nanite:
  * Saved/Staging/m3_buildings/*.fbx      new procedural Paris buildings (blender_paris_buildings.py); their slots map
                                           onto the existing Haussmann material instances (same UV/vertex-colour rules)
  * Saved/Staging/m3_models/<set>/*.fbx    cleaned source models (blender_prepare_models.py) with their own textures
                                           (prepare_textures.py) on instances of the new master M_M3_Textured
Writes Saved/Reports/M3_Building_Assets.json. Idempotent: existing assets are kept unless --rebuild [name-filter].

    python Tools/ue_run.py Tools/m3/m3_import_assets.py [--rebuild [filter]] [--only filter]
"""
import json
import os
import re
import sys
import time

import unreal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "paris"))
import paris_common as pc  # noqa: E402
from matlib import Graph, MP, get_or_create_mi  # noqa: E402

STAGING = pc.STAGING_DIR
OUT = pc.MESH + "/M3"
TEX_OUT = pc.TEX + "/M3"
MAT_OUT = pc.MAT + "/M3"
MASTER = MAT_OUT + "/M_M3_Textured"
REPORT = pc.REPORT_DIR + "/M3_Building_Assets.json"

SETS = ["AM229_025", "AM229_030", "AM229_037", "AM229_042", "Oushi", "Stuka", "SE5"]
ASSET_NAMES = {"AM229_025": "SM_M3_AM025", "AM229_030": "SM_M3_AM030", "AM229_037": "SM_M3_AM037",
               "AM229_042": "SM_M3_AM042", "Stuka": "SM_M3_Stuka", "SE5": "SM_M3_SE5"}
PROC_SLOTS = {
    "stone": "MI_Stone_Limestone", "rustic": "MI_Stone_Rustic", "court": "MI_Stone_Stucco", "zinc": "MI_Zinc",
    "zincdark": "MI_Zinc_Dark", "glass": "MI_Glass", "shop": "MI_Glass_Shop", "frame": "MI_Paint_Frame",
    "iron": "MI_Paint_Iron", "rail": "MI_Railing", "fascia": "MI_Paint_ShopFascia", "awning": "MI_Paint_Awning_Red",
    "awning2": "MI_Paint_Awning_Green", "door": "MI_Paint_Door", "chimney": "MI_Stone_Chimney",
    "pot": "MI_Paint_Terracotta", "char": "MI_Paint_Charred", "skylight": "MI_Glass",
    "brick": "MI_KB_BricksA", "concrete": "MI_Paint_Concrete", "soot": "MI_Paint_Charred",
}


def clean(name):
    return re.sub(r"[^A-Za-z0-9]", "_", name).strip("_")


def args():
    a = sys.argv[1:]
    rebuild = "--rebuild" in a
    filt = ""
    if rebuild:
        i = a.index("--rebuild")
        filt = a[i + 1] if i + 1 < len(a) and not a[i + 1].startswith("--") else ""
    only = a[a.index("--only") + 1] if "--only" in a else ""
    return rebuild, filt, only


def master_material():
    g = Graph(MASTER)
    uv = g.uv(0)
    base = g.tex("BaseTex", pc.TEX + "/T_Web_PlazaStone", uv)
    g.out(MP.MP_BASE_COLOR, g.mul(g.mul(g.mask(base, r=True, g=True, b=True), g.vector("Tint", (1.0, 1.0, 1.0))),
                                   g.scalar("Brightness", 1.0)))
    nrm = g.tex("NormalTex", "/Engine/EngineMaterials/FlatNormal", uv, sampler=unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    g.out(MP.MP_NORMAL, g.flatten_normal(g.mask(nrm, r=True, g=True, b=True), g.scalar("Flatness", 0.0)))
    g.out(MP.MP_ROUGHNESS, g.scalar("Roughness", 0.75))
    g.out(MP.MP_METALLIC, g.scalar("Metallic", 0.0))
    g.out(MP.MP_SPECULAR, g.scalar("Specular", 0.4))
    return g.finish()


def import_texture(src, folder, name, normal):
    path = folder + "/" + name
    if not pc.EAL.does_asset_exist(path):
        task = unreal.AssetImportTask()
        task.filename = src
        task.destination_path = folder
        task.destination_name = name
        task.automated = True
        task.replace_existing = True
        task.save = False
        pc.ASSET_TOOLS.import_asset_tasks([task])
    tex = pc.load(path)
    tex.set_editor_property("srgb", not normal)
    tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP if normal
                            else unreal.TextureCompressionSettings.TC_DEFAULT)
    tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD_NORMAL_MAP if normal
                            else unreal.TextureGroup.TEXTUREGROUP_WORLD)
    pc.EAL.save_asset(path, only_if_is_dirty=False)
    return path


def import_fbx(src, name, reimport, vertex_colors):
    path = OUT + "/" + name
    if reimport and pc.EAL.does_asset_exist(path):
        pc.EAL.delete_asset(path)
    if not pc.EAL.does_asset_exist(path):
        task = unreal.AssetImportTask()
        task.filename = src
        task.destination_path = OUT
        task.destination_name = name
        task.automated = True
        task.replace_existing = True
        task.save = False
        opt = unreal.FbxImportUI()
        opt.import_mesh = True
        opt.import_as_skeletal = False
        opt.import_materials = False
        opt.import_textures = False
        opt.import_animations = False
        sm = opt.static_mesh_import_data
        sm.combine_meshes = True
        sm.import_uniform_scale = 1.0
        sm.generate_lightmap_u_vs = False
        sm.auto_generate_collision = False
        sm.vertex_color_import_option = (unreal.VertexColorImportOption.REPLACE if vertex_colors
                                         else unreal.VertexColorImportOption.IGNORE)
        task.options = opt
        pc.ASSET_TOOLS.import_asset_tasks([task])
    mesh = pc.load(path)
    if mesh is None:
        raise RuntimeError("import failed: " + src)
    return mesh


def finish_mesh(mesh, slot_to_mi):
    missing = []
    for i, slot in enumerate(mesh.get_editor_property("static_materials")):
        key = clean(str(slot.material_slot_name))
        mi = slot_to_mi.get(key)
        if mi is None:
            # FBX importers may suffix slot names (_001 / _SkinXX); match on the longest known prefix
            cands = [k for k in slot_to_mi if key.startswith(k) or k.startswith(key)]
            mi = slot_to_mi[max(cands, key=len)] if cands else None
        if mi is None:
            missing.append(str(slot.material_slot_name))
            continue
        mesh.set_material(i, pc.load(mi))
    sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    ns = unreal.MeshNaniteSettings()
    ns.enabled = True
    sub.set_nanite_settings(mesh, ns, True)
    pc.EAL.save_asset(mesh.get_path_name().split(".")[0], only_if_is_dirty=False)
    return missing


def info(mesh, **extra):
    b = mesh.get_bounding_box()
    d = {"asset": mesh.get_path_name().split(".")[0], "tris": mesh.get_num_triangles(0),
         "bounds_m": [[round(v / 100.0, 2) for v in (p.x, p.y, p.z)] for p in (b.min, b.max)],
         "nanite": bool(mesh.get_editor_property("nanite_settings").enabled),
         "materials": [slot.material_interface.get_name() if slot.material_interface else None
                       for slot in mesh.get_editor_property("static_materials")]}
    d.update(extra)
    return d


def main():
    rebuild, filt, only = args()
    t0 = time.time()
    report = {"schema": "Tread.M3.BuildingAssets.v1", "procedural": {}, "imported": {}, "missing_slots": {}}
    if rebuild or not pc.EAL.does_asset_exist(MASTER):
        master_material()
    # procedural buildings
    pdir = STAGING + "/m3_buildings"
    proc = json.load(open(pdir + "/m3_buildings.json", encoding="utf-8"))["buildings"]
    proc_mis = {k: pc.MAT + "/Instances/" + v for k, v in PROC_SLOTS.items()}
    for name, rec in proc.items():
        if only and only not in name:
            continue
        mesh = import_fbx(pdir + "/" + rec["fbx"], name, rebuild and filt in name, vertex_colors=True)
        miss = finish_mesh(mesh, proc_mis)
        if miss:
            report["missing_slots"][name] = miss
        report["procedural"][name] = info(mesh, source="blender_paris_buildings.py", blender_tris=rec["tris"])
        unreal.SystemLibrary.execute_console_command(None, "obj gc")
    # textured source models
    for s in SETS:
        man_path = STAGING + "/m3_models/%s/ue/manifest_ue.json" % s
        man = json.load(open(man_path, encoding="utf-8"))
        tex_dir = STAGING + "/m3_models/%s/ue" % s
        slot_to_mi = {}
        if only and only not in s and not any(only in ASSET_NAMES.get(s, "") or only in p for p in man["pieces"]):
            continue
        for key, e in man["slots"].items():
            mi_path = "%s/%s/MI_M3_%s_%s" % (MAT_OUT, s, s, key)
            tex = {}
            if e["base"]:
                tex["BaseTex"] = import_texture(tex_dir + "/" + e["base"], "%s/%s" % (TEX_OUT, s), "T_M3_%s_%s_D" % (s, key), False)
            if e["normal"]:
                tex["NormalTex"] = import_texture(tex_dir + "/" + e["normal"], "%s/%s" % (TEX_OUT, s), "T_M3_%s_%s_N" % (s, key), True)
            vec = {}
            if not e["base"]:
                c = e.get("color") or [0.6, 0.6, 0.6]
                vec["Tint"] = (c[0], c[1], c[2]) if not e["glass"] else (0.05, 0.07, 0.09)
                tex["BaseTex"] = "/Engine/EngineResources/WhiteSquareTexture"
            if rebuild or not pc.EAL.does_asset_exist(mi_path):
                get_or_create_mi(mi_path, pc.load(MASTER),
                                 scalars={"Roughness": e["roughness"], "Metallic": e["metallic"],
                                          "Specular": 0.9 if e["glass"] else 0.4},
                                 vectors=vec, textures=tex)
            slot_to_mi[key] = mi_path
        for piece, prec in man["pieces"].items():
            name = ASSET_NAMES.get(s) or "SM_M3_" + piece.replace("Oushi_SMoushi", "Oushi_")
            if only and only not in name and only not in s:
                continue
            mesh = import_fbx(STAGING + "/m3_models/%s/%s" % (s, prec["fbx"]), name, rebuild and filt in name, vertex_colors=False)
            miss = finish_mesh(mesh, slot_to_mi)
            if miss:
                report["missing_slots"][name] = miss
            report["imported"][name] = info(mesh, source_set=s, source_size_m=prec["size_m"], blender_tris=prec["tris"])
            unreal.SystemLibrary.execute_console_command(None, "obj gc")
    own = [p for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages() if "/M3/" in p.get_name()]
    if own:
        unreal.EditorLoadingAndSavingUtils.save_packages(own, True)
    report["elapsed_s"] = round(time.time() - t0, 1)
    old = json.load(open(REPORT, encoding="utf-8")) if os.path.exists(REPORT) and only else {}
    for k in ("procedural", "imported", "missing_slots"):
        merged = dict(old.get(k, {}))
        merged.update(report[k])
        report[k] = merged
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, sort_keys=True)
    pc.log("M3 assets: %d procedural, %d imported, missing=%s, %.1fs" % (len(report["procedural"]), len(report["imported"]),
                                                                          report["missing_slots"], report["elapsed_s"]))


main()
