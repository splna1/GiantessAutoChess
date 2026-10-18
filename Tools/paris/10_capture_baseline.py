"""Step 10: regression screenshots from fixed cameras, rendered with a SceneCapture2D (independent of the editor viewport).

    --view board (default)  render "Board_Camera" (09_camera.py) to M0_Paris_Realistic_Board_Baseline.png and leave the
                            level viewport piloting it (B1 baseline state)
    --view north            B2: spawn/reuse a CineCameraActor "North_Camera" (tag CameraNorth, folder Camera) on the
                            board's north edge looking up the axis at the red base and Notre-Dame, render M0_Env_North.png
    --view south            B5: spawn/reuse "South_Camera" behind the blue base looking north at the command band,
                            render M0_Env_South_Base.png
    --view south_tank       B5: spawn/reuse "South_Tank_Camera" at tank level near a platoon, render M0_Env_South_Tank.png

Why a scene capture: AutomationLibrary.take_high_res_screenshot only completes when the level viewport draws a frame,
which does not happen while the editor window is in the background or minimised (B2, 2026-10-02: requests queued and
never wrote a file). A SceneCaptureComponent2D at the camera's pose and horizontal FOV renders immediately from
capture_scene(); WARM_FRAMES extra captures let Lumen / TSR history converge before the exported frame.

Usage (through Tools/ue_run.py):
    10_capture_baseline.py [--warm N] [--view board|north|south|south_tank] [--size 1920x1080] (default warm = 8 frames)
"""
import math
import json
import os
import sys
import time

import unreal

import paris_common as pc

WARM_FRAMES = 8
VIEWS = {
    "board": {"label": "Board_Camera", "out": "M0_Paris_Realistic_Board_Baseline"},
    "north": {"label": "North_Camera", "out": "M0_Env_North", "loc": (640.0, -200.0, 60.0), "pitch": -4.0, "yaw": 0.0, "vfov": 46.0},
    # B5: elevated view from behind the base looking north at the command band and shields
    "south": {"label": "South_Camera", "out": "M0_Env_South_Base", "loc": (-1150.0, -120.0, 60.0), "pitch": -16.0, "yaw": 10.0, "vfov": 40.0},
    # B5: low tank-level view of the y -700 platoon from its south-west corner; the fuel tank at (-950, -700)
    # sits ~90 deg off-axis (out of frame) so it no longer blocks the M1A2 / armoured-car rows
    "south_tank": {"label": "South_Tank_Camera", "out": "M0_Env_South_Tank", "loc": (-950.0, -725.0, 2.5), "pitch": -2.0, "yaw": 15.0, "vfov": 50.0},
}
SENSOR_W, SENSOR_H = 36.0, 20.25
CAPTURE_STEP = "Capture"


def ruins_view(view):
    """Aim B6 cameras at the deterministic placement manifest, including the scan's offset pivot."""
    with open(pc.REPORT_DIR + "/M0_B6_Layout.json", encoding="utf-8") as stream:
        records = json.load(stream)["instances"]
    if view == "ruins":
        target, offset = (400.0, 1750.0, 0.0), (-310.0, -230.0, 250.0)
        suffix = ""
    elif view == "ruins_kit":
        # ruin-kit courtyard of cell (14, 8) (WingWest + CornerStack + street spill), elevated 3/4 view
        target, offset = (880.0, 2100.0, 6.0), (-95.0, -80.0, 70.0)
        suffix = "_Kit"
    elif view == "ruins_kit_street":
        # low view up the x = 800 m street (runs along y) at the toppled KB_FacadeFall of cell (14, 8)
        target, offset = (812.0, 2072.0, 3.0), (-10.0, -40.0, 9.0)
        suffix = "_KitStreet"
    else:
        role = view.removeprefix("ruins_")
        selected = min((record for record in records if record["role"] == role and record["location_m"][1] > 1200),
                       key=lambda record: abs(record["location_m"][0] - 500.0) + abs(record["location_m"][1] - 1700.0))
        target = list(selected["location_m"])
        suffix = {"leaning": "_Leaning", "footprint": "_Footprint", "cracked_road": "_Cracked", "scan": "_Scan"}[role]
        if role == "leaning":
            # stand on the street centre line (cell edge, y - 100) and look along the street so the tilt reads in profile
            target[1] -= 78.0
            target[2] += 14.0
            offset = (-60.0, -21.0, -6.0)
        elif role == "scan":
            target = [(selected["cell"][1] - 3.5) * 200, (selected["cell"][0] - 3.5) * 200, 8.0]
            offset = (-48.0, -48.0, 56.0)
        elif role == "footprint":
            offset = (-12.0, -18.0, 78.0)
        else:
            offset = (-24.0, -14.0, 10.0)
    location = tuple(target[axis] + offset[axis] for axis in range(3))
    pitch = math.degrees(math.atan2(-offset[2], math.hypot(offset[0], offset[1])))
    yaw = math.degrees(math.atan2(-offset[1], -offset[0]))
    return {"label": "B6" + (suffix or "_Overview") + "_Camera", "out": "M0_Env_Ruins" + suffix,
            "loc": location, "pitch": pitch, "yaw": yaw, "vfov": 45.0}


