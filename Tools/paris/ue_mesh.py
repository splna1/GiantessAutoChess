"""Editor-side: turn a geom.MeshBuilder into a Nanite StaticMesh asset (re-runnable, updates in place).

Each used builder slot becomes one material section; materials are assigned from `materials`
(slot name -> material path or object). Existing assets are overwritten in place so placed actors keep
their references.
"""
import time

import unreal

import paris_common as pc

GS_EDIT = unreal.GeometryScript_MeshEdits
FLIP_WINDING = True  # geom.py emits CCW-from-outside triangles; UE needs them reversed (checked with SM_Winding_0/1 captures)


def to_dynamic_mesh(mb):
    dm = unreal.DynamicMesh()
    used = mb.used_slots()
    V, V2, LC, IV = unreal.Vector, unreal.Vector2D, unreal.LinearColor, unreal.IntVector
    for mid, s in enumerate(used):
        d = mb.data[s]
        buf = unreal.GeometryScriptSimpleMeshBuffers()
        buf.vertices = [V(p[0] * 100.0, p[1] * 100.0, p[2] * 100.0) for p in d["p"]]
        buf.normals = [V(n[0], n[1], n[2]) for n in d["n"]]
        buf.uv0 = [V2(uv[0], uv[1]) for uv in d["uv"]]
        buf.vertex_colors = [LC(c[0], c[1], c[2], c[3]) for c in d["c"]]
        if FLIP_WINDING:
            buf.triangles = [IV(t[0], t[2], t[1]) for t in d["t"]]
        else:
            buf.triangles = [IV(t[0], t[1], t[2]) for t in d["t"]]
        GS_EDIT.append_buffers_to_mesh(dm, buf, mid, defer_change_notifications=True)
    return dm, used


def nanite_settings(enabled=True):
    ns = unreal.MeshNaniteSettings()
    ns.set_editor_property("enabled", enabled)
    ns.set_editor_property("fallback_relative_error", 1.0)
    return ns


def build_static_mesh(path, mb, materials, nanite=True, collision=False):
    """Create or update `path` from builder `mb`. Returns (StaticMesh, stats dict)."""
    t0 = time.time()
    dm, used = to_dynamic_mesh(mb)
    folder, name = path.rsplit("/", 1)
    pc.ensure_dir(folder)
    mats = []
    for s in used:
        m = materials.get(s)
        mats.append(pc.load(m) if isinstance(m, str) else m)
    sm = pc.EAL.load_asset(path) if pc.EAL.does_asset_exist(path) else None
    if sm is None:
        opts = unreal.GeometryScriptCreateNewStaticMeshAssetOptions()
        opts.set_editor_property("enable_nanite", nanite)
        opts.set_editor_property("enable_collision", collision)
        opts.set_editor_property("enable_recompute_normals", False)
        opts.set_editor_property("enable_recompute_tangents", True)
        sm, outcome = unreal.GeometryScript_NewAssetUtils.create_new_static_mesh_asset_from_mesh(dm, path, opts)
        if sm is None:
            raise RuntimeError("create static mesh failed: " + path)
    copt = unreal.GeometryScriptCopyMeshToAssetOptions()
    copt.set_editor_property("enable_recompute_normals", False)
    copt.set_editor_property("enable_recompute_tangents", True)
    copt.set_editor_property("enable_remove_degenerates", True)
    copt.set_editor_property("replace_materials", True)
    copt.set_editor_property("new_materials", mats)
    copt.set_editor_property("new_material_slot_names", [unreal.Name(s) for s in used])
    copt.set_editor_property("apply_nanite_settings", True)
    copt.set_editor_property("new_nanite_settings", nanite_settings(nanite))
    copt.set_editor_property("emit_transaction", False)
    lod = unreal.GeometryScriptMeshWriteLOD()
    unreal.GeometryScript_AssetUtils.copy_mesh_to_static_mesh(dm, sm, copt, lod)
    pc.EAL.save_asset(path, only_if_is_dirty=False)
    stats = {"asset": path, "tris": mb.tri_count(), "verts": mb.vert_count(), "slots": used,
             "nanite": nanite, "seconds": round(time.time() - t0, 2)}
    pc.log("mesh %s tris=%d slots=%d %.1fs" % (name, stats["tris"], len(used), stats["seconds"]))
    return sm, stats
