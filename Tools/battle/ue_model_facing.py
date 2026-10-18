"""Model facing for the battle presentation (editor-side, Tools/ue_run.py), read-only on assets.

document/12 §3.2: units must face their target with their anatomical front, not a shared axis assumption (the old
Unity lesson: VRM / MMD fronts are not all local -Z).  For each of the 112 roster characters this reads the IK rig's
left / right thigh (or leg) and arm chain start bones, takes their reference-pose positions and derives the yaw of
the model's front in component space:  right = R - L (horizontal), forward = right x up  (UE: facing +X has its
right hand at +Y).  The thigh pair decides; the arm pair is a cross-check reported per character.

    python Tools/ue_run.py Tools/battle/ue_model_facing.py

Output: Content/Data/Generated/ModelFacing.json ({characterId: yaw}), Saved/Reports/Battle_ModelFacing.json.
"""
import json
import math
import os

import unreal

PROJECT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
ROSTER = os.path.join(PROJECT, "Content", "Data", "Generated", "CharacterRosterMap.json")
OUT = os.path.join(PROJECT, "Content", "Data", "Generated", "ModelFacing.json")
REPORT = os.path.join(PROJECT, "Saved", "Reports", "Battle_ModelFacing.json")
HERO_RIG = "/Game/Tread/Characters/Clukay416/Retarget/IK_Clukay416"


def rig_path(row):
    cid = row["characterId"]
    if row["modelSet"] == "VRM":
        return "/Game/Tread/Characters/VRM/%s/Retarget/IK_VRM_%s" % (cid, cid)
    if row["modelSet"] == "MMD":
        return "/Game/Tread/Characters/MMD/%s/Retarget/IK_MMD_%s" % (cid, cid)
    return HERO_RIG


def yaw_from(pose, left, right):
    l = unreal.AnimPoseExtensions.get_bone_pose(pose, left, unreal.AnimPoseSpaces.WORLD).translation
    r = unreal.AnimPoseExtensions.get_bone_pose(pose, right, unreal.AnimPoseSpaces.WORLD).translation
    rx, ry = r.x - l.x, r.y - l.y
    if rx * rx + ry * ry < 1e-4:
        return None
    # forward = right x up = (ry, -rx, 0)
    return math.degrees(math.atan2(-rx, ry))


def main():
    roster = json.load(open(ROSTER, encoding="utf-8"))["characters"]
    facing, rows = {}, []
    for row in roster:
        cid = row["characterId"]
        entry = {"characterId": cid, "modelSet": row["modelSet"]}
        rig = unreal.load_asset(rig_path(row))
        mesh = unreal.load_asset(row["meshAsset"])
        if not rig or not mesh:
            entry["error"] = "missing rig or mesh"
            rows.append(entry)
            continue
        ctrl = unreal.IKRigController.get_controller(rig)
        starts = {str(c.chain_name): str(ctrl.get_retarget_chain_start_bone(c.chain_name)) for c in ctrl.get_retarget_chains()}
        pose = unreal.AnimPoseExtensions.get_reference_pose(mesh.get_editor_property("skeleton"))
        legs = ("LeftThigh", "RightThigh") if "LeftThigh" in starts else ("LeftLeg", "RightLeg")
        leg_yaw = yaw_from(pose, starts.get(legs[0], ""), starts.get(legs[1], "")) if legs[0] in starts else None
        arm_yaw = yaw_from(pose, starts.get("LeftArm", ""), starts.get("RightArm", "")) if "LeftArm" in starts else None
        yaw = leg_yaw if leg_yaw is not None else arm_yaw
        entry.update({"legYaw": leg_yaw, "armYaw": arm_yaw, "yaw": yaw})
        if leg_yaw is not None and arm_yaw is not None:
            diff = abs((leg_yaw - arm_yaw + 180.0) % 360.0 - 180.0)
            entry["legArmDiff"] = round(diff, 1)
        if yaw is not None:
            facing[cid] = round(yaw, 2)
        rows.append(entry)
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump({"schema": "Tread.Battle.ModelFacing.v1", "note": "component-space yaw (deg) of each model's front",
                   "facing": facing}, handle, indent=1)
    bad = [r["characterId"] for r in rows if "yaw" not in r or r.get("yaw") is None or r.get("legArmDiff", 0) > 25]
    with open(REPORT, "w", encoding="utf-8") as handle:
        json.dump({"ok": not bad, "suspect": bad, "rows": rows}, handle, indent=1)
    hist = {}
    for v in facing.values():
        key = int(round(v / 15.0) * 15)
        hist[key] = hist.get(key, 0) + 1
    print("FACING n=%d suspect=%s hist=%s" % (len(facing), bad, sorted(hist.items())))


main()
