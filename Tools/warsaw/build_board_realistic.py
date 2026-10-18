# -*- coding: utf-8 -*-
"""Warsaw realistic board: map I as real city ground + landmarks at true relative
positions + 8x8 deployment grid (200 m cells, per doc 122) drawn as white lines.

Coordinates are derived from WGS84 (1 deg lat = 111.32 km, 1 deg lon at 52.24 N
= 68.2 km), origin at Rynek Starego Miasta.
"""
import bpy
import bmesh
import json
import math
import os
import time
from mathutils import Vector

BASE = r"E:\AI\Tread\Tread\model\warsaw"
LM = os.path.join(BASE, "landmarks")
MAP_I = os.path.join(BASE, "尸体痕迹-华沙3D地图I(Body traces - War_爱给网_aigei_com",
                     "body_traces_-_warsaw_3d_map_i.glb")
OUT_BLEND = os.path.join(LM, "Warsaw_Board_Realistic.blend")

# ---- board extent (m), centred on the landmark cluster -------------------
X0, X1 = -800.0, 2900.0
Y0, Y1 = -4500.0, 900.0
# ---- 8x8 deployment grid (doc 122: 200 m cells) ------------------------
CELL = 200.0
NCELL = 8
GX, GY = 70.0, -30.0          # grid centre: Old Town / Castle cluster

# real relative positions (m), origin = Rynek
LM_ITEMS = [
    ("Warsaw_01_Rynek.blend", "COL_LM_RYNEK", "LM_RYNEK", 0.0, 0.0),
    ("Warsaw_02_Zamek.blend", "COL_LM_ZAMEK", "LM_ZAMEK", 164.0, -200.0),
    ("Warsaw_03_Barbakan.blend", "COL_LM_BARBAKAN", "LM_BARBAKAN", -27.0, 145.0),
    ("Warsaw_06_PKin.blend", "COL_LM_PKIN", "LM_PKIN", -423.0, -1981.0),
    ("Warsaw_04_Lazienki.blend", "COL_LM_LAZIENKI", "LM_LAZIENKI", 1575.0, -3863.0),
    ("Warsaw_05_Stadion.blend", "COL_LM_STADION", "LM_STADION", 2203.0, -1202.0),
]

t0 = time.time()

# ---------------------------------------------------------------- ground
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=MAP_I)
map_mshes = [o for o in bpy.data.objects if o.type == "MESH"]

# flatten the Sketchfab hierarchy: unparent (keep world) then apply transforms,
# so mesh-local coordinates == world coordinates and bisect_plane works in world
for o in map_mshes:
    mw = o.matrix_world.copy()
    o.parent = None
    o.matrix_world = mw
bpy.ops.object.select_all(action="DESELECT")
for o in map_mshes:
    o.select_set(True)
bpy.context.view_layer.objects.active = map_mshes[0]
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

# bbox + ground level (2nd percentile of z, robust against stray verts)
zs = []
mn = [1e18] * 3
mx = [-1e18] * 3
for o in map_mshes:
    for v in o.data.vertices:
        w = v.co
        zs.append(w.z)
        for i in range(3):
            mn[i] = min(mn[i], w[i])
            mx[i] = max(mx[i], w[i])
zs.sort()
ground = zs[int(len(zs) * 0.02)]
del zs

from mathutils import Matrix
for o in map_mshes:
    o.data.transform(Matrix.Translation((0.0, 0.0, -ground)))
    o.data.update()


