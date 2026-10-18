# -*- coding: utf-8 -*-
"""Compare the three importable files in the XReconstruct package.

For each: import, measure the *vertex-level* world bbox (not bound_box), report
object/mesh counts, and render one auto-framed 3/4 view.  This decides whether
the .glb is the full Palace of Culture scan or only a chunk of it.
"""
import bpy
import json
import math
import os
from mathutils import Vector

BASE = (r"E:\AI\Tread\Tread\model\warsaw\华沙001 - X重建(Warsaw 001 - XReco_爱给网_aigei_com")
OUT = r"E:\AI\Tread\Tread\Saved\Warsaw\renders"
os.makedirs(OUT, exist_ok=True)

FILES = [
    ("glb", os.path.join(BASE, "warsaw_001_-_xreconstruct.glb")),
    ("gltf", os.path.join(BASE, "warsaw-001-xreconstruct", "scene.gltf")),
    ("usdz", os.path.join(BASE, "Warsaw_001_-_XReconstruct.usdz")),
]

rep = []
for tag, path in FILES:
    rec = {"format": tag, "path": path, "exists": os.path.exists(path)}
    if not rec["exists"]:
        rep.append(rec)
        continue
    rec["bytes"] = os.path.getsize(path)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    try:
        if tag == "usdz":
            try:
                bpy.ops.wm.usd_import(filepath=path)
            except Exception:
                bpy.ops.import_scene.usd(filepath=path)
        else:
            bpy.ops.import_scene.gltf(filepath=path)
        rec["import_ok"] = True
    except Exception as e:
        rec["import_ok"] = False
        rec["error"] = "%s: %s" % (type(e).__name__, e)
        rep.append(rec)
        continue

    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    mn = [1e18] * 3
    mx = [-1e18] * 3
    tris = 0
    verts = 0
    for o in meshes:
        mw = o.matrix_world
        me = o.data
        verts += len(me.vertices)
        me.calc_loop_triangles()
        tris += len(me.loop_triangles)
        for v in me.vertices:
            w = mw @ v.co
            for i in range(3):
                mn[i] = min(mn[i], w[i])
                mx[i] = max(mx[i], w[i])
    rec.update({"objects": len(bpy.data.objects), "meshes": len(meshes),
                "verts": verts, "tris": tris,
                "bbox_min": [round(v, 2) for v in mn],
                "bbox_max": [round(v, 2) for v in mx],
                "size": [round(mx[i] - mn[i], 2) for i in range(3)]})

    # render one auto-framed 3/4 view
    try:
        ctr = Vector(((mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, (mn[2] + mx[2]) / 2))
        span = max(mx[i] - mn[i] for i in range(3))
        cam_d = bpy.data.cameras.new("C")
        cam_d.lens = 50
        cam_d.clip_start = 0.1
        cam_d.clip_end = 10000
        cam = bpy.data.objects.new("C", cam_d)
        bpy.context.scene.collection.objects.link(cam)
        cam.location = ctr + Vector((1.0, -1.35, 0.75)).normalized() * span * 2.0
        d = ctr - cam.location
        cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        bpy.context.scene.camera = cam
        sd = bpy.data.lights.new("S", type="SUN")
        sd.energy = 3.0
        so = bpy.data.objects.new("S", sd)
        so.rotation_euler = (0.9, 0.0, 0.8)
        bpy.context.scene.collection.objects.link(so)
        w = bpy.data.worlds.new("W")
        w.use_nodes = True
        w.node_tree.nodes["Background"].inputs[0].default_value = (0.6, 0.68, 0.78, 1)
        w.node_tree.nodes["Background"].inputs[1].default_value = 0.7
        bpy.context.scene.world = w
        sc = bpy.context.scene
        sc.render.engine = "BLENDER_EEVEE"
        sc.render.resolution_x = 900
        sc.render.resolution_y = 760
        p = os.path.join(OUT, "xreco_fmt_%s.png" % tag)
        sc.render.filepath = p
        sc.render.image_settings.file_format = "PNG"
        bpy.ops.render.render(write_still=True)
        rec["render"] = p
    except Exception as e:
        rec["render_error"] = "%s: %s" % (type(e).__name__, e)
    rep.append(rec)

print("HEADLESS " + json.dumps({"formats": rep}, ensure_ascii=False))
