"""Blender (5.2) cleaner/exporter for the read-only building and aircraft sources used by M3.

Runs on a STAGED copy (Saved/Staging/m3_src/*.blend; the source folders are never written):
    blender --background <staged.blend> --python Tools/m3/blender_prepare_models.py -- \
        --kind am229|oushi|aircraft --out <dir> [--maps <source maps dir>] [--split] [--preview]
or from blender-mcp: sys.argv = ["x", "--", ...]; runpy.run_path(<this file>, run_name="__main__").

What it does (in memory, the staged .blend is not saved):
  * drops lights/cameras/empties and interior dressing (interiors, curtains, blinds, shop interiors) that sits
    behind glass we render opaque in UE;
  * applies transforms, joins the remaining meshes (one piece per output asset; --split keeps the top-level mesh
    objects separate, used for the 3d66 file which holds five different buildings);
  * re-pivots every piece to the centre of its footprint with z = 0 at its lowest vertex;
  * resolves each material's image textures by the socket they feed (base / normal / gloss / opacity), copies the
    image bytes to <out>/tex/ (packed images are written from their packed data) and writes <out>/manifest.json;
  * exports one FBX per piece (path_mode STRIP: UE builds its own material instances from the manifest).
Optional --preview renders a Workbench textured preview per piece to <out>/preview_<piece>.png for review.
"""
import argparse
import json
import math
import os
import re
import shutil
import sys

import bpy
from mathutils import Vector

DROP = re.compile(r"interior|curtain|blind|_Cycles|shop_interior", re.I)


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", required=True, choices=["am229", "oushi", "aircraft"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--maps", default="")
    ap.add_argument("--name", default="")
    ap.add_argument("--split", action="store_true")
    ap.add_argument("--preview", action="store_true")
    return ap.parse_args(argv)


def role_of(link_socket_name, image_name):
    s = (link_socket_name or "").lower()
    n = image_name.lower()
    if "normal" in s or re.search(r"(_n\b|_n\.|normal)", n):
        return "normal"
    if "rough" in s or "gloss" in n:
        return "gloss"
    if "opacity" in s or "alpha" in s or "opacity" in n:
        return "opacity"
    if "reflection" in s or "specular" in s or "reflection" in n or "specular" in n:
        return None
    if "diffuse" in s or "base" in s or "color" in s or "colour" in s:
        return "base"
    return "base" if not re.search(r"(gloss|refl|spec|bump|disp|ao)", n) else None


def downstream_socket(tree, node):
    """Name of the first socket this node feeds, looking through Normal Map / colour nodes."""
    for link in tree.links:
        if link.from_node == node:
            to = link.to_node
            if to.type in {"NORMAL_MAP", "BUMP"}:
                return "Normal"
            if to.type in {"MIX", "MIX_RGB", "CURVE_RGB", "HUE_SAT", "BRIGHTCONTRAST", "GAMMA", "INVERT", "SEPARATE_COLOR"}:
                deeper = downstream_socket(tree, to)
                return deeper or link.to_socket.name
            return link.to_socket.name
    return ""


def write_image(img, tex_dir, maps_dir):
    """Copy the image bytes into tex_dir; returns the written file name or None."""
    base = re.sub(r"[^A-Za-z0-9_.-]", "_", img.name)
    if img.packed_file:
        ext = os.path.splitext(img.filepath)[1] or "." + (img.file_format or "png").lower()
        name = os.path.splitext(base)[0] + ext.lower()
        with open(os.path.join(tex_dir, name), "wb") as f:
            f.write(img.packed_file.data)
        return name
    src = bpy.path.abspath(img.filepath)
    candidates = [src]
    if maps_dir:
        candidates.append(os.path.join(maps_dir, os.path.basename(img.filepath.replace("\\", "/"))))
    for c in candidates:
        if c and os.path.isfile(c):
            name = os.path.basename(c)
            dst = os.path.join(tex_dir, name)
            if not os.path.exists(dst):
                shutil.copy2(c, dst)
            return name
    return None


def material_record(mat, tex_dir, maps_dir):
    rec = {"slot": mat.name, "base": None, "normal": None, "gloss": None, "opacity": None, "color": None}
    if mat.use_nodes:
        tree = mat.node_tree
        for node in tree.nodes:
            if node.type == "TEX_IMAGE" and node.image:
                role = role_of(downstream_socket(tree, node), node.image.name)
                if role and rec[role] is None:
                    rec[role] = write_image(node.image, tex_dir, maps_dir)
            if node.type == "BSDF_PRINCIPLED" and rec["color"] is None:
                c = node.inputs["Base Color"].default_value
                rec["color"] = [round(c[0], 4), round(c[1], 4), round(c[2], 4)]
    if rec["color"] is None:
        c = mat.diffuse_color
        rec["color"] = [round(c[0], 4), round(c[1], 4), round(c[2], 4)]
    n = mat.name.lower()
    rec["glass"] = bool(re.search(r"glass|boli|window_glass|lens|canopy", n)) or rec["opacity"] is not None and "glass" in n
    return rec


