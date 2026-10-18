"""Blender 5.2 + mmd_tools: convert one staged MMD model (PMX) into an FBX skeletal mesh for UE, plus a preview.

    blender --background --python Tools/m4/blender_mmd_to_fbx.py -- --pmx <file.pmx> --out <dir> --name <char_1xx>
(run WITHOUT --factory-startup so the installed mmd_tools extension is enabled; also callable from blender-mcp via runpy)

Steps (all in memory; the staged PMX is never written):
  * mmd_tools import at scale 8.0 with the scene unit scale at 0.01, so 1 Blender unit = 1 cm and the
    geometry is authored in centimetres -- the same units the FBX file declares;
  * remove rigid bodies / joints / the MMD root empties' physics helpers (UE uses its own physics asset);
  * turn the model --yaw degrees about Z (default 180) so it faces the way the M1 hero does in UE;
  * apply transforms, keep the original Japanese/Chinese bone names (UE retarget maps them later);
  * export <name>.fbx (armature + mesh, no leaf bones, textures copied into <out>/tex via path_mode COPY);
  * write <name>.json (height, bones, triangles, materials, morph count, missing textures) and a front/3-4 preview.

Why centimetres: any metre->centimetre factor the exporter applies ends up on the armature object node,
which UE imports as a scale-100 root bone -- and a retargeted animation writes scale 1 on that bone,
shrinking the character to about 1 % of its size.  Measured with Tools/m4/n2_fbx_scale_probe.py:
importing at 0.08 with the exporter's default scalings gives a root bone at scale 100, "FBX All"
scalings still gives 100 (UE folds the file's unit scale back onto the root node), and only authoring
in centimetres gives 1.0.  See document/148 for the measurements.

Why the yaw: an MMD model faces Blender -Y and arrives in UE facing +Y, the opposite of the M1 hero
(Clukay416 faces -Y; measured on the reference poses' foot -> toe vectors, 2026-10-12), so on the board
every MMD unit turned its back to the enemy.  The turn is baked into the geometry and the bone rest
poses for the same reason as the centimetres: anything left on a node becomes a root-bone transform
that a retargeted animation overwrites.
"""
import argparse
import json
import math
import os
import shutil
import sys

import bpy
from mathutils import Matrix, Vector


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--pmx", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--scale", type=float, default=8.0,
                    help="mmd_tools import scale; 8.0 turns MMD units into centimetres")
    # How the metre -> centimetre factor is written into the FBX.  The exporter's default ("All Local")
    # bakes it into every object transform, so the armature object node arrives in UE as a scale-100
    # root bone; a retargeted animation then writes scale 1 on that bone and collapses the whole mesh
    # to ~1 % (see Tools/m4/n2_anim_pose_probe.py).  With centimetre geometry there is no factor left
    # to place, and "none" is the only mode measured to leave every node transform at identity.
    ap.add_argument("--scale-mode", choices=["none", "units", "custom", "all"], default="none")
    ap.add_argument("--unit-scale", type=float, default=0.01,
                    help="scene unit scale_length; 0.01 with --scale 8.0 makes 1 Blender unit = 1 cm")
    ap.add_argument("--yaw", type=float, default=180.0,
                    help="turn about Z baked into the export; 180 makes an MMD model face like the M1 hero in UE")
    return ap.parse_args(argv)


def ensure_mmd_tools():
    if hasattr(bpy.ops, "mmd_tools") and hasattr(bpy.ops.mmd_tools, "import_model"):
        return
    import addon_utils
    for mod in addon_utils.modules():
        if "mmd_tools" in mod.__name__:
            addon_utils.enable(mod.__name__, default_set=True, persistent=False)
            break
    if not (hasattr(bpy.ops, "mmd_tools") and hasattr(bpy.ops.mmd_tools, "import_model")):
        raise RuntimeError("mmd_tools is not available in this Blender")


