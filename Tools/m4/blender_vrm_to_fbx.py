"""Blender 5.2 + VRM Add-on: convert one staged roster VRM into an FBX skeletal mesh for UE, plus a sidecar and a preview.

    blender --background --python Tools/m4/blender_vrm_to_fbx.py -- --vrm <file.vrm> --out <dir> --name SK_VRM_<char_0xx>
(run WITHOUT --factory-startup so the installed VRM extension is enabled; the source file is only read)

Same contract as blender_mmd_to_fbx.py (document/151), because UE meets the same three traps:
  * centimetres: the model is scaled x100 under a scene unit scale of 0.01 and the transforms are applied, so the
    FBX carries no unit factor and UE imports the root bone at scale 1 (memory: tread-mmd-root-scale);
  * facing: the VRM Add-on stands every model facing Blender -Y whatever the file's convention (VRM 0.x files face
    glTF -Z, VRM 1.0 files +Z; measured on char_001/008/009/030/065, 2026-10-12), which UE receives facing +Y;
    --yaw 180 (default) is baked into the geometry and the bone rest poses so it faces -Y like the M1 hero
    (memory: tread-mmd-facing);
  * license: VRM 0.x files whose meta restricts use make the importer stop for a confirmation dialog.  The
    owner ruled the project a non-commercial fan work (document/143 section 4.3); the meta of every file is
    recorded by Tools/m4/vrm_inventory.py for the asset ledger, so the import confirms and proceeds.

Sidecar <name>.json: height, bones, the VRM humanoid map, and per material slot the base texture (written to
<out>/tex), alpha mode, cutoff, double-sidedness, base colour and the MToon shade parameters, all read from the
add-on's per-material VRM properties (VRM 0.x materials are converted into the same properties on import), so
ue_vrm_materials.py never has to match slots back to glTF materials by name.
"""
import argparse
import json
import math
import os
import re
import sys

import bpy
from mathutils import Matrix, Vector

HUMANOID = ["hips", "spine", "chest", "upper_chest", "neck", "head",
            "left_shoulder", "left_upper_arm", "left_lower_arm", "left_hand",
            "right_shoulder", "right_upper_arm", "right_lower_arm", "right_hand",
            "left_upper_leg", "left_lower_leg", "left_foot", "left_toes",
            "right_upper_leg", "right_lower_leg", "right_foot", "right_toes"]


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--vrm", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--yaw", type=float, default=180.0,
                    help="turn about Z baked into the export; 180 makes the model face like the M1 hero in UE")
    return ap.parse_args(argv)


def import_vrm(path):
    opts = dict(extract_textures_into_folder=False, set_shading_type_to_material_on_import=False,
                set_view_transform_to_standard_on_import=False, set_armature_display_to_wire=False,
                set_armature_display_to_show_in_front=False, set_armature_bone_shape_to_default=False,
                enable_mtoon_outline_preview=False)
    bpy.ops.import_scene.vrm(filepath=path, **opts)
    if not any(o.type == "ARMATURE" for o in bpy.data.objects):
        # LicenseConfirmationRequired: the add-on cancels and waits for a dialog; see the module docstring.
        bpy.ops.wm.vrm_license_warning(filepath=path, import_anyway=True, **opts)
    arm = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
    if arm is None:
        raise RuntimeError("VRM import produced no armature: %s" % path)
    return arm


def humanoid(arm):
    bones = arm.data.vrm_addon_extension.vrm1.humanoid.human_bones
    out = {}
    for key in HUMANOID:
        try:
            name = getattr(bones, key).node.bone_name
        except AttributeError:
            name = ""
        if name:
            out[key] = name
    return out


def safe(name):
    return re.sub(r"[^A-Za-z0-9_]", "_", name).strip("_") or "Tex"


def save_image(image, tex_dir, used):
    """Write a (usually packed) image into tex_dir once; returns the file name."""
    if image is None:
        return None
    if image.name in used:
        return used[image.name]
    ext = {"PNG": ".png", "JPEG": ".jpg", "TARGA": ".tga", "BMP": ".bmp"}.get(image.file_format, ".png")
    name = safe(os.path.splitext(image.name)[0]) + ext
    base, n = os.path.splitext(name)[0], 1
    while name in used.values():
        n += 1
        name = "%s_%d%s" % (base, n, ext)
    path = os.path.join(tex_dir, name)
    try:
        image.save(filepath=path)
    except RuntimeError:
        # Some packed images refuse save() with a path; go through a render-style write instead.
        image.filepath_raw = path
        image.save()
    used[image.name] = name
    return name


def solid_image(linear_rgba):
    """4x4 image of one base colour; the factor is linear, the PNG is sRGB."""
    srgb = [(12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055) for c in linear_rgba[:3]]
    key = "solid_%02x%02x%02x" % tuple(max(0, min(255, round(c * 255))) for c in srgb)
    image = bpy.data.images.get(key) or bpy.data.images.new(key, 4, 4, alpha=False)
    image.pixels = list(srgb + [1.0]) * 16
    image.file_format = "PNG"
    return image


