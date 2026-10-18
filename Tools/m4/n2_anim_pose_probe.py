"""N2 anim pose probe (editor-side, Tools/ue_run.py): does a retargeted clip pose the MMD mesh like the hero?

Read-only.  For the M1 hero clip and for each MMD character's retargeted A_GP_Idle, evaluate the pose
in component space and compare it with the reference pose the mesh renders in when nothing plays:
bone-position extent, smallest / largest bone scale, the root bone and any NaN.  A mesh that renders in
its reference pose but vanishes once the clip plays shows up here as a collapsed extent, a near-zero
scale or a far-away root.

It also reports each arm's angle away from straight down, because scale and extent alone passed a
retarget that had the arms rotated about 100 degrees the wrong way (2026-10-11, target retarget pose
not aligned to the source's): the hero idles with the wrists 43 cm below the shoulders, the MMD
characters had them 26 cm above, and every bone scale was still 1.

    python Tools/ue_run.py Tools/m4/n2_anim_pose_probe.py [--only char_101]
    python Tools/ue_run.py Tools/m4/n2_anim_pose_probe.py --clip all [--only char_101]
    python Tools/ue_run.py Tools/m4/n2_anim_pose_probe.py --clip Kick,Stomp
    python Tools/ue_run.py Tools/m4/n2_anim_pose_probe.py --set vrm --clip all [--only char_002]

--set vrm sweeps the M4 roster VRMs (/Game/Tread/Characters/VRM) instead of the twelve MMD models; their arm
and leg bones differ per model and are read from Saved/Reports/M4_Retarget_Build.json and M4_VRM_Inventory.json
(report: Saved/Reports/M4_AnimPoseSweep.json).

Without --clip it probes A_GP_Idle only, at t0 and mid-clip (report: Saved/Reports/N2_AnimPoseProbe.json).
With --clip (comma-separated names without the A_GP_ prefix, or "all" for every source clip) it sweeps
each clip at five points across its length and judges every MMD clip against the hero playing the same
source clip at the same point (report: Saved/Reports/N2_AnimPoseSweep.json, merged per character and
clip so the sweep can run one character per call).  A row fails on: a missing clip, a length that
differs from the hero's, NaN bones, a root scale away from 1, a bone scale collapsed below MIN_SCALE,
an arm more than ARM_TOL_DEG away from the hero's, a leg swing or knee bend more than LEG_TOL_DEG
away from the hero's (measured on the skinned D bones, see HERO_LEG), a heading more than
FACING_TOL_DEG away from the hero's, or a bounding diagonal that
grew or shrank against its own reference pose more than EXTENT_TOL times what the hero's did.
"""
import json
import math
import os
import re
import sys

import unreal

PROJECT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
REPORT = os.path.join(PROJECT, "Saved", "Reports", "N2_AnimPoseProbe.json")
HERO_IDLE = "/Game/Tread/Characters/Clukay416/Anim/GP/A_GP_Idle"
HERO_GP = "/Game/Tread/Characters/Clukay416/Anim/GP"
SWEEP_REPORT = os.path.join(PROJECT, "Saved", "Reports", "N2_AnimPoseSweep.json")
SWEEP_FRACTIONS = (0.0, 0.25, 0.5, 0.75, 1.0)
# Sweep verdict thresholds.  After the pose fix the idle arms sit about 6 degrees off the hero's
# (MMD 20-26, hero 17-20); the broken retarget was about 100 degrees off.
ARM_TOL_DEG = 45.0
ROOT_SCALE_TOL = 0.01
MIN_SCALE = 0.1
EXTENT_TOL = 1.6
LENGTH_TOL_S = 0.05
MMD = "/Game/Tread/Characters/MMD"
APE = unreal.AnimPoseExtensions
SPACE = unreal.AnimPoseSpaces.WORLD  # component space for an AnimPose
# Shoulder -> wrist per side; the chains are named the same on both rigs, the bones are not.
HERO_ARM = {"L": ("30_joint_LeftShoulder", "42_joint_LeftWrist"),
            "R": ("45_joint_RightShoulder", "57_joint_RightWrist")}
