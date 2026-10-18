# -*- coding: utf-8 -*-
"""Mesh diagnostic: finds stray/degenerate geometry in a landmark .blend.

Reports per object: verts, faces, longest edges (with world coords), zero-area
faces and loose vertices.  Used after each build to catch the "long thin sliver"
class of bug that only shows up as a stray line in a render.
"""
import bpy
import json
import sys
import os
from mathutils import Vector

PATH = r"E:\AI\Tread\Tread\model\warsaw\landmarks\Warsaw_02_Zamek.blend"
if not bpy.data.filepath:
    bpy.ops.wm.open_mainfile(filepath=PATH)
PATH = bpy.data.filepath or PATH
rep = {"file": PATH, "objects": []}
for ob in [o for o in bpy.data.objects if o.type == "MESH"]:
    me = ob.data
    mw = ob.matrix_world
    edges = []
    for e in me.edges:
        a = mw @ me.vertices[e.vertices[0]].co
        b = mw @ me.vertices[e.vertices[1]].co
        edges.append(((a - b).length, tuple(round(v, 2) for v in a), tuple(round(v, 2) for v in b)))
    edges.sort(reverse=True)
    tiny = 0
    for p in me.polygons:
        if p.area < 1e-7:
            tiny += 1
    used = set()
    for p in me.polygons:
        used.update(p.vertices)
    loose = len(me.vertices) - len(used)
    rep["objects"].append({
        "name": ob.name, "verts": len(me.vertices), "faces": len(me.polygons),
        "loose_verts": loose, "zero_area_faces": tiny,
        "longest_edges": [{"len": round(L, 2), "a": a, "b": b} for L, a, b in edges[:3]],
    })
rep["totals"] = {
    "objects": len(rep["objects"]),
    "verts": sum(o["verts"] for o in rep["objects"]),
    "faces": sum(o["faces"] for o in rep["objects"]),
    "loose_verts": sum(o["loose_verts"] for o in rep["objects"]),
    "zero_area_faces": sum(o["zero_area_faces"] for o in rep["objects"]),
}
print("HEADLESS " + json.dumps(rep, ensure_ascii=False))
