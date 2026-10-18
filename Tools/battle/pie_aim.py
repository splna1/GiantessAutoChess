"""PIE evidence helper: aim the Audience_Camera at a world focus point and cut to it.

    python Tools/ue_run.py Tools/battle/pie_aim.py "x_m y_m" [distance_m] [height_m] [fov]

`MoveAudienceCameraForTest` is C++-only (not a UFUNCTION), so the camera actor is moved directly; the presenter's public
`set_audience_camera_for_test` still performs the view-target switch.
"""
import sys

import unreal

argv = sys.argv[1:]
pair = (argv[0] if argv else "0 250").split()
focus_x = float(pair[0])
focus_y = float(pair[1])
distance = float(argv[1]) if len(argv) > 1 else 380.0
height = float(argv[2]) if len(argv) > 2 else 200.0
fov = float(argv[3]) if len(argv) > 3 else 30.0

FOCUS = unreal.Vector(focus_x * 100.0, focus_y * 100.0, 1500.0)
OFFSET = unreal.Vector(0.0, distance * 100.0, height * 100.0)

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
        location = FOCUS + OFFSET
        camera_actor.set_actor_location(location, False, False)
        camera_actor.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(location, FOCUS), False)
        component = camera_actor.get_component_by_class(unreal.CameraComponent)
        if component:
            component.set_field_of_view(fov)
        for presenter in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.TreadM3BoardPresenter):
            presenter.set_audience_camera_for_test(True)
            break
        print("AIMED %.1f %.1f" % (focus_x, focus_y))