MMD_ARM = {"L": ("肩_L", "手首_L"), "R": ("肩_R", "手首_R")}
# Hip -> knee -> ankle per side on the bones the legs are SKINNED to.  On both skeletons that is the
# MMD "D" set: the plain leg bones carry no weights on any of the 12 MMD meshes, and on the source the
# GP clips walk the D bones while the plain ones barely move (2026-10-12; the first retarget drove
# the plain bones, so every MMD leg stood still while the bone probe saw nothing wrong).
HERO_LEG = {"L": ("243_joint_LeftHipD", "244_joint_LeftKneeD", "245_joint_LeftFootD"),
            "R": ("239_joint_RightHipD", "240_joint_RightKneeD", "241_joint_RightFootD")}
MMD_LEG = {"L": ("足D_L", "ひざD_L", "足首D_L"), "R": ("足D_R", "ひざD_R", "足首D_R")}
LEG_TOL_DEG = 30.0
# Facing = heading of the right hip -> left hip axis.  Before 2026-10-12 every MMD mesh faced +Y while
# the hero faces -Y, a 180 degree turn no angle between bones can see.
FACING_TOL_DEG = 45.0


def arm_angles(pose, bones):
    """Angle of each shoulder -> wrist vector away from straight down, in degrees.  None per side if
    this skeleton does not have those bones."""
    out = {}
    for side, (shoulder, wrist) in bones.items():
        try:
            a = APE.get_bone_pose(pose, shoulder, SPACE).translation.to_tuple()
            b = APE.get_bone_pose(pose, wrist, SPACE).translation.to_tuple()
        except Exception:  # noqa: BLE001 - a name this skeleton does not carry
            out[side] = None
            continue
        v = [b[i] - a[i] for i in range(3)]
        length = math.sqrt(sum(x * x for x in v)) or 1.0
        out[side] = round(math.degrees(math.acos(max(-1.0, min(1.0, -v[2] / length)))), 1)
    return out


def angle_deg(u, v):
    lu = math.sqrt(sum(x * x for x in u)) or 1.0
    lv = math.sqrt(sum(x * x for x in v)) or 1.0
    return math.degrees(math.acos(max(-1.0, min(1.0, sum(a * b for a, b in zip(u, v)) / (lu * lv)))))


def leg_angles(pose, bones):
    """Per side: swing = hip -> knee (the thigh) away from straight down, bend = how far the knee folds
    (0 = straight leg).  None per side if this skeleton does not have those bones.

    Swing was hip -> ankle until 2026-10-13; with a bent knee that direction depends on the thigh/shin length
    ratio, so char_053 (thigh 0.58 of the shin, the hero's 0.96) read 30 deg off in every kneel while its
    joint rotations matched the hero's."""
    out = {}
    for side, (hip, knee, ankle) in bones.items():
        try:
            h, k, a = (APE.get_bone_pose(pose, b, SPACE).translation.to_tuple() for b in (hip, knee, ankle))
        except Exception:  # noqa: BLE001 - a name this skeleton does not carry
            out[side] = None
            continue
        down = [k[i] - h[i] for i in range(3)]
        out[side] = {"swing": round(angle_deg(down, (0.0, 0.0, -1.0)), 1),
                     "bend": round(180.0 - angle_deg([h[i] - k[i] for i in range(3)],
                                                     [a[i] - k[i] for i in range(3)]), 1)}
    return out


def facing(pose, leg_bones):
    """Heading in degrees of the right hip -> left hip axis, or None without those bones."""
    try:
        left = APE.get_bone_pose(pose, leg_bones["L"][0], SPACE).translation
        right = APE.get_bone_pose(pose, leg_bones["R"][0], SPACE).translation
    except Exception:  # noqa: BLE001 - a name this skeleton does not carry
        return None
    return round(math.degrees(math.atan2(left.y - right.y, left.x - right.x)), 1)


