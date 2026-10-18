"""M3 regression screenshots of the M3 Paris map (editor-side SceneCapture2D, same method as
Tools/paris/10_capture_baseline.py, which is bound to the M0 map).

    python Tools/ue_run.py Tools/m3/m3_capture.py [--view board|court|court_low|planes|ruin|crash|west|west_low] [--warm N] [--size WxH]

board      the map's own Board_Camera (the gameplay framing, 30-45 deg) -> M3_Paris_Board.png
court      3/4 view over the south-west board quarter                    -> M3_Paris_Courtyards.png
court_low  street-level view into a courtyard                            -> M3_Paris_Courtyard_Low.png
planes     the SE5 formation over the south edge                         -> M3_Paris_Aircraft.png
ruin       the ruined cell with the crashed dive bomber                  -> M3_Paris_Ruin_Crash.png
"""
import math
import os
import sys
import time

import unreal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "paris"))
import paris_common as pc  # noqa: E402

M3_MAP = "/Game/Tread/Maps/M3_Paris_Match"
CAPTURE_STEP = "M3Capture"
SENSOR_W, SENSOR_H = 36.0, 20.25


def views():
    rx, ry = pc.cell_center(*pc.RUIN_CELL)
    return {
        "board": {"label": "Board_Camera", "out": "M3_Paris_Board"},
        "court": {"label": "M3_Court_Camera", "loc": (-1150.0, -900.0, 520.0), "pitch": -33.0, "yaw": 38.0, "vfov": 40.0,
                  "out": "M3_Paris_Courtyards"},
        "court_low": {"label": "M3_CourtLow_Camera", "loc": (-420.0, -330.0, 70.0), "pitch": -14.0, "yaw": 40.0, "vfov": 48.0,
                      "out": "M3_Paris_Courtyard_Low"},
        "planes": {"label": "M3_Planes_Camera", "loc": (-700.0, -260.0, 190.0), "target": (-775.0, -180.0, 152.0), "vfov": 30.0,
                   "out": "M3_Paris_Aircraft"},
        "west": {"label": "M3_West_Camera", "loc": (-450.0, -900.0, 280.0), "target": (100.0, -1900.0, 20.0), "vfov": 42.0,
                 "out": "M3_Paris_West_Industry"},
        "west_low": {"label": "M3_WestLow_Camera", "loc": (150.0, -1180.0, 80.0), "target": (300.0, -1600.0, 35.0), "vfov": 46.0,
                     "out": "M3_Paris_West_Factories"},
        "crash": {"label": "M3_Crash_Camera", "loc": (rx - 30.0, ry - 110.0, 45.0), "target": (rx + 36.0, ry - 34.0, 2.0), "vfov": 34.0,
                  "out": "M3_Paris_Crash_Close"},
        "ruin": {"label": "M3_Ruin_Camera", "loc": (rx - 170.0, ry - 170.0, 120.0), "pitch": -27.0, "yaw": 45.0, "vfov": 40.0,
                 "out": "M3_Paris_Ruin_Crash"},
    }


def find_actor(label):
    for a in pc.actor_sub().get_all_level_actors():
        if a.get_actor_label() == label:
            return a
    return None


def look_at(loc, target):
    dx, dy, dz = (target[i] - loc[i] for i in range(3))
    return math.degrees(math.atan2(dz, math.hypot(dx, dy))), math.degrees(math.atan2(dy, dx))


def make_camera(spec):
    if "target" in spec:
        spec["pitch"], spec["yaw"] = look_at(spec["loc"], spec["target"])
    old = find_actor(spec["label"])
    if old is not None:
        old.destroy_actor()
    cam = pc.spawn(unreal.CineCameraActor, spec["loc"], (spec["pitch"], spec.get("yaw", 0.0), 0.0), step_tag=CAPTURE_STEP,
                   label=spec["label"], folder="Camera")
    cc = cam.get_cine_camera_component()
    fb = cc.get_editor_property("filmback")
    fb.set_editor_property("sensor_width", SENSOR_W)
    fb.set_editor_property("sensor_height", SENSOR_H)
    cc.set_editor_property("filmback", fb)
    cc.set_editor_property("current_focal_length", (SENSOR_H / 2.0) / math.tan(math.radians(spec["vfov"] / 2.0)))
    fs = cc.get_editor_property("focus_settings")
    fs.set_editor_property("focus_method", unreal.CameraFocusMethod.DISABLE)
    cc.set_editor_property("focus_settings", fs)
    return cam


def capture(cam, path, size, warm):
    world = pc.world()
    cc = cam.get_cine_camera_component()
    hfov = float(cc.get_editor_property("field_of_view"))
    rt = unreal.RenderingLibrary.create_render_target2d(world, size[0], size[1], unreal.TextureRenderTargetFormat.RTF_RGBA8,
                                                         unreal.LinearColor.BLACK, False)
    cap = pc.actor_sub().spawn_actor_from_class(unreal.SceneCapture2D, cam.get_actor_location(), cam.get_actor_rotation())
    comp = cap.get_component_by_class(unreal.SceneCaptureComponent2D)
    comp.set_editor_property("texture_target", rt)
    comp.set_editor_property("fov_angle", hfov)
    comp.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
    comp.set_editor_property("capture_every_frame", False)
    comp.set_editor_property("capture_on_movement", False)
    comp.set_editor_property("always_persist_rendering_state", True)
    for _ in range(max(0, warm)):
        comp.capture_scene()
    comp.capture_scene()
    folder, name = os.path.split(path)
    os.makedirs(folder, exist_ok=True)
    unreal.RenderingLibrary.export_render_target(world, rt, folder, name)
    cap.destroy_actor()
    return hfov


def main(argv):
    view = argv[argv.index("--view") + 1] if "--view" in argv else "board"
    warm = int(argv[argv.index("--warm") + 1]) if "--warm" in argv else 10
    size = tuple(int(v) for v in argv[argv.index("--size") + 1].split("x")) if "--size" in argv else (1920, 1080)
    if not pc.world().get_path_name().startswith(M3_MAP):
        raise RuntimeError("open %s first (run m3_board_city.py)" % M3_MAP)
    spec = views()[view]
    cam = make_camera(spec) if "loc" in spec else find_actor(spec["label"])
    if cam is None:
        raise RuntimeError("camera missing: " + spec["label"])
    t0 = time.time()
    path = pc.SHOT_DIR + "/" + spec["out"] + ".png"
    hfov = capture(cam, path, size, warm)
    if "loc" in spec:
        cam.destroy_actor()  # temporary review cameras are not part of the map
    pc.log("captured %s -> %s (hfov %.1f, %.1fs)" % (view, path, hfov, time.time() - t0))


main(sys.argv[1:])
