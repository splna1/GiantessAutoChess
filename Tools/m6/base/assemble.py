# -*- coding: utf-8 -*-
"""Assemble the M6 base site: ground, paving, perimeter fence, six modules,
yards, berms and light masts.  Modules are appended from their own .blend files
so each one stays independently rebuildable.
"""
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import lib_kit as K
import m6spec as S

OUT = os.path.join(K.ROOT, "model", "m6", "base", "M6_Base_Site.blend")
MBLENDS = {
    "C2": "M6_C2_Command.blend",
    "HGR": "M6_HGR_Hangar.blend",
    "BRK": "M6_BRK_Barracks.blend",
    "RDR": "M6_RDR_Radar.blend",
    "GTE": "M6_GTE_Gate.blend",
    "UAV": "M6_UAV_Pad.blend",
    "CON": "M6_CON_Site.blend",
    "CCR": "M6_CCR_Crane.blend",
    "SIT": "M6_SIT_Seat.blend",
}


def append_module(col, tag):
    """Append every GEO-* object of a module blend and parent it to a site empty."""
    path = os.path.join(K.ROOT, "model", "m6", "base", MBLENDS[tag])
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n.startswith("GEO-")]
    place = S.SITE["place"][tag]
    root = bpy.data.objects.new("SITE_" + tag, None)
    root.empty_display_type = "PLAIN_AXES"
    root.empty_display_size = 4.0
    col.objects.link(root)
    root.matrix_world = (Matrix.Translation((place["pos"][0], place["pos"][1], 0.0)) @
                         Matrix.Rotation(math.radians(place["rz"]), 4, "Z"))
    n = 0
    for ob in dst.objects:
        if ob is None:
            continue
        col.objects.link(ob)
        ob.parent = root
        ob.matrix_parent_inverse = Matrix.Identity(4)
        n += 1
    return root, n


