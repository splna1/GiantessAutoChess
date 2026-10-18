"""M4 avatar capture (editor-side, Tools/ue_run.py): chest-up screenshots of the 112 character 3D models.

The shop / bench / roster avatar of a character is a screenshot of its own model (owner's definition, 2026-10-14);
the PNG illustration is only the click-to-open detail image and is never cropped into an avatar.

Why a simulate session: a skeletal mesh in the plain editor world never evaluates its animation (the bones stay in the
reference T pose), so the poses are staged in the studio level and shot inside "Simulate" (editor_play_simulate), where
the actors tick.  Tools/m4/avatar_capture_driver.py runs the whole sequence per batch from the host.

Every phase is its own remote call (memory: tread-editor-python-map-switch: a map switch never shares a call with
actor references; memory: tread-editor-vram-batch: ~10 characters per batch, FlushThumbnailScenes + editor_release gc
between batches).

  studio                  guard dirty packages, remember the current map, create / load /Game/Tread/Dev/AvatarStudio
  setup                   (studio loaded) backdrop dome, lights, sky light, capture rig; saves the studio level
  stage  --ids a,b | --batch N [--size 10]
                          spawn the batch models in a row and give each its Idle pose (frozen at one frame)
  sim                     start the Simulate session (own call)
  shoot                   (in simulate) frame every staged model from its bones, capture a 1024 px render target,
                          export Saved/Staging/avatars_raw/<id>.png and merge the framing numbers into the report
  endsim                  end the Simulate session
  clear                   destroy the staged actors and save the (empty) studio level
  restore                 save the studio level if dirty, reload the map that studio remembered

Per-character framing overrides: Saved/Reports/M4_Avatar_Overrides.json
  {id: {"yawOffset": deg, "top": cm, "bottom": cm, "shiftX": cm, "shiftZ": cm, "scale": ratio, "time": s}}
Report: Saved/Reports/M4_Avatar_Capture_Report.json (merged per character).
Everything printed here is ASCII (the editor console is GBK).
"""
import json
import math
import os
import sys

import unreal

PROJECT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
REPORTS = os.path.join(PROJECT, "Saved", "Reports")
RAW_DIR = os.path.join(PROJECT, "Saved", "Staging", "avatars_raw")
STATE = os.path.join(REPORTS, "M4_Avatar_state.json")
REPORT = os.path.join(REPORTS, "M4_Avatar_Capture_Report.json")
OVERRIDES = os.path.join(REPORTS, "M4_Avatar_Overrides.json")
ROSTER = os.path.join(PROJECT, "Content", "Data", "Generated", "CharacterRosterMap.json")

STUDIO_DIR = "/Game/Tread/Dev"
STUDIO_MAP = STUDIO_DIR + "/AvatarStudio"
BACKDROP_MAT = STUDIO_DIR + "/M_AvatarBackdrop"
HERO_ID = "char_001"
HERO_FACE = "/Game/Tread/Characters/Clukay416/416/SkeletalMeshes/U_Char_1"
HERO_IDLE = "/Game/Tread/Characters/Clukay416/Anim/GP/A_GP_Idle"

# ---- capture constants: identical for every character (uniform lighting, FOV, background, resolution) ----------
RT_SIZE = 1024                 # rendered at 1024, downsampled to 512 on the host (supersampling instead of TAA)
FOV = 20.0                     # degrees; a narrow lens keeps the face free of perspective distortion
YAW_OFFSET = 16.0              # slight 3/4 view: the model turns by this many degrees away from the camera axis
BACKDROP_LINEAR = (0.075, 0.095, 0.135)  # emissive colour of the dome: the same flat slate behind every avatar
EXPOSURE_BIAS = 10.0           # manual exposure (the lights below are tuned for it)
SPACING = 420.0                # cm between staged models on the X axis (no shadow reaches the neighbour)
BATCH_SIZE = 10
IDLE_TIME = 1.5                # seconds into A_GP_Idle: arms down, relaxed
TOP_MARGIN = 0.07              # fraction of the frame kept free above the head top
CHEST_DROP = 0.12              # crop ends this fraction of (head - chest) below the chest bone: mid-chest
HEAD_CAP = 1.0                 # head top never above head bone + HEAD_CAP * (head - chest): ignores raised props

