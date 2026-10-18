# -*- coding: utf-8 -*-
"""06 文化科学宫 Pałac Kultury i Nauki — Warsaw landmark set.

The 1955 Stalinist tower: 84 m square podium with three-arch entrances and four
corner pavilions, a 66 m second tier, the 46 m main shaft with its vertical
stone ribs and window strips, a stepped crown with balustrade, clock faces and
corner pinnacles, then three diminishing steps, an octagonal spire and the
antenna — 237 m to the tip.

Reference note: model.d/warsaw "Warsaw 001 XReconstruct" is NOT this building —
it is a ~54x61 m patch of aerial city fabric.  Only its colour range was used
(warm grey roofs / asphalt) for the plaza.
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

OUT_BLEND = r"E:\AI\Tread\Tread\model\warsaw\landmarks\Warsaw_06_PKin.blend"

P = S.PKIN
PX, PY = P["podium"]
PH = P["podium_h"]
T2X, T2Y = P["tier2"]
T2H = P["tier2_h"]
SX, SY = P["shaft"]
STOP = P["shaft_top"]
CX, CY = P["crown"]
CTOP = P["crown_top"]


def face(mb, side, lat, z, half):
    """Push a frame on one of the four faces; local -Y points outward."""
    if side == 0:
        mb.at(lat, -half, z)
    elif side == 1:
        mb.at(half, lat, z, 90.0)
    elif side == 2:
        mb.at(-lat, half, z, 180.0)
    else:
        mb.at(-half, lat, z, -90.0)


def band(mb, half, z0, z1, proud):
    mb.box(-half - proud, -half - proud, z0, half + proud, half + proud, z1)


def cornice(T, half, z, h=0.9, proud=0.55):
    band(T, half, z, z + h * 0.45, proud)
    band(T, half, z + h * 0.45, z + h, proud * 1.55)


def main():
    G.scene_reset()
    col = G.collection("COL_LM_PKIN")
    root = G.empty("LM_PKIN", col)

    B = G.MB("PKIN-body")
    T = G.MB("PKIN-trim")
    W = G.MB("PKIN-win")
    R = G.MB("PKIN-roof")
    D = G.MB("PKIN-detail")
    Gd = G.MB("PKIN-gold")
    Pl = G.MB("PKIN-plaza")

    # ---- plaza (Plac Defilad) -------------------------------------------
    PZ = P["plaza"] / 2.0
    Pl.box(-PZ, -PZ, -1.4, PZ, PZ, 0.0)
    T.box(-PZ, -PZ, -0.1, PZ, -PZ + 1.2, 0.55)
    T.box(-PZ, PZ - 1.2, -0.1, PZ, PZ, 0.55)
    T.box(-PZ, -PZ, -0.1, -PZ + 1.2, PZ, 0.55)
    T.box(PZ - 1.2, -PZ, -0.1, PZ, PZ, 0.55)
    for k in range(-3, 4):
        Pl.box(-PZ, k * 22.0 - 0.35, 0.0, PZ, k * 22.0 + 0.35, 0.02)
        Pl.box(k * 22.0 - 0.35, -PZ, 0.0, k * 22.0 + 0.35, PZ, 0.02)

    # ---- podium ---------------------------------------------------------
    hx = PX / 2.0
    B.box(-hx, -hx, 0.0, hx, hx, PH)
    T.box(-hx - 0.55, -hx - 0.55, 0.0, hx + 0.55, hx + 0.55, 3.6)      # plinth
    for z in (8.2, 15.4):
        band(T, hx, z - 0.22, z + 0.10, 0.30)
    cornice(T, hx, PH - 1.1, 1.1, 0.62)
    T.box(-hx - 0.30, -hx - 0.30, PH - 1.1, hx + 0.30, hx + 0.30, PH + 0.35)
    # parapet / attic around the podium roof deck
    for x0, y0, x1, y1 in ((-hx, -hx, hx, -hx + 0.9), (-hx, hx - 0.9, hx, hx),
                           (-hx, -hx, -hx + 0.9, hx), (hx - 0.9, -hx, hx, hx)):
        T.box(x0, y0, PH + 0.35, x1, y1, PH + 2.8)

    # three-arch entrance + tall arched windows on all four faces
    for side in range(4):
        for lat, aw, ah in ((-21.0, 7.0, 10.5), (0.0, 8.4, 11.5), (21.0, 7.0, 10.5)):
            face(W, side, lat, 1.2, hx)
            W.arch_open(aw, ah, 10); W.pop()
            face(T, side, lat, 1.2, hx)
            T.arch_ring(aw, ah, 10, 0.55, 0.30); T.pop()
        for lat in (-30.0, -13.5, 13.5, 30.0):
            for z, aw, ah in ((9.2, 2.8, 6.0), (15.6, 2.6, 5.2)):
                face(W, side, lat, z, hx)
                W.arch_open(aw, ah, 8); W.pop()
                face(T, side, lat, z, hx)
                T.arch_ring(aw, ah, 8, 0.30, 0.20); T.pop()
        # pilasters between the bays
        for lat in (-34.0, -25.5, -17.5, -8.5, 8.5, 17.5, 25.5, 34.0):
            face(T, side, lat, 3.8, hx)
            T.box(-0.55, -0.42, 0.0, 0.55, 0.0, PH - 4.2); T.pop()

    # ---- four corner pavilions -------------------------------------------
    pvx, pvy = P["pavilion"]
    pvh = P["pavilion_h"]
    for sx in (-1, 1):
        for sy in (-1, 1):
            cx, cy = sx * (hx - pvx / 2 + 1.2), sy * (hx - pvy / 2 + 1.2)
            B.box(cx - pvx / 2, cy - pvy / 2, 0.0, cx + pvx / 2, cy + pvy / 2, pvh)
            for z in (9.0, 16.0, 23.0):
                T.push(Matrix.Translation((cx, cy, 0.0)))
                band(T, pvx / 2, z, z + 0.26, 0.22)
                T.pop()
            T.box(cx - pvx / 2 - 0.55, cy - pvy / 2 - 0.55, pvh - 0.9,
                  cx + pvx / 2 + 0.55, cy + pvy / 2 + 0.55, pvh + 0.25)
            T.box(cx - pvx / 2 - 0.30, cy - pvy / 2 - 0.30, 3.0,
                  cx + pvx / 2 + 0.30, cy + pvy / 2 + 0.30, 3.6)
            # windows on the outward faces
            for side in range(4):
                for lat in (-4.2, 0.0, 4.2):
                    for z in (7.5, 14.0, 20.5):
                        W.push(Matrix.Translation((cx, cy, 0)) @
                               Matrix.Rotation(math.radians(side * 90.0), 4, "Z"))
                        W.at(lat, -(pvy / 2), z)
                        W.window_glass(1.8, 3.4); W.pop(); W.pop()
                        T.push(Matrix.Translation((cx, cy, 0)) @
                               Matrix.Rotation(math.radians(side * 90.0), 4, "Z"))
                        T.at(lat, -(pvy / 2), z)
                        T.window_frame(1.8, 3.4, frame=0.22, sill=True); T.pop(); T.pop()
            # copper pyramid + spirelet
            R.hip(cx - pvx / 2 - 0.7, cy - pvy / 2 - 0.7,
                  cx + pvx / 2 + 0.7, cy + pvy / 2 + 0.7, pvh + 0.25, 9.5, ridge_axis="x")
            Gd.lathe([(0.34, pvh + 9.6), (0.20, pvh + 11.4), (0.0, pvh + 12.1)], cx, cy, seg=8)

    # ---- second tier -----------------------------------------------------
    h2 = T2X / 2.0
    B.box(-h2, -h2, PH, h2, h2, T2H)
    band(T, h2, PH, PH + 0.7, 0.40)
    cornice(T, h2, T2H - 1.2, 1.2, 0.58)
    for side in range(4):
        for k in range(-5, 6):
            lat = k * 5.4
            for z, ww, hh in ((27.0, 2.4, 6.4), (35.5, 2.3, 5.8)):
                face(W, side, lat, z, h2)
                W.window_glass(ww, hh); W.pop()
                face(T, side, lat, z, h2)
                T.window_frame(ww, hh, frame=0.18, sill=True); T.pop()
        for k in range(-6, 6):
            face(T, side, k * 5.4 + 2.7, PH + 0.7, h2)
            T.box(-0.42, -0.34, 0.0, 0.42, 0.0, T2H - PH - 1.8); T.pop()

    # ---- main shaft ------------------------------------------------------
    hs = SX / 2.0
    B.box(-hs, -hs, T2H, hs, hs, STOP)
    band(T, hs, T2H, T2H + 0.6, 0.35)
    cornice(T, hs, STOP - 1.4, 1.4, 0.65)
    nbay = 13
    bw = SX / nbay
    for side in range(4):
        for i in range(nbay + 1):
            face(T, side, -hs + i * bw, T2H + 0.6, hs)
            T.box(-0.55, -0.85, 0.0, 0.55, 0.0, STOP - T2H - 2.4); T.pop()
        for i in range(nbay):
            face(W, side, -hs + (i + 0.5) * bw, 48.0, hs)
            W.box(-1.05, -0.09, 0.0, 1.05, 0.02, 63.0); W.pop()
        for z in (70.0, 88.0, 104.0):
            band(T, hs, z, z + 0.45, 0.28)
    # corner buttresses (proud of both faces)
    for sx in (-1, 1):
        for sy in (-1, 1):
            x0, x1 = sorted((sx * hs - 1.2, sx * hs + 0.9))
            y0, y1 = sorted((sy * hs - 1.2, sy * hs + 0.9))
            T.box(x0, y0, T2H, x1, y1, STOP)

    # ---- crown + terrace -------------------------------------------------
    hc = CX / 2.0
    B.box(-hc, -hc, STOP, hc, hc, CTOP - 2.0)
    cornice(T, hc, CTOP - 2.8, 1.1, 0.62)
    # clock faces
    for side in range(4):
        zc = STOP + 5.5
        M = (Matrix.Translation((0, 0, zc)) @ Matrix.Rotation(math.radians(side * 90.0), 4, "Z") @
             Matrix.Translation((0, -hc - 0.06, 0)) @ Matrix.Rotation(math.pi / 2, 4, "X"))
        T.push(M); T.lathe([(2.6, 0.0), (2.6, 0.10)], 0, 0, seg=24); T.pop()
        D.push(M)
        D.box(-0.14, -1.9, 0.02, 0.14, 1.6, 0.12)      # minute hand (vertical)
        D.box(-0.14, -0.14, 0.02, 1.15, 0.14, 0.12)    # hour hand (horizontal)
        D.pop()
    # terrace balustrade
    T.balustrade(-hc - 0.4, -hc - 0.4, hc + 0.4, -hc - 0.4, CTOP - 2.0, h=1.0)
    T.balustrade(-hc - 0.4, hc + 0.4, hc + 0.4, hc + 0.4, CTOP - 2.0, h=1.0)
    T.balustrade(-hc - 0.4, -hc - 0.4, -hc - 0.4, hc + 0.4, CTOP - 2.0, h=1.0)
    T.balustrade(hc + 0.4, -hc - 0.4, hc + 0.4, hc + 0.4, CTOP - 2.0, h=1.0)
    B.box(-hc + 3.5, -hc + 3.5, CTOP - 2.0, hc - 3.5, hc - 3.5, CTOP)
    # corner pinnacles: square turrets with copper caps
    for sx in (-1, 1):
        for sy in (-1, 1):
            px, py = sx * (hc - 2.4), sy * (hc - 2.4)
            T.box(px - 2.3, py - 2.3, CTOP - 2.0, px + 2.3, py + 2.3, CTOP + 7.2)
            T.box(px - 2.8, py - 2.8, CTOP + 6.5, px + 2.8, py + 2.8, CTOP + 7.4)
            R.lathe([(3.1, CTOP + 7.4), (1.7, CTOP + 10.4), (0.0, CTOP + 13.4)],
                    px, py, seg=4)
            Gd.lathe([(0.22, CTOP + 13.4), (0.0, CTOP + 14.6)], px, py, seg=6)

    # ---- three diminishing steps ----------------------------------------
    z0 = CTOP
    for half, ztop in P["steps"]:
        hh = half / 2.0
        B.box(-hh, -hh, z0, hh, hh, ztop)
        cornice(T, hh, ztop - 1.1, 1.1, 0.50)
        band(T, hh, z0, z0 + 0.5, 0.30)
        for side in range(4):
            for k in (-1, 0, 1):
                if abs(k) * 3.6 > hh - 2.0:
                    continue
                face(W, side, k * 3.6, z0 + 2.0, hh)
                W.window_glass(1.5, 4.0); W.pop()
        z0 = ztop

    # ---- octagonal stepped spire + antenna ------------------------------
    ztop = P["spire_top"]
    prof = [(9.0, z0), (9.0, z0 + 0.9), (8.2, z0 + 0.9),
            (8.2, z0 + 5.0), (7.2, z0 + 5.0),
            (7.2, z0 + 9.0), (6.0, z0 + 9.0),
            (6.0, z0 + 13.0), (4.6, z0 + 13.0),
            (4.6, z0 + 17.0), (2.8, z0 + 17.0),
            (2.8, z0 + 20.0), (1.6, z0 + 20.0),
            (1.6, z0 + 22.5), (1.1, z0 + 23.6), (1.1, ztop)]
    T.lathe(prof, 0, 0, seg=8)
    # corner fins following the first three stages only
    for k in range(8):
        a = math.tau * k / 8.0
        T.push(Matrix.Translation((math.cos(a) * 8.1, math.sin(a) * 8.1, 0)) @
               Matrix.Rotation(a + math.pi / 2, 4, "Z"))
        T.box(-0.30, -0.45, z0 + 0.9, 0.30, 0.0, z0 + 9.0)
        T.pop()
    Gd.lathe([(1.1, ztop), (0.0, ztop + 1.2)], 0, 0, seg=8)
    D.lathe([(0.34, ztop), (0.22, P["tip"] - 6.0), (0.12, P["tip"] - 1.0),
             (0.0, P["tip"])], 0, 0, seg=6)
    for zz in (ztop + 18.0, ztop + 33.0):
        D.lathe([(0.55, zz), (0.55, zz + 0.5), (0.0, zz + 0.5)], 0, 0, seg=6)

    objs = []
    objs.append(B.emit(col, G.material("pkin_stone", "#c4baa2", 0.74, pattern="stone", scale=1.2),
                       "GEO-PKIN-body", parent=root))
    objs.append(T.emit(col, G.material("pkin_trim", "#d8d0bc", 0.70, pattern="stone", scale=1.6),
                       "GEO-PKIN-trim", parent=root))
    objs.append(W.emit(col, G.material("pkin_glass", "#181e22", 0.14, 0.55),
                       "GEO-PKIN-windows", parent=root))
    objs.append(R.emit(col, G.material("pkin_copper", "#4f7d66", 0.55, 0.25, pattern="metal", scale=0.7),
                       "GEO-PKIN-copper", parent=root))
    objs.append(D.emit(col, G.material("pkin_dark", "#2b2c2a", 0.55, 0.65),
                       "GEO-PKIN-detail", parent=root))
    objs.append(Gd.emit(col, G.material("pkin_gold", "#c9a23c", 0.28, 1.0),
                        "GEO-PKIN-gold", parent=root))
    objs.append(Pl.emit(col, G.material("pkin_plaza", "#8a8377", 0.90, pattern="concrete", scale=0.35),
                        "GEO-PKIN-plaza", parent=root))

    G.setup_world(strength=0.45, sky=(0.62, 0.72, 0.84))
    G.sun(rot=(math.radians(48), 0.0, math.radians(38)), energy=4.0)

    mn = [1e9] * 3
    mx = [-1e9] * 3
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ G.Vector(c)
            for i in range(3):
                mn[i] = min(mn[i], w[i])
                mx[i] = max(mx[i], w[i])
    stats = {"landmark": "Palac Kultury i Nauki", "objects": len(objs),
             "verts": sum(len(o.data.vertices) for o in objs),
             "tris": sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objs),
             "dropped_faces": sum(getattr(m, "dropped_faces", 0)
                                  for m in (B, T, W, R, D, Gd, Pl)),
             "bbox": [round(v, 2) for v in mn] + [round(v, 2) for v in mx],
             "size": [round(mx[i] - mn[i], 2) for i in range(3)]}
    os.makedirs(os.path.dirname(OUT_BLEND), exist_ok=True)
    G.save(OUT_BLEND)
    stats["blend"] = OUT_BLEND
    print("HEADLESS " + json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
