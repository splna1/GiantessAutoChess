"""Probe the imported scan mesh triangle count through the live UE Python API."""
import json
import time

import unreal

import paris_common as pc


PATH = "/Game/Tread/City/Paris/Meshes/Ruins/SM_CollapsedBuilding_Scan"
REPORT = pc.REPORT_DIR + "/M0_Scan_LOD_Probe.json"


def main():
    mesh = unreal.EditorAssetLibrary.load_asset(PATH)
    if not mesh:
        raise RuntimeError("could not load %s" % PATH)
    lod_count = mesh.get_num_lods()
    lods = []
    for lod in range(lod_count):
        try:
            tris = int(mesh.get_num_triangles(lod))
        except Exception as exc:  # UE versions may expose only the render-data API.
            tris = None
            error = str(exc)
        item = {"lod": lod, "triangles": tris}
        if tris is None:
            item["error"] = error
        lods.append(item)
    report = {
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "asset": PATH,
        "num_lods": lod_count,
        "lods": lods,
        "nanite_enabled": bool(mesh.get_editor_property("nanite_settings").enabled),
        "expected_probe_triangles": 2015451,
        "m0_report_triangles": 16064,
    }
    report["ok"] = bool(lods) and all(x["triangles"] is not None for x in lods)
    pc.write_json(REPORT, report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
