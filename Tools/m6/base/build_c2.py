# -*- coding: utf-8 -*-
"""C2 — 指挥中心 / command & control block.

Hardened podium + three upper storeys in a chamfered slab, a 360-degree glass
operations deck on the top floor, roof plant deck, 18 m lattice mast with a
radar / EW suite, blast shields on grade and a recessed entry with a canopy.
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

P = S.MODS["C2"]
OUT = os.path.join(K.ROOT, "model", "m6", "base", "M6_C2_Command.blend")

PLX, PLY, PLH = P["plinth"]
BX, BY = P["body"]
HX, HY = BX / 2.0, BY / 2.0
Z0 = PLH
POD = Z0 + P["podium_h"]
F1 = POD + P["floors"][0]
F2 = F1 + P["floors"][1]
F3 = F2 + P["floors"][2]
DECK = F3 + P["deck"][2]
UX, UY = 11.2, 7.4
AX, AY, AH = P["annex"]
AX0, AX1 = -PLX / 2.0, -PLX / 2.0 + AX
AY0, AY1 = -AY / 2.0, AY / 2.0


def face(mb, side, lat, z, hx, hy):
    """Push a detail frame on one face of a box body; local -Y is outward."""
    if side == 0:
        mb.at(lat, -hy, z)
    elif side == 1:
        mb.at(hx, lat, z, 90.0)
    elif side == 2:
        mb.at(-lat, hy, z, 180.0)
    else:
        mb.at(-hx, lat, z, -90.0)


def chamfer_poly(hx, hy, c):
    return [(-hx + c, -hy), (hx - c, -hy), (hx, -hy + c), (hx, hy - c),
            (hx - c, hy), (-hx + c, hy), (-hx, hy - c), (-hx, -hy + c)]


def lattice_mast(St, Sd, Am, x, y, z0, h=18.0, w0=1.15, w1=0.44, bays=6):
    """Square lattice mast: legs, X-bracing, mid platform, dish, AESA, whips."""
    corners = ((-1, -1), (1, -1), (1, 1), (-1, 1))
    for i in range(bays):
        t0, t1 = i / float(bays), (i + 1) / float(bays)
        a0, a1 = w0 + (w1 - w0) * t0, w0 + (w1 - w0) * t1
        za, zb = z0 + h * t0, z0 + h * t1
        for (sx, sy) in corners:
            St.tube([(x + sx * a0 / 2, y + sy * a0 / 2, za),
                     (x + sx * a1 / 2, y + sy * a1 / 2, zb)], 0.055, seg=6)
        for k in range(4):
            (sx0, sy0) = corners[k]
            (sx1, sy1) = corners[(k + 1) % 4]
            p0 = (x + sx0 * a0 / 2, y + sy0 * a0 / 2, za)
            p1 = (x + sx1 * a0 / 2, y + sy1 * a0 / 2, za)
            q0 = (x + sx1 * a1 / 2, y + sy1 * a1 / 2, zb)
            q1 = (x + sx0 * a1 / 2, y + sy0 * a1 / 2, zb)
            St.tube([p0, q0], 0.028, seg=4)
            St.tube([p1, q1], 0.028, seg=4)
            St.tube([p0, p1], 0.026, seg=4)
    # platform at 55 %
    zp = z0 + h * 0.55
    wp = (w0 + (w1 - w0) * 0.55) + 1.9
    St.box(x - wp / 2, y - wp / 2, zp, x + wp / 2, y + wp / 2, zp + 0.10)
    for (dx, dy, ang) in ((-wp / 2, -wp / 2, 0.0), (-wp / 2, wp / 2, 0.0),
                          (wp / 2, -wp / 2, 90.0), (wp / 2, wp / 2, 90.0)):
        St.push(Matrix.Translation((x + dx, y + dy, zp + 0.10)) @
                Matrix.Rotation(math.radians(ang), 4, "Z"))
        St.railing(wp, h=1.05)
        St.pop()
    # parabolic dish on the south face at 72 %
    zd = z0 + h * 0.72
    St.push(Matrix.Translation((x, y - 0.45, zd)) @ Matrix.Rotation(math.radians(-68), 4, "X"))
    St.dish(1.35, 0.42, seg=20, rings=5)
    St.pop()
    St.tube([(x, y - 0.40, zd), (x, y - 1.05, zd + 0.55)], 0.05, seg=6)
    # AESA face near the top, canted
    Sd.push(Matrix.Translation((x - 0.05, y - 0.26, z0 + h * 0.90)) @
            Matrix.Rotation(math.radians(14), 4, "X"))
    Sd.aesa_panel(2.30, 1.70, 7, 5)
    Sd.pop()
    Sd.whip(4.2, 0.032, z0 + h)
    for zz in (z0 + 2.0, z0 + h * 0.55, z0 + h + 0.2):
        Am.beacon(0.085, zz)
    Sd.cable_tray([(x + 0.66, y - 0.66, z0 + h * 0.90), (x + 0.66, y - 0.66, z0 + 0.4),
                   (x + 0.66, y - 2.8, z0 + 0.4)], 0.30, 0.12)


def main():
    col, root = K.scene("C2")

    C = K.MB("C2-plinth")
    Cd = K.MB("C2-conc")
    Pn = K.MB("C2-panel")
    St = K.MB("C2-steel")
    Sd = K.MB("C2-dark")
    Gl = K.MB("C2-glass")
    Em = K.MB("C2-light")
    Am = K.MB("C2-beacon")
    Or = K.MB("C2-hazard")
    Gv = K.MB("C2-galv")
    Rd = K.MB("C2-radome")

    # ---------------------------------------------------------- plinth
    C.box(-PLX / 2, -PLY / 2, 0.0, PLX / 2, PLY / 2, PLH)
    Cd.box(-PLX / 2 - 0.10, -PLY / 2 - 0.10, 0.0, PLX / 2 + 0.10, PLY / 2 + 0.10, 0.30)
    for i in range(1, 8):
        x = -PLX / 2 + i * PLX / 8.0
        C.box(x - 0.03, -PLY / 2 - 0.02, PLH - 0.05, x + 0.03, PLY / 2 + 0.02, PLH + 0.008)
    for sx in (-1, 1):
        Gv.paint_line((sx * 5.2, -PLY / 2 + 0.8), (sx * 5.2, -8.6), 0.16, z=PLH + 0.010)
    Gv.paint_line((-5.8, -8.8), (5.8, -8.8), 0.22, z=PLH + 0.010)

    # ---------------------------------------------------------- podium
    Cd.prism_z(chamfer_poly(HX + 0.35, HY + 0.35, 2.2), Z0, POD)
    Cd.box(-HX - 0.60, -HY - 0.60, POD - 0.50, HX + 0.60, HY + 0.60, POD - 0.12)
    Cd.box(-HX - 0.48, -HY - 0.48, POD - 0.12, HX + 0.48, HY + 0.48, POD + 0.05)

    # vertical fins on the south face
    for i in range(-5, 6):
        x = i * 2.15
        if abs(x) < 3.6:
            continue
        Cd.box(x - 0.24, -HY - 0.35 - 0.85, Z0, x + 0.24, -HY - 0.35, POD - 0.55)
    # louvre banks between the fins
    for i in range(-5, 5):
        x = i * 2.15 + 1.075
        if abs(x) < 4.2:
            continue
        Sd.push(Matrix.Translation((x, -HY - 0.38, 4.35)))
        Sd.louver(1.55, 0.95, 5)
        Sd.pop()
    # form-tie holes on the podium face (cast concrete tell-tale)
    for j in range(2):
        for i in range(-9, 10):
            Sd.box(i * 1.15 - 0.035, -HY - 0.362, 1.55 + j * 1.65,
                   i * 1.15 + 0.035, -HY - 0.345, 1.62 + j * 1.65)
    # slit windows on the flanks
    for side in (1, 3):
        for k in (-2, -1, 0, 1, 2):
            face(Gl, side, k * 2.6, 2.15, HX + 0.36, HY + 0.36)
            Gl.box(-0.55, -0.05, 0.0, 0.55, 0.02, 1.10)
            Gl.pop()
            face(St, side, k * 2.6, 2.15, HX + 0.36, HY + 0.36)
            St.punch_window(1.1, 1.10, frame=0.07, proud=0.09)
            St.pop()

    # ---------------------------------------------------------- upper slab
    Pn.prism_z(chamfer_poly(UX, UY, 1.2), POD, F3)
    for side in range(4):
        span = BX if side in (0, 2) else BY
        hband = F2 - POD - 0.32
        face(Sd, side, 0.0, POD, UX, UY)
        Sd.box(-(span - 4.4) / 2, -0.016, 0.0, (span - 4.4) / 2, 0.0, hband)
        Sd.pop()
        face(Pn, side, 0.0, POD, UX, UY)
        Pn.panel_grid(span - 4.4, hband, 8, 4, gap=0.058, thick=0.085)
        Pn.pop()
        lats = (-7.0, -3.5, 0.0, 3.5, 7.0) if side in (0, 2) else (-4.0, 0.0, 4.0)
        for lz in (POD + 0.85, POD + 4.25):
            for lat in lats:
                face(Sd, side, lat, lz, UX, UY)
                Sd.punch_window(1.45, 1.55, frame=0.09, proud=0.13)
                Sd.pop()
        face(Sd, side, 0.0, POD + 0.10, UX, UY)
        for j in range(4):
            for i in range(9):
                x = -(span - 4.4) / 2 + i * (span - 4.4) / 8.0
                Sd.box(x - 0.030, -0.115, j * hband / 4.0, x + 0.030, -0.070,
                       0.055 + j * hband / 4.0)
        Sd.pop()
    # band between the panel field and the glazed deck
    for side in range(4):
        span = BX if side in (0, 2) else BY
        face(Cd, side, 0.0, F2 - 0.12, UX, UY)
        Cd.box(-span / 2 + 0.9, -0.32, 0.0, span / 2 - 0.9, 0.02, 0.44)
        Cd.pop()

    # ---------------------------------------------------------- ops deck
    St.box(-HX - 1.00, -HY - 1.00, F2 - 0.30, HX + 1.00, HY + 1.00, F2 + 0.10)
    GH = 3.52
    for side in (0, 1, 3):
        span = BX if side == 0 else BY
        face(Gl, side, 0.0, F2 + 0.10, UX, UY)
        Gl.box(-span / 2 + 1.0, -0.055, 0.0, span / 2 - 1.0, 0.02, GH)
        Gl.pop()
        face(St, side, 0.0, F2 + 0.10, UX, UY)
        St.window_band(span - 2.0, GH, 7 if side == 0 else 5,
                       z0=0.0, mull=0.11, head=0.18, sill=0.14)
        St.pop()
        face(Em, side, 0.0, F2 - 0.24, UX, UY)
        Em.box(-span / 2 + 1.2, -0.19, 0.0, span / 2 - 1.2, -0.10, 0.05)
        Em.pop()
    for sx in (-1, 1):
        for sy in (-1, 1):
            St.box(sx * (UX - 0.35) - 0.26, sy * (UY - 0.35) - 0.26, F2,
                   sx * (UX - 0.35) + 0.26, sy * (UY - 0.35) + 0.26, F3)
    St.box(-UX - 0.55, -UY - 0.55, F3 - 0.22, UX + 0.55, UY + 0.55, F3 + 0.12)
    for (x0, y0, x1, y1) in ((-UX - 0.55, -UY - 0.55, UX + 0.55, -UY - 0.16),
                             (-UX - 0.55, UY + 0.16, UX + 0.55, UY + 0.55),
                             (-UX - 0.55, -UY - 0.55, -UX - 0.16, UY + 0.55),
                             (UX + 0.16, -UY - 0.55, UX + 0.55, UY + 0.55)):
        St.box(x0, y0, F3 + 0.12, x1, y1, F3 + 0.88)

    # ---------------------------------------------------------- entry
    EW, EH, EST = P["entry"]["w"], P["entry"]["h"], P["entry"]["steps"]
    Cd.box(-EW / 2 - 0.60, -HY - 0.62, Z0, EW / 2 + 0.60, -HY + 0.55, Z0 + EH + 0.72)
    Sd.box(-EW / 2, -HY - 0.64, Z0, EW / 2, -HY - 0.02, Z0 + EH)
    for k in range(2):
        x0 = -EW / 2 + 0.06 + k * (EW / 2 - 0.03)
        Sd.box(x0, -HY - 0.70, Z0 + 0.02, x0 + EW / 2 - 0.10, -HY - 0.62, Z0 + EH - 0.06)
        Sd.box(x0 + 0.12, -HY - 0.76, Z0 + 0.95, x0 + 0.26, -HY - 0.70, Z0 + 1.55)
    St.box(-5.2, -HY - 3.3, Z0 + EH + 0.55, 5.2, -HY + 0.2, Z0 + EH + 0.92)
    St.box(-5.0, -HY - 3.25, Z0 + EH + 0.30, 5.0, -HY - 2.95, Z0 + EH + 0.55)
    for sx in (-1, 1):
        St.box(sx * 4.4 - 0.09, -HY - 3.15, Z0, sx * 4.4 + 0.09, -HY - 2.97, Z0 + EH + 0.55)
    Em.box(-4.7, -HY - 3.10, Z0 + EH + 0.26, 4.7, -HY - 2.96, Z0 + EH + 0.31)
    for i in range(EST):
        zz = i * Z0 / EST
        C.box(-3.6, -PLY / 2 - (EST - i) * 0.42 + 0.02, 0.0,
              3.6, -PLY / 2 + 0.02, zz + Z0 / EST)
    for sx in (-1, 1):
        Or.box(sx * 5.8 - 0.95, -PLY / 2 - 0.03, 0.10, sx * 5.8 + 0.95, -PLY / 2 - 0.015, 0.44)
    Sd.box(-1.7, -HY - 3.0, Z0 + EH + 1.02, 1.7, -HY - 2.92, Z0 + EH + 1.40)

    # ---------------------------------------------------------- annex
    Cd.box(AX0, AY0, Z0, AX1, AY1, Z0 + AH)
    St.box(AX0 - 0.36, AY0 - 0.36, Z0 + AH - 0.14, AX1 + 0.36, AY1 + 0.36, Z0 + AH + 0.20)
    for i in range(4):
        y = AY0 + 1.0 + i * 1.9
        Sd.push(Matrix.Translation((AX0, y, 3.5)) @ Matrix.Rotation(math.radians(-90), 4, "Z"))
        Sd.louver(1.5, 0.85, 5)
        Sd.pop()
    Sd.push(Matrix.Translation((AX0 - 0.01, 0.0, Z0)) @ Matrix.Rotation(math.radians(-90), 4, "Z"))
    Sd.roller_door(2.6, 2.7, 9)
    Sd.pop()
    Sd.cable_tray([(AX1 - 0.2, 0.0, Z0 + AH - 0.55), (AX1 + 1.2, 0.0, Z0 + AH - 0.55),
                   (AX1 + 1.2, 0.0, POD + 0.4), (AX1 + 2.4, 0.0, POD + 0.4)], 0.34, 0.14)
    for y in (-2.2, 0.2, 2.4):
        Sd.push(Matrix.Translation((AX0 + 2.4, y, Z0 + AH + 0.20)))
        Sd.ac_unit(1.7, 0.95, 1.15)
        Sd.pop()
    Sd.vent_cap(0.30, 0.60, z0=Z0 + AH + 0.20)

    # ---------------------------------------------------------- roof deck
    DX, DY, DH = P["deck"]
    Gv.box(-DX / 2, -DY / 2 + 0.6, F3 + 0.12, DX / 2, DY / 2 + 0.6, DECK)
    for i in range(5):
        Gv.box(-DX / 2 + 1.0, -DY / 2 + 0.6 + i * DY / 5.0, DECK - 0.02,
               DX / 2 - 1.0, -DY / 2 + 0.74 + i * DY / 5.0, DECK + 0.012)
    for x, y in ((-6.0, 1.0), (-2.6, 1.0), (0.8, 1.0)):
        Sd.push(Matrix.Translation((x, y, DECK)))
        Sd.ac_unit(1.75, 1.0, 1.20)
        Sd.pop()
    for x in (5.0, 7.4):
        Sd.push(Matrix.Translation((x, 3.4, DECK)))
        Sd.extractor(0.75, 1.35)
        Sd.pop()
    for x in (-8.2, 1.6):
        Sd.push(Matrix.Translation((x, -3.0, DECK)))
        Sd.extractor(0.60, 1.05)
        Sd.pop()
    # coolant plant, ducts and a satcom dish
    Sd.box(-7.6, 3.0, DECK, -3.4, 3.6, DECK + 0.55)
    Sd.pipe_run([(-7.6, 3.3, DECK + 0.55), (-2.0, 3.3, DECK + 0.55),
                 (-2.0, 2.4, DECK + 0.55)], 0.11)
    Sd.box(-2.4, -3.4, DECK, 0.6, -2.2, DECK + 0.85)
    Sd.pipe_run([(0.6, -2.8, DECK + 0.30), (4.4, -2.8, DECK + 0.30),
                 (4.4, -1.2, DECK + 0.30)], 0.13)
    St.push(Matrix.Translation((-3.2, -3.6, DECK + 0.55)) @
            Matrix.Rotation(math.radians(38), 4, "Z") @
            Matrix.Rotation(math.radians(-72), 4, "X"))
    St.dish(0.95, 0.30, seg=18, rings=4)
    St.pop()
    St.box(-3.55, -3.95, DECK, -2.85, -3.25, DECK + 0.55)
    for (x, y, ang, L) in ((-DX / 2, -DY / 2 + 0.6, 0.0, DX),
                           (-DX / 2, DY / 2 + 0.6, 0.0, DX),
                           (-DX / 2, -DY / 2 + 0.6, 90.0, DY)):
        St.push(Matrix.Translation((x, y, DECK)) @ Matrix.Rotation(math.radians(ang), 4, "Z"))
        St.railing(L, h=1.05)
        St.pop()
    # roof access hatch
    St.box(2.2, 4.6, DECK, 3.6, 5.7, DECK + 0.55)
    Sd.box(2.3, 4.7, DECK + 0.55, 3.5, 5.6, DECK + 0.62)

    # ---------------------------------------------------------- mast / EW
    MX, MY = P["mast_at"]
    lattice_mast(St, Sd, Am, MX, MY, DECK, P["mast_h"])
    Rd.lathe([(0.0, DECK), (1.05, DECK + 0.35), (1.55, DECK + 1.05),
              (1.55, DECK + 1.75), (1.05, DECK + 2.45), (0.0, DECK + 2.80)],
             -7.0, 4.4, seg=24)
    St.box(-8.2, 3.2, DECK, -5.8, 5.6, DECK + 0.35)

    # ---------------------------------------------------------- blast shields
    SH = P["shield"]
    for (x, y, ang, L) in ((-11.5, -24.6, 90.0, 10.0), (11.5, -24.6, 90.0, 10.0),
                           (-24.9, 0.0, 0.0, 10.0), (24.9, 0.0, 0.0, 10.0)):
        Cd.push(Matrix.Translation((x, y, 0.0)) @ Matrix.Rotation(math.radians(ang), 4, "Z"))
        Cd.blast_wall(L, SH["h"], SH["t"], lean=0.26)
        Cd.box(-L / 2 - 0.15, -SH["t"] / 2 - 0.14, 0.0, L / 2 + 0.15, SH["t"] / 2 + 0.14, 0.34)
        Cd.pop()
    for (x, y, ang, L) in ((-11.5, -24.6, 90.0, 10.0), (11.5, -24.6, 90.0, 10.0)):
        Pn.push(Matrix.Translation((x, y, 0.0)) @ Matrix.Rotation(math.radians(ang), 4, "Z"))
        for k in range(3):
            Pn.box(-L / 2 + 0.4 + k * 3.1, -SH["t"] / 2 - 0.17, 0.55,
                   -L / 2 + 2.6 + k * 3.1, -SH["t"] / 2 - 0.02, 4.9)
        Pn.pop()

    # ---------------------------------------------------------- vehicles
    Veh = K.MB("C2-veh")
    Vg = K.MB("C2-veh-glass")
    Vr = K.MB("C2-veh-rubber")
    for (vx, vy, vrz) in ((-12.6, -10.2, 8.0), (12.0, -11.0, -104.0)):
        Veh.push(Matrix.Translation((vx, vy, PLH)) @ Matrix.Rotation(math.radians(vrz), 4, "Z"))
        Veh.vehicle(L=5.35, W=2.26, H=1.96, glass=Vg, rubber=Vr)
        Veh.pop()
    for i in range(5):
        Sd.push(Matrix.Translation((-17.6 + i * 0.85, 6.4, PLH)))
        Sd.barrel(0.29, 0.86)
        Sd.pop()

    # ---------------------------------------------------------- services
    for sx in (-1, 1):
        for sy in (-1, 1):
            Sd.pipe_run([(sx * (UX - 0.78), sy * (UY - 0.78), F3),
                         (sx * (UX - 0.78), sy * (UY - 0.78), POD + 0.4),
                         (sx * (UX - 0.55), sy * (UY - 0.55), POD + 0.1)], 0.075)
    Sd.cable_tray([(MX, MY - 0.5, DECK + 0.06), (MX, -DY / 2 + 0.9, DECK + 0.06),
                   (MX, -DY / 2 + 0.9, DECK - 0.35)], 0.36, 0.14)
    for sx in (-1, 1):
        Sd.box(sx * (UX - 0.25) - 0.13, -UY - 0.30, F3 - 0.58,
               sx * (UX - 0.25) + 0.13, -UY - 0.02, F3 - 0.38)
        Sd.box(sx * (UX - 0.25) - 0.09, -UY - 0.56, F3 - 0.74,
               sx * (UX - 0.25) + 0.09, -UY - 0.28, F3 - 0.52)
        Em.box(sx * (UX - 0.22) - 0.07, -UY - 0.51, F3 - 0.72,
               sx * (UX - 0.22) + 0.07, -UY - 0.41, F3 - 0.62)
    Sd.box(-3.0, -PLY / 2 - 2.6, 0.0, 3.0, -PLY / 2 - 2.52, 0.92)
    Or.box(-3.0, -PLY / 2 - 2.64, 0.88, 3.0, -PLY / 2 - 2.50, 1.02)
    for sx in (-1, 1):
        for k in range(3):
            Sd.box(sx * (7.5 + k * 1.1) - 0.10, -PLY / 2 - 1.2, 0.0,
                   sx * (7.5 + k * 1.1) + 0.10, -PLY / 2 - 1.0, 0.85)

    # ---------------------------------------------------------- apron clutter
    EmC = K.MB("C2-cyan")
    # guard booth on the west apron
    Cd.box(-17.6, -14.4, PLH, -13.4, -10.4, PLH + 0.35)
    Pn.box(-17.4, -14.2, PLH + 0.35, -13.6, -10.6, PLH + 2.55)
    Gl.box(-17.45, -14.15, PLH + 1.45, -13.55, -14.05, PLH + 2.35)
    for sy in (-1, 1):
        Gl.box(-17.3, -14.2 + (sy + 1) * 1.8, PLH + 1.45,
               -16.4, -14.10 + (sy + 1) * 1.8, PLH + 2.35)
    St.box(-17.9, -14.7, PLH + 2.55, -13.1, -10.1, PLH + 2.85)
    Em.box(-17.2, -14.25, PLH + 2.30, -13.8, -14.18, PLH + 2.36)
    # generator set, cable drum, crates, barrels
    Sd.box(14.2, -12.6, PLH, 17.6, -11.0, PLH + 1.55)
    Sd.box(14.4, -12.55, PLH + 0.35, 17.4, -12.45, PLH + 1.20)
    Sd.pipe_run([(17.6, -11.8, PLH + 1.2), (18.6, -11.8, PLH + 1.2)], 0.10)
    Sd.push(Matrix.Translation((-3.2, -13.6, PLH)) @ Matrix.Rotation(math.radians(90), 4, "Y"))
    Sd.lathe([(1.15, -0.5), (1.15, 0.5)], 0, 0, seg=20)
    Sd.pop()
    for (cx, cy, cw, cd, ch, crz) in ((8.2, 12.6, 1.5, 1.0, 1.1, 6.0),
                                      (9.9, 12.4, 1.2, 1.2, 0.9, -12.0),
                                      (8.9, 11.2, 1.1, 0.9, 0.8, 24.0)):
        Sd.push(Matrix.Translation((cx, cy, PLH)) @ Matrix.Rotation(math.radians(crz), 4, "Z"))
        Sd.crate(cw, cd, ch)
        Sd.pop()
    for i in range(4):
        Sd.push(Matrix.Translation((12.4 + i * 0.72, 13.2, PLH)))
        Sd.barrel(0.28, 0.85)
        Sd.pop()
    # jersey barriers guarding the approach
    for i in range(3):
        Cd.push(Matrix.Translation((9.0 + i * 3.1, -15.2, 0.0)) @
                Matrix.Rotation(math.radians(90), 4, "Z"))
        Cd.jersey(3.0, 1.02, 0.60)
        Cd.pop()
    # flood-light masts
    for (lx, ly) in ((-18.4, 6.0), (18.4, 13.0)):
        St.lathe([(0.20, 0.0), (0.14, 9.8)], lx, ly, seg=12)
        St.box(lx - 0.55, ly - 0.18, 9.8, lx + 0.55, ly + 0.18, 10.05)
        for sx in (-1, 1):
            Sd.box(lx + sx * 0.38 - 0.24, ly - 0.30, 9.9, lx + sx * 0.38 + 0.24, ly + 0.02, 10.28)
            Em.box(lx + sx * 0.38 - 0.20, ly - 0.32, 10.02, lx + sx * 0.38 + 0.20, ly - 0.26, 10.22)
    # info screen + corner sensor pods (cyan = live systems)
    EmC.box(-6.6, -HY - 0.80, Z0 + 1.35, -4.2, -HY - 0.72, Z0 + 2.55)
    St.box(-6.75, -HY - 0.86, Z0 + 1.22, -4.05, -HY - 0.78, Z0 + 2.68)
    for sx in (-1, 1):
        Sd.box(sx * (UX - 0.15) - 0.22, -UY - 0.34, F1 + 0.55,
               sx * (UX - 0.15) + 0.22, -UY - 0.05, F1 + 0.85)
        EmC.box(sx * (UX - 0.15) - 0.14, -UY - 0.37, F1 + 0.60,
                sx * (UX - 0.15) + 0.14, -UY - 0.33, F1 + 0.80)
    # conduit bundle along the podium + junction boxes
    Sd.pipe_run([(-12.2, -HY - 0.55, POD - 0.55), (-12.2, -HY - 0.55, 1.2),
                 (-12.2, -HY - 0.55, 0.65), (-12.2, -PLY / 2 + 0.6, 0.65)], 0.09)
    Sd.pipe_run([(-11.6, -HY - 0.55, POD - 0.55), (-11.6, -HY - 0.55, 0.65),
                 (-11.6, -PLY / 2 + 0.6, 0.65)], 0.07)
    for zz in (2.4, 4.2):
        Sd.box(-12.9, -HY - 0.72, zz, -12.3, -HY - 0.55, zz + 0.55)

    objs = [
        K.emit(C, col, "conc", "GEO-C2-plinth", root),
        K.emit(Cd, col, "conc_dark", "GEO-C2-structure", root),
        K.emit(Pn, col, "panel", "GEO-C2-panel", root),
        K.emit(St, col, "steel", "GEO-C2-steel", root),
        K.emit(Sd, col, "steel_dark", "GEO-C2-dark", root),
        K.emit(Gl, col, "glass_green", "GEO-C2-glass", root),
        K.emit(Gv, col, "galv", "GEO-C2-deck", root),
        K.emit(Em, col, "em_white", "GEO-C2-light", root),
        K.emit(Am, col, "em_amber", "GEO-C2-beacon", root),
        K.emit(EmC, col, "em_cyan", "GEO-C2-systems", root),
        K.emit(Or, col, "orange", "GEO-C2-hazard", root),
        K.emit(Rd, col, "radome", "GEO-C2-radome", root, smooth=True),
        K.emit(Veh, col, "panel_sand", "GEO-C2-vehicles", root),
        K.emit(Vg, col, "glass", "GEO-C2-veh-glass", root),
        K.emit(Vr, col, "rubber", "GEO-C2-veh-tyres", root),
    ]
    K.sky()
    K.finish(objs, OUT, "C2", extra={"grid": S.GRID, "floors": P["floors"]})


if __name__ == "__main__":
    main()
