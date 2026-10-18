# -*- coding: utf-8 -*-
"""03 巴比肯 Barbakan — Warsaw landmark set.

The半圆形 red-brick barbican: a battered semicircular bastion with three
levels of loopholes, a projecting machicolated gallery, crenellations, the
square Nowomiejska gate tower with a hip roof and the round Prochowa tower
with a conical roof, joined by curtain walls with merlons, plus the wooden
approach bridge over the old moat.
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

OUT_BLEND = r"E:\AI\Tread\Tread\model\warsaw\landmarks\Warsaw_03_Barbakan.blend"

SP = S.BARBAKAN
R_OUT = SP["r_out"]
R_IN = SP["r_in"]
H1, H2, H3 = SP["levels"]
HTOP = H1 + H2 + H3            # 12.1


def arc_poly(r_in, r_out, a0, a1, seg):
    pts = []
    for i in range(seg + 1):
        a = a0 + (a1 - a0) * i / seg
        pts.append((math.cos(a) * r_out, math.sin(a) * r_out))
    for i in range(seg + 1):
        a = a1 + (a0 - a1) * i / seg
        pts.append((math.cos(a) * r_in, math.sin(a) * r_in))
    return pts


def radial(mb, ang_deg, r, z=0.0):
    """Push a frame at radius r on the given angle, +Y pointing outward."""
    a = math.radians(ang_deg)
    return mb.push(Matrix.Translation((math.cos(a) * r, math.sin(a) * r, z)) @
                   Matrix.Rotation(a + math.pi / 2.0, 4, "Z"))


def build_bastion(B, T, W, R, D):
    seg = 30
    # battered three-stage wall
    B.prism_z(arc_poly(R_IN, R_OUT, math.pi, math.tau, seg), 0.0, H1)
    B.prism_z(arc_poly(R_IN, R_OUT - 0.30, math.pi, math.tau, seg), H1, H1 + H2)
    B.prism_z(arc_poly(R_IN, R_OUT - 0.60, math.pi, math.tau, seg), H1 + H2, HTOP)
    # string courses
    for r, z in ((R_OUT + 0.05, H1), (R_OUT - 0.25, H1 + H2)):
        T.prism_z(arc_poly(R_IN, r + 0.16, math.pi, math.tau, seg), z - 0.16, z + 0.10)
    # top cornice
    T.prism_z(arc_poly(R_IN, R_OUT - 0.45, math.pi, math.tau, seg), HTOP - 0.35, HTOP + 0.05)

    # loopholes: three rows on the outer face
    rows = [(1.45, 1.05), (H1 + 1.5, 0.95), (H1 + H2 + 1.5, 0.9)]
    for ri, (z, hh) in enumerate(rows):
        n = 13 - ri * 2
        for i in range(n):
            a = 180.0 + (i + 0.5) * 180.0 / n
            r = R_OUT - 0.28 * ri
            radial(W, a, r, z)
            W.box(-0.20, -1.0, 0.0, 0.20, 0.05, hh)
            W.pop()
            radial(T, a, r, z - 0.12)
            T.box(-0.34, -0.55, 0.0, 0.34, 0.02, 0.14)
            T.box(-0.34, -0.55, hh, 0.34, 0.02, hh + 0.14)
            T.pop()

    # machicolated gallery: corbels + projecting parapet
    n = 34
    for i in range(n):
        a = 180.0 + (i + 0.5) * 180.0 / n
        radial(T, a, R_OUT - 0.55, HTOP - 1.35)
        T.box(-0.18, -0.80, 0.0, 0.18, 0.10, 0.55)
        T.box(-0.18, -0.95, 0.55, 0.18, 0.10, 1.35)
        T.pop()
    B.prism_z(arc_poly(R_OUT - 0.20, R_OUT + 0.85, math.pi, math.tau, seg), HTOP - 0.10, HTOP + 1.30)
    T.prism_z(arc_poly(R_OUT + 0.80, R_OUT + 0.95, math.pi, math.tau, seg), HTOP + 1.10, HTOP + 1.35)
    # crenellations
    m = 26
    for i in range(m):
        a0 = 180.0 + i * 180.0 / m
        a1 = 180.0 + (i + 0.55) * 180.0 / m
        B.prism_z(arc_poly(R_OUT + 0.05, R_OUT + 0.85, math.radians(a0), math.radians(a1), 2),
                  HTOP + 1.30, HTOP + 2.35)

    # inner face: faint arcade lines (stone)
    for i in range(9):
        a = 185.0 + i * 21.0
        radial(T, a, R_IN + 0.06, 0.0)
        T.box(-0.35, -0.06, 0.0, 0.35, 0.12, HTOP - 0.5)
        T.pop()

    # gate passage through the chord
    W.box(-2.4, -1.0, 0.0, 2.4, 3.0, 5.2)
    T.box(-3.0, -0.6, 0.0, -2.4, 0.4, 5.6)
    T.box(2.4, -0.6, 0.0, 3.0, 0.4, 5.6)
    T.box(-3.0, -0.6, 5.2, 3.0, 0.4, 5.7)
    W.push(Matrix.Translation((0, 0, 0)) @ Matrix.Rotation(math.pi, 4, "Z"))
    W.arch_open(4.8, 2.8, 10, y0=-0.02, y1=0.06)
    W.pop()
    T.push(Matrix.Translation((0, 0, 0)) @ Matrix.Rotation(math.pi, 4, "Z"))
    T.arch_ring(4.8, 2.8, 10, 0.30, 0.22)
    T.pop()


def build_tower_square(B, T, W, R, D, cx, cy, w, body, roof_h):
    hx = w / 2.0
    B.box(cx - hx, cy - hx, 0.0, cx + hx, cy + hx, body)
    for z in (H1, H1 + H2, HTOP):
        T.box(cx - hx - 0.12, cy - hx - 0.12, z - 0.16, cx + hx + 0.12, cy + hx + 0.12, z + 0.08)
    T.box(cx - hx - 0.34, cy - hx - 0.34, body - 0.45, cx + hx + 0.34, cy + hx + 0.34, body + 0.05)
    # windows on four faces
    for face in range(4):
        a = face * 90.0
        for z in (1.6, H1 + 1.6, H1 + H2 + 1.6):
            for off in (-hx * 0.40, hx * 0.40):
                W.push(Matrix.Translation((cx, cy, 0)) @ Matrix.Rotation(math.radians(a), 4, "Z"))
                W.at(off, -hx, z); W.window_glass(0.60, 1.35); W.pop(); W.pop()
                T.push(Matrix.Translation((cx, cy, 0)) @ Matrix.Rotation(math.radians(a), 4, "Z"))
                T.at(off, -hx, z); T.window_frame(0.60, 1.35, frame=0.09); T.pop(); T.pop()
    # hip roof + finial
    R.hip(cx - hx - 0.45, cy - hx - 0.45, cx + hx + 0.45, cy + hx + 0.45, body,
          roof_h, ridge_axis="x")
    D.boxc(cx, cy, body + roof_h + 0.55, 0.16, 0.16, 1.10)
    # corner bartizans
    for sx in (-1, 1):
        for sy in (-1, 1):
            T.lathe([(0.72, body - 1.2), (0.72, body + 1.4), (0.95, body + 1.5),
                     (0.95, body + 1.9)], cx + sx * hx, cy + sy * hx, seg=10)
            R.lathe([(1.15, body + 1.9), (0.0, body + 4.2)], cx + sx * hx, cy + sy * hx, seg=10)


def build_tower_round(B, T, W, R, D, cx, cy, r, body, roof_h):
    B.cyl(cx, cy, 0.0, body, r, seg=20)
    for z in (H1 + 0.6, H1 + H2 + 0.6):
        T.lathe([(r + 0.10, z - 0.18), (r + 0.10, z + 0.08), (r, z + 0.08)], cx, cy, seg=20)
    T.lathe([(r + 0.28, body - 0.42), (r + 0.28, body + 0.06), (r, body + 0.06)], cx, cy, seg=20)
    for i in range(10):
        a = math.radians(36 * i)
        W.push(Matrix.Translation((cx, cy, 0)) @ Matrix.Rotation(a, 4, "Z"))
        W.at(0, -r, H1 + 2.0); W.window_glass(0.45, 0.95); W.pop(); W.pop()
        W.push(Matrix.Translation((cx, cy, 0)) @ Matrix.Rotation(a, 4, "Z"))
        W.at(0, -r, H1 + H2 + 2.2); W.window_glass(0.45, 0.95); W.pop(); W.pop()
    R.lathe([(r + 0.55, body), (r * 0.62, body + roof_h * 0.45),
             (r * 0.30, body + roof_h * 0.80), (0.0, body + roof_h)], cx, cy, seg=20)
    D.boxc(cx, cy, body + roof_h + 0.5, 0.14, 0.14, 1.0)


def curtain_wall(B, T, W, p0, p1, h, t):
    B.wall_between(p0, p1, 0.0, h, t)
    T.wall_between(p0, p1, h - 0.32, h + 0.05, t + 0.28)
    # merlons
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    L = math.hypot(dx, dy)
    ang = math.degrees(math.atan2(dy, dx))
    n = max(2, int(L / 2.0))
    T.push(Matrix.Translation((p0[0], p0[1], 0)) @ Matrix.Rotation(math.radians(ang), 4, "Z"))
    for i in range(n):
        x = i * L / n
        B.box(x + 0.2, -t / 2 - 0.08, h, x + L / n - 0.5, t / 2 + 0.08, h + 1.15)
    T.pop()
    # loopholes
    for i in range(max(1, int(L / 5.0))):
        x = (i + 0.5) * L / max(1, int(L / 5.0))
        W.push(Matrix.Translation((p0[0], p0[1], 0)) @ Matrix.Rotation(math.radians(ang), 4, "Z"))
        W.box(x - 0.18, -t / 2 - 0.05, 3.2, x + 0.18, -t / 2 + 0.05, 4.2)
        W.box(x - 0.18, t / 2 - 0.05, 3.2, x + 0.18, t / 2 + 0.05, 4.2)
        W.pop()


def main():
    G.scene_reset()
    col = G.collection("COL_LM_BARBAKAN")
    root = G.empty("LM_BARBAKAN", col)

    B = G.MB("BARB-body")
    T = G.MB("BARB-trim")
    W = G.MB("BARB-open")
    R = G.MB("BARB-roof")
    D = G.MB("BARB-detail")
    P = G.MB("BARB-ground")

    build_bastion(B, T, W, R, D)
    build_tower_square(B, T, W, R, D, 0.0, 9.5, 8.4, 18.5, 8.5)
    build_tower_round(B, T, W, R, D, -30.0, 6.0, 4.6, 20.0, 9.0)
    curtain_wall(B, T, W, (-15.2, 0.0), (-25.6, 4.2), 8.6, 3.2)
    curtain_wall(B, T, W, (15.2, 0.0), (34.0, 2.0), 8.6, 3.2)
    # small corner turret at the east end of the wall
    build_tower_round(B, T, W, R, D, 34.0, 2.0, 3.2, 13.0, 6.0)

    # moat / platform
    P.box(-44.0, -30.0, -1.2, 44.0, 26.0, 0.0)
    # approach bridge
    D.box(-4.5, -25.0, 0.05, 4.5, -14.0, 0.55)
    for k in range(6):
        D.box(-4.5, -24.0 + k * 1.7, 0.55, 4.5, -23.6 + k * 1.7, 0.75)
    for s in (-1, 1):
        T.box(s * 4.5 - 0.25, -25.0, 0.55, s * 4.5 + 0.25, -14.0, 1.55)
        D.box(s * 4.5 - 0.10, -25.0, 1.55, s * 4.5 + 0.10, -14.0, 1.70)

    objs = []
    objs.append(B.emit(col, G.material("barb_brick", "#8f4233", 0.85, pattern="brick",
                                       scale=0.45, hex2="#7a3929", mortar="#a89c88"),
                       "GEO-BARBAKAN-brick", parent=root))
    objs.append(T.emit(col, G.material("barb_stone", "#c3b9a4", 0.80, pattern="stone", scale=1.1),
                       "GEO-BARBAKAN-stone", parent=root))
    objs.append(W.emit(col, G.material("barb_dark", "#15181a", 0.9),
                       "GEO-BARBAKAN-openings", parent=root))
    objs.append(R.emit(col, G.material("barb_roof", "#5a5148", 0.78, pattern="tile", scale=0.5,
                                       hex2="#463f38"),
                       "GEO-BARBAKAN-roof", parent=root))
    objs.append(D.emit(col, G.material("barb_wood", "#4a3a2a", 0.88),
                       "GEO-BARBAKAN-timber", parent=root))
    objs.append(P.emit(col, G.material("barb_ground", "#7c7568", 0.9, pattern="stone", scale=2.0),
                       "GEO-BARBAKAN-ground", parent=root))

    G.setup_world(strength=0.42, sky=(0.62, 0.72, 0.84))
    G.sun(rot=(math.radians(52), 0.0, math.radians(38)), energy=3.9)

    mn = [1e9] * 3
    mx = [-1e9] * 3
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ G.Vector(c)
            for i in range(3):
                mn[i] = min(mn[i], w[i])
                mx[i] = max(mx[i], w[i])
    stats = {"landmark": "Barbakan", "objects": len(objs),
             "verts": sum(len(o.data.vertices) for o in objs),
             "tris": sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objs),
             "dropped_faces": sum(getattr(m, "dropped_faces", 0) for m in (B, T, W, R, D, P)),
             "bbox": [round(v, 2) for v in mn] + [round(v, 2) for v in mx],
             "size": [round(mx[i] - mn[i], 2) for i in range(3)]}
    os.makedirs(os.path.dirname(OUT_BLEND), exist_ok=True)
    G.save(OUT_BLEND)
    stats["blend"] = OUT_BLEND
    print("HEADLESS " + json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
