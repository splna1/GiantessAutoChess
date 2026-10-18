"""B2: red faction base -> /Game/Tread/City/Paris/Meshes/Base + level actors tagged BaseRed.

Geometry comes from basegen.py (pure Python, seeded). The solid props (sandbags, barriers, tents, towers, flags,
searchlights, signal lamps) are placed as ISMs by 05_city_layout.py for every zones "base_red" cell; this step adds
what an ISM cannot hold and what 05 should not own:
    SpotLight on the watch-tower searchlights (warm, no shadows) + additive beam cones (SM_Base_Beam_*, M_FX_Beam)
    red PointLight at the gate signal lamps facing the board
Both scripts call basegen.cell_layout(c, r), which is deterministic per cell, so lights and meshes always match.

Usage (through Tools/ue_run.py):
    07_base_red.py [--rebuild]      --rebuild regenerates the base meshes (05_city_layout.py --rebuild does too)
"""
import os
import sys
import time

import unreal

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import basegen  # noqa: E402
import paris_common as pc  # noqa: E402
import ue_mesh  # noqa: E402
import zones  # noqa: E402

STEP = "BaseRed"
OUT = pc.MESH + "/Base"
BEAM_MAT = pc.MAT + "/M_FX_Beam"
SPOTS_PER_CELL = 2  # the two tower searchlights get a real light + beam cone; the ground unit is a prop only
POINTS_PER_CELL = 1  # gate signal lamp facing the board (first gate = south side)


def mats():
    out = {}
    for slot, name in basegen.SLOT_MATERIALS.items():
        out[slot] = pc.MAT + "/" + name if name.startswith("M_") else pc.MAT + "/Instances/" + name
    return out


def build_meshes(rebuild=False, only=()):
    """Build every base mesh that is missing (or all with rebuild). Returns {name: asset path}."""
    m = mats()
    t0 = time.time()
    n = 0
    paths = {}
    for name, fn in basegen.MESHES.items():
        path = OUT + "/" + name
        if rebuild or name in only or not pc.EAL.does_asset_exist(path):
            ue_mesh.build_static_mesh(path, fn(), m, nanite=name not in basegen.NON_NANITE)
            n += 1
        paths[name] = path
    if n:
        unreal.SystemLibrary.execute_console_command(None, "obj gc")
    pc.log("base meshes built: %d in %.1fs" % (n, time.time() - t0))
    return paths


def cells():
    return zones.cells_of("base_red")


def spot_light(loc, rot, label):
    a = pc.spawn(unreal.SpotLight, loc, rot, step_tag=STEP, label=label, folder="Base/Lights")
    lc = a.spot_light_component
    lc.set_editor_property("intensity_units", unreal.LightUnits.CANDELAS)
    lc.set_intensity(50000.0)
    lc.set_light_color(unreal.LinearColor(1.0, 0.94, 0.82, 1.0))
    lc.set_attenuation_radius(22000.0)
    lc.set_inner_cone_angle(5.0)
    lc.set_outer_cone_angle(9.0)
    lc.set_source_radius(40.0)
    lc.set_cast_shadows(False)
    lc.set_editor_property("volumetric_scattering_intensity", 4.0)
    return a


def point_light(loc, label):
    a = pc.spawn(unreal.PointLight, loc, step_tag=STEP, label=label, folder="Base/Lights")
    lc = a.point_light_component
    lc.set_editor_property("intensity_units", unreal.LightUnits.CANDELAS)
    lc.set_intensity(2500.0)
    lc.set_light_color(unreal.LinearColor(1.0, 0.06, 0.02, 1.0))
    lc.set_attenuation_radius(5000.0)
    lc.set_source_radius(25.0)
    lc.set_cast_shadows(False)
    return a


def main(argv):
    rebuild = "--rebuild" in argv
    pc.ensure_map_loaded()
    t0 = time.time()
    paths = build_meshes(rebuild)
    beam_mat = pc.load(BEAM_MAT)
    unreal.MaterialEditingLibrary.set_base_material_usage(beam_mat, unreal.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES)
    pc.EAL.save_asset(BEAM_MAT, only_if_is_dirty=True)
    pc.clear_step(STEP)

    beams = {}
    spots, points, prop_count = 0, 0, {}
    cell_list = cells()
    for (c, r) in cell_list:
        x0, y0 = pc.cell_center(c, r)
        ns, np_ = 0, 0
        for name, (px, py, pz), (pitch, yaw, roll), extra in basegen.cell_layout(c, r):
            prop_count[name] = prop_count.get(name, 0) + 1
            light = extra.get("light")
            if light == "spot":
                v = extra["variant"]
                if extra.get("beam"):
                    beams.setdefault(paths["SM_Base_Beam_" + v], []).append(pc.xform((x0 + px, y0 + py, pz), yaw))
                if ns < SPOTS_PER_CELL:
                    lp = basegen.lens_point(v)
                    lx, ly = basegen.rot2(lp[0], lp[1], yaw)
                    spot_light((x0 + px + lx, y0 + py + ly, pz + lp[2]), (basegen.SEARCH_ELEV[v], yaw, 0.0), "BaseRed_Search_%d_%d_%d" % (c, r, ns))
                    ns += 1
                    spots += 1
            elif light == "point" and np_ < POINTS_PER_CELL:
                point_light((x0 + px, y0 + py, pz + 6.55), "BaseRed_Signal_%d_%d_%d" % (c, r, np_))
                np_ += 1
                points += 1
    if beams:
        pc.spawn_instances(beams, STEP, "BaseRed_Beams", "Base", shadows=False)
    pc.save_map()
    report = {"step": STEP, "time": time.strftime("%Y-%m-%d %H:%M:%S"), "cells": [list(c) for c in cell_list],
              "cell_rows": list(zones.BASE_RED_ROWS), "cell_cols": list(zones.BASE_RED_COLS),
              "props_total": sum(prop_count.values()), "props_by_mesh": dict(sorted(prop_count.items())),
              "spot_lights": spots, "point_lights": points, "beam_cones": sum(len(t) for t in beams.values()),
              "meshes": sorted(paths.values()), "seconds": round(time.time() - t0, 1)}
    pc.write_json(pc.REPORT_DIR + "/M0_Base_Red.json", report)
    pc.log("base red: %d cells, %d props, %d spot lights, %d point lights, %d beams" % (len(cell_list), report["props_total"], spots, points, report["beam_cones"]))


if __name__ == "__main__":
    main(sys.argv[1:])
