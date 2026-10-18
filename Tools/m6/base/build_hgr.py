# -*- coding: utf-8 -*-
"""HGR — 机库 / 维修坞: clear-span hangar, sliding door bank, gantry crane,
apron with markings, fuel farm and a maintenance annex.
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

P = S.MODS["HGR"]
OUT = os.path.join(K.ROOT, "model", "m6", "base", "M6_HGR_Hangar.blend")

BX, BY = P["body"]
HX, HY = BX / 2.0, BY / 2.0
EAVE, RIDGE = P["eave"], P["ridge"]
DW, DH = P["door"]
AX, AY, AH = P["annex"]
APX, APY, APH = P["apron"]


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
    col, root = K.scene("HGR")

    C = K.MB("HGR-slab")        # concrete
    St = K.MB("HGR-steel")      # painted steel structure
    Sd = K.MB("HGR-dark")       # dark steel, doors, interior
    Pn = K.MB("HGR-panel")      # cladding panels
    Gl = K.MB("HGR-glass")
    Em = K.MB("HGR-light")
    EmC = K.MB("HGR-systems")
    Or = K.MB("HGR-hazard")
    Gv = K.MB("HGR-galv")
    Rd = K.MB("HGR-radome")

    # ---------------------------------------------------------- slab + apron
    C.box(-HX - 1.0, -HY - 1.2, -0.35, HX + 8.0, HY + 1.2, 0.22)
    C.box(-APX / 2, -HY - 0.4 - APY, 0.0, APX / 2, -HY - 0.4, APH)
    # apron markings: centreline, door threshold, parking box
    for x in (-11.0, 11.0):
        Gv.paint_line((x, -HY - 1.0), (x, -HY - 0.4 - APY + 2.0), 0.20, z=APH + 0.006)
    Gv.paint_line((-13.5, -HY - 2.4), (13.5, -HY - 2.4), 0.30, z=APH + 0.006)
    for i in range(7):
        Gv.paint_line((-14.0, -HY - 5.0 - i * 4.6), (-6.2, -HY - 5.0 - i * 4.6), 0.12, z=APH + 0.006)
        Gv.paint_line((6.2, -HY - 5.0 - i * 4.6), (14.0, -HY - 5.0 - i * 4.6), 0.12, z=APH + 0.006)
    Gv.arrow_marking(4.0, 1.9, z=APH + 0.006)
    # tie-down rings + bollards
    for ix in range(-2, 3):
        for iy in range(-1, 4):
            Sd.lathe([(0.22, 0.0), (0.22, 0.06), (0.12, 0.06), (0.12, 0.0)],
                     ix * 9.0, -HY - 8.0 - iy * 8.0, seg=10)
    for i in range(6):
        Sd.push(Matrix.Translation((-15.0 + i * 6.0, -HY - 1.4, APH)))
        Sd.bollard(0.12, 0.95)
        Sd.pop()

    # ---------------------------------------------------------- walls
    # wainscot
    C.box(-HX - 0.12, -HY - 0.10, 0.22, HX + 0.12, HY + 0.10, 1.35)
    # north wall (solid)
    Pn.box(-HX, HY - 0.30, 0.22, HX, HY, EAVE)
    # east / west walls
    for sx in (-1, 1):
        x0, x1 = sorted((sx * HX, sx * (HX - 0.30)))
        Pn.box(x0, -HY, 0.22, x1, HY, EAVE)
    # south wall with the door opening
    left, right = -DW / 2.0, DW / 2.0
    Pn.box(-HX, -HY, 0.22, left, -HY + 0.30, EAVE)
    Pn.box(right, -HY, 0.22, HX, -HY + 0.30, EAVE)
    Pn.box(left, -HY, DH, right, -HY + 0.30, EAVE)
    St.box(-HX - 0.15, -HY - 0.16, EAVE - 0.55, HX + 0.15, -HY + 0.32, EAVE)
    # vertical ribs on the three clad walls
    Pn.push(Matrix.Translation((0, HY, 0)) @ Matrix.Rotation(math.pi, 4, "Z"))
    Pn.rib_wall(BX, EAVE - 1.35, 38, z0=1.35, thick=0.10, depth=0.07)
    Pn.pop()
    for sx in (-1, 1):
        Pn.push(Matrix.Translation((sx * HX, 0, 0)) @
                Matrix.Rotation(math.radians(90 * sx), 4, "Z"))
        Pn.rib_wall(BY, EAVE - 1.35, 27, z0=1.35, thick=0.10, depth=0.07)
        Pn.pop()
    for sx in (-1, 1):
        Pn.push(Matrix.Translation((sx * (HX - 0.16), -HY, 0)))
        Pn.pop()

    # ---------------------------------------------------------- roof
    rise = RIDGE - EAVE
    slope = math.hypot(HY, rise)
    ang = math.degrees(math.atan2(rise, HY))
    for sy in (-1, 1):
        Pn.push(Matrix.Translation((0, sy * HY / 2.0, EAVE + rise / 2.0 + 0.18)) @
                Matrix.Rotation(math.radians(-ang * sy), 4, "X"))
        Pn.box(-HX - 0.25, -slope / 2.0, -0.18, HX + 0.25, slope / 2.0, 0.18)
        Pn.pop()
    St.box(-HX - 0.3, -0.35, RIDGE - 0.10, HX + 0.3, 0.35, RIDGE + 0.22)
    # gable ends
    for sx in (-1, 1):
        x0, x1 = sorted((sx * HX, sx * (HX - 0.32)))
        Pn.prism_x([(-HY, EAVE), (HY, EAVE), (0.0, RIDGE)], x0, x1)
    # skylight strips on the north slope
    for k in range(3):
        x = -14.0 + k * 14.0
        St.push(Matrix.Translation((x, HY / 2.0, EAVE + rise / 2.0 + 0.42)) @
                Matrix.Rotation(math.radians(ang), 4, "X"))
        Gl.box(-4.6, -slope / 2.0 + 3.2, -0.06, 4.6, slope / 2.0 - 6.0, 0.06)
        St.pop()
    # extractors along the ridge
    for i in range(P["extractors"]):
        x = -18.0 + i * 7.2
        Sd.push(Matrix.Translation((x, 0.0, RIDGE + 0.15)))
        Sd.extractor(0.72, 1.30)
        Sd.pop()
    # roof access + cable trays
    St.box(16.0, 4.0, RIDGE - 1.1, 19.0, 8.5, RIDGE + 0.6)
    Sd.box(16.2, 4.2, RIDGE + 0.6, 18.8, 8.3, RIDGE + 0.68)
    for sy in (-1, 1):
        Sd.cable_tray([(-HX + 1.0, sy * 3.0, RIDGE - 1.4), (HX - 1.0, sy * 3.0, RIDGE - 1.4)],
                      0.30, 0.12)

    # ---------------------------------------------------------- door bank
    leaves = P["leaves"]
    lw = DW / leaves
    # leaves 1 and 4 closed at the jambs, the middle open
    for k in (0, 1):
        x0 = left + k * lw
        Sd.box(x0 + 0.04, -HY - 0.20, 0.22, x0 + lw - 0.04, -HY - 0.06, DH - 0.10)
        for j in range(14):
            z = 0.30 + j * (DH - 0.4) / 14.0
            Sd.box(x0 + 0.10, -HY - 0.25, z, x0 + lw - 0.10, -HY - 0.20, z + 0.09)
        Sd.box(x0 + lw / 2 - 0.05, -HY - 0.28, 1.2, x0 + lw / 2 + 0.05, -HY - 0.24, 3.2)
    for k in (2, 3):
        x0 = left + (k - 2) * lw            # stacked onto the closed pair
        Sd.box(x0 + 0.05, -HY - 0.13, 0.22, x0 + lw - 0.05, -HY + 0.01, DH - 0.10)
        for j in range(14):
            z = 0.30 + j * (DH - 0.4) / 14.0
            Sd.box(x0 + 0.11, -HY - 0.18, z, x0 + lw - 0.11, -HY - 0.13, z + 0.09)
    # head beam + track + warning stripes
    St.box(-DW / 2 - 0.7, -HY - 0.45, DH, DW / 2 + 0.7, -HY - 0.02, DH + 0.55)
    St.box(-DW / 2 - 0.7, -HY - 0.30, DH + 0.55, DW / 2 + 0.7, -HY - 0.10, DH + 0.95)
    for x in (-DW / 2 - 0.35, DW / 2 + 0.35):
        Sd.box(x - 0.16, -HY - 0.55, 0.22, x + 0.16, -HY - 0.02, DH + 0.55)
    for sx in (-1, 1):
        Or.push(Matrix.Translation((sx * (DW / 2 + 0.10), -HY - 0.06, 0.30)) @
                Matrix.Rotation(math.radians(90), 4, "Z"))
        Or.hazard(1.2, 0.42, 5)
        Or.pop()
    Em.box(-DW / 2 + 1.0, -HY - 0.42, DH - 0.06, DW / 2 - 1.0, -HY - 0.36, DH + 0.02)
    # personnel door + signage on the south wall
    Sd.box(HX - 6.2, -HY - 0.20, 0.22, HX - 4.6, -HY - 0.04, 2.35)
    Sd.box(HX - 6.3, -HY - 0.28, 2.35, HX - 4.5, -HY - 0.02, 2.55)
    Em.box(HX - 6.0, -HY - 0.26, 2.42, HX - 4.8, -HY - 0.22, 2.50)
    Sd.box(-HX + 3.0, -HY - 0.16, 7.0, -HX + 9.0, -HY - 0.10, 7.9)

    # ---------------------------------------------------------- interior
    St.box(-HX + 1.0, -HY + 1.2, 0.24, HX - 1.0, HY - 1.2, 0.30)          # floor slab
    for sy in (-1, 1):
        y = sy * (HY - 3.2)
        St.box(-HX + 1.4, y - 0.22, 12.30, HX - 1.4, y + 0.22, 12.65)      # crane rails
    St.box(-0.9, -HY + 3.0, 12.55, 0.9, HY - 3.0, 13.35)                   # bridge
    for sy in (-1, 1):
        St.box(-1.1, sy * (HY - 3.4) - 0.30, 12.45, 1.1, sy * (HY - 3.4) + 0.30, 13.45)
    Sd.box(-0.55, -1.2, 10.9, 0.55, 1.2, 12.55)                            # hoist
    Sd.tube([(0.0, 0.0, 12.55), (0.0, 0.0, 9.6)], 0.05, seg=6)
    Sd.box(-0.45, -0.45, 9.35, 0.45, 0.45, 9.6)
    for x in (-14.0, 14.0):
        Em.box(x - 0.35, -HY + 2.0, 11.9, x + 0.35, HY - 2.0, 12.0)
    # interior work benches / racks along the north wall
    for i in range(5):
        x = -16.0 + i * 8.0
        Sd.box(x - 1.6, HY - 2.6, 0.30, x + 1.6, HY - 1.6, 1.45)
    EmC.box(-2.2, -HY + 0.7, 6.8, 2.2, -HY + 0.74, 7.4)
    Pn.box(-HX + 0.6, HY - 0.55, 0.30, HX - 0.6, HY - 0.30, 9.5)
    for i in range(5):
        Em.box(-HX + 4.0 + i * 8.0, HY - 0.62, 8.6, -HX + 8.0 + i * 8.0, HY - 0.55, 9.1)
    Gv.paint_line((-DW / 2 + 2.0, -HY + 1.0), (-DW / 2 + 2.0, HY - 3.0), 0.18, z=0.34)
    Gv.paint_line((DW / 2 - 2.0, -HY + 1.0), (DW / 2 - 2.0, HY - 3.0), 0.18, z=0.34)

    # ---------------------------------------------------------- annex
    Cd0, Cd1 = HX + 1.2, HX + 1.2 + AX
    C.box(Cd0, -AY, 0.0, Cd1, AY, 0.20)
    St.box(Cd0, -AY, 0.20, Cd1, AY, AH)
    St.box(Cd0 - 0.25, -AY - 0.25, AH - 0.10, Cd1 + 0.25, AY + 0.25, AH + 0.22)
    for i in range(5):
        Sd.push(Matrix.Translation((Cd1, -AY + 1.4 + i * 2.6, 3.6)) @
                Matrix.Rotation(math.radians(90), 4, "Z"))
        Sd.louver(1.5, 0.9, 5)
        Sd.pop()
    Sd.push(Matrix.Translation((Cd0 + 2.0, -AY - 0.02, 0.20)))
    Sd.roller_door(4.2, 3.6, 12)
    Sd.pop()
    for y in (-5.0, 5.0):
        Sd.push(Matrix.Translation((Cd1 - 2.0, y, AH + 0.22)))
        Sd.ac_unit(1.7, 0.95, 1.15)
        Sd.pop()
    Sd.vent_cap(0.34, 0.7, z0=AH + 0.22)

    # ---------------------------------------------------------- fuel farm
    FF = P["fuel_farm"]
    fx, fy = FF["at"]
    C.box(fx - 6.4, fy - 5.4, 0.0, fx + 6.4, fy + 5.4, 0.35)
    for sx in (-1, 1):
        C.box(fx + sx * 6.1 - 0.25, fy - 5.4, 0.35, fx + sx * 6.1 + 0.25, fy + 5.4, 1.30)
    C.box(fx - 6.4, fy - 5.65, 0.35, fx + 6.4, fy - 5.15, 1.30)
    for i in range(FF["tanks"]):
        tx = fx - 2.6 + i * 5.2
        Sd.lathe([(FF["r"], 0.35), (FF["r"], FF["h"]), (FF["r"] * 0.82, FF["h"] + 0.35),
                  (0.0, FF["h"] + 0.55)], tx, fy, seg=24)
        for zz in (1.2, 3.0, 4.8):
            Sd.lathe([(FF["r"] * 1.03, zz), (FF["r"] * 1.03, zz + 0.10)], tx, fy, seg=24)
        Sd.lathe([(0.18, 0.35), (0.18, FF["h"] + 1.2)], tx + 2.2, fy, seg=8)
        Or.box(tx - 2.2, fy - 5.5, 0.42, tx + 2.2, fy - 5.44, 1.24)
    Sd.pipe_run([(fx - 2.6, fy + 1.2, FF["h"] - 0.4), (fx + 2.6, fy + 1.2, FF["h"] - 0.4),
                 (fx + 2.6, fy + 4.6, FF["h"] - 0.4), (fx + 2.6, fy + 4.6, 0.6)], 0.14)
    St.box(fx - 1.2, fy + 3.4, 0.35, fx + 1.2, fy + 4.4, 1.05)

    # ---------------------------------------------------------- extras
    # floodlight masts on the apron
    for (mx, my) in ((-APX / 2 + 4.0, -HY - APY + 5.0), (APX / 2 - 4.0, -HY - APY + 5.0)):
        St.lathe([(0.22, 0.0), (0.15, 13.0)], mx, my, seg=12)
        St.box(mx - 0.7, my - 0.22, 13.0, mx + 0.7, my + 0.22, 13.25)
        for sx in (-1, 1):
            Sd.box(mx + sx * 0.48 - 0.26, my - 0.34, 13.1, mx + sx * 0.48 + 0.26, my + 0.02, 13.55)
            Em.box(mx + sx * 0.48 - 0.22, my - 0.37, 13.2, mx + sx * 0.48 + 0.22, my - 0.31, 13.45)
    # jersey barriers + cable reel at the apron edge
    for i in range(4):
        C.push(Matrix.Translation((-10.0 + i * 3.2, -HY - APY + 3.0, APH)) @
               Matrix.Rotation(math.radians(90), 4, "Z"))
        C.jersey(3.0, 1.02, 0.60)
        C.pop()
    Sd.push(Matrix.Translation((APX / 2 - 6.0, -HY - 12.0, APH)) @
            Matrix.Rotation(math.radians(90), 4, "Y"))
    Sd.lathe([(1.05, -0.45), (1.05, 0.45)], 0, 0, seg=18)
    Sd.pop()
    # antenna + radome for EW
    Rd.lathe([(0.0, AH + 0.22), (0.75, AH + 0.45), (1.05, AH + 1.15),
              (0.0, AH + 1.75)], Cd0 + 2.4, AY - 1.8, seg=20)
    Sd.whip(5.0, 0.05, z0=AH + 0.22)

    objs = [
        K.emit(C, col, "conc", "GEO-HGR-concrete", root),
        K.emit(St, col, "steel", "GEO-HGR-structure", root),
        K.emit(Pn, col, "panel", "GEO-HGR-cladding", root),
        K.emit(Sd, col, "steel_dark", "GEO-HGR-dark", root),
        K.emit(Gl, col, "glass_green", "GEO-HGR-glass", root),
        K.emit(Gv, col, "galv", "GEO-HGR-markings", root),
        K.emit(Em, col, "em_white", "GEO-HGR-light", root),
        K.emit(EmC, col, "em_cyan", "GEO-HGR-systems", root),
        K.emit(Or, col, "orange", "GEO-HGR-hazard", root),
        K.emit(Rd, col, "radome", "GEO-HGR-radome", root, smooth=True),
    ]
    K.sky()
    K.finish(objs, OUT, "HGR", extra={"door": [DW, DH], "eave": EAVE, "ridge": RIDGE})


if __name__ == "__main__":
    main()
