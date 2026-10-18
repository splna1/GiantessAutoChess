"""Blender background probe: dump object/material/bounds/triangle stats of the opened (staged) blend as JSON.

blender --background <staged.blend> --python Tools/m3/blender_probe.py -- --out <report.json>
"""
import json
import sys

import bpy
from mathutils import Vector


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = argv[argv.index("--out") + 1]
    dg = bpy.context.evaluated_depsgraph_get()
    objs, lo, hi, tris = [], Vector((1e18,) * 3), Vector((-1e18,) * 3), 0
    for obj in bpy.context.scene.objects:
        rec = {"name": obj.name, "type": obj.type, "parent": obj.parent.name if obj.parent else None,
               "hidden": obj.hide_get() or obj.hide_render, "collection": [c.name for c in obj.users_collection]}
        if obj.type == "MESH":
            ev = obj.evaluated_get(dg)
            me = ev.to_mesh()
            t = sum(len(p.vertices) - 2 for p in me.polygons)
            rec["tris"] = t
            rec["materials"] = [m.name if m else None for m in obj.data.materials]
            ev.to_mesh_clear()
            if not rec["hidden"]:
                tris += t
                for c in obj.bound_box:
                    w = obj.matrix_world @ Vector(c)
                    lo = Vector(map(min, lo, w))
                    hi = Vector(map(max, hi, w))
        objs.append(rec)
    images = [{"name": i.name, "file": i.filepath, "packed": bool(i.packed_file), "size": list(i.size)} for i in bpy.data.images]
    mats = []
    for m in bpy.data.materials:
        tex = []
        if m.use_nodes:
            tex = [n.image.name for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image]
        mats.append({"name": m.name, "users": m.users, "textures": tex})
    rep = {"file": bpy.data.filepath, "unit_scale": bpy.context.scene.unit_settings.scale_length,
           "visible_tris": tris, "bounds_min": list(lo), "bounds_max": list(hi), "size": list(hi - lo),
           "objects": objs, "materials": mats, "images": images}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    print("PROBE_OK", out, len(objs), tris)


main()