def crop(obj, x0, x1, y0, y1):
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    geom = list(bm.verts) + list(bm.edges) + list(bm.faces)
    for co, no in (((x0, 0, 0), (-1, 0, 0)), ((x1, 0, 0), (1, 0, 0)),
                   ((0, y0, 0), (0, -1, 0)), ((0, y1, 0), (0, 1, 0))):
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=co, plane_no=no,
                               clear_outer=True, clear_inner=False)
        geom = list(bm.verts) + list(bm.edges) + list(bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.update()


# map geometry is offset in z; already shifted to ground = 0 above
t_crop = time.time()
for o in map_mshes:
    crop(o, X0, X1, Y0, Y1)
print("crop %.1fs" % (time.time() - t_crop))

# ---------------------------------------------------------------- map tint
# The map is a land-use plan: built-up area is near-white.  Push only the
# low-saturation materials to a warm concrete grey so the city reads as mass
# instead of chalk; leave water / vegetation (saturated) untouched.
import colorsys
tinted = 0
for m in bpy.data.materials:
    if not m.use_nodes:
        continue
    b = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if b is None:
        continue
    c = b.inputs["Base Color"].default_value
    h, s, v = colorsys.rgb_to_hsv(c[0], c[1], c[2])
    if s < 0.14:
        b.inputs["Base Color"].default_value = (0.30, 0.29, 0.27, 1.0)
        b.inputs["Roughness"].default_value = 0.92
        tinted += 1

# ---------------------------------------------------------------- landmarks
board = bpy.data.collections.new("COL_BOARD")
bpy.context.scene.collection.children.link(board)
placed = []
for fname, cname, root_name, px, py in LM_ITEMS:
    path = os.path.join(LM, fname)
    if not os.path.exists(path):
        placed.append({"file": fname, "error": "missing"})
        continue
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.collections = [cname]
    coll = dst.collections[0]
    board.children.link(coll)
    root = bpy.data.objects.get(root_name)
    if root:
        root.location = (px, py, 0.0)
    placed.append({"file": fname, "pos": [px, py],
                   "meshes": len([o for o in coll.all_objects if o.type == "MESH"])})

# ---------------------------------------------------------------- white grid
grid_col = bpy.data.collections.new("COL_DEPLOY_GRID")
bpy.context.scene.collection.children.link(grid_col)

wmat = bpy.data.materials.new("M_GridWhite")
wmat.use_nodes = True
nt = wmat.node_tree
nt.nodes.clear()
out = nt.nodes.new("ShaderNodeOutputMaterial")
em = nt.nodes.new("ShaderNodeEmission")
em.inputs[0].default_value = (1.0, 1.0, 1.0, 1.0)
em.inputs[1].default_value = 7.0
nt.links.new(em.outputs[0], out.inputs[0])

verts, faces = [], []


def bar(cx, cy, sx, sy, h=0.35):
    x0, x1 = cx - sx / 2, cx + sx / 2
    y0, y1 = cy - sy / 2, cy + sy / 2
    o = len(verts)
    verts.extend([(x0, y0, 0.15), (x1, y0, 0.15), (x1, y1, 0.15), (x0, y1, 0.15),
                  (x0, y0, 0.15 + h), (x1, y0, 0.15 + h), (x1, y1, 0.15 + h), (x0, y1, 0.15 + h)])
    faces.extend([(o, o + 3, o + 2, o + 1), (o + 4, o + 5, o + 6, o + 7),
                  (o, o + 1, o + 5, o + 4), (o + 1, o + 2, o + 6, o + 5),
                  (o + 2, o + 3, o + 7, o + 6), (o + 3, o, o + 4, o + 7)])


half = NCELL * CELL / 2.0
for i in range(NCELL + 1):
    off = -half + i * CELL
    w = 7.0 if i in (0, NCELL) else 2.6
    bar(GX, GY + off, NCELL * CELL + w, w)      # east-west line
    bar(GX + off, GY, w, NCELL * CELL + w)      # north-south line
me = bpy.data.meshes.new("GEO-DEPLOY-GRID")
me.from_pydata(verts, [], faces)
me.validate()
me.update()
me.materials.append(wmat)
go = bpy.data.objects.new("GEO-DEPLOY-GRID", me)
grid_col.objects.link(go)

# ---------------------------------------------------------------- light / world
w = bpy.data.worlds.new("W")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.42, 0.52, 0.66, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 0.34
bpy.context.scene.world = w
sun_d = bpy.data.lights.new("SUN", type="SUN")
sun_d.energy = 4.6
sun_d.angle = math.radians(1.2)
sun = bpy.data.objects.new("SUN", sun_d)
sun.rotation_euler = (math.radians(38), 0.0, math.radians(42))
bpy.context.scene.collection.objects.link(sun)

sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.image_settings.file_format = "PNG"

stats = {"ground_z": round(ground, 1),
         "map_crop": [X0, X1, Y0, Y1],
         "grid_centre": [GX, GY], "cell": CELL, "cells": NCELL,
         "landmarks": placed,
         "objects": len([o for o in bpy.data.objects if o.type == "MESH"]),
         "tris": sum(sum(len(p.vertices) - 2 for p in o.data.polygons)
                     for o in bpy.data.objects if o.type == "MESH"),
         "seconds": round(time.time() - t0, 1)}
os.makedirs(LM, exist_ok=True)

# ---------------------------------------------------------------- renders
shots_dir = r"E:\AI\Tread\Tread\Saved\Warsaw\renders"
os.makedirs(shots_dir, exist_ok=True)
cam_d = bpy.data.cameras.new("BOARD_CAM")
cam_d.clip_start = 1.0
cam_d.clip_end = 60000.0
cam = bpy.data.objects.new("BOARD_CAM", cam_d)
sc.collection.objects.link(cam)
sc.camera = cam
views = [
    ("board_real_overview", (900.0, -6200.0, 2600.0), (900.0, -1600.0, 0.0), 32, 1400, 900),
    ("board_real_grid", (70.0, -1150.0, 780.0), (70.0, -30.0, 0.0), 32, 1200, 900),
    ("board_real_core", (330.0, 330.0, 165.0), (40.0, -40.0, 45.0), 42, 1200, 800),
]
shots = []
for name, pos, look, lens, rx, ry in views:
    cam_d.lens = lens
    cam.location = pos
    cam.rotation_euler = (Vector(look) - Vector(pos)).to_track_quat("-Z", "Y").to_euler()
    sc.render.resolution_x = rx
    sc.render.resolution_y = ry
    p = os.path.join(shots_dir, name + ".png")
    sc.render.filepath = p
    bpy.ops.render.render(write_still=True)
    shots.append(p)

bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
stats["blend"] = OUT_BLEND
stats["shots"] = shots
print("HEADLESS " + json.dumps(stats, ensure_ascii=False))