def stats(pose, arm_bones=None, leg_bones=None):
    names = list(APE.get_bone_names(pose))
    lo = [math.inf] * 3
    hi = [-math.inf] * 3
    smin, smax, nan = math.inf, 0.0, 0
    smallest = largest = None
    for name in names:
        t = APE.get_bone_pose(pose, name, SPACE)
        p = t.translation.to_tuple()
        s = t.scale3d.to_tuple()
        if any(math.isnan(v) or math.isinf(v) for v in p + s):
            nan += 1
            continue
        for i in range(3):
            lo[i] = min(lo[i], p[i])
            hi[i] = max(hi[i], p[i])
        m = min(abs(v) for v in s)
        if m < smin:
            smin, smallest = m, str(name)
        if max(abs(v) for v in s) > smax:
            smax, largest = max(abs(v) for v in s), str(name)
    root = APE.get_bone_pose(pose, names[0], SPACE) if names else None
    return {
        "bones": len(names),
        "extentCm": [round(hi[i] - lo[i], 2) for i in range(3)],
        "minCm": [round(v, 2) for v in lo],
        "maxCm": [round(v, 2) for v in hi],
        "minScale": [round(smin, 5), smallest],
        "maxScale": [round(smax, 5), largest],
        "root": None if root is None else {"bone": str(names[0]),
                                            "loc": [round(v, 2) for v in root.translation.to_tuple()],
                                            "scale": [round(v, 5) for v in root.scale3d.to_tuple()]},
        "arms": arm_angles(pose, arm_bones) if arm_bones else None,
        "legs": leg_angles(pose, leg_bones) if leg_bones else None,
        "facingDeg": facing(pose, leg_bones) if leg_bones else None,
        "nanBones": nan,
    }


def options(mesh):
    opt = unreal.AnimPoseEvaluationOptions()
    if mesh is not None:
        try:
            opt.set_editor_property("optional_skeletal_mesh", mesh)
        except Exception:
            pass
    return opt


def probe(label, anim_path, mesh, arm_bones):
    anim = unreal.EditorAssetLibrary.load_asset(anim_path)
    if anim is None:
        return {"label": label, "error": "missing " + anim_path}
    skeleton = anim.get_editor_property("skeleton")
    row = {"label": label, "anim": anim_path, "skeleton": skeleton.get_path_name() if skeleton else None,
           "mesh": mesh.get_path_name() if mesh else None, "length": round(anim.get_play_length(), 3)}
    row["reference"] = stats(APE.get_reference_pose(skeleton), arm_bones)
    for key, t in (("t0", 0.0), ("tMid", anim.get_play_length() * 0.5)):
        row[key] = stats(APE.get_anim_pose_at_time(anim, t, options(mesh)), arm_bones)
    return row


def diagonal(s):
    return math.sqrt(sum(v * v for v in s["extentCm"]))


def sweep_clip(anim_path, mesh, arm_bones, leg_bones):
    """Stats at SWEEP_FRACTIONS of the clip, or None if the clip is missing."""
    anim = unreal.EditorAssetLibrary.load_asset(anim_path)
    if anim is None:
        return None
    length = anim.get_play_length()
    skeleton = anim.get_editor_property("skeleton")
    samples = []
    for f in SWEEP_FRACTIONS:
        # Stay a frame short of the end: evaluating exactly at the length may wrap to the first key.
        t = max(0.0, min(length * f, length - 1.0 / 120.0))
        samples.append(dict(stats(APE.get_anim_pose_at_time(anim, t, options(mesh)), arm_bones, leg_bones),
                            t=round(t, 3)))
    return {"length": round(length, 3), "reference": stats(APE.get_reference_pose(skeleton), arm_bones, leg_bones),
            "samples": samples}