def clean_scene(kind):
    for obj in list(bpy.data.objects):
        if obj.type != "MESH" or DROP.search(obj.name) or obj.hide_render:
            bpy.data.objects.remove(obj, do_unlink=True)
    # re-parenting is irrelevant after transform_apply; clear parents keeping the world transform
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    for o in meshes:
        mw = o.matrix_world.copy()
        o.parent = None
        o.matrix_world = mw
    return meshes


def apply_and_join(objs, name):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.make_single_user(object=True, obdata=True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if len(objs) > 1:
        bpy.ops.object.join()
    piece = bpy.context.view_layer.objects.active
    piece.name = name
    piece.data.name = name
    # pivot: footprint centre, z = 0 at the lowest vertex
    vs = piece.data.vertices
    lo = Vector((min(v.co.x for v in vs), min(v.co.y for v in vs), min(v.co.z for v in vs)))
    hi = Vector((max(v.co.x for v in vs), max(v.co.y for v in vs), max(v.co.z for v in vs)))
    off = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    for v in vs:
        v.co -= off
    piece.location = (0, 0, 0)
    piece.data.update()
    return piece, [round(x, 3) for x in (hi - lo)]


def export_piece(piece, path):
    bpy.ops.object.select_all(action="DESELECT")
    piece.select_set(True)
    bpy.context.view_layer.objects.active = piece
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={"MESH"}, mesh_smooth_type="FACE",
                             use_mesh_modifiers=True, add_leaf_bones=False, bake_anim=False, path_mode="STRIP")


def render_preview(piece, path, size):
    scene = bpy.context.scene
    for o in scene.objects:
        o.hide_render = o is not piece and o.type == "MESH"
    cam_data = bpy.data.cameras.new("m3_prev_cam")
    cam = bpy.data.objects.new("m3_prev_cam", cam_data)
    scene.collection.objects.link(cam)
    r = max(size) * 1.25
    cam.location = (r, -r, r * 0.8 + size[2] * 0.3)
    direction = Vector((0, 0, size[2] * 0.4)) - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    cam_data.lens = 40
    scene.camera = cam
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "TEXTURE"
    scene.display.shading.show_shadows = True
    scene.render.resolution_x, scene.render.resolution_y = 1024, 768
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam, do_unlink=True)
    bpy.data.cameras.remove(cam_data)


def main():
    a = parse()
    os.makedirs(os.path.join(a.out, "tex"), exist_ok=True)
    if a.maps and os.path.isdir(a.maps):
        bpy.ops.file.find_missing_files(directory=a.maps)
    meshes = clean_scene(a.kind)
    base_name = a.name or os.path.splitext(os.path.basename(bpy.data.filepath))[0]
    groups = [[o] for o in sorted(meshes, key=lambda o: o.name)] if a.split else [meshes]
    pieces = {}
    used = {}
    for group in groups:
        name = base_name if not a.split else "%s_%s" % (base_name, re.sub(r"[^A-Za-z0-9]", "", group[0].name))
        piece, size = apply_and_join(group, name)
        tris = sum(len(p.vertices) - 2 for p in piece.data.polygons)
        for m in piece.data.materials:
            if m and m.name not in used:
                used[m.name] = material_record(m, os.path.join(a.out, "tex"), a.maps)
        fbx = os.path.join(a.out, name + ".fbx")
        pieces[name] = {"fbx": os.path.basename(fbx), "size_m": size, "tris": tris,
                        "slots": [m.name if m else None for m in piece.data.materials]}
    # export after all joins so the selection state of one piece cannot leak into another
    for name in pieces:
        piece = bpy.data.objects[name]
        export_piece(piece, os.path.join(a.out, pieces[name]["fbx"]))
        if a.preview:
            render_preview(piece, os.path.join(a.out, "preview_%s.png" % name), pieces[name]["size_m"])
    manifest = {"source": bpy.data.filepath, "kind": a.kind, "pieces": pieces, "materials": used}
    with open(os.path.join(a.out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print("M3_PREPARE_OK", a.out, json.dumps({k: (v["size_m"], v["tris"]) for k, v in pieces.items()}))


if __name__ == "__main__":
    main()
