"""N2 (b): build the IK Rigs, the IK Retargeters and the retargeted GP animation set.

Editor-side (run through Tools/ue_run.py).  Everything it creates is a generated asset under
Content/Tread/Characters/<...>/Retarget or /Anim, so re-running the script rebuilds from scratch.

    python Tools/ue_run.py Tools/m4/n2_build_retarget.py [--pilot] [--chars char_101,char_102]

  --pilot        one character, three clips (Idle/Walk/Run) -- the eyeball pass before the full batch
  --chars a,b    restrict the run to these characters (default: all twelve)

Layout
  /Game/Tread/Characters/Clukay416/Retarget/IK_Clukay416          source rig   (mesh U_Char_1)
  /Game/Tread/Characters/MMD/char_1xx/Retarget/IK_MMD_char_1xx    target rig   (mesh SK_MMD_char_1xx)
  /Game/Tread/Characters/MMD/char_1xx/Retarget/RTG_char_1xx       retargeter   (source -> target)
  /Game/Tread/Characters/MMD/char_1xx/Anim/A_GP_*                 retargeted clips

Report: Saved/Reports/N2_Retarget_Build.json
"""
import json
import os
import sys

import unreal

PROJECT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
REPORT = os.path.join(PROJECT, "Saved", "Reports", "N2_Retarget_Build.json")

SOURCE_MESH = "/Game/Tread/Characters/Clukay416/416/SkeletalMeshes/U_Char_1.U_Char_1"
SOURCE_RIG = "/Game/Tread/Characters/Clukay416/Retarget/IK_Clukay416"
SOURCE_ANIM_DIR = "/Game/Tread/Characters/Clukay416/Anim/GP"
MMD_ROOT = "/Game/Tread/Characters/MMD"
CHARACTERS = ["char_%03d" % n for n in range(101, 113)]
PILOT_CLIPS = ["A_GP_Idle", "A_GP_Walk", "A_GP_Run"]

# chain -> (source start, source end, MMD start, MMD end).  The source VRM is a translated MMD
# skeleton, but NOT bone-for-bone in the torso: its "4__joint_Waist" is a dead-end branch under
# Centre/Groove and the real pelvis is "5_joint_HipMaster", which hangs directly off the root bone
# next to it.  MMD's hip is "腰" (waist) under "センター"; the two play the same role, so the
# retarget root pairs them and every chain below is a one-to-one counterpart.  The UE FBX importer
# also rewrote the MMD ".L"/".R" suffixes to "_L"/"_R" (see Saved/Reports/N2_MMD_Bones.json).
CHAINS = [
    ("Spine", "6_joint_Torso", "7_joint_Torso2", "上半身", "上半身2"),
    ("Neck", "8_joint_Neck", "8_joint_Neck", "首", "首"),
    ("Head", "9_joint_Head", "9_joint_Head", "頭", "頭"),
    ("LeftArm", "30_joint_LeftShoulder", "42_joint_LeftWrist", "肩_L", "手首_L"),
    ("RightArm", "45_joint_RightShoulder", "57_joint_RightWrist", "肩_R", "手首_R"),
    # The legs run on the MMD "D" bones on both sides.  Every one of the 12 MMD meshes skins its legs
    # to 足D/ひざD/足首D only (足/ひざ/足首 carry no weights; in MMD the D set follows them through
    # append-rotation, which UE does not evaluate), and the GP clips walk the source's D bones while
    # its plain leg bones barely move.  A first build drove 足 -> 足首: the bones moved, the skinned
    # legs stood straight through every walk and kneel (2026-10-12, N2_AnimPoseSweep legs check).
    ("LeftLeg", "243_joint_LeftHipD", "245_joint_LeftFootD", "足D_L", "足首D_L"),
    ("RightLeg", "239_joint_RightHipD", "241_joint_RightFootD", "足D_R", "足首D_R"),
]
SOURCE_ROOT = "5_joint_HipMaster"
MMD_ROOT_BONE = "センター"

report = {"schema": "Tread.N2.RetargetBuild.v1", "sourceRig": None, "characters": [], "errors": []}


def log(message):
    unreal.log("N2: " + message)
    print("N2 " + message)


def asset_tools():
    return unreal.AssetToolsHelpers.get_asset_tools()