def arm_pairs(mmd, hero):
    """(fraction, side, mmd degrees, hero degrees) wherever both skeletons have the arm."""
    for f, s, h in zip(SWEEP_FRACTIONS, mmd["samples"], hero["samples"]):
        for side in ("L", "R"):
            a, b = (s["arms"] or {}).get(side), (h["arms"] or {}).get(side)
            if a is not None and b is not None:
                yield f, side, a, b


def leg_pairs(mmd, hero):
    """(fraction, side, measure, mmd degrees, hero degrees) for leg swing and knee bend."""
    for f, s, h in zip(SWEEP_FRACTIONS, mmd["samples"], hero["samples"]):
        for side in ("L", "R"):
            a, b = (s.get("legs") or {}).get(side), (h.get("legs") or {}).get(side)
            if a and b:
                for measure in ("swing", "bend"):
                    yield f, side, measure, a[measure], b[measure]


def judge(hero, mmd):
    """Failure strings of one MMD clip against the hero's run of the same source clip."""
    if mmd is None:
        return ["missing"]
    fails = []
    if hero is not None and abs(mmd["length"] - hero["length"]) > LENGTH_TOL_S:
        fails.append("length %.3f vs hero %.3f" % (mmd["length"], hero["length"]))
    ref_min = mmd["reference"]["minScale"][0]
    ref_diag = diagonal(mmd["reference"]) or 1.0
    for i, s in enumerate(mmd["samples"]):
        at = "@%.2f" % SWEEP_FRACTIONS[i]
        if s["nanBones"]:
            fails.append("nan %d %s" % (s["nanBones"], at))
        if s["root"] and any(abs(v - 1.0) > ROOT_SCALE_TOL for v in s["root"]["scale"]):
            fails.append("rootScale %s %s" % (s["root"]["scale"], at))
        if s["minScale"][0] < MIN_SCALE <= ref_min:
            fails.append("minScale %s %s" % (s["minScale"], at))
        if hero is not None:
            h = hero["samples"][i]
            hero_ratio = diagonal(h) / (diagonal(hero["reference"]) or 1.0)
            ratio = (diagonal(s) / ref_diag) / (hero_ratio or 1.0)
            if not 1.0 / EXTENT_TOL <= ratio <= EXTENT_TOL:
                fails.append("extent x%.2f of hero %s" % (ratio, at))
            if s.get("facingDeg") is not None and h.get("facingDeg") is not None:
                turn = abs((s["facingDeg"] - h["facingDeg"] + 180.0) % 360.0 - 180.0)
                if turn > FACING_TOL_DEG:
                    fails.append("facing %.0f vs hero %.0f %s" % (s["facingDeg"], h["facingDeg"], at))
    if hero is not None:
        for f, side, a, b in arm_pairs(mmd, hero):
            if abs(a - b) > ARM_TOL_DEG:
                fails.append("arm%s %.0f vs hero %.0f @%.2f" % (side, a, b, f))
        for f, side, measure, a, b in leg_pairs(mmd, hero):
            if abs(a - b) > LEG_TOL_DEG:
                fails.append("leg%s %s %.0f vs hero %.0f @%.2f" % (side, measure, a, b, f))
    return fails


def summarize(hero, mmd):
    """The numbers a reader wants per row: worst arm offset, root scale range, extents."""
    if mmd is None:
        return {}
    deltas = [abs(a - b) for _, _, a, b in arm_pairs(mmd, hero)] if hero is not None else []
    legs = [abs(a - b) for _, _, _, a, b in leg_pairs(mmd, hero)] if hero is not None else []
    roots = [v for s in mmd["samples"] if s["root"] for v in s["root"]["scale"]]
    return {"length": mmd["length"],
            "maxArmDeltaDeg": round(max(deltas or [0.0]), 1),
            "maxLegDeltaDeg": round(max(legs or [0.0]), 1),
            "legs": [s.get("legs") for s in mmd["samples"]],
            "facingDeg": [s.get("facingDeg") for s in mmd["samples"]],
            "armDeg": [s["arms"] for s in mmd["samples"]],
            "rootScaleRange": [min(roots), max(roots)] if roots else None,
            "minScale": min(s["minScale"][0] for s in mmd["samples"]),
            "extentCm": [s["extentCm"] for s in mmd["samples"]],
            "nanBones": sum(s["nanBones"] for s in mmd["samples"])}


