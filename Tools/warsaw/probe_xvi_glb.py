# -*- coding: utf-8 -*-
"""Import the XVI .glb (embedded textures) and render it properly."""
import bpy
import json
import os
from mathutils import Vector

GLB = (r"E:\AI\Tread\Tread\model\warsaw\尸体痕迹-华沙3D地图XVI(Body traces - W_爱给网_aigei_com"
       r"\body_traces_-_warsaw_3d_map_xvi.glb")
OUT = r"E:\AI\Tread\Tread\Saved\Warsaw\renders"

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)

meshes = [o for o in bpy.data.objects if o.type == "MESH"]
mn = [1e18] * 3
mx = [-1e18] * 3
tris = 0
for o in meshes:
    mw = o.matrix_world
    me = o.data
    me.calc_loop_triangles()
    tris += len(me.loop_triangles)
    for v in me.vertices:
        w = mw @ v.co
        for i in range(3):
            mn[i] = min(mn[i], w[i])
            mx[i] = max(mx[i], w[i])

sc = bpy.context.scene
ctr = Vector(((mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, (mn[2] + mx[2]) / 2))
span = max(mx[i] - mn[i] for i in range(3))
cam_d = bpy.data.cameras.new("C")
cam_d.lens = 50
cam_d.clip_start = 0.1
cam_d.clip_end = 5000
cam = bpy.data.objects.new("C", cam_d)
sc.collection.objects.link(cam)
sc.camera = cam
sd = bpy.data.lights.new("S", type="SUN")
sd.energy = 3.2
so = bpy.data.objects.new("S", sd)
so.rotation_euler = (0.8, 0.05, 0.75)
sc.collection.objects.link(so)
w = bpy.data.worlds.new("W")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.58, 0.66, 0.78, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 0.9
sc.world = w
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = 1200
sc.render.resolution_y = 760
sc.render.image_settings.file_format = "PNG"

shots = []
for name, dirv, mul in (("xvi_glb_34", Vector((1.0, -1.25, 0.42)), 1.05),
                        ("xvi_glb_top", Vector((0.01, -0.02, 1.0)), 1.05),
                        ("xvi_glb_close", Vector((1.0, -1.1, 0.22)), 0.30)):
    d = dirv.normalized()
    cam.location = ctr + d * span * mul
    cam.rotation_euler = (ctr - cam.location).to_track_quat("-Z", "Y").to_euler()
    p = os.path.join(OUT, "%s.png" % name)
    sc.render.filepath = p
    bpy.ops.render.render(write_still=True)
    shots.append(p)

imgs = [{"name": i.name, "size": list(i.size), "packed": bool(i.packed_file)}
        for i in bpy.data.images if i.size[0] > 0]
print("HEADLESS " + json.dumps({
    "meshes": len(meshes), "tris": tris,
    "bbox": [round(v, 2) for v in mn] + [round(v, 2) for v in mx],
    "size": [round(mx[i] - mn[i], 2) for i in range(3)],
    "images": imgs[:6], "shots": shots}, ensure_ascii=False))
