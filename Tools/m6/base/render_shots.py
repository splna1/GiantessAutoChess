# -*- coding: utf-8 -*-
"""Render a module .blend with fixed, repeatable views (projection-fitted).

Usage (headless):
    blender -b --factory-startup --python render_shots.py -- \
        --blend <blend> --out <dir> --tag C2 --engine cycles --samples 96 \
        --res 1600x1000 --views hero,front,aerial,detail,entry
"""
import json
import math
import os
import sys
import time

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import lib_kit as K


def argv_after_dd():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(args, name, default=None):
    if name in args:
        i = args.index(name)
        if i + 1 < len(args):
            return args[i + 1]
    return default


def scene_meshes():
    return [o for o in bpy.context.scene.objects
            if o.type == "MESH" and not o.name.startswith("GEO-shot")]


def bounds(objs):
    mn = Vector((1e9, 1e9, 1e9))
    mx = Vector((-1e9, -1e9, -1e9))
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            for i in range(3):
                mn[i] = min(mn[i], w[i])
                mx[i] = max(mx[i], w[i])
    return mn, mx


def set_engine(name, samples):
    sc = bpy.context.scene
    want = "CYCLES" if name == "cycles" else "BLENDER_EEVEE"
    # NOTE: in this build the engine enum only reports BLENDER_EEVEE even
    # though CYCLES is accepted on assignment -- so assign, don't filter.
    for cand in (want, "CYCLES", "BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            sc.render.engine = cand
            break
        except Exception:
            continue
    if sc.render.engine == "CYCLES":
        sc.cycles.samples = samples
        sc.cycles.use_denoising = True
        sc.cycles.max_bounces = 6
        sc.cycles.diffuse_bounces = 3
        sc.cycles.glossy_bounces = 3
        try:
            sc.cycles.device = "GPU"
        except Exception:
            sc.cycles.device = "CPU"
    else:
        try:
            sc.eevee.taa_render_samples = samples
            sc.eevee.use_raytracing = True
            sc.eevee.ray_tracing_options.resolution_scale = "1"
        except Exception:
            pass
    return sc.render.engine


def make_cam():
    name = "GEO-shot-cam"
    cam = bpy.data.cameras.get(name) or bpy.data.cameras.new(name)
    ob = bpy.data.objects.get(name)
    if ob is None:
        ob = bpy.data.objects.new(name, cam)
        bpy.context.scene.collection.objects.link(ob)
    ob.data = cam
    cam.sensor_width = 36.0
    cam.clip_start = 0.1
    cam.clip_end = 8000.0
    return ob


def fit(cam, corners, center, direction, lens, res, target=0.86):
    """Analytic fit: smallest distance where every bbox corner projects inside NDC.

    With the camera looking at `center` from `center + d*t`, a corner P projects to
    A/(t-B) where A = (P-c)·axis/tan(fov/2), B = (P-c)·d.  Solve t directly.
    """
    d = Vector(direction).normalized()
    cam.data.lens = lens
    tan_h = 0.5 * cam.data.sensor_width / lens
    tan_v = tan_h * res[1] / float(res[0])
    fwd = -d
    rot = fwd.to_track_quat("-Z", "Y")
    M = rot.to_matrix()
    X, Y = M.col[0], M.col[1]
    t = 1.0
    for P in corners:
        v = P - center
        B = v.dot(d)
        ax = abs(v.dot(X)) / tan_h
        ay = abs(v.dot(Y)) / tan_v
        need = B + max(ax, ay) / target
        t = max(t, need)
    t = max(t, 2.0)
    cam.location = center + d * t
    cam.rotation_euler = rot.to_euler()
    k = 0.0
    for P in corners:
        v = P - cam.location
        dep = v.dot(fwd)
        if dep > 0.05:
            k = max(k, abs(v.dot(X) / (dep * tan_h)), abs(v.dot(Y) / (dep * tan_v)))
    return k


def ensure_ground(center, size):
    name = "GEO-shot-ground"
    if bpy.data.objects.get(name):
        bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
    mb = K.MB("shot-ground")
    mb.box(center.x - size / 2, center.y - size / 2, -0.30,
           center.x + size / 2, center.y + size / 2, -0.02)
    ob = mb.emit(bpy.context.scene.collection, K.ground_mat(), name)
    for n in ("GEO-shot-rocks", "GEO-shot-bushes"):
        if bpy.data.objects.get(n):
            bpy.data.objects.remove(bpy.data.objects[n], do_unlink=True)
    K.scatter_rocks((center.x, center.y), r0=max(24.0, size * 0.03),
                    r1=min(size * 0.55, 420.0), rocks=320, bushes=200,
                    seed=int(abs(center.x * 7 + center.y * 13)) % 9973 + 1)
    return ob


def fill_light(center, radius, sun_dir):
    """Large soft area light opposite the sun to keep shadows readable."""
    name = "GEO-shot-fill"
    if bpy.data.objects.get(name):
        bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
    d = bpy.data.lights.new(name, type="AREA")
    d.shape = "DISK"
    d.size = max(30.0, radius * 2.2)
    d.energy = max(600.0, radius * radius * 1.5)
    d.color = (0.80, 0.86, 1.0)
    ob = bpy.data.objects.new(name, d)
    bpy.context.scene.collection.objects.link(ob)
    p = center + Vector(sun_dir).normalized() * (-radius * 3.2) + Vector((0, 0, radius * 1.6))
    ob.location = p
    ob.rotation_euler = (center - p).normalized().to_track_quat("-Z", "Y").to_euler()
    return ob


VIEWS = {
    "hero":   {"dir": (0.86, -1.00, 0.17), "lens": 62, "aim": 0.50},
    "front":  {"dir": (0.04, -1.00, 0.10), "lens": 55, "aim": 0.42},
    "aerial": {"dir": (0.40, -0.55, 1.00), "lens": 58, "aim": 0.50},
    "detail": {"dir": (0.95, -0.85, 0.24), "lens": 110, "aim": 0.72, "zoom": 0.48},
    "entry":  {"dir": (0.26, -1.00, 0.07), "lens": 45, "aim": 0.12, "zoom": 0.40},
    "back":   {"dir": (-0.60, 0.95, 0.42), "lens": 55, "aim": 0.42},
    "top":    {"dir": (0.02, -0.12, 1.00), "lens": 55, "aim": 0.50},
    "side":   {"dir": (1.00, 0.30, 0.20), "lens": 55, "aim": 0.42},
    "low":    {"dir": (0.95, -0.55, 0.16), "lens": 85, "aim": 0.20, "zoom": 0.42},
}


def main():
    args = argv_after_dd()
    blend = opt(args, "--blend")
    out = opt(args, "--out", os.path.join(K.ROOT, "Saved", "M6Base", "renders"))
    tag = opt(args, "--tag", "MOD")
    engine = opt(args, "--engine", "cycles")
    samples = int(opt(args, "--samples", "96"))
    res_s = opt(args, "--res", "1200x1000")
    res = (int(res_s.split("x")[0]), int(res_s.split("x")[1]))
    views = opt(args, "--views", "hero,front,aerial,detail").split(",")
    exposure = float(opt(args, "--exposure", "0.35"))
    fill = float(opt(args, "--fill", "0.90"))

    if blend:
        bpy.ops.wm.open_mainfile(filepath=blend)
        K.reset_cache()
    sc = bpy.context.scene
    os.makedirs(out, exist_ok=True)
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
    eng = set_engine(engine, samples)

    objs = scene_meshes()
    mn, mx = bounds(objs)
    center = (mn + mx) / 2.0
    radius = (mx - mn).length / 2.0
    corners = [Vector((x, y, z)) for x in (mn.x, mx.x) for y in (mn.y, mx.y) for z in (mn.z, mx.z)]
    ensure_ground(center, max(3000.0, radius * 60.0))
    fill_light(center, radius, (-0.80, 0.60, 0.45))
    cam = make_cam()
    sc.camera = cam

    shots = []
    t0 = time.time()
    for v in views:
        spec = VIEWS.get(v)
        if not spec:
            continue
        aim = center.copy()
        aim.z = mn.z + (mx.z - mn.z) * spec["aim"]
        z = fill * spec.get("zoom", 1.0)
        corners_v = [center + (c - center) * z for c in corners]
        k = fit(cam, corners_v, aim, spec["dir"], spec["lens"], res)
        if cam.location.z < 2.0:
            cam.location.z = 2.0
        path = os.path.join(out, "shot_%s_%s.png" % (tag, v))
        sc.render.filepath = path
        t = time.time()
        bpy.ops.render.render(write_still=True)
        shots.append({"view": v, "path": path, "sec": round(time.time() - t, 2),
                      "ndc": round(k, 3), "camera": [round(c, 2) for c in cam.location]})
    print("HEADLESS " + json.dumps({
        "tag": tag, "blend": blend, "engine": eng, "samples": samples,
        "res": list(res), "bbox": [round(v, 2) for v in list(mn) + list(mx)],
        "shots": shots, "total_sec": round(time.time() - t0, 2)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