def source_clips():
    names = []
    for path in unreal.EditorAssetLibrary.list_assets(HERO_GP, recursive=False):
        name = path.rsplit("/", 1)[-1].split(".")[0]
        if name.startswith("A_GP_"):
            names.append(name[len("A_GP_"):])
    return sorted(names)


SETS = {"mmd": {"root": MMD, "prefix": "SK_MMD_", "report": SWEEP_REPORT},
        "vrm": {"root": "/Game/Tread/Characters/VRM", "prefix": "SK_VRM_",
                "report": os.path.join(PROJECT, "Saved", "Reports", "M4_AnimPoseSweep.json")}}
SET = SETS["mmd"]


def norm(name):
    # The FBX importer turns '.', spaces and other punctuation in bone names into '_'.
    return re.sub(r"[^0-9A-Za-z-￿]", "_", name)


_VRM_TABLES = {}


def character_bones(cid, mesh):
    """(arm bones, leg bones) of one character in the probe's {"L": (...), "R": (...)} form."""
    if SET is SETS["mmd"]:
        return MMD_ARM, MMD_LEG
    if not _VRM_TABLES:
        reports = os.path.join(PROJECT, "Saved", "Reports")
        _VRM_TABLES["rtg"] = {r["characterId"]: r for r in json.load(
            open(os.path.join(reports, "M4_Retarget_Build.json"), encoding="utf-8"))["characters"]}
        _VRM_TABLES["inv"] = {r["characterId"]: r for r in json.load(
            open(os.path.join(reports, "M4_VRM_Inventory.json"), encoding="utf-8"))["rows"]}
    lut = {norm(str(b)): str(b) for b in APE.get_bone_names(APE.get_reference_pose(mesh.get_editor_property("skeleton")))}
    chains = _VRM_TABLES["rtg"][cid]["chains"]  # already UE names
    inv = _VRM_TABLES["inv"][cid]["chains"]  # glTF names: upper leg, lower leg, foot
    arm = {"L": tuple(chains["LeftArm"]), "R": tuple(chains["RightArm"])}
    leg = {"L": tuple(lut[norm(b)] for b in inv["LeftLeg"]["bones"]),
           "R": tuple(lut[norm(b)] for b in inv["RightLeg"]["bones"])}
    return arm, leg


