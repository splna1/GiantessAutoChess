"""N2 review shot (editor-side, Tools/ue_run.py): line up the imported MMD models in the scratch review map
/Game/Tread/Maps/Review_Lineup (created from the engine's default template the first time; never one of the game maps),
capture them with a SceneCapture2D to Saved/Screenshots/N2_MMD_Lineup.png, remove the spawned actors and save the
scratch map so the editor is left clean. The previously open map is reopened afterwards.

    python Tools/ue_run.py Tools/m4/ue_mmd_lineup.py [--scale 1.0]
"""
import math
import os
import sys

import unreal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "paris"))
import paris_common as pc  # noqa: E402

DEST = "/Game/Tread/Characters/MMD"
OUT = pc.SHOT_DIR + "/N2_MMD_Lineup.png"
ORIGIN = (0.0, 0.0, 0.0)
REVIEW_MAP = "/Game/Tread/Maps/Review_Lineup"
TEMPLATE = "/Engine/Maps/Templates/Template_Default"


def open_review_map():
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    previous = pc.world().get_path_name().split(".")[0]
    dirty = unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages() + unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
    if dirty:
        raise RuntimeError("dirty packages present, refusing to switch map: %s" % [p.get_name() for p in dirty])
    if not unreal.EditorAssetLibrary.does_asset_exist(REVIEW_MAP):
        unreal.EditorLoadingAndSavingUtils.new_map_from_template(TEMPLATE, False)
        unreal.EditorLoadingAndSavingUtils.save_map(pc.world(), REVIEW_MAP)
    les.load_level(REVIEW_MAP)
    return previous


def main():
    previous = open_review_map()
    scale = float(sys.argv[sys.argv.index("--scale") + 1]) if "--scale" in sys.argv else 1.0
    meshes = []
    for folder in sorted(unreal.EditorAssetLibrary.list_assets(DEST, recursive=False, include_folder=True)):
        cid = folder.rstrip("/").rsplit("/", 1)[-1]
        path = "%s/%s/SK_MMD_%s" % (DEST, cid, cid)
        if unreal.EditorAssetLibrary.does_asset_exist(path):
            meshes.append(unreal.EditorAssetLibrary.load_asset(path))
    spawned = []
    spacing = 1.4 * scale
    for i, mesh in enumerate(meshes):
        loc = (ORIGIN[0], ORIGIN[1] + (i - (len(meshes) - 1) / 2.0) * spacing, ORIGIN[2])
        a = pc.actor_sub().spawn_actor_from_class(unreal.SkeletalMeshActor, pc.v(*loc), unreal.Rotator(roll=0.0, pitch=0.0, yaw=90.0))  # MMD front is +Y; face the camera at -X
        a.skeletal_mesh_component.set_skeletal_mesh_asset(mesh)
        a.set_actor_scale3d(unreal.Vector(scale, scale, scale))
        spawned.append(a)
    width = max(1, len(meshes)) * spacing
    # vertical FOV at 1920x720 and 62 deg horizontal is ~25 deg: 4.6 m fits a 2 m tall model
    dist = max(4.6 * scale, width * 0.95)
    cam_loc = pc.v(ORIGIN[0] - dist, ORIGIN[1], 0.95 * scale)
    cap = pc.actor_sub().spawn_actor_from_class(unreal.SceneCapture2D, cam_loc, unreal.Rotator(roll=0, pitch=-2.0, yaw=0.0))
    spawned.append(cap)
    world = pc.world()
    rt = unreal.RenderingLibrary.create_render_target2d(world, 1920, 720, unreal.TextureRenderTargetFormat.RTF_RGBA8, unreal.LinearColor.BLACK, False)
    comp = cap.get_component_by_class(unreal.SceneCaptureComponent2D)
    comp.set_editor_property("texture_target", rt)
    comp.set_editor_property("fov_angle", 62.0)
    comp.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
    comp.set_editor_property("capture_every_frame", False)
    comp.set_editor_property("always_persist_rendering_state", True)
    # Finish pending shader compiles and texture streaming before the exported frame (fresh materials otherwise
    # render with the default material / lowest mips).
    for cmd in ("r.ShaderCompiler.FinishAll", "FinishAllShaderCompilation", "r.Streaming.FullyLoadUsedTextures 1", "FlushRenderingCommands"):
        unreal.SystemLibrary.execute_console_command(world, cmd)
    for _ in range(24):
        comp.capture_scene()
    folder, name = os.path.split(OUT)
    unreal.RenderingLibrary.export_render_target(world, rt, folder, name)
    for a in spawned:
        a.destroy_actor()
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    if previous and previous != REVIEW_MAP:
        unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level(previous)
    print("N2_LINEUP", OUT, len(meshes))


main()
