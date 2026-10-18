"""Probe / fix collision on the pre-cut chunk meshes (plan 126, document/162).

Chunk meshes were built with collision disabled; the destruction manager now spawns them as rigid bodies, so they need
a body setup. This tries the static-mesh collision flags in order, saves what stuck and writes a small report (prints
from a commandlet do not always reach the log, so the JSON is the source of truth).

    UnrealEditor-Cmd.exe Tread.uproject -run=pythonscript -script="E:/AI/Tread/Tread/Tools/destruction/chunk_collision.py" -nullrhi -unattended -nosplash
"""
import json
import os

import unreal

PROJECT = r"E:\AI\Tread\Tread"
MANIFEST = os.path.join(PROJECT, "Content", "Tread", "Destruction", "DestructionChunks.json")
REPORT = os.path.join(PROJECT, "Saved", "Reports", "Chunk_Collision.json")

CANDIDATES = ("bEnableCollision", "bUseComplexAsSimpleCollision", "bHasNavigationData")


def describe(mesh, property_names):
    found = {}
    for name in property_names:
        try:
            found[name] = repr(mesh.get_editor_property(name))
        except Exception:  # noqa: BLE001
            pass
    try:
        found["body_setup"] = "yes" if mesh.get_body_setup() else "no"
    except Exception:  # noqa: BLE001
        found["body_setup"] = "n/a"
    return found


def main():
    with open(MANIFEST, encoding="utf-8") as handle:
        manifest = json.load(handle)
    paths = [chunk["asset"] for group in manifest["sets"] for chunk in group["chunks"]]

    first = unreal.load_asset(paths[0])
    before = describe(first, CANDIDATES)

    applied = {}
    changed = 0
    for path in paths:
        mesh = unreal.load_asset(path)
        if not mesh:
            continue
        touched = False
        for name in CANDIDATES:
            try:
                mesh.set_editor_property(name, True)
                touched = True
                applied[name] = applied.get(name, 0) + 1
            except Exception:  # noqa: BLE001
                continue
        if touched:
            unreal.EditorAssetLibrary.save_asset(path, only_if_is_dirty=False)
            changed += 1

    after = describe(unreal.load_asset(paths[0]), CANDIDATES)
    report = {"schema": "Tread.Destruction.ChunkCollision.v1", "chunks": len(paths), "saved": changed,
              "properties_applied": applied, "before": before, "after": after}
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=1)


main()
