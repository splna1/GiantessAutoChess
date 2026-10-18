"""N2 (b) review shots: retargeted GP clips on the MMD meshes, side by side with the source.

A single-node skeletal mesh only gets its pose from the animation tick, which an editor-world
component does not run, and the editor viewport capture does not draw what a PIE world renders
(memory: tread-viewport-capture-lies).  So the review poses are placed in the map as real level
actors, posed again inside a PIE session where the duplicated actors tick, and shot with HighResShot
from the game viewport.  The host-side driver runs the whole sequence:

    python Tools/m4/n2_retarget_review_pie.py [--chars char_101,char_105]

which calls these phases (each its own remote call; a map switch must never share a call with
anything that reads the world, memory: tread-editor-python-map-switch):

    load                 remember the current map, switch to Review_Lineup        (editor)
    stage   [--chars]    game mode override, one row of actors per clip x character (editor)
    frame <row>          pose one row, hide the others, view it through the camera  (PIE)
    shoot <row>          HighResShot of what the game viewport shows                (PIE)
    cleanup              remove the review actors and save the scratch map           (editor)
    restore              switch back to the remembered map                           (editor)

Each row renders 2 x 5 poses at the same clip times: the left half is the Clukay416 source mesh
playing the Clukay416 clip (the reference motion), the right half is one MMD mesh playing its
retargeted clip.  Matching silhouettes across the halves is the acceptance signal.  Every row stands
on the same spot so all shots share one floor, light and camera; frame hides every other row and
checks that exactly this row is left visible.

Shots: Saved/Screenshots/N2_Retarget_<Clip>_<NNN>.png (copied there by the host-side driver)
"""
import json
import math
import os
import sys

import unreal

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATE = os.path.join(PROJECT, "Saved", "Reports", "N2_Retarget_Review_state.json")

MMD_ROOT = "/Game/Tread/Characters/MMD"
MESH_PREFIX = "SK_MMD_"
# --set vrm reviews the M4 roster VRMs instead (characters must then be named with --chars).
SETS = {"mmd": ("/Game/Tread/Characters/MMD", "SK_MMD_"), "vrm": ("/Game/Tread/Characters/VRM", "SK_VRM_")}
SOURCE_MESH = "/Game/Tread/Characters/Clukay416/SK_Clukay416"
SOURCE_DIR = "/Game/Tread/Characters/Clukay416/Anim/GP"
REVIEW_MAP = "/Game/Tread/Maps/Review_Lineup"
CHARACTERS = ["char_%d" % n for n in range(101, 113)]
SPACING_M = 1.35
FOV_DEG = 90.0  # CameraActor default
CAMERA_LABEL = "N2ReviewCamera"
PREFIX = "N2Review_"
SHOT_SIZE = "2560x1440"
# Throw / Kneel / Walk were picked by measured motion amplitude on the retargeted bones; Stomp is the
# clip with the largest arm offset against the hero in N2_AnimPoseSweep.json (26.6 degrees).
SHOTS = [
    ("Throw", "A_GP_Throw", [0.0, 0.45, 0.9, 1.35, 1.8]),
    ("Kneel", "A_GP_Kneel", [0.0, 0.6, 1.2, 1.8, 2.4]),
    ("Walk", "A_GP_Walk", [0.0, 0.35, 0.7, 1.05, 1.4]),
    ("Stomp", "A_GP_Stomp", [0.0, 0.7, 1.4, 2.1, 2.8]),
]


def write_state(doc):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, indent=1)


def read_state():
    if not os.path.exists(STATE):
        return {}
    with open(STATE, encoding="utf-8") as handle:
        return json.load(handle)


def editor_world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


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


def review_actors(world):
    found = []
    for cls in (unreal.SkeletalMeshActor, unreal.CameraActor, unreal.SceneCapture2D):
        for actor in unreal.GameplayStatics.get_all_actors_of_class(world, cls):
            label = actor.get_actor_label()
            if label.startswith(PREFIX) or label == CAMERA_LABEL:
                found.append(actor)
    return found


def load(path):
    return unreal.load_asset(path)


def row_name(clip_row, character):
    return "%s_%s" % (clip_row, character.split("_")[-1])


