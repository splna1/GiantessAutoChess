# -*- coding: utf-8 -*-
"""02 皇家城堡 Zamek Królewski — Warsaw landmark set.

A four-wing baroque palace around a courtyard.  The long south wing carries the
public facade: giant pilasters, piano-nobile windows with pediments, a heavy
cornice, a Polish broken (mansard) copper roof with dormers.  The Sigismund
Tower rises at the west corner with a clock, balustrade, onion helmet, lantern
and gilded spire; the shorter Władysław Tower closes the east corner.
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

OUT_BLEND = r"E:\AI\Tread\Tread\model\warsaw\landmarks\Warsaw_02_Zamek.blend"

SP = S.ZAMEK
EAV = 18.6


def build_wing(body, T, W, roof, D, L, depth, pos, rz, n_side_arcade=False):
    """Wing in local frame: facade at y=0 facing -Y, body to +Y."""
    for mb in (body, T, W, roof, D):
        mb.at(pos[0], pos[1], 0.0, rz)
    hx = L / 2.0

    body.box(-hx, 0.0, 0.0, hx, depth, EAV)
    # plinth + string courses + main cornice
    T.box(-hx - 0.10, -0.20, 0.0, hx + 0.10, 0.0, 0.95)
    for z in (5.4, 10.4, 14.6):
        T.box(-hx - 0.07, -0.14, z - 0.09, hx + 0.07, 0.0, z + 0.04)
    T.box(-hx - 0.30, -0.42, EAV - 0.85, hx + 0.30, 0.02, EAV + 0.05)
    T.box(-hx - 0.18, -0.28, EAV - 1.15, hx + 0.18, 0.0, EAV - 0.85)

    nb = max(2, int(round(L / 4.8)))
    bw = L / nb

    # giant pilasters on the piano nobile
    for k in range(nb + 1):
        x = -hx + k * bw
        T.box(x - 0.22, -0.11, 5.6, x + 0.22, 0.0, EAV - 1.2)
        T.box(x - 0.30, -0.20, EAV - 1.75, x + 0.30, 0.0, EAV - 1.35)
        T.box(x - 0.30, -0.20, 5.5, x + 0.30, 0.0, 5.75)

    rows = [(2.9, 1.70, 2.15, False), (8.2, 1.85, 3.10, True),
            (12.9, 1.70, 2.45, False), (16.3, 0.95, 1.15, False)]
    for k in range(nb):
        x = -hx + (k + 0.5) * bw
        for z, ww, hh, ped in rows:
            W.at(x, 0, z); W.window_glass(ww, hh); W.pop()
            T.at(x, 0, z); T.window_frame(ww, hh, frame=0.10); T.pop()
            if ped:
                T.push(Matrix.Translation((x, -0.02, z + hh + 0.10)))
                T.prism_y([(-ww / 2 - 0.28, 0.0), (ww / 2 + 0.28, 0.0), (0.0, 0.78)], -0.26, 0.0)
                T.box(-ww / 2 - 0.34, -0.30, -0.14, ww / 2 + 0.34, -0.02, 0.02)
                T.pop()

    # courtyard side: simple arcade
    if n_side_arcade:
        nb2 = max(3, int(L / 4.2))
        for k in range(nb2):
            x = -hx + (k + 0.5) * (L / nb2)
            W.at(x, depth, 1.2); W.push(Matrix.Rotation(math.pi, 4, "Z"))
            W.arch_open(1.8, 2.4, 7); W.pop(); W.pop()
            T.at(x, depth, 1.2); T.push(Matrix.Rotation(math.pi, 4, "Z"))
            T.arch_ring(1.8, 2.4, 7); T.pop(); T.pop()
            W.at(x, depth, 8.2); W.push(Matrix.Rotation(math.pi, 4, "Z"))
            W.window_glass(1.3, 2.2); W.pop(); W.pop()
            T.at(x, depth, 8.2); T.push(Matrix.Rotation(math.pi, 4, "Z"))
            T.window_frame(1.3, 2.2); T.pop(); T.pop()

    # ---- mansard copper roof --------------------------------------------
    roof.mansard(-hx - 0.55, -0.70, hx + 0.55, depth + 0.70, EAV, 9.0, 3.0, 2.2, ridge_axis="x")
    # dormers standing on the lower slope
    nd = max(2, int(L / 8.0))
    for k in range(nd):
        x = -hx + (k + 0.5) * (L / nd)
        W.at(x, -1.24, EAV + 0.55); W.window_glass(1.05, 1.35, y0=-0.06, y1=0.06); W.pop()
        T.at(x, -1.24, EAV + 0.55); T.window_frame(1.05, 1.35, frame=0.09, sill=False); T.pop()
        roof.at(x, 0.0, EAV)
        roof.box(-0.92, -1.30, 0.30, 0.92, 1.10, 2.75)
        roof.hip(-1.05, -1.42, 1.05, 1.22, 2.75, 0.85, ridge_axis="x")
        roof.pop()

    for mb in (body, T, W, roof, D):
        mb.pop()


def build_tower(body, T, W, roof, gold, D, cx, cy, w, hbody, hhelm, faces=4, clock=True):
    hx = w / 2.0
    body.box(cx - hx, cy - hx, 0.0, cx + hx, cy + hx, hbody)
    # shaft articulation
    for z in (5.4, 10.4, 14.6, 22.0, 30.0):
        T.box(cx - hx - 0.09, cy - hx - 0.09, z - 0.10, cx + hx + 0.09, cy + hx + 0.09, z + 0.06)
    # corner quoins
    for sx in (-1, 1):
        for sy in (-1, 1):
            qz = 1.0
            while qz < hbody - 2.0:
                wq = 0.55 if (int(qz) // 3) % 2 == 0 else 0.38
                T.box(cx + sx * hx - (wq if sx > 0 else 0) - (0 if sx > 0 else 0),
                      cy + sy * hx - (wq if sy > 0 else 0),
                      qz, cx + sx * hx + (0 if sx > 0 else wq),
                      cy + sy * hx + (0 if sy > 0 else wq), qz + 0.5)
                qz += 1.05
    # windows on all four faces
    for face in range(4):
        ang = face * 90.0
        for z in (7.0, 12.0, 16.4, 21.0):
            for off in (-hx * 0.42, hx * 0.42):
                W.push(Matrix.Translation((cx, cy, 0)) @ Matrix.Rotation(math.radians(ang), 4, "Z"))
                W.at(off, -hx, z); W.window_glass(0.95, 1.9); W.pop(); W.pop()
                T.push(Matrix.Translation((cx, cy, 0)) @ Matrix.Rotation(math.radians(ang), 4, "Z"))
                T.at(off, -hx, z); T.window_frame(0.95, 1.9, frame=0.09); T.pop(); T.pop()

    # clock band
    if clock:
        T.box(cx - hx - 0.12, cy - hx - 0.12, hbody - 4.6, cx + hx + 0.12, cy + hx + 0.12, hbody - 3.4)
        for face in range(4):
            ang = math.radians(face * 90.0)
            M = (Matrix.Translation((cx, cy, hbody - 4.0)) @ Matrix.Rotation(ang, 4, "Z") @
                 Matrix.Translation((0, -hx - 0.13, 0)) @ Matrix.Rotation(math.pi / 2, 4, "X"))
            T.push(M); T.lathe([(1.55, 0.0), (1.55, 0.10)], 0, 0, seg=20); T.pop()
            D.push(M)
            D.box(-0.07, 0.10, -0.85, 0.07, 0.18, 0.72)
            D.box(-0.55, 0.10, -0.05, 0.05, 0.18, 0.07)
            D.pop()
    # crowning cornice + balustrade
    T.box(cx - hx - 0.55, cy - hx - 0.55, hbody - 0.55, cx + hx + 0.55, cy + hx + 0.55, hbody + 0.05)
    T.box(cx - hx - 0.30, cy - hx - 0.30, hbody - 0.95, cx + hx + 0.30, cy + hx + 0.30, hbody - 0.55)
    for side in range(4):
        ang = side * 90.0
        T.push(Matrix.Translation((cx, cy, hbody + 0.05)) @ Matrix.Rotation(math.radians(ang), 4, "Z"))
        T.balustrade(-hx - 0.35, -hx - 0.35, hx + 0.35, -hx - 0.35, 0.0, h=0.95, spacing=0.62)
        T.pop()
    # helmet: onion dome + lantern + spire
    roof.onion(cx, cy, hbody + 0.05, hx + 0.30, hhelm, seg=24)
    T.lathe([(1.15, hbody + 0.05 + hhelm * 0.86), (1.15, hbody + 0.05 + hhelm * 0.86 + 1.5),
             (0.85, hbody + 0.05 + hhelm * 0.86 + 1.7)], cx, cy, seg=12)
    roof.onion(cx, cy, hbody + 0.05 + hhelm * 0.86 + 1.7, 0.95, 2.2, seg=16)
    gold.lathe([(0.16, hbody + 0.05 + hhelm * 0.86 + 3.7),
                (0.16, hbody + 0.05 + hhelm * 0.86 + 7.2),
                (0.0, hbody + 0.05 + hhelm * 0.86 + 7.8)], cx, cy, seg=8)
    gold.lathe([(0.34, hbody + 0.05 + hhelm * 0.86 + 5.0),
                (0.34, hbody + 0.05 + hhelm * 0.86 + 5.5), (0.0, hbody + 0.05 + hhelm * 0.86 + 5.5)],
               cx, cy, seg=10)


def main():
    G.scene_reset()
    col = G.collection("COL_LM_ZAMEK")
    root = G.empty("LM_ZAMEK", col)

    body = G.MB("ZAMEK-body")
    T = G.MB("ZAMEK-trim")
    W = G.MB("ZAMEK-win")
    roof = G.MB("ZAMEK-roof")
    gold = G.MB("ZAMEK-gold")
    D = G.MB("ZAMEK-detail")

    # south (public) wing: 92 long, 18 deep, facade at y=-44
    build_wing(body, T, W, roof, D, 92.0, 18.0, (0.0, -44.0), 0.0, n_side_arcade=True)
    # north wing: 92 long, 16 deep, facade at y=+28 facing north
    build_wing(body, T, W, roof, D, 92.0, 16.0, (0.0, 28.0), 180.0, n_side_arcade=True)
    # west wing: 72 long, 16 deep, facade at x=-46 facing west
    build_wing(body, T, W, roof, D, 72.0, 16.0, (-46.0, -8.0), -90.0, n_side_arcade=True)
    # east wing: 72 long, 16 deep, facade at x=+46 facing east
    build_wing(body, T, W, roof, D, 72.0, 16.0, (46.0, -8.0), 90.0, n_side_arcade=True)

    # towers at the two west/east corners of the public facade
    build_tower(body, T, W, roof, gold, D, -38.0, -48.0, 11.0, 44.0, 14.0, clock=True)
    build_tower(body, T, W, roof, gold, D, 38.0, -48.0, 9.0, 30.0, 9.5, clock=False)

    # courtyard paving
    P = G.MB("ZAMEK-yard")
    P.box(-30.0, -26.0, -0.6, 30.0, 12.0, 0.0)
    T.lathe([(5.0, 0.0), (5.0, 0.30), (4.4, 0.30), (4.4, 0.0)], 0, -7.0, seg=8)
    D.lathe([(0.9, 0.0), (0.9, 1.7), (0.6, 1.9)], 0, -7.0, seg=10)

    objs = []
    objs.append(body.emit(col, G.material("zamek_plaster", "#cfa96c", 0.76, pattern="plaster", scale=0.35),
                          "GEO-ZAMEK-body", parent=root))
    objs.append(T.emit(col, G.material("zamek_stone", "#e2d9c2", 0.72, pattern="stone", scale=1.3),
                       "GEO-ZAMEK-trim", parent=root))
    objs.append(W.emit(col, G.material("zamek_glass", "#1a2126", 0.12, 0.6),
                       "GEO-ZAMEK-windows", parent=root))
    objs.append(roof.emit(col, G.material("zamek_copper", "#3d6a57", 0.58, 0.15, pattern="metal", scale=0.8),
                          "GEO-ZAMEK-roof", parent=root, smooth=False))
    objs.append(gold.emit(col, G.material("zamek_gold", "#c9a23c", 0.28, 1.0),
                          "GEO-ZAMEK-gold", parent=root, smooth=True))
    objs.append(D.emit(col, G.material("zamek_iron", "#2b2825", 0.55, 0.8),
                       "GEO-ZAMEK-iron", parent=root))
    objs.append(P.emit(col, G.material("zamek_yard", "#8c8578", 0.88, pattern="stone", scale=2.0),
                       "GEO-ZAMEK-yard", parent=root))

    G.setup_world(strength=0.42, sky=(0.62, 0.72, 0.84))
    G.sun(rot=(math.radians(50), 0.0, math.radians(35)), energy=3.9)

    mn = [1e9] * 3
    mx = [-1e9] * 3
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ G.Vector(c)
            for i in range(3):
                mn[i] = min(mn[i], w[i])
                mx[i] = max(mx[i], w[i])
    stats = {"landmark": "Zamek Krolewski", "objects": len(objs),
             "verts": sum(len(o.data.vertices) for o in objs),
             "tris": sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objs),
             "bbox": [round(v, 2) for v in mn] + [round(v, 2) for v in mx],
             "size": [round(mx[i] - mn[i], 2) for i in range(3)]}
    os.makedirs(os.path.dirname(OUT_BLEND), exist_ok=True)
    G.save(OUT_BLEND)
    stats["blend"] = OUT_BLEND
    print("HEADLESS " + json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
