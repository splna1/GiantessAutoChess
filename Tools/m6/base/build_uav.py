# -*- coding: utf-8 -*-
"""UAV — 无人机坪: VTOL pad with hex markings, launch shed with roof rails,
control cab, charging gantries, perimeter lighting and cable trenches.
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

P = S.MODS["UAV"]
OUT = os.path.join(K.ROOT, "model", "m6", "base", "M6_UAV_Pad.blend")

PW, PD, PH = P["pad"]
SW, SD, SHH = P["shed"]
CW, CD, CH = P["cab"]
CIRCLES = P["circles"]


def main():
    col, root = K.scene("UAV")

    C = K.MB("UAV-conc")
    Pn = K.MB("UAV-panel")
    St = K.MB("UAV-steel")
    Sd = K.MB("UAV-dark")
    Gl = K.MB("UAV-glass")
    Em = K.MB("UAV-light")
    EmC = K.MB("UAV-systems")
    Or = K.MB("UAV-hazard")
    Gv = K.MB("UAV-markings")

    # ---------------------------------------------------------- pad
    C.box(-PW / 2 - 1.6, -PD / 2 - 1.6, -0.30, PW / 2 + 1.6, PD / 2 + 1.6, 0.06)
    C.box(-PW / 2, -PD / 2, 0.06, PW / 2, PD / 2, PH)
    # chamfered pad skirt
    for sx in (-1, 1):
        for sy in (-1, 1):
            C.push(Matrix.Translation((sx * (PW / 2 - 1.0), sy * (PD / 2 - 1.0), PH)) @
                   Matrix.Rotation(math.radians(45 * sx * sy), 4, "Z"))
            C.box(0, -1.0, -0.20, 2.2, 0.0, 0.02)
            C.pop()
    # hex + circle markings
    Gv.ring_hex(10.0, z=PH + 0.004, tube=0.16)
    Gv.ring_hex(9.2, z=PH + 0.004, tube=0.08)
    for (cx, cy, r) in CIRCLES:
        Gv.ring_circle(r, z=PH + 0.004, tube=0.13)
        Gv.paint_line((cx - r + 0.5, cy), (cx + r - 0.5, cy), 0.12, z=PH + 0.006)
    Gv.paint_line((-PW / 2 + 1.0, 0.0), (PW / 2 - 1.0, 0.0), 0.10, z=PH + 0.006)
    # tie-downs
    for ix in (-1, 0, 1):
        for iy in (-1, 0, 1):
            Sd.lathe([(0.20, 0.0), (0.20, 0.05), (0.10, 0.05), (0.10, 0.0)],
                     ix * 11.0, iy * 8.0, seg=10)
    # cable trenches
    for x in (-6.0, 6.0):
        Sd.box(x - 0.35, -PD / 2 + 1.0, PH - 0.02, x + 0.35, PD / 2 - 1.0, PH + 0.01)
    # perimeter lights
    for i in range(8):
        t = i / 7.0
        x = -PW / 2 + 1.2 + t * (PW - 2.4)
        for sy in (-1, 1):
            EmC.cyl(x, sy * (PD / 2 - 0.9), PH, PH + 0.22, 0.11, seg=8)
    for i in range(5):
        y = -PD / 2 + 1.2 + i * (PD - 2.4) / 4.0
        for sx in (-1, 1):
            EmC.cyl(sx * (PW / 2 - 0.9), y, PH, PH + 0.22, 0.11, seg=8)

    # ---------------------------------------------------------- shed
    sy0 = PD / 2 - SD - 0.5
    Pn.box(-SW / 2, sy0, PH, SW / 2, sy0 + SD, SHH)
    St.box(-SW / 2 - 0.35, sy0 - 0.35, SHH, SW / 2 + 0.35, sy0 + SD + 0.2, SHH + 0.30)
    for i in range(3):
        x = -SW / 2 + 1.0 + i * (SW - 2.0) / 3.0
        Sd.push(Matrix.Translation((x, sy0 - 0.01, PH)))
        Sd.roller_door(4.0, 3.3, 12)
        Sd.pop()
        Or.box(x, sy0 - 0.06, PH + 3.3, x + 4.0, sy0 - 0.02, PH + 3.5)
    # roof launch rails
    for i in range(2):
        y = sy0 + 1.8 + i * 2.6
        St.box(-SW / 2 + 1.0, y - 0.20, SHH + 0.30, SW / 2 - 1.0, y + 0.20, SHH + 0.55)
        for k in range(4):
            x = -SW / 2 + 2.6 + k * 3.2
            Sd.box(x - 0.42, y - 0.55, SHH + 0.55, x + 0.42, y + 0.55, SHH + 1.25)
            EmC.box(x - 0.20, y - 0.58, SHH + 0.75, x + 0.20, y + 0.58, SHH + 0.80)
    # roof plant
    Sd.push(Matrix.Translation((SW / 2 - 2.4, sy0 + 2.0, SHH + 0.30)))
    Sd.ac_unit(1.7, 0.95, 1.15)
    Sd.pop()
    Sd.whip(3.6, 0.05, z0=SHH + 0.30)
    Em.box(-1.6, sy0 - 0.10, SHH - 0.10, 1.6, sy0 - 0.03, SHH - 0.02)

    # ---------------------------------------------------------- control cab
    cx0 = -PW / 2 - 1.2 - CW
    C.box(cx0 - 0.4, -CD / 2 - 0.4, 0.0, cx0 + CW + 0.4, CD / 2 + 0.4, 0.30)
    Pn.box(cx0, -CD / 2, 0.30, cx0 + CW, CD / 2, CH)
    St.box(cx0 - 0.30, -CD / 2 - 0.30, CH, cx0 + CW + 0.30, CD / 2 + 0.30, CH + 0.28)
    Gl.box(cx0 + 0.4, -CD / 2 - 0.08, 1.10, cx0 + CW - 0.4, -CD / 2 + 0.02, 2.55)
    St.box(cx0 + 0.25, -CD / 2 - 0.20, 1.00, cx0 + CW - 0.25, -CD / 2 + 0.05, 2.68)
    for i in range(3):
        x = cx0 + 1.0 + i * (CW - 2.0) / 2.0
        St.box(x - 0.06, -CD / 2 - 0.24, 1.02, x + 0.06, -CD / 2 - 0.10, 2.66)
    Sd.box(cx0 + CW - 1.1, CD - CD / 2 - 0.02, 0.30, cx0 + CW - 0.2, CD / 2 + 0.04, 2.30)
    EmC.box(cx0 + 1.2, -CD / 2 - 0.12, 2.58, cx0 + CW - 1.2, -CD / 2 - 0.06, 2.70)
    # mast + dish on the cab roof
    St.box(cx0 + 1.0, -1.2, CH + 0.28, cx0 + 1.5, -0.7, CH + 3.6)
    St.push(Matrix.Translation((cx0 + 1.25, -0.95, CH + 3.0)) @
            Matrix.Rotation(math.radians(-64), 4, "X"))
    St.dish(0.75, 0.24, seg=16, rings=4)
    St.pop()
    for i in range(2):
        Sd.push(Matrix.Translation((cx0 + 3.0, -0.5 + i * 1.4, CH + 0.28)))
        Sd.ac_unit(1.2, 0.8, 0.9)
        Sd.pop()

    # ---------------------------------------------------------- charging gantries
    for i in range(P["gantries"]):
        x = -9.0 + i * 9.0
        y = -PD / 2 + 4.0
        for sx in (-1, 1):
            St.box(x + sx * 2.3 - 0.12, y - 0.12, PH, x + sx * 2.3 + 0.12, y + 0.12, PH + 3.4)
        St.box(x - 2.42, y - 0.18, PH + 3.4, x + 2.42, y + 0.18, PH + 3.75)
        Sd.box(x - 0.55, y - 0.22, PH + 3.05, x + 0.55, y + 0.22, PH + 3.40)
        EmC.box(x - 0.42, y - 0.25, PH + 3.12, x + 0.42, y + 0.25, PH + 3.20)
        Sd.tube([(x + 2.3, y, PH + 3.4), (x + 2.3, y + 1.6, PH + 2.2),
                 (x + 2.3, y + 2.2, PH + 0.4)], 0.05, seg=6)

    # ---------------------------------------------------------- ground kit
    # drone rack outside the shed
    for r in range(2):
        for c in range(4):
            x = -5.0 + c * 1.25
            y = sy0 - 2.6 - r * 1.2
            Sd.box(x - 0.5, y - 0.45, PH, x + 0.5, y + 0.45, PH + 0.75)
            EmC.box(x - 0.3, y - 0.48, PH + 0.55, x + 0.3, y + 0.48, PH + 0.60)
    # windsock
    St.lathe([(0.09, PH), (0.06, PH + 5.0)], PW / 2 - 3.0, -PD / 2 + 3.0, seg=8)
    Or.lathe([(0.42, PH + 5.0), (0.30, PH + 5.6), (0.26, PH + 6.2)], PW / 2 - 3.0,
             -PD / 2 + 3.0, seg=10)
    # cable reels + crates near the cab
    Sd.push(Matrix.Translation((cx0 + CW + 1.6, 3.0, PH)) @ Matrix.Rotation(math.radians(90), 4, "Y"))
    Sd.lathe([(0.9, -0.35), (0.9, 0.35)], 0, 0, seg=16)
    Sd.pop()
    for i in range(2):
        Sd.push(Matrix.Translation((cx0 + CW + 1.2 + i * 1.4, -2.0, PH)))
        Sd.crate(1.1, 0.9, 0.8)
        Sd.pop()

    objs = [
        K.emit(C, col, "conc", "GEO-UAV-concrete", root),
        K.emit(Pn, col, "panel", "GEO-UAV-panel", root),
        K.emit(St, col, "steel", "GEO-UAV-steel", root),
        K.emit(Sd, col, "steel_dark", "GEO-UAV-dark", root),
        K.emit(Gl, col, "glass_green", "GEO-UAV-glass", root),
        K.emit(Gv, col, "galv", "GEO-UAV-markings", root),
        K.emit(Em, col, "em_white", "GEO-UAV-light", root),
        K.emit(EmC, col, "em_cyan", "GEO-UAV-systems", root),
        K.emit(Or, col, "orange", "GEO-UAV-hazard", root),
    ]
    K.sky()
    K.finish(objs, OUT, "UAV", extra={"pad": [PW, PD], "circles": len(CIRCLES)})


if __name__ == "__main__":
    main()
