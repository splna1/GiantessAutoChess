"""Pick a dust/smoke Niagara system from the project and write the destruction VFX config (document/162).

Run this after importing a VFX pack (Fab: the official "50+ free Niagara systems" pack, or any smoke/dust pack):

    python Tools/ue_run.py Tools/destruction/set_dust_system.py            # scan + pick + write config
    python Tools/ue_run.py Tools/destruction/set_dust_system.py --list     # only list candidates
    python Tools/ue_run.py Tools/destruction/set_dust_system.py --set /Game/Path/NS_Foo

It writes Content/Tread/Destruction/DestructionVFX.json, which ATreadBuildingDestructionManager reads at BeginPlay, so
switching VFX needs no code change and no rebuild.

Ranking: name keywords first (dust > smoke > debris > explosion), then fewer/smaller emitters win (a collapse puff must
not be a 5-second cinematic cloud), then path length. Systems under /Game/Tread/City or /Game/Tread/Characters are
skipped - those are gameplay effects that must not be repurposed.
"""
import json
import os
import sys

import unreal

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG = os.path.join(PROJECT, "Content", "Tread", "Destruction", "DestructionVFX.json")
ROOTS = ["/Game"]
SKIP_PREFIXES = ("/Game/Tread/City", "/Game/Tread/Characters", "/Game/Tread/UI", "/Game/Tread/Maps")

KEYWORDS = (("dust", 6), ("smoke", 5), ("debris", 5), ("collapse", 5), ("rubble", 4),
            ("explosion", 2), ("explos", 2), ("fire", 1), ("spark", 1))


def candidates():
    found = []
    for root in ROOTS:
        for path in unreal.EditorAssetLibrary.list_assets(root, recursive=True, include_folder=False):
            asset_path = path.split(".")[0]
            if any(asset_path.startswith(skip) for skip in SKIP_PREFIXES):
                continue
            if not unreal.EditorAssetLibrary.does_asset_exist(asset_path):
                continue
            try:
                asset = unreal.EditorAssetLibrary.load_asset(asset_path)
            except Exception:  # noqa: BLE001
                continue
            if not isinstance(asset, unreal.NiagaraSystem):
                continue
            name = asset_path.rsplit("/", 1)[-1].lower()
            score = 0
            for keyword, weight in KEYWORDS:
                if keyword in name:
                    score = max(score, weight)
            emitters = 0
            try:
                emitters = asset.get_num_emitters()
            except Exception:  # noqa: BLE001
                pass
            found.append({"path": asset_path, "score": score, "emitters": emitters, "name": name})
    found.sort(key=lambda c: (-c["score"], c["emitters"], len(c["path"])))
    return found


def write_config(path):
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    with open(CONFIG, "w", encoding="utf-8") as handle:
        json.dump({"schema": "Tread.Destruction.VFX.v1", "dust_system": path}, handle, ensure_ascii=False, indent=1)
    print("CONFIG", CONFIG, "->", path)


def main():
    argv = sys.argv[1:]
    found = candidates()
    print("CANDIDATES", len(found))
    for item in found[:15]:
        print("  score=%d emitters=%-3d %s" % (item["score"], item["emitters"], item["path"]))

    if "--list" in argv:
        return
    if "--set" in argv:
        write_config(argv[argv.index("--set") + 1])
        return
    best = next((item for item in found if item["score"] >= 2), None)
    if best is None:
        print("NO_CANDIDATE: import a VFX pack first (Fab panel -> Library -> Add to project)")
        return
    write_config(best["path"])


main()
