"""M4 (editor-side, Tools/ue_run.py): repair colour textures that UE's importer mistook for normal maps.

UE's NormalMapIdentification (Runtime/TextureUtilitiesCommon) sets TC_NORMALMAP + sRGB off on imported textures whose
pixels look like normals (large blue / purple areas).  The toon materials sample those as Color, B reads 0 and blue
hair turns yellow-green (see document/154, section "textures mistaken for normal maps").

Every material instance under /Game/Tread/Characters is scanned; the texture bound to its BaseTex parameter is a
colour texture, so a BaseTex that is TC_NORMALMAP or sRGB-off is reset to TC_DEFAULT / sRGB / TEXTUREGROUP_WORLD and
saved.  Safe to rerun (a clean project reports fixed=0).

    python Tools/ue_run.py Tools/m4/fix_color_textures.py [--check]      --check only reports

Report: Saved/Reports/M4_Color_Texture_Fix.json
"""
import json
import os
import sys

import unreal

PROJECT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
REPORT = os.path.join(PROJECT, "Saved", "Reports", "M4_Color_Texture_Fix.json")
ROOT = "/Game/Tread/Characters"
EAL = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary


def main(argv):
    check = "--check" in argv
    ar = unreal.AssetRegistryHelpers.get_asset_registry()
    flt = unreal.ARFilter(package_paths=[ROOT], recursive_paths=True,
                          class_paths=[unreal.TopLevelAssetPath("/Script/Engine", "MaterialInstanceConstant")])
    seen, bad, fixed = set(), [], []
    n_mi = 0
    for a in ar.get_assets(flt):
        n_mi += 1
        mi = a.get_asset()
        tex = MEL.get_material_instance_texture_parameter_value(mi, "BaseTex")
        if tex is None or not isinstance(tex, unreal.Texture2D):
            continue
        path = tex.get_path_name().split(".")[0]
        if path in seen:
            continue
        seen.add(path)
        cs = tex.get_editor_property("compression_settings")
        if cs == unreal.TextureCompressionSettings.TC_NORMALMAP or not tex.get_editor_property("srgb"):
            bad.append(path)
            if not check:
                tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_DEFAULT)
                tex.set_editor_property("srgb", True)
                tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
                if EAL.save_loaded_asset(tex):
                    fixed.append(path)
    doc = {"schema": "Tread.M4.ColorTextureFix.v1", "mode": "check" if check else "fix", "materialInstances": n_mi,
           "baseTextures": len(seen), "bad": bad, "fixed": fixed}
    with open(REPORT, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, indent=1)
    print("M4_COLOR_TEX mode=%s mi=%d baseTex=%d bad=%d fixed=%d" % (doc["mode"], n_mi, len(seen), len(bad), len(fixed)))
    for p in bad:
        print("M4_COLOR_TEX BAD", p)


main(sys.argv[1:])
