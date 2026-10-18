"""N2 (b): inventory the MMD skeletons through the editor MCP and check the retarget bones exist.

The UE Python API cannot list a skeleton's bones (doc 148 section 4.3); the editor MCP
SkeletalMeshTools.get_bone_names can, so this script talks to the MCP endpoint instead of
running inside the editor.  It also pairs each MMD bone with the Clukay416 bone it retargets from,
which is the mapping the IK Rig chain definitions in n2_build_retarget.py use.

    python Tools/m4/n2_mmd_bone_inventory.py

Report: Saved/Reports/N2_MMD_Bones.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from ue_mcp import UeMcp, text_of  # noqa: E402

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPORT = os.path.join(PROJECT, "Saved", "Reports", "N2_MMD_Bones.json")

SOURCE_MESH = "/Game/Tread/Characters/Clukay416/416/SkeletalMeshes/U_Char_1.U_Char_1"
MMD_FOLDER = "/Game/Tread/Characters/MMD"
CHARACTERS = ["char_%03d" % n for n in range(101, 113)]

# Chain -> (source bone, MMD bone).  The source VRM is a translated MMD skeleton, so every pair is a
# direct counterpart; the arm entries deliberately start at the upper arm rather than the shoulder so
# the MMD 腕捩/肩 twist bones are driven by retargeting rather than by a chain of their own.
CHAINS = [
    ("Spine", "6_joint_Torso", "上半身"),
    ("Neck", "8_joint_Neck", "首"),
    ("Head", "9_joint_Head", "頭"),
    ("LeftArm", "30_joint_LeftShoulder", "肩_L"),
    ("RightArm", "45_joint_RightShoulder", "肩_R"),
    ("LeftLeg", "19__joint_LeftHip", "足_L"),
    ("RightLeg", "14__joint_RightHip", "足_R"),
]


MESH_TOOLSET = "editor_toolset.toolsets.skeletal_mesh.SkeletalMeshTools"


def bone_names(client, mesh_path):
    result = client.call("get_bone_names", {"mesh": {"refPath": mesh_path}}, toolset=MESH_TOOLSET)
    text = text_of(result)
    names = None
    for chunk in [text] + [str((result or {}).get("structuredContent"))]:
        try:
            names = json.loads(chunk)
        except ValueError:
            continue
        if isinstance(names, dict) and "returnValue" in names:
            names = names["returnValue"]
        if isinstance(names, list):
            break
        names = None
    if not isinstance(names, list) or not names:
        raise RuntimeError("no bone names for %s: %s" % (mesh_path, text[:300]))
    return [str(n) for n in names]


def main():
    client = UeMcp()
    source = bone_names(client, SOURCE_MESH)
    print("SOURCE %d bones" % len(source))
    missing_source = [pair[1] for pair in CHAINS if pair[1] and pair[1] not in source]
    if missing_source:
        raise RuntimeError("source mesh is missing %s" % missing_source)

    doc = {"schema": "Tread.N2.MmdBones.v1", "sourceMesh": SOURCE_MESH, "sourceBoneCount": len(source),
           "chains": [{"chain": c, "source": s, "target": t} for c, s, t in CHAINS], "characters": []}
    ok = True
    for character in CHARACTERS:
        mesh = "%s/%s/SK_MMD_%s.SK_MMD_%s" % (MMD_FOLDER, character, character, character)
        names = bone_names(client, mesh)
        missing = [pair[2] for pair in CHAINS if pair[2] and pair[2] not in names]
        present = [pair[2] for pair in CHAINS if pair[2] and pair[2] in names]
        doc["characters"].append({"characterId": character, "mesh": mesh, "boneCount": len(names),
                                  "missing": missing, "present": present})
        ok = ok and not missing
        print("MMD %-9s bones=%-5d chains=%d/20 %s" % (character, len(names), len(present),
                                                       "" if not missing else "MISSING " + ",".join(missing)))

    doc["ok"] = ok
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, ensure_ascii=False, indent=1)
    print("REPORT %s" % REPORT)
    print("RESULT %s" % ("OK" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
