# -*- coding: utf-8 -*-
"""Showcase lineup: all five landmarks at 1:1, in a row, one render."""
import bpy
import math
import os
import json

LM_DIR = r"E:\AI\Tread\Tread\model\warsaw\landmarks"
OUT = r"E:\AI\Tread\Tread\Saved\Warsaw\renders\shot_lineup.png"

ITEMS = [
    ("Warsaw_01_Rynek.blend", "COL_LM_RYNEK", "LM_RYNEK", -740.0, 0.0),
    ("Warsaw_02_Zamek.blend", "COL_LM_ZAMEK", "LM_ZAMEK", -578.0, 70.0),
    ("Warsaw_03_Barbakan.blend", "COL_LM_BARBAKAN", "LM_BARBAKAN", -432.0, 0.0),
    ("Warsaw_04_Lazienki.blend", "COL_LM_LAZIENKI", "LM_LAZIENKI", -269.0, 25.0),
    ("Warsaw_06_PKin.blend", "COL_LM_PKIN", "LM_PKIN", -65.0, 0.0),
    ("Warsaw_05_Stadion.blend", "COL_LM_STADION", "LM_STADION", 236.0, 0.0),
]

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
top = bpy.data.collections.new("COL_LINEUP")
sc.collection.children.link(top)
rep = []
for fname, cname, root_name, x, y in ITEMS:
    path = os.path.join(LM_DIR, fname)
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.collections = [cname]
    coll = dst.collections[0]
    top.children.link(coll)
    root = bpy.data.objects.get(root_name)
    if root:
        root.location = (x, y, 0.0)
    rep.append({"landmark": cname, "x": x, "y": y,
                "meshes": len([o for o in coll.all_objects if o.type == "MESH"])})


def srgb(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


w = bpy.data.worlds.new("W")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.60, 0.70, 0.83, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 0.55
sc.world = w
ld = bpy.data.lights.new("SUN", type="SUN")
ld.energy = 4.0
ld.angle = 0.05
lo = bpy.data.objects.new("SUN", ld)
lo.rotation_euler = (math.radians(50), 0.0, math.radians(38))
sc.collection.objects.link(lo)

# ground slab
import bmesh
me = bpy.data.meshes.new("GEO-LINEUP-GROUND")
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=1.0)
for v in bm.verts:
    v.co.x = v.co.x * 5200 + 300
    v.co.y = v.co.y * 4600
    v.co.z = (v.co.z - 0.5) * 2.4
bm.to_mesh(me)
bm.free()
gmat = bpy.data.materials.new("lineup_ground")
gmat.use_nodes = True
gmat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (
    srgb(0.26), srgb(0.27), srgb(0.24), 1.0)
gmat.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.92
me.materials.append(gmat)
go = bpy.data.objects.new("GEO-LINEUP-GROUND", me)
top.objects.link(go)

cam_d = bpy.data.cameras.new("CAM")
cam_d.lens = 45
cam_d.clip_start = 5.0
cam_d.clip_end = 20000.0
cam = bpy.data.objects.new("CAM", cam_d)
cam.location = (-200, -1700, 400)
from mathutils import Vector
d = Vector((-200, 40, -20)) - cam.location
cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
sc.collection.objects.link(cam)
sc.camera = cam

sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = 1600
sc.render.resolution_y = 760
sc.render.film_transparent = False
sc.render.filepath = OUT
sc.render.image_settings.file_format = "PNG"
try:
    sc.eevee.taa_render_samples = 48
except Exception:
    pass
bpy.ops.render.render(write_still=True)

print("HEADLESS " + json.dumps({"lineup": rep, "png": OUT,
                                "objects": len([o for o in bpy.data.objects if o.type == "MESH"])},
                               ensure_ascii=False))
