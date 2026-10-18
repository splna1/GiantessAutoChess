# -*- coding: utf-8 -*-
"""Re-render the realistic board: ortho plan of the deployment grid + a clean
Old Town three-quarter view (the previous core camera sat inside a map block)."""
import bpy
import math
import os
from mathutils import Vector

BLEND = r"E:\AI\Tread\Tread\model\warsaw\landmarks\Warsaw_Board_Realistic.blend"
OUT = r"E:\AI\Tread\Tread\Saved\Warsaw\renders"
bpy.ops.wm.open_mainfile(filepath=BLEND)

sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.image_settings.file_format = "PNG"

cam = bpy.data.objects.get("BOARD_CAM")
if cam is None:
    cd = bpy.data.cameras.new("BOARD_CAM")
    cam = bpy.data.objects.new("BOARD_CAM", cd)
    sc.collection.objects.link(cam)
sc.camera = cam
cam.data.clip_start = 0.5
cam.data.clip_end = 80000.0

views = [
    # ortho plan: the 8x8 deployment grid over the real city
    ("board_plan_grid", "ORTHO", (70.0, -30.0, 2400.0), (70.0, -30.0, 0.0), 0, 1900.0, 1200, 1200),
    # Old Town cluster from the south-east, above the roof line
    ("board_core_se", "PERSP", (430.0, -430.0, 210.0), (10.0, 10.0, 35.0), 50, 0, 1200, 800),
    # whole board
    ("board_wide", "PERSP", (900.0, -6000.0, 2400.0), (900.0, -1600.0, 0.0), 32, 0, 1400, 900),
]
for name, kind, pos, look, lens, oscale, rx, ry in views:
    cam.data.type = kind
    if kind == "ORTHO":
        cam.data.ortho_scale = oscale
    else:
        cam.data.lens = lens
    cam.location = pos
    d = Vector(look) - Vector(pos)
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    sc.render.resolution_x = rx
    sc.render.resolution_y = ry
    p = os.path.join(OUT, name + ".png")
    sc.render.filepath = p
    bpy.ops.render.render(write_still=True)
    print("SHOT " + p)
