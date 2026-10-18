"""Blue faction base kit: meshes, prop layout and lights for the south front-line command centre (B5).

Meshes are built through 07_base_blue.py; layout is consumed by 05_city_layout.py and 07.
All south objects satisfy the hard height constraint (≤25 m, radar ≤35 m) and the camera sight rule
H(x) ≤ 0.8 × 1202 × (−800 − x) / 929 for x < −800.

Run standalone to print mesh stats, bounds, height pre-audit and zfight self-check.
"""
import math
import sys

import citygen as cg
import geom
import haussmann as hm
from geom import MeshBuilder, Z, norm, rng

# ---------------------------------------------------------------- materials
SLOT_MATERIALS = {
    # blue faction palette
    "sandbag": "MI_Paint_BlueSandbag", "concrete": "MI_Paint_BlueConcrete", "steel": "MI_Paint_BlueSteel",
    "blue": "MI_Paint_Blue", "dark": "MI_Paint_BlueDark", "canvas": "MI_Paint_BlueCanvas",
    "cloth": "MI_Cloth_Blue", "banner": "MI_Cloth_BlueBanner", "signal": "MI_Signal_Blue",
    "glow": "MI_Glow_Blue", "glass": "MI_Glass", "wood": "MI_Paint_Frame", "iron": "MI_Paint_Iron",
    # new slots for B5 expansion
    "bright": "MI_Paint_BlueBright", "white": "MI_Paint_BlueWhite", "gold": "MI_Paint_Gold",
    "marking": "MI_Paint_Marking", "olive": "MI_Paint_Olive", "khaki": "MI_Paint_Canvas",
    "rubble": "MI_Ground_Rubble", "dirt": "MI_Ground_Damaged", "char": "MI_Paint_Charred",
    "grey": "MI_Paint_Concrete",
}
SLOTS = list(SLOT_MATERIALS)
NON_NANITE = {"SM_Blue_Flag", "SM_Blue_Banner"}
RADAR_TOWER_H = 21.0

# ---------------------------------------------------------------- helpers
def builder():
    return MeshBuilder(SLOTS)

def _flag_card(mb, slot, bottom, height, width):
    """Vertical cloth card at x=0 facing +x."""
    y = width / 2.0
    mb.poly(slot, [(0, -y, bottom), (0, y, bottom), (0, y, bottom + height), (0, -y, bottom + height)], (1, 0, 0))

# ---------------------------------------------------------------- original meshes (unchanged)
def sandbag_wall(length=16.0, height=1.35, depth=0.9):
    mb = builder()
    n = max(1, int(length / 0.9 + 0.5))
    dx = length / n
    for i in range(n):
        x0, x1 = (i - n / 2.0) * dx, (i + 1 - n / 2.0) * dx
        mb.box("sandbag", x0 + 0.02, x1 - 0.02, -depth / 2, depth / 2, 0.0, height)
    return mb

def barrier(length=3.0):
    mb = builder()
    h, d = 1.05, 0.42
    mb.box("concrete", -length / 2, length / 2, -d, d, 0.0, h)
    return mb

def wire_obstacle(length=8.0):
    mb = builder()
    n = max(2, int(length / 2.2))
    for i in range(n + 1):
        x = (i / n - 0.5) * length
        cg.prism(mb, "steel", (x, 0, 0), (x, 0, 1.1), 0.05, 0.03, 5)
    for z in (0.3, 0.6, 0.9):
        cg.bar(mb, "steel", (-length / 2, 0, z), (length / 2, 0, z), 0.025)
    return mb

def flag(height=8.0):
    mb = builder()
    cg.prism(mb, "steel", (0, 0, 0), (0, 0, height), 0.06, 0.04, 6)
    _flag_card(mb, "cloth", height - 1.6, 1.2, 1.8)
    return mb

def banner(span=10.0, height=1.2, pole_h=4.2):
    mb = builder()
    for x in (-span / 2, span / 2):
        cg.prism(mb, "steel", (x, 0, 0), (x, 0, pole_h), 0.06, 0.04, 6)
    cg.bar(mb, "steel", (-span / 2, 0, pole_h - 0.1), (span / 2, 0, pole_h - 0.1), 0.04)
    mb.poly("banner", [(-span / 2, 0, pole_h - 0.12), (span / 2, 0, pole_h - 0.12),
                       (span / 2, 0, pole_h - 0.12 - height), (-span / 2, 0, pole_h - 0.12 - height)], (0, -1, 0))
    return mb

def tent(length, width, wall, ridge, medical=False):
    mb = builder()
    slot = "canvas" if medical else "cloth"
    cross = "white" if medical else "blue"
    n = max(3, int(length / 2.5))
    for i in range(n + 1):
        u = i / n
        x = (u - 0.5) * length
        pts = [(-width / 2, wall), (width / 2, wall), (width / 2, 0), (-width / 2, 0)]
        for j in range(len(pts)):
            k = (j + 1) % len(pts)
            ya, za = pts[j]
            yb, zb = pts[k]
            if i < n:
                xn = ((i + 1) / n - 0.5) * length
                mb.poly(slot, [(x, ya, za), (xn, ya, za), (xn, yb, zb), (x, yb, zb)])
    for x in (-length / 2, length / 2):
        mb.poly(slot, [(x, -width / 2, wall), (x, width / 2, wall), (x, 0, ridge)])
    for x in (-length / 2, length / 2):
        for y in (-width / 2, width / 2):
            cg.prism(mb, "steel", (x, y, 0), (x, y, wall + 0.1), 0.04, 0.03, 5)
    if medical:
        for side in (-1, 1):
            cx, cw = side * length * 0.35, wall * 0.4
            mb.box(cross, cx - cw * 0.2, cx + cw * 0.2, -width / 2 - 0.01, -width / 2 + 0.01, wall * 0.3, wall * 0.7)
            mb.box(cross, cx - cw, cx + cw, -width / 2 - 0.01, -width / 2 + 0.01, wall * 0.48, wall * 0.52)
    return mb

def container(length=12.2, width=2.44, height=2.6, seed=0):
    mb = builder()
    r = rng(seed)
    slot = "blue" if r.random() < 0.5 else "dark"
    mb.box(slot, -length / 2, length / 2, -width / 2, width / 2, 0, height, skip=("nz",))
    for x in (-length / 2 + 0.15, length / 2 - 0.15):
        for y in (-width / 2 + 0.15, width / 2 - 0.15):
            cg.bar(mb, "steel", (x, y, 0), (x, y, height), 0.05)
    for z in (0.3, height - 0.3):
        for y in (-width / 2, width / 2):
            cg.bar(mb, "steel", (-length / 2 + 0.3, y, z), (length / 2 - 0.3, y, z), 0.04)
    return mb

def repair_truck():
    mb = builder()
    mb.box("dark", -4.5, 4.5, -1.3, 1.3, 0.8, 1.4)
    mb.box("blue", 2.8, 4.5, -1.2, 1.2, 1.4, 2.8)
    mb.box("glass", 3.0, 4.3, -1.0, 1.0, 2.2, 2.6)
    mb.box("canvas", -4.2, 2.5, -1.2, 1.2, 1.5, 2.7, skip=("nz",))
    for x in (-3.2, -1.6, 2.0):
        for y in (-1.15, 1.15):
            cg.prism(mb, "char", (x, y, 0.0), (x, y, 0.0), 0.5, 0.5, 12)
    return mb

