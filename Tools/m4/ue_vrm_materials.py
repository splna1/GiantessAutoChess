"""M4 (editor-side, Tools/ue_run.py): toon materials for the imported roster VRMs.

blender_vrm_to_fbx.py records every slot's base texture (written to Saved/Staging/vrm_fbx/<id>/tex, solid-colour
textures included) and its VRM material properties in the sidecar.  Per slot this step assigns:
  * M_MMD_Hidden (masked, opacity 0) when the base colour alpha is ~0: expression overlays and "Hide" variants;
  * every BaseTex is forced to TC_DEFAULT / sRGB (force_color_texture) and a TC_NORMALMAP / sRGB-off BaseTex fails the
    character (UE auto-detects blue textures as normal maps; Tools/m4/fix_color_textures.py repairs existing ones);
  * otherwise MI_Toon_<NN>_<slot> under M_Char_Toon, or under M_Char_ToonMasked for MASK / BLEND slots (lashes,
    hair cards), with the MToon shade parameters converted to M_Char_Toon's convention.

M_Char_Toon (Tools/paris/08_vrm.py) lights with smoothstep(Shift, Shift + 1 - Toony, N.L), the VRM 0.x reading that
the M1 hero's instances were built from.  The VRM Add-on hands every material over in VRM 1.0 terms,
linearstep(-1 + toony, 1 - toony, N.L + shift), which is the same band for Shift = -1 + toony - shift and
Toony = 2 toony - 1 (VRM 0.x shift 0 / toony 0.9 arrives as -0.05 / 0.95 and converts back exactly).  Colours
arrive linear; the hero's instances carry the VRM 0.x sRGB values, so they are converted to match.  SunDir is the
hero's, so every VRM unit is lit like the hero standing next to it.

UE renames slots on import (every character outside letters, digits, '-' and CJK becomes '_'); slots are matched
to the sidecar through the same normalisation.

    python Tools/ue_run.py Tools/m4/ue_vrm_materials.py [--only char_002,char_003] [--limit N] [--force]

Without --only / --force a run skips characters the report already has as ok.

Report: Saved/Reports/M4_VRM_Materials.json (merged per character).
"""
import json
import os
import re
import sys

import unreal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "paris"))
import paris_common as pc  # noqa: E402
from matlib import get_or_create_mi  # noqa: E402

PROJECT = pc.PROJECT_DIR
SRC = PROJECT + "/Saved/Staging/vrm_fbx"
DEST = "/Game/Tread/Characters/VRM"
TOON = "/Game/Tread/Characters/Materials/M_Char_Toon"
TOON_MASKED = "/Game/Tread/Characters/Materials/M_Char_ToonMasked"  # built by ue_mmd_materials.py
HIDDEN = "/Game/Tread/Characters/Materials/M_MMD_Hidden"  # built by ue_mmd_materials.py
HERO_MI = "/Game/Tread/Characters/Clukay416/Materials/MI_Toon_0_Face"
REPORT = PROJECT + "/Saved/Reports/M4_VRM_Materials.json"
MEL = unreal.MaterialEditingLibrary
EAL = unreal.EditorAssetLibrary


def safe(name):
    return re.sub(r"[^A-Za-z0-9_]", "_", name).strip("_") or "Slot"


def slot_key(name):
    return re.sub(r"[^0-9A-Za-z\-\u0080-￿]", "_", name)


def srgb(c):
    return [12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055 for v in c[:3]]


