"""M4: IK Rigs, IK Retargeters and the retargeted GP clip set for the imported roster VRMs.

Editor-side (Tools/ue_run.py).  The VRM counterpart of n2_build_retarget.py, with the same rules
(document/151 and the memories it names):

  * the source rig IK_Clukay416 is the one N2 configured; it is loaded and checked here, never reconfigured,
    because the twelve MMD retargeters reference it;
  * target rigs and retargeters are reconfigured in place, never deleted (memory: tread-editor-ikrig-crash);
  * chains come from each model's VRM humanoid map (the sidecar of blender_vrm_to_fbx.py); a leg whose skin lives
    on the MMD "D" twins instead (28 of the 100 roster files, Saved/Reports/M4_VRM_Inventory.json) takes the twins,
    because a chain on unskinned bones moves nothing (memory: tread-mmd-dbone-skin);
  * the target retarget pose is aligned chain-to-chain (memory: tread-retarget-pose-align); every roster VRM binds
    in a T-pose like the hero, so this is close to a no-op, but it keeps one code path for both;
  * each leg is retargeted as three chains (thigh, shin, foot) from a leg-split copy of the source rig.  With one
    hip-to-foot chain the FK op takes every target bone's rotation at its fractional position along the source
    chain, so a target whose knee sits elsewhere along the leg gets only part of the knee bend (char_053: knee at
    37 % of the leg against the hero's 49 %, kneel bend 105 deg against 138), and twist bones inside the leg take
    half the bend and curve the thigh (char_046: Hip, HipPart1, HipPart2, Knee, ...).  The pose sweep found both
    (Saved/Reports/M4_AnimPoseSweep.json, 2026-10-13).

    python Tools/ue_run.py Tools/m4/m4_build_retarget.py [--chars char_002,char_003] [--clips Idle,Walk] [--limit N]

  --limit N   stop after N characters that still need building (batch runs, resumable: a character whose
              report row is ok with every clip is skipped unless it is named in --chars)

Layout
  /Game/Tread/Characters/VRM/char_0xx/Retarget/IK_VRM_char_0xx   target rig
  /Game/Tread/Characters/VRM/char_0xx/Retarget/RTG_char_0xx      retargeter (source IK_Clukay416 -> target)
  /Game/Tread/Characters/VRM/char_0xx/Anim/A_GP_*                retargeted clips

Report: Saved/Reports/M4_Retarget_Build.json (merged per character)
"""
import json
import os
import re
import sys

import unreal

PROJECT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
REPORT = os.path.join(PROJECT, "Saved", "Reports", "M4_Retarget_Build.json")
INVENTORY = os.path.join(PROJECT, "Saved", "Reports", "M4_VRM_Inventory.json")
SIDECARS = os.path.join(PROJECT, "Saved", "Staging", "vrm_fbx")

SOURCE_MESH = "/Game/Tread/Characters/Clukay416/416/SkeletalMeshes/U_Char_1.U_Char_1"
SOURCE_RIG = "/Game/Tread/Characters/Clukay416/Retarget/IK_Clukay416"
SOURCE_ANIM_DIR = "/Game/Tread/Characters/Clukay416/Anim/GP"
VRM_ROOT = "/Game/Tread/Characters/VRM"
SPLIT_SOURCE_RIG = "/Game/Tread/Characters/Clukay416/Retarget/IK_Clukay416_LegSplit"
CHAIN_NAMES = ["Spine", "Neck", "Head", "LeftArm", "RightArm", "LeftLeg", "RightLeg"]
LEG_PARTS = ("Thigh", "Shin", "Foot")
SPLIT_CHAIN_NAMES = CHAIN_NAMES[:5] + [side + part for side in ("Left", "Right") for part in LEG_PARTS]
EAL = unreal.EditorAssetLibrary


def log(message):
    unreal.log("M4: " + message)
    print("M4 " + message)


def norm(name):
    # The FBX importer turns '.', spaces and other punctuation in bone names into '_'.
    return re.sub(r"[^0-9A-Za-z\u0080-￿]", "_", name)