def material_record(mat, tex_dir, used):
    m1 = mat.vrm_addon_extension.mtoon1
    pbr = m1.pbr_metallic_roughness
    image = pbr.base_color_texture.index.source
    if image is None and mat.use_nodes:
        node = next((n for n in mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image), None)
        image = node.image if node else None
    ext = m1.extensions.vrmc_materials_mtoon
    solid = False
    if image is None and pbr.base_color_factor[3] >= 0.05:
        # An untextured slot is coloured by its base colour alone (socks, shoes, trims); the UE toon master
        # only takes a texture, so bake the colour into a tiny one rather than leave the slot white.
        image, solid = solid_image(pbr.base_color_factor), True
    return {"slot": mat.name, "texture": save_image(image, tex_dir, used), "solidColor": solid, "mtoon": bool(m1.enabled),
            "alphaMode": m1.alpha_mode, "alphaCutoff": round(float(m1.alpha_cutoff), 3),
            "doubleSided": bool(m1.double_sided),
            "baseColor": [round(float(v), 3) for v in pbr.base_color_factor],
            "shadeColor": [round(float(v), 3) for v in ext.shade_color_factor],
            "shadingShift": round(float(ext.shading_shift_factor), 3),
            "shadingToony": round(float(ext.shading_toony_factor), 3),
            "rimColor": [round(float(v), 3) for v in ext.parametric_rim_color_factor],
            "rimPower": round(float(ext.parametric_rim_fresnel_power_factor), 3)}


def preview(path, height, yaw_deg):
    scene = bpy.context.scene
    cam_data = bpy.data.cameras.new("prev")
    cam = bpy.data.objects.new("prev", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam_data.lens = 50
    cam_data.clip_end = height * 20
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "TEXTURE"
    scene.render.resolution_x, scene.render.resolution_y = 600, 900
    scene.render.image_settings.file_format = "PNG"
    d = height * 2.4
    # Front three-quarter view; the camera turns with the model so the preview still shows its face.
    cam.location = Matrix.Rotation(math.radians(yaw_deg), 3, "Z") @ Vector((d * 0.35, -d, height * 0.55))
    cam.rotation_euler = (Vector((0, 0, height * 0.5)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam, do_unlink=True)


def main():
    a = args()
    # Absolute: the renderer resolves a relative output path against the drive root, not the working directory.
    a.out = os.path.abspath(a.out)
    os.makedirs(a.out, exist_ok=True)
    bpy.ops.wm.read_homefile(use_empty=True)
    arm = import_vrm(a.vrm)
    hmap = humanoid(arm)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if not meshes:
        raise RuntimeError("VRM import produced no mesh: %s" % a.vrm)
    # Spring-bone colliders and other helpers: UE builds its own physics asset.
    for o in list(bpy.data.objects):
        if o.type not in ("ARMATURE", "MESH"):
            bpy.data.objects.remove(o, do_unlink=True)
    # Centimetres + yaw, applied to everything so no node keeps a transform (see the module docstring).
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 0.01
    turn = Matrix.Rotation(math.radians(a.yaw), 4, "Z") @ Matrix.Scale(100.0, 4)
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
    morphs = sum(len(o.data.shape_keys.key_blocks) - 1 for o in meshes if o.data.shape_keys)
    fbx = os.path.join(a.out, a.name + ".fbx")
    bpy.ops.export_scene.fbx(filepath=fbx, use_selection=True, object_types={"ARMATURE", "MESH"}, add_leaf_bones=False,
                             bake_anim=False, armature_nodetype="NULL", primary_bone_axis="Y", secondary_bone_axis="X",
                             mesh_smooth_type="FACE", use_armature_deform_only=False, path_mode="STRIP",
                             embed_textures=False, axis_forward="-Z", axis_up="Y", apply_unit_scale=True,
                             use_tspace=False, apply_scale_options="FBX_SCALE_NONE")
    tex_dir = os.path.join(a.out, "tex")
    os.makedirs(tex_dir, exist_ok=True)
    used = {}
    slots = [material_record(m, tex_dir, used)
             for m in sorted({m for o in meshes for m in o.data.materials if m}, key=lambda m: m.name)]
    # Facing check in the exported frame: after the yaw the model faces Blender +Y, so its left hip sits on
    # -X (a negative value here); UE (axis_forward -Z) receives that as a model facing -Y.
    b = arm.data.bones
    lh, rh = hmap.get("left_upper_leg"), hmap.get("right_upper_leg")
    left_x = (b[lh].head_local.x - b[rh].head_local.x) if lh in b and rh in b else None
    info = {"name": a.name, "vrm": a.vrm, "fbx": os.path.basename(fbx), "units": "cm", "yawDeg": a.yaw,
            "specVersion": arm.data.vrm_addon_extension.spec_version, "height_cm": round(height, 3),
            "bounds_cm": [[round(v, 3) for v in lo], [round(v, 3) for v in hi]], "bones": len(b),
            "meshes": len(meshes), "triangles": tris, "morphs": morphs, "humanoid": hmap,
            "leftHipMinusRightHipX_cm": round(left_x, 3) if left_x is not None else None,
            "rootBones": [x.name for x in b if x.parent is None], "slots": slots}
    with open(os.path.join(a.out, a.name + ".json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=1)
    preview(os.path.join(a.out, a.name + "_preview.png"), height, a.yaw)
    print("VRM_OK", a.name, info["height_cm"], info["bones"], tris, len(slots))


main()