def radar():
    mb = builder()
    h = RADAR_TOWER_H
    cg.prism(mb, "steel", (0, 0, 0), (0, 0, h), 1.2, 0.8, 8)
    cg.prism(mb, "dark", (0, 0, h), (0, 0, h + 1.5), 1.5, 1.2, 8)
    cg.prism(mb, "steel", (0, 0, h + 1.5), (0, 0, h + 3.0), 0.4, 0.3, 6)
    mb.box("glow", -0.6, 0.6, -0.6, 0.6, h + 3.0, h + 3.6)
    for a in range(0, 360, 45):
        rad = math.radians(a)
        x, y = 2.8 * math.cos(rad), 2.8 * math.sin(rad)
        cg.bar(mb, "steel", (x, y, h + 1.8), (0, 0, h + 2.4), 0.15)
    return mb

def generator():
    mb = builder()
    mb.box("dark", -1.8, 1.8, -1.0, 1.0, 0.0, 1.4)
    mb.box("steel", -1.6, 1.6, -0.9, 0.9, 1.4, 1.6)
    cg.prism(mb, "steel", (0, 0, 1.6), (0, 0, 3.2), 0.2, 0.15, 6)
    return mb

def light_tower():
    mb = builder()
    h = 12.0
    for x, y in ((-0.8, -0.8), (0.8, -0.8), (0.8, 0.8), (-0.8, 0.8)):
        cg.prism(mb, "steel", (x, y, 0), (x * 0.3, y * 0.3, h), 0.08, 0.06, 5)
    mb.box("dark", -0.6, 0.6, -0.6, 0.6, h, h + 0.6)
    for i in range(4):
        a = math.radians(45 + 90 * i)
        x, y = 0.7 * math.cos(a), 0.7 * math.sin(a)
        mb.box("glow", x - 0.2, x + 0.2, y - 0.2, y + 0.2, h + 0.2, h + 0.5)
    return mb

def signal():
    mb = builder()
    cg.prism(mb, "steel", (0, 0, 0), (0, 0, 5.0), 0.08, 0.06, 6)
    mb.box("dark", -0.3, 0.3, -0.3, 0.3, 5.0, 5.25)
    mb.box("signal", -0.25, 0.25, -0.25, 0.25, 5.05, 5.2)
    return mb

def map_table():
    mb = builder()
    for x, y in ((-0.9, -0.6), (0.9, -0.6), (0.9, 0.6), (-0.9, 0.6)):
        cg.prism(mb, "steel", (x, y, 0), (x, y, 0.9), 0.05, 0.04, 5)
    mb.box("wood", -1.0, 1.0, -0.7, 0.7, 0.9, 1.0)
    return mb

