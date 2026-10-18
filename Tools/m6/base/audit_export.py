# -*- coding: utf-8 -*-
"""Audit every module blend and export FBX + GLB.

    blender -b --factory-startup --python audit_export.py -- --preload audit
"""
import json
import os
import sys
import time

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import lib_kit as L   # NOTE: do not shadow the injected kernel `K`

MODULES = [
    ("M6_C2_Command.blend", "C2"),
    ("M6_HGR_Hangar.blend", "HGR"),
    ("M6_BRK_Barracks.blend", "BRK"),
    ("M6_RDR_Radar.blend", "RDR"),
    ("M6_GTE_Gate.blend", "GTE"),
    ("M6_UAV_Pad.blend", "UAV"),
    ("M6_CON_Site.blend", "CON"),
    ("M6_CCR_Crane.blend", "CCR"),
    ("M6_SIT_Seat.blend", "SIT"),
    ("M6_Base_Site.blend", "SITE"),
]
MODEL = os.path.join(L.ROOT, "model", "m6", "base")
EXPORT = os.path.join(L.ROOT, "model", "m6", "base", "export")
REPORTS = os.path.join(L.ROOT, "Saved", "M6Base", "reports")


def audit(names, self_intersect=False):
    api = getattr(K, "dsh_audit_api", None)   # kernel global, not lib_kit
    if api is None:
        return {"ok": False, "error": "audit module not preloaded"}
    try:
        return api("mesh", {"objects": names, "self_intersect": self_intersect})
    except Exception as e:
        return {"ok": False, "error": repr(e)}


def main():
    os.makedirs(EXPORT, exist_ok=True)
    os.makedirs(REPORTS, exist_ok=True)
    out = []
    for fname, tag in MODULES:
        path = os.path.join(MODEL, fname)
        if not os.path.exists(path):
            out.append({"tag": tag, "error": "missing"})
            continue
        bpy.ops.wm.open_mainfile(filepath=path)
        L.reset_cache()
        names = [o.name for o in bpy.context.scene.objects if o.type == "MESH"]
        t = time.time()
        rep = audit(names)
        rec = {"tag": tag, "blend": path, "objects": len(names),
               "audit_sec": round(time.time() - t, 2)}
        if isinstance(rep, dict) and rep.get("ok", False) is not False:
            rec["state"] = rep.get("state") or rep.get("verdict")
            rec["totals"] = rep.get("totals")
            objs = rep.get("objects") or []
            bad = [o for o in objs if not o.get("closed", True)] if objs else []
            rec["objects_closed"] = len(objs) - len(bad)
            rec["objects_open"] = len(bad)
            rec["normals_unknown"] = sum(1 for o in objs
                                         if o.get("normals_state") == "unknown")
        else:
            rec["audit_raw"] = rep
        # exports
        fb = os.path.join(EXPORT, tag + ".fbx")
        glb = os.path.join(EXPORT, tag + ".glb")
        try:
            bpy.ops.export_scene.fbx(filepath=fb, use_selection=False,
                                     object_types={"MESH"},
                                     apply_scale_options="FBX_SCALE_ALL",
                                     path_mode="COPY", embed_textures=False,
                                     mesh_smooth_type="FACE")
            rec["fbx"] = fb
            rec["fbx_bytes"] = os.path.getsize(fb)
        except Exception as e:
            rec["fbx_error"] = repr(e)
        try:
            bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB",
                                      use_selection=False, export_apply=True)
            rec["glb"] = glb
            rec["glb_bytes"] = os.path.getsize(glb)
        except Exception as e:
            rec["glb_error"] = repr(e)
        out.append(rec)
        print("AUDIT %s %s" % (tag, json.dumps(rec, ensure_ascii=False)[:400]))
    rp = os.path.join(REPORTS, "audit_export.json")
    with open(rp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("HEADLESS " + json.dumps({"reports": rp, "items": out}, ensure_ascii=False))


if __name__ == "__main__":
    main()
