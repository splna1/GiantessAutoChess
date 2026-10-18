# -*- coding: utf-8 -*-
"""L-shaped corner block for the Warsaw board.

Follows the prototype's free-form city: streets bend, so a corner block cannot
assume 90 degrees.  The footprint is a real polygon (L with a chamfered corner),
extruded and then dressed with facades along each street edge.

Demo scene: one four-way intersection closed by four L blocks, plus two blocks
following a street that bends 20 degrees.
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

OUT_BLEND = r"E:\AI\Tread\Tread\model\warsaw\landmarks\Warsaw_LBlocks.blend"


def facade(B, T, W, p0, p1, h, storeys, sh, shop=True, bay=3.3, ground=4.4):
    """Dress one street edge: p0->p1, outward normal on the right (-Y)."""
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    L = math.hypot(dx, dy)
    if L < 3.0:
        return
    ang = math.atan2(dy, dx)
    M = Matrix.Translation((p0[0], p0[1], 0)) @ Matrix.Rotation(ang, 4, "Z")
    for mb in (B, T, W):
        mb.push(M)
    # string courses + cornice
    for i in range(1, storeys):
        z = ground + i * sh
        T.box(-0.1, -0.16, z - 0.09, L + 0.1, 0.02, z + 0.05)
    T.box(-0.1, -0.30, h - 0.75, L + 0.1, 0.02, h + 0.05)
    T.box(-0.1, -0.18, h - 1.05, L + 0.1, 0.02, h - 0.75)
    # ground floor: shopfronts
    if shop:
        n = max(1, int(L / 8.0))
        for k in range(n):
            x = (k + 0.5) * L / n
            W.box(x - 2.6, -0.07, 0.8, x + 2.6, 0.02, 3.5)
            T.box(x - 2.9, -0.22, 0.7, x - 2.6, 0.0, 3.7)
            T.box(x + 2.6, -0.22, 0.7, x + 2.9, 0.0, 3.7)
            T.box(x - 2.9, -0.30, 3.5, x + 2.9, 0.0, 3.75)
    # upper floors
    nb = max(1, int(L / bay))
    for f in range(storeys - 1):
        z = ground + f * sh + 0.55
        for k in range(nb):
            x = (k + 0.5) * L / nb
            W.box(x - 0.58, -0.06, z, x + 0.58, 0.03, z + 1.85)
            T.box(x - 0.72, -0.18, z - 0.12, x + 0.72, 0.0, z + 1.97)
            T.box(x - 0.66, -0.26, z + 1.97, x + 0.66, 0.0, z + 2.12)
    for mb in (B, T, W):
        mb.pop()


def l_block(B, T, W, R, D, origin, ang_deg, arm_x, arm_y, depth,
            storeys=5, chamfer=5.0, flat_roof=True):
    sh = 3.2
    ground = 4.4
    h = ground + (storeys - 1) * sh
    poly = [(chamfer, 0.0), (arm_x, 0.0), (arm_x, depth), (depth, depth),
            (depth, arm_y), (0.0, arm_y), (0.0, chamfer)]
    M = Matrix.Translation((origin[0], origin[1], 0.0)) @ \
        Matrix.Rotation(math.radians(ang_deg), 4, "Z")
    for mb in (B, T, W, R, D):
        mb.push(M)
    B.prism_z(poly, 0.0, h)
    # plinth
    T.box(chamfer - 0.1, -0.18, 0.0, arm_x + 0.1, 0.0, 0.8)
    T.box(-0.18, chamfer - 0.1, 0.0, 0.0, arm_y + 0.1, 0.8)
    # facades on the three street edges
    facade(B, T, W, (chamfer, 0.0), (arm_x, 0.0), h, storeys, sh)
    facade(B, T, W, (0.0, chamfer), (0.0, arm_y), h, storeys, sh)
    facade(B, T, W, (0.0, chamfer), (chamfer, 0.0), h, storeys, sh, shop=True, bay=3.0)
    # roof
    if flat_roof:
        R.prism_z(poly, h, h + 0.30)
        # parapet
        for a, b in (((chamfer, 0.0), (arm_x, 0.0)), ((arm_x, 0.0), (arm_x, depth)),
                     ((arm_x, depth), (depth, depth)), ((depth, depth), (depth, arm_y)),
                     ((depth, arm_y), (0.0, arm_y)), ((0.0, arm_y), (0.0, chamfer)),
                     ((0.0, chamfer), (chamfer, 0.0))):
            T.wall_between(a, b, h + 0.30, h + 1.15, 0.5)
        # roof plant
        D.box(depth + 3, depth + 3, h + 0.30, depth + 7, depth + 6, h + 2.4)
        D.lathe([(1.0, h + 0.30), (1.0, h + 2.2), (0.0, h + 2.4)], arm_x * 0.55, depth * 0.5, seg=8)
    else:
        R.prism_z(poly, h, h + 0.3)
    for mb in (B, T, W, R, D):
        mb.pop()


def street(mb, pts, width, z=0.02):
    for i in range(len(pts) - 1):
        p0, p1 = pts[i], pts[i + 1]
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        L = math.hypot(dx, dy)
        ang = math.degrees(math.atan2(dy, dx))
        mb.push(Matrix.Translation((p0[0], p0[1], 0)) @ Matrix.Rotation(math.radians(ang), 4, "Z"))
        mb.box(-width / 2, -width / 2, z, L + width / 2, width / 2, z + 0.02)
        mb.pop()
    for p in pts:                       # joint patches
        mb.lathe([(width * 0.52, z), (width * 0.52, z + 0.02)], p[0], p[1], seg=12)


def main():
    G.scene_reset()
    col = G.collection("COL_LBLOCK")
    root = G.empty("LM_LBLOCK", col)

    bodies = [G.MB("LB-body-%d" % i) for i in range(4)]
    T = G.MB("LB-trim")
    W = G.MB("LB-win")
    R = G.MB("LB-roof")
    D = G.MB("LB-iron")
    St = G.MB("LB-street")

    # ---- four-way intersection at the origin, street half-width 9 m -----
    s = 9.0
    quad = [((s, s), 0.0), ((-s, s), 90.0), ((-s, -s), 180.0), ((s, -s), 270.0)]
    for i, ((cx, cy), a) in enumerate(quad):
        l_block(bodies[i % 4], T, W, R, D, (cx, cy), a,
                58.0, 46.0, 16.0, storeys=5, chamfer=5.5)

    # ---- a street that bends 20 degrees, two more L blocks --------------
    pts = [(9.0, -60.0), (9.0, 9.0), (60.0, 52.0), (150.0, 86.0)]
    street(St, pts, 18.0)
    l_block(bodies[0], T, W, R, D, (72.0, 12.0), -20.0, 64.0, 62.0, 16.0, storeys=4, chamfer=5.0)
    l_block(bodies[1], T, W, R, D, (112.0, 74.0), -45.0, 58.0, 52.0, 16.0, storeys=5, chamfer=5.5)
    # the straight street of the intersection
    street(St, [(-200.0, 0.0), (200.0, 0.0)], 18.0)
    street(St, [(0.0, -200.0), (0.0, 200.0)], 18.0)

    # ---- ground -------------------------------------------------------
    Gr = G.MB("LB-ground")
    Gr.box(-260, -260, -0.6, 300, 220, -0.05)
    gob = Gr.emit(col, G.material("lb_ground", "#5c5a52", 0.94), "GEO-LB-ground", parent=root)

    objs = []
    for i, mb in enumerate(bodies):
        if mb.v:
            objs.append(mb.emit(col, G.material("lb_body_%d" % i, ["#a8875f", "#b9b1a2", "#8f6b52", "#c2b9a4"][i],
                                                0.80, pattern="plaster", scale=0.45),
                                "GEO-LB-body-%d" % i, parent=root))
    objs.append(T.emit(col, G.material("lb_stone", "#d2c9b4", 0.76, pattern="stone", scale=1.4),
                       "GEO-LB-stone", parent=root))
    objs.append(W.emit(col, G.material("lb_glass", "#161b1f", 0.14, 0.55), "GEO-LB-glass", parent=root))
    objs.append(R.emit(col, G.material("lb_roof", "#4d4942", 0.88, pattern="concrete", scale=0.5),
                       "GEO-LB-roof", parent=root))
    objs.append(D.emit(col, G.material("lb_metal", "#43423e", 0.55, 0.65), "GEO-LB-metal", parent=root))
    objs.append(St.emit(col, G.material("lb_asphalt", "#373735", 0.96), "GEO-LB-street", parent=root))

    G.setup_world(strength=0.42, sky=(0.60, 0.70, 0.84))
    G.sun(rot=(math.radians(46), 0.0, math.radians(40)), energy=4.2)

    mn = [1e9] * 3
    mx = [-1e9] * 3
    for o in objs + [gob]:
        for c in o.bound_box:
            w = o.matrix_world @ G.Vector(c)
            for i in range(3):
                mn[i] = min(mn[i], w[i])
                mx[i] = max(mx[i], w[i])
    stats = {"objects": len(objs) + 1,
             "verts": sum(len(o.data.vertices) for o in objs + [gob]),
             "tris": sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objs + [gob]),
             "bbox": [round(v, 1) for v in mn] + [round(v, 1) for v in mx]}
    os.makedirs(os.path.dirname(OUT_BLEND), exist_ok=True)
    G.save(OUT_BLEND)
    stats["blend"] = OUT_BLEND
    print("HEADLESS " + json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
