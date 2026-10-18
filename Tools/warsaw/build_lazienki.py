# -*- coding: utf-8 -*-
"""04 瓦津基宫 Pałac na Wyspie — Warsaw landmark set.

Neoclassical palace on an island in the Łazienki lake: a two-storey central
block with a giant-order portico, pediment and shallow dome with a lantern,
two end pavilions joined by low galleries, balustrades along every roofline,
a stone bridge from the shore, and the lake itself.
"""
import bpy
import math
import os
import sys
import json
from mathutils import Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import lib_geom as G
import spec as S

OUT_BLEND = r"E:\AI\Tread\Tread\model\warsaw\landmarks\Warsaw_04_Lazienki.blend"

SP = S.LAZIENKI
MW, MD = SP["main"]
MH = SP["main_h"]          # 12.2 to the balustrade
WW, WD = SP["wing"]
GW, GD = SP["gallery"]
BODY = 10.4                # cornice of the main block


def column(mb, x, y, z0, h, r=0.42, seg=12):
    mb.lathe([(r * 1.28, z0), (r * 1.28, z0 + 0.18), (r, z0 + 0.28),
              (r * 0.88, z0 + h - 0.45), (r * 1.12, z0 + h - 0.32),
              (r * 1.30, z0 + h - 0.16), (r * 1.30, z0 + h)], x, y, seg=seg)


def balustrade_ring(mb, x0, y0, x1, y1, z, h=0.85):
    mb.balustrade(x0, y0, x1, y0, z, h)
    mb.balustrade(x0, y1, x1, y1, z, h)
    mb.balustrade(x0, y0, x0, y1, z, h)
    mb.balustrade(x1, y0, x1, y1, z, h)


def build_block(B, T, W, R, D, cx, cy, w, d, h_body, rows, bays, ridge="x"):
    """Generic palace block with two window rows and a hip roof."""
    x0, x1 = cx - w / 2, cx + w / 2
    y0, y1 = cy - d / 2, cy + d / 2
    B.box(x0, y0, 0.0, x1, y1, h_body)
    T.box(x0 - 0.14, y0 - 0.14, 0.0, x1 + 0.14, y1 + 0.14, 0.85)
    T.box(x0 - 0.20, y0 - 0.20, h_body - 0.55, x1 + 0.20, y1 + 0.20, h_body + 0.05)
    # pilasters on the long facades
    for k in range(bays + 1):
        x = x0 + k * w / bays
        for yy, s in ((y0, -1), (y1, 1)):
            T.box(x - 0.16, yy - (0.10 if s < 0 else 0.0), 0.9,
                  x + 0.16, yy + (0.0 if s < 0 else 0.10), h_body - 0.6)
    for r, (z, hh) in enumerate(rows):
        for k in range(bays):
            x = x0 + (k + 0.5) * w / bays
            for yy, s in ((y0, -1), (y1, 1)):
                W.push(Matrix.Translation((x, yy, z)) @
                       Matrix.Rotation(0.0 if s < 0 else math.pi, 4, "Z"))
                W.window_glass(hh * 0.55, hh); W.pop()
                T.push(Matrix.Translation((x, yy, z)) @
                       Matrix.Rotation(0.0 if s < 0 else math.pi, 4, "Z"))
                T.window_frame(hh * 0.55, hh, frame=0.10, sill=True)
                if r == 0:
                    T.prism_y([(-hh * 0.30, hh + 0.16), (hh * 0.30, hh + 0.16), (0.0, hh + 0.62)], -0.00, 0.22)
                T.pop()
    return x0, x1, y0, y1


