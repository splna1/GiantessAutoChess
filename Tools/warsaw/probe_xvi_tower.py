# -*- coding: utf-8 -*-
"""Find the tower in the XVI 3D map and measure its proportions."""
import bpy
import json
import os
from mathutils import Vector

GLB = (r"E:\AI\Tread\Tread\model\warsaw\尸体痕迹-华沙3D地图XVI(Body traces - W_爱给网_aigei_com"
       r"\body_traces_-_warsaw_3d_map_xvi.glb")
OUT = r"E:\AI\Tread\Tread\Saved\Warsaw\renders"

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)

rows = []
for o in bpy.data.objects:
    if o.type != "MESH":
        continue
    mw = o.matrix_world
    mn = [1e18] * 3
    mx = [-1e18] * 3
    for v in o.data.vertices:
        w = mw @ v.co
        for i in range(3):
            mn[i] = min(mn[i], w[i])
            mx[i] = max(mx[i], w[i])
    dx, dy, dz = (mx[i] - mn[i] for i in range(3))
    foot = max(dx, dy, 1e-3)
    rows.append({"name": o.name, "h": round(dz, 3), "dx": round(dx, 3), "dy": round(dy, 3),
                 "xy": [round((mn[0] + mx[0]) / 2, 2), round((mn[1] + mx[1]) / 2, 2)],
                 "z0": round(mn[2], 3), "z1": round(mx[2], 3),
                 "aspect": round(dz / foot, 2), "tris": len(o.data.polygons)})

by_h = sorted(rows, key=lambda r: -r["h"])
by_aspect = sorted([r for r in rows if r["h"] > 0.4], key=lambda r: -r["aspect"])
rep = {"objects": len(rows), "top_by_height": by_h[:8], "top_by_aspect": by_aspect[:8]}

# frame the most tower-like object
t = by_aspect[0]
cx, cy = t["xy"]
z0, z1 = t["z0"], t["z1"]
h = z1 - z0
ctr = Vector((cx, cy, (z0 + z1) / 2))

sc = bpy.context.scene
cam_d = bpy.data.cameras.new("C")
cam_d.lens = 60
cam_d.clip_start = 0.01
cam_d.clip_end = 500
cam = bpy.data.objects.new("C", cam_d)
sc.collection.objects.link(cam)
sc.camera = cam
sd = bpy.data.lights.new("S", type="SUN")
sd.energy = 3.5
so = bpy.data.objects.new("S", sd)
so.rotation_euler = (0.85, 0.05, 0.75)
sc.collection.objects.link(so)
w = bpy.data.worlds.new("W")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.58, 0.66, 0.78, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 0.9
sc.world = w
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = 760
sc.render.resolution_y = 900
sc.render.image_settings.file_format = "PNG"

d = Vector((1.0, -1.2, 0.30)).normalized()
cam.location = ctr + d * max(h * 2.4, 2.0)
cam.rotation_euler = (ctr - cam.location).to_track_quat("-Z", "Y").to_euler()
p = os.path.join(OUT, "xvi_tower.png")
sc.render.filepath = p
bpy.ops.render.render(write_still=True)

rep["tower"] = t
rep["shot"] = p
print("HEADLESS " + json.dumps(rep, ensure_ascii=False))
