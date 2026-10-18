"""Step 09: board camera -> CineCameraActor "Board_Camera" (tag Camera), Unity M1 framing.

Unity reference (docs 115_BOARD_CAST / 110_M1_PARIS_REFERENCE_LAYOUT): pitch 36 deg, vertical FOV 42 deg, board
seen from the south with the Eiffel Tower in the far-left backfield. UE equivalent pose (metres): (-1729, 0, 1202),
yaw 0 (looking north). With a 16:9 filmback (36 x 20.25 mm) a 26.38 mm focal length gives the 42 deg vertical /
68.6 deg horizontal FOV; the board then spans ~12%..74% of the frame height and the tower top sits at ~94%.

The camera auto-activates for Player 0, so a -game run (10_capture_baseline.py) renders exactly this view.
Depth of field is disabled (the whole board must stay sharp); exposure is locked by the level's PPV (step 01).

Usage (through Tools/ue_run.py):
    09_camera.py [--pilot]      --pilot also locks the level viewport to the camera (for editor captures)
"""
import json
import math
import sys

import unreal

import paris_common as pc

STEP = "Camera"
LOC = (-1729.0, 0.0, 1202.0)
PITCH = -36.0
VFOV = 42.0
SENSOR_W, SENSOR_H = 36.0, 20.25  # 16:9 filmback, mm


def focal_for_vfov(vfov):
    return (SENSOR_H / 2.0) / math.tan(math.radians(vfov / 2.0))


def hfov_for_focal(f):
    return math.degrees(2.0 * math.atan((SENSOR_W / 2.0) / f))


def main(argv):
    pc.ensure_map_loaded()
    pc.clear_step(STEP)
    cam = pc.spawn(unreal.CineCameraActor, LOC, (PITCH, 0.0, 0.0), step_tag=STEP, label="Board_Camera", folder="Camera")
    cc = cam.get_cine_camera_component()
    fb = cc.get_editor_property("filmback")
    fb.set_editor_property("sensor_width", SENSOR_W)
    fb.set_editor_property("sensor_height", SENSOR_H)
    cc.set_editor_property("filmback", fb)
    f = focal_for_vfov(VFOV)
    cc.set_editor_property("current_focal_length", f)
    fs = cc.get_editor_property("focus_settings")
    fs.set_editor_property("focus_method", unreal.CameraFocusMethod.DISABLE)
    cc.set_editor_property("focus_settings", fs)
    cc.set_editor_property("constrain_aspect_ratio", False)
    cam.set_editor_property("auto_activate_for_player", unreal.AutoReceiveInput.PLAYER0)
    if "--pilot" in argv:
        unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).pilot_level_actor(cam)
    pc.save_map()
    info = {"step": STEP, "location_m": list(LOC), "pitch": PITCH, "yaw": 0.0, "focal_mm": round(f, 3),
            "filmback_mm": [SENSOR_W, SENSOR_H], "vfov": VFOV, "hfov": round(hfov_for_focal(f), 2),
            "field_of_view_ue": round(cc.get_editor_property("field_of_view"), 2)}
    pc.write_json(pc.REPORT_DIR + "/M0_Camera.json", info)
    pc.log("camera", json.dumps(info))


main(sys.argv[1:])