EAL = unreal.EditorAssetLibrary

# Bone naming schemes of the imported models (head, neck, chest candidates, left / right shoulder).  "suffix" schemes match
# the end of the name (the hero and some VRMs carry numbered "9_joint_Head" names), the others are exact.
SCHEMES = [
    ("mmd", False, ["頭"], ["首"], ["上半身2", "上半身"], ["肩_L"], ["肩_R"]),
    ("joint", True, ["joint_Head"], ["joint_Neck"], ["joint_Torso2", "joint_Torso"], ["joint_LeftShoulder"], ["joint_RightShoulder"]),
    ("jbip", False, ["J_Bip_C_Head"], ["J_Bip_C_Neck"], ["J_Bip_C_UpperChest", "J_Bip_C_Chest"], ["J_Bip_L_Shoulder"], ["J_Bip_R_Shoulder"]),
    ("bip", False, ["Bip001Head"], ["Bip001Neck"], ["Bip001Spine2", "Bip001Spine1"], ["Bip001LClavicle"], ["Bip001RClavicle"]),
    ("bip-dash", False, ["Bip001-Head"], ["Bip001-Neck"], ["Bip001-Spine2", "Bip001-Spine1"], ["Bip001-L-Clavicle"], ["Bip001-R-Clavicle"]),
    ("m-suffix", False, ["Head_M"], ["Neck_M"], ["Chest_M", "Spine2_M"], ["Shoulder_L"], ["Shoulder_R"]),
    ("lower", False, ["head"], ["neck"], ["chest", "spine"], ["shoulder_L"], ["shoulder_R"]),
    ("capital", False, ["Head"], ["Neck"], ["Chest", "Spine"], ["Left-shoulder"], ["Right-shoulder"]),
    ("hyphen", False, ["head-neck-upper"], ["head-neck-lower"], ["spine-upper", "spine-abs"], ["arm-left-shoulder-1"], ["arm-right-shoulder-1"]),
]


def read(path, default=None):
    if not os.path.exists(path):
        return {} if default is None else default
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def write(path, doc):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, ensure_ascii=True, indent=1)


def roster():
    return read(ROSTER).get("characters", [])


def rot(yaw=0.0, pitch=0.0, roll=0.0):
    # unreal.Rotator's positional order is (roll, pitch, yaw): always pass by name.
    return unreal.Rotator(roll=roll, pitch=pitch, yaw=yaw)


def game_world():
    sub = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    return sub.get_game_world() if sub else None


def editor_world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def dirty_packages():
    return (unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
            + unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())


def current_map():
    return editor_world().get_path_name().split(".")[0]


def in_studio():
    return current_map() == STUDIO_MAP


def level_subsystem():
    return unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)


def batch_ids(args):
    rows = [r["characterId"] for r in roster()]
    if "--ids" in args:
        return [i for i in args[args.index("--ids") + 1].split(",") if i]
    size = int(args[args.index("--size") + 1]) if "--size" in args else BATCH_SIZE
    n = int(args[args.index("--batch") + 1])
    return rows[n * size:(n + 1) * size]


def row_of(cid):
    for r in roster():
        if r["characterId"] == cid:
            return r
    raise RuntimeError("unknown character " + cid)


def asset_dir(row):
    return row["meshAsset"].rsplit("/", 1)[0]


def idle_path(row):
    return HERO_IDLE if row["modelSet"] == "Hero" else asset_dir(row) + "/Anim/A_GP_Idle"


