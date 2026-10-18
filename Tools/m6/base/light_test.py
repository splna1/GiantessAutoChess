# -*- coding: utf-8 -*-
"""Lighting test: render the same view under several light rigs (small, fast)."""
import json
import math
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import render_shots as R  # noqa: E402

BLEND = os.path.join(R.K.ROOT, "model", "m6", "base", "M6_C2_Command.blend")
OUT = os.path.join(R.K.ROOT, "Saved", "M6Base", "diag")


def world_flat(col, strength):
    w = bpy.context.scene.world
    if w is None:
        w = bpy.data.worlds.new("W")
        bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs[0].default_value = (col[0], col[1], col[2], 1.0)
    bg.inputs[1].default_value = strength
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])


def main():
    bpy.ops.wm.open_mainfile(filepath=BLEND)
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = 560, 350
    sc.render.image_settings.file_format = "PNG"
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 24
    sc.cycles.use_denoising = True

    objs = R.scene_meshes()
    mn, mx = R.bounds(objs)
    center = (mn + mx) / 2.0
    corners = [Vector((x, y, z)) for x in (mn.x, mx.x) for y in (mn.y, mx.y) for z in (mn.z, mx.z)]
    R.ensure_ground(center, 700.0)
    cam = R.make_cam()
    sc.camera = cam
    aim = center.copy()
    aim.z = mn.z + (mx.z - mn.z) * 0.46
    R.fit(cam, corners, aim, (0.80, -1.00, 0.30), 70, (560, 350))

    sun = bpy.data.objects.get("SUN")
    variants = [
        ("v4", (0.45, 0.48, 0.52), 0.30, 4.5, 0.15, 315.0, 30.0),
        ("v5", (0.55, 0.52, 0.46), 0.45, 3.5, 0.10, 300.0, 24.0),
        ("v6", (0.40, 0.44, 0.50), 0.20, 5.5, 0.00, 330.0, 38.0),
    ]
    shots = []
    for name, col, ws, se, ex, az, el in variants:
        world_flat(col, ws)
        if sun:
            sun.data.energy = se
            sun.rotation_euler = (math.radians(90.0 - el), 0.0, math.radians(az))
        sc.view_settings.exposure = ex
        p = os.path.join(OUT, "light_%s.png" % name)
        sc.render.filepath = p
        bpy.ops.render.render(write_still=True)
        shots.append(p)
    print("HEADLESS " + json.dumps({"shots": shots}))


if __name__ == "__main__":
    main()