def main():
    G.scene_reset()
    col = G.collection("COL_LM_LAZIENKI")
    root = G.empty("LM_LAZIENKI", col)

    B = G.MB("LAZ-body")
    T = G.MB("LAZ-trim")
    W = G.MB("LAZ-win")
    R = G.MB("LAZ-roof")
    D = G.MB("LAZ-detail")
    Gd = G.MB("LAZ-gold")
    Wt = G.MB("LAZ-water")
    Gr = G.MB("LAZ-green")

    # ---- lake + island ---------------------------------------------------
    Wt.lathe([(SP["water_r"], -1.20), (SP["water_r"], -0.35)], seg=64)
    Gr.lathe([(SP["island_r"], -0.40), (SP["island_r"], 0.20),
              (SP["island_r"] - 1.6, 0.42), (SP["island_r"] - 3.2, 0.30)], seg=48)
    Gr.lathe([(SP["island_r"] - 3.2, 0.30), (SP["island_r"] - 3.2, 0.26)], seg=48)

    # ---- central block ---------------------------------------------------
    mx0, mx1, my0, my1 = build_block(B, T, W, R, D, 0.0, 0.0, MW, MD,
                                     BODY, [(1.10, 2.35), (5.90, 2.10)], 9)
    # rusticated ground floor band
    for z in (1.0, 2.3, 3.6, 4.9):
        T.box(mx0 - 0.10, my0 - 0.10, z, mx1 + 0.10, my0 + 0.02, z + 0.10)
        T.box(mx0 - 0.10, my1 - 0.02, z, mx1 + 0.10, my1 + 0.10, z + 0.10)
    # roof + balustrade
    R.hip(mx0 - 0.55, my0 - 0.55, mx1 + 0.55, my1 + 0.55, BODY, 3.4, ridge_axis="x")
    T.box(mx0 - 0.42, my0 - 0.42, BODY + 0.02, mx1 + 0.42, BODY + 0.02 + 0.0, BODY + 0.3) if False else None
    balustrade_ring(T, mx0 - 0.40, my0 - 0.40, mx1 + 0.40, my1 + 0.40, BODY + 0.10)

    # ---- giant-order portico on the lake facade --------------------------
    py = my0 - 2.6
    T.box(mx0 * 0.55, py - 1.5, 0.0, mx1 * 0.55, py + 0.4, 0.55)      # stylobate
    for k in range(4):
        x = -(MW * 0.30) + k * (MW * 0.60 / 3.0)
        column(T, x, py - 0.6, 0.55, 7.4)
        Gd.lathe([(0.52, 7.95), (0.52, 8.15), (0.40, 8.15)], x, py - 0.6, seg=12)
    T.box(-MW * 0.36, py - 1.7, 7.95, MW * 0.36, py + 0.2, 8.60)       # entablature
    T.prism_y([(-MW * 0.36, 8.60), (MW * 0.36, 8.60), (0.0, 10.40)], py - 1.5, py - 0.5)
    # steps down to the water
    for i in range(3):
        T.box(-6.2, py - 2.6 - i * 1.1, 0.0, 6.2, py - 1.5 - i * 1.1, 0.55 - i * 0.18)

    # ---- dome ------------------------------------------------------------
    R.dome(0.0, 0.0, BODY + 0.10, SP["dome_r"], SP["dome_h"], seg=40, rings=12)
    T.lathe([(SP["dome_r"] + 0.28, BODY + 0.10), (SP["dome_r"] + 0.28, BODY + 0.62),
             (SP["dome_r"] - 0.10, BODY + 0.62)], 0, 0, seg=40)
    T.lathe([(1.55, BODY + SP["dome_h"] - 0.10), (1.55, BODY + SP["dome_h"] + 1.35),
             (1.85, BODY + SP["dome_h"] + 1.50)], 0, 0, seg=16)
    R.dome(0.0, 0.0, BODY + SP["dome_h"] + 1.50, 1.95, 1.55, seg=20, rings=6)
    Gd.lathe([(0.20, BODY + SP["dome_h"] + 2.9), (0.20, BODY + SP["dome_h"] + 4.2),
              (0.0, BODY + SP["dome_h"] + 4.55)], 0, 0, seg=10)

    # ---- galleries + end pavilions ---------------------------------------
    gx = MW / 2.0
    for s in (-1, 1):
        cx = s * (gx + GW / 2.0)
        build_block(B, T, W, R, D, cx, 0.0, GW, GD, SP["gallery_h"],
                    [(1.05, 2.05)], 3)
        R.hip(cx - GW / 2 - 0.4, -GD / 2 - 0.4, cx + GW / 2 + 0.4, GD / 2 + 0.4,
              SP["gallery_h"], 2.2, ridge_axis="x")
        balustrade_ring(T, cx - GW / 2 - 0.3, -GD / 2 - 0.3,
                        cx + GW / 2 + 0.3, GD / 2 + 0.3, SP["gallery_h"] + 0.05, h=0.75)
        px = s * (gx + GW + WW / 2.0)
        build_block(B, T, W, R, D, px, 0.0, WW, WD, SP["wing_h"],
                    [(1.15, 2.30), (6.10, 2.00)], 4)
        R.hip(px - WW / 2 - 0.45, -WD / 2 - 0.45, px + WW / 2 + 0.45, WD / 2 + 0.45,
              SP["wing_h"], 3.0, ridge_axis="x")
        balustrade_ring(T, px - WW / 2 - 0.35, -WD / 2 - 0.35,
                        px + WW / 2 + 0.35, WD / 2 + 0.35, SP["wing_h"] + 0.05, h=0.85)
        # a pair of statues on the pavilion corners
        for sy in (-1, 1):
            D.boxc(px + s * (WW / 2 - 0.9), sy * (WD / 2 - 0.9), SP["wing_h"] + 1.4,
                   0.55, 0.55, 1.9)
            D.lathe([(0.30, SP["wing_h"] + 2.3), (0.22, SP["wing_h"] + 2.9),
                     (0.0, SP["wing_h"] + 3.15)], px + s * (WW / 2 - 0.9),
                    sy * (WD / 2 - 0.9), seg=8)

    # ---- bridge from the shore -------------------------------------------
    by0, by1 = -SP["island_r"] + 1.0, -SP["water_r"] - 1.0
    D.box(-6.4, by1, -0.20, 6.4, by0, 0.30)
    for k in range(7):
        D.box(-6.2, by1 + 3.2 + k * 3.4, 0.30, 6.2, by1 + 3.6 + k * 3.4, 0.40)
    for s in (-1, 1):
        T.box(s * 6.4 - 0.35, by1, 0.30, s * 6.4 + 0.35, by0, 1.35)
        T.box(s * 6.4 - 0.55, by1, 1.35, s * 6.4 + 0.55, by0, 1.60)
        for k in range(14):
            x = s * 6.4
            yy = by1 + 2.0 + k * 3.0
            T.lathe([(0.22, 0.30), (0.16, 1.30)], x, yy, seg=6)

    # ---- trees around the island -----------------------------------------
    rng = __import__("random").Random(77)
    for i in range(11):
        a = math.tau * i / 11.0 + 0.3
        r = SP["island_r"] - 4.0 - rng.uniform(0, 2.5)
        x, y = math.cos(a) * r, math.sin(a) * r
        if abs(x) < 12 and y < 0:
            continue
        D.lathe([(0.34, 0.25), (0.26, 3.2)], x, y, seg=6)
        Gr.lathe([(2.6, 3.0), (1.7, 5.2), (0.0, 7.0)], x, y, seg=9)

    objs = []
    objs.append(B.emit(col, G.material("laz_stucco", "#e6e0cf", 0.72, pattern="plaster", scale=0.5),
                       "GEO-LAZIENKI-body", parent=root))
    objs.append(T.emit(col, G.material("laz_stone", "#efe9da", 0.68, pattern="stone", scale=1.6),
                       "GEO-LAZIENKI-stone", parent=root))
    objs.append(W.emit(col, G.material("laz_glass", "#1b2226", 0.12, 0.6),
                       "GEO-LAZIENKI-windows", parent=root))
    objs.append(R.emit(col, G.material("laz_roof", "#6d7a72", 0.62, 0.10, pattern="metal", scale=0.6),
                       "GEO-LAZIENKI-roof", parent=root))
    objs.append(D.emit(col, G.material("laz_stone2", "#d8d0bd", 0.74, pattern="stone", scale=1.4),
                       "GEO-LAZIENKI-detail", parent=root))
    objs.append(Gd.emit(col, G.material("laz_gold", "#c9a23c", 0.28, 1.0),
                        "GEO-LAZIENKI-gold", parent=root))
    objs.append(Wt.emit(col, G.material("laz_water", "#33556a", 0.10, 0.25),
                        "GEO-LAZIENKI-water", parent=root))
    objs.append(Gr.emit(col, G.material("laz_grass", "#5f7c46", 0.92),
                        "GEO-LAZIENKI-green", parent=root))

    G.setup_world(strength=0.45, sky=(0.64, 0.74, 0.86))
    G.sun(rot=(math.radians(48), 0.0, math.radians(40)), energy=4.0)

    mn = [1e9] * 3
    mx = [-1e9] * 3
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ G.Vector(c)
            for i in range(3):
                mn[i] = min(mn[i], w[i])
                mx[i] = max(mx[i], w[i])
    stats = {"landmark": "Palac na Wyspie", "objects": len(objs),
             "verts": sum(len(o.data.vertices) for o in objs),
             "tris": sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objs),
             "dropped_faces": sum(getattr(m, "dropped_faces", 0)
                                  for m in (B, T, W, R, D, Gd, Wt, Gr)),
             "bbox": [round(v, 2) for v in mn] + [round(v, 2) for v in mx],
             "size": [round(mx[i] - mn[i], 2) for i in range(3)]}
    os.makedirs(os.path.dirname(OUT_BLEND), exist_ok=True)
    G.save(OUT_BLEND)
    stats["blend"] = OUT_BLEND
    print("HEADLESS " + json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