def find_bones(names):
    """(scheme, {head, neck, chest, lsh, rsh}) of the first naming scheme whose bones all exist in the skeleton."""
    for scheme, suffix, head, neck, chest, lsh, rsh in SCHEMES:
        found = {}
        for key, wanted in (("head", head), ("neck", neck), ("chest", chest), ("lsh", lsh), ("rsh", rsh)):
            hit = None
            for want in wanted:
                hit = next((n for n in names if (n.endswith(want) if suffix else n == want)), None)
                if hit:
                    break
            found[key] = hit
        if all(found.values()):
            return scheme, found
    return None, {}


# ------------------------------------------------------------------------------------------------ studio / restore
def phase_studio():
    if game_world():
        raise RuntimeError("a PIE / simulate session is running")
    state = read(STATE)
    if in_studio():
        print("AVATAR studio already loaded (previous=%s)" % state.get("previousMap"))
        return
    dirty = dirty_packages()
    if dirty:
        raise RuntimeError("dirty packages present, refusing to switch map: %s" % [p.get_name() for p in dirty][:10])
    state["previousMap"] = current_map()
    write(STATE, state)
    level = level_subsystem()
    ok = level.load_level(STUDIO_MAP) if EAL.does_asset_exist(STUDIO_MAP) else level.new_level(STUDIO_MAP)
    if not ok:
        raise RuntimeError("failed to create / load " + STUDIO_MAP)
    print("AVATAR studio previous=%s now=%s" % (state["previousMap"], STUDIO_MAP))


def phase_restore():
    if game_world():
        raise RuntimeError("end the simulate session first")
    previous = read(STATE).get("previousMap", "")
    if not previous:
        raise RuntimeError("no remembered map")
    if in_studio():
        level_subsystem().save_current_level()
        left = dirty_packages()
        if left:
            unreal.EditorLoadingAndSavingUtils.save_packages(left, True)
    if not level_subsystem().load_level(previous):
        raise RuntimeError("failed to restore " + previous)
    print("AVATAR restore %s" % previous)


# ------------------------------------------------------------------------------------------------ setup
def spawn(cls, loc=(0, 0, 0), rotation=None, label=None):
    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(cls, unreal.Vector(*loc), rotation or rot())
    if label:
        actor.set_actor_label(label)
    return actor


def ensure_backdrop_material():
    mat = EAL.load_asset(BACKDROP_MAT) if EAL.does_asset_exist(BACKDROP_MAT) else None
    if mat is None:
        mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset("M_AvatarBackdrop", STUDIO_DIR, unreal.Material,
                                                                      unreal.MaterialFactoryNew())
    mel = unreal.MaterialEditingLibrary
    mel.delete_all_material_expressions(mat)
    mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    mat.set_editor_property("two_sided", True)
    color = mel.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector, -300, 0)
    color.set_editor_property("constant", unreal.LinearColor(BACKDROP_LINEAR[0], BACKDROP_LINEAR[1], BACKDROP_LINEAR[2], 1.0))
    mel.connect_material_property(color, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(mat)
    EAL.save_loaded_asset(mat)
    return mat


def phase_setup():
    if not in_studio():
        raise RuntimeError("run the studio phase first (current map %s)" % current_map())
    world = editor_world()
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor):
        if actor.get_actor_label().startswith(("AV_", "AVT_")):
            actor.destroy_actor()
    mat = ensure_backdrop_material()
    # The simulate session must not start the game's own GameMode (HUD, match controller).
    world.get_world_settings().set_editor_property("default_game_mode", unreal.GameModeBase)
    # Backdrop dome: one flat unlit colour everywhere (the sky light captures it as ambient light too).
    dome = spawn(unreal.StaticMeshActor, (0, 0, 0), None, "AV_Backdrop")
    comp = dome.static_mesh_component
    comp.set_editor_property("static_mesh", EAL.load_asset("/Engine/BasicShapes/Sphere"))
    dome.set_actor_scale3d(unreal.Vector(300, 300, 300))
    comp.set_material(0, mat)
    comp.set_editor_property("cast_shadow", False)
    # The camera looks along +Y at a face that looks along -Y.  Directional lights travel along their forward vector:
    # key from front-left above (shadows on), fill from front-right, rim from behind.
    for label, intensity, pitch, yaw, shadow in (("AV_Key", 6.5, -34.0, 55.0, True), ("AV_Fill", 2.4, -14.0, 125.0, False),
                                                 ("AV_Rim", 3.0, -18.0, -90.0, False)):
        light = spawn(unreal.DirectionalLight, (0, 0, 600), rot(yaw=yaw, pitch=pitch), label)
        light.root_component.set_mobility(unreal.ComponentMobility.MOVABLE)
        lc = light.get_component_by_class(unreal.DirectionalLightComponent)
        lc.set_editor_property("intensity", intensity)
        lc.set_editor_property("cast_shadows", shadow)
        lc.set_editor_property("light_color", unreal.Color(255, 250, 244, 255))
    sky = spawn(unreal.SkyLight, (0, 0, 300), None, "AV_Sky")
    sky.root_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    sc = sky.get_component_by_class(unreal.SkyLightComponent)
    sc.set_editor_property("source_type", unreal.SkyLightSourceType.SLS_CAPTURED_SCENE)
    sc.set_editor_property("real_time_capture", True)
    sc.set_editor_property("intensity", 1.0)
    rig = spawn(unreal.SceneCapture2D, (0, -150, 130), rot(yaw=90), "AV_Capture")
    cc = rig.capture_component2d
    cc.set_editor_property("capture_every_frame", False)
    cc.set_editor_property("capture_on_movement", False)
    cc.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
    cc.set_editor_property("fov_angle", FOV)
    cc.set_editor_property("always_persist_rendering_state", True)
    level_subsystem().save_current_level()
    print("AVATAR setup done")