def make_rig(package_path, name, mesh, root_bone, chains):
    """Reconfigure one IK Rig in place, creating it the first time.

    NOT delete-and-recreate.  That is what crashed the editor on 2026-10-11: the IK Retargeter still
    held ops pointing at the deleted rig, and the next IK Rig call dereferenced the freed object
    (EXCEPTION_ACCESS_VIOLATION inside UnrealEditor-IKRig, editor gone).  Reusing the asset keeps every
    reference valid, and unlike the retargeter's chain mapping the rig's chain list reads back fine,
    so it is also the one piece of this step that can be checked afterwards.
    """
    full = "%s/%s" % (package_path, name)
    rig = unreal.EditorAssetLibrary.load_asset(full)
    if rig is None:
        if not unreal.EditorAssetLibrary.does_directory_exist(package_path):
            unreal.EditorAssetLibrary.make_directory(package_path)
        rig = asset_tools().create_asset(name, package_path, unreal.IKRigDefinition, unreal.IKRigDefinitionFactory())
        if rig is None:
            raise RuntimeError("could not create IK Rig " + full)
    controller = unreal.IKRigController.get_controller(rig)
    current = controller.get_skeletal_mesh()
    if current is None or current.get_path_name() != mesh.get_path_name():
        if not controller.set_skeletal_mesh(mesh):
            raise RuntimeError("IK Rig %s rejected mesh %s" % (full, mesh.get_path_name()))
    controller.set_retarget_root(root_bone)
    existing = [str(chain.get_editor_property("chain_name")) for chain in (controller.get_retarget_chains() or [])]
    for chain in existing:
        controller.remove_retarget_chain(chain)
    for chain, start_bone, end_bone in chains:
        created = controller.add_retarget_chain(chain, start_bone, end_bone, "")
        # A rejected chain comes back as NAME_None, which is still a truthy Python object.
        if str(created) in ("None", ""):
            raise RuntimeError("chain %s rejected on %s (%s -> %s)" % (chain, full, start_bone, end_bone))
    unreal.EditorAssetLibrary.save_loaded_asset(rig, False)
    log("%s: chains %s (replaced %s)" % (name, [c[0] for c in chains], existing))
    return rig


def rig_chains(rig):
    """The chain names this rig actually carries.  Blank names mean the read failed, not an empty rig."""
    controller = unreal.IKRigController.get_controller(rig)
    return [str(chain.get_editor_property("chain_name")) for chain in (controller.get_retarget_chains() or [])]


def make_retargeter(package_path, name, source_rig, target_rig, source_mesh, target_mesh):
    """Configure one character's IK Retargeter, creating it the first time.

    Reconfigured in place rather than deleted and recreated: an IK Retargeter this editor process has
    ever loaded keeps its .uasset file locked on Windows, so delete_loaded_asset() reports success
    while the file stays on disk, the asset registry keeps listing it, and the next create_asset()
    with that name returns None.  Clearing the op stack and re-adding the defaults is equivalent.
    """
    full = "%s/%s" % (package_path, name)
    retargeter = unreal.EditorAssetLibrary.load_asset(full)
    if retargeter is None:
        if not unreal.EditorAssetLibrary.does_directory_exist(package_path):
            unreal.EditorAssetLibrary.make_directory(package_path)
        retargeter = asset_tools().create_asset(name, package_path, unreal.IKRetargeter, unreal.IKRetargetFactory())
        if retargeter is None:
            raise RuntimeError("could not create IK Retargeter " + full)
    controller = unreal.IKRetargeterController.get_controller(retargeter)
    controller.remove_all_ops()
    controller.set_ik_rig(unreal.RetargetSourceOrTarget.SOURCE, source_rig)
    controller.set_ik_rig(unreal.RetargetSourceOrTarget.TARGET, target_rig)
    controller.set_preview_mesh(unreal.RetargetSourceOrTarget.SOURCE, source_mesh)
    controller.set_preview_mesh(unreal.RetargetSourceOrTarget.TARGET, target_mesh)
    controller.add_default_ops()
    # Both rigs declare the same chain names, so an exact-name map is all that is needed.
    controller.auto_map_chains(unreal.AutoMapChainType.EXACT, True)
    # The two skeletons do not bind in the same pose: the VRM hero is a T-pose, an mmd_tools import is
    # an A-pose.  Without aligning them the FK op rotates every target chain in a frame that is offset
    # by that difference, which threw the arms about 100 degrees the wrong way -- measured on char_101,
    # the wrist sat 26 cm above the shoulder instead of 46 cm below it.  Aligning the target's retarget
    # pose chain-to-chain brings the idle to 23 degrees from vertical against the source's 20.
    controller.auto_align_all_bones(unreal.RetargetSourceOrTarget.TARGET,
                                    unreal.RetargetAutoAlignMethod.CHAIN_TO_CHAIN)
    unreal.EditorAssetLibrary.save_loaded_asset(retargeter, False)
    return retargeter


def source_animations(only=None):
    data = []
    for path in sorted(unreal.EditorAssetLibrary.list_assets(SOURCE_ANIM_DIR, recursive=False, include_folder=False)):
        object_path = path.split(".")[0]
        name = object_path.rsplit("/", 1)[-1]
        if only and name not in only:
            continue
        found = unreal.EditorAssetLibrary.find_asset_data(object_path)
        if found.is_valid():
            data.append(found)
    return data


