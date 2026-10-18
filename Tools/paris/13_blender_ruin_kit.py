"""Blender 5.2: cut the BldgLG_J ruin scan into a reusable ruin kit and export one FBX per piece.

The source blend is read-only; 09_ruins.py / the caller copies it to Saved/Staging/ruins first. This script appends
its objects into a throw-away scene, so it can run inside a live Blender session (blender-mcp) without touching the
user's open file, or headless:

    blender --background --factory-startup --python 13_blender_ruin_kit.py -- --src staged.blend --out DIR

Through blender-mcp (execute_blender_code):
    import sys, runpy; sys.argv = ["13", "--", "--src", SRC, "--out", DIR]; runpy.run_path(THIS, run_name="__main__")

Every piece = all 20 scan meshes joined (material slots keep the KB3D names, so 09_ruins.py maps them to MI_KB_*),
clipped to an axis-aligned box with bmesh.bisect_plane, re-pivoted to the box centre in x/y with z = 0 left at the
scan's ground level (the rubble skirt stays buried down to -3.5 m). Units are scan metres; UE imports at 0.85 like
SM_CollapsedBuilding_Scan. Writes <out>/ruin_kit.json with per-piece triangle counts and bounds.
"""
import argparse
import json
import os
import sys

import bmesh
import bpy
from mathutils import Vector

# name: (x range, y range, z range) in scan-blend metres (scan bounds x -52.9..25.1, y 85.9..135.0, z -3.5..27.7)
PIECES = {
    "KB_WingEast":   ((-11.0, 26.0), (85.0, 136.0), (-4.0, 29.0)),   # east half of the steel frame + skirt
    "KB_WingWest":   ((-54.0, -11.0), (103.0, 136.0), (-4.0, 29.0)),  # west half of the frame, without the facade
    "KB_FacadeFall": ((-54.0, -8.0), (85.0, 103.0), (-4.0, 12.0)),    # toppled street facade with floor slabs
    "KB_Stub":       ((-54.0, 26.0), (85.0, 136.0), (-4.0, 9.0)),     # whole ruin cut above the second floor
    "KB_RubbleField": ((-54.0, 26.0), (85.0, 136.0), (-4.0, 3.0)),    # skirt, slabs and column stumps only
    "KB_CornerStack": ((4.0, 26.0), (118.0, 136.0), (-4.0, 29.0)),    # tall frame corner (street-corner filler)
}


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", action="append", default=[])
    return ap.parse_args(argv)


def append_scan(scene, src):
    with bpy.data.libraries.load(src, link=False) as (data_from, data_to):
        data_to.objects = list(data_from.objects)
    meshes = []
    for obj in data_to.objects:
        scene.collection.objects.link(obj)
        if obj.type == "MESH":
            meshes.append(obj)
    return data_to.objects, meshes


def clip(bm, box):
    """Keep the part of bm inside box (half-open cuts leave the torn edges a ruin should have)."""
    for axis, (lo, hi) in enumerate(box):
        for value, keep_below in ((lo, False), (hi, True)):
            normal = Vector((0.0, 0.0, 0.0))
            normal[axis] = 1.0
            point = Vector((0.0, 0.0, 0.0))
            point[axis] = value
            geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
            bmesh.ops.bisect_plane(bm, geom=geom, plane_co=point, plane_no=normal, dist=1e-4,
                                   clear_outer=keep_below, clear_inner=not keep_below)
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")


def build_piece(scene, sources, name, box):
    """One joined, clipped, re-pivoted mesh object for piece `name`."""
    bm = bmesh.new()
    materials = []
    for obj in sources:
        local = bmesh.new()
        local.from_mesh(obj.data)
        local.transform(obj.matrix_world)
        remap = []
        for slot in obj.material_slots:
            if slot.material not in materials:
                materials.append(slot.material)
            remap.append(materials.index(slot.material))
        for face in local.faces:
            face.material_index = remap[face.material_index] if remap else 0
        mesh = bpy.data.meshes.new("tmp")
        local.to_mesh(mesh)
        local.free()
        bm.from_mesh(mesh)
        bpy.data.meshes.remove(mesh)
    clip(bm, box)
    used = sorted({face.material_index for face in bm.faces})
    for face in bm.faces:
        face.material_index = used.index(face.material_index)
    cx = (box[0][0] + box[0][1]) * 0.5
    cy = (box[1][0] + box[1][1]) * 0.5
    bmesh.ops.translate(bm, verts=bm.verts, vec=Vector((-cx, -cy, 0.0)))
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for index in used:
        mesh.materials.append(materials[index])
    obj = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(obj)
    return obj


def stats(obj):
    mesh = obj.data
    mesh.calc_loop_triangles()
    lo = [min(v.co[axis] for v in mesh.vertices) for axis in range(3)]
    hi = [max(v.co[axis] for v in mesh.vertices) for axis in range(3)]
    return {"tris": len(mesh.loop_triangles), "verts": len(mesh.vertices),
            "bounds_blend_m": [[round(v, 3) for v in lo], [round(v, 3) for v in hi]],
            "materials": [m.name for m in mesh.materials]}


def export_fbx(scene, obj, path):
    window = bpy.context.window_manager.windows[0] if bpy.context.window_manager.windows else None
    previous = window.scene if window else None
    if window:
        window.scene = scene
    try:
        for other in scene.objects:
            other.select_set(other is obj)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={"MESH"},
                                 mesh_smooth_type="FACE", use_mesh_modifiers=False, add_leaf_bones=False,
                                 bake_anim=False, path_mode="STRIP")
    finally:
        if window:
            window.scene = previous


def main():
    a = args()
    os.makedirs(a.out, exist_ok=True)
    scene = bpy.data.scenes.new("TreadRuinKit")
    appended, sources = append_scan(scene, a.src)
    report = {"source": a.src.replace("\\", "/"), "pieces": {}}
    built = []
    try:
        for name, box in PIECES.items():
            if a.only and name not in a.only:
                continue
            obj = build_piece(scene, sources, name, box)
            built.append(obj)
            path = os.path.join(a.out, name + ".fbx")
            export_fbx(scene, obj, path)
            report["pieces"][name] = dict(stats(obj), box_blend_m=[list(b) for b in box],
                                          fbx=path.replace("\\", "/"), fbx_bytes=os.path.getsize(path))
            print("[ruin_kit]", name, report["pieces"][name]["tris"], "tris")
    finally:
        # remove only the datablocks this run created (never purge orphans of the user's open file)
        meshes = {o.data for o in list(appended) + built if o.type == "MESH"}
        materials = {m for mesh in meshes for m in mesh.materials if m}
        images = {n.image for m in materials if m.node_tree for n in m.node_tree.nodes
                  if n.type == "TEX_IMAGE" and n.image}
        for obj in list(appended) + built:
            bpy.data.objects.remove(obj, do_unlink=True)
        for collection, blocks in ((bpy.data.meshes, meshes), (bpy.data.materials, materials),
                                   (bpy.data.images, images)):
            for block in blocks:
                if block.users == 0:
                    collection.remove(block)
        bpy.data.scenes.remove(scene)
    with open(os.path.join(a.out, "ruin_kit.json"), "w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
    print("RUIN_KIT_REPORT=" + json.dumps({k: v["tris"] for k, v in report["pieces"].items()}))


if __name__ == "__main__":
    main()