# ------------------------------------------------------------------------------------------------ stage
def load_or_none(path):
    try:
        return EAL.load_asset(path)
    except Exception:  # noqa: BLE001
        return None


def stage_one(index, row, overrides):
    cid = row["characterId"]
    hero = row["modelSet"] == "Hero"
    mesh = load_or_none(row["meshAsset"])
    anim = load_or_none(idle_path(row))
    if mesh is None or anim is None:
        return {"status": "FAIL", "error": "mesh or idle missing", "mesh": row["meshAsset"], "idle": idle_path(row)}
    time = float(overrides.get(cid, {}).get("time", IDLE_TIME))
    time = min(time, max(0.0, anim.get_play_length() - 0.05))
    actor = spawn(unreal.SkeletalMeshActor, (index * SPACING, 0, 0), None, "AVT_" + cid)
    comp = actor.skeletal_mesh_component
    comp.set_skeletal_mesh_asset(mesh)
    comp.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
    if overrides.get(cid, {}).get("pose") == "ref":
        pass  # per-character escape hatch: reference (T) pose, used when the Idle clip breaks the model
    else:
        comp.override_animation_data(anim, True, False, time, 1.0)
    comp.set_editor_property("visibility_based_anim_tick_option",
                             unreal.VisibilityBasedAnimTickOption.ALWAYS_TICK_POSE_AND_REFRESH_BONES)
    if hero:
        face_mesh = load_or_none(HERO_FACE)
        face = spawn(unreal.SkeletalMeshActor, (index * SPACING, 0, 0), None, "AVT_" + cid + "_face")
        fc = face.skeletal_mesh_component
        fc.set_skeletal_mesh_asset(face_mesh)
        face.attach_to_actor(actor, "", unreal.AttachmentRule.KEEP_WORLD, unreal.AttachmentRule.KEEP_WORLD,
                             unreal.AttachmentRule.KEEP_WORLD, False)
        fc.set_leader_pose_component(comp)
    return {"status": "STAGED", "time": time, "slot": index}


