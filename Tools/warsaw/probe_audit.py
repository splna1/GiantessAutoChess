# -*- coding: utf-8 -*-
"""Probe: dump the full audit record of one object to see why clean=false."""
import bpy
import json

bpy.ops.wm.open_mainfile(filepath=r"E:\AI\Tread\Tread\model\warsaw\landmarks\Warsaw_02_Zamek.blend")
api = K.dsh_audit_api
objs = ["GEO-ZAMEK-yard", "GEO-ZAMEK-body"]
for flag in (False, True):
    r = api("mesh", {"objects": objs, "self_intersect": flag})
    print("HEADLESS " + json.dumps({"self_intersect": flag, "result": r}, ensure_ascii=False)[:4000])
