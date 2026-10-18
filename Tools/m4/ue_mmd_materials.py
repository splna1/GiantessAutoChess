"""N2 (editor-side, Tools/ue_run.py): toon materials for the 12 imported MMD skeletal meshes.

mmd_tools shader links do not survive FBX, so blender_mmd_to_fbx.py records each slot's base texture
(Saved/Staging/mmd_fbx/<id>/SK_MMD_<id>.json + tex/). This step:
  * builds /Game/Tread/Characters/Materials/M_Char_ToonMasked once: a duplicate of the VRM toon master
    (M_Char_Toon) that is masked + two-sided with the base texture alpha as opacity mask (hair strands, lashes);
  * builds M_MMD_Hidden (masked, opacity 0) for MMD slots whose material alpha is ~0 (helper / effect layers);
  * imports every slot texture into <char folder>/Textures and assigns MI_Toon_<id>_<slot> to each slot.
Report: Saved/Reports/N2_MMD_Materials.json.

    python Tools/ue_run.py Tools/m4/ue_mmd_materials.py [--only char_1xx]
"""
import json
import os
import re
import sys

import unreal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "paris"))
import paris_common as pc  # noqa: E402
from matlib import Graph, get_or_create_mi  # noqa: E402

PROJECT = pc.PROJECT_DIR
SRC = PROJECT + "/Saved/Staging/mmd_fbx"
DEST = "/Game/Tread/Characters/MMD"
TOON = "/Game/Tread/Characters/Materials/M_Char_Toon"
TOON_MASKED = "/Game/Tread/Characters/Materials/M_Char_ToonMasked"
HIDDEN = "/Game/Tread/Characters/Materials/M_MMD_Hidden"
REPORT = PROJECT + "/Saved/Reports/N2_MMD_Materials.json"
MEL = unreal.MaterialEditingLibrary
EAL = unreal.EditorAssetLibrary


def safe(name):
    return re.sub(r"[^A-Za-z0-9_]", "_", name).strip("_") or "Slot"


def masked_master():
    if not EAL.does_asset_exist(TOON_MASKED):
        EAL.duplicate_asset(TOON, TOON_MASKED)
    m = EAL.load_asset(TOON_MASKED)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
    m.set_editor_property("two_sided", True)
    m.set_editor_property("opacity_mask_clip_value", 0.33)
    base = None
    for e in MEL.get_material_expressions(m) if hasattr(MEL, "get_material_expressions") else []:
        if isinstance(e, unreal.MaterialExpressionTextureSampleParameter2D) and str(e.get_editor_property("parameter_name")) == "BaseTex":
            base = e
    if base is None:
        raise RuntimeError("BaseTex sampler not found in %s" % TOON_MASKED)
    MEL.connect_material_property(base, "A", unreal.MaterialProperty.MP_OPACITY_MASK)
    MEL.recompile_material(m)
    EAL.save_asset(TOON_MASKED, only_if_is_dirty=False)
    return m


def hidden_master():
    if EAL.does_asset_exist(HIDDEN):
        return EAL.load_asset(HIDDEN)
    g = Graph(HIDDEN, blend=unreal.BlendMode.BLEND_MASKED)
    g.out(unreal.MaterialProperty.MP_OPACITY_MASK, g.const(0.0))
    return g.finish()


def import_texture(path, folder):
    name = "T_" + safe(os.path.splitext(os.path.basename(path))[0])
    asset = folder + "/" + name
    if not EAL.does_asset_exist(asset):
        task = unreal.AssetImportTask()
        task.filename = path
        task.destination_path = folder
        task.destination_name = name
        task.automated = True
        task.replace_existing = True
        task.save = True
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    return EAL.load_asset(asset)


def main():
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else ""
    toon = EAL.load_asset(TOON)
    masked = masked_master()
    hidden = hidden_master()
    sun = (0.35, -0.45, 0.82)
    report = []
    for cid in sorted(d for d in os.listdir(SRC) if d.startswith("char_") and (not only or d == only)):
        info = json.load(open("%s/%s/SK_MMD_%s.json" % (SRC, cid, cid), encoding="utf-8"))
        slots = {s["slot"]: s for s in info["slots"]}
        mesh_path = "%s/%s/SK_MMD_%s" % (DEST, cid, cid)
        mesh = EAL.load_asset(mesh_path)
        if mesh is None:
            report.append({"characterId": cid, "ok": False, "error": "mesh missing (run ue_import_mmd.py)"})
            continue
        mats = mesh.get_editor_property("materials")
        counts = {"toon": 0, "masked": 0, "hidden": 0, "untextured": 0}
        for i, slot in enumerate(mats):
            name = str(slot.get_editor_property("material_slot_name"))
            rec = slots.get(name) or slots.get(name.replace("_", " ")) or {}
            if rec.get("alpha", 1.0) < 0.05:
                slot.set_editor_property("material_interface", hidden)
                counts["hidden"] += 1
            else:
                tex = None
                if rec.get("texture"):
                    tex = import_texture("%s/%s/tex/%s" % (SRC, cid, rec["texture"]), "%s/%s/Textures" % (DEST, cid))
                # Cut out when the texture has real transparency (mmd_texture_alpha.py) or the material is translucent.
                cut = bool(rec.get("cutout")) or rec.get("alpha", 1.0) < 0.99
                parent = masked if cut else toon
                diffuse = rec.get("diffuse", [1, 1, 1])
                # Slot names are often CJK only; the slot index keeps every instance name unique.
                mi = get_or_create_mi("%s/%s/Materials/MI_Toon_%02d_%s" % (DEST, cid, i, safe(name)), parent,
                                      scalars={"ShadeShift": -0.1, "ShadeToony": 0.85, "RimPower": 3.0, "Brightness": 1.0},
                                      vectors={"ShadeColor": (0.78, 0.74, 0.80), "RimColor": (0.12, 0.12, 0.14), "SunDir": sun},
                                      textures={"BaseTex": tex} if tex else None, two_sided=True)
                if not tex:
                    counts["untextured"] += 1
                slot.set_editor_property("material_interface", mi)
                counts["masked" if cut else "toon"] += 1
            mats[i] = slot
        mesh.set_editor_property("materials", mats)
        EAL.save_loaded_asset(mesh, only_if_is_dirty=False)
        report.append(dict({"characterId": cid, "ok": True, "slots": len(mats)}, **counts))
        print("MMD_MAT", json.dumps(report[-1]))
        unreal.SystemLibrary.execute_console_command(None, "obj gc")
    # Persist every package this step touched (material instances, textures, meshes) and nothing else.
    own = [p for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
           if p.get_name().startswith(DEST) or p.get_name().startswith("/Game/Tread/Characters/Materials/M_")]
    if own:
        unreal.EditorLoadingAndSavingUtils.save_packages(own, True)
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump({"schema": "Tread.N2.MmdMaterials.v1", "models": report, "savedPackages": len(own)}, f, ensure_ascii=False, indent=1)


main()
