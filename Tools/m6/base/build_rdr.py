# -*- coding: utf-8 -*-
"""RDR — 雷达 · 近防塔: lattice tower, AESA face, CIWS mount, box launcher,
equipment shelter and aviation lighting.
"""
import math
import os
import sys

from mathutils import Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import lib_kit as K
import m6spec as S

P = S.MODS["RDR"]
OUT = os.path.join(K.ROOT, "model", "m6", "base", "M6_RDR_Radar.blend")

SHX, SHY, SHH = P["shelter"]
TH = P["tower_h"]
W0, W1 = P["base_w"], P["top_w"]
AW, AH = P["aesa"]
BAYS = 10


def main():
    col, root = K.scene("RDR")

    C = K.MB("RDR-conc")
    St = K.MB("RDR-steel")
    Sd = K.MB("RDR-dark")
    Pn = K.MB("RDR-panel")
    Gl = K.MB("RDR-glass")
    EmR = K.MB("RDR-red")
    EmW = K.MB("RDR-light")
    EmC = K.MB("RDR-systems")
    Or = K.MB("RDR-hazard")
    Gv = K.MB("RDR-galv")

    # ---------------------------------------------------------- shelter
    C.box(-SHX / 2 - 1.0, -SHY / 2 - 1.0, -0.30, SHX / 2 + 1.0, SHY / 2 + 1.0, 0.30)
    Pn.box(-SHX / 2, -SHY / 2, 0.30, SHX / 2, SHY / 2, SHH)
    St.box(-SHX / 2 - 0.3, -SHY / 2 - 0.3, SHH, SHX / 2 + 0.3, SHY / 2 + 0.3, SHH + 0.30)
    for i in range(4):
        Sd.push(Matrix.Translation((-SHX / 2, -SHY / 2 + 1.4 + i * 2.4, 3.2)) @
                Matrix.Rotation(math.radians(-90), 4, "Z"))
        Sd.louver(1.5, 0.85, 5)
        Sd.pop()
    Sd.push(Matrix.Translation((-SHX / 2 + 2.2, -SHY / 2 - 0.01, 0.30)))
    Sd.roller_door(2.6, 2.6, 9)
    Sd.pop()
    Gl.box(SHX / 2 - 2.4, -SHY / 2 - 0.06, 1.6, SHX / 2 - 0.4, -SHY / 2 + 0.02, 3.0)
    St.box(SHX / 2 - 2.5, -SHY / 2 - 0.14, 1.5, SHX / 2 - 0.3, -SHY / 2 + 0.05, 3.1)
    for i in range(3):
        Sd.push(Matrix.Translation((SHX / 2 + 1.2 + i * 1.0, -1.6, 0.30)))
        Sd.box(-0.45, -0.45, 0.0, 0.45, 0.45, 1.9)
        Sd.pop()
    # cable ladder from the shelter to the tower base
    Sd.cable_tray([(SHX / 2 - 0.4, 0.0, SHH), (2.2, 0.0, SHH), (2.2, 0.0, 1.2),
                   (1.4, 0.0, 1.2)], 0.34, 0.14)

    # ---------------------------------------------------------- lattice tower
    corners = ((-1, -1), (1, -1), (1, 1), (-1, 1))
    for i in range(BAYS):
        t0, t1 = i / float(BAYS), (i + 1) / float(BAYS)
        a0 = W0 + (W1 - W0) * t0
        a1 = W0 + (W1 - W0) * t1
        z0, z1 = SHH + TH * t0, SHH + TH * t1
        for (sx, sy) in corners:
            St.tube([(sx * a0 / 2, sy * a0 / 2, z0), (sx * a1 / 2, sy * a1 / 2, z1)],
                    0.11, seg=6)
        for k in range(4):
            (sx0, sy0) = corners[k]
            (sx1, sy1) = corners[(k + 1) % 4]
            p0 = (sx0 * a0 / 2, sy0 * a0 / 2, z0)
            p1 = (sx1 * a0 / 2, sy1 * a0 / 2, z0)
            q0 = (sx1 * a1 / 2, sy1 * a1 / 2, z1)
            q1 = (sx0 * a1 / 2, sy0 * a1 / 2, z1)
            St.tube([p0, q0], 0.055, seg=4)
            St.tube([p1, q1], 0.055, seg=4)
            St.tube([p0, p1], 0.05, seg=4)
        if i % 2 == 1:
            St.box(-a1 / 2 - 0.4, -a1 / 2 - 0.4, z1 - 0.12, a1 / 2 + 0.4, a1 / 2 + 0.4, z1)
    # foundation block
    C.box(-W0 / 2 - 1.2, -W0 / 2 - 1.2, 0.0, W0 / 2 + 1.2, W0 / 2 + 1.2, 0.55)

    # ---------------------------------------------------------- platforms
    def platform(z, half, rail=True):
        St.box(-half, -half, z - 0.14, half, half, z)
        Sd.lathe([(0.10, z), (0.10, z + 0.8)], -half + 0.2, -half + 0.2, seg=6)
        if rail:
            for (dx, dy, ang) in ((-half, -half, 0.0), (-half, half, 0.0),
                                  (half, -half, 90.0), (half, half, 90.0)):
                St.push(Matrix.Translation((dx, dy, z)) @ Matrix.Rotation(math.radians(ang), 4, "Z"))
                St.railing(half * 2 if ang == 0.0 else half * 2, h=1.05)
                St.pop()

    platform(P["launcher_at"], 3.6)
    platform(P["ciws_at"], 3.0)
    platform(32.0, 2.2)

    # ---------------------------------------------------------- box launcher
    lz = P["launcher_at"]
    St.box(-3.2, -3.2, lz, 3.2, 3.2, lz + 0.5)
    Sd.push(Matrix.Translation((0.0, 1.2, lz + 0.5)) @ Matrix.Rotation(math.radians(-52), 4, "X"))
    for r in range(2):
        for c in range(3):
            Sd.box(-2.1 + c * 1.4, -0.55 + r * 1.1, 0.0, -0.75 + c * 1.4, 0.55 + r * 1.1, 4.6)
    Sd.pop()
    St.box(-2.5, -0.9, lz + 0.5, 2.5, 1.6, lz + 0.9)
    Or.box(-2.5, 1.5, lz + 0.9, 2.5, 1.62, lz + 1.1)

    # ---------------------------------------------------------- CIWS mount
    cz = P["ciws_at"]
    St.lathe([(1.2, cz), (1.0, cz + 0.5)], 0, 0, seg=16)
    Sd.box(-1.0, -1.0, cz + 0.5, 1.0, 1.0, cz + 1.7)
    Sd.dome(0.0, 0.0, cz + 1.7, 1.0, 0.55, seg=16, rings=4)
    for sx in (-1, 1):
        Sd.tube([(sx * 0.28, 0.6, cz + 1.1), (sx * 0.28, 3.6, cz + 1.15)], 0.09, seg=8)
        Sd.tube([(sx * 0.28, 1.4, cz + 1.05), (sx * 0.28, 3.5, cz + 1.1)], 0.06, seg=6)
    St.box(-1.3, -1.6, cz + 1.2, 1.3, -0.6, cz + 1.9)
    St.box(-0.9, -1.9, cz + 1.35, 0.9, -1.2, cz + 1.75)

    # ---------------------------------------------------------- AESA + turntable
    ty = SHH + TH
    St.box(-1.5, -1.5, ty - 0.1, 1.5, 1.5, ty + 0.55)
    St.lathe([(1.1, ty + 0.55), (1.1, ty + 0.95)], 0, 0, seg=20)
    Sd.push(Matrix.Translation((0.0, -0.4, ty + 0.95)) @ Matrix.Rotation(math.radians(14), 4, "X"))
    Sd.aesa_panel(AW, AH, 10, 8)
    Sd.pop()
    St.box(-AW / 2 - 0.5, 0.6, ty + 0.6, AW / 2 + 0.5, 1.4, ty + 1.1)
    # back frame + waveguides
    for sx in (-1, 1):
        Sd.tube([(sx * AW / 2, 1.0, ty + 1.2), (sx * AW / 2, 1.9, ty + 2.6),
                 (sx * 0.4, 1.9, ty + 2.6)], 0.06, seg=6)
    Sd.whip(5.0, 0.06, z0=ty + 0.9)
    EmR.beacon(0.11, ty + 6.1)

    # ---------------------------------------------------------- dish + ladder
    dz = 20.0
    St.box(-2.0, 1.4, dz, 2.0, 2.4, dz + 0.25)
    St.push(Matrix.Translation((0.0, 2.0, dz + 0.4)) @ Matrix.Rotation(math.radians(-62), 4, "X"))
    St.dish(P["dish_r"], 0.45, seg=22, rings=5)
    St.pop()
    St.tube([(0.0, 2.0, dz + 0.4), (0.0, 1.0, dz + 1.5)], 0.06, seg=6)
    # climbing ladder up the north face
    St.push(Matrix.Translation((0.0, -W0 / 2 + 0.3, SHH)))
    St.ladder(TH - 1.0)
    St.pop()

    # ---------------------------------------------------------- aviation lights
    for z in (SHH + 2.0, SHH + 12.0, SHH + 22.0, SHH + 32.0, ty + 0.4):
        t = max(0.0, min(1.0, (z - SHH) / TH))
        a = W0 + (W1 - W0) * t
        for sx in (-1, 1):
            for sy in (-1, 1):
                EmR.cyl(sx * a / 2, sy * a / 2, z - 0.10, z + 0.10, 0.10, seg=8)
    for sx in (-1, 1):
        EmC.box(sx * 2.2 - 0.5, -0.7, ty - 0.6, sx * 2.2 + 0.5, -0.4, ty - 0.2)
    for i in range(3):
        EmW.box(SHX / 2 - 1.2 + i * 1.2, -SHY / 2 - 0.10, 0.36, SHX / 2 - 0.4 + i * 1.2,
                -SHY / 2 - 0.04, 0.44)

    # ---------------------------------------------------------- ground kit
    for i in range(3):
        Sd.push(Matrix.Translation((-SHX / 2 - 2.4 - i * 1.4, -3.0, 0.0)))
        Sd.crate(1.2, 0.9, 0.85)
        Sd.pop()
    Sd.push(Matrix.Translation((SHX / 2 + 2.0, -4.0, 0.0)))
    Sd.barrel(0.30, 0.88)
    Sd.pop()
    Gv.paint_line((-2.0, -SHY / 2 - 2.4), (2.0, -SHY / 2 - 2.4), 0.20, z=0.012)
    Or.box(-2.4, -SHY / 2 - 2.6, 0.0, 2.4, -SHY / 2 - 2.5, 0.30)

    objs = [
        K.emit(C, col, "conc", "GEO-RDR-concrete", root),
        K.emit(St, col, "steel", "GEO-RDR-steel", root),
        K.emit(Sd, col, "steel_dark", "GEO-RDR-dark", root),
        K.emit(Pn, col, "panel", "GEO-RDR-cladding", root),
        K.emit(Gl, col, "glass_green", "GEO-RDR-glass", root),
        K.emit(Gv, col, "galv", "GEO-RDR-markings", root),
        K.emit(EmR, col, "em_red", "GEO-RDR-beacon", root),
        K.emit(EmW, col, "em_white", "GEO-RDR-light", root),
        K.emit(EmC, col, "em_cyan", "GEO-RDR-systems", root),
        K.emit(Or, col, "orange", "GEO-RDR-hazard", root),
    ]
    K.sky()
    K.finish(objs, OUT, "RDR", extra={"tower_h": TH, "aesa": [AW, AH]})


if __name__ == "__main__":
    main()
