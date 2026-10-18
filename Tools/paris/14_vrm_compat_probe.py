"""Import the VRM 1.0 MToon sample into an isolated UE folder and write a compatibility report."""
import json
import os
import shutil
import struct
import sys
import time

import unreal
import paris_common as pc

SOURCE = pc.UNITY_ROOT + "/MyProject/Assets/Art/Giantess/阿芙.vrm"
STAGING = pc.STAGING_DIR + "/vrm/Afu_vrm1.glb"
DEST = pc.CHAR + "/M0Probe_Afu"
REPORT = pc.REPORT_DIR + "/M0_VRM_Compatibility_Report.json"


def gltf_summary(path):
    with open(path, "rb") as stream:
        blob = stream.read()
    length = struct.unpack_from("<I", blob, 12)[0]
    data = json.loads(blob[20:20 + length])
    return {"bytes": len(blob), "extensions_used": data.get("extensionsUsed", []),
            "extensions": sorted(data.get("extensions", {}).keys()),
            "nodes": len(data.get("nodes", [])), "meshes": len(data.get("meshes", [])),
            "materials": len(data.get("materials", [])), "skins": len(data.get("skins", [])),
            "animations": len(data.get("animations", []))}


def main(argv):
    started = time.time()
    os.makedirs(os.path.dirname(STAGING), exist_ok=True)
    if not os.path.exists(STAGING) or os.path.getsize(STAGING) != os.path.getsize(SOURCE):
        shutil.copy2(SOURCE, STAGING)
    result = {"source": SOURCE, "staged": STAGING, "source_format": gltf_summary(STAGING),
              "destination": DEST, "ok": False, "imported_object_paths": [], "seconds": 0.0}
    try:
        if "--reimport" in argv and pc.EAL.does_directory_exist(DEST):
            pc.EAL.delete_directory(DEST)
        os.makedirs(os.path.dirname(REPORT), exist_ok=True)
        task = unreal.AssetImportTask()
        task.filename = STAGING.replace("/", "\\")
        task.destination_path = DEST
        task.automated = True
        task.replace_existing = True
        task.save = True
        pc.ASSET_TOOLS.import_asset_tasks([task])
        imported = [str(p) for p in task.imported_object_paths]
        result["imported_object_paths"] = imported
        result["ok"] = bool(imported)
    except Exception as exc:
        result["error"] = repr(exc)
    result["seconds"] = round(time.time() - started, 2)
    pc.write_json(REPORT, result)
    pc.log("VRM compatibility", result)


main(sys.argv[1:])