def plan(characters):
    """[(row, [(mesh, animation, time)])]: per clip and character, the source half then the MMD half."""
    out = []
    source_mesh = load(SOURCE_MESH)
    for clip_row, clip, times in SHOTS:
        source = [(source_mesh, load("%s/%s" % (SOURCE_DIR, clip)), t) for t in times]
        for character in characters:
            animation = load("%s/%s/Anim/%s" % (MMD_ROOT, character, clip))
            mesh = load("%s/%s/%s%s" % (MMD_ROOT, character, MESH_PREFIX, character))
            if animation is None or mesh is None:
                raise RuntimeError("missing review asset for %s %s" % (character, clip))
            out.append((row_name(clip_row, character), source + [(mesh, animation, t) for t in times]))
    return out


def rotator(pitch=0.0, yaw=0.0, roll=0.0):
    # unreal.Rotator's positional order is (roll, pitch, yaw), which reads as a silent 90 degree
    # error whenever someone passes (pitch, yaw, roll). Always pass by name.
    return unreal.Rotator(roll=roll, pitch=pitch, yaw=yaw)


def column_y(index, columns):
    return (index - (columns - 1) / 2.0) * SPACING_M * 100.0


def camera_distance_cm(columns):
    span = columns * SPACING_M
    return max(4.0, span / (2.0 * math.tan(math.radians(FOV_DEG / 2.0))) * 1.25) * 100.0


def pose(actor, animation, time):
    component = actor.skeletal_mesh_component
    component.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
    component.set_animation(animation)
    component.set_play_rate(0.0)  # freeze so the sampled time survives until the shot
    component.set_position(time, False)


def characters_arg():
    if "--chars" in sys.argv:
        return sys.argv[sys.argv.index("--chars") + 1].split(",")
    return CHARACTERS


def phase_load():
    """Switch to the review map and nothing else (memory: tread-editor-python-map-switch)."""
    if game_world():
        raise RuntimeError("a PIE session is already running")
    dirty = (unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
             + unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    if dirty:
        raise RuntimeError("dirty packages present, refusing to switch map: %s" % [p.get_name() for p in dirty])
    if not unreal.EditorAssetLibrary.does_asset_exist(REVIEW_MAP):
        raise RuntimeError("missing %s (created by Tools/m4/ue_mmd_lineup.py)" % REVIEW_MAP)
    previous = editor_world().get_path_name().split(".")[0]
    state = read_state()
    # A rerun after a failed restore must not remember the review map as the one to go back to.
    if previous != REVIEW_MAP or not state.get("previousMap"):
        state["previousMap"] = previous
    write_state(state)
    if previous != REVIEW_MAP and not unreal.EditorLoadingAndSavingUtils.load_map(REVIEW_MAP):
        raise RuntimeError("failed to load " + REVIEW_MAP)
    print("N2_REVIEW load previous=%s" % state["previousMap"])


def phase_stage():
    if game_world():
        raise RuntimeError("stop PIE: the review actors are placed in the editor world")
    world = editor_world()
    if not world.get_path_name().startswith(REVIEW_MAP):
        raise RuntimeError("run the load phase first, the editor is on %s" % world.get_path_name())
    # The project's global game mode is the M1 match, which would put its UI over the shot.
    world.get_world_settings().set_editor_property("default_game_mode", unreal.GameModeBase)
    for actor in review_actors(world):
        actor.destroy_actor()
    rows = plan(characters_arg())
    for row, panels in rows:
        for index, (mesh, _, _) in enumerate(panels):
            actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
                unreal.SkeletalMeshActor, unreal.Vector(0.0, column_y(index, len(panels)), 0.0),
                rotator(yaw=-90.0 if "--front" in sys.argv else 90.0))  # --front: faces toward the camera
            actor.set_actor_label("%s%s_%02d" % (PREFIX, row, index))
            actor.skeletal_mesh_component.set_skeletal_mesh_asset(mesh)
    columns = max(len(p) for _, p in rows)
    camera = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.CameraActor, unreal.Vector(-camera_distance_cm(columns), 0.0, 100.0), rotator(pitch=-2.0))
    camera.set_actor_label(CAMERA_LABEL)
    state = read_state()
    state.update({"rows": [row for row, _ in rows], "columns": [len(p) for _, p in rows],
                  "times": {clip_row: times for clip_row, _, times in SHOTS}})
    write_state(state)
    print("N2_REVIEW stage rows=%d actors=%d" % (len(rows), sum(len(p) for _, p in rows)))


def row_arg():
    row = sys.argv[2] if len(sys.argv) > 2 else ""
    if row not in read_state().get("rows", []):
        raise RuntimeError("row must be one of the staged rows, got %r" % row)
    return row


