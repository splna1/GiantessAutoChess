# -*- coding: utf-8 -*-
"""BRK — 兵营: four-storey troop block on an arcade, ribbon glazing with
sunshades, external stair tower, roof solar array + plant, container annex.
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

P = S.MODS["BRK"]
OUT = os.path.join(K.ROOT, "model", "m6", "base", "M6_BRK_Barracks.blend")

BX, BY = P["body"]
HX, HY = BX / 2.0, BY / 2.0
N = P["storeys"]
SH = P["storey_h"]
Z0 = 0.35
G = 3.9
LV = [Z0 + G + i * SH for i in range(N)]          # 3.9 / 7.05 / 10.20 / 13.35
TOP = LV[-1]
PAR = TOP + P["parapet"]
STX, STY, STH = P["stair"]
ARC = P["arcade"]


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
    col, root = K.scene("BRK")

    C = K.MB("BRK-conc")
    Pn = K.MB("BRK-panel")
    St = K.MB("BRK-steel")
    Sd = K.MB("BRK-dark")
    Gl = K.MB("BRK-glass")
    Em = K.MB("BRK-light")
    EmC = K.MB("BRK-systems")
    Or = K.MB("BRK-hazard")
    So = K.MB("BRK-solar")
    Gv = K.MB("BRK-galv")

    # ---------------------------------------------------------- plinth + arcade
    C.box(-HX - 2.2, -HY - 2.6, -0.30, HX + 2.2, HY + 1.0, Z0)
    C.box(-HX, -HY + ARC, Z0, HX, HY, G)                        # recessed ground wall
    for i in range(11):
        x = -HX + 1.2 + i * (BX - 2.4) / 10.0
        C.box(x - 0.30, -HY, Z0, x + 0.30, -HY + 0.55, G)
    St.box(-HX - 0.4, -HY - 0.4, G - 0.35, HX + 0.4, -HY + ARC, G + 0.10)   # arcade slab
    for i in range(10):
        x = -HX + 1.2 + i * (BX - 2.4) / 10.0
        Sd.box(x - 0.9, -HY + 0.05, Z0 + 0.35, x + 0.9, -HY + 0.40, G - 0.55)
        Gl.box(x - 0.82, -HY + 0.02, Z0 + 0.42, x + 0.82, -HY + 0.10, G - 0.62)
    # ground-floor doors under the arcade
    for x in (-13.0, -3.0, 7.0, 15.0):
        Sd.push(Matrix.Translation((x, -HY + ARC - 0.02, Z0)))
        Sd.roller_door(2.2, 2.5, 8)
        Sd.pop()
    # arcade strip lights
    for i in range(6):
        x = -HX + 3.4 + i * 6.6
        Em.box(x - 1.0, -HY + 1.4, G - 0.42, x + 1.0, -HY + 1.8, G - 0.36)

    # ---------------------------------------------------------- upper mass
    Pn.box(-HX, -HY, G, HX, HY, TOP)
    # floor bands
    for z in LV[:-1]:
        St.box(-HX - 0.18, -HY - 0.18, z - 0.12, HX + 0.18, HY + 0.18, z + 0.10)
    # roof slab + parapet
    St.box(-HX - 0.35, -HY - 0.35, TOP - 0.15, HX + 0.35, HY + 0.35, TOP + 0.18)
    for (x0, y0, x1, y1) in ((-HX - 0.35, -HY - 0.35, HX + 0.35, -HY + 0.10),
                             (-HX - 0.35, HY - 0.10, HX + 0.35, HY + 0.35),
                             (-HX - 0.35, -HY - 0.35, -HX + 0.10, HY + 0.35),
                             (HX - 0.10, -HY - 0.35, HX + 0.35, HY + 0.35)):
        St.box(x0, y0, TOP + 0.18, x1, y1, PAR)

    # ribbon windows + sunshades + spandrel panels
    for k, z in enumerate(LV[:-1]):
        for side in (0, 1, 3):
            span = BX if side == 0 else BY
            nb = 9 if side == 0 else 3
            ww = (span - 3.0) / nb
            face(Gl, side, 0.0, z + 0.95, HX, HY)
            Gl.box(-span / 2 + 1.5, -0.06, 0.0, span / 2 - 1.5, 0.02, 1.55)
            Gl.pop()
            face(St, side, 0.0, z + 0.95, HX, HY)
            St.window_band(span - 3.0, 1.55, nb, z0=0.0, mull=0.10, head=0.12, sill=0.10)
            St.pop()
            # sunshade fins above each window bay
            face(St, side, 0.0, z + 2.55, HX, HY)
            for i in range(nb):
                x = -span / 2 + 1.5 + (i + 0.5) * ww
                St.box(x - ww * 0.46, -0.95, -0.06, x + ww * 0.46, 0.0, 0.06)
            St.pop()
            # spandrel field under each window
            face(Pn, side, 0.0, z - 0.10, HX, HY)
            Pn.panel_grid(span - 3.0, 0.95, nb * 2, 1, gap=0.05, thick=0.06)
            Pn.pop()

    # ---------------------------------------------------------- stair tower
    sx0, sx1 = -HX - STX + 1.0, -HX + 1.0
    C.box(sx0, -HY - STY + 0.4, Z0, sx1, -HY + 0.4, STH)
    St.box(sx0 - 0.2, -HY - STY + 0.2, STH, sx1 + 0.2, -HY + 0.6, STH + 0.35)
    for k in range(4):
        z = Z0 + 1.0 + k * 3.1
        Gl.box(sx1 - 0.04, -HY - STY + 1.0, z, sx1 + 0.02, -HY + 0.0, z + 2.3)
        St.box(sx1 + 0.02, -HY - STY + 0.9, z - 0.12, sx1 + 0.10, -HY + 0.1, z + 2.45)
    Sd.box(sx1 - 0.6, -HY - STY - 0.05, Z0, sx1 - 0.1, -HY - STY + 0.30, Z0 + 2.4)
    Or.box(sx1 - 0.8, -HY - STY - 0.10, Z0 + 2.4, sx1 + 0.1, -HY - STY + 0.32, Z0 + 2.55)
    St.push(Matrix.Translation((sx0 - 0.15, -HY - STY + 0.9, Z0)) @
            Matrix.Rotation(math.radians(-90), 4, "Z"))
    St.ladder(STH - Z0 - 0.4)
    St.pop()
    Sd.box(sx1 - 2.6, -HY - STY - 0.10, STH + 0.35, sx1 - 1.2, -HY - STY + 0.05, STH + 0.80)

    # ---------------------------------------------------------- roof plant
    # solar array, tilted toward the south
    SX, SY = P["solar"]
    for row in range(3):
        y = -HY + 1.8 + row * 2.4
        So.push(Matrix.Translation((0.0, y, TOP + 0.85)) @
                Matrix.Rotation(math.radians(22), 4, "X"))
        So.solar_panel(SX, SY / 3.0)
        So.pop()
        St.box(-SX / 2, y - 0.06, TOP + 0.18, SX / 2, y + 0.06, TOP + 0.9)
    # condensers + extractors + stair head
    for x, y in ((10.0, -4.6), (12.6, -4.6), (10.0, 2.4), (12.6, 2.4)):
        Sd.push(Matrix.Translation((x, y, TOP + 0.18)))
        Sd.ac_unit(1.7, 0.95, 1.15)
        Sd.pop()
    for x in (-6.0, 0.0, 6.0):
        Sd.push(Matrix.Translation((x, 4.4, TOP + 0.18)))
        Sd.extractor(0.55, 1.05)
        Sd.pop()
    St.box(15.6, 2.6, TOP + 0.18, 19.0, 5.2, TOP + 2.6)
    Sd.box(15.8, 2.8, TOP + 2.6, 18.8, 5.0, TOP + 2.68)
    Sd.whip(4.5, 0.05, z0=TOP + 2.68)
    # roof railing on the front edge
    St.push(Matrix.Translation((-HX, -HY - 0.3, TOP + 0.18)))
    St.railing(BX, h=1.05)
    St.pop()

    # ---------------------------------------------------------- container annex
    for i in range(2):
        Sd.push(Matrix.Translation((HX + 2.2 + i * 2.55, 0.0, Z0)) @
                Matrix.Rotation(math.radians(90), 4, "Z"))
        Sd.container(6.06, 2.44, 2.60, ribs=18)
        Sd.pop()
    Sd.push(Matrix.Translation((HX + 3.5, 0.0, Z0 + 2.60)) @
            Matrix.Rotation(math.radians(90), 4, "Z"))
    Sd.container(6.06, 2.44, 2.60, ribs=18)
    Sd.pop()
    # cable bridge from containers into the block
    Sd.cable_tray([(HX + 2.2, 0.0, Z0 + 2.9), (HX + 0.6, 0.0, Z0 + 2.9),
                   (HX + 0.6, 0.0, G + 1.2), (HX - 0.1, 0.0, G + 1.2)], 0.30, 0.12)

    # ---------------------------------------------------------- services
    for sx in (-1, 1):
        Sd.pipe_run([(sx * (HX - 0.6), -HY - 0.2, TOP - 0.3),
                     (sx * (HX - 0.6), -HY - 0.2, Z0 + 0.6),
                     (sx * (HX - 0.3), -HY - 0.05, Z0 + 0.2)], 0.08)
    # entry sign + unit board
    Sd.box(-2.6, -HY - 0.14, G + 0.55, 2.6, -HY - 0.06, G + 0.95)
    EmC.box(-2.4, -HY - 0.17, G + 0.62, 2.4, -HY - 0.13, G + 0.86)
    # bike / gear racks along the plinth
    for i in range(6):
        St.box(-HX + 4.0 + i * 1.4, -HY - 1.3, Z0, -HX + 4.15 + i * 1.4, -HY - 0.5, Z0 + 0.75)
    # flag mast at the forecourt
    St.lathe([(0.10, 0.0), (0.06, 7.5)], -HX + 2.0, -HY - 3.2, seg=10)
    Gv.box(-HX + 2.1, -HY - 3.2, 7.0, -HX + 3.7, -HY - 3.15, 7.9)
    Or.box(-HX + 2.1, -HY - 3.22, 7.5, -HX + 2.6, -HY - 3.18, 7.9)

    objs = [
        K.emit(C, col, "conc", "GEO-BRK-concrete", root),
        K.emit(Pn, col, "panel", "GEO-BRK-cladding", root),
        K.emit(St, col, "steel", "GEO-BRK-steel", root),
        K.emit(Sd, col, "steel_dark", "GEO-BRK-dark", root),
        K.emit(Gl, col, "glass_green", "GEO-BRK-glass", root),
        K.emit(So, col, "solar", "GEO-BRK-solar", root),
        K.emit(Em, col, "em_white", "GEO-BRK-light", root),
        K.emit(EmC, col, "em_cyan", "GEO-BRK-systems", root),
        K.emit(Or, col, "orange", "GEO-BRK-hazard", root),
        K.emit(Gv, col, "galv", "GEO-BRK-markings", root),
    ]
    K.sky()
    K.finish(objs, OUT, "BRK", extra={"storeys": N, "levels": [round(v, 2) for v in LV]})


if __name__ == "__main__":
    main()
