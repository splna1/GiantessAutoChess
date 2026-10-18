# -*- coding: utf-8 -*-
"""Audit gate for the Warsaw landmark set (needs preload="audit").

Opens each landmark .blend in turn and runs the plugin's mesh audit on every
mesh object, returning a compact per-file summary.  `degraded` is NOT a pass.
"""
import bpy
import json
import os

LM = r"E:\AI\Tread\Tread\model\warsaw\landmarks"
FILES = [
    "Warsaw_01_Rynek.blend",
    "Warsaw_02_Zamek.blend",
    "Warsaw_03_Barbakan.blend",
    "Warsaw_04_Lazienki.blend",
    "Warsaw_05_Stadion.blend",
    "Warsaw_06_PKin.blend",
    "Warsaw_Board_Landmarks.blend",
]

api = K.dsh_audit_api          # injected by preload="audit"
out = []
for f in FILES:
    p = os.path.join(LM, f)
    if not os.path.exists(p):
        out.append({"file": f, "error": "missing"})
        continue
    bpy.ops.wm.open_mainfile(filepath=p)
    names = [o.name for o in bpy.data.objects if o.type == "MESH"]
    rec = {"file": f, "objects": len(names)}
    try:
        r = api("mesh", {"objects": names, "self_intersect": True})
        objs = r.get("objects", [])
        bad = [o for o in objs if not o.get("clean")]
        rec["state"] = r.get("state") or r.get("verdict")
        rec["clean"] = r.get("clean")
        rec["unclean_objects"] = [o.get("name") for o in bad][:8]
        rec["unclean_count"] = len(bad)
        keys = ("boundary_edges", "nonmanifold_edges", "degenerate_faces",
                "loose_verts", "loose_edges", "self_intersections",
                "normals_inverted", "empty")
        tot = {k: 0 for k in keys}
        for o in objs:
            for k in keys:
                tot[k] += int(o.get(k) or 0)
        rec["totals"] = tot
        rec["normals"] = {s: sum(1 for o in objs if o.get("normals_state") == s)
                          for s in ("pass", "fail", "unknown")}
        rec["closed_false"] = [o.get("name") for o in objs if not o.get("closed")][:8]
    except Exception as e:
        rec["error"] = "%s: %s" % (type(e).__name__, e)
    out.append(rec)

print("HEADLESS " + json.dumps({"audit": out}, ensure_ascii=False))
