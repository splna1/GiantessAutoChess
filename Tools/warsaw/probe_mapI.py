# -*- coding: utf-8 -*-
"""Map I at proper framing: ortho plan + low oblique, plus the tallest point
(should be the Palace of Culture spire) with its XY and height."""
import bpy
import json
import math
import os
from mathutils import Vector

GLB = (r"E:\AI\Tread\Tread\model\warsaw\尸体痕迹-华沙3D地图I(Body traces - War_爱给网_aigei_com"
       r"\body_traces_-_warsaw_3d_map_i.glb")
OUT = r"E:\AI\Tread\Tread\Saved\Warsaw\renders"

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)

mn = [1e18] * 3
mx = [-1e18] * 3
top_verts = []
for o in bpy.data.objects:
    if o.type != "MESH":
        continue
    mw = o.matrix_world
    for v in o.data.vertices:
        w = mw @ v.co
        for i in range(3):
            mn[i] = min(mn[i], w[i])
            mx[i] = max(mx[i], w[i])
        top_verts.append((w.z, w.x, w.y))
top_verts.sort(reverse=True)
peaks = [{"z": round(z, 1), "xy": [round(x, 1), round(y, 1)]} for z, x, y in top_verts[:6]]

ctr = Vector(((mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, (mn[2] + mx[2]) / 2))
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.image_settings.file_format = "PNG"
w = bpy.data.worlds.new("W")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.62, 0.70, 0.82, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 1.0
sc.world = w
sd = bpy.data.lights.new("S", type="SUN")
sd.energy = 3.6
so = bpy.data.objects.new("S", sd)
so.rotation_euler = (0.75, 0.0, 0.6)
sc.collection.objects.link(so)

cam_d = bpy.data.cameras.new("C")
cam_d.clip_start = 1.0
cam_d.clip_end = 200000
cam = bpy.data.objects.new("C", cam_d)
sc.collection.objects.link(cam)
sc.camera = cam
shots = []

# 1) ortho plan over the whole map
cam_d.type = "ORTHO"
cam_d.ortho_scale = 32000
cam.location = (ctr.x, ctr.y, mx[2] + 8000)
cam.rotation_euler = (0, 0, 0)
sc.render.resolution_x = 900
sc.render.resolution_y = 520
p = os.path.join(OUT, "mapI_plan.png")
sc.render.filepath = p
bpy.ops.render.render(write_still=True)
shots.append(p)

# 2) low oblique across the centre, camera 4 km up / 12 km south
cam_d.type = "PERSP"
cam_d.lens = 70
look = Vector((ctr.x + 2000, ctr.y, mn[2] + 120))
cam.location = look + Vector((0.25, -1.0, 0.30)).normalized() * 12000
cam.rotation_euler = (look - cam.location).to_track_quat("-Z", "Y").to_euler()
sc.render.resolution_x = 1100
sc.render.resolution_y = 620
p = os.path.join(OUT, "mapI_oblique.png")
sc.render.filepath = p
bpy.ops.render.render(write_still=True)
shots.append(p)

print("HEADLESS " + json.dumps({
    "size": [round(mx[i] - mn[i], 1) for i in range(3)],
    "z_range": [round(mn[2], 1), round(mx[2], 1)],
    "peaks": peaks,
    "shots": shots,
}, ensure_ascii=False))