def sweep(clips, only):
    hero = {clip: sweep_clip("%s/A_GP_%s" % (HERO_GP, clip), None, HERO_ARM, HERO_LEG) for clip in clips}
    try:
        with open(SET["report"], encoding="utf-8") as f:
            old = json.load(f)
    except (OSError, ValueError):
        old = {}
    rows = {(r["characterId"], r["clip"]): r for r in old.get("rows", [])}
    for folder in sorted(unreal.EditorAssetLibrary.list_assets(SET["root"], recursive=False, include_folder=True)):
        cid = folder.rstrip("/").rsplit("/", 1)[-1]
        if not cid.startswith("char_") or (only and cid not in only.split(",")):
            continue
        mesh = unreal.EditorAssetLibrary.load_asset("%s/%s/%s%s" % (SET["root"], cid, SET["prefix"], cid))
        if mesh is None:
            continue
        arm_bones, leg_bones = character_bones(cid, mesh)
        for clip in clips:
            mmd = sweep_clip("%s/%s/Anim/A_GP_%s" % (SET["root"], cid, clip), mesh, arm_bones, leg_bones)
            fails = judge(hero[clip], mmd)
            row = dict(characterId=cid, clip=clip, ok=not fails, fails=fails, **summarize(hero[clip], mmd))
            rows[(cid, clip)] = row
            print("SWEEP %-8s %-12s %s armDelta=%s legDelta=%s rootScale=%s%s" % (
                cid, clip, "OK  " if row["ok"] else "FAIL", row.get("maxArmDeltaDeg"), row.get("maxLegDeltaDeg"),
                row.get("rootScaleRange"), "" if row["ok"] else " " + "; ".join(fails[:3])))
    ordered = [rows[k] for k in sorted(rows)]
    hero_rows = old.get("hero", {})
    for clip, h in hero.items():
        hero_rows[clip] = None if h is None else {"length": h["length"],
                                                  "armDeg": [s["arms"] for s in h["samples"]],
                                                  "legs": [s["legs"] for s in h["samples"]],
                                                  "extentCm": [s["extentCm"] for s in h["samples"]]}
    bad = [r for r in ordered if not r["ok"]]
    report = {"schema": "Tread.N2.AnimPoseSweep.v3",
              "thresholds": {"armTolDeg": ARM_TOL_DEG, "legTolDeg": LEG_TOL_DEG, "facingTolDeg": FACING_TOL_DEG, "rootScaleTol": ROOT_SCALE_TOL, "minScale": MIN_SCALE,
                             "extentTol": EXTENT_TOL, "lengthTolS": LENGTH_TOL_S,
                             "fractions": list(SWEEP_FRACTIONS)},
              "total": len(ordered), "bad": len(bad), "ok": bool(ordered) and not bad,
              "characters": sorted({r["characterId"] for r in ordered}),
              "clips": sorted({r["clip"] for r in ordered}),
              "maxArmDeltaDeg": max([r.get("maxArmDeltaDeg", 0.0) for r in ordered] or [0.0]),
              "maxLegDeltaDeg": max([r.get("maxLegDeltaDeg", 0.0) for r in ordered] or [0.0]),
              "hero": hero_rows, "rows": ordered}
    os.makedirs(os.path.dirname(SET["report"]), exist_ok=True)
    with open(SET["report"], "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("SWEEP total=%d bad=%d ok=%s maxArmDeltaDeg=%s maxLegDeltaDeg=%s" % (
        report["total"], report["bad"], report["ok"], report["maxArmDeltaDeg"], report["maxLegDeltaDeg"]))


def main():
    global SET
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else ""
    SET = SETS[sys.argv[sys.argv.index("--set") + 1] if "--set" in sys.argv else "mmd"]
    if "--clip" in sys.argv:
        arg = sys.argv[sys.argv.index("--clip") + 1]
        sweep(source_clips() if arg == "all" else [c.strip() for c in arg.split(",") if c.strip()], only)
        return
    rows = [probe("hero", HERO_IDLE, None, HERO_ARM)]
    for folder in sorted(unreal.EditorAssetLibrary.list_assets(MMD, recursive=False, include_folder=True)):
        cid = folder.rstrip("/").rsplit("/", 1)[-1]
        if not cid.startswith("char_") or (only and cid != only):
            continue
        mesh = unreal.EditorAssetLibrary.load_asset("%s/%s/SK_MMD_%s" % (MMD, cid, cid))
        rows.append(probe(cid, "%s/%s/Anim/A_GP_Idle" % (MMD, cid), mesh, MMD_ARM))
    for row in rows:
        if "error" in row:
            print("POSE", row["label"], row["error"])
            continue
        for key in ("reference", "t0", "tMid"):
            s = row[key]
            print("POSE %-8s %-9s ext=%s rootScale=%s armDeg=%s nan=%d" % (
                row["label"], key, s["extentCm"], s["root"]["scale"] if s["root"] else None,
                s["arms"], s["nanBones"]))
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump({"schema": "Tread.N2.AnimPoseProbe.v1", "rows": rows}, f, ensure_ascii=False, indent=1)


main()
