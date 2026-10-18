# -*- coding: utf-8 -*-
"""01 老城集市 Rynek Starego Miasta — Warsaw landmark set.

A closed market square ringed by burgher houses (kamienice): 3 storeys,
steep tiled gable roofs, decorative stepped / volute / triangular front gables,
pilasters, quoins, stone window surrounds, arcaded ground floors, dormers,
chimneys.  Centre: the Warsaw Mermaid fountain on a cobbled plaza.
"""
import bpy
import math
import os
import random
import sys
import json
from mathutils import Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import lib_geom as G
import spec as S

OUT_BLEND = r"E:\AI\Tread\Tread\model\warsaw\landmarks\Warsaw_01_Rynek.blend"

SP = S.RYNEK
SQX, SQY = SP["square"]
HD = SP["house_depth"]
EAV = SP["eaves"]
RNG = random.Random(20261018)

BODY_COLORS = [
    ("plaster_ochre", "#c9a05c"),
    ("plaster_cream", "#dbcdae"),
    ("plaster_pink",  "#bd8467"),
    ("plaster_olive", "#a39b5f"),
    ("plaster_blue",  "#87949f"),
    ("plaster_white", "#e6dfcd"),
    ("plaster_gold",  "#cfa855"),
]
ROOF_TONES = [
    ("tile_red",   "#9c4630"),
    ("tile_brown", "#7a4a35"),
    ("tile_dark",  "#6a4433"),
]


def gable_profile(style, w, gh):
    half = w / 2.0
    if style == "tri":
        return [(-half, 0.0), (-half * 0.44, gh * 0.72), (0.0, gh),
                (half * 0.44, gh * 0.72), (half, 0.0)]
    if style == "volute":
        return [(-half, 0.0), (-half, gh * 0.34), (-half * 0.80, gh * 0.52),
                (-half * 0.66, gh * 0.74), (-half * 0.40, gh * 0.88),
                (-half * 0.20, gh), (half * 0.20, gh), (half * 0.40, gh * 0.88),
                (half * 0.66, gh * 0.74), (half * 0.80, gh * 0.52),
                (half, gh * 0.34), (half, 0.0)]
    steps = 4
    hs = gh / steps
    pts = []
    for i in range(steps):
        xw = half * (1.0 - 0.70 * i / steps)
        pts.append((-xw, i * hs))
        pts.append((-xw, (i + 1) * hs))
    for i in reversed(range(steps)):
        xw = half * (1.0 - 0.70 * i / steps)
        pts.append((xw, (i + 1) * hs))
        pts.append((xw, i * hs))
    return pts


