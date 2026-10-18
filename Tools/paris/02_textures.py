"""Step 02: import city textures into /Game/Tread/City/Paris/Textures (re-runnable, replaces in place).

Sources (read-only): Unity web_backup material photos, KB3D warzone textures shipped with the ruin model,
plus procedural textures produced by gen_textures.py in Saved/Staging/Textures, plus (B2) the base-colour atlas
embedded in the Notre-Dame .glb (staged and extracted with gltf_io, capped at 2048 for the 8 GB budget).

Usage (through Tools/ue_run.py):
    02_textures.py [--only T_NotreDame_D ...]
"""
import os
import sys

import unreal
import gltf_io
import paris_common as pc

WEB = pc.SRC["web_mats"]
KB = pc.SRC["ruin_tex"]
GEN = pc.STAGING_DIR + "/Textures"

# (source file, asset name, kind) kind: color | normal | linear
TEXTURES = [
    (WEB + "/battle_damaged_concrete.png", "T_Web_DamagedConcrete", "color"),
    (WEB + "/concrete_road_surface.png", "T_Web_Asphalt", "color"),
    (WEB + "/damaged_plaster_wall.png", "T_Web_LimestoneBlocks", "color"),
    (WEB + "/paris_plaza_stone.png", "T_Web_PlazaStone", "color"),
    (WEB + "/scorched_cobblestone_sidewalk.png", "T_Web_ScorchedCobble", "color"),
    (WEB + "/seine_river_water.png", "T_Web_SeineWater", "color"),
    (WEB + "/seine_riverbank_stone.png", "T_Web_QuayStone", "color"),
    (WEB + "/urban_grass_ground.png", "T_Web_Grass", "color"),
    (WEB + "/wet_cobblestone_street.png", "T_Web_Cobble", "color"),
    (KB + "/KB3D_WZT_plasterA_diffuse.jpg", "T_KB_PlasterA_D", "color"),
    (KB + "/KB3D_WZT_plasterA_normal.jpg", "T_KB_PlasterA_N", "normal"),
    (KB + "/KB3D_WZT_ConcreteA_diffuse.jpg", "T_KB_ConcreteA_D", "color"),
    (KB + "/KB3D_WZT_ConcreteA_normal.jpg", "T_KB_ConcreteA_N", "normal"),
    (KB + "/KB3D_WZT_ConcreteB_diffuse.jpg", "T_KB_ConcreteB_D", "color"),
    (KB + "/KB3D_WZT_rubbleA_diffuse.jpg", "T_KB_RubbleA_D", "color"),
    (KB + "/KB3D_WZT_rubbleA_normal.jpg", "T_KB_RubbleA_N", "normal"),
    (KB + "/KB3D_WZT_damageA_diffuse.jpg", "T_KB_DamageA_D", "color"),
    (KB + "/KB3D_WZT_damageA_normal.jpg", "T_KB_DamageA_N", "normal"),
    (KB + "/KB3D_WZT_MetalRustA_diffuse.jpg", "T_KB_MetalRustA_D", "color"),
    # B6: remaining base colours of the BldgLG_J ruin scan (09_ruins.py MI_KB_* instances, capped at 2048)
    (KB + "/KB3D_WZT_assetsA_diffuse.jpg", "T_KB_AssetsA_D", "color"),
    (KB + "/KB3D_WZT_bricksA_diffuse.jpg", "T_KB_BricksA_D", "color"),
    (KB + "/KB3D_WZT_bricksAdamage_diffuse.jpg", "T_KB_BricksADamage_D", "color"),
    (KB + "/KB3D_WZT_floorA_diffuse.jpg", "T_KB_FloorA_D", "color"),
    (KB + "/KB3D_WZT_floorB_diffuse.jpg", "T_KB_FloorB_D", "color"),
    (KB + "/KB3D_WZT_MetalFrameA_diffuse.jpg", "T_KB_MetalFrameA_D", "color"),
    (KB + "/KB3D_WZT_plasterB_diffuse.jpg", "T_KB_PlasterB_D", "color"),
    (KB + "/KB3D_WZT_plasterC_diffuse.jpg", "T_KB_PlasterC_D", "color"),
    (KB + "/KB3D_WZT_woodA_diffuse.jpg", "T_KB_WoodA_D", "color"),
    (GEN + "/T_Water_N.png", "T_Water_N", "normal"),
    (GEN + "/T_SmokePuff.png", "T_SmokePuff", "color"),
    (GEN + "/T_FlameTongue.png", "T_FlameTongue", "color"),
    (GEN + "/T_Scorch.png", "T_Scorch", "color"),
    (GEN + "/T_StoneGrunge.png", "T_StoneGrunge", "linear"),
    (pc.STAGING_DIR + "/notre_dame/T_NotreDame_D.jpg", "T_NotreDame_D", "color"),
]
MAX_SIZE = {"T_NotreDame_D": 2048}


def prepare_notre_dame():
    """Stage the read-only Notre-Dame .glb and dump its embedded base-colour JPEG next to it."""
    out = pc.STAGING_DIR + "/notre_dame/T_NotreDame_D.jpg"
    if os.path.exists(out):
        return out
    staged = pc.stage(pc.SRC["notre_dame"], "notre_dame")
    mime = gltf_io.Gltf(staged).extract_image(out, 0)
    pc.log("extracted", mime, "->", out)
    return out


def import_textures(only=()):
    pc.ensure_dir(pc.TEX)
    textures = [t for t in TEXTURES if not only or t[1] in only]
    if any(t[1] == "T_NotreDame_D" for t in textures):
        prepare_notre_dame()
    tasks = []
    for src, name, _ in textures:
        if not os.path.exists(src):
            raise RuntimeError("missing source texture " + src)
        t = unreal.AssetImportTask()
        t.filename = pc.stage(src, "ruins/textures") if name.startswith("T_KB_") else src
        t.destination_path = pc.TEX
        t.destination_name = name
        t.automated = True
        t.replace_existing = True
        t.save = False
        tasks.append(t)
    pc.ASSET_TOOLS.import_asset_tasks(tasks)
    done = []
    for src, name, kind in textures:
        path = pc.TEX + "/" + name
        tex = pc.EAL.load_asset(path)
        if tex is None:
            pc.log("FAILED", name)
            continue
        if kind == "normal":
            tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
            tex.set_editor_property("srgb", False)
        elif kind == "linear":
            tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
            tex.set_editor_property("srgb", False)
        if "/KB3D_" in src or name in MAX_SIZE:
            tex.set_editor_property("max_texture_size", MAX_SIZE.get(name, 2048))
        pc.EAL.save_asset(path, only_if_is_dirty=False)
        done.append(name)
    pc.log("imported %d/%d textures" % (len(done), len(textures)))
    return done


import_textures([sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--only"])