def main():
    col, _ = K.scene("SITE")
    col.name = "COL_M6_SITE"

    C = K.MB("SITE-ground")
    Pv = K.MB("SITE-paving")
    St = K.MB("SITE-steel")
    Sd = K.MB("SITE-dark")
    Em = K.MB("SITE-light")
    EmC = K.MB("SITE-systems")
    Or = K.MB("SITE-hazard")
    Gv = K.MB("SITE-markings")
    Dirt = K.MB("SITE-berm")

    SW, SD = S.SITE["size"]
    # ---------------------------------------------------------- ground
    C.box(-SW / 2 - 18, -SD / 2 - 18, -0.55, SW / 2 + 18, SD / 2 + 18, 0.0)
    # ---------------------------------------------------------- paving
    for (x0, y0, x1, y1, key, z) in S.SITE["paving"]:
        Pv.box(x0, y0, z - 0.12, x1, y1, z)
    # road centre lines + edge lines
    for (x0, y0, x1, y1, key, z) in S.SITE["paving"]:
        if key != "asphalt":
            continue
        if abs(x1 - x0) < abs(y1 - y0):
            cx = (x0 + x1) / 2.0
            Gv.paint_line((cx, y0 + 1.0), (cx, y1 - 1.0), 0.16, z=z + 0.006)
            for sx in (-1, 1):
                Gv.paint_line((cx + sx * (x1 - x0) / 2.0 - sx * 0.6, y0 + 1.0),
                              (cx + sx * (x1 - x0) / 2.0 - sx * 0.6, y1 - 1.0), 0.10, z=z + 0.006)
        else:
            cy = (y0 + y1) / 2.0
            Gv.paint_line((x0 + 1.0, cy), (x1 - 1.0, cy), 0.16, z=z + 0.006)
    # hatched no-go area in front of the gate
    for i in range(6):
        Gv.paint_line((-8.0 + i * 2.6, -58.0), (-6.0 + i * 2.6, -64.0), 0.22, z=0.036)

    # ---------------------------------------------------------- fence ring
    fh = S.SITE["fence_h"]
    inset = S.SITE["fence_inset"]
    fx, fy = SW / 2.0 - inset, SD / 2.0 - inset
    gate_half = 20.0

    def fence_run(p0, p1, skip=None):
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        L = math.hypot(dx, dy)
        if L < 1e-6:
            return
        ux, uy = dx / L, dy / L
        n = int(L / 3.0)
        for i in range(n + 1):
            x, y = p0[0] + ux * i * L / n, p0[1] + uy * i * L / n
            if skip and skip[0] <= i <= skip[1]:
                continue
            St.box(x - 0.07, y - 0.07, 0.0, x + 0.07, y + 0.07, fh)
            if i % 4 == 0:
                EmC.cyl(x, y, fh, fh + 0.16, 0.09, seg=8)
        # rails + mesh panel
        for zz in (fh - 0.20, 0.35):
            St.push(Matrix.Translation((p0[0], p0[1], zz)) @
                    Matrix.Rotation(math.atan2(dy, dx), 4, "Z"))
            St.box(0.0, -0.035, 0.0, L, 0.035, 0.07)
            St.pop()
        Sd.push(Matrix.Translation((p0[0], p0[1], 0.40)) @
                Matrix.Rotation(math.atan2(dy, dx), 4, "Z"))
        Sd.box(0.0, -0.012, 0.0, L, 0.012, fh - 0.60)
        Sd.pop()

    fence_run((-fx, -fy), (-gate_half, -fy))
    fence_run((gate_half, -fy), (fx, -fy))
    fence_run((-fx, -fy), (-fx, fy))
    fence_run((fx, -fy), (fx, fy))
    fence_run((-fx, fy), (-gate_half, fy))
    fence_run((gate_half, fy), (fx, fy))
    # corner towers (simple posts + lights)
    for sx in (-1, 1):
        for sy in (-1, 1):
            St.box(sx * fx - 0.14, sy * fy - 0.14, 0.0, sx * fx + 0.14, sy * fy + 0.14, fh + 3.4)
            Em.box(sx * fx - 0.22, sy * fy - 0.22, fh + 3.4, sx * fx + 0.22, sy * fy + 0.22,
                   fh + 3.62)

    # ---------------------------------------------------------- light masts
    for (lx, ly) in S.SITE["light_masts"]:
        St.lathe([(0.24, 0.0), (0.16, 22.0)], lx, ly, seg=12)
        St.box(lx - 1.4, ly - 0.22, 22.0, lx + 1.4, ly + 0.22, 22.30)
        for k in (-1, 0, 1):
            Sd.box(lx + k * 0.9 - 0.28, ly - 0.42, 21.9, lx + k * 0.9 + 0.28, ly + 0.02, 22.45)
            Em.box(lx + k * 0.9 - 0.24, ly - 0.46, 22.05, lx + k * 0.9 + 0.24, ly - 0.40, 22.35)
        # hazard band at the base
        Or.box(lx - 0.26, ly - 0.26, 0.2, lx + 0.26, ly + 0.26, 0.9)

    # ---------------------------------------------------------- container yards
    for (yx0, yy0, yx1, yy1) in S.SITE["yards"]:
        rows = 3
        cols = 2
        for r in range(rows):
            for c in range(cols):
                for k in range(2 if (r + c) % 2 == 0 else 1):
                    cx = yx0 + 4.0 + c * 3.4
                    cy = yy0 + 8.0 + r * 7.2
                    Sd.push(Matrix.Translation((cx, cy, 0.02 + k * 2.62)) @
                            Matrix.Rotation(math.radians(90 * ((r + c) % 2)), 4, "Z"))
                    Sd.container(6.06, 2.44, 2.60, ribs=16)
                    Sd.pop()
        # yard lighting + hazard bollards
        for i in range(3):
            EmC.cyl(yx0 + 2.0, yy0 + 4.0 + i * 8.0, 0.0, 0.24, 0.11, seg=8)
    # generator + fuel bladder yard near the barracks
    Sd.box(-42.0, -22.0, 0.0, -38.0, -19.4, 1.7)
    Sd.push(Matrix.Translation((-35.0, -20.6, 0.0)))
    Sd.ac_unit(1.8, 1.0, 1.2)
    Sd.pop()
    Sd.lathe([(1.9, 0.0), (1.9, 1.1), (1.6, 1.35), (0.0, 1.45)], -30.0, -20.0, seg=18)

    # ---------------------------------------------------------- berms
    for b in S.SITE["berms"]:
        Dirt.prism_y([(b["y0"], 0.0), (b["y1"], 0.0), ((b["y0"] + b["y1"]) / 2.0, b["h"])],
                     b["x0"], b["x1"])

    # ---------------------------------------------------------- site facilities
    # helipad (south-west)
    C.box(-84.0, -60.0, 0.0, -62.0, -40.0, 0.22)
    Gv.ring_circle(8.0, z=0.226, tube=0.18)
    Gv.box(-71.4, -54.6, 0.226, -74.6, -53.9, 0.24)
    Gv.box(-71.4, -46.1, 0.226, -74.6, -45.4, 0.24)
    Gv.box(-73.5, -54.6, 0.226, -72.7, -45.4, 0.24)
    for i in range(8):
        a = math.radians(i * 45)
        EmC.cyl(-73.0 + math.cos(a) * 8.4, -50.0 + math.sin(a) * 8.4, 0.22, 0.46, 0.12, seg=8)

    # water tower (centre-east)
    wx, wy = 44.0, -56.0
    for sx in (-1, 1):
        for sy in (-1, 1):
            St.tube([(wx + sx * 3.2, wy + sy * 3.2, 0.0), (wx + sx * 2.2, wy + sy * 2.2, 20.0)],
                    0.18, seg=6)
    for zz in (6.0, 12.0, 18.0):
        for sx in (-1, 1):
            St.box(wx + sx * 2.9 - 0.10, wy - 3.0, zz, wx + sx * 2.9 + 0.10, wy + 3.0, zz + 0.18)
        for sy in (-1, 1):
            St.box(wx - 3.0, wy + sy * 2.9 - 0.10, zz, wx + 3.0, wy + sy * 2.9 + 0.10, zz + 0.18)
    St.lathe([(4.6, 20.0), (4.6, 24.6), (4.0, 25.2), (0.0, 25.4)], wx, wy, seg=24)
    St.box(wx - 4.8, wy - 4.8, 24.6, wx + 4.8, wy + 4.8, 24.9)
    Sd.tube([(wx + 2.4, wy, 20.0), (wx + 2.4, wy, 1.0)], 0.12, seg=6)
    Or.box(wx - 4.75, wy - 4.75, 20.5, wx + 4.75, wy + 4.75, 21.0)
    EmC.cyl(wx, wy, 25.4, 25.9, 0.16, seg=8)

    # earth-covered ammunition bunkers (east edge)
    for k in range(3):
        by = -30.0 + k * 16.0
        bx0, bx1 = 88.0, 102.0
        C.box(bx0, by - 5.0, 0.0, bx1, by + 5.0, 0.45)
        C.prism_x([(by - 4.0, 0.45), (by + 4.0, 0.45), (by + 2.6, 4.2), (by - 2.6, 4.2)],
                  bx0 + 0.6, bx1 - 0.6)
        for sy in (-1, 1):
            Dirt.prism_x([(by + sy * 3.4, 0.0), (by + sy * 5.4, 0.0),
                          (by + sy * 5.0, 2.6), (by + sy * 3.4, 3.4)],
                         bx0 + 0.3, bx1 - 0.3)
        Dirt.box(bx0 + 0.3, by - 4.4, 3.2, bx1 - 0.3, by + 4.4, 3.9)
        Sd.box(bx0 - 0.05, by - 1.4, 0.45, bx0 + 0.20, by + 1.4, 2.6)
        Or.box(bx0 - 0.08, by - 1.5, 2.6, bx0 + 0.22, by + 1.5, 2.8)

    # vehicle park (west)
    Veh = K.MB("SITE-veh")
    Vg = K.MB("SITE-veh-glass")
    Vr = K.MB("SITE-veh-rubber")
    for i in range(3):
        for j in range(2):
            vx, vy = -52.0 + j * 9.0, -46.0 + i * 4.2
            Veh.push(Matrix.Translation((vx, vy, 0.02)) @ Matrix.Rotation(math.radians(90), 4, "Z"))
            Veh.vehicle(L=5.35, W=2.26, H=1.96, glass=Vg, rubber=Vr)
            Veh.pop()
    for i in range(3):
        EmC.cyl(-46.0, -48.0 + i * 4.2, 0.0, 0.35, 0.13, seg=8)

    # dirt skirt so the compound does not read as a plate dropped on the desert
    for sx in (-1, 1):
        Dirt.prism_x([(-SD / 2 - 18, -0.55), (-SD / 2 - 4, 0.25), (SD / 2 + 4, 0.25),
                      (SD / 2 + 18, -0.55)], sx * (SW / 2 + 18), sx * (SW / 2 + 2))
    for sy in (-1, 1):
        Dirt.prism_y([(-SW / 2 - 18, -0.55), (-SW / 2 - 4, 0.25), (SW / 2 + 4, 0.25),
                      (SW / 2 + 18, -0.55)], sy * (SD / 2 + 18), sy * (SD / 2 + 2))

    # ---------------------------------------------------------- expansion plots
    # data-driven: every entry in SITE["expansion"] gets a pad, an outline,
    # corner stakes and a "reserved" board, so a new module only needs one
    # spec entry + one row in MBLENDS.
    for pl in S.SITE["expansion"]:
        px, py = pl["pos"]
        pw, pd = pl["size"]
        Dirt.box(px - pw / 2, py - pd / 2, 0.0, px + pw / 2, py + pd / 2, 0.06)
        for (ax, ay, bx, by) in ((px - pw / 2, py - pd / 2, px + pw / 2, py - pd / 2),
                                 (px - pw / 2, py + pd / 2, px + pw / 2, py + pd / 2),
                                 (px - pw / 2, py - pd / 2, px - pw / 2, py + pd / 2),
                                 (px + pw / 2, py - pd / 2, px + pw / 2, py + pd / 2)):
            Gv.paint_line((ax, ay), (bx, by), 0.22, z=0.075)
        for sx in (-1, 1):
            for sy in (-1, 1):
                x, y = px + sx * (pw / 2 - 0.4), py + sy * (pd / 2 - 0.4)
                St.box(x - 0.06, y - 0.06, 0.06, x + 0.06, y + 0.06, 1.35)
                Or.box(x - 0.09, y - 0.09, 1.18, x + 0.09, y + 0.09, 1.38)
        # plot board at the south edge
        St.box(px - 1.6, py - pd / 2 - 0.5, 0.06, px - 1.45, py - pd / 2 - 0.35, 1.9)
        St.box(px + 1.45, py - pd / 2 - 0.5, 0.06, px + 1.6, py - pd / 2 - 0.35, 1.9)
        St.box(px - 1.8, py - pd / 2 - 0.55, 1.55, px + 1.8, py - pd / 2 - 0.45, 2.35)
        EmC.box(px - 1.6, py - pd / 2 - 0.58, 1.62, px + 1.6, py - pd / 2 - 0.52, 2.28)

    # ---------------------------------------------------------- giant-seat annex
    # the seat stands outside the south gate on its own plaza, linked by a road
    ax, ay = S.SITE["place"]["SIT"]["pos"]
    Ann = K.MB("SITE-annex")
    Ann.box(-60.0, ay - 46.0, 0.0, 60.0, ay + 46.0, 0.10)
    for i in range(1, 13):
        Ann.box(-60.0, ay - 46.0 + i * 92.0 / 12.0 - 0.05, 0.10,
                60.0, ay - 46.0 + i * 92.0 / 12.0 + 0.05, 0.102)
    Pv.box(-8.0, ay + 46.0 - 4.0, 0.0, 8.0, -100.0, 0.06)
    Gv.paint_line((0.0, ay + 44.0), (0.0, -102.0), 0.18, z=0.11)
    for sx in (-1, 1):
        for i in range(4):
            EmC.cyl(sx * 56.0, ay - 36.0 + i * 24.0, 0.10, 0.34, 0.12, seg=8)
    # low kerb around the plaza so it reads as a designed forecourt
    for (x0, y0, x1, y1) in ((-60.0, ay - 46.0, 60.0, ay - 45.4),
                             (-60.0, ay + 45.4, 60.0, ay + 46.0),
                             (-60.0, ay - 46.0, -59.4, ay + 46.0),
                             (59.4, ay - 46.0, 60.0, ay + 46.0)):
        Dirt.box(x0, y0, 0.10, x1, y1, 0.55)

    # ---------------------------------------------------------- modules
    placed = {}
    for tag in ("C2", "HGR", "BRK", "RDR", "GTE", "UAV", "CON", "CCR", "SIT"):
        root, n = append_module(col, tag)
        placed[tag] = {"objects": n, "pos": S.SITE["place"][tag]["pos"],
                       "rz": S.SITE["place"][tag]["rz"]}

    # ---------------------------------------------------------- site signage
    St.box(-4.0, -SD / 2 + 6.0, 0.0, 4.0, -SD / 2 + 6.4, 0.45)
    Or.box(-4.0, -SD / 2 + 5.9, 0.42, 4.0, -SD / 2 + 6.1, 0.62)

    objs = [
        C.emit(col, K.ground_mat(), "GEO-SITE-ground"),
        K.emit(Pv, col, "asphalt", "GEO-SITE-paving", None),
        K.emit(St, col, "steel", "GEO-SITE-structure", None),
        K.emit(Sd, col, "steel_dark", "GEO-SITE-dark", None),
        K.emit(Em, col, "em_white", "GEO-SITE-light", None),
        K.emit(EmC, col, "em_cyan", "GEO-SITE-systems", None),
        K.emit(Or, col, "orange", "GEO-SITE-hazard", None),
        K.emit(Gv, col, "white", "GEO-SITE-markings", None),
        K.emit(Dirt, col, "dust", "GEO-SITE-berms", None),
        K.emit(Ann, col, "concrete_rd", "GEO-SITE-annex", None),
        K.emit(Veh, col, "panel_sand", "GEO-SITE-vehicles", None),
        K.emit(Vg, col, "glass", "GEO-SITE-veh-glass", None),
        K.emit(Vr, col, "rubber", "GEO-SITE-veh-tyres", None),
    ]
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    K.sky()
    K.finish(objs, OUT, "SITE", extra={"modules": placed, "size": [SW, SD]})


if __name__ == "__main__":
    main()
