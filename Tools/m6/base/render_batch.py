# -*- coding: utf-8 -*-
"""Batch render several module blends in one Blender process.

    blender -b --factory-startup --python render_batch.py -- \
        --out <dir> --res 900x750 --samples 32 --views hero,front [--preview]
"""
import json
import os
import sys
import time

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import render_shots as R  # noqa: E402

MODULES = [
    ("M6_C2_Command.blend", "C2"),
    ("M6_HGR_Hangar.blend", "HGR"),
    ("M6_BRK_Barracks.blend", "BRK"),
    ("M6_RDR_Radar.blend", "RDR"),
    ("M6_GTE_Gate.blend", "GTE"),
    ("M6_UAV_Pad.blend", "UAV"),
    ("M6_CON_Site.blend", "CON"),
    ("M6_CCR_Crane.blend", "CCR"),
    ("M6_SIT_Seat.blend", "SIT"),
    ("M6_Base_Site.blend", "SITE"),
]


def opt(args, name, default=None):
    if name in args:
        i = args.index(name)
        if i + 1 < len(args):
            return args[i + 1]
    return default


def shoot(blend, tag, out, res, samples, views, only=None, exposure=0.35, fill=0.96):
    bpy.ops.wm.open_mainfile(filepath=blend)
    R.K.reset_cache()
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "AgX"
    for look in ("AgX - Medium High Contrast", "AgX - Punchy", "None"):
        try:
            sc.view_settings.look = look
            break
        except Exception:
            continue
    sc.view_settings.exposure = exposure
    eng = R.set_engine("cycles", samples)

    objs = R.scene_meshes()
    mn, mx = R.bounds(objs)
    center = (mn + mx) / 2.0
    radius = (mx - mn).length / 2.0
    corners = [Vector((x, y, z)) for x in (mn.x, mx.x) for y in (mn.y, mx.y) for z in (mn.z, mx.z)]
    R.ensure_ground(center, max(3000.0, radius * 60.0))
    R.fill_light(center, radius, (-0.80, 0.60, 0.45))
    cam = R.make_cam()
    sc.camera = cam
    shots = []
    for v in views:
        spec = R.VIEWS.get(v)
        if not spec or (only and v not in only):
            continue
        aim = center.copy()
        aim.z = mn.z + (mx.z - mn.z) * spec["aim"]
        z = fill * spec.get("zoom", 1.0)
        corners_v = [center + (c - center) * z for c in corners]
        k = R.fit(cam, corners_v, aim, spec["dir"], spec["lens"], res)
        if cam.location.z < 2.0:
            cam.location.z = 2.0
        path = os.path.join(out, "shot_%s_%s.png" % (tag, v))
        sc.render.filepath = path
        t = time.time()
        bpy.ops.render.render(write_still=True)
        shots.append({"tag": tag, "view": v, "path": path, "sec": round(time.time() - t, 2),
                      "ndc": round(k, 3)})
        print("RENDERED %s %s %.1fs" % (tag, v, time.time() - t))
    return shots


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = opt(args, "--out", os.path.join(R.K.ROOT, "Saved", "M6Base", "renders"))
    res_s = opt(args, "--res", "900x750")
    res = (int(res_s.split("x")[0]), int(res_s.split("x")[1]))
    samples = int(opt(args, "--samples", "32"))
    views = opt(args, "--views", "hero,front").split(",")
    mods = opt(args, "--mods", "all")
    os.makedirs(out, exist_ok=True)
    t0 = time.time()
    all_shots = []
    for fname, tag in MODULES:
        if mods != "all" and tag not in mods.split(","):
            continue
        blend = os.path.join(R.K.ROOT, "model", "m6", "base", fname)
        if not os.path.exists(blend):
            print("SKIP missing %s" % blend)
            continue
        all_shots += shoot(blend, tag, out, res, samples, views)
    print("HEADLESS " + json.dumps({"shots": all_shots, "total_sec": round(time.time() - t0, 1)},
                                   ensure_ascii=False))


if __name__ == "__main__":
    main()