def target_chains(cid, skeleton_bones, inventory_row):
    """[(chain, start, end)] in UE bone names, plus the retarget root."""
    side = json.load(open(os.path.join(SIDECARS, cid, "SK_VRM_%s.json" % cid), encoding="utf-8"))
    h = side["humanoid"]
    lut = {norm(b): b for b in skeleton_bones}

    def ue(name):
        found = lut.get(norm(name))
        if found is None:
            raise RuntimeError("%s: bone %r not in the UE skeleton" % (cid, name))
        return found

    spine_end = h.get("upper_chest") or h.get("chest") or h["spine"]
    legs, knees = {}, {}
    for chain in ("LeftLeg", "RightLeg"):
        inv = (inventory_row or {}).get("chains", {}).get(chain)
        prefix = "left" if chain.startswith("Left") else "right"
        if inv and inv.get("via") == "D":
            legs[chain] = (inv["bones"][0], inv["bones"][-1])
            knees[chain] = inv["bones"][1]
        else:
            legs[chain] = (h[prefix + "_upper_leg"], h[prefix + "_foot"])
            knees[chain] = h[prefix + "_lower_leg"]
    chains = [("Spine", h["spine"], spine_end), ("Neck", h["neck"], h["neck"]), ("Head", h["head"], h["head"]),
              ("LeftArm", h.get("left_shoulder") or h["left_upper_arm"], h["left_hand"]),
              ("RightArm", h.get("right_shoulder") or h["right_upper_arm"], h["right_hand"]),
              ("LeftLeg",) + legs["LeftLeg"], ("RightLeg",) + legs["RightLeg"]]
    return (ue(h["hips"]), [(c, ue(s), ue(e)) for c, s, e in chains], {c: inv_via(inventory_row, c) for c in legs},
            {c: ue(k) for c, k in knees.items()})


def ancestors(mesh, bone):
    out = [bone]
    while True:
        parent = str(mesh.get_bone_parent(out[-1]))
        if parent in ("None", ""):
            return out
        out.append(parent)


def retarget_root(mesh, chains):
    """The lowest common ancestor of the spine and both leg chains.

    Not the VRM "hips" bone: on MMD-derived models that is センター (centre), which can sit far below the pelvis
    (39 % of the height on char_009, the hero's root is at 62 %).  The retargeter scales the root's vertical motion
    by the ratio of the root heights, so a low root squats too shallow and the knees hang in the air in every
    kneel and sit (found by the Sonnet image review, 2026-10-12: knees at 10-13 % of the height against the
    hero's 4 %).  The common ancestor is 腰 (waist) there, at 55-60 %; on the other rigs it is the hips bone itself.
    """
    paths = [ancestors(mesh, start) for name, start, _ in chains if name in ("Spine", "LeftLeg", "RightLeg")]
    return next(b for b in paths[0] if all(b in p for p in paths[1:]))


def split_legs(mesh, chains, knees):
    """Replace each hip-to-foot leg chain by thigh, shin and foot chains, split at the knee and the foot."""
    out = []
    for name, start, end in chains:
        if name not in knees:
            out.append((name, start, end))
            continue
        path = list(reversed(ancestors(mesh, end)))
        path = path[path.index(start):]
        knee = path.index(knees[name])
        if not 0 < knee < len(path) - 1:
            raise RuntimeError("knee %s is not inside leg %s -> %s" % (knees[name], start, end))
        side = name[:-len("Leg")]
        out += [(side + "Thigh", start, path[knee - 1]), (side + "Shin", path[knee], path[-2]),
                (side + "Foot", end, end)]
    return out


def make_split_source(source_rig, source_mesh):
    """IK_Clukay416 with each leg as thigh, shin and foot chains, created once.

    IK_Clukay416 itself stays as N2 configured it: the twelve MMD retargeters use its single leg chains.
    """
    rig = EAL.load_asset(SPLIT_SOURCE_RIG)
    if rig is not None and sorted(rig_chains(rig)) == sorted(SPLIT_CHAIN_NAMES):
        return rig
    controller = unreal.IKRigController.get_controller(source_rig)
    chains = [(n, str(controller.get_retarget_chain_start_bone(n)), str(controller.get_retarget_chain_end_bone(n)))
              for n in CHAIN_NAMES]
    knees = {}
    for name, start, end in chains:
        if name in ("LeftLeg", "RightLeg"):
            path = list(reversed(ancestors(source_mesh, end)))
            path = path[path.index(start):]
            if len(path) != 3:
                raise RuntimeError("source leg %s is %s, expected hip, knee, foot" % (name, path))
            knees[name] = path[1]
    package_path, name = SPLIT_SOURCE_RIG.rsplit("/", 1)
    return make_rig(package_path, name, source_mesh, str(controller.get_retarget_root()),
                    split_legs(source_mesh, chains, knees))


def inv_via(row, chain):
    return ((row or {}).get("chains", {}).get(chain) or {}).get("via", "humanoid")


