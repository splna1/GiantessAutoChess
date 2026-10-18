# -*- coding: utf-8 -*-
"""Assemble the five Warsaw landmarks on the level-2 board.

Links each landmark collection from its own .blend into one scene, places the
root empty at the board coordinate taken from the HTML prototype
(Saved/UIPrototype/Tread_Warsaw_Board_Prototype.html), and adds the Vistula
band + city ground so the set can be inspected at board scale.
"""
import bpy
import math
import os
import sys
import json
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import lib_geom as G
import spec as S

LM_DIR = r"E:\AI\Tread\Tread\model\warsaw\landmarks"
OUT = os.path.join(LM_DIR, "Warsaw_Board_Landmarks.blend")

ITEMS = [
    ("Warsaw_01_Rynek.blend", "COL_LM_RYNEK", "LM_RYNEK", S.RYNEK["place"]),
    ("Warsaw_02_Zamek.blend", "COL_LM_ZAMEK", "LM_ZAMEK", S.ZAMEK["place"]),
    ("Warsaw_03_Barbakan.blend", "COL_LM_BARBAKAN", "LM_BARBAKAN", S.BARBAKAN["place"]),
    ("Warsaw_04_Lazienki.blend", "COL_LM_LAZIENKI", "LM_LAZIENKI", S.LAZIENKI["place"]),
    ("Warsaw_05_Stadion.blend", "COL_LM_STADION", "LM_STADION", S.STADION["place"]),
    ("Warsaw_06_PKin.blend", "COL_LM_PKIN", "LM_PKIN", S.PKIN["place"]),
]


def main():
    G.scene_reset()
    top = G.collection("COL_WARSAW_BOARD")
    report = []

    for fname, cname, root_name, (px, py) in ITEMS:
        path = os.path.join(LM_DIR, fname)
        if not os.path.exists(path):
            report.append({"file": fname, "error": "missing"})
            continue
        with bpy.data.libraries.load(path, link=False) as (src, dst):
            dst.collections = [cname]
        coll = dst.collections[0]
        if coll is None:
            report.append({"file": fname, "error": "collection not found"})
            continue
        top.children.link(coll)
        root = bpy.data.objects.get(root_name)
        if root:
            root.location = (px, py, 0.0)
        n_obj = len([o for o in coll.all_objects if o.type == "MESH"])
        n_tri = sum(sum(len(p.vertices) - 2 for p in o.data.polygons)
                    for o in coll.all_objects if o.type == "MESH")
        report.append({"file": fname, "objects": n_obj, "tris": n_tri,
                       "place": [px, py], "ok": True})

    # ---- ground + Vistula band ------------------------------------------
    gcol = G.collection("COL_WARSAW_GROUND")
    ground = G.MB("GROUND")
    ground.box(-2400, -3200, -3.2, 5400, 3200, -0.4)
    gob = ground.emit(gcol, G.material("warsaw_ground", "#63665b", 0.94,
                                       pattern="plaster", scale=0.03),
                      "GEO-GROUND", smooth=False)
    river = G.MB("RIVER")
    river.box(2750, -3200, -2.6, 3250, 3200, -0.28)
    rob = river.emit(gcol, G.material("vistula", "#33566a", 0.10, 0.25), "GEO-VISTULA")
    # bridges (schematic, on the prototype's bridge rows)
    br = G.MB("BRIDGES")
    for py in (296, 386, 500, 648):
        y = -(py - 500) * (800.0 / 120.0)
        br.box(2700, y - 14, -0.5, 3300, y + 14, 1.2)
    bob = br.emit(gcol, G.material("bridge_stone", "#a9a294", 0.8), "GEO-BRIDGES")
    # board rim so the set reads as a table-top board
    rim = G.MB("RIM")
    rim.box(-2400, -3200, -3.2, 5400, -3140, 6.0)
    rim.box(-2400, 3140, -3.2, 5400, 3200, 6.0)
    rim.box(-2400, -3200, -3.2, -2340, 3200, 6.0)
    rim.box(5340, -3200, -3.2, 5400, 3200, 6.0)
    rim.emit(gcol, G.material("board_rim", "#2b2825", 0.7), "GEO-BOARD-RIM")

    G.setup_world(strength=0.55, sky=(0.60, 0.71, 0.85))
    G.sun(rot=(math.radians(48), 0.0, math.radians(40)), energy=4.0)

    stats = {"objects": len([o for o in bpy.data.objects if o.type == "MESH"]),
             "tris": sum(sum(len(p.vertices) - 2 for p in o.data.polygons)
                         for o in bpy.data.objects if o.type == "MESH"),
             "landmarks": report}
    os.makedirs(LM_DIR, exist_ok=True)
    G.save(OUT)
    stats["blend"] = OUT
    print("HEADLESS " + json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