def phase_frame():
    world = game_world()
    if not world:
        raise RuntimeError("no PIE world; start PIE first")
    row = row_arg()
    clip_row, number = row.rsplit("_", 1)
    panels = dict(plan(["char_" + number]))[row]
    visible = 0
    camera = None
    for actor in review_actors(world):
        label = actor.get_actor_label()
        if label == CAMERA_LABEL:
            camera = actor
            continue
        mine = label.startswith("%s%s_" % (PREFIX, row))
        actor.set_actor_hidden_in_game(not mine)
        if mine:
            mesh, animation, time = panels[int(label.rsplit("_", 1)[1])]
            actor.skeletal_mesh_component.set_skeletal_mesh_asset(mesh)
            pose(actor, animation, time)
            visible += 1
    if visible != len(panels):
        raise RuntimeError("row %s: %d visible actors, expected %d" % (row, visible, len(panels)))
    if camera is None:
        raise RuntimeError("no %s in the PIE world" % CAMERA_LABEL)
    controller = unreal.GameplayStatics.get_player_controller(world, 0)
    pawn = controller.get_controlled_pawn() if controller else None
    if pawn:
        pawn.set_actor_hidden_in_game(True)
    controller.set_view_target_with_blend(camera, 0.0)
    print("N2_REVIEW frame %s visible=%d camera=%s" % (row, visible, camera.get_actor_location()))


def phase_shoot():
    world = game_world()
    if not world:
        raise RuntimeError("no PIE world; start PIE first")
    row = row_arg()
    unreal.SystemLibrary.execute_console_command(world, "HighResShot " + SHOT_SIZE)
    print("N2_REVIEW shoot %s requested" % row)


def phase_cleanup():
    if game_world():
        raise RuntimeError("stop PIE before cleaning up")
    world = editor_world()
    if not world.get_path_name().startswith(REVIEW_MAP):
        raise RuntimeError("the editor is not on the review map: %s" % world.get_path_name())
    removed = 0
    for actor in review_actors(world):
        actor.destroy_actor()
        removed += 1
    # Leave the scratch map clean so the restore phase (and the next map switch) sees no dirty package.
    saved = unreal.EditorLoadingAndSavingUtils.save_map(world, REVIEW_MAP)
    print("N2_REVIEW cleanup removed=%d saved=%s" % (removed, saved))


def phase_restore():
    """Switch back to the remembered map and nothing else."""
    if game_world():
        raise RuntimeError("stop PIE before restoring the map")
    previous = read_state().get("previousMap", "")
    if not previous or previous == REVIEW_MAP:
        print("N2_REVIEW restore nothing to do (previous=%s)" % previous)
        return
    if not unreal.EditorLoadingAndSavingUtils.load_map(previous):
        raise RuntimeError("failed to restore " + previous)
    print("N2_REVIEW restore %s" % previous)


PHASES = {"load": phase_load, "stage": phase_stage, "frame": phase_frame, "shoot": phase_shoot,
          "cleanup": phase_cleanup, "restore": phase_restore}


def main():
    global MMD_ROOT, MESH_PREFIX, SHOTS
    if "--set" in sys.argv:
        MMD_ROOT, MESH_PREFIX = SETS[sys.argv[sys.argv.index("--set") + 1]]
    phase = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in PHASES else ""
    if "--shots" in sys.argv:
        # Any source clips, e.g. --shots SitCrush,Grab: five times spread over each clip's length.
        SHOTS = []
        staged = read_state().get("times") or {} if phase != "stage" else {}
        for clip in sys.argv[sys.argv.index("--shots") + 1].split(","):
            if clip in staged:  # the editor asset library does not load during PIE: reuse the staged times
                SHOTS.append((clip, "A_GP_" + clip, staged[clip]))
                continue
            anim = unreal.EditorAssetLibrary.load_asset("%s/A_GP_%s" % (SOURCE_DIR, clip))
            if anim is None:
                raise RuntimeError("no source clip A_GP_" + clip)
            length = anim.get_editor_property("sequence_length")
            SHOTS.append((clip, "A_GP_" + clip, [round(length * f, 3) for f in (0.0, 0.25, 0.5, 0.75, 0.98)]))
    if not phase:
        raise RuntimeError("phase must be one of %s" % sorted(PHASES))
    PHASES[phase]()


main()
