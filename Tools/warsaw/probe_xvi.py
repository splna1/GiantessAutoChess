# -*- coding: utf-8 -*-
"""Inspect "Body traces - Warsaw 3D MAP XVI": open the author's .blend, report
object/material stats, the tallest structures (does it contain the Palace of
Culture?), and render 3 auto-framed views."""
import bpy
import json
import math
import os
from mathutils import Vector

BLEND = (r"E:\AI\Tread\Tread\model\warsaw\尸体痕迹-华沙3D地图XVI(Body traces - W_爱给网_aigei_com"
         r"\body-traces-warsaw-3d-map-xvi\source\Sketchfab_2023_03_09_23_39_51.blend")
OUT = r"E:\AI\Tread\Tread\Saved\Warsaw\renders"
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.open_mainfile(filepath=BLEND)

meshes = [o for o in bpy.data.objects if o.type == "MESH"]
mn = [1e18] * 3
mx = [-1e18] * 3
verts = 0
tris = 0
per_obj = []
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
    per_obj.append({"name": o.name, "tris": len(me.loop_triangles),
                    "z0": round(omn[2], 1), "z1": round(omx[2], 1),
                    "h": round(omx[2] - omn[2], 1),
                    "xy": [round((omn[0] + omx[0]) / 2, 1), round((omn[1] + omx[1]) / 2, 1)]})

per_obj.sort(key=lambda r: -r["h"])
tallest = per_obj[:12]

# z histogram (10 buckets)
hist = [0] * 10
for o in meshes:
    mw = o.matrix_world
    for v in o.data.vertices:
        z = (mw @ v.co).z
        k = int((z - mn[2]) / max(1e-6, (mx[2] - mn[2])) * 9.999)
        hist[max(0, min(9, k))] += 1

sc = bpy.context.scene
ctr = Vector(((mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, (mn[2] + mx[2]) / 2))
span = max(mx[i] - mn[i] for i in range(3))

cam_d = bpy.data.cameras.new("C")
cam_d.lens = 50
cam_d.clip_start = 0.5
cam_d.clip_end = 50000
cam = bpy.data.objects.new("C", cam_d)
sc.collection.objects.link(cam)
sc.camera = cam
sd = bpy.data.lights.new("S", type="SUN")
sd.energy = 3.6
so = bpy.data.objects.new("S", sd)
so.rotation_euler = (0.85, 0.05, 0.7)
sc.collection.objects.link(so)
w = bpy.data.worlds.new("W")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.64, 0.76, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 0.8
sc.world = w
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = 1200
sc.render.resolution_y = 760
sc.render.image_settings.file_format = "PNG"

shots = []
for name, dirv, dist_mul, look in (
        ("xvi_34", Vector((1.0, -1.3, 0.55)), 1.15, ctr),
        ("xvi_top", Vector((0.02, -0.05, 1.0)), 1.15, ctr),
        ("xvi_tall", Vector((1.0, -1.2, 0.35)), 0.22, ctr)):
    d = dirv.normalized()
    cam.location = look + d * span * dist_mul
    cam.rotation_euler = (look - cam.location).to_track_quat("-Z", "Y").to_euler()
    p = os.path.join(OUT, "%s.png" % name)
    sc.render.filepath = p
    bpy.ops.render.render(write_still=True)
    shots.append(p)

rep = {
    "objects_total": len(bpy.data.objects),
    "meshes": len(meshes),
    "verts": verts,
    "tris": tris,
    "bbox_min": [round(v, 1) for v in mn],
    "bbox_max": [round(v, 1) for v in mx],
    "size": [round(mx[i] - mn[i], 1) for i in range(3)],
    "materials": [m.name for m in bpy.data.materials][:12],
    "images": [{"name": i.name, "size": list(i.size)} for i in bpy.data.images][:10],
    "tallest": tallest,
    "z_histogram": hist,
    "shots": shots,
}
print("HEADLESS " + json.dumps(rep, ensure_ascii=False))
