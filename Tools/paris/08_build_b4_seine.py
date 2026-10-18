"""B4 Eastern Seine enhancements build script.

Builds:
- Single Layer Water material (M_Paris_Water_SLW)
- Enhanced Seine segments with flood walls, stairs, balustrades (citygen)
- Tour boats and docks (rivergen)
- Updates city layout to place river props

Usage:
    python Tools/ue_run.py Tools/paris/08_build_b4_seine.py [--materials] [--meshes] [--layout]
"""
import os
import sys
import time

import unreal

import paris_common as pc

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import rivergen  # noqa: E402


def build_materials():
    """Build Single Layer Water material."""
    import importlib
    mat = importlib.import_module("03_materials")
    importlib.reload(mat)

    pc.log("Building water_slw material...")
    masters = mat.build_masters(only=["water_slw"])
    pc.log("Built %d masters" % len(masters))

    compile_errors = unreal.MaterialEditingLibrary.recompile_material(masters["water_slw"])
    if compile_errors:
        raise RuntimeError("M_Paris_Water_SLW failed to compile: %s" % "; ".join(str(e) for e in compile_errors))
    pc.log("M_Paris_Water_SLW compile check passed")

    instances = mat.build_instances(masters, only=["water_slw"])
    pc.log("Built %d instances" % instances)

    return {"masters": len(masters), "instances": instances}


def build_meshes():
    """Build tour boats, docks, and enhanced Seine segments."""
    import ue_mesh
    OUT = pc.MESH + "/River"

    stats = {}
    for name, fn in rivergen.MESHES.items():
        path = OUT + "/" + name
        if pc.EAL.does_asset_exist(path):
            pc.log("mesh %s exists, skipping" % name)
            continue
        mb = fn()
        mats = {slot: pc.MAT + "/Instances/" + rivergen.cg.SLOT_MATERIALS[slot] for slot in mb.used_slots()}
        _, s = ue_mesh.build_static_mesh(path, mb, mats, nanite=True)
        stats[name] = s
        pc.log("mesh %s tris=%d slots=%d %.1fs" % (name, s["tris"], len(s["slots"]), s["seconds"]))

    # Rebuild enhanced Seine segments (05_city_layout will use them)
    import citygen
    import importlib
    importlib.reload(citygen)

    OUT_CITY = pc.MESH + "/City"
    for name, is_bridge in [("SM_Seine", False), ("SM_Seine_Bridge", True)]:
        path = OUT_CITY + "/" + name
        mb = citygen.seine_segment(bridge=is_bridge, style="classic")
        mats = {slot: pc.MAT + "/Instances/" + citygen.SLOT_MATERIALS[slot] for slot in mb.used_slots()}
        _, s = ue_mesh.build_static_mesh(path, mb, mats, nanite=True)
        stats[name] = s
        pc.log("mesh %s tris=%d slots=%d %.1fs" % (name, s["tris"], len(s["slots"]), s["seconds"]))

    # Gilded bridge variant
    path = OUT_CITY + "/SM_Seine_Bridge_Gold"
    mb = citygen.seine_segment(bridge=True, style="gold")
    mats = {slot: pc.MAT + "/Instances/" + citygen.SLOT_MATERIALS[slot] for slot in mb.used_slots()}
    _, s = ue_mesh.build_static_mesh(path, mb, mats, nanite=True)
    stats["SM_Seine_Bridge_Gold"] = s
    pc.log("mesh %s tris=%d slots=%d %.1fs" % ("SM_Seine_Bridge_Gold", s["tris"], len(s["slots"]), s["seconds"]))

    return stats


def update_layout():
    """Place river props using rivergen.river_layout()."""
    import importlib
    rg = importlib.import_module("rivergen")
    importlib.reload(rg)

    STEP = "City_River_Props"
    pc.clear_step(STEP)

    items = rg.river_layout()
    pc.log("river layout: %d items" % len(items))

    # Check clearances
    errs = rg.check_layout(items)
    if errs:
        pc.log("WARNING: layout clearance issues:")
        for e in errs:
            pc.log("  " + e)

    # Group by mesh
    by_mesh = {}
    for mesh, pos, rot, tag in items:
        if mesh == "tree":
            continue  # 05_city_layout handles trees
        full_path = pc.MESH + "/River/" + mesh
        # rivergen coordinates are metres; pc.xform performs the metres-to-centimetres conversion.
        # Do not pre-scale Z, or boats/docks are placed hundreds of metres below the water.
        by_mesh.setdefault(full_path, []).append(pc.xform((pos[0], pos[1], pos[2]), rot[1], (1, 1, 1)))

    if by_mesh:
        pc.spawn_instances(by_mesh, STEP, "City_River_Props", "City")

    pc.save_map()
    return {"items": len(items), "meshes": len(by_mesh), "errors": len(errs)}


def main(argv):
    run_all = not argv
    do_materials = "--materials" in argv or run_all
    do_meshes = "--meshes" in argv or run_all
    do_layout = "--layout" in argv or run_all

    pc.ensure_map_loaded()
    t0 = time.time()
    stats = {}

    if do_materials:
        pc.log("\n=== Building materials ===")
        stats["materials"] = build_materials()

    if do_meshes:
        pc.log("\n=== Building meshes ===")
        stats["meshes"] = build_meshes()

    if do_layout:
        pc.log("\n=== Updating layout ===")
        stats["layout"] = update_layout()

    stats["seconds"] = round(time.time() - t0, 1)
    pc.write_json(pc.REPORT_DIR + "/M0_B4_Seine.json", stats)
    pc.log("\nB4 Seine enhancements complete:", stats)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