# ---------------------------------------------------------------- new B5 meshes
def eagle_shield():
    """Large shield banner with eagle emblem (83.5 m tall × 35 m, tilted 16°)."""
    mb = builder()
    L, W, K = 83.5, 35.0, 42.0
    theta = math.radians(16.0)
    s, c = math.sin(theta), math.cos(theta)

    def T(u, v, w):
        return (u * c - w * s, v, 1.0 + u * s + w * c)

    # outline
    seg = 8
    lo = [(K * i / seg, -W * (2.0 * i / seg - (i / seg) ** 2)) for i in range(seg + 1)]
    outline = lo + [(L, -W), (L, W)] + [(p[0], -p[1]) for p in reversed(lo[1:])]

    # plate
    for i in range(len(outline)):
        j = (i + 1) % len(outline)
        mb.poly("bright", [T(outline[i][0], outline[i][1], 0), T(outline[j][0], outline[j][1], 0), (0, 0, 1.0)])

    # back
    for i in range(len(outline)):
        j = (i + 1) % len(outline)
        a, b = outline[i], outline[j]
        mb.poly("dark", [T(a[0], a[1], -0.4), T(b[0], b[1], -0.4), T(b[0], b[1], 0), T(a[0], a[1], 0)], (-s, 0, -c))

    # glow rim
    for i in range(len(outline)):
        j = (i + 1) % len(outline)
        a, b = outline[i], outline[j]
        du, dv = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(du, dv)
        if ln < 1e-6:
            continue
        nu, nv = -dv / ln, du / ln
        a0, a1 = (a[0] + nu * 1.2, a[1] + nv * 1.2), (b[0] + nu * 1.2, b[1] + nv * 1.2)
        mb.poly("glow", [T(a[0], a[1], -0.4), T(b[0], b[1], -0.4), T(a1[0], a1[1], 0.10), T(a0[0], a0[1], 0.10)])
    for i in range(len(outline)):
        j = (i + 1) % len(outline)
        a, b = outline[i], outline[j]
        du, dv = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(du, dv)
        if ln < 1e-6:
            continue
        nu, nv = -dv / ln, du / ln
        a0, a1 = (a[0] + nu * 1.2, a[1] + nv * 1.2), (b[0] + nu * 1.2, b[1] + nv * 1.2)
        mb.poly("glow", [T(a0[0], a0[1], 0.10), T(a1[0], a1[1], 0.10), T(b[0], b[1], 0.10), T(a[0], a[1], 0.10)])

    # white ring
    for i in range(len(outline)):
        j = (i + 1) % len(outline)
        a, b = outline[i], outline[j]
        du, dv = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(du, dv)
        if ln < 1e-6:
            continue
        nu, nv = -dv / ln, du / ln
        a0, a1 = (a[0] - nu * 2.8, a[1] - nv * 2.8), (b[0] - nu * 2.8, b[1] - nv * 2.8)
        mb.poly("white", [T(a[0], a[1], 0.10), T(b[0], b[1], 0.10), T(a1[0], a1[1], 0.10), T(a0[0], a0[1], 0.10)])
        mb.poly("white", [T(a[0], a[1], 0), T(b[0], b[1], 0), T(b[0], b[1], 0.10), T(a[0], a[1], 0.10)])

    # gold ring
    for i in range(len(outline)):
        j = (i + 1) % len(outline)
        a, b = outline[i], outline[j]
        du, dv = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(du, dv)
        if ln < 1e-6:
            continue
        nu, nv = -dv / ln, du / ln
        # Keep the gold ring inside the shield perimeter.  On the right edge
        # the previous outward offset added 4.4 m to u and broke the 25 m cap.
        a0, a1 = (a[0] + nu * 3.6, a[1] + nv * 3.6), (b[0] + nu * 3.6, b[1] + nv * 3.6)
        b0, b1 = (a[0] + nu * 4.4, a[1] + nv * 4.4), (b[0] + nu * 4.4, b[1] + nv * 4.4)
        mb.poly("gold", [T(a0[0], a0[1], 0.10), T(a1[0], a1[1], 0.10), T(b1[0], b1[1], 0.10), T(b0[0], b0[1], 0.10)])
        mb.poly("gold", [T(a0[0], a0[1], 0), T(a1[0], a1[1], 0), T(a1[0], a1[1], 0.10), T(a0[0], a0[1], 0.10)])
        mb.poly("gold", [T(b0[0], b0[1], 0), T(b1[0], b1[1], 0), T(b1[0], b1[1], 0.10), T(b0[0], b0[1], 0.10)])

    # eagle: tail, body, wings, head, beak, talons
    tail = [(31, -4.5), (31, 4.5), (17, 9), (14, 0), (17, -9)]
    body = [(28, 0), (34, -5), (56, -6), (62, -4), (62, 4), (56, 6), (34, 5)]
    head = [(62, -3.5), (70, -3), (73, -1), (73, 3), (70, 4), (62, 3.5)]

    for poly, w, slot in [(tail, 0.14, "white"), (body, 0.20, "white"), (head, 0.32, "white")]:
        for i in range(len(poly)):
            j = (i + 1) % len(poly)
            k = (i + 2) % len(poly)
            mb.poly(slot, [T(poly[i][0], poly[i][1], w), T(poly[j][0], poly[j][1], w), T(poly[k][0], poly[k][1], w)])

    # wings
    W_VEC = (-s, 0, c)
    for side in (-1, 1):
        feathers = []
        for k in range(6):
            phi = math.radians(35 + 11 * k)
            length = 22 - 0.8 * k
            base = (58 - 2.6 * k, side * (6 + 1.2 * k))
            tip = (base[0] + length * math.cos(phi), base[1] + side * length * math.sin(phi))
            feathers.append((base, tip))
        notches = []
        for k in range(5):
            p0 = (feathers[k][0][0] * 0.4 + feathers[k][1][0] * 0.6, feathers[k][0][1] * 0.4 + feathers[k][1][1] * 0.6)
            p1 = (feathers[k + 1][0][0] * 0.4 + feathers[k + 1][1][0] * 0.6, feathers[k + 1][0][1] * 0.4 + feathers[k + 1][1][1] * 0.6)
            notches.append(((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2))
        wing_poly = [(60, side * 5.5)]
        for k in range(6):
            wing_poly.append(feathers[k][1])
            if k < 5:
                wing_poly.append(notches[k])
        wing_poly += [(41, side * 25), (40, side * 17), (44, side * 9), (50, side * 6.2)]
        for i in range(len(wing_poly)):
            j = (i + 1) % len(wing_poly)
            k = (i + 2) % len(wing_poly)
            mb.poly("white", [T(wing_poly[i][0], wing_poly[i][1], 0.26), T(wing_poly[j][0], wing_poly[j][1], 0.26),
                              T(wing_poly[k][0], wing_poly[k][1], 0.26)], W_VEC)

    # beak
    beak = [(69.5, -2.5), (68.5, -7.5), (72.5, -1.5)]
    mb.poly("gold", [T(p[0], p[1], 0.40) for p in beak], W_VEC)

    # talons
    for side in (-1, 1):
        talon = [(35, side * 2), (35, side * 5), (27, side * 10.5), (25.5, side * 8)]
        mb.poly("gold", [T(p[0], p[1], 0.40) for p in talon], W_VEC)

    # supports
    for u, v in [(21, -18), (21, 18), (46, -25), (46, 25), (71, -25), (71, 25)]:
        cg.prism(mb, "steel", (0, v, 0), T(u, v, -0.4), 0.4, 0.3, 6)
    for v in (-22, 22):
        cg.bar(mb, "steel", T(10, v, -0.62), T(78, v, -0.62), 0.2)

    return mb

def hangar():
    """Quonset hut (80 m × 36 m × 16 m)."""
    mb = builder()
    a_semi, b_semi = 18.0, 16.0
    seg = 14
    for i in range(seg):
        # Upper half of the Quonset cross-section: z stays on or above ground.
        a0 = math.pi * i / seg
        a1 = math.pi * (i + 1) / seg
        y0, z0 = a_semi * math.cos(a0), b_semi * math.sin(a0)
        y1, z1 = a_semi * math.cos(a1), b_semi * math.sin(a1)
        n0 = norm((0, b_semi * math.cos(a0), a_semi * math.sin(a0)))
        n1 = norm((0, b_semi * math.cos(a1), a_semi * math.sin(a1)))
        n = norm((n0[0] + n1[0], n0[1] + n1[1], n0[2] + n1[2]))
        mb.poly("olive", [(-40, y0, z0), (40, y0, z0), (40, y1, z1), (-40, y1, z1)], n)

    # ribs
    for k in range(11):
        x = -40 + 8 * k
        x = max(-39.8, min(39.8, x))
        for i in range(seg):
            a0 = math.pi * i / seg
            a1 = math.pi * (i + 1) / seg
            am = (a0 + a1) / 2
            # skip rib segments near the roundel
            if abs(x) < 7.5:
                a_deg = math.degrees(am)
                if 40 <= a_deg <= 100:
                    continue
            y, z = a_semi * math.cos(am), b_semi * math.sin(am)
            n = norm((0, b_semi * math.cos(am), a_semi * math.sin(am)))
            c = (x, y + n[1] * 0.25, z + n[2] * 0.25)
            mb.obox("dark", c, (1, 0, 0), (0, n[1], n[2]), (0, -n[2], n[1]), 0.2, 0.1, 0.1, skip=("nz",))

    # end walls
    pts = []
    for i in range(seg + 1):
        a = math.pi * i / seg
        pts.append((a_semi * math.cos(a), b_semi * math.sin(a)))
    for x, sgn in ((-40, 1), (40, -1)):
        for i in range(1, len(pts)):
            mb.poly("olive", [(x, pts[i - 1][0], pts[i - 1][1]), (x, pts[i][0], pts[i][1]), (x, 0, 0)], (sgn, 0, 0))

    # doors
    for x in (-40.05, 40.05):
        for y in (-9, 9):
            sgn = -1 if x < 0 else 1
            mb.box("dark", x, x + sgn * 0.1, y, y + 9 if y < 0 else y - 9, 0, 10)

    # sign boxes
    for x in (-40.05, 40.05):
        sgn = -1 if x < 0 else 1
        mb.box("bright", x, x + sgn * 0.1, -6, 6, 11.5, 13)

    # ridge band
    a_out, b_out = 18.08, 16.08
    for i in range(2):
        a0 = math.pi / 2 + math.pi * i / seg
        a1 = math.pi / 2 + math.pi * (i + 1) / seg
        y0, z0 = a_out * math.cos(a0), b_out * math.sin(a0)
        y1, z1 = a_out * math.cos(a1), b_out * math.sin(a1)
        n = norm((0, b_out * math.cos((a0 + a1) / 2), a_out * math.sin((a0 + a1) / 2)))
        mb.poly("bright", [(-40, y0, z0), (40, y0, z0), (40, y1, z1), (-40, y1, z1)], n)

    # roundel on +y side at x=0
    a_deg = 50.0
    r_disk = 7.0
    pts_disk = []
    for i in range(24):
        ang = 2 * math.pi * i / 24
        pts_disk.append((r_disk * math.cos(ang), r_disk * math.sin(ang)))
    y_c = a_semi * math.cos(math.radians(a_deg))
    z_c = b_semi * math.sin(math.radians(a_deg))
    n_c = norm((0, b_semi * math.cos(math.radians(a_deg)), a_semi * math.sin(math.radians(a_deg))))
    u_c = (1, 0, 0)
    v_c = norm((0, -n_c[2], n_c[1]))

    def R(dx, dz):
        return (0, y_c + dx * u_c[0] + dz * v_c[1] + n_c[1] * 0.10, z_c + dx * u_c[2] + dz * v_c[2] + n_c[2] * 0.10)

    # white rings
    for r_in, r_out in [(0, 1.75), (1.75, 3.5), (3.5, 5.25), (5.25, 7)]:
        for i in range(24):
            j = (i + 1) % 24
            a0, a1 = 2 * math.pi * i / 24, 2 * math.pi * j / 24
            x0, z0 = r_in * math.cos(a0), r_in * math.sin(a0)
            x1, z1 = r_out * math.cos(a0), r_out * math.sin(a0)
            x2, z2 = r_out * math.cos(a1), r_out * math.sin(a1)
            x3, z3 = r_in * math.cos(a1), r_in * math.sin(a1)
            mb.poly("white", [R(x0, z0), R(x1, z1), R(x2, z2), R(x3, z3)], n_c)

    # star
    pts_star = []
    for i in range(5):
        a_out = 2 * math.pi * i / 5 - math.pi / 2
        a_in = a_out + math.pi / 5
        pts_star.append((6.0 * math.cos(a_out), 6.0 * math.sin(a_out)))
        pts_star.append((2.4 * math.cos(a_in), 2.4 * math.sin(a_in)))
    for i in range(len(pts_star)):
        j = (i + 1) % len(pts_star)
        mb.poly("bright", [R(0, 0), R(pts_star[i][0], pts_star[i][1]), R(pts_star[j][0], pts_star[j][1])], n_c)

    return mb

def radar_mast():
    """Tall radar mast (33.8 m with antenna)."""
    mb = builder()
    legs = [((-3.5, -3.5, 0), (-1.2, -1.2, 28)), ((3.5, -3.5, 0), (1.2, -1.2, 28)),
            ((3.5, 3.5, 0), (1.2, 1.2, 28)), ((-3.5, 3.5, 0), (-1.2, 1.2, 28))]
    for k, (p0, p1) in enumerate(legs):
        for i in range(7):
            z0, z1 = i * 4.0, (i + 1) * 4.0
            z0, z1 = min(z0, 28), min(z1, 28)
            slot = "bright" if i % 2 == 0 else "white"
            f = lambda z: (p0[0] + (p1[0] - p0[0]) * z / 28, p0[1] + (p1[1] - p0[1]) * z / 28, z)
            cg.prism(mb, slot, f(z0), f(z1), 0.22, 0.18, 6)

    # X-bracing
    for z in range(0, 28, 4):
        for (i, j) in [(0, 1), (1, 2), (2, 3), (3, 0)]:
            f = lambda idx, zz: (legs[idx][0][0] + (legs[idx][1][0] - legs[idx][0][0]) * zz / 28,
                                  legs[idx][0][1] + (legs[idx][1][1] - legs[idx][0][1]) * zz / 28, zz)
            cg.bar(mb, "steel", f(i, z), f(j, z + 4), 0.08)
            cg.bar(mb, "steel", f(i, z + 4), f(j, z), 0.08)

    # platform
    mb.box("blue", -1.8, 1.8, -1.8, 1.8, 28, 28.3)
    mb.box("dark", -1.2, 1.2, -1.2, 1.2, 28.3, 30.5)

    # antenna
    cg.bar(mb, "steel", (0, -3, 31), (0, 3, 31), 0.25)
    cg.prism(mb, "steel", (0, 0, 30.5), (0, 0, 33.3), 0.2, 0.15, 6)
    mb.box("glow", -0.3, 0.3, -0.3, 0.3, 33.3, 33.6)

    return mb

def marker():
    """Small marker post (4.5 m)."""
    mb = builder()
    mb.box("concrete", -0.3, 0.3, -0.3, 0.3, 0, 0.25)
    cg.prism(mb, "white", (0, 0, 0.25), (0, 0, 3.6), 0.12, 0.10, 6)
    mb.box("bright", -0.15, 0.15, -0.7, 0.7, 3.0, 3.6)
    mb.box("glow", -0.2, 0.2, -0.6, 0.6, 3.6, 4.5)
    return mb

def helipad():
    """Helipad (22 m × 22 m)."""
    mb = builder()
    mb.box("grey", -11, 11, -11, 11, 0, 0.32, skip=("nz",))
    # H marking
    mb.box("marking", -4, 4, -3.2, -2, 0.34, 0.36)
    mb.box("marking", -4, 4, 2, 3.2, 0.34, 0.36)
    mb.box("marking", -0.6, 0.6, -2, 2, 0.34, 0.36)
    # ring
    for i in range(32):
        a0, a1 = 2 * math.pi * i / 32, 2 * math.pi * (i + 1) / 32
        for r_in, r_out in [(8.5, 9.3)]:
            x0, y0 = r_in * math.cos(a0), r_in * math.sin(a0)
            x1, y1 = r_out * math.cos(a0), r_out * math.sin(a0)
            x2, y2 = r_out * math.cos(a1), r_out * math.sin(a1)
            x3, y3 = r_in * math.cos(a1), r_in * math.sin(a1)
            mb.poly("marking", [(x0, y0, 0.34), (x1, y1, 0.34), (x2, y2, 0.34), (x3, y3, 0.34)], Z)
    # corner lights
    for x, y in [(-10.2, -10.2), (10.2, -10.2), (10.2, 10.2), (-10.2, 10.2)]:
        mb.box("glow", x - 0.3, x + 0.3, y - 0.3, y + 0.3, 0.32, 0.5)
    return mb

def fuel_tank():
    """Horizontal fuel tank (10 m × 3.2 m dia)."""
    mb = builder()
    sides = 16
    for i in range(sides):
        a0, a1 = 2 * math.pi * i / sides, 2 * math.pi * (i + 1) / sides
        y0, z0 = 1.6 * math.cos(a0), 1.9 + 1.6 * math.sin(a0)
        y1, z1 = 1.6 * math.cos(a1), 1.9 + 1.6 * math.sin(a1)
        n = (0, math.cos((a0 + a1) / 2), math.sin((a0 + a1) / 2))
        mb.poly("white", [(-5, y0, z0), (5, y0, z0), (5, y1, z1), (-5, y1, z1)], n)

    # saddles
    for x in (-3, 3):
        mb.box("concrete", x - 0.3, x + 0.3, -1.2, 1.2, 0, 0.9)

    # band
    sides_band = 16
    for i in range(sides_band):
        a0, a1 = 2 * math.pi * i / sides_band, 2 * math.pi * (i + 1) / sides_band
        y0, z0 = 1.63 * math.cos(a0), 1.9 + 1.63 * math.sin(a0)
        y1, z1 = 1.63 * math.cos(a1), 1.9 + 1.63 * math.sin(a1)
        n = (0, math.cos((a0 + a1) / 2), math.sin((a0 + a1) / 2))
        mb.poly("bright", [(-1, y0, z0), (1, y0, z0), (1, y1, z1), (-1, y1, z1)], n)

    # ladder
    cg.bar(mb, "steel", (5.15, -0.25, 0), (5.15, -0.25, 3.4), 0.05)
    cg.bar(mb, "steel", (5.15, 0.25, 0), (5.15, 0.25, 3.4), 0.05)
    for z in [0.4 * i for i in range(9)]:
        cg.bar(mb, "steel", (5.15, -0.25, z), (5.15, 0.25, z), 0.04)

    return mb

def _container_box(mb, slot, cx, cy, z0, L, W, H, skip):
    """Container box with corner bars and ribs."""
    mb.box(slot, cx - L / 2, cx + L / 2, cy - W / 2, cy + W / 2, z0, z0 + H, skip=skip)
    for dx in (-L / 2 + 0.15, L / 2 - 0.15):
        for dy in (-W / 2 + 0.15, W / 2 - 0.15):
            cg.bar(mb, "steel", (cx + dx + 0.01, cy + dy + 0.01, z0), (cx + dx + 0.01, cy + dy + 0.01, z0 + H), 0.05)
    for dy in (-W / 2, W / 2):
        for z in (z0 + 0.3, z0 + H - 0.3):
            cg.bar(mb, "dark", (cx - L / 2 + 0.3, cy + dy + 0.01, z), (cx + L / 2 - 0.3, cy + dy + 0.01, z), 0.04)
    return mb

def container_stack():
    """Stack of 3 containers (2 base + 1 on top)."""
    mb = builder()
    L, W, H = 12.2, 2.44, 2.6
    _container_box(mb, "blue", -W / 2 - 0.1, 0, 0, L, W, H, ())
    _container_box(mb, "olive", W / 2 + 0.1, 0, 0, L, W, H, ())
    _container_box(mb, "steel", 0, 0, H, L, W, H, ("nz",))
    return mb

def cargo_truck():
    """6-wheel cargo truck with canvas cover."""
    mb = builder()
    L, W = 8.0, 2.4
    # chassis
    mb.box("dark", -L / 2, L / 2, -W / 2, W / 2, 0.6, 1.0)
    # cab
    mb.box("olive", L / 2 - 1.6, L / 2, -W / 2 + 0.2, W / 2 - 0.2, 1.0, 3.0)
    mb.box("glass", L / 2 - 1.4, L / 2 - 0.2, -W / 2 + 0.35, W / 2 - 0.35, 2.0, 2.8)
    # bed frame
    mb.box("olive", -L / 2 + 0.5, L / 2 - 1.8, -W / 2, W / 2, 1.0, 1.5, skip=("pz",))
    # canvas
    n = 8
    for i in range(n):
        x0 = -L / 2 + 0.5 + (L - 2.3) * i / n
        x1 = -L / 2 + 0.5 + (L - 2.3) * (i + 1) / n
        z0, z1 = 1.5, 2.9
        for y, sgn in [(-W / 2, -1), (W / 2, 1)]:
            mb.poly("khaki", [(x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)], (0, sgn, 0))
    # roof
    for i in range(n):
        x0 = -L / 2 + 0.5 + (L - 2.3) * i / n
        x1 = -L / 2 + 0.5 + (L - 2.3) * (i + 1) / n
        mb.poly("khaki", [(x0, -W / 2, 2.9), (x1, -W / 2, 2.9), (x1, 0, 3.2), (x0, 0, 3.2)])
        mb.poly("khaki", [(x0, W / 2, 2.9), (x1, W / 2, 2.9), (x1, 0, 3.2), (x0, 0, 3.2)])
    # gable ends
    for x in (-L / 2 + 0.5, L / 2 - 1.8):
        sgn = 1 if x < 0 else -1
        mb.poly("khaki", [(x, -W / 2, 1.5), (x, W / 2, 1.5), (x, 0, 3.2)], (sgn, 0, 0))
    # door stripe
    mb.box("bright", L / 2 - 0.05, L / 2, -W / 2 + 0.5, W / 2 - 0.5, 1.5, 1.7)
    # wheels
    for x in [-L / 2 + 1.2, -L / 2 + 2.6, L / 2 - 1.0]:
        for y_sgn in (-1, 1):
            for y_off in (1.0, 1.35):
                y = y_sgn * y_off
                cg.prism(mb, "char", (x, y, 0), (x, y, 0), 0.55, 0.55, 12)
    return mb

def rubble(seed):
    """Rubble heap (heightfield)."""
    r = rng(seed)
    mb = builder()
    rad = r.uniform(6, 14)
    peak = r.uniform(1.2, 3.0)
    nx, ny = int(rad * 2 / 1.0) + 1, int(rad * 2 / 1.0) + 1

    def hfun(x, y):
        d2 = (x ** 2 + y ** 2) / (rad ** 2)
        mound = max(0, 1 - d2) ** 1.5
        noise = r.uniform(-0.15, 0.15)
        return -0.15 + (peak + 0.15) * mound + noise * mound

    mb.heightfield("rubble", -rad, -rad, 2 * rad, 2 * rad, nx, ny, hfun)

    # debris
    for _ in range(int(rad * 1.5)):
        x, y = r.uniform(-rad * 0.8, rad * 0.8), r.uniform(-rad * 0.8, rad * 0.8)
        z = hfun(x, y) + r.uniform(0, 0.3)
        if z < 0:
            continue
        slot = "grey" if r.random() < 0.6 else "char"
        s = r.uniform(0.3, 1.2)
        yaw = r.uniform(0, 360)
        tilt = r.uniform(-25, 25)
        yr = math.radians(yaw)
        tr = math.radians(tilt)
        ax = (math.cos(yr) * math.cos(tr), math.sin(yr) * math.cos(tr), math.sin(tr))
        ay = (-math.sin(yr), math.cos(yr), 0)
        az = geom.cross(ax, ay)
        mb.obox(slot, (x, y, z), ax, ay, az, s, s * 0.6, s * 0.4)

    return mb

def dirt_patch(seed):
    """Dirt mound (heightfield)."""
    r = rng(seed)
    mb = builder()
    w, h = r.uniform(35, 45), r.uniform(25, 35)
    nx, ny = int(w / 2) + 1, int(h / 2) + 1

    def hfun(x, y):
        d2 = (x / (w / 2)) ** 2 + (y / (h / 2)) ** 2
        mound = max(0, min(1, (1 - d2) * 3))
        noise = r.uniform(-0.05, 0.05)
        return -0.1 + 0.45 * mound + noise

    mb.heightfield("dirt", -w / 2, -h / 2, w, h, nx, ny, hfun)
    return mb

def ruin_lots(seed, flip=False):
    """Low-rise ruin lots for one wing."""
    r = rng(seed)
    lots = []

    # row lots
    y = -62.0
    widths = hm.split_run(108.0, r, 9.0, 16.0)
    for i, w in enumerate(widths):
        y0, y1 = y, y + w
        poly = [(0.0, y1), (0.0, y0), (16.0, y0), (16.0, y1)]
        types = ["street", "end" if i == 0 else "party", "court", "party"]
        lots.append((poly, types, False))
        y = y1

    # corner lot
    poly = [(0.0, 62.0), (0.0, 46.0), (16.0, 46.0), (16.0, 62.0)]
    types = ["street", "party", "party", "street"]
    lots.append((poly, types, True))

    # wing lots
    wing_w = r.uniform(40.0, 60.0)
    ws = hm.split_run(wing_w, r, 9.0, 16.0)
    x = 16.0
    for i, w in enumerate(ws):
        poly = [(x, 46.0), (x + w, 46.0), (x + w, 62.0), (x, 62.0)]
        types = ["court", "end" if i == len(ws) - 1 else "party", "street", "party"]
        lots.append((poly, types, False))
        x += w

    if flip:
        out = []
        for poly, types, corner in lots:
            k = len(poly)
            poly_f = [(p[0], -p[1]) for p in reversed(poly)]
            types_f = [types[(k - 2 - j) % k] for j in range(k)]
            out.append((poly_f, types_f, corner))
        lots = out

    hm_lots = []
    for poly, types, corner in lots:
        lot = hm.Lot(poly, types, r, hm.pick_floors(r, corner, True), corner=corner, low=True)
        lot.damage = "collapsed" if r.random() < 0.6 else "burnt"
        hm_lots.append(lot)

    return hm_lots

def ruin_piece(seed, flip=False):
    """Low-rise ruin mesh (one L-shaped wing)."""
    return hm.piece_mesh(ruin_lots(seed, flip))

# ---------------------------------------------------------------- mesh registry
MESHES = {
    "SM_Blue_SandbagWall": lambda: sandbag_wall(),
    "SM_Blue_Barrier": lambda: barrier(),
    "SM_Blue_Wire": lambda: wire_obstacle(),
    "SM_Blue_Flag": lambda: flag(),
    "SM_Blue_Banner": lambda: banner(),
    "SM_Blue_Tent_Cmd": lambda: tent(12, 8, 2.0, 4.5),
    "SM_Blue_Tent_Medical": lambda: tent(10, 6, 1.8, 4.0, True),
    "SM_Blue_Tent_Field": lambda: tent(7, 4.5, 1.5, 3.2),
    "SM_Blue_Container": lambda: container(),
    "SM_Blue_RepairTruck": lambda: repair_truck(),
    "SM_Blue_Radar": lambda: radar(),
    "SM_Blue_Generator": lambda: generator(),
    "SM_Blue_LightTower": lambda: light_tower(),
    "SM_Blue_Signal": lambda: signal(),
    "SM_Blue_MapTable": lambda: map_table(),
    # B5 expansion
    "SM_Blue_EagleShield": lambda: eagle_shield(),
    "SM_Blue_Hangar": lambda: hangar(),
    "SM_Blue_RadarMast": lambda: radar_mast(),
    "SM_Blue_Marker": lambda: marker(),
    "SM_Blue_Helipad": lambda: helipad(),
    "SM_Blue_FuelTank": lambda: fuel_tank(),
    "SM_Blue_ContainerStack": lambda: container_stack(),
    "SM_Blue_CargoTruck": lambda: cargo_truck(),
    "SM_Blue_Rubble_0": lambda: rubble(7700),
    "SM_Blue_Rubble_1": lambda: rubble(7701),
    "SM_Blue_Rubble_2": lambda: rubble(7702),
    "SM_Blue_Rubble_3": lambda: rubble(7703),
    "SM_Blue_Dirt_0": lambda: dirt_patch(7800),
    "SM_Blue_Dirt_1": lambda: dirt_patch(7801),
    "SM_Blue_Ruin_A": lambda: ruin_piece(7101, False),
    "SM_Blue_Ruin_B": lambda: ruin_piece(7203, True),
}

RUIN_MESHES = {"SM_Blue_Ruin_A", "SM_Blue_Ruin_B"}

# ---------------------------------------------------------------- prop layout
def _under_shield(x, y):
    """Is (x, y) under one of the three shields?"""
    for yc in (-500, 0, 500):
        if abs(y - yc) <= 36:
            return True
    return False

def prop_layout():
    """Complete south base layout: (mesh, loc_m, rot_deg, extra_dict)."""
    out = []

    def put(mesh, x, y, z=0.0, yaw=0.0, **extra):
        out.append((mesh, (x, y, z), (0.0, yaw, 0.0), extra))

    # ================================================================ ROW -1 (front line x ~ -822 to -962)
    # trees
    for y in range(-1390, 1000, 13):
        if abs(y % 200) < 16:
            continue
        i = (y + 1390) // 13
        put("SM_Tree_%d" % (i % 4), -822, y, 0.15, (i * 37) % 360, lib="City", scale=0.98)

    # defence line y -888..968
    y = -888
    while y <= 968:
        # wire
        put("SM_Blue_Wire", -838, y, 0.0, 90.0)
        y += 8

    y = -888
    while y <= 968:
        # barriers
        put("SM_Blue_Barrier", -843.5, y, 0.0, 90.0)
        y += 4.5

    y = -888
    while y <= 968:
        # sandbags
        put("SM_Blue_SandbagWall", -850, y, 0.0, 90.0)
        y += 16

    # flags (every 40 m, skip shields, y <= 620)
    for y in range(-888, 628, 40):
        if y > 620:
            continue
        if _under_shield(-857, y):
            continue
        put("SM_Blue_Flag", -857, y, 0.0, 0.0)

    # banners (every 80 m, skip shields, y <= 620)
    for y in range(-888, 628, 80):
        if y > 620:
            continue
        if _under_shield(-862, y):
            continue
        put("SM_Blue_Banner", -862, y, 0.0, 0.0)

    # markers (every 25 m, offset 6.25 from trees, skip |y-200j|<16)
    for y in range(-1390, 1000, 25):
        if abs(y % 200) < 16:
            continue
        put("SM_Blue_Marker", -813, y + 6.25, 0.0, 0.0, light="signal", light_z=4.7)

    # eagle shields at y -500, 0, 500
    for yc in (-500, 0, 500):
        put("SM_Blue_EagleShield", -927, yc, 0.0, 0.0, role="shield")
        # side strips: tents/containers in [yc-66, yc-38] and [yc+38, yc+66]
        for dy, rot in [(yc - 52, 0), (yc + 52, 0)]:
            put("SM_Blue_Tent_Field", -930, dy, 0.0, rot)
        for dy in (yc - 58, yc + 58):
            put("SM_Blue_Container", -945, dy, 0.18, 90.0)
        # truck/APC in front x -962..-932, |y-yc|<=20
        put("SM_M1A2_Blue", -947, yc, 0.18, 0.0, vehicle=True)

    # y -1300 / -1100: vehicle parks
    for yc in (-1300, -1100):
        for dx, dy in [(0, -40), (0, 40), (15, -40), (15, 40)]:
            put("SM_M1A2_Blue", -950 + dx, yc + dy, 0.18, 0.0, vehicle=True)
        put("SM_Blue_Generator", -925, yc, 0.0, 0.0)
        put("SM_Blue_LightTower", -920, yc + 50, 0.0, 0.0, light="point")

    # y -900: radar mast cell
    put("SM_Blue_RadarMast", -885, -870, 0.0, 0.0, radar=True, light="signal", light_z=33.8)
    for dx, dy in [(0, -60), (15, -60)]:
        put("SM_Blue_ContainerStack", -950 + dx, -900 + dy, 0.18, 0.0)
    put("SM_Blue_Generator", -920, -920, 0.0, 0.0)
    put("SM_Blue_LightTower", -915, -880, 0.0, 0.0, light="point")
    for dx in (0, 15):
        put("SM_Blue_CargoTruck", -945 + dx, -940, 0.18, 90.0)

    # y -700: platoon
    for x, rank in [(-905, 0), (-930, 1)]:
        for i in range(4):
            put("SM_M1A2_Blue", x, -700 + i * 12, 0.18, 0.0, vehicle=True)
    for i in range(2):
        put("SM_ArmoredCar_Blue", -920, -750 + i * 12, 0.18, 0.0, vehicle=True)
    put("SM_Blue_FuelTank", -950, -700, 0.18, 90.0)
    put("SM_Blue_Tent_Field", -945, -670, 0.0, 0.0)
    put("SM_Blue_LightTower", -910, -670, 0.0, 0.0, light="point")

    # y -300: hangar
    put("SM_Blue_Hangar", -895, -300, 0.0, 90.0, role="hangar")
    put("SM_M1A2_Blue", -895, -352, 0.18, 270.0, vehicle=True)
    put("SM_M1A2_Blue", -895, -248, 0.18, 90.0, vehicle=True)
    put("SM_Blue_CargoTruck", -935, -330, 0.18, 0.0)
    put("SM_Blue_CargoTruck", -935, -270, 0.18, 0.0)
    put("SM_Blue_FuelTank", -950, -300, 0.18, 90.0)
    put("SM_Blue_LightTower", -910, -300, 0.0, 0.0, light="point")

    # y -100: platoon
    for x in (-905, -930):
        for i in range(4):
            put("SM_M1A2_Blue", x, -160 + i * 12, 0.18, 0.0, vehicle=True)
    for i in range(2):
        put("SM_ArmoredCar_Blue", -920, -145 + i * 12, 0.18, 0.0, vehicle=True)
    put("SM_Blue_LightTower", -910, -110, 0.0, 0.0, light="point")

    # y 100: field camp
    put("SM_Blue_Tent_Cmd", -915, 110, 0.0, 0.0)
    put("SM_Blue_SandbagWall", -927, 98, 0.0, 90.0)
    put("SM_Blue_SandbagWall", -903, 98, 0.0, 90.0)
    put("SM_Blue_SandbagWall", -915, 86, 0.0, 0.0)
    put("SM_Blue_SandbagWall", -915, 122, 0.0, 0.0)
    put("SM_Blue_Tent_Medical", -948, 75, 0.0, 0.0)
    put("SM_Blue_Tent_Field", -945, 115, 0.0, 0.0)
    put("SM_Blue_Tent_Field", -930, 135, 0.0, 0.0)
    put("SM_Blue_MapTable", -890, 110, 0.0, 0.0)
    put("SM_Blue_Signal", -895, 120, 0.0, 0.0, light="signal")
    put("SM_Blue_LightTower", -910, 140, 0.0, 0.0, light="point")

    # y 300: platoon + repair
    for x in (-905, -930):
        for i in range(4):
            put("SM_M1A2_Blue", x, 300 + i * 12, 0.18, 0.0, vehicle=True)
    put("SM_Blue_RepairTruck", -950, 300, 0.18, 0.0)
    put("SM_Blue_LightTower", -910, 330, 0.0, 0.0, light="point")

    # y 700 / 900: ruins + rubble
    for yc, ruin_name in [(700, "SM_Blue_Ruin_A"), (900, "SM_Blue_Ruin_B")]:
        put(ruin_name, -940, yc, 0.0, 0.0, lib="Blue", role="ruin")
        put("SM_Blue_Rubble_0", -950, yc - 50, 0.0, 0.0)
        put("SM_Blue_Rubble_1", -950, yc + 50, 0.0, 0.0)
        put("SM_Car_Burnt_0", -945, yc - 35, 0.0, (yc * 17) % 360, lib="City")
        put("SM_Car_Burnt_1", -945, yc + 35, 0.0, (yc * 23) % 360, lib="City")

    # dirt patches (avoid vehicles)
    for yc in (-1200, -1000, -800, -600, -400, -200, 0, 200, 400, 600, 800):
        if yc == -700 or yc == -100 or yc == 300 or yc == 0:
            continue
        put("SM_Blue_Dirt_0", -935, yc, 0.0, 0.0)

    # ================================================================ ROW -2 (x ~ -1100)
    cells_2 = [
        (-1300, [("vehicle_park", 0)]),
        (-1100, [("tent_grid", 0)]),
        (-900, [("containers", 0)]),
        (-700, [("helipad", 0)]),
        (-500, [("tents", 0)]),
        (-300, [("vehicle_repair", 0)]),
        (-100, [("hq", 0)]),
        (100, [("medical_heli", 0)]),
        (300, [("fuel", 0)]),
        (500, [("tents", 0)]),
        (700, [("containers", 0)]),
        (900, [("vehicle_park", 0)]),
    ]

    for yc, roles in cells_2:
        role = roles[0][0]
        if role == "vehicle_park":
            for dx, dy in [(0, -40), (0, 40), (15, -40), (15, 40)]:
                put("SM_M1A2_Blue", -1100 + dx, yc + dy, 0.18, 0.0, vehicle=True)
        elif role == "tent_grid":
            for dx in (0, 15):
                for dy in (-50, -30, -10, 10, 30, 50):
                    put("SM_Blue_Tent_Field", -1105 + dx, yc + dy, 0.0, 0.0)
        elif role == "containers":
            for dx in (0, 15):
                for dy in (-50, -30, -10, 10, 30, 50):
                    put("SM_Blue_Container", -1105 + dx, yc + dy, 0.18, 90.0)
        elif role == "helipad":
            put("SM_Blue_Helipad", -1100, yc, 0.0, 0.0)
        elif role == "tents":
            for dx in (0, 15):
                for dy in (-40, 0, 40):
                    put("SM_Blue_Tent_Field", -1105 + dx, yc + dy, 0.0, 0.0)
        elif role == "vehicle_repair":
            for dx, dy in [(0, -40), (0, 40), (15, -40), (15, 40)]:
                put("SM_M1A2_Blue", -1100 + dx, yc + dy, 0.18, 0.0, vehicle=True)
            put("SM_Blue_RepairTruck", -1120, yc, 0.18, 0.0)
        elif role == "hq":
            put("SM_Blue_Tent_Cmd", -1100, yc, 0.0, 0.0)
            put("SM_Blue_MapTable", -1090, yc - 20, 0.0, 0.0)
            put("SM_Blue_MapTable", -1090, yc + 20, 0.0, 0.0)
        elif role == "medical_heli":
            put("SM_Blue_Tent_Medical", -1110, yc - 30, 0.0, 0.0)
            put("SM_Blue_Helipad", -1100, yc + 30, 0.0, 0.0)
        elif role == "fuel":
            for dx in (0, 15):
                for dy in (-40, 0, 40):
                    put("SM_Blue_FuelTank", -1105 + dx, yc + dy, 0.18, 90.0)

        put("SM_Blue_LightTower", -1090, yc, 0.0, 0.0, light="point")

    # ================================================================ ROW -3 (x ~ -1300)
    cells_3 = [
        (-1300, [("containers", 0)]),
        (-1100, [("fuel", 0)]),
        (-900, [("tents", 0)]),
        (-700, [("vehicles", 0)]),
        (-500, [("helipad", 0)]),
        (-300, [("containers", 0)]),
        (-100, [("tents", 0)]),
        (100, [("vehicles", 0)]),
        (300, [("helipad", 0)]),
        (500, [("radar_gen", 0)]),
        (700, [("tents", 0)]),
        (900, [("containers", 0)]),
    ]

    for yc, roles in cells_3:
        role = roles[0][0]
        if role == "containers":
            for dx in (0, 15):
                for dy in (-50, -30, -10, 10, 30, 50):
                    put("SM_Blue_Container", -1305 + dx, yc + dy, 0.18, 90.0)
        elif role == "fuel":
            for dx in (0, 15):
                for dy in (-40, 0, 40):
                    put("SM_Blue_FuelTank", -1305 + dx, yc + dy, 0.18, 90.0)
        elif role == "tents":
            for dx in (0, 15):
                for dy in (-40, 0, 40):
                    put("SM_Blue_Tent_Field", -1305 + dx, yc + dy, 0.0, 0.0)
        elif role == "vehicles":
            for dx, dy in [(0, -40), (0, 40), (15, -40), (15, 40)]:
                put("SM_M1A2_Blue", -1300 + dx, yc + dy, 0.18, 0.0, vehicle=True)
        elif role == "helipad":
            put("SM_Blue_Helipad", -1300, yc, 0.0, 0.0)
        elif role == "radar_gen":
            put("SM_Blue_Radar", -1300, yc, 0.0, 0.0)
            for dy in (-40, 40):
                put("SM_Blue_Generator", -1310, yc + dy, 0.0, 0.0)

        put("SM_Blue_LightTower", -1290, yc, 0.0, 0.0, light="point")

    return out

def light_layout():
    """Filter prop_layout for light sources: (mesh, loc_m, rot_deg, extra_dict)."""
    return [p for p in prop_layout() if p[3].get("light")]

# ---------------------------------------------------------------- main (standalone check)
if __name__ == "__main__":
    import zfight_check
    from collections import Counter

    SIGHT_K = 0.8 * 1202.0 / 929.0
    VEHICLE_BOUNDS = {
        "SM_M1A2_Blue": ((-4.1, -2.462, 0), (4.1, 2.462, 3.175)),
        "SM_ArmoredCar_Blue": ((-3.5, -1.8, 0), (3.5, 1.8, 3.0)),
    }

    print("=== Mesh stats ===")
    for name, fn in MESHES.items():
        mb = fn()
        b = mb.bounds()
        tris = mb.tri_count()
        print("%-30s %6d tri  bounds [%.1f..%.1f, %.1f..%.1f, %.1f..%.1f]" %
              (name, tris, b[0][0], b[1][0], b[0][1], b[1][1], b[0][2], b[1][2]))

    print("\n=== Prop layout ===")
    props = prop_layout()
    roles = Counter(p[3].get("role", "prop") for p in props)
    print("%d props:" % len(props), dict(roles))
    lights = light_layout()
    print("%d lights" % len(lights))

    print("\n=== Height pre-audit ===")
    errors = []
    for idx, (name, loc, rot, extra) in enumerate(props):
        if name in MESHES:
            mb = MESHES[name]()
            b = mb.bounds()
        elif name.startswith("SM_Tree_") or name.startswith("SM_Car_"):
            lib = extra.get("lib")
            if lib == "City":
                if name.startswith("SM_Tree_"):
                    b = ((-6.5, -6.5, -0.3), (6.5, 6.5, 13.0))
                else:
                    b = ((-2.5, -1.0, 0), (2.5, 1.0, 1.5))
            else:
                continue
        elif name in VEHICLE_BOUNDS:
            b = VEHICLE_BOUNDS[name]
        else:
            continue

        scale = extra.get("scale", 1.0)
        b = ((b[0][0] * scale, b[0][1] * scale, b[0][2] * scale),
             (b[1][0] * scale, b[1][1] * scale, b[1][2] * scale))

        yaw_rad = math.radians(rot[1])
        c, s = math.cos(yaw_rad), math.sin(yaw_rad)
        wc = []
        for x, y, z in [(b[0][0], b[0][1], b[0][2]), (b[1][0], b[0][1], b[0][2]),
                        (b[0][0], b[1][1], b[0][2]), (b[1][0], b[1][1], b[0][2]),
                        (b[0][0], b[0][1], b[1][2]), (b[1][0], b[0][1], b[1][2]),
                        (b[0][0], b[1][1], b[1][2]), (b[1][0], b[1][1], b[1][2])]:
            wx = loc[0] + x * c - y * s
            wy = loc[1] + x * s + y * c
            wz = loc[2] + z
            wc.append((wx, wy, wz))

        top = max(p[2] for p in wc)
        near_x = max(p[0] for p in wc)
        is_radar = bool(extra.get("radar"))
        hard = 35.0 if is_radar else 25.0
        sight = SIGHT_K * (-800.0 - near_x) if near_x < -800.0 else 0.0
        allowed = min(hard, sight)
        ok = near_x < -800.0 and top <= allowed + 1e-4

        if not ok:
            errors.append((idx, name, loc, top, near_x, allowed))
            print("  [%d] %s at (%.1f, %.1f): top %.2f m, near_x %.2f m, allowed %.2f m - FAIL" %
                  (idx, name, loc[0], loc[1], top, near_x, allowed))

    if errors:
        print("HEIGHT CHECK FAILED: %d props exceed limits" % len(errors))
        sys.exit(1)
    else:
        print("HEIGHT CHECK PASS: all %d props within limits" % len(props))

    print("\n=== zfight self-check ===")
    for name in ["SM_Blue_EagleShield", "SM_Blue_Hangar", "SM_Blue_Ruin_A", "SM_Blue_Ruin_B"]:
        if name not in MESHES:
            continue
        mb = MESHES[name]()
        tris = zfight_check.tris_of(mb, 0, 0.0, name)
        hits, where = zfight_check.audit(tris, min_area=0.02)
        if hits:
            tot = sum(hits.values())
            # Keep standalone diagnostics ASCII-safe on Windows GBK consoles.
            print("  %s: %.1f m2 in %d pairs" % (name, tot, len(hits)))
            for pair, area in sorted(hits.items(), key=lambda kv: -kv[1])[:5]:
                w = where[pair]
                print("    %-40s %8.2f m2" % (" vs ".join(pair), area))
        else:
            print("  %s: no overlap" % name)

    print("\nblue base B5 layout ready")