def phase_stage(args):
    if not in_studio() or game_world():
        raise RuntimeError("studio must be loaded and no simulate session running")
    ids = batch_ids(args)
    overrides = read(OVERRIDES)
    report = read(REPORT)
    staged = {}
    for index, cid in enumerate(ids):
        result = stage_one(index, row_of(cid), overrides)
        staged[cid] = result
        if result["status"] == "FAIL":
            report[cid] = dict(report.get(cid, {}), id=cid, **result)
    write(REPORT, report)
    state = read(STATE)
    state["staged"] = staged
    write(STATE, state)
    print("AVATAR staged %s" % ",".join(ids))


def phase_sim():
    if game_world():
        print("AVATAR simulate already running")
        return
    level_subsystem().editor_play_simulate()
    print("AVATAR simulate requested")


def phase_endsim():
    level_subsystem().editor_request_end_play()
    print("AVATAR end simulate requested")


def phase_clear():
    if game_world():
        raise RuntimeError("end the simulate session first")
    world = editor_world()
    n = 0
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.SkeletalMeshActor):
        if actor.get_actor_label().startswith("AVT_"):
            actor.destroy_actor()
            n += 1
    level_subsystem().save_current_level()
    state = read(STATE)
    state["staged"] = {}
    write(STATE, state)
    print("AVATAR cleared %d actors" % n)


# ------------------------------------------------------------------------------------------------ shoot
def v3(t):
    return (t.translation.x, t.translation.y, t.translation.z)


