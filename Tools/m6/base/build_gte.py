# -*- coding: utf-8 -*-
"""GTE — 门禁 · 围墙: gatehouse with canopy, two sentry towers, sliding gates,
drop-arm barrier, inspection lane, and a sensor-fenced perimeter wall run.
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

P = S.MODS["GTE"]
OUT = os.path.join(K.ROOT, "model", "m6", "base", "M6_GTE_Gate.blend")

HW, HD, HH = P["house"]
CW, CD, CH = P["canopy"]
TW, TD, TH = P["tower"]
GAP = P["tower_gap"]
BL = P["barrier"]
WL, WH, WT, PIER = P["wall"]["len"], P["wall"]["h"], P["wall"]["t"], P["wall"]["pier"]
LANE_W, LANE_D = P["lane"]


def main():
    col, root = K.scene("GTE")

    C = K.MB("GTE-conc")
    Pn = K.MB("GTE-panel")
    St = K.MB("GTE-steel")
    Sd = K.MB("GTE-dark")
    Gl = K.MB("GTE-glass")
    Em = K.MB("GTE-light")
    EmC = K.MB("GTE-systems")
    Or = K.MB("GTE-hazard")
    Rd = K.MB("GTE-red")
    Gv = K.MB("GTE-markings")

    HY = 5.0
    # ---------------------------------------------------------- lane + markings
    C.box(-LANE_W / 2, -LANE_D / 2 - 1.0, -0.30, LANE_W / 2, HY, 0.10)
    for x in (-4.2, 4.2):
        Gv.paint_line((x, -LANE_D / 2), (x, -1.0), 0.16, z=0.104)
    for x in (-2.0, 2.0):
        Gv.paint_line((x, 1.0), (x, HY - 0.6), 0.16, z=0.104)
    for i in range(7):
        Gv.paint_line((-LANE_W / 2 + 1.2, -LANE_D / 2 + 1.0 + i * 1.6),
                      (-LANE_W / 2 + 1.2, -LANE_D / 2 + 2.0 + i * 1.6), 0.10, z=0.104)
    for i in range(2):
        Gv.box(-4.6, -6.0 - i * 6.0, 0.10, 4.6, -5.4 - i * 6.0, 0.22)
    # jersey barriers funnelling the approach
    for sx in (-1, 1):
        for i in range(3):
            C.push(Matrix.Translation((sx * 7.4, -3.0 - i * 3.4, 0.10)) @
                   Matrix.Rotation(math.radians(90), 4, "Z"))
            C.jersey(3.2, 1.02, 0.62)
            C.pop()

    # ---------------------------------------------------------- gatehouse
    C.box(-HW / 2 - 0.5, HY - HD / 2 - 0.5, 0.0, HW / 2 + 0.5, HY + HD / 2, 0.45)
    Pn.box(-HW / 2, HY - HD / 2, 0.45, HW / 2, HY + HD / 2, HH)
    St.box(-HW / 2 - 0.35, HY - HD / 2 - 0.35, HH, HW / 2 + 0.35, HY + HD / 2 + 0.35, HH + 0.30)
    # continuous glazing on the lane side + door
    Gl.box(-HW / 2 + 0.5, HY - HD / 2 - 0.10, 1.30, HW / 2 - 0.5, HY - HD / 2 + 0.02, 2.85)
    St.box(-HW / 2 + 0.35, HY - HD / 2 - 0.22, 1.20, HW / 2 - 0.35, HY - HD / 2 + 0.05, 2.98)
    for i in range(5):
        x = -HW / 2 + 1.2 + i * (HW - 2.4) / 4.0
        St.box(x - 0.06, HY - HD / 2 - 0.26, 1.22, x + 0.06, HY - HD / 2 - 0.10, 2.96)
    Sd.box(HW / 2 - 1.2, HY - HD / 2 - 0.14, 0.45, HW / 2 - 0.2, HY - HD / 2 + 0.02, 2.35)
    Em.box(-HW / 2 + 0.7, HY - HD / 2 - 0.30, 2.82, HW / 2 - 0.7, HY - HD / 2 - 0.24, 2.90)
    # canopy over the lane
    St.box(-CW / 2, HY - HD / 2 - CD, HH - CH, CW / 2, HY - HD / 2 + 0.2, HH)
    St.box(-CW / 2 + 0.4, HY - HD / 2 - CD + 0.1, HH - CH - 0.25, CW / 2 - 0.4,
           HY - HD / 2 - CD + 0.35, HH - CH)
    for sx in (-1, 1):
        St.box(sx * (CW / 2 - 0.5) - 0.12, HY - HD / 2 - CD + 0.2, 0.10,
               sx * (CW / 2 - 0.5) + 0.12, HY - HD / 2 - CD + 0.44, HH - CH)
    Em.box(-CW / 2 + 0.8, HY - HD / 2 - CD + 0.35, HH - CH - 0.12,
           CW / 2 - 0.8, HY - HD / 2 - CD + 0.5, HH - CH - 0.04)
    # roof plant + comms
    Sd.push(Matrix.Translation((-HW / 2 + 2.0, HY + 1.0, HH + 0.30)))
    Sd.ac_unit(1.6, 0.9, 1.05)
    Sd.pop()
    Sd.whip(3.2, 0.05, z0=HH + 0.30)
    Sd.box(HW / 2 - 3.4, HY - 0.4, HH + 0.30, HW / 2 - 2.0, HY + 1.0, HH + 1.15)

    # ---------------------------------------------------------- towers
    for sx in (-1, 1):
        tx = sx * GAP
        C.box(tx - TW / 2 - 0.3, -TD / 2 - 0.3, 0.0, tx + TW / 2 + 0.3, TD / 2 + 0.3, 0.55)
        Pn.box(tx - TW / 2, -TD / 2, 0.55, tx + TW / 2, TD / 2, TH)
        St.box(tx - TW / 2 - 0.30, -TD / 2 - 0.30, TH - 0.2, tx + TW / 2 + 0.30,
               TD / 2 + 0.30, TH + 0.25)
        # cabin
        St.box(tx - TW / 2 - 0.55, -TD / 2 - 0.55, TH + 0.25, tx + TW / 2 + 0.55,
               TD / 2 + 0.55, TH + 2.75)
        for side, (ax, ay, aw, ad) in enumerate((
                (tx, -TD / 2 - 0.58, TW - 1.0, 0.04),
                (tx, TD / 2 + 0.54, TW - 1.0, 0.04),
                (tx - TW / 2 - 0.58, 0.0, 0.04, TD - 1.0),
                (tx + TW / 2 + 0.54, 0.0, 0.04, TD - 1.0))):
            Gl.box(ax - aw / 2, ay - ad / 2, TH + 0.45, ax + aw / 2, ay + ad / 2, TH + 2.45)
        St.box(tx - TW / 2 - 0.85, -TD / 2 - 0.85, TH + 2.75, tx + TW / 2 + 0.85,
               TD / 2 + 0.85, TH + 3.05)
        # roof lamp + searchlight
        Em.box(tx - 0.5, -0.5, TH + 3.05, tx + 0.5, 0.5, TH + 3.15)
        St.box(tx - 0.45, -TD / 2 - 0.9, TH + 2.2, tx + 0.45, -TD / 2 - 0.55, TH + 2.7)
        EmC.box(tx - 0.34, -TD / 2 - 0.93, TH + 2.28, tx + 0.34, -TD / 2 - 0.86, TH + 2.62)
        # ladder + railing
        St.push(Matrix.Translation((tx + TW / 2 + 0.62, 0.0, 0.55)) @
                Matrix.Rotation(math.radians(90), 4, "Z"))
        St.ladder(TH - 0.6)
        St.pop()
        for (dx, dy, ang) in ((-TW / 2 - 0.7, -TD / 2 - 0.7, 0.0),
                              (-TW / 2 - 0.7, TD / 2 + 0.7, 0.0)):
            St.push(Matrix.Translation((tx + dx, dy, TH + 0.25)) @
                    Matrix.Rotation(math.radians(ang), 4, "Z"))
            St.railing(TW + 1.4, h=0.95)
            St.pop()

    # ---------------------------------------------------------- gates + barrier
    for sx in (-1, 1):
        x0 = sx * (GAP - TW / 2 - 0.1)
        Sd.push(Matrix.Translation((x0 - sx * 6.2, 0.0, 0.10)))
        for k in range(5):
            Sd.box(k * 1.22, -0.10, 0.0, k * 1.22 + 1.12, 0.10, 2.35)
            Sd.box(k * 1.22, -0.06, 1.15, k * 1.22 + 1.12, 0.06, 1.25)
        Sd.pop()
    St.box(-GAP + TW / 2, -0.20, 2.45, GAP - TW / 2, 0.20, 2.70)
    # drop-arm barrier
    St.lathe([(0.20, 0.10), (0.20, 1.05)], 0.0, -1.8, seg=10)
    St.box(-0.25, -2.05, 1.05, 0.25, -1.55, 1.45)
    for k in range(8):
        Rd.box(0.2 + k * (BL / 8.0), -1.42, 1.18, 0.2 + (k + 1) * (BL / 8.0) - 0.05,
               -1.36, 1.36)
    Sd.box(0.2, -1.55, 1.14, BL, -1.42, 1.18)
    Sd.box(0.2, -1.36, 1.36, BL, -1.30, 1.40)
    # guard kiosk in the lane
    C.box(5.4, -1.0, 0.10, 6.6, 0.4, 0.35)
    Pn.box(5.45, -0.95, 0.35, 6.55, 0.35, 2.55)
    Gl.box(5.50, -0.98, 1.10, 6.50, -0.90, 2.35)
    St.box(5.3, -1.10, 2.55, 6.7, 0.55, 2.75)
    Em.box(5.55, -1.05, 2.68, 6.45, -0.98, 2.73)

    # ---------------------------------------------------------- perimeter wall
    for sx in (-1, 1):
        x0 = sx * (GAP + 2.1)
        n = int(WL / PIER)
        Pn.box(min(x0, x0 + sx * WL), -WT / 2, 0.0, max(x0, x0 + sx * WL), WT / 2, WH)
        for i in range(n + 1):
            x = x0 + sx * i * PIER
            Pn.box(x - 0.28, -WT / 2 - 0.16, 0.0, x + 0.28, WT / 2 + 0.16, WH + 0.28)
        # sensor posts + lamps
        for i in range(4):
            x = x0 + sx * (3.0 + i * 9.5)
            St.box(x - 0.07, -WT / 2 - 0.34, WH - 0.55, x + 0.07, -WT / 2 - 0.20, WH + 0.35)
            EmC.box(x - 0.12, -WT / 2 - 0.40, WH + 0.05, x + 0.12, -WT / 2 - 0.32, WH + 0.22)
        # razor coil: shallow helix along the top
        pts = []
        for i in range(40):
            t = i / 39.0
            pts.append((x0 + sx * t * WL, 0.35 * math.cos(t * 30.0), WH + 0.75 + 0.22 * math.sin(t * 30.0)))
        Sd.tube(pts, 0.035, seg=4)
        # hazard band at the base
        for i in range(3):
            Or.box(min(x0 + sx * (1.0 + i * 12.0), x0 + sx * (4.0 + i * 12.0)),
                   -WT / 2 - 0.02, 0.30, max(x0 + sx * (1.0 + i * 12.0), x0 + sx * (4.0 + i * 12.0)),
                   -WT / 2 + 0.01, 0.75)

    # gate signage board
    St.box(-3.4, HY - HD / 2 - CD - 0.1, HH + 0.3, 3.4, HY - HD / 2 - CD + 0.05, HH + 1.4)
    EmC.box(-3.1, HY - HD / 2 - CD - 0.14, HH + 0.45, 3.1, HY - HD / 2 - CD - 0.08, HH + 1.2)

    objs = [
        K.emit(C, col, "conc", "GEO-GTE-concrete", root),
        K.emit(Pn, col, "panel", "GEO-GTE-panel", root),
        K.emit(St, col, "steel", "GEO-GTE-steel", root),
        K.emit(Sd, col, "steel_dark", "GEO-GTE-dark", root),
        K.emit(Gl, col, "glass_green", "GEO-GTE-glass", root),
        K.emit(Gv, col, "galv", "GEO-GTE-markings", root),
        K.emit(Em, col, "em_white", "GEO-GTE-light", root),
        K.emit(EmC, col, "em_cyan", "GEO-GTE-systems", root),
        K.emit(Rd, col, "red", "GEO-GTE-arm", root),
        K.emit(Or, col, "orange", "GEO-GTE-hazard", root),
    ]
    K.sky()
    K.finish(objs, OUT, "GTE", extra={"house": [HW, HD, HH], "wall": [WL, WH]})


if __name__ == "__main__":
    main()
