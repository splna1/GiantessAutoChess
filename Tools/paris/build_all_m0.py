"""Deterministic M0 rebuild entry point. Run inside UE through Tools/ue_run.py."""
import os
import runpy
import sys
import time

import paris_common as pc


HERE = os.path.dirname(__file__)


def run(name, args=()):
    previous = sys.argv
    try:
        sys.argv = [os.path.join(HERE, name)] + list(args)
        try:
            runpy.run_path(sys.argv[0], run_name="__main__")
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 0
            if code not in (0, None):
                raise RuntimeError("%s exited with code %s" % (name, code))
    finally:
        sys.argv = previous


def main(argv):
    started = time.time()
    steps = [
        ("00_project_config.py", []), ("01_level_lighting.py", []), ("02_textures.py", []),
        ("03_materials.py", ["--b6"]), ("04_haussmann_modules.py", []), ("05_city_layout.py", []),
        ("06_landmarks.py", []), ("07_industrial.py", []), ("07_fx_industrial.py", []),
        ("07_fx.py", []), ("08_build_b4_seine.py", []), ("08_build_b5_south.py", []),
        ("08_build_b6_ruins.py", ["--assets", "--layout", "--fx", "--audit"]),
        ("08_vrm.py", []), ("11_gp_animations.py", []), ("11_gp_animations.py", ["--verify-reload"]), ("09_camera.py", []),
        ("15_m0_validate.py", []),
    ]
    completed = []
    for name, args in steps:
        run(name, args)
        completed.append(name)
    report = {"ok": True, "completed_steps": completed, "seconds": round(time.time() - started, 2),
              "map": pc.MAP_PATH, "entry": "Tools/paris/build_all_m0.py"}
    pc.write_json(pc.REPORT_DIR + "/M0_Build_All.json", report)
    print("M0_BUILD_ALL_SECONDS=%.2f" % report["seconds"])


if __name__ == "__main__":
    main(sys.argv[1:])
