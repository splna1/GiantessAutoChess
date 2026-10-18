"""Blender 5.2 background exporter for the B5 vehicle sources.

The input blend is copied to Saved/Staging before Blender opens it.  This
script only edits that staged copy in memory, strips scene-only objects,
retints materials for the blue faction and writes a self-contained GLB.

Invocation:
    blender --background staged.blend --python this.py -- --kind M1A2 --out out.glb
"""
import argparse
import json
import os
import sys

import bpy


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", required=True)
    ap.add_argument("--out", required=True)
    return ap.parse_args(argv)


def retint_material(mat, kind):
    if not mat or not mat.use_nodes:
        return
    bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        return
    # Preserve texture wiring where present, but tint plain materials and the
    # Principled fallback used by the source blends into the blue palette.
    base = bsdf.inputs.get("Base Color")
    if base is not None and base.is_linked is False:
        base.default_value = (0.025, 0.12, 0.42, 1.0) if kind == "M1A2" else (0.035, 0.16, 0.50, 1.0)
    metal = bsdf.inputs.get("Metallic")
    if metal is not None and not metal.is_linked:
        metal.default_value = 0.55
    rough = bsdf.inputs.get("Roughness")
    if rough is not None and not rough.is_linked:
        rough.default_value = 0.48
    mat.diffuse_color = (0.025, 0.12, 0.42, 1.0)


def main():
    a = args()
    meshes = []
    for obj in list(bpy.context.scene.objects):
        if obj.type != "MESH":
            bpy.data.objects.remove(obj, do_unlink=True)
            continue
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        try:
            bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        except RuntimeError:
            pass
        for mat in obj.data.materials:
            retint_material(mat, a.kind)
        meshes.append(obj)
    if not meshes:
        raise RuntimeError("no mesh objects found in source blend")
    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    # Apply a common bottom-to-ground translation to the collection.  GLTF
    # reader later normalizes the footprint and does a second robust ground
    # placement, so this keeps the exported artifact pleasant to inspect too.
    zmin = min((obj.matrix_world @ v.co).z for obj in meshes for v in obj.data.vertices)
    for obj in meshes:
        obj.location.z -= zmin
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=os.path.abspath(a.out), export_format="GLB", use_selection=True,
                              export_apply=True, export_materials="EXPORT")
    lo = [1e30, 1e30, 1e30]
    hi = [-1e30, -1e30, -1e30]
    verts = 0
    for obj in meshes:
        for v in obj.data.vertices:
            p = obj.matrix_world @ v.co
            verts += 1
            for i in range(3):
                lo[i] = min(lo[i], p[i]); hi[i] = max(hi[i], p[i])
    report = {"kind": a.kind, "output": os.path.abspath(a.out).replace("\\", "/"), "objects": len(meshes),
              "vertices": verts, "bounds_blender_m": [[round(v, 4) for v in lo], [round(v, 4) for v in hi]]}
    print("B5_GLTF_REPORT=" + json.dumps(report, ensure_ascii=False))


main()