def force_color_texture(tex):
    """UE's importer guesses "normal map" for blue / purple colour textures (NormalMapIdentification.cpp) and sets
    TC_NORMALMAP + sRGB off, which reads the B channel as 0 (blue hair turns yellow-green).  Every texture this
    script imports is a base-colour texture, so the colour settings are forced.  Returns True when anything changed."""
    changed = False
    for prop, value in (("compression_settings", unreal.TextureCompressionSettings.TC_DEFAULT), ("srgb", True),
                        ("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)):
        if tex.get_editor_property(prop) != value:
            tex.set_editor_property(prop, value)
            changed = True
    return changed


def bad_color_texture(tex):
    return (tex.get_editor_property("compression_settings") == unreal.TextureCompressionSettings.TC_NORMALMAP
            or not tex.get_editor_property("srgb"))


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
    tex = EAL.load_asset(asset)
    if tex is not None and force_color_texture(tex):  # new imports and already existing textures alike
        EAL.save_loaded_asset(tex)
    return tex


def one(cid, toon, masked, hidden, sun):
    info = json.load(open("%s/%s/SK_VRM_%s.json" % (SRC, cid, cid), encoding="utf-8"))
    slots = {slot_key(s["slot"]): s for s in info["slots"]}
    mesh = EAL.load_asset("%s/%s/SK_VRM_%s" % (DEST, cid, cid))
    if mesh is None:
        return {"characterId": cid, "ok": False, "error": "mesh missing (run ue_import_vrm.py)"}
    mats = mesh.get_editor_property("materials")
    counts = {"toon": 0, "masked": 0, "hidden": 0, "untextured": 0, "solid": 0, "unmatched": [], "badTex": []}
    for i, slot in enumerate(mats):
        name = str(slot.get_editor_property("material_slot_name"))
        rec = slots.get(slot_key(name))
        if rec is None:
            counts["unmatched"].append(name)
            rec = {}
        if rec.get("baseColor", [1, 1, 1, 1])[3] < 0.05:
            slot.set_editor_property("material_interface", hidden)
            counts["hidden"] += 1
        else:
            tex = None
            if rec.get("texture"):
                tex = import_texture("%s/%s/tex/%s" % (SRC, cid, rec["texture"]), "%s/%s/Textures" % (DEST, cid))
                if tex is not None and bad_color_texture(tex):  # acceptance: a BaseTex must be a colour texture
                    counts["badTex"].append(tex.get_name())
            cut = rec.get("alphaMode", "OPAQUE") != "OPAQUE"
            toony, shift = rec.get("shadingToony", 0.95), rec.get("shadingShift", -0.05)
            mi = get_or_create_mi("%s/%s/Materials/MI_Toon_%02d_%s" % (DEST, cid, i, safe(name)), masked if cut else toon,
                                  scalars={"ShadeShift": -1.0 + toony - shift, "ShadeToony": 2.0 * toony - 1.0,
                                           "RimPower": rec.get("rimPower", 1.0), "Brightness": 1.0},
                                  vectors={"ShadeColor": tuple(srgb(rec.get("shadeColor", [0.6, 0.6, 0.6]))),
                                           "RimColor": tuple(srgb(rec.get("rimColor", [0, 0, 0]))), "SunDir": sun},
                                  textures={"BaseTex": tex} if tex else None,
                                  two_sided=True if rec.get("doubleSided") else None)
            slot.set_editor_property("material_interface", mi)
            counts["masked" if cut else "toon"] += 1
            counts["untextured"] += 0 if tex else 1
            counts["solid"] += 1 if rec.get("solidColor") else 0
        mats[i] = slot
    mesh.set_editor_property("materials", mats)
    EAL.save_loaded_asset(mesh, only_if_is_dirty=False)
    return dict({"characterId": cid, "ok": not counts["unmatched"] and not counts["badTex"], "slots": len(mats)}, **counts)


def main():
    only = set(sys.argv[sys.argv.index("--only") + 1].split(",")) if "--only" in sys.argv else set()
    toon, masked, hidden = (EAL.load_asset(p) for p in (TOON, TOON_MASKED, HIDDEN))
    if not (toon and masked and hidden):
        raise RuntimeError("toon masters missing; run Tools/paris/08_vrm.py and Tools/m4/ue_mmd_materials.py first")
    hero_sun = MEL.get_material_instance_vector_parameter_value(EAL.load_asset(HERO_MI), "SunDir")
    sun = (hero_sun.r, hero_sun.g, hero_sun.b)
    old = json.load(open(REPORT, encoding="utf-8")) if os.path.exists(REPORT) else {"models": []}
    merged = {r["characterId"]: r for r in old.get("models", [])}
    # A long batch can take the editor's GPU memory down (2026-10-12 import crash), so a run does at most --limit
    # characters and skips the ones the report already has as ok, unless they are named in --only or --force.
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 0
    force = "--force" in sys.argv
    ids = sorted(d for d in os.listdir(SRC) if d.startswith("char_") and (not only or d in only)
                 and EAL.does_asset_exist("%s/%s/SK_VRM_%s" % (DEST, d, d)))
    todo = [c for c in ids if force or only or not merged.get(c, {}).get("ok")]
    saved = 0
    for cid in todo[:limit] if limit else todo:
        merged[cid] = one(cid, toon, masked, hidden, sun)
        print("VRM_MAT", json.dumps(merged[cid], ensure_ascii=True))
        own = [p for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
               if p.get_name().startswith(DEST)]
        if own:
            unreal.EditorLoadingAndSavingUtils.save_packages(own, True)
            saved += len(own)
        unreal.SystemLibrary.execute_console_command(None, "Tread.FlushThumbnailScenes")  # TreadEditorThumbnails.cpp
        unreal.SystemLibrary.execute_console_command(None, "obj gc")
        models = [merged[k] for k in sorted(merged)]
        with open(REPORT, "w", encoding="utf-8") as f:
            json.dump({"schema": "Tread.M4.VrmMaterials.v1", "ok": all(m["ok"] for m in models), "count": len(models),
                       "models": models}, f, ensure_ascii=False, indent=1)
    models = [merged[k] for k in sorted(merged)]
    remaining = len([c for c in ids if not merged.get(c, {}).get("ok")])
    print("M4_VRM_MATERIALS", "PASS" if all(m["ok"] for m in models) else "PARTIAL", len(models),
          "saved=%d remaining=%d" % (saved, remaining))


main()
