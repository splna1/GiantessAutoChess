"""B6 pipeline via Tools/ue_run.py. Flags: --assets --layout --fx --audit --capture; no flags runs all.
--rebuild regenerates the ruingen meshes, --rebuild-kit re-imports the SM_KB_* ruin kit (13_blender_ruin_kit.py output)."""
import json
import os
import runpy
import sys
import time

import paris_common as pc

HERE = os.path.dirname(__file__)


def run_step(filename, arguments=()):
    previous = sys.argv
    try:
        sys.argv = [os.path.join(HERE, filename)] + list(arguments)
        namespace = runpy.run_path(sys.argv[0], run_name="__main__")
        namespace.clear()
    finally:
        sys.argv = previous


def main(arguments):
    stages = {"--assets", "--layout", "--fx", "--audit", "--capture"}
    selected = stages.intersection(arguments) or stages
    completed = []
    started = time.time()
    pc.ensure_map_loaded()
    pc.save_map()
    baseline = pc.REPORT_DIR + "/M0_B6_Protected_Before.json"
    if not os.path.exists(baseline):
        run_step("11_audit_b6.py", ["--snapshot"])
    if "--assets" in selected:
        textures = ("AssetsA", "BricksA", "BricksADamage", "ConcreteA", "ConcreteB", "DamageA", "FloorA", "FloorB",
                    "MetalFrameA", "MetalRustA", "PlasterA", "PlasterB", "PlasterC", "RubbleA", "WoodA")
        texture_arguments = [value for suffix in textures for value in ("--only", "T_KB_" + suffix + "_D")]
        run_step("02_textures.py", texture_arguments)
        run_step("03_materials.py", ["--b6"])
        run_step("09_ruins.py", [flag for flag in ("--rebuild", "--rebuild-kit") if flag in arguments])
        completed.append("assets")
    if "--layout" in selected:
        run_step("05_city_layout.py")
        completed.append("layout")
    if "--fx" in selected:
        run_step("07_fx.py", ["--b6"])
        completed.append("fx")
    if "--audit" in selected:
        run_step("11_audit_b6.py")
        run_step("08_build_b5_south.py", ["--height"])
        completed.append("audit")
    if "--capture" in selected:
        for view in ("ruins", "ruins_scan", "ruins_leaning", "ruins_footprint", "ruins_cracked_road", "ruins_kit",
                     "ruins_kit_street", "board"):
            run_step("10_capture_baseline.py", ["--view", view, "--warm", "24"])
        completed.append("capture")
    pc.save_map()
    pc.write_json(pc.REPORT_DIR + "/M0_B6_Build.json", {"ok": True, "completed_stages": completed,
                  "seconds": round(time.time() - started, 2), "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})


if __name__ == "__main__":
    main(sys.argv[1:])
