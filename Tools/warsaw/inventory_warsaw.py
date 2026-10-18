# -*- coding: utf-8 -*-
"""Inventory every Warsaw asset the author published: import, measure, thumbnail.

For each .glb: vertex bbox, mesh/tri counts, tallest structure (tower detector),
and one auto-framed render.  Sequential with a factory reset between assets.
"""
import bpy
import json
import os
from mathutils import Vector

BASE = r"E:\AI\Tread\Tread\model\warsaw"
OUT = r"E:\AI\Tread\Tread\Saved\Warsaw\renders"
os.makedirs(OUT, exist_ok=True)

ASSETS = [
    ("warsaw001", os.path.join(BASE, "华沙001 - X重建(Warsaw 001 - XReco_爱给网_aigei_com",
                               "warsaw_001_-_xreconstruct.glb")),
    ("warsaw002", os.path.join(BASE, "华沙002 - X重建(Warsaw 002 - XReco_爱给网_aigei_com",
                               "warsaw_002_-_xreconstruct.glb")),
    ("mapI", os.path.join(BASE, "尸体痕迹-华沙3D地图I(Body traces - War_爱给网_aigei_com",
                          "body_traces_-_warsaw_3d_map_i.glb")),
    ("mapIV", os.path.join(BASE, "尸体痕迹-华沙3D地图IV(Body traces - Wa_爱给网_aigei_com",
                           "body_traces_-_warsaw_3d_map_iv.glb")),
    ("mapXVI", os.path.join(BASE, "尸体痕迹-华沙3D地图XVI(Body traces - W_爱给网_aigei_com",
                            "body_traces_-_warsaw_3d_map_xvi.glb")),
    ("mapXIX", os.path.join(BASE, "尸体痕迹-华沙3D地图XIX(Body traces - W_爱给网_aigei_com",
                            "body_traces_-_warsaw_3d_map_xix.glb")),
]

rep = []
for tag, path in ASSETS:
    rec = {"tag": tag, "exists": os.path.exists(path)}
    if not rec["exists"]:
        rec["path"] = path
        rep.append(rec)
        continue
    rec["bytes"] = os.path.getsize(path)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    try:
        bpy.ops.import_scene.gltf(filepath=path)
    except Exception as e:
        rec["error"] = "%s: %s" % (type(e).__name__, e)
        rep.append(rec)
        continue

    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    mn = [1e18] * 3
    mx = [-1e18] * 3
    tris = 0
    verts = 0
    tallest = None
    for o in meshes:
        mw = o.matrix_world
        me = o.data
        verts += len(me.vertices)
        me.calc_loop_triangles()
        tris += len(me.loop_triangles)
        omn = [1e18] * 3
        omx = [-1e18] * 3
        for v in me.vertices:
            w = mw @ v.co
            for i in range(3):
                omn[i] = min(omn[i], w[i])
                omx[i] = max(omx[i], w[i])
                mn[i] = min(mn[i], w[i])
                mx[i] = max(mx[i], w[i])
        h = omx[2] - omn[2]
        if tallest is None or h > tallest["h"]:
            tallest = {"name": o.name, "h": round(h, 2),
                       "foot": [round(omx[0] - omn[0], 2), round(omx[1] - omn[1], 2)],
                       "z0": round(omn[2], 2), "z1": round(omx[2], 2)}
    rec.update({"meshes": len(meshes), "verts": verts, "tris": tris,
                "size": [round(mx[i] - mn[i], 1) for i in range(3)],
                "z_range": [round(mn[2], 1), round(mx[2], 1)],
                "tallest": tallest})

    # thumbnail
    try:
        sc = bpy.context.scene
        ctr = Vector(((mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, (mn[2] + mx[2]) / 2))
        span = max(mx[i] - mn[i] for i in range(3))
        cam_d = bpy.data.cameras.new("C")
        cam_d.lens = 50
        cam_d.clip_start = max(span * 0.001, 0.01)
        cam_d.clip_end = span * 50
        cam = bpy.data.objects.new("C", cam_d)
        sc.collection.objects.link(cam)
        sc.camera = cam
        cam.location = ctr + Vector((1.0, -1.3, 0.45)).normalized() * span * 1.15
        cam.rotation_euler = (ctr - cam.location).to_track_quat("-Z", "Y").to_euler()
        sd = bpy.data.lights.new("S", type="SUN")
        sd.energy = 3.4
        so = bpy.data.objects.new("S", sd)
        so.rotation_euler = (0.85, 0.05, 0.75)
        sc.collection.objects.link(so)
        w = bpy.data.worlds.new("W")
        w.use_nodes = True
        w.node_tree.nodes["Background"].inputs[0].default_value = (0.58, 0.66, 0.78, 1)
        w.node_tree.nodes["Background"].inputs[1].default_value = 0.85
        sc.world = w
        sc.render.engine = "BLENDER_EEVEE"
        sc.render.resolution_x = 760
        sc.render.resolution_y = 480
        sc.render.image_settings.file_format = "PNG"
        p = os.path.join(OUT, "inv_%s.png" % tag)
        sc.render.filepath = p
        bpy.ops.render.render(write_still=True)
        rec["shot"] = p
    except Exception as e:
        rec["render_error"] = "%s: %s" % (type(e).__name__, e)
    rep.append(rec)

print("HEADLESS " + json.dumps({"assets": rep}, ensure_ascii=False))