def run_batch(retargeter, source_mesh, target_mesh, anim_data, target_path):
    inputs = unreal.IKRetargetBatchOperationInputs()
    inputs.set_editor_property("assets_to_retarget", anim_data)
    inputs.set_editor_property("source_mesh", source_mesh)
    inputs.set_editor_property("target_mesh", target_mesh)
    inputs.set_editor_property("ik_retarget_asset", retargeter)
    inputs.set_editor_property("search", "")
    inputs.set_editor_property("replace", "")
    inputs.set_editor_property("prefix", "")
    inputs.set_editor_property("suffix", "")
    inputs.set_editor_property("target_path", target_path)
    inputs.set_editor_property("use_source_path", False)
    inputs.set_editor_property("include_referenced_assets", True)
    inputs.set_editor_property("overwrite_existing_files", True)
    inputs.set_editor_property("retain_additive_flags", True)
    return list(unreal.IKRetargetBatchOperation.run_batch_retarget(inputs) or [])


def main(argv):
    pilot = "--pilot" in argv
    characters = CHARACTERS
    if "--chars" in argv:
        characters = argv[argv.index("--chars") + 1].split(",")
    if pilot:
        characters = characters[:1]

    source_mesh = unreal.EditorAssetLibrary.load_asset(SOURCE_MESH)
    if source_mesh is None:
        raise RuntimeError("missing source mesh " + SOURCE_MESH)
    source_rig = make_rig("/Game/Tread/Characters/Clukay416/Retarget", "IK_Clukay416",
                          source_mesh, SOURCE_ROOT, [(chain, start, end) for chain, start, end, _, _ in CHAINS])
    report["sourceRig"] = {"asset": SOURCE_RIG, "mesh": SOURCE_MESH, "root": SOURCE_ROOT,
                           "chains": len(CHAINS)}
    log("source rig built: %d chains, root %s" % (len(CHAINS), SOURCE_ROOT))

    anim_data = source_animations(PILOT_CLIPS if pilot else None)
    if not anim_data:
        raise RuntimeError("no source animations under " + SOURCE_ANIM_DIR)
    log("source clips: %d" % len(anim_data))

    for character in characters:
        entry = {"characterId": character}
        try:
            target_mesh_path = "%s/%s/SK_MMD_%s" % (MMD_ROOT, character, character)
            target_mesh = unreal.EditorAssetLibrary.load_asset(target_mesh_path)
            if target_mesh is None:
                raise RuntimeError("missing target mesh " + target_mesh_path)
            retarget_dir = "%s/%s/Retarget" % (MMD_ROOT, character)
            target_rig = make_rig(retarget_dir, "IK_MMD_%s" % character, target_mesh, MMD_ROOT_BONE,
                                  [(chain, start, end) for chain, _, _, start, end in CHAINS])
            retargeter = make_retargeter(retarget_dir, "RTG_%s" % character, source_rig, target_rig,
                                         source_mesh, target_mesh)
            entry["rig"] = "%s/IK_MMD_%s" % (retarget_dir, character)
            entry["retargeter"] = "%s/RTG_%s" % (retarget_dir, character)
            # The target rig's chains DO read back, so record them: a rig missing an arm chain would
            # retarget without complaint and simply leave that limb alone.
            entry["rigChains"] = rig_chains(target_rig)
            rig_ok = sorted(entry["rigChains"]) == sorted(c for c, _, _, _, _ in CHAINS)
            # The retargeter's own chain mapping does not read back on UE 5.8: get_all_chain_settings()
            # returns an empty array and get_retarget_chain_settings() a blank struct for every name,
            # mapped or not, while auto_map_chains() returns nothing.  An earlier version printed that
            # empty result as chainMapping: [] and still called the run ok, which said nothing at all.
            entry["chainMapping"] = None
            entry["chainMappingReadable"] = False
            target_path = "%s/%s/Anim" % (MMD_ROOT, character)
            created = run_batch(retargeter, source_mesh, target_mesh, anim_data, target_path)
            entry["clips"] = len(created)
            entry["clipPaths"] = sorted(str(a.package_name) for a in created)
            entry["ok"] = rig_ok and len(created) == len(anim_data)
            log("%s: rig chains %s clips %d/%d -> %s" %
                (character, entry["rigChains"], len(created), len(anim_data), target_path))
        except Exception as error:  # noqa: BLE001 - report per character and keep going
            entry["ok"] = False
            entry["error"] = str(error)
            report["errors"].append("%s: %s" % (character, error))
            log("%s: ERROR %s" % (character, error))
        report["characters"].append(entry)

    report["pilot"] = pilot
    report["sourceClips"] = [str(a.package_name) for a in anim_data]
    report["ok"] = bool(report["characters"]) and all(c.get("ok") for c in report["characters"])
    # Persist the clips this step produced.  The batch writes the packages but leaves them dirty, and a
    # dirty content package blocks the separate map switch every PIE check starts with.
    own = [p for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
           if p.get_name().startswith(MMD_ROOT)]
    if own:
        unreal.EditorLoadingAndSavingUtils.save_packages(own, True)
    report["savedPackages"] = len(own)
    log("saved %d packages under %s" % (len(own), MMD_ROOT))
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=1)
    log("report %s ok=%s" % (REPORT, report["ok"]))
    return 0 if report["ok"] else 1


sys.exit(main(sys.argv[1:]))