def make_rig(package_path, name, mesh, root_bone, chains):
    """Reconfigure one IK Rig in place, creating it the first time (see n2_build_retarget.make_rig)."""
    full = "%s/%s" % (package_path, name)
    rig = EAL.load_asset(full)
    if rig is None:
        if not EAL.does_directory_exist(package_path):
            EAL.make_directory(package_path)
        rig = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, package_path, unreal.IKRigDefinition,
                                                                     unreal.IKRigDefinitionFactory())
        if rig is None:
            raise RuntimeError("could not create IK Rig " + full)
    controller = unreal.IKRigController.get_controller(rig)
    current = controller.get_skeletal_mesh()
    if current is None or current.get_path_name() != mesh.get_path_name():
        if not controller.set_skeletal_mesh(mesh):
            raise RuntimeError("IK Rig %s rejected mesh %s" % (full, mesh.get_path_name()))
    controller.set_retarget_root(root_bone)
    for chain in rig_chains(rig):
        controller.remove_retarget_chain(chain)
    for chain, start_bone, end_bone in chains:
        created = controller.add_retarget_chain(chain, start_bone, end_bone, "")
        if str(created) in ("None", ""):
            raise RuntimeError("chain %s rejected on %s (%s -> %s)" % (chain, full, start_bone, end_bone))
    EAL.save_loaded_asset(rig, False)
    return rig


def rig_chains(rig):
    controller = unreal.IKRigController.get_controller(rig)
    return [str(chain.get_editor_property("chain_name")) for chain in (controller.get_retarget_chains() or [])]


def make_retargeter(package_path, name, source_rig, target_rig, source_mesh, target_mesh):
    """Configure one IK Retargeter in place, creating it the first time (see n2_build_retarget.make_retargeter)."""
    full = "%s/%s" % (package_path, name)
    retargeter = EAL.load_asset(full)
    if retargeter is None:
        retargeter = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, package_path, unreal.IKRetargeter,
                                                                            unreal.IKRetargetFactory())
        if retargeter is None:
            raise RuntimeError("could not create IK Retargeter " + full)
    controller = unreal.IKRetargeterController.get_controller(retargeter)
    controller.remove_all_ops()
    controller.set_ik_rig(unreal.RetargetSourceOrTarget.SOURCE, source_rig)
    controller.set_ik_rig(unreal.RetargetSourceOrTarget.TARGET, target_rig)
    controller.set_preview_mesh(unreal.RetargetSourceOrTarget.SOURCE, source_mesh)
    controller.set_preview_mesh(unreal.RetargetSourceOrTarget.TARGET, target_mesh)
    controller.add_default_ops()
    controller.auto_map_chains(unreal.AutoMapChainType.EXACT, True)
    controller.auto_align_all_bones(unreal.RetargetSourceOrTarget.TARGET, unreal.RetargetAutoAlignMethod.CHAIN_TO_CHAIN)
    EAL.save_loaded_asset(retargeter, False)
    return retargeter


def source_animations(only=None):
    data = []
    for path in sorted(EAL.list_assets(SOURCE_ANIM_DIR, recursive=False, include_folder=False)):
        object_path = path.split(".")[0]
        name = object_path.rsplit("/", 1)[-1]
        if only and name not in only:
            continue
        found = EAL.find_asset_data(object_path)
        if found.is_valid():
            data.append(found)
    return data


def run_batch(retargeter, source_mesh, target_mesh, anim_data, target_path):
    inputs = unreal.IKRetargetBatchOperationInputs()
    for key, value in (("assets_to_retarget", anim_data), ("source_mesh", source_mesh), ("target_mesh", target_mesh),
                       ("ik_retarget_asset", retargeter), ("search", ""), ("replace", ""), ("prefix", ""),
                       ("suffix", ""), ("target_path", target_path), ("use_source_path", False),
                       ("include_referenced_assets", True), ("overwrite_existing_files", True),
                       ("retain_additive_flags", True)):
        inputs.set_editor_property(key, value)
    return list(unreal.IKRetargetBatchOperation.run_batch_retarget(inputs) or [])


def build_one(cid, source_rig, source_mesh, anim_data, inventory_row):
    entry = {"characterId": cid}
    mesh = EAL.load_asset("%s/%s/SK_VRM_%s" % (VRM_ROOT, cid, cid))
    if mesh is None:
        raise RuntimeError("missing target mesh (run ue_import_vrm.py)")
    bones = [str(n) for n in unreal.AnimPoseExtensions.get_bone_names(
        unreal.AnimPoseExtensions.get_reference_pose(mesh.get_editor_property("skeleton")))]
    hips, chains, legs_via, knees = target_chains(cid, bones, inventory_row)
    root = retarget_root(mesh, chains)
    chains = split_legs(mesh, chains, knees)
    retarget_dir = "%s/%s/Retarget" % (VRM_ROOT, cid)
    target_rig = make_rig(retarget_dir, "IK_VRM_%s" % cid, mesh, root, chains)
    retargeter = make_retargeter(retarget_dir, "RTG_%s" % cid, source_rig, target_rig, source_mesh, mesh)
    entry.update({"rig": "%s/IK_VRM_%s" % (retarget_dir, cid), "retargeter": "%s/RTG_%s" % (retarget_dir, cid),
                  "root": root, "humanoidHips": hips, "chains": {c: [s, e] for c, s, e in chains}, "legsVia": legs_via,
                  "rigChains": rig_chains(target_rig)})
    anim_dir = "%s/%s/Anim" % (VRM_ROOT, cid)
    if EAL.does_directory_exist(anim_dir) and EAL.list_assets(anim_dir, recursive=False, include_folder=False):
        # Overwriting makes the batch force-delete every old clip on its own (a GC and reference scan each,
        # ~3.5 s per clip, 2 min per character); one directory delete does them together.  Nothing but the
        # presenter's soft paths refers to these clips, and a crash after this line only leaves the character
        # to be rebuilt (its report row still names the old source rig).
        EAL.delete_directory(anim_dir)
    created = run_batch(retargeter, source_mesh, mesh, anim_data, anim_dir)
    entry["clips"] = len(created)
    entry["sourceRig"] = SPLIT_SOURCE_RIG
    entry["ok"] = sorted(entry["rigChains"]) == sorted(SPLIT_CHAIN_NAMES) and len(created) == len(anim_data)
    # Persist this character now: the batch leaves its packages dirty, and a later failure must not lose them.
    own = [p for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
           if p.get_name().startswith("%s/%s/" % (VRM_ROOT, cid))]
    if own:
        unreal.EditorLoadingAndSavingUtils.save_packages(own, True)
    entry["savedPackages"] = len(own)
    return entry