def find_actor(label):
    for a in pc.actor_sub().get_all_level_actors():
        if a.get_actor_label() == label:
            return a
    return None


def north_camera(spec):
    """CineCameraActor for the north view (re-created on every call so the pose always matches this file)."""
    old = find_actor(spec["label"])
    if old is not None:
        old.destroy_actor()
    cam = pc.spawn(unreal.CineCameraActor, spec["loc"], (spec["pitch"], spec.get("yaw", 0.0), 0.0), step_tag="CameraNorth", label=spec["label"], folder="Camera")
    cc = cam.get_cine_camera_component()
    fb = cc.get_editor_property("filmback")
    fb.set_editor_property("sensor_width", SENSOR_W)
    fb.set_editor_property("sensor_height", SENSOR_H)
    cc.set_editor_property("filmback", fb)
    cc.set_editor_property("current_focal_length", (SENSOR_H / 2.0) / math.tan(math.radians(spec["vfov"] / 2.0)))
    fs = cc.get_editor_property("focus_settings")
    fs.set_editor_property("focus_method", unreal.CameraFocusMethod.DISABLE)
    cc.set_editor_property("focus_settings", fs)
    cc.set_editor_property("constrain_aspect_ratio", False)
    return cam


def scene_capture(cam, path, size, warm):
    """Render the world from CineCameraActor `cam` into a PNG at `path` (final tone-mapped colour)."""
    world = pc.world()
    cc = cam.get_cine_camera_component()
    hfov = float(cc.get_editor_property("field_of_view"))
    loc = cam.get_actor_location()
    rot = cam.get_actor_rotation()
    pc.clear_step(CAPTURE_STEP)
    rt = unreal.RenderingLibrary.create_render_target2d(world, size[0], size[1], unreal.TextureRenderTargetFormat.RTF_RGBA8, unreal.LinearColor.BLACK, False)
    cap = pc.actor_sub().spawn_actor_from_class(unreal.SceneCapture2D, loc, rot)
    cap.tags = [unreal.Name(pc.TAG), unreal.Name(CAPTURE_STEP)]
    cap.set_actor_label("Capture_" + cam.get_actor_label())
    comp = cap.get_component_by_class(unreal.SceneCaptureComponent2D)
    comp.set_editor_property("texture_target", rt)
    comp.set_editor_property("fov_angle", hfov)
    comp.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
    comp.set_editor_property("capture_every_frame", False)
    comp.set_editor_property("capture_on_movement", False)
    comp.set_editor_property("always_persist_rendering_state", True)  # keeps TSR / Lumen history between captures
    for _ in range(max(0, warm)):
        comp.capture_scene()
    comp.capture_scene()
    folder, name = os.path.split(path)
    os.makedirs(folder, exist_ok=True)
    unreal.RenderingLibrary.export_render_target(world, rt, folder, name)
    cap.destroy_actor()
    return {"camera": cam.get_actor_label(), "location_m": [round(loc.x / 100, 1), round(loc.y / 100, 1), round(loc.z / 100, 1)],
            "pitch": round(rot.pitch, 2), "yaw": round(rot.yaw, 2), "hfov": round(hfov, 2), "size": list(size), "warm_frames": warm}


def main(argv):
    warm = WARM_FRAMES
    view = "board"
    size = (1920, 1080)
    for i, a in enumerate(argv):
        if a == "--warm" and i + 1 < len(argv):
            warm = int(float(argv[i + 1]))
        if a == "--view" and i + 1 < len(argv):
            view = argv[i + 1]
        if a == "--size" and i + 1 < len(argv):
            size = tuple(int(v) for v in argv[i + 1].lower().split("x"))
    spec = ruins_view(view) if view.startswith("ruins") else VIEWS[view]
    pc.ensure_map_loaded()
    cam = north_camera(spec) if "loc" in spec else find_actor(spec["label"])
    if cam is None:
        raise RuntimeError("camera %s missing, run 09_camera.py first" % spec["label"])
    t0 = time.time()
    path = pc.SHOT_DIR + "/" + spec["out"] + ".png"
    info = scene_capture(cam, path, size, warm)
    info["seconds"] = round(time.time() - t0, 1)
    if view == "board":
        unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).pilot_level_actor(cam)
    pc.write_json(pc.REPORT_DIR + "/M0_Capture_%s.json" % view, info)
    pc.log("captured %s view:" % view, path, info)


main(sys.argv[1:])
