"""M4-B (editor-side, Tools/ue_run.py): import the staged portraits, voice lines, SFX and BGM.

Input: Saved/Staging/m4_content/manifest.json, written by Tools/m4/build_roster_map.py (run that first).

  portraits  /Game/Tread/UI/Portraits/T_Portrait_char_001..112  UI texture group, no mips, never streamed (the PNG
                                                                illustration: click-to-open detail image only)
  avatars    /Game/Tread/UI/Avatars/T_Avatar_char_001..112      same settings; chest-up model screenshots (shop / bench)
  voices     /Game/Tread/Audio/Voice/char_0xx/SW_Voice_*_{1,2}  SoundWave
  sfx        /Game/Tread/Audio/SFX/SW_SFX_*                     SoundWave
  bgm        /Game/Tread/Audio/BGM/SW_BGM_{battle,menu}         SoundWave, looping

    python Tools/ue_run.py Tools/m4/ue_import_content.py [--kind portraits|avatars|voices|sfx|bgm] [--force] [--limit N]

An asset that already exists is skipped unless --force; --limit stops after N new imports so a long run can be
split into several remote calls.  A missing staged file or a failed import stops the run (no silent placeholders)
and is listed in the report.  Saves per batch.  Report: Saved/Reports/M4_Content_Import_Report.json (merged).
"""
import json
import os
import sys

import unreal

PROJECT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
STAGE = os.path.join(PROJECT, "Saved", "Staging", "m4_content")
REPORT = os.path.join(PROJECT, "Saved", "Reports", "M4_Content_Import_Report.json")
EAL = unreal.EditorAssetLibrary
KINDS = ("portraits", "avatars", "voices", "sfx", "bgm")


def import_file(staged, asset):
    folder, name = asset.rsplit("/", 1)
    task = unreal.AssetImportTask()
    task.filename = staged
    task.destination_path = folder
    task.destination_name = name
    task.replace_existing = True
    task.automated = True
    task.save = False
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    return EAL.load_asset(asset)


def configure(kind, obj, entry):
    if kind in ("portraits", "avatars"):
        obj.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_UI)
        obj.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
        obj.set_editor_property("never_stream", True)
        # BC1: 512x768 at ~200 KB each; the roster panel can show 32 at once without a 1.5 MB-per-portrait cost.
        obj.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_DEFAULT)
        obj.set_editor_property("srgb", True)
    elif kind == "bgm":
        obj.set_editor_property("looping", bool(entry.get("loop")))


def main(argv):
    kinds = [argv[argv.index("--kind") + 1]] if "--kind" in argv else list(KINDS)
    force = "--force" in argv
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else 0
    manifest = json.load(open(os.path.join(STAGE, "manifest.json"), encoding="utf-8"))
    report = json.load(open(REPORT, encoding="utf-8")) if os.path.exists(REPORT) else {}
    done = report.get("assets", {})
    failed = []
    imported = 0
    for kind in kinds:
        for entry in manifest[kind]:
            asset = entry["asset"]
            if not force and EAL.does_asset_exist(asset):
                done[asset] = {"kind": kind, "ok": True}
                continue
            staged = os.path.join(STAGE, entry["staged"])
            if not os.path.isfile(staged):
                failed.append({"asset": asset, "error": "staged file missing: " + entry["staged"]})
                break
            obj = import_file(staged, asset)
            if obj is None:
                failed.append({"asset": asset, "error": "import produced no asset"})
                break
            configure(kind, obj, entry)
            done[asset] = {"kind": kind, "ok": True, "class": obj.get_class().get_name(), "source": entry["source"]}
            imported += 1
            if limit and imported >= limit:
                break
        if failed or (limit and imported >= limit):
            break
    dirty = [p for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
             if p.get_name().startswith(("/Game/Tread/UI/Portraits", "/Game/Tread/UI/Avatars", "/Game/Tread/Audio"))]
    if dirty:
        unreal.EditorLoadingAndSavingUtils.save_packages(dirty, True)
    unreal.SystemLibrary.execute_console_command(None, "Tread.FlushThumbnailScenes")
    expected = {e["asset"]: kind for kind in KINDS for e in manifest[kind]}
    counts = {kind: sum(1 for a, k in expected.items() if k == kind and done.get(a, {}).get("ok")) for kind in KINDS}
    totals = {kind: len(manifest[kind]) for kind in KINDS}
    doc = {"schema": "Tread.M4.ContentImport.v1", "ok": not failed and counts == totals, "counts": counts,
           "expected": totals, "failed": failed, "assets": dict(sorted(done.items()))}
    with open(REPORT, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, ensure_ascii=False, indent=1)
    print("M4_CONTENT imported=%d saved=%d counts=%s expected=%s failed=%s ok=%s"
          % (imported, len(dirty), counts, totals, len(failed), doc["ok"]))
    for f in failed:
        print("M4_CONTENT FAIL %s %s" % (f["asset"], f["error"]))


main(sys.argv[1:])
