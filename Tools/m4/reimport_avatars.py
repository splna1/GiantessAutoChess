"""M4 (editor-side, Tools/ue_run.py): re-import chosen avatars from Saved/Staging/m4_content/avatars.

    python Tools/ue_run.py Tools/m4/reimport_avatars.py --ids char_025,char_026

Same texture settings as ue_import_content.py (UI group, no mips, never streamed, TC_DEFAULT, sRGB), but only the named
ids are touched (ue_import_content.py --force would redo all 112).  Saves the packages it dirtied.
"""
import os
import sys

import unreal

PROJECT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
STAGE = os.path.join(PROJECT, "Saved", "Staging", "m4_content", "avatars")
FOLDER = "/Game/Tread/UI/Avatars"
EAL = unreal.EditorAssetLibrary


def main(argv):
    ids = [i for i in argv[argv.index("--ids") + 1].split(",") if i]
    for cid in ids:
        name = "T_Avatar_" + cid
        task = unreal.AssetImportTask()
        task.filename = os.path.join(STAGE, name + ".png")
        task.destination_path = FOLDER
        task.destination_name = name
        task.replace_existing = True
        task.automated = True
        task.save = False
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        tex = EAL.load_asset(FOLDER + "/" + name)
        tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_UI)
        tex.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
        tex.set_editor_property("never_stream", True)
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_DEFAULT)
        tex.set_editor_property("srgb", True)
        EAL.save_loaded_asset(tex)
        print("REIMPORT %s %dx%d" % (name, tex.blueprint_get_size_x(), tex.blueprint_get_size_y()))
    unreal.SystemLibrary.execute_console_command(None, "Tread.FlushThumbnailScenes")


main(sys.argv[1:])
