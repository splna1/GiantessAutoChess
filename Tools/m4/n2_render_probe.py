"""N2 render probe: does an MMD skeletal mesh draw in a PIE world at all?

The review shots came back showing only the Clukay416 half of every row, which could be a mesh-level
problem with the imported MMD assets or something about how the review posed them.  This probe removes
every other variable: four plain SkeletalMeshActors, no animation, no material overrides, no swaps.

    python Tools/ue_run.py Tools/m4/n2_render_probe.py stage
    # MCP: EditorToolset.EditorAppToolset StartPIE
    python Tools/ue_run.py Tools/m4/n2_render_probe.py shoot
    # MCP: EditorToolset.EditorAppToolset StopPIE
    python Tools/ue_run.py Tools/m4/n2_render_probe.py cleanup

Shot: Saved/Screenshots/N2_RenderProbe.png  (left to right: Clukay416, MMD char_101, MMD char_108, Clukay416)
"""
import os
import sys

import unreal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "paris"))
import paris_common as pc  # noqa: E402

REVIEW_MAP = "/Game/Tread/Maps/Review_Lineup"
PREFIX = "N2Probe_"
CAMERA_LABEL = "N2ProbeCamera"
ORDER = [
    "/Game/Tread/Characters/Clukay416/SK_Clukay416",
    "/Game/Tread/Characters/MMD/char_101/SK_MMD_char_101",
    "/Game/Tread/Characters/MMD/char_108/SK_MMD_char_108",
    "/Game/Tread/Characters/Clukay416/SK_Clukay416",
]
SPACING_M = 3.0
FOV_DEG = 45.0


def game_world():
    sub = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    world = sub.get_game_world() if sub else None
    if world:
        return world
    if hasattr(unreal.EditorLevelLibrary, "get_pie_worlds"):
        for world in unreal.EditorLevelLibrary.get_pie_worlds(False) or []:
            if world:
                return world
    return None


def find(world, prefix):
    found = []
    for cls in (unreal.SkeletalMeshActor, unreal.SceneCapture2D):
        for actor in unreal.GameplayStatics.get_all_actors_of_class(world, cls):
            if actor.get_actor_label().startswith(prefix):
                found.append(actor)
    return found


def phase_stage():
    if game_world():
        raise RuntimeError("stop PIE: the probe actors are placed in the editor world")
    world = pc.world()
    for actor in find(world, PREFIX):
        actor.destroy_actor()
    for index, mesh_path in enumerate(ORDER):
        mesh = unreal.load_asset(mesh_path)
        if mesh is None:
            raise RuntimeError("missing mesh " + mesh_path)
        y = (index - (len(ORDER) - 1) / 2.0) * SPACING_M * 100.0
        actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
            unreal.SkeletalMeshActor, unreal.Vector(0.0, y, 0.0), unreal.Rotator(roll=0.0, pitch=0.0, yaw=90.0))
        actor.set_actor_label("%s%02d" % (PREFIX, index))
        actor.skeletal_mesh_component.set_skeletal_mesh_asset(mesh)
        print("N2_PROBE staged %s %s y=%.0f" % (actor.get_actor_label(), mesh.get_name(), y))
    camera = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.SceneCapture2D, unreal.Vector(0.0, 0.0, 90.0), unreal.Rotator(roll=0.0, pitch=-2.0, yaw=0.0))
    camera.set_actor_label(CAMERA_LABEL)


def phase_shoot():
    world = game_world()
    if not world:
        raise RuntimeError("no PIE world; start PIE first")
    print("N2_PROBE pie world %s" % world.get_path_name())
    for actor in find(world, PREFIX):
        if actor.get_class().get_name() != "SkeletalMeshActor":
            continue
        component = actor.skeletal_mesh_component
        mesh = component.get_skeletal_mesh_asset()
        origin, extent = actor.get_actor_bounds(False)
        print("N2_PROBE %s mesh=%s y=%.0f origin=%s extent=%s visible=%s" % (
            actor.get_actor_label(), mesh.get_name() if mesh else None, actor.get_actor_location().y,
            origin, extent, component.is_visible()))
    cameras = [a for a in find(world, CAMERA_LABEL) if a.get_class().get_name() == "SceneCapture2D"]
    if not cameras:
        raise RuntimeError("no probe camera in the PIE world")
    camera = cameras[0]
    component = camera.get_component_by_class(unreal.SceneCaptureComponent2D)
    component.set_editor_property("fov_angle", FOV_DEG)
    component.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
    component.set_editor_property("capture_every_frame", False)
    component.set_editor_property("always_persist_rendering_state", True)
    target = unreal.RenderingLibrary.create_render_target2d(world, 1600, 900,
                                                            unreal.TextureRenderTargetFormat.RTF_RGBA8,
                                                            unreal.LinearColor.BLACK, False)
    component.set_editor_property("texture_target", target)
    for _ in range(10):
        component.capture_scene()
    path = pc.SHOT_DIR + "/N2_RenderProbe.png"
    folder, name = os.path.split(path)
    unreal.RenderingLibrary.export_render_target(world, target, folder, name)
    print("N2_PROBE shot -> %s" % path)


def phase_cleanup():
    if game_world():
        raise RuntimeError("stop PIE before cleaning up")
    world = pc.world()
    for actor in find(world, PREFIX):
        actor.destroy_actor()
    print("N2_PROBE cleaned")


PHASES = {"stage": phase_stage, "shoot": phase_shoot, "cleanup": phase_cleanup}

phase = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in PHASES else ""
if not phase:
    raise RuntimeError("phase must be one of %s" % sorted(PHASES))
PHASES[phase]()
