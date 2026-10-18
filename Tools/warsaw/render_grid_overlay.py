# -*- coding: utf-8 -*-
"""Render the deployment grid as a clean overlay: pass A = scene, pass B = grid
only on transparent film, then alpha-composite with numpy so the white square
lines are never hidden by buildings."""
import bpy
import math
import os
import numpy as np
from mathutils import Vector

BLEND = r"E:\AI\Tread\Tread\model\warsaw\landmarks\Warsaw_Board_Realistic.blend"
OUT = r"E:\AI\Tread\Tread\Saved\Warsaw\renders"
bpy.ops.wm.open_mainfile(filepath=BLEND)

sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.color_mode = "RGBA"
sc.render.film_transparent = False

cam = bpy.data.objects.get("BOARD_CAM")
if cam is None:
    cd = bpy.data.cameras.new("BOARD_CAM")
    cam = bpy.data.objects.new("BOARD_CAM", cd)
    sc.collection.objects.link(cam)
sc.camera = cam
cam.data.clip_start = 0.5
cam.data.clip_end = 80000.0

VIEWS = [
    ("board_plan_grid", "ORTHO", (70.0, -30.0, 2400.0), (70.0, -30.0, 0.0), 0, 1900.0, 1200, 1200),
    ("board_real_grid", "PERSP", (70.0, -1150.0, 780.0), (70.0, -30.0, 0.0), 32, 0, 1200, 900),
]

grid = bpy.data.objects.get("GEO-DEPLOY-GRID")
others = [o for o in bpy.data.objects if o is not grid and o.type in ("MESH", "EMPTY")]


def render_to(path):
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def load_rgba(path):
    im = bpy.data.images.load(path)
    w, h = im.size
    a = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)
    bpy.data.images.remove(im)
    return a


for name, kind, pos, look, lens, oscale, rx, ry in VIEWS:
    cam.data.type = kind
    if kind == "ORTHO":
        cam.data.ortho_scale = oscale
    else:
        cam.data.lens = lens
    cam.location = pos
    cam.rotation_euler = (Vector(look) - Vector(pos)).to_track_quat("-Z", "Y").to_euler()
    sc.render.resolution_x, sc.render.resolution_y = rx, ry

    # pass A: the city
    for o in others:
        o.hide_render = False
    grid.hide_render = True
    sc.render.film_transparent = False
    a_path = os.path.join(OUT, "_A_%s.png" % name)
    render_to(a_path)

    # pass B: grid only, transparent film
    for o in others:
        o.hide_render = True
    grid.hide_render = False
    sc.render.film_transparent = True
    b_path = os.path.join(OUT, "_B_%s.png" % name)
    render_to(b_path)

    A = load_rgba(a_path)
    B = load_rgba(b_path)
    al = B[:, :, 3:4]
    out = A[:, :, :3] * (1.0 - al) + B[:, :, :3] * al
    rgba = np.concatenate([out, np.ones_like(al)], axis=2)

    im = bpy.data.images.new(name, A.shape[1], A.shape[0], alpha=False)
    im.pixels = rgba.ravel().tolist()
    p = os.path.join(OUT, name + ".png")
    im.filepath_raw = p
    im.file_format = "PNG"
    im.save()
    bpy.data.images.remove(im)
    print("OVERLAY " + p)

# restore
for o in others:
    o.hide_render = False
grid.hide_render = False
sc.render.film_transparent = False