def main(argv):
    named = argv[argv.index("--chars") + 1].split(",") if "--chars" in argv else []
    clips = ["A_GP_" + c for c in argv[argv.index("--clips") + 1].split(",")] if "--clips" in argv else None
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else 0
    source_mesh = EAL.load_asset(SOURCE_MESH)
    source_rig = EAL.load_asset(SOURCE_RIG)
    if source_mesh is None or source_rig is None:
        raise RuntimeError("missing source mesh or rig")
    if sorted(rig_chains(source_rig)) != sorted(CHAIN_NAMES):
        raise RuntimeError("source rig chains %s; rebuild it with n2_build_retarget.py" % rig_chains(source_rig))
    source_rig = make_split_source(source_rig, source_mesh)
    anim_data = source_animations(clips)
    inventory = {r["characterId"]: r for r in json.load(open(INVENTORY, encoding="utf-8"))["rows"]}
    old = json.load(open(REPORT, encoding="utf-8")) if os.path.exists(REPORT) else {"characters": []}
    merged = {r["characterId"]: r for r in old.get("characters", [])}
    staged = sorted(d for d in os.listdir(SIDECARS) if d.startswith("char_"))
    if named:
        todo = [c for c in staged if c in named]
    else:
        todo = [c for c in staged if not (merged.get(c, {}).get("ok") and merged[c].get("clips") == len(anim_data)
                                          and merged[c].get("sourceRig") == SPLIT_SOURCE_RIG)]
    built = 0
    for cid in todo:
        if not EAL.does_asset_exist("%s/%s/SK_VRM_%s" % (VRM_ROOT, cid, cid)):
            continue
        try:
            entry = build_one(cid, source_rig, source_mesh, anim_data, inventory.get(cid))
        except Exception as error:  # noqa: BLE001 - report per character and keep going
            entry = {"characterId": cid, "ok": False, "error": str(error)}
        merged[cid] = entry
        log("%s ok=%s clips=%s legs=%s %s" % (cid, entry.get("ok"), entry.get("clips"), entry.get("legsVia"),
                                              entry.get("error", "")))
        built += 1
        # Saving renders thumbnails, and every rendered IK Rig / Retargeter keeps a ~90 MB preview scene on the GPU
        # until its renderer goes (Source/Tread/TreadEditorThumbnails.cpp, memory: tread-editor-vram-batch).
        unreal.SystemLibrary.execute_console_command(None, "Tread.FlushThumbnailScenes")
        unreal.SystemLibrary.execute_console_command(None, "obj gc")
        with open(REPORT, "w", encoding="utf-8") as handle:
            json.dump({"schema": "Tread.M4.RetargetBuild.v1", "sourceRig": SPLIT_SOURCE_RIG,
                       "sourceClips": [str(a.package_name) for a in anim_data],
                       "characters": [merged[k] for k in sorted(merged)]}, handle, ensure_ascii=False, indent=1)
        if limit and built >= limit:
            break
    rows = [merged[k] for k in sorted(merged)]
    report = {"schema": "Tread.M4.RetargetBuild.v1", "sourceRig": SPLIT_SOURCE_RIG,
              "sourceClips": [str(a.package_name) for a in anim_data], "count": len(rows),
              "ok": bool(rows) and all(r.get("ok") for r in rows), "characters": rows}
    with open(REPORT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=1)
    log("built %d now; %d characters in report, ok=%s" % (built, len(rows), report["ok"]))
    return 0


sys.exit(main(sys.argv[1:]))
