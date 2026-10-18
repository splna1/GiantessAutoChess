"""PIE evidence helper: point the Audience_Camera at a world spot (the destruction line) and cut to it.

`MoveAudienceCameraForTest` is C++-only (not a UFUNCTION), so this moves the camera actor directly from Python; the
presenter's public `set_audience_camera_for_test` still does the view-target switch.
"""
import unreal

FOCUS = unreal.Vector(0.0, 250.0, 1000.0)   # cm: the trampled centre line, ~10 m up
OFFSET = unreal.Vector(0.0, 380.0, 200.0)   # m: stand off on the audience side, high enough to look down at the rubble
FOV = 30.0

world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()
if not world:
    print("NO_PIE_WORLD")
else:
    camera_actor = None
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.CameraActor):
        if "Audience" in actor.get_actor_label():
            camera_actor = actor
            break
    if not camera_actor:
        print("NO_AUDIENCE_CAMERA")
    else:
        location = FOCUS + OFFSET * 100.0
        camera_actor.set_actor_location(location, False, False)
        camera_actor.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(location, FOCUS), False)
        component = camera_actor.get_component_by_class(unreal.CameraComponent)
        if component:
            component.set_field_of_view(FOV)
        for presenter in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.TreadM3BoardPresenter):
            presenter.set_audience_camera_for_test(True)
            break
        print("AUDIENCE_CAMERA_AIMED", location)