def rot_z(p, origin, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    dx, dy = p[0] - origin[0], p[1] - origin[1]
    return (origin[0] + c * dx - s * dy, origin[1] + s * dx + c * dy, p[2])


def actor_top(actor):
    origin, extent = actor.get_actor_bounds(False)
    return origin.z + extent.z


def make_target(world, cc):
    rt = unreal.RenderingLibrary.create_render_target2d(world, RT_SIZE, RT_SIZE,
                                                        unreal.TextureRenderTargetFormat.RTF_RGBA8_SRGB)
    cc.set_editor_property("texture_target", rt)
    pps = cc.get_editor_property("post_process_settings")
    pps.set_editor_property("override_auto_exposure_method", True)
    pps.set_editor_property("auto_exposure_method", unreal.AutoExposureMethod.AEM_MANUAL)
    pps.set_editor_property("override_auto_exposure_bias", True)
    pps.set_editor_property("auto_exposure_bias", EXPOSURE_BIAS)
    pps.set_editor_property("override_bloom_intensity", True)
    pps.set_editor_property("bloom_intensity", 0.0)
    pps.set_editor_property("override_vignette_intensity", True)
    pps.set_editor_property("vignette_intensity", 0.0)
    pps.set_editor_property("override_film_grain_intensity", True)
    pps.set_editor_property("film_grain_intensity", 0.0)
    pps.set_editor_property("override_motion_blur_amount", True)
    pps.set_editor_property("motion_blur_amount", 0.0)
    cc.set_editor_property("post_process_settings", pps)
    cc.set_editor_property("post_process_blend_weight", 1.0)
    return rt


def phase_shoot(args):
    world = game_world()
    if not world:
        raise RuntimeError("no simulate session (run sim, wait a few seconds)")
    overrides = read(OVERRIDES)
    report = read(REPORT)
    staged = read(STATE).get("staged", {})
    rig = [a for a in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.SceneCapture2D)
           if a.get_actor_label() == "AV_Capture"][0]
    cc = rig.capture_component2d
    rt = make_target(world, cc)
    os.makedirs(RAW_DIR, exist_ok=True)
    actors = {a.get_actor_label(): a for a in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.SkeletalMeshActor)}
    shot = failed = 0
    for cid, info in staged.items():
        if info.get("status") != "STAGED":
            continue
        row = row_of(cid)
        hero = row["modelSet"] == "Hero"
        actor = actors.get("AVT_" + cid)
        entry = {"id": cid, "mesh": row["meshAsset"], "modelSet": row["modelSet"], "idle": idle_path(row),
                 "idleTime": info["time"]}
        try:
            comp = actor.skeletal_mesh_component
            names = [str(comp.get_bone_name(i)) for i in range(comp.get_num_bones())]
            scheme, used = find_bones(names)
            if not scheme:
                raise RuntimeError("no known bone naming scheme (%d bones, first: %s)" % (len(names), names[:3]))
            pos = {k: v3(comp.get_bone_transform(b)) for k, b in used.items() if b}
            ov = overrides.get(cid, {})
            origin = actor.get_actor_location()
            origin_t = (origin.x, origin.y, origin.z)
            # Face the camera: forward is the right vector (rsh - lsh) turned a quarter circle; the camera sits on -Y.
            dx, dy = pos["rsh"][0] - pos["lsh"][0], pos["rsh"][1] - pos["lsh"][1]
            facing = math.degrees(math.atan2(-dx, dy))
            delta = (-90.0 + YAW_OFFSET + float(ov.get("yawOffset", 0.0))) - facing
            delta = (delta + 180.0) % 360.0 - 180.0
            actor.set_actor_rotation(rot(yaw=delta), False)
            pos = {k: rot_z(p, origin_t, delta) for k, p in pos.items()}
            head, chest = pos["head"], pos["chest"]
            span = head[2] - chest[2]
            # Bounds can be stale right after staging: never below 0.35 spans above the head bone.
            top = max(min(actor_top(actor), head[2] + HEAD_CAP * span), head[2] + 0.35 * span)
            if hero:
                top = min(top, head[2] + HEAD_CAP * span)
            top = float(ov.get("top", top))
            bottom = float(ov.get("bottom", chest[2] - CHEST_DROP * span))
            frame = (top - bottom) / (1.0 - TOP_MARGIN) * float(ov.get("scale", 1.0))
            cz = top + TOP_MARGIN * frame - frame / 2.0 + float(ov.get("shiftZ", 0.0))
            cx = 0.5 * (head[0] + chest[0]) + float(ov.get("shiftX", 0.0))
            dist = (frame / 2.0) / math.tan(math.radians(FOV / 2.0))
            rig.set_actor_location_and_rotation(unreal.Vector(cx, head[1] - dist, cz), rot(yaw=90), False, False)
            cc.set_editor_property("fov_angle", FOV)
            cc.capture_scene()
            unreal.RenderingLibrary.export_render_target(world, rt, RAW_DIR, cid + ".png")
            entry.update({"status": "SHOT", "boneScheme": scheme, "bonesUsed": used, "facingYawBefore": round(facing, 1),
                          "rotatedBy": round(delta, 1), "headTop": round(top, 1), "bottom": round(bottom, 1),
                          "frameCm": round(frame, 1), "camera": [round(cx, 1), round(head[1] - dist, 1), round(cz, 1)],
                          "fov": FOV, "yawOffset": YAW_OFFSET, "headZ": round(head[2], 1), "chestZ": round(chest[2], 1),
                          "rawPng": os.path.join(RAW_DIR, cid + ".png"), "overrides": ov})
            shot += 1
        except Exception as exc:  # noqa: BLE001
            entry.update({"status": "FAIL", "error": str(exc)[:300]})
            failed += 1
        report[cid] = entry
    write(REPORT, report)
    print("AVATAR shot=%d failed=%d" % (shot, failed))


def main(argv):
    name = argv[0] if argv else ""
    simple = {"studio": phase_studio, "setup": phase_setup, "sim": phase_sim, "endsim": phase_endsim,
              "clear": phase_clear, "restore": phase_restore}
    if name in simple:
        simple[name]()
    elif name == "stage":
        phase_stage(argv[1:])
    elif name == "shoot":
        phase_shoot(argv[1:])
    elif name == "plan":
        ids = [r["characterId"] for r in roster()]
        for n in range(0, len(ids), BATCH_SIZE):
            print("batch %d: %s" % (n // BATCH_SIZE, ",".join(ids[n:n + BATCH_SIZE])))
    else:
        raise RuntimeError("unknown phase " + name)


main(sys.argv[1:])
