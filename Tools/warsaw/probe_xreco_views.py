# -*- coding: utf-8 -*-
"""Identify the XReconstruct scan: 5 ortho views + downscaled textures.

Writes PNGs to Saved/Warsaw/renders/xreco_*.png so the scan can be identified
(and its proportions measured) before modelling the Palace of Culture.
"""
import bpy
import math
import os
import json
from mathutils import Vector

GLB = (r"E:\AI\Tread\Tread\model\warsaw\华沙001 - X重建(Warsaw 001 - XReco_爱给网_aigei_com"
       r"\warsaw_001_-_xreconstruct.glb")
OUT = r"E:\AI\Tread\Tread\Saved\Warsaw\renders"
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)

meshes = [o for o in bpy.data.objects if o.type == "MESH"]
mn = [1e18] * 3
mx = [-1e18] * 3
for o in meshes:
    for c in o.bound_box:
        w = o.matrix_world @ Vector(c)
        for i in range(3):
            mn[i] = min(mn[i], w[i])
            mx[i] = max(mx[i], w[i])
ctr = [(mn[i] + mx[i]) / 2 for i in range(3)]
size = [mx[i] - mn[i] for i in range(3)]

sc = bpy.context.scene
cam_d = bpy.data.cameras.new("C")
cam_d.type = "ORTHO"
cam_d.ortho_scale = max(size) * 1.12
cam_d.clip_start = 0.5
cam_d.clip_end = 500.0
cam = bpy.data.objects.new("C", cam_d)
sc.collection.objects.link(cam)
sc.camera = cam

sun_d = bpy.data.lights.new("S", type="SUN")
sun_d.energy = 3.0
sun = bpy.data.objects.new("S", sun_d)
sun.rotation_euler = (0.9, 0.0, 0.8)
sc.collection.objects.link(sun)
w = bpy.data.worlds.new("W")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.62, 0.70, 0.80, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 0.85
sc.world = w
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = 900
sc.render.resolution_y = 900
sc.render.image_settings.file_format = "PNG"

views = [("front", Vector((0, -1, 0))), ("right", Vector((1, 0, 0))),
         ("back", Vector((0, 1, 0))), ("left", Vector((-1, 0, 0))),
         ("top", Vector((0, -0.001, 1)))]
made = []
for name, d in views:
    d = d.normalized()
    cam.location = Vector(ctr) + d * (max(size) * 3.0)
    fwd = -d
    up = Vector((0, 0, 1))
    if abs(fwd.dot(up)) > 0.99:
        up = Vector((0, 1, 0))
    z = -fwd
    y = (up - z * up.dot(z)).normalized()
    x = y.cross(z).normalized()
    from mathutils import Matrix
    rot = Matrix((x, y, z)).transposed().to_4x4()
    cam.rotation_euler = rot.to_euler()
    p = os.path.join(OUT, "xreco_%s.png" % name)
    sc.render.filepath = p
    bpy.ops.render.render(write_still=True)
    made.append({"view": name, "png": p})

tex = []
for im in bpy.data.images:
    if im.size[0] == 0:
        continue
    im.scale(1200, 1200)
    p = os.path.join(OUT, "xreco_tex_%s.png" % im.name.replace(".", "_"))
    im.filepath_raw = p
    im.file_format = "PNG"
    try:
        im.save()
        tex.append({"image": im.name, "png": p})
    except Exception as e:
        tex.append({"image": im.name, "error": str(e)})

print("HEADLESS " + json.dumps({"bbox_min": [round(v, 2) for v in mn],
                                "bbox_max": [round(v, 2) for v in mx],
                                "size": [round(v, 2) for v in size],
                                "views": made, "textures": tex},
                               ensure_ascii=False))
