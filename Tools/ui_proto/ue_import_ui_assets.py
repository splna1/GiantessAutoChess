"""Doc 157 task A (editor-side, run via Tools/ue_run.py): import the UI style textures and font faces.

    python Tools/ue_run.py Tools/ui_proto/ue_import_ui_assets.py

* 16 PNGs  Saved/UIPrototype/textures -> /Game/Tread/UI/Style   (UTexture2D, UI group, no mips, never streamed,
  TC_DEFAULT + sRGB forced so colour art is never misdetected as a normal map; tiling textures use TA_WRAP).
* 9 TTFs   Saved/UIPrototype/fonts    -> /Game/Tread/UI/Fonts    (UFontFace via UFontFileImportFactory; no UFont).
* OFL_*.txt Saved/UIPrototype/fonts_src -> Content/Tread/UI/Fonts/Licenses (plain file copies, not assets).
* Report   Saved/Reports/UI_Style_Import.json

Re-runnable: assets are re-imported in place (replace_existing), nothing is ever deleted.
Editor Python rules: ASCII output only, no sleeps, no map switching.
"""
import glob
import json
import os
import shutil
import sys
import time
import traceback

import unreal

PROJECT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
TEX_SRC = os.path.join(PROJECT, "Saved", "UIPrototype", "textures")
FONT_SRC = os.path.join(PROJECT, "Saved", "UIPrototype", "fonts")
LICENSE_SRC = os.path.join(PROJECT, "Saved", "UIPrototype", "fonts_src")
LICENSE_DST = os.path.join(PROJECT, "Content", "Tread", "UI", "Fonts", "Licenses")
REPORT_PATH = os.path.join(PROJECT, "Saved", "Reports", "UI_Style_Import.json")

STYLE_DIR = "/Game/Tread/UI/Style"
FONT_DIR = "/Game/Tread/UI/Fonts"

EAL = unreal.EditorAssetLibrary

TEXTURES = [
    "T_UI_Paper", "T_UI_Grain", "T_UI_Vignette", "T_UI_Logo", "T_UI_Disc", "T_UI_DiscShade",
    "T_UI_Stamp_Approved", "T_UI_Stamp_Cleared", "T_UI_Stamp_Ready", "T_UI_Stamp_Sortie",
    "T_UI_InkSplat", "T_UI_Giantess", "T_UI_GiantessInDisc", "T_UI_Hatch", "T_UI_Halftone", "T_UI_Scanlines",
]
TILED = {"T_UI_Grain", "T_UI_Hatch", "T_UI_Halftone", "T_UI_Scanlines"}

# ttf file stem -> FontFace asset name (doc 157 section 2.2)
FONTS = [
    ("TreadSans-Black", "FF_TreadSans_Black"),
    ("TreadSans-Bold", "FF_TreadSans_Bold"),
    ("TreadSans-Medium", "FF_TreadSans_Medium"),
    ("TreadSerif-Black", "FF_TreadSerif_Black"),
    ("TreadCond-SemiBold", "FF_TreadCond_SemiBold"),
    ("TreadMono-Medium", "FF_TreadMono_Medium"),
    ("TreadMono-ExtraBold", "FF_TreadMono_ExtraBold"),
    ("TreadStencil-Black", "FF_TreadStencil_Black"),
    ("TreadRusso-Regular", "FF_TreadRusso_Regular"),
]


def enum_name(value):
    """Short ASCII name of a unreal enum value."""
    return getattr(value, "name", str(value))


def uasset_path(asset_dir, name):
    """Disk path of /Game/<rel>/<name>.uasset."""
    rel = asset_dir[len("/Game/"):]
    return os.path.join(PROJECT, "Content", rel.replace("/", os.sep), name + ".uasset")


def run_import(filename, dest_dir, dest_name, factory=None):
    """Import one file in place; returns (task, error_text or None)."""
    task = unreal.AssetImportTask()
    task.filename = filename
    task.destination_path = dest_dir
    task.destination_name = dest_name
    task.replace_existing = True
    task.replace_existing_settings = True
    task.automated = True
    task.save = True
    if factory is not None:
        task.factory = factory
    try:
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    except Exception:
        return task, traceback.format_exc()
    return task, None


