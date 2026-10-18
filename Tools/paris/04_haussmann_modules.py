"""Step 04: Haussmann block modules -> Nanite static meshes in /Game/Tread/City/Paris/Meshes/Haussmann.

Geometry comes from haussmann.py (pure Python, seeded, so re-runs rebuild identical meshes in place).
Every module is block-local (pivot = block centre, metres -> cm) and covers the SW corner (L) or the
south mid-block gap (infill) or the whole courtyard (court fill, background blocks only); 05_city_layout.py rotates them 0/90/180/270 deg to assemble full blocks.

B2 adds the low-rise modules (SM_Hsm_Low*: 2-3 upper floors, <= 18 m, haussmann.low_height_check) for the
northern district; the standard modules are untouched.
B6 adds damaged low-rise variants for the outer ruin ring (SM_Hsm_LowLRuin_*, SM_Hsm_LowLBurnt_*,
SM_Hsm_LowInfillRuin_*; same 18 m ceiling, built with --group low as well).

Usage (through Tools/ue_run.py):
    04_haussmann_modules.py                 build every module + report
    04_haussmann_modules.py --only SM_Hsm_L_00 [--only ...]
    04_haussmann_modules.py --group low     build only the low-rise modules (merged into the report)
    04_haussmann_modules.py --test [x y]    also place one test block at (x, y) metres (tag BlockTest)
"""
import json
import os
import sys
import time

import unreal

import haussmann as hm
import paris_common as pc
import ue_mesh

OUT = pc.MESH + "/Haussmann"
TEST_STEP = "BlockTest"

# name -> (kind, seed, damage)
MODULES = {}
for _i in range(8):
    MODULES["SM_Hsm_L_%02d" % _i] = ("l", 1100 + _i * 7, None)
for _i in range(3):
    MODULES["SM_Hsm_LBurnt_%02d" % _i] = ("l", 2100 + _i * 7, "burnt")
for _i in range(3):
    MODULES["SM_Hsm_LRuin_%02d" % _i] = ("l", 3100 + _i * 7, "collapsed")
for _i in range(5):
    MODULES["SM_Hsm_Infill_%02d" % _i] = ("infill", 4100 + _i * 7, None)
MODULES["SM_Hsm_InfillBurnt_00"] = ("infill", 5100, "burnt")
for _i in range(2):
    MODULES["SM_Hsm_InfillRuin_%02d" % _i] = ("infill", 6100 + _i * 7, "collapsed")
for _i in range(6):
    MODULES["SM_Hsm_Court_%02d" % _i] = ("court", 7100 + _i * 7, None)  # courtyard fill of background blocks
for _i, _s in enumerate(hm.LOW_SEEDS["lowl"]):
    MODULES["SM_Hsm_LowL_%02d" % _i] = ("lowl", _s, None)  # B2 low-rise district
for _i, _s in enumerate(hm.LOW_SEEDS["lowinfill"]):
    MODULES["SM_Hsm_LowInfill_%02d" % _i] = ("lowinfill", _s, None)
for _i, _s in enumerate(hm.LOW_SEEDS["lowcourt"]):
    MODULES["SM_Hsm_LowCourt_%02d" % _i] = ("lowcourt", _s, None)
for _i in range(3):
    MODULES["SM_Hsm_LowLRuin_%02d" % _i] = ("lowl", 8300 + _i * 7, "collapsed")  # B6 ruin ring, north district
for _i in range(2):
    MODULES["SM_Hsm_LowLBurnt_%02d" % _i] = ("lowl", 8400 + _i * 7, "burnt")
for _i in range(2):
    MODULES["SM_Hsm_LowInfillRuin_%02d" % _i] = ("lowinfill", 8500 + _i * 7, "collapsed")
LOW_MODULES = [n for n, (k, _, _) in MODULES.items() if k.startswith("low")]


