# -*- coding: utf-8 -*-
"""SIT — 巨人座 / giant's seat building.

Two volumes only, as asked: a LOW block (64 x 46 x 26 m) that is the seat pan,
and a TALL block (64 x 18 x 78 m) behind it that is the backrest.  Built for a
100 m helper: 26 m seat height is ~26 % of her height, the same ratio a 1.7 m
person has with a 0.45 m chair.  Near-future military detailing throughout.
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

P = S.MODS["SIT"]
OUT = os.path.join(K.ROOT, "model", "m6", "base", "M6_SIT_Seat.blend")

SW, SD, SH = P["seat"]              # 64 x 46 x 26
PANW, PAND, PANDEP = P["pan"]       # 56 x 39 x 2.4
BW, BD, BH = P["back"]              # 64 x 18 x 78
SPW, SPD = P["spine"]
GW, GH, GZ = P["gallery"]
MAST = P["mast"]
STW, STD, STH = P["stair"]
ELW, ELD, ELH = P["elev"]

X0, X1 = -SW / 2, SW / 2            # -32 .. 32
SY0, SY1 = -SD / 2, SD / 2          # -32 .. 14   (seat)
BY0, BY1 = SY1, SY1 + BD            # 14 .. 32    (backrest)
PLH = 0.9
BODY = SH - PANDEP                  # 23.6  top of the solid seat body
PANZ = BODY - 0.4                   # 23.2  pan floor
PLX, PLY0, PLY1 = 76.0, -38.0, 43.0


def main():
    col, root = K.scene("SIT")

    C = K.MB("SIT-conc")
    Cr = K.MB("SIT-raw")
    Pn = K.MB("SIT-panel")
    Pg = K.MB("SIT-grey")
    St = K.MB("SIT-steel")
    Sd = K.MB("SIT-dark")
    Gl = K.MB("SIT-glass")
    Em = K.MB("SIT-light")
    EmC = K.MB("SIT-systems")
    Am = K.MB("SIT-beacon")
    Or = K.MB("SIT-hazard")
    Ru = K.MB("SIT-cushion")
    Wh = K.MB("SIT-markings")

    # ---------------------------------------------------------- plinth
    C.box(-PLX / 2, PLY0, 0.0, PLX / 2, PLY1, PLH)
    C.box(-PLX / 2 - 0.2, PLY0 - 0.2, 0.0, PLX / 2 + 0.2, PLY1 + 0.2, 0.28)
    for i in range(1, 9):
        y = PLY0 + i * (PLY1 - PLY0) / 9.0
        C.box(-PLX / 2 - 0.02, y - 0.04, 0.02, PLX / 2 + 0.02, y + 0.04, PLH + 0.005)
    for sx in (-1, 1):
        Or.box(sx * (PLX / 2) - 3.0, PLY0 + 1.0, 0.28, sx * (PLX / 2) + 3.0,
               PLY0 + 1.30, 0.46)

    # ---------------------------------------------------------- seat body
    Cr.box(X0, SY0, PLH, X1, SY1, BODY)
    # pan floor + rim kerb
    Cr.box(X0 + 3.0, SY0 + 3.0, PANZ, X1 - 3.0, SY1 - 3.0, BODY)
    Cr.box(X0, SY0, BODY, X1, SY0 + 3.0, SH)                 # south kerb
    Cr.box(X0, SY1 - 3.0, BODY, X1, SY1, SH)                 # north kerb
    Pg.box(X0, SY0 + 3.0, BODY, X0 + 3.0, SY1 - 3.0, SH)     # west kerb
    Pg.box(X1 - 3.0, SY0 + 3.0, BODY, X1, SY1 - 3.0, SH)     # east kerb
    # cushion deck (6 x 4 pads) — reads as the seat surface
    cn, cm = P["cushions"]
    px, py = (X1 - X0 - 6.0) / cn, (SY1 - SY0 - 6.0) / cm
    for i in range(cn):
        for j in range(cm):
            x = X0 + 3.0 + i * px
            y = SY0 + 3.0 + j * py
            Ru.box(x + 0.35, y + 0.35, BODY - 0.05, x + px - 0.35, y + py - 0.35, BODY + 0.22)
            St.box(x + 0.30, y + 0.30, BODY - 0.10, x + px - 0.30, y + py - 0.30, BODY - 0.02)
    # rim nosing + edge lighting
    for (x0, y0, x1, y1) in ((X0, SY0, X1, SY0 + 3.0), (X0, SY1 - 3.0, X1, SY1),
                             (X0, SY0, X0 + 3.0, SY1), (X1 - 3.0, SY0, X1, SY1)):
        St.box(x0 - 0.05, y0 - 0.05, SH - 0.10, x1 + 0.05, y1 + 0.05, SH + 0.05)
    Em.box(X0 + 3.2, SY0 + 2.85, SH - 0.22, X1 - 3.2, SY0 + 2.95, SH - 0.12)
    Em.box(X0 + 3.2, SY1 - 2.95, SH - 0.22, X1 - 3.2, SY1 - 2.85, SH - 0.12)

    # ---------------------------------------------------------- seat elevations
    # south facade: fins + doors + insignia band
    for i in range(-3, 4):
        x = i * 9.0
        Pn.box(x - 0.7, SY0 - 1.3, PLH, x + 0.7, SY0, 24.2)
    for x in (-20.0, -6.0, 8.0):
        Sd.box(x, SY0 - 0.10, PLH, x + 11.0, SY0 + 0.02, PLH + 7.4)
        for k in range(9):
            Sd.box(x + 0.2, SY0 - 0.16, PLH + 0.3 + k * 0.78, x + 10.8, SY0 - 0.10,
                   PLH + 0.72 + k * 0.78)
    Or.box(-14.0, SY0 - 0.55, 17.0, 14.0, SY0 - 0.05, 23.0)
    Wh.box(-13.0, SY0 - 0.62, 17.6, 13.0, SY0 - 0.55, 20.4)
    Wh.box(-13.0, SY0 - 0.62, 21.0, 13.0, SY0 - 0.55, 22.2)
    # service ladders + downpipes on the seat corners
    for sx in (-1, 1):
        Sd.pipe_run([(sx * (X1 - 0.8), SY0 - 0.25, 24.0), (sx * (X1 - 0.8), SY0 - 0.25, PLH + 0.6),
                     (sx * (X1 - 0.6), SY0 + 0.2, PLH + 0.1)], 0.16)
    St.push(Matrix.Translation((X1 + 0.05, -18.0, PLH)))
    St.ladder(18.0)
    St.pop()
    # cable tray under the rim, along the south face
    Sd.cable_tray([(X0 + 2.0, SY0 - 0.45, 23.9), (X1 - 2.0, SY0 - 0.45, 23.9)], 0.45, 0.18)
    # east / west flanks: panel fields + louvres
    for sx in (-1, 1):
        Pn.push(Matrix.Translation((sx * X1, -9.0, PLH)) @
                Matrix.Rotation(math.radians(90 * sx), 4, "Z"))
        Pn.panel_grid(40.0, 21.0, 10, 7, z0=0.6, gap=0.10, thick=0.12)
        Pn.pop()
        for k in range(3):
            Sd.push(Matrix.Translation((sx * (X1 + 0.02), -8.0 + k * 9.0, 18.0)) @
                    Matrix.Rotation(math.radians(90 * sx), 4, "Z"))
            Sd.louver(5.0, 3.2, 10, angle=-30.0)
            Sd.pop()
    # north face (against the backrest): access doors only
    Sd.box(-10.0, SY1 - 0.10, PLH, 10.0, SY1 + 0.02, PLH + 6.0)

    # ---------------------------------------------------------- backrest
    mid = SPW / 2.0
    Pn.box(X0, BY0, PLH, -mid, BY1, BH)                 # left slab
    Pn.box(mid, BY0, PLH, X1, BY1, BH)                  # right slab
    Pg.box(-mid, BY0 + SPD, PLH, mid, BY1, BH)          # recessed spine slab
    St.box(X0 - 0.15, BY0 - 0.15, BH - 0.55, X1 + 0.15, BY1 + 0.15, BH)
    # spine channel trim + light line
    for sx in (-1, 1):
        St.box(sx * mid - 0.18, BY0 - 0.10, 26.0, sx * mid + 0.18, BY0 + 0.02, BH - 0.6)
    EmC.box(-0.10, BY0 - 0.02, 27.0, 0.10, BY0 + 0.06, BH - 1.2)
    # one big padded back cushion (light composite) with quilting seams
    Pn.box(-27.0, BY0 - 0.75, 26.6, 27.0, BY0 - 0.05, 59.0)
    for k in range(6):
        Sd.box(-26.4, BY0 - 0.82, 28.0 + k * 5.2, 26.4, BY0 - 0.72, 28.35 + k * 5.2)
    for sx in (-1, 1):
        Sd.box(sx * 27.2 - 0.35, BY0 - 0.85, 26.6, sx * 27.2 + 0.35, BY0 - 0.05, 59.0)
    # structural fins only on the side wings
    for x in (-30.0, -26.0, 26.0, 30.0):
        Pn.box(x - 0.55, BY0 - 1.05, 26.0, x + 0.55, BY0, 76.0)
    # screen + frame high on the south face
    St.box(-13.0, BY0 - 0.60, 61.5, 13.0, BY0 - 0.05, 71.0)
    Sd.box(-12.4, BY0 - 0.66, 62.2, 12.4, BY0 - 0.60, 70.3)
    EmC.box(-11.6, BY0 - 0.70, 65.4, 11.6, BY0 - 0.66, 68.0)
    # glazed gallery bands on the flanks and the north face
    GWF = BD - 4.0                        # flank band must fit the 18 m backrest depth
    for z in (GZ, GZ + GH + 3.0):
        for sx in (1, -1):
            M = (Matrix.Translation((sx * X1, BY0 + BD / 2.0, z)) @
                 Matrix.Rotation(math.radians(90 * sx), 4, "Z"))
            Gl.push(M)
            Gl.box(-GWF / 2, -0.05, 0.0, GWF / 2, 0.03, GH)
            Gl.pop()
            St.push(M)
            St.window_band(GWF, GH, 4, z0=0.0, mull=0.28, head=0.35, sill=0.30)
            St.pop()
    for z in (GZ, GZ + GH + 3.0):
        M = Matrix.Translation((0.0, BY1, z))
        Gl.push(M)
        Gl.box(-GW / 2, -0.02, 0.0, GW / 2, 0.06, GH)
        Gl.pop()
        St.push(M)
        St.window_band(GW, GH, 10, z0=0.0, mull=0.28, head=0.35, sill=0.30)
        St.pop()
    # roof parapet + plant + mast + aviation lights
    for (x0, y0, x1, y1) in ((X0 - 0.3, BY0 - 0.3, X1 + 0.3, BY0 + 0.4),
                             (X0 - 0.3, BY1 - 0.4, X1 + 0.3, BY1 + 0.3),
                             (X0 - 0.3, BY0 - 0.3, X0 + 0.4, BY1 + 0.3),
                             (X1 - 0.4, BY0 - 0.3, X1 + 0.3, BY1 + 0.3)):
        St.box(x0, y0, BH + 0.45, x1, y1, BH + 1.55)
    for x in (-24.0, -12.0, 0.0, 12.0, 24.0):
        Sd.push(Matrix.Translation((x, BY0 + 5.5, BH + 0.45)))
        Sd.ac_unit(3.2, 1.8, 2.2)
        Sd.pop()
    Sd.push(Matrix.Translation((0.0, BY0 + BD / 2.0, BH + 0.45)))
    Sd.whip(MAST, 0.28)
    Sd.pop()
    for sx in (-1, 1):
        Am.beacon(0.35, BH + 1.6)
        Am.cyl(sx * (X1 - 0.6), BY1 - 0.6, BH + 1.55, BH + 1.95, 0.30, seg=8)
    St.push(Matrix.Translation((X1 + 0.1, BY0 + 2.0, 26.0)))
    St.ladder(BH - 26.0)
    St.pop()

    # ---------------------------------------------------------- stair + lift
    C.box(X1 + 1.0, -20.0, 0.0, X1 + 1.0 + STW, -11.0, PLH)
    Pg.box(X1 + 1.0, -20.0, PLH, X1 + 1.0 + STW, -11.0, STH)
    St.box(X1 + 0.8, -20.2, STH, X1 + 1.2 + STW, -10.8, STH + 0.35)
    for k in range(4):
        z = PLH + 1.2 + k * 6.6
        Gl.box(X1 + 0.96, -17.0, z, X1 + 1.04, -12.0, z + 3.0)
        St.box(X1 + 0.93, -17.2, z - 0.25, X1 + 1.07, -11.8, z + 3.25)
    Sd.box(X1 + 1.0, -20.6, PLH, X1 + 1.6, -20.0, PLH + 2.6)
    Or.box(X1 + 0.95, -20.75, PLH + 2.6, X1 + 1.65, -20.0, PLH + 2.9)
    C.box(X0 - 1.0 - ELW, -18.0, 0.0, X0 - 1.0, -10.0, PLH)
    Pg.box(X0 - 1.0 - ELW, -18.0, PLH, X0 - 1.0, -10.0, ELH)
    St.box(X0 - 1.2 - ELW, -18.2, ELH, X0 - 0.8, -9.8, ELH + 0.35)
    Sd.box(X0 - 1.0 - ELW, -14.4, PLH, X0 - 0.94, -13.6, ELH - 1.0)
    Sd.push(Matrix.Translation((X0 - 1.0 - ELW / 2, -14.0, ELH + 0.35)))
    Sd.ac_unit(3.0, 1.8, 1.8)
    Sd.pop()

    # ---------------------------------------------------------- ground kit
    Veh = K.MB("SIT-veh")
    Vg = K.MB("SIT-veh-glass")
    Vr = K.MB("SIT-veh-rubber")
    for i in range(2):
        M = Matrix.Translation((-24.0 + i * 10.0, -35.0, PLH))
        Veh.push(M)
        Vg.push(M)
        Vr.push(M)
        Veh.vehicle(L=5.35, W=2.26, H=1.96, glass=Vg, rubber=Vr)
        Vr.pop()
        Vg.pop()
        Veh.pop()
    for i in range(3):
        Sd.push(Matrix.Translation((-24.0 + i * 14.0, -33.6, PLH)) @
                Matrix.Rotation(math.pi / 2, 4, "Z"))
        Sd.container(12.19, 2.44, 2.59, ribs=26)
        Sd.pop()
    for sx in (-1, 1):
        St.lathe([(0.22, 0.0), (0.15, 15.0)], sx * (PLX / 2 - 2.0), PLY0 + 2.0, seg=10)
        St.box(sx * (PLX / 2 - 2.0) - 0.8, PLY0 + 1.7, 15.0,
               sx * (PLX / 2 - 2.0) + 0.8, PLY0 + 2.3, 15.3)
        for k in (-1, 1):
            Sd.box(sx * (PLX / 2 - 2.0) + k * 0.45 - 0.30, PLY0 + 1.6, 15.05,
                   sx * (PLX / 2 - 2.0) + k * 0.45 + 0.30, PLY0 + 1.96, 15.4)
            Em.box(sx * (PLX / 2 - 2.0) + k * 0.45 - 0.26, PLY0 + 1.56, 15.12,
                   sx * (PLX / 2 - 2.0) + k * 0.45 + 0.26, PLY0 + 1.62, 15.34)

    objs = [
        K.emit(C, col, "conc", "GEO-SIT-plinth", root),
        K.emit(Cr, col, "concrete_raw", "GEO-SIT-seat", root),
        K.emit(Pn, col, "panel", "GEO-SIT-panel", root),
        K.emit(Pg, col, "panel_grey", "GEO-SIT-grey", root),
        K.emit(St, col, "steel", "GEO-SIT-steel", root),
        K.emit(Sd, col, "steel_dark", "GEO-SIT-dark", root),
        K.emit(Gl, col, "glass_green", "GEO-SIT-glass", root),
        K.emit(Em, col, "em_white", "GEO-SIT-light", root),
        K.emit(EmC, col, "em_cyan", "GEO-SIT-systems", root),
        K.emit(Am, col, "em_amber", "GEO-SIT-beacon", root),
        K.emit(Or, col, "orange", "GEO-SIT-hazard", root),
        K.emit(Ru, col, "rubber_dark", "GEO-SIT-cushions", root),
        K.emit(Wh, col, "white", "GEO-SIT-markings", root),
        K.emit(Veh, col, "panel_sand", "GEO-SIT-vehicles", root),
        K.emit(Vg, col, "glass", "GEO-SIT-veh-glass", root),
        K.emit(Vr, col, "rubber", "GEO-SIT-veh-tyres", root),
    ]
    K.sky()
    K.finish(objs, OUT, "SIT", extra={"seat": [SW, SD, SH], "back": [BW, BD, BH]})


if __name__ == "__main__":
    main()
