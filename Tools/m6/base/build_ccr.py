# -*- coding: utf-8 -*-
"""CCR — 履带式集装箱吊车 / heavy crawler container crane.

Real-machine proportions (Liebherr-LHM / crawler-crane class): long crawler
tracks with grouser shoes, carbody + slew ring, counterweighted superstructure,
lattice boom with pendant lines, hoist ropes, telescopic container spreader.
Matte heavy steel, hazard stripes only where a real machine has them.
"""
import math
import os
import sys

from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import lib_kit as K
import m6spec as S

P = S.MODS["CCR"]
OUT = os.path.join(K.ROOT, "model", "m6", "base", "M6_CCR_Crane.blend")

TL, TW, GAUGE = P["track_len"], P["track_w"], P["gauge"]
CB = P["carbody"]
HW, HD, HH = P["house"]
CW, CD, CH = P["counterweight"]
CAB = P["cab"]
BL, BA = P["boom_len"], math.radians(P["boom_angle"])
BW0, BW1 = P["boom_w0"], P["boom_w1"]
SP = P["spreader"]
CN = P["container"]
TAU = math.pi * 2.0


def main():
    col, root = K.scene("CCR")

    Pl = K.MB("CCR-plate")       # heavy steel
    Ma = K.MB("CCR-matte")       # matte plate / walkway / counterweight
    Tr = K.MB("CCR-track")       # track steel
    Dk = K.MB("CCR-dark")        # dark details
    Gl = K.MB("CCR-glass")
    Rb = K.MB("CCR-rubber")
    Rp = K.MB("CCR-rope")
    Or = K.MB("CCR-hazard")
    Em = K.MB("CCR-light")
    Am = K.MB("CCR-amber")
    Ct = K.MB("CCR-container")

    # ---------------------------------------------------------- crawler tracks
    for sx in (-1, 1):
        Tr.push(Matrix.Translation((sx * GAUGE / 2.0, 0.0, 0.0)) @
                Matrix.Rotation(math.pi / 2, 4, "Z"))
        Tr.crawler(TL, TW, 1.30, shoes=38)
        Tr.pop()

    # ---------------------------------------------------------- carbody + slew
    Pl.box(-CB[0] / 2, -CB[1] / 2, 0.65, CB[0] / 2, CB[1] / 2, 0.65 + CB[2])
    Ma.box(-CB[0] / 2 - 0.12, -CB[1] / 2 - 0.12, 0.55, CB[0] / 2 + 0.12, CB[1] / 2 + 0.12, 0.78)
    Pl.lathe([(1.85, 0.65 + CB[2]), (1.85, 0.65 + CB[2] + 0.35),
              (1.55, 0.65 + CB[2] + 0.40)], 0, 0, seg=28)
    Dk.lathe([(1.35, 0.65 + CB[2] + 0.40), (1.35, 0.65 + CB[2] + 0.85)], 0, 0, seg=24)
    for k in range(12):
        a = TAU * k / 12
        Dk.box(math.cos(a) * 1.55 - 0.10, math.sin(a) * 1.55 - 0.10, 0.65 + CB[2] + 0.36,
               math.cos(a) * 1.55 + 0.10, math.sin(a) * 1.55 + 0.10, 0.65 + CB[2] + 0.48)

    # ---------------------------------------------------------- superstructure
    DECK = 0.65 + CB[2] + 0.85
    y0, y1 = -3.6, 7.4
    Ma.box(-HW / 2, y0, DECK, HW / 2, y0 + 1.2, DECK + 0.30)
    Pl.box(-HW / 2, y0, DECK + 0.30, HW / 2, y1, DECK + 0.65)
    # engine / machinery house
    Pl.box(-HW / 2 + 0.35, -1.2, DECK + 0.65, HW / 2 - 0.35, y1 - 1.4, DECK + 0.65 + HH)
    Ma.box(-HW / 2 + 0.10, -1.45, DECK + 0.65 + HH, HW / 2 - 0.10, y1 - 1.15, DECK + 0.95 + HH)
    # louvre banks on both flanks
    for sx in (-1, 1):
        for i in range(4):
            Dk.push(Matrix.Translation((sx * (HW / 2), 2.0 + i * 1.25, DECK + 1.55)) @
                    Matrix.Rotation(math.radians(90 * sx), 4, "Z"))
            Dk.louver(1.05, 0.95, 6, angle=-32.0)
            Dk.pop()
    # roof walkway + railing
    for sy in (-1, 1):
        Ma.box(-HW / 2 + 0.4, 3.1 + sy * 0.9 - 0.35, DECK + 0.95 + HH,
               HW / 2 - 0.4, 3.1 + sy * 0.9 + 0.35, DECK + 1.02 + HH)
    for sx in (-1, 1):
        Pl.push(Matrix.Translation((sx * (HW / 2 - 0.3), 1.0, DECK + 0.95 + HH)) @
                Matrix.Rotation(math.radians(90), 4, "Z"))
        Pl.railing(6.4, h=0.95)
        Pl.pop()
    # exhaust + air cleaners
    Dk.lathe([(0.28, DECK + 0.95 + HH), (0.24, DECK + 2.6 + HH)], -2.2, 5.6, seg=12)
    Dk.lathe([(0.30, DECK + 0.95 + HH), (0.30, DECK + 2.1 + HH),
              (0.22, DECK + 2.25 + HH)], -1.4, 5.6, seg=12)
    for sy in (-1, 1):
        Ma.box(1.2 - 0.35, 6.2 + sy * 0.8 - 0.35, DECK + 0.95 + HH,
               1.2 + 0.35, 6.2 + sy * 0.8 + 0.35, DECK + 1.55 + HH)
    # counterweight stack
    cwy0 = y1 - 0.2
    for k in range(3):
        z = DECK + 0.30 + k * 0.95
        Pl.box(-CW / 2, cwy0, z, CW / 2, cwy0 + CD, z + 0.88)
        Or.box(-CW / 2 + 0.05, cwy0 + CD, z + 0.10, CW / 2 - 0.05, cwy0 + CD + 0.06, z + 0.55)
    Ma.box(-CW / 2 - 0.15, cwy0 + 0.2, DECK + 0.30, CW / 2 + 0.15, cwy0 + CD + 0.15, DECK + 0.55)
    # gantry (A-frame) for the pendants
    for sx in (-1, 1):
        Pl.tube([(sx * 1.05, y1 - 1.0, DECK + 0.65 + HH),
                 (sx * 0.55, y1 - 2.6, DECK + 6.4 + HH)], 0.16, seg=6)
        Pl.tube([(sx * 0.55, y1 - 2.6, DECK + 6.4 + HH),
                 (sx * 0.20, y1 - 3.4, DECK + 6.5 + HH)], 0.10, seg=6)
    Pl.box(-0.85, y1 - 3.30, DECK + 6.35 + HH, 0.85, y1 - 2.75, DECK + 6.62 + HH)

    # ---------------------------------------------------------- cab
    cx, cy, cz = -HW / 2 + 0.55, -2.4, DECK + 0.65
    Pl.box(cx - CAB[0] / 2, cy - CAB[1] / 2, cz, cx + CAB[0] / 2, cy + CAB[1] / 2, cz + 0.55)
    Gl.box(cx - CAB[0] / 2 + 0.10, cy - CAB[1] / 2 - 0.03, cz + 0.55,
           cx + CAB[0] / 2 - 0.10, cy - CAB[1] / 2 + 0.03, cz + CAB[2] - 0.15)
    Gl.box(cx - CAB[0] / 2 - 0.03, cy - CAB[1] / 2 + 0.10, cz + 0.55,
           cx - CAB[0] / 2 + 0.03, cy + CAB[1] / 2 - 0.10, cz + CAB[2] - 0.15)
    Ma.box(cx - CAB[0] / 2 - 0.12, cy - CAB[1] / 2 - 0.12, cz + CAB[2] - 0.15,
           cx + CAB[0] / 2 + 0.12, cy + CAB[1] / 2 + 0.12, cz + CAB[2])
    for sx in (-1, 1):
        Dk.box(cx + sx * 0.55 - 0.16, cy - CAB[1] / 2 - 0.10, cz + 1.05,
               cx + sx * 0.55 + 0.16, cy - CAB[1] / 2 - 0.04, cz + 1.35)
    Em.box(cx - 0.6, cy - CAB[1] / 2 - 0.06, cz + CAB[2] - 0.22,
           cx + 0.6, cy - CAB[1] / 2 - 0.02, cz + CAB[2] - 0.12)
    # access ladder + platform to the cab
    Pl.push(Matrix.Translation((cx - CAB[0] / 2 - 0.35, cy + 1.0, DECK)) @
            Matrix.Rotation(math.radians(-90), 4, "Z"))
    Pl.ladder(3.4)
    Pl.pop()
    Ma.box(cx - CAB[0] / 2 - 1.5, cy - 0.9, DECK + 0.30, cx - CAB[0] / 2 - 0.1, cy + 1.4,
           DECK + 0.38)

    # ---------------------------------------------------------- boom
    dirv = Vector((0.0, -math.cos(BA), math.sin(BA))).normalized()
    rot = Vector((1.0, 0.0, 0.0)).rotation_difference(dirv).to_matrix().to_4x4()
    foot = Vector((0.0, -2.0, DECK + 0.55))
    Mb = Matrix.Translation(foot) @ rot
    Pl.push(Mb)
    Pl.lattice_boom(BL, BW0, BW1, bays=22, chord=0.19)
    # boom foot pins + hydraulic rams
    Pl.pop()
    for sx in (-1, 1):
        Pl.lathe([(0.34, 0), (0.34, 0.9)], sx * 1.25, -2.0, seg=12)
    for sx in (-1, 1):
        Pl.tube([(sx * 1.1, -0.4, DECK + 0.6), (sx * 0.55, -7.5, DECK + 6.4)], 0.20, seg=8)
        Pl.tube([(sx * 1.1, -0.4, DECK + 0.6), (sx * 0.55, -7.5, DECK + 6.4)], 0.13, seg=8)
    # boom head block + sheaves + platform
    head = foot + dirv * BL
    Pl.push(Matrix.Translation(head))
    Pl.box(-1.25, -0.55, -0.55, 1.25, 0.55, 0.55)
    for sx in (-1, 1):
        Pl.push(Matrix.Rotation(math.pi / 2, 4, "X"))
        Pl.cyl(sx * 0.55, 0.0, -0.42, 0.42, 0.42, seg=16)
        Pl.pop()
    Pl.box(-0.9, -0.75, -1.55, 0.9, 0.75, -0.55)
    Pl.pop()
    # pendant bars (gantry -> boom head)
    for sx in (-1, 1):
        Pl.tube([(sx * 0.55, y1 - 2.9, DECK + 6.45 + HH),
                 (head.x + sx * 1.0, head.y, head.z + 0.4)], 0.075, seg=5)
    # walkway along the boom top (push on BOTH builders: stacks are per-mesh)
    Mb2 = Mb.copy()
    Pl.push(Mb2)
    Ma.push(Mb2)
    for i in range(6):
        x = 6.0 + i * 6.2
        Ma.box(x - 1.2, -0.55, BW1 * 0.42, x + 1.2, 0.55, BW1 * 0.42 + 0.05)
        Pl.box(x - 1.2, -0.62, BW1 * 0.42 - 0.06, x + 1.2, -0.55, BW1 * 0.42)
    Ma.pop()
    Pl.pop()

    # ---------------------------------------------------------- hoist + spreader
    sp_z = 12.0
    sp_y = head.y + 0.2
    for (dx, dy) in ((-4.6, -1.0), (4.6, -1.0), (-4.6, 1.0), (4.6, 1.0)):
        Rp.tube([(head.x + dx * 0.12, head.y, head.z - 1.5),
                 (dx, sp_y + dy, sp_z + 1.5)], 0.035, seg=5)
    # hook block
    Pl.push(Matrix.Translation((0.0, sp_y, sp_z + 2.1)))
    Pl.box(-0.85, -0.7, -0.55, 0.85, 0.7, 0.55)
    for sx in (-1, 1):
        Pl.push(Matrix.Rotation(math.pi / 2, 4, "X"))
        Pl.cyl(sx * 0.5, 0.0, -0.30, 0.30, 0.30, seg=14)
        Pl.pop()
    Pl.pop()
    Pl.push(Matrix.Translation((0.0, sp_y, sp_z)))
    Pl.spreader(SP[0], SP[1], SP[2])
    Pl.pop()
    # the lifted container
    Ct.push(Matrix.Translation((0.0, sp_y, sp_z - 0.36 - CN[2])) @
            Matrix.Rotation(math.pi / 2, 4, "Z"))
    Ct.container(CN[0], CN[1], CN[2], ribs=22)
    Ct.pop()
    # two more containers staged on the ground
    for i in range(2):
        Ct.push(Matrix.Translation((-8.0 + i * 3.0, 6.0, 0.0)) @
                Matrix.Rotation(math.pi / 2, 4, "Z"))
        Ct.container(CN[0], CN[1], CN[2], ribs=22)
        Ct.pop()

    # ---------------------------------------------------------- details
    # handrails on the deck edge
    for sy in (-1, 1):
        Ma.push(Matrix.Translation((-HW / 2 + 0.2, 0.0, DECK + 0.65)) @
                Matrix.Rotation(math.radians(90 * sy), 4, "Z"))
        Ma.railing(HW - 0.4, h=1.0)
        Ma.pop()
    # fuel tank + toolbox
    Dk.lathe([(0.75, DECK + 0.30), (0.75, DECK + 1.45), (0.62, DECK + 1.55),
              (0.0, DECK + 1.55)], -1.9, -1.6, seg=18)
    Ma.box(1.4, -1.4, DECK + 0.30, 2.6, -0.4, DECK + 1.15)
    # work lights + beacons
    for (lx, ly, lz) in ((-2.4, 6.8, DECK + 1.65 + HH), (2.4, 6.8, DECK + 1.65 + HH),
                         (-1.1, -2.9, DECK + 1.75)):
        Ma.box(lx - 0.28, ly - 0.18, lz, lx + 0.28, ly + 0.18, lz + 0.26)
        Em.box(lx - 0.24, ly - 0.22, lz + 0.02, lx + 0.24, ly - 0.17, lz + 0.22)
    for sx in (-1, 1):
        Am.beacon(0.09, DECK + 1.02 + HH)
    # mirrors, steps, fire bottle
    for sx in (-1, 1):
        Dk.box(cx + sx * (CAB[0] / 2 + 0.35) - 0.05, cy - 0.2, cz + 1.9,
               cx + sx * (CAB[0] / 2 + 0.35) + 0.05, cy + 0.2, cz + 2.15)
    for i in range(4):
        Ma.box(-HW / 2 - 0.55, -1.0 + i * 0.45, DECK - 0.55 + i * 0.28,
               -HW / 2 - 0.10, -0.55 + i * 0.45, DECK - 0.40 + i * 0.28)
    Rb.tube([(1.6, -1.2, DECK + 0.40), (2.2, -1.2, DECK + 0.40),
             (2.2, -1.0, DECK + 0.30)], 0.06, seg=6)
    # cable drum on the deck
    Dk.push(Matrix.Translation((2.0, 1.4, DECK + 0.65)) @ Matrix.Rotation(math.pi / 2, 4, "X"))
    Dk.cyl(0.0, 0.0, -0.55, 0.55, 0.55, seg=16)
    Dk.pop()

    objs = [
        K.emit(Pl, col, "steel_plate", "GEO-CCR-plate", root),
        K.emit(Ma, col, "steel_matte", "GEO-CCR-matte", root),
        K.emit(Tr, col, "track_steel", "GEO-CCR-tracks", root),
        K.emit(Dk, col, "steel_dark", "GEO-CCR-dark", root),
        K.emit(Gl, col, "glass", "GEO-CCR-glass", root),
        K.emit(Rb, col, "rubber_dark", "GEO-CCR-hose", root),
        K.emit(Rp, col, "galv", "GEO-CCR-ropes", root),
        K.emit(Or, col, "orange", "GEO-CCR-hazard", root),
        K.emit(Em, col, "em_white", "GEO-CCR-light", root),
        K.emit(Am, col, "em_amber", "GEO-CCR-beacon", root),
        K.emit(Ct, col, "panel_sand", "GEO-CCR-containers", root),
    ]
    K.sky()
    K.finish(objs, OUT, "CCR", extra={"boom": [BL, P["boom_angle"]],
                                      "head": [round(head.x, 2), round(head.y, 2), round(head.z, 2)]})


if __name__ == "__main__":
    main()
