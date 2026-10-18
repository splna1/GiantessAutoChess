# -*- coding: utf-8 -*-
"""CON — 施工场 / construction site.

Open excavation with sheet-pile shoring, a half-built concrete frame, formwork,
scaffolding, laydown yard sized for the 100 m helper (beams 20 m, panels 12 m,
containers 12.2 m), site offices, batching plant and a marked hand-off pad.
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

P = S.MODS["CON"]
OUT = os.path.join(K.ROOT, "model", "m6", "base", "M6_CON_Site.blend")

PW, PD = P["plot"]
CX0, CX1 = -PW / 2, PW / 2
CY0, CY1 = -PD / 2, PD / 2
PIT_W, PIT_D, PIT_DP = P["pit"]
PIT_CX, PIT_CY = -12.0, 8.0
PX0, PX1 = PIT_CX - PIT_W / 2, PIT_CX + PIT_W / 2
PY0, PY1 = PIT_CY - PIT_D / 2, PIT_CY + PIT_D / 2
FX0, FX1, FY0, FY1 = 4.0, 28.0, -2.0, 16.0
BH = P["frame_bh"]
OFFW, OFFD, OFFH = P["office"]


def face(mb, side, lat, z, hx, hy):
    if side == 0:
        mb.at(lat, -hy, z)
    elif side == 1:
        mb.at(hx, lat, z, 90.0)
    elif side == 2:
        mb.at(-lat, hy, z, 180.0)
    else:
        mb.at(-hx, lat, z, -90.0)


def main():
    col, root = K.scene("CON")

    C = K.MB("CON-conc")
    Pn = K.MB("CON-panel")
    St = K.MB("CON-steel")
    Pl = K.MB("CON-plate")
    Dk = K.MB("CON-dark")
    Tm = K.MB("CON-timber")
    Rb = K.MB("CON-rebar")
    Dt = K.MB("CON-dirt")
    Gv = K.MB("CON-gravel")
    Yl = K.MB("CON-yellow")
    Or = K.MB("CON-hazard")
    Wh = K.MB("CON-white")
    Em = K.MB("CON-light")
    EmC = K.MB("CON-systems")
    Gl = K.MB("CON-glass")

    # ---------------------------------------------------------- pad + pit
    # gravel working surface, split around the excavation
    for (x0, y0, x1, y1) in ((CX0, CY0, PX0, CY1), (PX1, CY0, CX1, CY1),
                             (PX0, PY1, PX1, CY1), (PX0, CY0, PX1, PY0)):
        Gv.box(x0, y0, 0.0, x1, y1, 0.10)
    Dt.box(PX0, PY0, -PIT_DP, PX1, PY1, -PIT_DP + 0.25)   # excavated earth, reads as depth
    # sheet-pile walls with walers + struts
    for (x0, y0, x1, y1, horiz) in ((PX0, PY0, PX1, PY0 + 0.35, True),
                                    (PX0, PY1 - 0.35, PX1, PY1, True),
                                    (PX0, PY0, PX0 + 0.35, PY1, False),
                                    (PX1 - 0.35, PY0, PX1, PY1, False)):
        Pl.box(x0, y0, -PIT_DP, x1, y1, 0.30)
        n = int(((x1 - x0) if horiz else (y1 - y0)) / 1.2)
        for i in range(n):
            if horiz:
                x = x0 + i * (x1 - x0) / n
                Pl.box(x, y0 - 0.06, -PIT_DP + 0.2, x + 0.10, y0, 0.30)
            else:
                y = y0 + i * (y1 - y0) / n
                Pl.box(x0 - 0.06, y, -PIT_DP + 0.2, x0, y + 0.10, 0.30)
        # waler band + trench brace
        if horiz:
            St.box(x0, y0 - 0.22, -1.1, x1, y0, -0.75)
            for i in range(1, 4):
                x = x0 + i * (x1 - x0) / 4
                St.tube([(x, y0, -0.95), (x, PY1, -0.95)], 0.16, seg=8)
        else:
            St.box(x0 - 0.22, y0, -1.1, x0, y1, -0.75)
    # pit floor details: rebar mat, sump, ramp
    for i in range(9):
        Rb.box(PX0 + 1.0, PY0 + 1.2 + i * 2.2, -PIT_DP + 0.27, PX1 - 1.0,
               PY0 + 1.28 + i * 2.2, -PIT_DP + 0.33)
    for i in range(7):
        Rb.box(PX0 + 1.6 + i * 4.0, PY0 + 1.0, -PIT_DP + 0.27, PX0 + 1.66 + i * 4.0,
               PY1 - 1.0, -PIT_DP + 0.33)
    C.box(PX1 - 5.0, PY0 + 1.0, -PIT_DP + 0.25, PX1 - 2.0, PY0 + 3.5, -PIT_DP + 1.0)
    Dt.prism_y([(PY0, -PIT_DP + 0.25), (PY1 - 6.0, -PIT_DP + 0.25),
                (PY1 - 6.0, 0.10), (PY1 - 10.0, 0.10)], PX0 + 1.0, PX0 + 5.0)

    # pit rim safety railing (orange/white posts + two rails)
    edges = ((PX0, PY0, PX1, PY0, True), (PX0, PY1, PX1, PY1, True),
             (PX0, PY0, PX0, PY1, False), (PX1, PY0, PX1, PY1, False))
    for (x0, y0, x1, y1, horiz) in edges:
        n = int(max(abs(x1 - x0), abs(y1 - y0)) / 2.4) + 1
        for i in range(n + 1):
            if horiz:
                x = x0 + i * (x1 - x0) / n
                Or.box(x - 0.05, y0 - 0.05, 0.10, x + 0.05, y0 + 0.05, 1.15)
            else:
                y = y0 + i * (y1 - y0) / n
                Or.box(x0 - 0.05, y - 0.05, 0.10, x0 + 0.05, y + 0.05, 1.15)
        for zz in (0.65, 1.10):
            if horiz:
                Wh.box(x0, y0 - 0.03, zz, x1, y0 + 0.03, zz + 0.05)
                Wh.box(x0, y1 - 0.03, zz, x1, y1 + 0.03, zz + 0.05)
            else:
                Wh.box(x0 - 0.03, y0, zz, x0 + 0.03, y1, zz + 0.05)
                Wh.box(x1 - 0.03, y0, zz, x1 + 0.03, y1, zz + 0.05)
    # staged "giant" bundles beside the hand-off pad
    for i in range(3):
        Rb.push(Matrix.Translation((18.0, -24.0 + i * 2.0, 0.55)))
        Rb.rebar_bundle(20.0, 0.80, 11)
        Rb.pop()
    Tm.box(4.0, -25.0, 0.0, 30.0, -25.6, 0.30)

    # ---------------------------------------------------------- partial frame
    bays_x, bays_y = 3, 2
    xs = [FX0 + i * (FX1 - FX0) / bays_x for i in range(bays_x + 1)]
    ys = [FY0 + j * (FY1 - FY0) / bays_y for j in range(bays_y + 1)]
    for x in xs:
        for y in ys:
            C.box(x - 0.45, y - 0.45, 0.0, x + 0.45, y + 0.45, BH)
            for (dx, dy) in ((-0.26, -0.26), (0.26, -0.26), (0.26, 0.26), (-0.26, 0.26)):
                Rb.box(x + dx - 0.035, y + dy - 0.035, BH, x + dx + 0.035,
                       y + dy + 0.035, BH + 1.35)
    # level 1 slab: all bays, level 2: three bays
    for i in range(bays_x):
        for j in range(bays_y):
            C.box(xs[i], ys[j], 4.40, xs[i + 1], ys[j + 1], 4.74)
            if i < 2 and j < 1:
                C.box(xs[i], ys[j], 8.80, xs[i + 1], ys[j + 1], 9.14)
    # edge beams + slab edge formwork
    for x in xs:
        C.box(x - 0.22, FY0, 4.40, x + 0.22, FY1, 5.00)
    for y in ys:
        C.box(FX0, y - 0.22, 4.40, FX1, y + 0.22, 5.00)
    for i in range(bays_x):
        Tm.box(xs[i], FY0 - 0.35, 4.74, xs[i + 1], FY0 - 0.10, 5.55)
        Tm.box(xs[i], FY0 - 0.45, 5.55, xs[i + 1], FY0 - 0.10, 5.70)
    # props under the second slab
    for i in range(2):
        for j in range(1):
            for k in range(3):
                px = xs[i] + (k + 1) * (xs[i + 1] - xs[i]) / 4
                py = ys[j] + 2.6
                St.tube([(px, py, 4.74), (px, py, 8.80)], 0.09, seg=8)
                St.tube([(px, py, 7.9), (px, py + 2.2, 8.80)], 0.05, seg=6)

    # ---------------------------------------------------------- scaffolding
    for j in range(9):
        y = FY0 + j * 2.0
        for sx in (-1, 1):
            St.tube([(FX0 - 0.9, y, 0.10), (FX0 - 0.9, y, 8.9)], 0.055, seg=6)
            St.tube([(FX0 - 1.9, y, 0.10), (FX0 - 1.9, y, 8.9)], 0.055, seg=6)
        for z in (2.2, 4.4, 6.6):
            St.box(FX0 - 2.1, y - 0.05, z, FX0 - 0.7, y + 0.05, z + 0.08)
            St.tube([(FX0 - 1.9, y, z), (FX0 - 0.9, y, z + 2.2)], 0.04, seg=5)
        Tm.box(FX0 - 2.0, y - 0.6, 2.24, FX0 - 0.8, y + 0.6, 2.30)
        Tm.box(FX0 - 2.0, y - 0.6, 6.64, FX0 - 0.8, y + 0.6, 6.70)
    for z in (2.2, 4.4, 6.6, 8.8):
        St.tube([(FX0 - 0.9, FY0, z), (FX0 - 0.9, FY1, z)], 0.05, seg=6)

    # ---------------------------------------------------------- laydown yard
    # steel beams (20 m): three courses
    BL, BD = P["beams"]["len"], P["beams"]["d"]
    for row, (n, zz) in enumerate(((3, 0.60), (2, 1.72), (1, 2.84))):
        for i in range(n):
            y = -22.0 + i * 1.45
            Pl.push(Matrix.Translation((-30.0, y, zz)))
            Pl.i_beam(BL, BD, 0.42)
            Pl.pop()
    # timber dunnage under the stacks
    for i in range(4):
        x = -30.0 + 2.0 + i * 5.2
        Tm.box(x, -22.6, 0.0, x + 0.35, -20.0, 0.14)
    # precast panels on A-frames
    PAN = P["panels"]
    for i in range(PAN["n"]):
        x = -28.0 + i * 2.6
        Pn.push(Matrix.Translation((x, -12.0, 0.62)) @ Matrix.Rotation(math.radians(-74), 4, "X"))
        Pn.box(-PAN["w"] / 2, -PAN["t"] / 2, 0.0, PAN["w"] / 2, PAN["t"] / 2, PAN["h"])
        Pn.pop()
        Tm.box(x - 1.2, -12.9, 0.0, x + 1.2, -12.3, 0.55)
        Tm.box(x - 1.2, -11.9, 0.0, x + 1.2, -11.2, 0.90)
    # rebar bundles + pipe bundle
    for i in range(3):
        Rb.push(Matrix.Translation((-26.0, -6.0 + i * 1.8, 0.65)))
        Rb.rebar_bundle(18.0, 0.62, 9)
        Rb.pop()
    Rb.push(Matrix.Translation((-26.0, -1.2, 1.95)))
    Rb.rebar_bundle(18.0, 0.55, 7)
    Rb.pop()
    Pl.push(Matrix.Translation((-24.0, 7.0, 0.0)))
    Pl.pipe_bundle(14.0, 0.50, 3, 2)
    Pl.pop()
    # block pallets
    for i in range(4):
        for j in range(2):
            Tm.push(Matrix.Translation((-8.0 + i * 3.0, -22.0 + j * 2.6, 0.10)))
            Tm.pallet(2.4, 1.2, 1.2)
            Tm.pop()
    # containers (12.2 m) along the south edge
    for i in range(P["containers"]):
        x = -2.0 + i * 3.0
        layers = 2 if i in (1, 3) else 1
        for k in range(layers):
            Dk.push(Matrix.Translation((x, -20.0, 0.10 + k * 2.62)) @
                    Matrix.Rotation(math.pi / 2, 4, "Z"))
            Dk.container(12.19, 2.44, 2.59, ribs=30)
            Dk.pop()

    # ---------------------------------------------------------- handoff pad
    HX, HY = 17.0, -18.0
    C.box(HX - 10.0, HY - 6.0, 0.0, HX + 10.0, HY + 6.0, 0.16)
    for i in range(6):
        Wh.paint_line((HX - 8.5, HY - 5.0 + i * 2.0), (HX + 8.5, HY - 5.0 + i * 2.0),
                      0.16, z=0.17)
    for i in range(7):
        Wh.prism_z([(HX - 8.0 + i * 2.4, HY - 5.6), (HX - 7.2 + i * 2.4, HY - 5.6),
                    (HX - 7.6 + i * 2.4, HY - 4.9)], 0.165, 0.175)
    for sx in (-1, 1):
        for sy in (-1, 1):
            St.box(HX + sx * 9.4 - 0.14, HY + sy * 5.4 - 0.14, 0.16,
                   HX + sx * 9.4 + 0.14, HY + sy * 5.4 + 0.14, 1.35)
            EmC.box(HX + sx * 9.4 - 0.18, HY + sy * 5.4 - 0.18, 1.35,
                    HX + sx * 9.4 + 0.18, HY + sy * 5.4 + 0.18, 1.55)
    Pl.box(HX - 10.5, HY + 6.0, 0.0, HX + 10.5, HY + 6.6, 0.30)
    Or.box(HX - 10.5, HY + 5.95, 0.30, HX + 10.5, HY + 6.1, 0.45)

    # ---------------------------------------------------------- site office
    OX, OY = -26.0, 22.0
    for k in range(2):
        for i in range(2):
            Dk.push(Matrix.Translation((OX + i * 3.0, OY + k * 3.0, 0.10)) @
                    Matrix.Rotation(math.pi / 2, 4, "Z"))
            Dk.container(9.0, 2.9, 2.9, ribs=22)
            Dk.pop()
    Gl.box(OX + 2.2, OY - 4.7, 1.5, OX + 5.8, OY - 4.0, 2.6)
    Em.box(OX + 2.4, OY - 4.75, 2.95, OX + 5.6, OY - 4.68, 3.02)
    EmC.box(OX + 6.6, OY + 4.2, 1.2, OX + 7.2, OY + 4.26, 2.0)
    St.box(OX - 1.0, OY + 6.4, 0.0, OX + 1.0, OY + 6.5, 2.4)
    Wh.box(OX - 0.9, OY + 6.42, 1.0, OX + 0.9, OY + 6.48, 2.2)

    # ---------------------------------------------------------- batching plant
    BX, BY = 22.0, 22.0
    C.box(BX - 3.0, BY - 3.0, 0.0, BX + 3.0, BY + 3.0, 0.35)
    for sx in (-1, 1):
        for sy in (-1, 1):
            St.box(BX + sx * 2.4 - 0.12, BY + sy * 2.4 - 0.12, 0.35,
                   BX + sx * 2.4 + 0.12, BY + sy * 2.4 + 0.12, 3.4)
    Pl.lathe([(2.6, 3.4), (2.6, 4.0), (1.6, 4.6), (1.6, 5.4),
              (2.2, 5.6), (2.2, 6.0)], BX, BY, seg=20)
    Pl.silo(1.5, 5.0, z0=3.4, legs=2.2)
    St.tube([(BX - 4.0, BY - 4.0, 1.0), (BX - 1.0, BY - 1.0, 7.0)], 0.22, seg=8)
    Dt.prism_z([(BX - 2.2, BY - 6.5), (BX + 2.2, BY - 6.5), (BX + 1.4, BY - 4.2),
                (BX - 1.4, BY - 4.2)], 0.0, 1.5)

    # ---------------------------------------------------------- plant + piles
    for (px, py, pr, ph) in ((12.0, -8.0, 3.2, 2.2), (-4.0, -14.0, 2.6, 1.8)):
        Dt.lathe([(pr, 0.0), (pr * 0.75, ph * 0.55), (0.0, ph)], px, py, seg=14)
    Gv.lathe([(2.4, 0.0), (2.0, 1.1), (0.0, 1.6)], 8.0, 4.0, seg=14)
    # light tower
    St.lathe([(0.16, 0.10), (0.12, 11.0)], 30.0, -22.0, seg=10)
    St.box(29.2, -22.2, 11.0, 30.8, -21.8, 11.3)
    for k in (-1, 0, 1):
        Em.box(29.6 + k * 0.45, -22.3, 11.1, 29.9 + k * 0.45, -22.15, 11.28)
    # generator + fuel
    Dk.box(-30.0, 6.0, 0.10, -27.0, 8.0, 1.6)
    Dt.lathe([(0.9, 0.10), (0.9, 1.25), (0.0, 1.35)], -29.0, 10.0, seg=14)

    # ---------------------------------------------------------- fence + gate
    # open site fencing: low concrete kerb + posts + rails (keeps the yard readable)
    for (x0, y0, x1, y1, horiz) in ((CX0, CY0, CX1, CY0 + 0.20, True),
                                    (CX0, CY1 - 0.20, CX1, CY1, True),
                                    (CX0, CY0, CX0 + 0.20, CY1, False),
                                    (CX1 - 0.20, CY0, CX1, CY1, False)):
        Pl.box(x0, y0, 0.0, x1, y1, 0.55)
        n = int(max(x1 - x0, y1 - y0) / 3.0)
        for i in range(n + 1):
            if horiz:
                x = x0 + i * (x1 - x0) / n
                Pl.box(x - 0.05, y0 - 0.05, 0.55, x + 0.05, y1 + 0.05, 2.45)
            else:
                y = y0 + i * (y1 - y0) / n
                Pl.box(x0 - 0.05, y - 0.05, 0.55, x1 + 0.05, y + 0.05, 2.45)
        for zz in (1.45, 2.10, 2.42):
            if horiz:
                Pl.box(x0, y0 + 0.06, zz, x1, y1 - 0.06, zz + 0.06)
            else:
                Pl.box(x0 + 0.06, y0, zz, x1 - 0.06, y1, zz + 0.06)
        # wire mesh suggestion: vertical strands every 0.6 m
        m = int(max(x1 - x0, y1 - y0) / 0.6)
        for i in range(m):
            if horiz:
                x = x0 + i * (x1 - x0) / m
                Pl.box(x - 0.012, y0 + 0.08, 0.55, x + 0.012, y0 + 0.12, 2.42)
            else:
                y = y0 + i * (y1 - y0) / m
                Pl.box(x0 + 0.08, y - 0.012, 0.55, x0 + 0.12, y + 0.012, 2.42)
    # gate posts + barrier
    for sx in (-1, 1):
        St.box(sx * 4.2 - 0.16, CY0 - 0.9, 0.0, sx * 4.2 + 0.16, CY0 + 0.2, 2.7)
    for k in range(9):
        Or.box(-3.9 + k * 0.9, CY0 - 0.75, 1.05, -3.4 + k * 0.9, CY0 - 0.68, 1.35)

    objs = [
        K.emit(C, col, "concrete_raw", "GEO-CON-concrete", root),
        K.emit(Pn, col, "panel_grey", "GEO-CON-panels", root),
        K.emit(St, col, "steel_matte", "GEO-CON-steel", root),
        K.emit(Pl, col, "steel_plate", "GEO-CON-plate", root),
        K.emit(Dk, col, "steel_dark", "GEO-CON-dark", root),
        K.emit(Tm, col, "timber", "GEO-CON-timber", root),
        K.emit(Rb, col, "rebar", "GEO-CON-rebar", root),
        K.emit(Dt, col, "dirt_pile", "GEO-CON-dirt", root),
        K.emit(Gv, col, "gravel_pile", "GEO-CON-gravel", root),
        K.emit(Or, col, "orange", "GEO-CON-hazard", root),
        K.emit(Wh, col, "white", "GEO-CON-markings", root),
        K.emit(Em, col, "em_white", "GEO-CON-light", root),
        K.emit(EmC, col, "em_cyan", "GEO-CON-systems", root),
        K.emit(Gl, col, "glass", "GEO-CON-glass", root),
    ]
    K.sky()
    K.finish(objs, OUT, "CON", extra={"pit": [PIT_W, PIT_D, PIT_DP],
                                      "beams": P["beams"], "panels": P["panels"]})


if __name__ == "__main__":
    main()
