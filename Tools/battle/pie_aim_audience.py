"""Aim the audience camera at the board centre during PIE so a destruction screenshot frames the trampled line."""
import unreal

world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()
if not world:
    print("NO_PIE_WORLD")
else:
    found = 0
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.TreadM3BoardPresenter):
        actor.move_audience_camera_for_test(unreal.Vector(0.0, 0.0, 0.0))
        actor.set_audience_camera_for_test(True)
        found += 1
    print("PRESENTER_CAMERA_MOVED", found)