def build_house(bodies, T, W, roofs, D, ox, oy, rz, w, style, roof_h, seed):
    """One burgher house. Local frame: facade at y=0 facing -Y, body to +Y."""
    rng = random.Random(seed)
    depth = HD * rng.uniform(0.92, 1.06)
    eaves = EAV * rng.uniform(0.92, 1.09)
    body = bodies[rng.randrange(len(bodies))]
    roof = roofs[rng.choice([0, 0, 0, 1, 1, 2])]

    allmb = (body, T, W, roof, D)
    for mb in allmb:
        mb.at(ox, oy, 0.0, rz)

    z1 = SP["storey"][0]
    z2 = z1 + SP["storey"][1]

    # ---- body -----------------------------------------------------------
    body.box(-w / 2, 0.0, 0.0, w / 2, depth, eaves)
    # plinth, string courses, main cornice
    T.box(-w / 2 - 0.12, -0.19, 0.0, w / 2 + 0.12, 0.0, 0.66)
    for z in (z1, z2):
        T.box(-w / 2 - 0.09, -0.16, z - 0.11, w / 2 + 0.09, 0.0, z + 0.05)
    T.box(-w / 2 - 0.26, -0.36, eaves - 0.62, w / 2 + 0.26, 0.02, eaves + 0.02)
    T.box(-w / 2 - 0.16, -0.24, eaves - 0.90, w / 2 + 0.16, 0.0, eaves - 0.62)

    # ---- facade articulation: quoins + pilasters ------------------------
    qz = 0.66
    step = 0.46
    while qz + step < eaves - 1.0:
        ww = 0.52 if (int(qz * 10) // 4) % 2 == 0 else 0.34
        for s in (-1, 1):
            T.box(s * w / 2 - (0.0 if s < 0 else ww), -0.10, qz,
                  s * w / 2 + (ww if s < 0 else 0.0), 0.0, qz + step * 0.62)
        qz += step
    nbay = 3 if w >= 10.5 else 2
    for k in range(nbay + 1):
        x = -w / 2 + k * (w / nbay)
        if k in (0, nbay):
            continue
        T.box(x - 0.19, -0.075, z1 + 0.02, x + 0.19, 0.0, eaves - 0.95)
        T.box(x - 0.25, -0.12, eaves - 1.02, x + 0.25, 0.0, eaves - 0.90)

    # ---- ground floor: arcaded shop front + doorway ---------------------
    if w >= 10.5:
        for cx, aw, ah, seg in ((-w * 0.24, 2.0, 2.55, 8), (w * 0.22, 1.5, 2.9, 7)):
            W.at(cx, 0, 0); W.arch_open(aw, ah, seg); W.pop()
            T.at(cx, 0, 0); T.arch_ring(aw, ah, seg); T.pop()
    else:
        for cx, aw, ah, seg in ((-w * 0.20, 1.6, 2.6, 7), (w * 0.24, 1.3, 2.7, 6)):
            W.at(cx, 0, 0); W.arch_open(aw, ah, seg); W.pop()
            T.at(cx, 0, 0); T.arch_ring(aw, ah, seg); T.pop()

    # ---- windows --------------------------------------------------------
    ws = 1.02
    for k in range(nbay):
        x = -w / 2 + (k + 0.5) * (w / nbay)
        for z, hh in ((z1 + 0.60, 2.0), (z2 + 0.64, 1.82)):
            W.at(x, 0, z); W.window_glass(ws, hh); W.pop()
            T.at(x, 0, z); T.window_frame(ws, hh); T.pop()
            if hh > 1.9:
                T.box(x - ws / 2 - 0.22, -0.38, z + hh + 0.10,
                      x + ws / 2 + 0.22, 0.0, z + hh + 0.28)
                T.box(x - ws / 2 - 0.16, -0.36, z + hh + 0.28,
                      x + ws / 2 + 0.16, 0.0, z + hh + 0.40)
    # rear (street side), plain
    for k in range(2):
        x = -w / 2 + (k + 0.5) * (w / 2)
        for z, hh in ((z1 + 0.60, 1.85), (z2 + 0.64, 1.70)):
            W.at(x, depth, z); W.push(Matrix.Rotation(math.pi, 4, "Z"))
            W.window_glass(0.95, hh); W.pop(); W.pop()
            T.at(x, depth, z); T.push(Matrix.Rotation(math.pi, 4, "Z"))
            T.window_frame(0.95, hh); T.pop(); T.pop()

    # ---- roof + gable walls ---------------------------------------------
    roof.gable_y(-w / 2 - 0.34, w / 2 + 0.34, 0.10, depth - 0.10, eaves, roof_h)
    # ridge cap
    roof.box(-0.16, 0.10, eaves + roof_h - 0.10, 0.16, depth - 0.10, eaves + roof_h + 0.10)
    # front decorative gable (plaster)
    gh = roof_h * rng.uniform(0.84, 0.96)
    prof = [(x, eaves + z) for x, z in gable_profile(style, w - 0.55, gh)]
    body.prism_y(prof, -0.30, 0.05)
    T.coping_xz(prof, -0.40, -0.26, 0.20)
    D.boxc(0.0, -0.20, eaves + gh + 0.40, 0.16, 0.16, 0.9)
    D.boxc(0.0, -0.20, eaves + gh + 0.02, 0.36, 0.36, 0.24)
    # rear triangular gable wall (street side)
    body.prism_y([(-w / 2, eaves), (w / 2, eaves), (0.0, eaves + roof_h)], depth - 0.06, depth + 0.10)

    # ---- dormers --------------------------------------------------------
    for k in (-1, 1):
        dx = k * w * 0.24
        W.at(dx, 0.80, eaves + 0.55); W.window_glass(0.85, 1.05, y0=-0.06, y1=0.06); W.pop()
        T.at(dx, 0.80, eaves + 0.55); T.window_frame(0.85, 1.05, frame=0.07, sill=False); T.pop()
        roof.at(dx, 1.42, eaves)
        roof.box(-0.66, -0.58, 0.0, 0.66, 0.58, 1.78)
        roof.hip(-0.82, -0.72, 0.82, 0.72, 1.78, 0.82, ridge_axis="x")
        roof.pop()

    # ---- chimney --------------------------------------------------------
    cx = rng.uniform(-w * 0.3, w * 0.3)
    body.box(cx - 0.42, depth * 0.42, eaves + roof_h * 0.15,
             cx + 0.42, depth * 0.42 + 0.84, eaves + roof_h + 1.20)
    T.box(cx - 0.52, depth * 0.42 - 0.08, eaves + roof_h + 1.05,
          cx + 0.52, depth * 0.42 + 0.92, eaves + roof_h + 1.30)

    for mb in allmb:
        mb.pop()


def build_ring(bodies, T, W, roofs, D):
    half_x, half_y = SQX / 2.0, SQY / 2.0
    gap = SP["gap_corners"]
    seed = 1000
    rows = [
        ("x", -half_x + gap, half_x - gap, -half_y, 180.0),
        ("x", -half_x + gap, half_x - gap, half_y, 0.0),
        ("y", -half_y + gap, half_y - gap, half_x, -90.0),
        ("y", -half_y + gap, half_y - gap, -half_x, 90.0),
    ]
    count = 0
    lo, hi = SP["house_w"]
    for axis, a0, a1, fixed, rz in rows:
        L = a1 - a0
        ws, rem = [], L
        while rem > hi * 1.15:
            w = RNG.uniform(lo, hi)
            ws.append(w)
            rem -= w
        ws.append(rem)
        if ws[-1] < lo * 0.8 and len(ws) > 1:
            ws[-2] += ws[-1]
            ws.pop()
        pos = a0
        for w in ws:
            seed += 7
            style = SP["gable_styles"][seed % len(SP["gable_styles"])]
            roof_h = RNG.uniform(*SP["roof_h"])
            c = pos + w / 2.0
            if axis == "x":
                build_house(bodies, T, W, roofs, D, c, fixed, rz,
                            w * 0.985, style, roof_h, seed)
            else:
                build_house(bodies, T, W, roofs, D, fixed, c, rz,
                            w * 0.985, style, roof_h, seed)
            count += 1
            pos += w
    return count


def build_plaza(P, T, D):
    ex = SQX / 2.0 + HD + 1.4
    ey = SQY / 2.0 + HD + 1.4
    P.box(-ex, -ey, -1.0, ex, ey, -0.02)
    # inner paving field, slightly proud
    P.box(-SQX / 2 - 0.6, -SQY / 2 - 0.6, -0.02, SQX / 2 + 0.6, SQY / 2 + 0.6, 0.0)
    # concentric stone rings
    for r0, r1 in ((13.4, 14.2), (21.0, 21.7)):
        T.lathe([(r1, 0.0), (r1, 0.035), (r0, 0.035), (r0, 0.0)], seg=64)

    # ---- mermaid fountain ------------------------------------------------
    F = D
    T.lathe([(5.0, 0.0), (5.0, 0.62), (4.72, 0.74), (4.42, 0.74), (4.42, 0.0)], seg=12)
    T.lathe([(5.06, 0.74), (5.06, 0.85), (4.36, 0.85), (4.36, 0.74)], seg=12)
    T.lathe([(1.15, 0.0), (1.15, 1.15), (0.90, 1.28), (0.66, 1.10)], seg=8)
    T.lathe([(0.66, 1.10), (0.50, 2.45), (0.34, 2.62)], seg=8)
    F.lathe([(0.34, 2.60), (0.42, 3.10), (0.34, 3.42)], 0, 0, seg=12)
    F.boxc(0.0, 0.0, 3.62, 0.66, 0.44, 1.15)
    F.lathe([(0.24, 4.05), (0.20, 4.40), (0.0, 4.58)], 0, 0, seg=12)
    F.boxc(0.0, -0.04, 4.32, 0.36, 0.32, 0.38)
    F.tube([(0, 0.22, 3.20), (0.0, 0.92, 2.70), (0.0, 1.40, 3.06), (0.0, 1.30, 3.68)], 0.16, seg=6)
    F.push(Matrix.Translation((0.34, -0.06, 3.72)) @ Matrix.Rotation(math.radians(-16), 4, "Y"))
    F.box(-0.05, -0.05, 0.0, 0.05, 0.05, 1.30)
    F.box(-0.24, -0.06, -0.13, 0.24, 0.06, 0.02)
    F.pop()

    # ---- lamps -----------------------------------------------------------
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * (SQX / 2 - 6.0), sy * (SQY / 2 - 6.0)
            D.cyl(x, y, 0.0, 0.38, 0.34, seg=8)
            D.cyl(x, y, 0.38, 4.60, 0.11, seg=8)
            D.lathe([(0.16, 4.55), (0.34, 4.85), (0.22, 5.15), (0.0, 5.35)], x, y, seg=8)


def main():
    G.scene_reset()
    col = G.collection("COL_LM_RYNEK")
    root = G.empty("LM_RYNEK", col)

    bodies = [G.MB("RYNEK-body-%d" % i) for i in range(len(BODY_COLORS))]
    T = G.MB("RYNEK-trim")
    W = G.MB("RYNEK-win")
    roofs = [G.MB("RYNEK-roof-%d" % i) for i in range(len(ROOF_TONES))]
    D = G.MB("RYNEK-detail")
    P = G.MB("RYNEK-plaza")
    T2 = G.MB("RYNEK-stone")
    F = G.MB("RYNEK-fountain")

    n = build_ring(bodies, T, W, roofs, D)
    build_plaza(P, T2, F)

    objs = []
    for mb, (nm, hx) in zip(bodies, BODY_COLORS):
        if mb.v:
            objs.append(mb.emit(col, G.material(nm, hx, 0.78, pattern="plaster", scale=0.4),
                                "GEO-RYNEK-" + nm, parent=root))
    objs.append(T.emit(col, G.material("rynek_stone", "#c8c0ac", 0.74, pattern="stone", scale=1.6),
                       "GEO-RYNEK-trim", parent=root))
    objs.append(W.emit(col, G.material("rynek_glass", "#161c21", 0.12, 0.6),
                       "GEO-RYNEK-windows", parent=root))
    for mb, (nm, hx) in zip(roofs, ROOF_TONES):
        if mb.v:
            objs.append(mb.emit(col, G.material(nm, hx, 0.82, pattern="tile", scale=0.30,
                                                hex2="#5c3324"),
                                "GEO-RYNEK-" + nm, parent=root))
    objs.append(D.emit(col, G.material("wrought_iron", "#2b2825", 0.55, 0.8),
                       "GEO-RYNEK-iron", parent=root))
    objs.append(P.emit(col, G.material("cobble", "#7d766b", 0.90, pattern="stone", scale=2.2),
                       "GEO-RYNEK-plaza", parent=root))
    objs.append(T2.emit(col, G.material("stone_grey", "#a9a294", 0.80, pattern="stone", scale=1.4),
                        "GEO-RYNEK-stone", parent=root))
    objs.append(F.emit(col, G.material("bronze", "#6a5330", 0.40, 0.85),
                       "GEO-RYNEK-fountain", parent=root))

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
    stats = {
        "landmark": "Rynek Starego Miasta",
        "houses": n,
        "objects": len(objs),
        "verts": sum(len(o.data.vertices) for o in objs),
        "tris": sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objs),
        "bbox": [round(v, 2) for v in mn] + [round(v, 2) for v in mx],
        "size": [round(mx[i] - mn[i], 2) for i in range(3)],
    }
    os.makedirs(os.path.dirname(OUT_BLEND), exist_ok=True)
    G.save(OUT_BLEND)
    stats["blend"] = OUT_BLEND
    print("HEADLESS " + json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
