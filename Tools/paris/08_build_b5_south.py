"""B5 south build driver: blue materials, meshes, layout and hard height audit."""
import importlib.util
import math
import os
import sys
import time

import unreal

import bluegen
import paris_common as pc

HERE = os.path.dirname(os.path.abspath(__file__))


def load_file(filename, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_materials():
    mat = load_file("03_materials.py", "materials_b5")
    # Existing masters are reused; this targeted call creates only the paint,
    # cloth and emissive parents/instances needed by the blue kit.
    mat.main(["--only", "paint", "--only", "cloth", "--only", "emissive"])
    return {"masters": ["paint", "cloth", "emissive"], "instances": "blue faction set"}


def build_meshes(rebuild=False):
    blue = load_file("07_base_blue.py", "base_blue_b5")
    paths, meta = blue.build_meshes(rebuild)
    report = {"meshes": sorted(paths.values()), "vehicles": meta, "props": len(bluegen.prop_layout())}
    pc.write_json(pc.REPORT_DIR + "/M0_B5_Meshes.json", report)
    return report


def build_layout(rebuild=True):
    city = load_file("05_city_layout.py", "city_layout_b5")
    blue = load_file("07_base_blue.py", "base_blue_layout_b5")
    city.main(["--rebuild"] if rebuild else [])
    lights = blue.build_lights()
    report = {"layout": "05_city_layout.py", "rebuild": rebuild, "props": len(bluegen.prop_layout()), "lights": lights}
    pc.write_json(pc.REPORT_DIR + "/M0_B5_Layout.json", report)
    return report


def _corners(bounds):
    b0, b1 = bounds
    return [(x, y, z) for x in (b0[0], b1[0]) for y in (b0[1], b1[1]) for z in (b0[2], b1[2])]


def _world_corners(bounds, loc, rot, scale=1.0):
    pitch, yaw, roll = [math.radians(float(v)) for v in rot]
    # Current B5 placements use yaw only.  Keep full Euler support so the
    # report stays conservative if a prop gains a tilt later.
    cp, sp, cy, sy, cr, sr = math.cos(pitch), math.sin(pitch), math.cos(yaw), math.sin(yaw), math.cos(roll), math.sin(roll)
    out = []
    for x, y, z in _corners(bounds):
        # scale first
        x, y, z = x * scale, y * scale, z * scale
        # intrinsic roll (X), pitch (Y), yaw (Z), equivalent for the current
        # yaw-only placements and conservative for future props.
        x1, y1, z1 = x, y * cr - z * sr, y * sr + z * cr
        x2, y2, z2 = x1 * cp + z1 * sp, y1, -x1 * sp + z1 * cp
        x3, y3, z3 = x2 * cy - y2 * sy, x2 * sy + y2 * cy, z2
        out.append((loc[0] + x3, loc[1] + y3, loc[2] + z3))
    return out


def height_check():
    blue = load_file("07_base_blue.py", "base_blue_height_b5")
    paths, meta = blue.build_meshes(False)

    # Build bounds cache: path -> bounds_m
    bounds_cache = {}
    records = []
    errors = []

    for index, (name, loc, rot, extra) in enumerate(bluegen.prop_layout()):
        # Resolve path using 07's resolver
        path = blue.path_of(name, extra, paths)

        # Get bounds from cache or load
        if path not in bounds_cache:
            sm = pc.load(path)
            b = sm.get_bounding_box()
            bounds_cache[path] = ((b.min.x / 100.0, b.min.y / 100.0, b.min.z / 100.0),
                                   (b.max.x / 100.0, b.max.y / 100.0, b.max.z / 100.0))

        bounds = bounds_cache[path]
        scale = extra.get("scale", 1.0)
        wc = _world_corners(bounds, loc, rot, scale)
        top = max(p[2] for p in wc)
        near_x = max(p[0] for p in wc)
        sight = 0.8 * 1202.0 * (-800.0 - near_x) / 929.0 if near_x < -800.0 else 0.0
        is_radar = bool(extra.get("radar"))
        hard = 35.0 if is_radar else 25.0
        allowed = min(hard, sight)
        ok = near_x < -800.0 and top <= allowed + 1e-4
        rec = {"index": index, "mesh": name, "role": extra.get("role"), "location_m": [round(v, 3) for v in loc],
               "bounds_local_m": [[round(v, 3) for v in q] for q in bounds], "world_top_m": round(top, 3),
               "nearest_x_m": round(near_x, 3), "sight_ceiling_m": round(sight, 3),
               "hard_limit_m": hard, "allowed_m": round(allowed, 3), "ok": ok}
        if scale != 1.0:
            rec["scale"] = scale
        records.append(rec)
        if not ok:
            errors.append(rec)
    report = {"step": "B5", "time": time.strftime("%Y-%m-%d %H:%M:%S"), "camera": {"height_m": 1202, "board_south_x_m": -800, "horizontal_m": 929, "factor": 0.8},
              "limits_m": {"south_all": 25.0, "radar": 35.0}, "props": records, "errors": errors, "ok": not errors,
              "vehicles": meta}
    pc.write_json(pc.REPORT_DIR + "/M0_South_HeightCheck.json", report)
    pc.log("B5 height check: %s (%d props, %d errors)" % ("PASS" if not errors else "FAIL", len(records), len(errors)))
    if errors:
        raise RuntimeError("B5 south height check failed: " + repr(errors[:3]))
    return report


def main(argv):
    flags = set(argv)
    all_steps = not flags.intersection({"--materials", "--meshes", "--layout", "--height"})
    if all_steps or "--materials" in flags:
        build_materials()
    if all_steps or "--meshes" in flags:
        build_meshes("--rebuild" in flags)
    if all_steps or "--layout" in flags:
        build_layout(True)
    if all_steps or "--height" in flags:
        height_check()
    pc.save_map()
    pc.log("B5 south build complete")


if __name__ == "__main__":
    main(sys.argv[1:])
