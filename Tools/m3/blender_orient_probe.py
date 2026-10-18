"""Blender orientation probe for the M3 building FBX files (as UE will see them).

For every FBX: imports it into an empty scene, mirrors y (Blender -> UE axis convention of the FBX importer,
verified on SM_M3_Townhouse_* whose -y street front lands on UE +y), and reports
  * the bounding box in UE metres,
  * vertex density per footprint quadrant above 3 m (an L-shaped corner building has one nearly empty quadrant),
and renders a 4-side contact sheet (views from UE +x, +y, -x, -y) so fronts can be checked by eye.

    blender --background --factory-startup --python Tools/m3/blender_orient_probe.py -- --out <dir> <fbx> [...]
"""
import json
import math
import os
import sys

import bpy
from mathutils import Vector


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    out = argv[argv.index("--out") + 1]
    files = [a for a in argv if a.lower().endswith(".fbx")]
    os.makedirs(out, exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.render.resolution_x, scene.render.resolution_y = 400, 400
    scene.render.image_settings.file_format = "PNG"
    report = {}
    for path in files:
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        bpy.ops.import_scene.fbx(filepath=path)
        meshes = [o for o in scene.objects if o.type == "MESH"]
        pts = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
        ue = [(p.x, -p.y, p.z) for p in pts]
        lo = [min(p[i] for p in ue) for i in range(3)]
        hi = [max(p[i] for p in ue) for i in range(3)]
        cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
        quad = {"+x+y": 0, "+x-y": 0, "-x+y": 0, "-x-y": 0}
        for x, y, z in ue:
            if z > 3.0:
                quad[("+x" if x > cx else "-x") + ("+y" if y > cy else "-y")] += 1
        tot = max(1, sum(quad.values()))
        name = os.path.splitext(os.path.basename(path))[0]
        report[name] = {"bounds_ue_m": [[round(v, 2) for v in lo], [round(v, 2) for v in hi]],
                        "quadrant_share": {k: round(v / tot, 3) for k, v in quad.items()}}
        size = max(hi[0] - lo[0], hi[1] - lo[1], hi[2])
        cam_data = bpy.data.cameras.new("c")
        cam = bpy.data.objects.new("c", cam_data)
        scene.collection.objects.link(cam)
        scene.camera = cam
        # views from UE +x, +y, -x, -y (UE y = -Blender y)
        for tag, (dx, dy) in (("from_UE+x", (1, 0)), ("from_UE+y", (0, -1)), ("from_UE-x", (-1, 0)), ("from_UE-y", (0, 1))):
            cam.location = Vector((dx * size * 1.6, dy * size * 1.6, hi[2] * 0.6 + size * 0.25))
            cam.rotation_euler = (Vector((0, 0, hi[2] * 0.4)) - cam.location).to_track_quat("-Z", "Y").to_euler()
            scene.render.filepath = os.path.join(out, "%s_%s.png" % (name, tag))
            bpy.ops.render.render(write_still=True)
        bpy.data.objects.remove(cam, do_unlink=True)
    with open(os.path.join(out, "orient.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    print("ORIENT_OK", len(report))


main()