def slot_materials():
    return {s: pc.MAT + "/Instances/" + mi for s, mi in hm.SLOT_MATERIALS.items()}


def build_module(name, mats):
    kind, seed, damage = MODULES[name]
    if kind == "l":
        mb = hm.l_piece(seed, damage)
    elif kind == "infill":
        mb = hm.infill_piece(seed, damage)
    elif kind == "court":
        mb = hm.court_fill_piece(seed)
    elif kind == "lowl":
        mb = hm.l_piece(seed, damage, low=True)
    elif kind == "lowinfill":
        mb = hm.infill_piece(seed, damage, low=True)
    else:
        mb = hm.court_fill_piece(seed, low=True)
    top = mb.bounds()[1][2]
    if kind.startswith("low") and top > hm.LOW_MAX_H:
        raise RuntimeError("%s is %.2f m tall, above the %.1f m low-rise ceiling" % (name, top, hm.LOW_MAX_H))
    sm, stats = ue_mesh.build_static_mesh(OUT + "/" + name, mb, mats, nanite=True)
    ns = sm.get_editor_property("nanite_settings")
    stats["nanite_enabled"] = bool(ns.get_editor_property("enabled"))
    stats["kind"], stats["seed"], stats["damage"], stats["height_m"] = kind, seed, damage, round(top, 2)
    return stats


def place_block(x, y, names, step, folder, label):
    """4 L-pieces + 4 infills around (x, y) metres, yaw 0/90/180/270 (UE yaw +90 maps local (x,y) -> (-y,x))."""
    actors = []
    for k in range(4):
        yaw = 90.0 * k
        for nm in names[k]:
            mesh = pc.load(OUT + "/" + nm)
            actors.append(pc.spawn_mesh(mesh, (x, y, 0.0), (0.0, yaw, 0.0), step_tag=step, label="%s_%s_%d" % (label, nm, k), folder=folder))
    return actors


def main(argv):
    only = [argv[i + 1] for i, a in enumerate(argv) if a == "--only"]
    if "--group" in argv and argv[argv.index("--group") + 1] == "low":
        only = only + LOW_MODULES
    test = "--test" in argv
    pc.ensure_map_loaded()
    mats = slot_materials()
    names = only or list(MODULES)
    report = []
    t0 = time.time()
    for nm in names:
        report.append(build_module(nm, mats))
        unreal.SystemLibrary.execute_console_command(None, "obj gc")
    pc.log("modules built: %d in %.1fs, tris total %d" % (len(report), time.time() - t0, sum(r["tris"] for r in report)))
    path = pc.REPORT_DIR + "/M0_Haussmann_Modules.json"
    if only and os.path.exists(path):  # partial rebuild: merge into the existing report
        with open(path, encoding="utf-8") as f:
            old = {m["asset"]: m for m in json.load(f).get("modules", [])}
        old.update({m["asset"]: m for m in report})
        report = [old[k] for k in sorted(old)]
    pc.write_json(path, {"modules": report, "slots": hm.SLOT_MATERIALS})
    for a in ("WindTest0", "WindTest1"):
        pc.clear_step(a)
    if test:
        i = argv.index("--test")
        try:
            x, y = float(argv[i + 1]), float(argv[i + 2])
        except (IndexError, ValueError):
            x, y = pc.cell_center(2, 2)
        pc.clear_step(TEST_STEP)
        L = ["SM_Hsm_L_00", "SM_Hsm_L_01", "SM_Hsm_LBurnt_00", "SM_Hsm_L_02"]
        I = ["SM_Hsm_Infill_00", "SM_Hsm_Infill_01", "SM_Hsm_InfillRuin_00", "SM_Hsm_Infill_02"]
        place_block(x, y, [[L[k], I[k]] for k in range(4)], TEST_STEP, "Test", "TestBlock")
        pc.save_map()
        pc.log("test block at", x, y)


if __name__ == "__main__":
    main(sys.argv[1:])