def preview(objs, path, height, yaw_deg=0.0):
    scene = bpy.context.scene
    cam_data = bpy.data.cameras.new("prev")
    cam = bpy.data.objects.new("prev", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam_data.lens = 50
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "TEXTURE"
    scene.render.resolution_x, scene.render.resolution_y = 600, 900
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    d = height * 2.4
    # Front three-quarter view: the camera turns with the model so the preview still shows its face.
    cam.location = Matrix.Rotation(math.radians(yaw_deg), 3, "Z") @ Vector((d * 0.35, -d, height * 0.55))
    cam.rotation_euler = (Vector((0, 0, height * 0.5)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam, do_unlink=True)


def main():
    a = args()
    ensure_mmd_tools()
    os.makedirs(a.out, exist_ok=True)
    # units_blender_to_fbx_factor() returns a flat 100 while the unit system is NONE, so scale_length
    # only takes effect with a real unit system selected.
    bpy.context.scene.unit_settings.system = "METRIC" if a.unit_scale != 1.0 else "NONE"
    bpy.context.scene.unit_settings.scale_length = a.unit_scale
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.mmd_tools.import_model(filepath=a.pmx, scale=a.scale, types={"MESH", "ARMATURE", "MORPHS"},
                                   clean_model=True, remove_doubles=False, log_level="ERROR")
    # Drop physics helpers (rigid bodies, joints, their empties) - not imported with the type filter, but be safe.
    for o in list(bpy.data.objects):
        if o.type == "EMPTY" or o.rigid_body is not None or o.rigid_body_constraint is not None:
            if o.type != "ARMATURE" and not any(c.type in ("MESH", "ARMATURE") for c in o.children_recursive):
                bpy.data.objects.remove(o, do_unlink=True)
    arm = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if arm is None or not meshes:
        raise RuntimeError("PMX import produced no armature/mesh: %s" % a.pmx)
    # Unparent from the MMD root empty keeping world transforms, then delete the empty.
    for o in [arm] + meshes:
        mw = o.matrix_world.copy()
        if o.parent and o.parent.type == "EMPTY":
            o.parent = None
            o.matrix_world = mw
    for o in list(bpy.data.objects):
        if o.type == "EMPTY":
            bpy.data.objects.remove(o, do_unlink=True)
    if a.yaw:
        turn = Matrix.Rotation(math.radians(a.yaw), 4, "Z")
        for o in [arm] + meshes:
            if o.parent is None:
                o.matrix_world = turn @ o.matrix_world
    bpy.ops.object.select_all(action="DESELECT")
    for o in [arm] + meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    height = hi[2] - lo[2]
    tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in meshes)
    missing = sorted({img.name for img in bpy.data.images if img.source == "FILE" and not os.path.exists(bpy.path.abspath(img.filepath))})
    morphs = sum(len(o.data.shape_keys.key_blocks) - 1 for o in meshes if o.data.shape_keys)
    fbx = os.path.join(a.out, a.name + ".fbx")
    bpy.ops.export_scene.fbx(filepath=fbx, use_selection=True, object_types={"ARMATURE", "MESH"}, add_leaf_bones=False,
                             bake_anim=False, armature_nodetype="NULL", primary_bone_axis="Y", secondary_bone_axis="X",
                             mesh_smooth_type="FACE", use_armature_deform_only=False, path_mode="STRIP", embed_textures=False,
                             axis_forward="-Z", axis_up="Y", apply_unit_scale=True, use_tspace=False,
                             apply_scale_options="FBX_SCALE_" + a.scale_mode.upper())
    # UE does not receive mmd_tools shader links through FBX: record each slot's base texture and copy it to <out>/tex
    # so ue_import_mmd.py can build toon material instances itself.
    tex_dir = os.path.join(a.out, "tex")
    os.makedirs(tex_dir, exist_ok=True)
    slots = []
    for mat in sorted({m for o in meshes for m in o.data.materials if m}, key=lambda m: m.name):
        node = next((n for n in mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image and n.name == "mmd_base_tex"), None) if mat.use_nodes else None
        if node is None and mat.use_nodes:
            node = next((n for n in mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image), None)
        tex = None
        if node is not None:
            src = bpy.path.abspath(node.image.filepath)
            if os.path.isfile(src):
                tex = os.path.basename(src)
                out_path = os.path.join(tex_dir, tex)
                if not os.path.exists(out_path):
                    shutil.copy2(src, out_path)
        mmd = getattr(mat, "mmd_material", None)
        slots.append({"slot": mat.name, "texture": tex, "alpha": round(float(getattr(mmd, "alpha", 1.0)), 3) if mmd else 1.0,
                      "doubleSided": bool(getattr(mmd, "is_double_sided", False)) if mmd else False,
                      "diffuse": [round(float(c), 3) for c in getattr(mmd, "diffuse_color", (1, 1, 1))] if mmd else [1, 1, 1]})
    info = {"name": a.name, "pmx": a.pmx, "fbx": os.path.basename(fbx), "units": "cm", "yawDeg": a.yaw,
            "height_cm": round(height, 3), "slots": slots,
            "bounds_cm": [[round(v, 3) for v in lo], [round(v, 3) for v in hi]], "bones": len(arm.data.bones),
            "meshes": len(meshes), "triangles": tris, "materials": sorted({m.name for o in meshes for m in o.data.materials if m}),
            "morphs": morphs, "missingTextures": missing, "rootBones": [b.name for b in arm.data.bones if b.parent is None]}
    with open(os.path.join(a.out, a.name + ".json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=1)
    preview(meshes, os.path.join(a.out, a.name + "_preview.png"), height, a.yaw)
    print("MMD_OK", a.name, info["height_cm"], info["bones"], info["triangles"], len(missing))


main()
