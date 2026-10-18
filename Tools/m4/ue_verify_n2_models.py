"""N2 (editor-side): verify that MMD skeletal meshes can be loaded from Roster112.json.

Checks:
1. Load Roster112.json and Roster112_Models.json.
2. For each MMD character (char_101 through char_112), verify that the skeletal mesh exists at
   /Game/Tread/Characters/MMD/<characterId>/SK_MMD_<characterId>.
3. Report success/failure per model.

Report: Saved/Reports/N2_Model_Verification.json

    python Tools/ue_run.py Tools/m4/ue_verify_n2_models.py
"""
import json
import os
import sys

import unreal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "paris"))
import paris_common as pc  # noqa: E402

PROJECT = pc.PROJECT_DIR
ROSTER = PROJECT + "/Content/Data/Generated/Roster112.json"
MODELS = PROJECT + "/Content/Data/Source/Roster112_Models.json"
REPORT = PROJECT + "/Saved/Reports/N2_Model_Verification.json"
EAL = unreal.EditorAssetLibrary


def main():
    roster_doc = json.load(open(ROSTER, encoding="utf-8"))
    roster = roster_doc.get("characters", [])
    models_doc = json.load(open(MODELS, encoding="utf-8"))
    models_map = {m["characterId"]: m for m in models_doc.get("models", [])}

    results = []
    for char in roster:
        char_id = char["characterId"]
        if char_id < "char_101" or char_id > "char_112":
            continue  # Skip non-MMD

        model_info = models_map.get(char_id)
        if not model_info:
            results.append({"characterId": char_id, "ok": False, "error": "not in Roster112_Models.json"})
            continue

        mesh_path = f"/Game/Tread/Characters/MMD/{char_id}/SK_MMD_{char_id}"
        if not EAL.does_asset_exist(mesh_path):
            results.append({"characterId": char_id, "modelName": model_info["modelName"],
                            "ok": False, "error": "skeletal mesh not found"})
            continue

        mesh = EAL.load_asset(mesh_path)
        if mesh is None:
            results.append({"characterId": char_id, "modelName": model_info["modelName"],
                            "ok": False, "error": "failed to load mesh"})
            continue

        skeleton = mesh.get_editor_property("skeleton")
        bone_count = len(skeleton.get_editor_property("bone_tree")) if skeleton else 0

        results.append({"characterId": char_id, "modelName": model_info["modelName"],
                        "ok": True, "meshPath": mesh_path, "boneCount": bone_count})

    ok_count = sum(1 for r in results if r["ok"])
    report = {
        "schema": "Tread.N2.ModelVerification.v1",
        "total": len(results),
        "ok": ok_count,
        "failed": len(results) - ok_count,
        "models": results
    }

    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)

    for r in results:
        status = "OK" if r["ok"] else "ERROR"
        name = r.get("modelName", "?")
        msg = r.get("error", f"{r.get('boneCount', 0)} bones")
        print(f"N2_MODEL {status:5s} {r['characterId']} {name:20s} {msg}")

    if ok_count == len(results):
        print(f"\nAll {len(results)} MMD models verified")
        return 0
    else:
        print(f"\n{len(results) - ok_count}/{len(results)} models failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