def task_result_paths(task):
    try:
        return [str(p) for p in task.get_editor_property("imported_object_paths")]
    except Exception:
        return []


def load_manifest():
    path = os.path.join(TEX_SRC, "textures_manifest.json")
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def import_texture(name, manifest):
    entry = {"name": name, "path": "%s/%s" % (STYLE_DIR, name), "ok": False, "errors": []}
    src = os.path.join(TEX_SRC, name + ".png")
    entry["source"] = src
    if not os.path.isfile(src):
        entry["errors"].append("source png missing")
        return entry
    task, err = run_import(src, STYLE_DIR, name)
    if err:
        entry["errors"].append("import exception: " + err.replace("\n", " | "))
        return entry
    entry["imported_object_paths"] = task_result_paths(task)

    tex = EAL.load_asset(entry["path"])
    if tex is None:
        entry["errors"].append("asset not loadable after import")
        return entry
    entry["class"] = tex.get_class().get_name()
    if entry["class"] != "Texture2D":
        entry["errors"].append("unexpected class " + entry["class"])
        return entry

    wrap = name in TILED
    addr = unreal.TextureAddress.TA_WRAP if wrap else unreal.TextureAddress.TA_CLAMP
    wanted = [
        ("compression_settings", unreal.TextureCompressionSettings.TC_DEFAULT),
        ("srgb", True),
        ("lod_group", unreal.TextureGroup.TEXTUREGROUP_UI),
        ("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS),
        ("never_stream", True),
        ("address_x", addr),
        ("address_y", addr),
    ]
    for prop, value in wanted:
        try:
            tex.set_editor_property(prop, value)
        except Exception as exc:
            entry["errors"].append("set %s failed: %s" % (prop, exc))
    if not EAL.save_asset(entry["path"], only_if_is_dirty=False):
        entry["errors"].append("save_asset returned False")

    # Read everything back from a fresh handle on the asset
    tex = EAL.load_asset(entry["path"])
    entry["size"] = [int(tex.blueprint_get_size_x()), int(tex.blueprint_get_size_y())]
    settings = {}
    for prop, value in wanted:
        got = tex.get_editor_property(prop)
        settings[prop] = enum_name(got) if hasattr(got, "name") else got
    entry["settings"] = settings
    entry["expected"] = {p: (enum_name(v) if hasattr(v, "name") else v) for p, v in wanted}
    settings_ok = all(settings[p] == entry["expected"][p] for p, _ in wanted)
    if not settings_ok:
        entry["errors"].append("read-back mismatch")

    m = manifest.get(name)
    if m and "size" in m:
        entry["manifest_size"] = list(m["size"])
        if entry["manifest_size"] != entry["size"]:
            entry["errors"].append("size differs from manifest")
    disk = uasset_path(STYLE_DIR, name)
    entry["uasset_exists"] = os.path.isfile(disk)
    entry["uasset_bytes"] = os.path.getsize(disk) if entry["uasset_exists"] else 0
    if not entry["uasset_exists"]:
        entry["errors"].append("uasset not on disk")
    entry["ok"] = not entry["errors"]
    return entry


def import_font(stem, asset_name):
    entry = {"name": asset_name, "path": "%s/%s" % (FONT_DIR, asset_name), "ok": False, "errors": []}
    src = os.path.join(FONT_SRC, stem + ".ttf")
    entry["source"] = src
    if not os.path.isfile(src):
        entry["errors"].append("source ttf missing")
        return entry
    entry["source_bytes"] = os.path.getsize(src)
    factory = unreal.FontFileImportFactory()
    t0 = time.time()
    task, err = run_import(src, FONT_DIR, asset_name, factory)
    entry["import_seconds"] = round(time.time() - t0, 1)
    if err:
        entry["errors"].append("import exception: " + err.replace("\n", " | "))
        return entry
    entry["imported_object_paths"] = task_result_paths(task)

    asset = EAL.load_asset(entry["path"])
    if asset is None:
        entry["errors"].append("asset not loadable after import")
        return entry
    entry["class"] = asset.get_class().get_name()
    if entry["class"] != "FontFace":
        entry["errors"].append("unexpected class " + entry["class"])
        return entry
    for prop in ("loading_policy", "hinting", "layout_method"):
        try:
            got = asset.get_editor_property(prop)
            entry[prop] = enum_name(got)
        except Exception as exc:
            entry[prop] = None
            entry["errors"].append("read %s failed: %s" % (prop, exc))
    try:
        entry["source_filename_prop"] = os.path.basename(str(asset.get_editor_property("source_filename")))
    except Exception:
        entry["source_filename_prop"] = None
    if not EAL.save_asset(entry["path"], only_if_is_dirty=False):
        entry["errors"].append("save_asset returned False")
    disk = uasset_path(FONT_DIR, asset_name)
    entry["uasset_exists"] = os.path.isfile(disk)
    entry["uasset_bytes"] = os.path.getsize(disk) if entry["uasset_exists"] else 0
    if not entry["uasset_exists"]:
        entry["errors"].append("uasset not on disk")
    elif entry["uasset_bytes"] < entry["source_bytes"] // 2:
        entry["errors"].append("uasset much smaller than ttf (font data not embedded?)")
    entry["ok"] = not entry["errors"]
    return entry


def stray_font_assets():
    """Any asset in the Fonts dir that is not one of the 9 expected FontFaces (e.g. a stray UFont)."""
    expected = set(n for _, n in FONTS)
    stray = []
    for path in EAL.list_assets(FONT_DIR, recursive=False, include_folder=False):
        base = str(path).split(".")[0].rsplit("/", 1)[-1]
        if base not in expected:
            stray.append(str(path))
    return stray


def copy_licenses():
    os.makedirs(LICENSE_DST, exist_ok=True)
    copied = []
    for src in sorted(glob.glob(os.path.join(LICENSE_SRC, "OFL_*.txt"))):
        dst = os.path.join(LICENSE_DST, os.path.basename(src))
        shutil.copyfile(src, dst)
        copied.append({"file": os.path.basename(src), "bytes": os.path.getsize(dst)})
    return copied


def main():
    t_start = time.time()
    report = {"ok": False, "textures": [], "fonts": [], "licenses": [], "notes": []}

    EAL.make_directory(STYLE_DIR)
    EAL.make_directory(FONT_DIR)
    manifest = load_manifest()

    for name in TEXTURES:
        try:
            entry = import_texture(name, manifest)
        except Exception:
            entry = {"name": name, "ok": False, "errors": ["exception: " + traceback.format_exc().replace("\n", " | ")]}
        report["textures"].append(entry)
        print("TEX  %-22s ok=%s size=%s %s" % (name, entry.get("ok"), entry.get("size"), "; ".join(entry.get("errors", []))))

    for stem, asset_name in FONTS:
        try:
            entry = import_font(stem, asset_name)
        except Exception:
            entry = {"name": asset_name, "ok": False, "errors": ["exception: " + traceback.format_exc().replace("\n", " | ")]}
        report["fonts"].append(entry)
        print("FONT %-24s ok=%s class=%s policy=%s bytes=%s %s" % (
            asset_name, entry.get("ok"), entry.get("class"), entry.get("loading_policy"),
            entry.get("uasset_bytes"), "; ".join(entry.get("errors", []))))

    stray = stray_font_assets()
    report["stray_font_dir_assets"] = stray
    if stray:
        report["notes"].append("extra assets in Fonts dir (not deleted): " + ", ".join(stray))
        print("NOTE stray assets in Fonts dir: " + ", ".join(stray))

    try:
        report["licenses"] = copy_licenses()
        print("LICENSES copied: %d" % len(report["licenses"]))
    except Exception:
        report["notes"].append("license copy failed: " + traceback.format_exc().replace("\n", " | "))

    report["ok"] = (
        len(report["textures"]) == len(TEXTURES) and all(t.get("ok") for t in report["textures"])
        and len(report["fonts"]) == len(FONTS) and all(f.get("ok") for f in report["fonts"])
        and len(report["licenses"]) > 0
    )
    report["elapsed_seconds"] = round(time.time() - t_start, 1)

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=True)
    print("REPORT %s ok=%s elapsed=%.1fs" % (REPORT_PATH, report["ok"], report["elapsed_seconds"]))
    if not report["ok"]:
        sys.exit(1)


main()
