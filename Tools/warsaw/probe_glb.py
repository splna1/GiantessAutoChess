# -*- coding: utf-8 -*-
"""Probe: can the Warsaw 001 XReconstruct GLB be used in Blender?

Read-only. Imports the .glb into a factory-startup scene, reports mesh/material/
texture statistics, world bbox and unit scale, then renders one preview frame.
"""
import bpy, json, os, sys, time

GLB = r"E:\AI\Tread\Tread\model\warsaw\华沙001 - X重建(Warsaw 001 - XReco_爱给网_aigei_com\warsaw_001_-_xreconstruct.glb"
OUT = r"E:\AI\Tread\Tread\Saved\Warsaw"
os.makedirs(OUT, exist_ok=True)

rep = {"blender": bpy.app.version_string, "glb": GLB, "exists": os.path.exists(GLB)}
if rep["exists"]:
    rep["bytes"] = os.path.getsize(GLB)

t0 = time.time()
bpy.ops.wm.read_factory_settings(use_empty=True)
try:
    r = bpy.ops.import_scene.gltf(filepath=GLB)
    rep["import_result"] = str(r)
    rep["import_ok"] = True
except Exception as e:
    rep["import_ok"] = False
    rep["import_error"] = "%s: %s" % (type(e).__name__, e)
rep["import_seconds"] = round(time.time() - t0, 2)

meshes = [o for o in bpy.data.objects if o.type == "MESH"]
rep["objects"] = len(bpy.data.objects)
rep["meshes"] = len(meshes)
tris = 0
verts = 0
per_obj = []
for o in meshes:
    m = o.data
    m.calc_loop_triangles()
    t = len(m.loop_triangles)
    tris += t
    verts += len(m.vertices)
    if len(per_obj) < 12:
        per_obj.append({"name": o.name, "verts": len(m.vertices), "tris": t,
                        "uv": [u.name for u in m.uv_layers],
                        "mats": [s.material.name if s.material else None for s in o.material_slots]})
rep["total_verts"] = verts
rep["total_tris"] = tris
rep["per_object"] = per_obj

# world bbox
mn = [1e18] * 3
mx = [-1e18] * 3
for o in meshes:
    mw = o.matrix_world
    for c in o.bound_box:
        w = mw @ __import__("mathutils").Vector(c)
        for i in range(3):
            mn[i] = min(mn[i], w[i])
            mx[i] = max(mx[i], w[i])
rep["bbox_min"] = [round(v, 3) for v in mn]
rep["bbox_max"] = [round(v, 3) for v in mx]
rep["bbox_size"] = [round(mx[i] - mn[i], 3) for i in range(3)]
rep["scene_unit_scale"] = bpy.context.scene.unit_settings.scale_length
rep["scene_unit_system"] = bpy.context.scene.unit_settings.system

# transforms: check for non-uniform parent scale (typical glTF cm -> m)
xform = []
for o in bpy.data.objects[:12]:
    if o.type == "EMPTY" or o.parent:
        xform.append({"name": o.name, "type": o.type,
                      "scale": [round(v, 4) for v in o.scale],
                      "loc": [round(v, 3) for v in o.location]})
rep["transforms"] = xform

imgs = []
for im in bpy.data.images:
    imgs.append({"name": im.name, "size": list(im.size),
                 "bytes": im.packed_file.size if im.packed_file else None,
                 "path": os.path.basename(im.filepath) if im.filepath else ""})
rep["images"] = imgs
rep["materials"] = [m.name for m in bpy.data.materials]

# ---- one preview render (EEVEE), camera auto-framed on bbox ----
try:
    sc = bpy.context.scene
    cam_data = bpy.data.cameras.new("PROBE-CAM")
    cam = bpy.data.objects.new("PROBE-CAM", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cx = (mn[0] + mx[0]) / 2.0
    cy = (mn[1] + mx[1]) / 2.0
    cz = (mn[2] + mx[2]) / 2.0
    span = max(mx[i] - mn[i] for i in range(3))
    cam.location = (cx + span * 0.75, cy - span * 1.35, cz + span * 0.85)
    import math
    from mathutils import Vector
    d = Vector((cx, cy, cz)) - cam.location
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    cam_data.lens = 50
    sun_d = bpy.data.lights.new("PROBE-SUN", type='SUN')
    sun_d.energy = 3.5
    sun = bpy.data.objects.new("PROBE-SUN", sun_d)
    sc.collection.objects.link(sun)
    sun.rotation_euler = (0.9, 0.1, 0.7)
    w = bpy.data.worlds.new("PROBE-W")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.9
    sc.world = w
    sc.render.resolution_x = 900
    sc.render.resolution_y = 600
    sc.render.filepath = os.path.join(OUT, "probe_xreco.png")
    sc.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)
    rep["render"] = sc.render.filepath
except Exception as e:
    rep["render_error"] = "%s: %s" % (type(e).__name__, e)

print("HEADLESS " + json.dumps(rep, ensure_ascii=False))
