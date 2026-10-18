"""Haussmann block generator (pure Python on geom.MeshBuilder, no `unreal` import; testable with CPython).

Block-local frame in metres: one board cell holds one block centred on the origin, street facades at +-81 m,
building depth 16 m, a courtyard inside. `l_piece` fills the SW corner (chamfered "pan coupe"); rotating it by
0/90/180/270 deg gives the four corners. `infill_piece` closes the 22 m gap between two L-pieces on the south side.

Every piece is split into lots (individual buildings, 11-22 m frontage) with their own floor count, stone tint
(vertex colour R), shop palette (G) and soot (A = 1 - soot). Street facades follow the Haussmann grammar:
    ground floor 0-4.6 m rusticated with shops / porte-cochere, stone band 4.6-5.0 m
    upper floors from 5.0 m: moulded surrounds, window caps / pediments, continuous balconies on the first and
    last floor, balconets elsewhere, string courses, stepped cornice
    zinc mansard (4.0 m rise, 2.3 m run) with dormers, chimney stacks along the party walls
Damage modes per lot: "burnt" (soot, burnt-out windows, roof open) and "collapsed" (jagged broken walls,
exposed slabs, rubble heap and street spill).
Low-rise variant (B2, northern district): low=True gives faubourg-scale lots with 2-3 upper floors, a shallow
mansard (RISE_LOW) and half-height chimney stacks so the whole module stays under 18 m (LOW_MAX_H).
"""
import math

import geom
from geom import Frame, MeshBuilder, Z, norm, rect_minus_rects, rng, seg_normal

F = 81.0  # street facade offset from the block centre
DEPTH = 16.0
INNER = F - DEPTH  # courtyard facade offset
GAP = 11.0  # half width of the infill slot on each block side
CHAMFER = 5.0

SLOTS = ["stone", "rustic", "court", "zinc", "glass", "shop", "frame", "iron", "rail", "fascia",
         "awning", "awning2", "door", "chimney", "pot", "char", "rubble"]
SLOT_MATERIALS = {
    "stone": "MI_Stone_Limestone", "rustic": "MI_Stone_Rustic", "court": "MI_Stone_Stucco", "zinc": "MI_Zinc",
    "glass": "MI_Glass", "shop": "MI_Glass_Shop", "frame": "MI_Paint_Frame", "iron": "MI_Paint_Iron",
    "rail": "MI_Railing", "fascia": "MI_Paint_ShopFascia", "awning": "MI_Paint_Awning_Red",
    "awning2": "MI_Paint_Awning_Green", "door": "MI_Paint_Door", "chimney": "MI_Stone_Chimney",
    "pot": "MI_Paint_Terracotta", "char": "MI_Paint_Charred", "rubble": "MI_Ground_Rubble",
}

FLOORS = {
    4: [3.4, 3.2, 3.0, 2.9],
    5: [3.3, 3.1, 3.1, 2.9, 2.9],
    6: [3.3, 3.1, 3.0, 2.9, 2.8, 2.8],
}
FLOORS_LOW = {  # low-rise district: 2-3 upper floors over the same 5 m ground floor
    2: [3.2, 3.0],
    3: [3.0, 2.9, 2.7],
}
GROUND_TOP = 4.6
BAND_TOP = 5.0
CORNICE = 0.8
RISE = 4.0
RUN = 2.3
RISE_LOW = 2.2  # shallow mansard of the low-rise lots
CHIMNEY_LOW = 0.5  # chimney stack / pot height factor of the low-rise lots
DORMER_H = 2.0
DORMER_H_LOW = 1.4
LOW_MAX_H = 18.0  # hard ceiling (m) of every low-rise module, checked in __main__ / 04_haussmann_modules.py


# ---------------------------------------------------------------- lot description
class Lot:
    def __init__(self, poly, types, rnd, n_up=5, damage=None, corner=False, low=False):
        self.poly = poly
        self.types = types
        self.n_up = n_up
        self.low = low
        self.fh = (FLOORS_LOW if low else FLOORS)[n_up]
        self.rise = RISE_LOW if low else RISE
        self.chimney_k = CHIMNEY_LOW if low else 1.0
        self.dormer_h = DORMER_H_LOW if low else DORMER_H
        self.zf = []
        z = BAND_TOP
        for h in self.fh:
            self.zf.append(z)
            z += h
        self.H = z
        self.roof0 = self.H + CORNICE
        self.roof1 = self.roof0 + self.rise
        self.tint = rnd.random()
        self.pal = rnd.random()
        self.bay = rnd.uniform(3.05, 3.45)
        self.shops = corner or rnd.random() < 0.8
        self.awning = rnd.random() < (0.8 if corner else 0.5)
        self.awning_slot = "awning" if rnd.random() < 0.6 else "awning2"
        self.pediments = rnd.random() < 0.45
        self.balconies = {0, n_up - 1} if rnd.random() < 0.85 else {n_up - 1}
        self.damage = damage
        self.corner = corner
        self.seed = rnd.randint(0, 1 << 30)
        self.cut_h0 = rnd.uniform(6.5, 11.0)
        self.cut_phase = (rnd.uniform(0, 6.28), rnd.uniform(0, 6.28))

    def color(self):
        return (self.tint, self.pal, 1.0, 1.0)

    def cut(self, x, y, r):
        """Collapsed lots: broken wall height at local point (x, y)."""
        h = self.cut_h0 + 4.0 * math.sin(0.23 * x + self.cut_phase[0]) * math.sin(0.19 * y + self.cut_phase[1])
        return max(BAND_TOP + 0.6, min(self.H - 1.0, h + r.uniform(-1.4, 1.4)))


def soot_fn(H, phase, base):
    def f(p, c):
        k = min(1.0, max(0.0, (p[2] - 2.0) / max(1.0, H - 2.0)))
        n = 0.5 + 0.5 * math.sin(p[0] * 0.9 + p[1] * 1.3 + phase)
        soot = min(1.0, base + (0.9 - base) * k * (0.55 + 0.45 * n))
        return (c[0], c[1], c[2], 1.0 - soot)
    return f


# ---------------------------------------------------------------- facade parts
def opening(mb, fr, a0, a1, z0, z1, depth, reveal, back, b_face=0.0, head=True, back_slot_z0=None):
    """Recessed opening: jambs, head, sill in `reveal`, back face in `back` (None = no back)."""
    bf, bb = b_face, b_face - depth
    P = fr.at
    mb.poly(reveal, [P(a0, bb, z0), P(a0, bf, z0), P(a0, bf, z1), P(a0, bb, z1)], fr.t)
    mb.poly(reveal, [P(a1, bb, z0), P(a1, bf, z0), P(a1, bf, z1), P(a1, bb, z1)], geom.mul(fr.t, -1))
    mb.poly(reveal, [P(a0, bb, z0), P(a1, bb, z0), P(a1, bf, z0), P(a0, bf, z0)], Z)
    if head:
        mb.poly(reveal, [P(a0, bb, z1), P(a1, bb, z1), P(a1, bf, z1), P(a0, bf, z1)], (0, 0, -1))
    if back:
        mb.fquad(back, fr, a0, a1, z0 if back_slot_z0 is None else back_slot_z0, z1, bb)


def window_frame(mb, fr, a0, a1, z0, z1, bb):
    """Painted casement: perimeter ring, central mullion and transom just in front of the glass."""
    t = 0.07
    b = bb + 0.05
    for r in rect_minus_rects(a0, a1, z0, z1, [(a0 + t, a1 - t, z0 + t, z1 - t)]):
        mb.fquad("frame", fr, r[0], r[1], r[2], r[3], b)
    ac = (a0 + a1) * 0.5
    mb.fbox("frame", fr, ac - 0.03, ac + 0.03, bb, b + 0.02, z0 + t, z1 - t, skip=("back", "top", "bottom"))
    zt = z0 + (z1 - z0) * 0.76
    mb.fbox("frame", fr, a0 + t, a1 - t, bb, b + 0.02, zt - 0.03, zt + 0.03, skip=("back", "left", "right"))


def rail_quad(mb, fr, a0, a1, z0, z1, b):
    mb.fquad("rail", fr, a0, a1, z0, z1, b, uvs=[(a0, 1.0), (a1, 1.0), (a1, 0.0), (a0, 0.0)])
    mb.fbox("iron", fr, a0, a1, b - 0.03, b + 0.03, z1 - 0.02, z1 + 0.035, skip=("back",))


def awning(mb, fr, a0, a1, zt, slot, proj=1.6, drop=0.7):
    P = fr.at
    n_up = norm(geom.add(geom.mul(fr.n, drop), (0.0, 0.0, proj)))
    pts = [P(a0, 0.02, zt), P(a1, 0.02, zt), P(a1, proj, zt - drop), P(a0, proj, zt - drop)]
    mb.poly(slot, pts, n_up)
    mb.poly(slot, pts, geom.mul(n_up, -1))
    mb.fquad(slot, fr, a0, a1, zt - drop - 0.25, zt - drop, proj)
    for a, s in ((a0, -1.0), (a1, 1.0)):
        mb.poly(slot, [P(a, 0.02, zt), P(a, proj, zt - drop), P(a, proj, zt - drop - 0.25)], geom.mul(fr.t, s))


def street_facade(mb, fr, lot, r, first, last):
    L = fr.length
    n = max(1, int(round(L / lot.bay)))
    w = L / n
    cs = [w * (i + 0.5) for i in range(n)]
    burnt = lot.damage == "burnt"
    collapsed = lot.damage == "collapsed"
    glass = "char" if collapsed else None

    # broken wall heights (two per bay) for collapsed lots
    if collapsed:
        cuts = []
        for ac in cs:
            pa = fr.at(ac - w * 0.25, 0, 0)
            pb = fr.at(ac + w * 0.25, 0, 0)
            cuts.append((lot.cut(pa[0], pa[1], r), lot.cut(pb[0], pb[1], r)))
    else:
        cuts = [(1e9, 1e9)] * n

    def wall(slot, a0, a1, z0, z1, holes, i):
        ca, cb = cuts[i]
        am = (a0 + a1) * 0.5
        for (s0, s1, top) in ((a0, am, ca), (am, a1, cb)):
            zz1 = min(z1, top)
            if zz1 <= z0 + 1e-3:
                continue
            hs = [(max(h[0], s0), min(h[1], s1), h[2], min(h[3], zz1)) for h in holes if h[1] > s0 and h[0] < s1 and h[2] < zz1]
            for rr in rect_minus_rects(s0, s1, z0, zz1, hs):
                mb.fquad(slot, fr, rr[0], rr[1], rr[2], rr[3], 0.0)
            if collapsed and top < z1:
                # broken wall: top cap + inner plaster face
                P = fr.at
                mb.poly("stone", [P(s0, -0.45, zz1), P(s1, -0.45, zz1), P(s1, 0.0, zz1), P(s0, 0.0, zz1)], Z)

    # ---------------- ground floor
    for i, ac in enumerate(cs):
        a0b, a1b = ac - w / 2, ac + w / 2
        door = (not lot.shops and i == n // 2) or (lot.shops and n >= 4 and i == n // 2 and not lot.corner)
        holes = []
        if door:
            hw = min(1.45, w / 2 - 0.35)
            hole = (ac - hw, ac + hw, 0.0, 4.05)
            holes.append(hole)
            wall("rustic", a0b, a1b, 0.0, GROUND_TOP, holes, i)
            opening(mb, fr, *hole, 0.5, "rustic", "char" if collapsed else "door")
            mb.fbox("stone", fr, ac - 0.22, ac + 0.22, 0.0, 0.12, 3.85, 4.45, skip=("back",))
        elif lot.shops:
            hole = (a0b + 0.32, a1b - 0.32, 0.0, 3.6)
            holes.append(hole)
            wall("rustic", a0b, a1b, 0.0, GROUND_TOP, holes, i)
            opening(mb, fr, *hole, 0.32, "rustic", "char" if (burnt or collapsed) else "shop", back_slot_z0=0.55)
            if not (burnt or collapsed):
                mb.fquad("fascia", fr, hole[0], hole[1], 0.0, 0.55, -0.3)
            mb.fbox("char" if (burnt or collapsed) else "fascia", fr, hole[0] - 0.05, hole[1] + 0.05, 0.0, 0.1, 3.68, 4.32, skip=("back",))
            if lot.awning and not (burnt or collapsed) and r.random() < 0.85:
                awning(mb, fr, hole[0] - 0.05, hole[1] + 0.05, 3.62, lot.awning_slot)
        else:
            hole = (ac - 0.62, ac + 0.62, 0.9, 3.7)
            holes.append(hole)
            wall("rustic", a0b, a1b, 0.0, GROUND_TOP, holes, i)
            opening(mb, fr, *hole, 0.3, "rustic", glass or ("char" if burnt and r.random() < 0.7 else "glass"))
            if not collapsed:
                window_frame(mb, fr, hole[0], hole[1], hole[2], hole[3], -0.3)

    # ---------------- upper floors
    for fi in range(lot.n_up):
        z0 = lot.zf[fi]
        h = lot.fh[fi]
        top_floor = fi == lot.n_up - 1
        wh = h * (0.7 if top_floor else 0.77)
        ww = min(1.42, w * 0.46)
        cont_balcony = fi in lot.balconies and not collapsed
        for i, ac in enumerate(cs):
            a0, a1 = ac - ww / 2, ac + ww / 2
            zs, zh = z0 + 0.03, z0 + wh
            lim = min(cuts[i])
            if z0 >= max(cuts[i]):
                continue
            wall("stone", ac - w / 2, ac + w / 2, z0, z0 + h, [(a0, a1, zs, zh)], i)
            if zs >= lim - 0.4:
                continue
            broken = zh > lim - 0.1
            back = "char" if (collapsed or (burnt and r.random() < 0.75)) else "glass"
            opening(mb, fr, a0, a1, zs, min(zh, lim), 0.3, "stone", back, head=not broken)
            if broken:
                continue
            if back == "glass":
                window_frame(mb, fr, a0, a1, zs, zh, -0.3)
            # moulded surround
            s = 0.17
            mb.fbox("stone", fr, a0 - s, a0, 0.0, 0.07, zs, zh + s, skip=("back",))
            mb.fbox("stone", fr, a1, a1 + s, 0.0, 0.07, zs, zh + s, skip=("back",))
            mb.fbox("stone", fr, a0 - s, a1 + s, 0.0, 0.07, zh, zh + s, skip=("back",))
            if fi <= 1 and zh + 0.8 < lim:
                zc = zh + s + 0.05
                mb.fbox("stone", fr, a0 - 0.32, a1 + 0.32, 0.0, 0.2, zc, zc + 0.16, skip=("back",))
                if fi == 0:
                    for ca in (a0 - 0.3, a1 + 0.18):
                        mb.fbox("stone", fr, ca, ca + 0.12, 0.0, 0.17, zh - 0.25, zc, skip=("back",))
                    if lot.pediments:
                        mb.extrude_profile("stone", fr, [(a0 - 0.34, zc + 0.16), (a1 + 0.34, zc + 0.16), (ac, zc + 0.6)], 0.0, 0.18)
            elif fi <= 3:
                mb.fbox("stone", fr, ac - 0.13, ac + 0.13, 0.0, 0.11, zh - 0.1, zh + 0.27, skip=("back",))
            if not cont_balcony and not collapsed:
                mb.fbox("stone", fr, a0 - 0.1, a1 + 0.1, 0.0, 0.2, z0 - 0.1, z0 + 0.03, skip=("back",))
                rail_quad(mb, fr, a0 - 0.05, a1 + 0.05, z0 + 0.03, z0 + 0.95, 0.12)
        if cont_balcony:
            for i in range(n + 1):
                a = i * w
                a = min(max(a, 0.3), L - 0.3)
                mb.fbox("stone", fr, a - 0.1, a + 0.1, 0.0, 0.78, z0 - 0.62, z0 - 0.2, skip=("back", "top"))

    if collapsed:
        interior_ruin(mb, fr, lot, r, cs, w, cuts)
        return
    # cornice modillions
    for i in range(int(L / 0.9)):
        a = 0.45 + i * 0.9
        if 0.2 < a < L - 0.2:
            mb.fbox("stone", fr, a - 0.08, a + 0.08, 0.0, 0.45, lot.H + 0.12, lot.H + 0.52, skip=("back", "top"))
    # dormers on the mansard
    if lot.damage != "burnt" or r.random() < 0.5:
        for i, ac in enumerate(cs):
            if (first and i == 0 and ac < 1.4) or (last and i == n - 1 and L - ac < 1.4):
                continue
            dormer(mb, fr, ac, lot.roof0, burnt=lot.damage == "burnt", h=lot.dormer_h)


def dormer(mb, fr, ac, z0, burnt=False, court=False, h=DORMER_H):
    hw = 0.58 if not court else 0.5
    bf = -0.4
    bb = -RUN
    zb = z0 + 0.1
    zt = z0 + h
    zr = zt + 0.55
    P = fr.at
    win = (ac - 0.36, ac + 0.36, zb + 0.45 * h / DORMER_H, zt - 0.22)
    face = "court" if court else "stone"
    for rr in rect_minus_rects(ac - hw, ac + hw, zb, zt, [win]):
        mb.fquad(face, fr, rr[0], rr[1], rr[2], rr[3], bf)
    opening(mb, fr, win[0], win[1], win[2], win[3], 0.18, face, "char" if burnt else "glass", b_face=bf)
    if not burnt:
        window_frame(mb, fr, win[0], win[1], win[2], win[3], bf - 0.18)
    mb.poly(face, [P(ac - hw, bf, zt), P(ac + hw, bf, zt), P(ac, bf, zr)], fr.n)
    for a, s in ((ac - hw, -1.0), (ac + hw, 1.0)):
        mb.poly("zinc", [P(a, bf, zb), P(a, bb, zb), P(a, bb, zt), P(a, bf, zt)], geom.mul(fr.t, s))
    o = 0.12
    dz, da = zr - (zt - 0.06), hw + o
    for s in (-1.0, 1.0):
        ea = ac + s * (hw + o)
        n = norm(fr.vec(s * dz, 0.0, da))
        mb.poly("zinc", [P(ea, bf + o, zt - 0.06), P(ac, bf + o, zr), P(ac, bb, zr), P(ea, bb, zt - 0.06)], n)
    mb.poly("zinc", [P(ac - hw - o, bf + o, zt - 0.06), P(ac + hw + o, bf + o, zt - 0.06), P(ac, bf + o, zr)], (0, 0, -1))


def court_facade(mb, fr, lot, r):
    L = fr.length
    n = max(1, int(round(L / 3.4)))
    w = L / n
    burnt = lot.damage == "burnt"
    collapsed = lot.damage == "collapsed"
    zmax = lot.roof0
    cutv = None
    if collapsed:
        cutv = [lot.cut(*fr.at(w * (i + 0.5), 0, 0)[:2], r) for i in range(n)]
    for i in range(n):
        a0b, a1b = i * w, (i + 1) * w
        ac = (a0b + a1b) * 0.5
        top = zmax if cutv is None else cutv[i]
        holes = []
        levels = [(0.0, GROUND_TOP)] + [(lot.zf[k], lot.fh[k]) for k in range(lot.n_up)]
        for k, (z0, h) in enumerate(levels):
            if k == 0:
                if i % 3 == 1:
                    hole = (ac - 0.6, ac + 0.6, 0.0, 2.6)
                else:
                    hole = (ac - 0.55, ac + 0.55, 1.1, 3.4)
            else:
                hole = (ac - 0.5, ac + 0.5, z0 + 0.7, z0 + 0.7 + h * 0.56)
            if hole[3] < top - 0.2:
                holes.append(hole)
        for rr in rect_minus_rects(a0b, a1b, 0.0, top, holes):
            mb.fquad("court", fr, rr[0], rr[1], rr[2], rr[3], 0.0)
        for hole in holes:
            back = "char" if (collapsed or (burnt and r.random() < 0.7)) else ("door" if hole[2] == 0.0 else "glass")
            opening(mb, fr, *hole, 0.2, "court", back)
        if collapsed:
            P = fr.at
            mb.poly("court", [P(a0b, -0.45, top), P(a1b, -0.45, top), P(a1b, 0.0, top), P(a0b, 0.0, top)], Z)
            mb.poly("char", [P(a0b, -0.45, 0.0), P(a1b, -0.45, 0.0), P(a1b, -0.45, top), P(a0b, -0.45, top)], geom.mul(fr.n, -1))
        elif lot.damage != "burnt" and i % 2 == 0:
            dormer(mb, fr, ac, lot.roof0, court=True, h=lot.dormer_h)
    if not collapsed:
        mb.fbox("court", fr, 0.0, L, 0.0, 0.25, lot.H + 0.4, lot.roof0, skip=("back",))


def party_wall(mb, fr, lot):
    top = lot.roof0 if lot.damage != "collapsed" else BAND_TOP + 1.0
    mb.fquad("court", fr, 0.0, fr.length, 0.0, top, 0.0)


def interior_ruin(mb, fr, lot, r, cs, w, cuts):
    """Collapsed lot seen from the street edge: inner wall faces, torn slabs, rubble spill in the street."""
    P = fr.at
    for i, ac in enumerate(cs):
        for s0, s1, top in ((ac - w / 2, ac, cuts[i][0]), (ac, ac + w / 2, cuts[i][1])):
            mb.poly("char", [P(s0, -0.45, 0.0), P(s1, -0.45, 0.0), P(s1, -0.45, top), P(s0, -0.45, top)], geom.mul(fr.n, -1))
        lim = min(cuts[i])
        for k in range(lot.n_up):
            z0 = lot.zf[k]
            if z0 < lim - 0.6 and r.random() < 0.8:
                depth = r.uniform(1.2, 4.5)
                mb.fbox("court", fr, ac - w / 2 + 0.05, ac + w / 2 - 0.05, -0.45 - depth, -0.45, z0 - 0.28, z0, skip=("back",))
    # street spill
    L = fr.length
    for _ in range(int(L * 1.6)):
        a = r.uniform(0.5, L - 0.5)
        b = r.uniform(-0.2, 1.0) ** 2 * 7.0
        hs = r.uniform(0.25, 1.2)
        c = P(a, b, hs * 0.4)
        ax = norm((r.uniform(-1, 1), r.uniform(-1, 1), r.uniform(-0.6, 0.6)))
        ay = norm(geom.cross(Z, ax)) if abs(ax[2]) < 0.95 else (1.0, 0.0, 0.0)
        az = geom.cross(ax, ay)
        mb.obox("rubble" if r.random() < 0.7 else "stone", c, ax, ay, az, hs * r.uniform(0.8, 2.0), hs, hs * r.uniform(0.5, 1.0))
    for _ in range(4):
        a = r.uniform(1.0, L - 1.0)
        c = P(a, r.uniform(-3, 2), r.uniform(1.0, 3.0))
        ax = norm((r.uniform(-1, 1), r.uniform(-1, 1), r.uniform(-0.9, 0.9)))
        ay = norm(geom.cross(Z, ax))
        az = geom.cross(ax, ay)
        mb.obox("char", c, ax, ay, az, r.uniform(2.0, 4.0), 0.12, 0.14)


def rubble_heap(mb, lot, r):
    """Rubble mound filling a collapsed lot (heightfield over the lot bbox, faces tilted by real normals)."""
    xs = [p[0] for p in lot.poly]
    ys = [p[1] for p in lot.poly]
    x0, x1, y0, y1 = min(xs) + 0.45, max(xs) - 0.45, min(ys) + 0.45, max(ys) - 0.45
    nx = max(2, int((x1 - x0) / 1.6))
    ny = max(2, int((y1 - y0) / 1.6))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    ph = r.uniform(0, 6.28)

    def hf(x, y):
        u = (x - cx) / max(1.0, (x1 - x0) / 2)
        v = (y - cy) / max(1.0, (y1 - y0) / 2)
        mound = max(0.0, 1.0 - 0.6 * (u * u + v * v))
        return 0.6 + 4.5 * mound + 0.5 * math.sin(x * 1.7 + ph) * math.cos(y * 1.3 - ph) + r.uniform(-0.3, 0.3)

    hs = [[hf(x0 + (x1 - x0) * i / nx, y0 + (y1 - y0) * j / ny) for i in range(nx + 1)] for j in range(ny + 1)]
    for j in range(ny):
        for i in range(nx):
            xa, xb = x0 + (x1 - x0) * i / nx, x0 + (x1 - x0) * (i + 1) / nx
            ya, yb = y0 + (y1 - y0) * j / ny, y0 + (y1 - y0) * (j + 1) / ny
            p00, p10 = (xa, ya, hs[j][i]), (xb, ya, hs[j][i + 1])
            p11, p01 = (xb, yb, hs[j + 1][i + 1]), (xa, yb, hs[j + 1][i])
            for tri in ((p00, p10, p11), (p00, p11, p01)):
                nn = geom.newell(tri)
                if nn[2] < 0:
                    nn = geom.mul(nn, -1)
                mb.poly("rubble", list(tri), nn)
    for _ in range(int((x1 - x0) * (y1 - y0) / 14)):
        x, y = r.uniform(x0, x1), r.uniform(y0, y1)
        hs_ = r.uniform(0.3, 1.1)
        ax = norm((r.uniform(-1, 1), r.uniform(-1, 1), r.uniform(-0.7, 0.7)))
        ay = norm(geom.cross(Z, ax))
        mb.obox("stone" if r.random() < 0.5 else "court", (x, y, hf(x, y)), ax, ay, geom.cross(ax, ay), hs_ * 1.6, hs_, hs_ * 0.6)


# ---------------------------------------------------------------- roof
def roof(mb, lot, r):
    poly, types = lot.poly, lot.types
    k = len(poly)
    z0, z1 = lot.roof0, lot.roof1
    d = [RUN if t in ("street", "court") else 0.0 for t in types]
    ins = geom.inset_polygon(poly, d)
    burnt = lot.damage == "burnt"
    open_edge = r.randrange(k) if burnt else -1
    for i in range(k):
        p, q = poly[i], poly[(i + 1) % k]
        pi, qi = ins[i], ins[(i + 1) % k]
        n2 = seg_normal(p, q)
        quad = [(p[0], p[1], z0), (q[0], q[1], z0), (qi[0], qi[1], z1), (pi[0], pi[1], z1)]
        if d[i] > 0:
            n = norm((n2[0] * lot.rise, n2[1] * lot.rise, d[i]))
            if i == open_edge and types[i] == "street":
                rafters(mb, quad, r)
                continue
            mb.poly("zinc", quad, n)
            if burnt:
                mb.poly("char", quad, geom.mul(n, -1))
        else:
            mb.poly("court", quad, (n2[0], n2[1], 0.0))
            fr = Frame(p, q)
            chimney(mb, fr, z1, r, lot.chimney_k)
    if burnt:
        mb.polygon2d("char", poly, z0 - 0.05)
        for i in range(k):
            if d[i] == 0:
                continue
            p, q = ins[i], ins[(i + 1) % k]
            fr = Frame(p, q)
            for j in range(int(fr.length / 2.5)):
                a = 1.0 + j * 2.5
                if a < fr.length - 0.5 and r.random() < 0.6:
                    mb.fbox("char", fr, a, a + 0.2, -3.0, 0.0, z1 - 0.25, z1, skip=())
    else:
        mb.polygon2d("zinc", ins, z1)


def rafters(mb, quad, r):
    p0, p1, p2, p3 = quad
    for j in range(1, 9):
        t = j / 9.0
        if r.random() < 0.35:
            continue
        a = geom.add(p0, geom.mul(geom.sub(p1, p0), t))
        b = geom.add(p3, geom.mul(geom.sub(p2, p3), t))
        c = geom.mul(geom.add(a, b), 0.5)
        ax = norm(geom.sub(b, a))
        ay = norm(geom.sub(p1, p0))
        az = geom.cross(ax, ay)
        mb.obox("char", c, ax, ay, az, geom.length(geom.sub(b, a)) * 0.5 * r.uniform(0.6, 1.0), 0.08, 0.1)


def chimney(mb, fr, z1, r, k=1.0):
    """Chimney stacks along a party-wall roof edge; k scales the stack and pot heights (low-rise lots)."""
    L = fr.length
    if L < 9.0:
        return
    segs = [(3.0, 6.6), (L - 6.6, L - 3.0)] if L > 14.0 else [(3.0, L - 3.0)]
    for a0, a1 in segs:
        ht = z1 + r.uniform(1.1, 1.8) * k
        mb.fbox("chimney", fr, a0, a1, -0.85, -0.1, z1 - 1.0, ht, skip=("bottom",))
        mb.fbox("stone", fr, a0 - 0.08, a1 + 0.08, -0.93, -0.02, ht, ht + 0.12, skip=())
        a = a0 + 0.25
        while a < a1 - 0.3:
            if r.random() < 0.85:
                ph = r.uniform(0.35, 0.6) * k
                mb.fbox("pot", fr, a, a + 0.22, -0.58, -0.36, ht + 0.12, ht + 0.12 + ph, skip=("bottom",))
            a += 0.42


# ---------------------------------------------------------------- lots -> mesh
def street_chains(types):
    k = len(types)
    chains = []
    for i in range(k):
        if types[i] == "street" and types[i - 1] != "street":
            c = [i]
            j = (i + 1) % k
            while types[j] == "street" and j != i:
                c.append(j)
                j = (j + 1) % k
            chains.append(c)
    if not chains and all(t == "street" for t in types):
        chains.append(list(range(k)))
    return chains


def street_bands(mb, lot, pts):
    collapsed = lot.damage == "collapsed"
    mb.band("stone", pts, False, 0.0, 0.24, GROUND_TOP, BAND_TOP)
    if collapsed:
        return
    for fi in range(lot.n_up):
        z0 = lot.zf[fi]
        if fi in lot.balconies:
            # slab top 3 cm above the floor line: on the first floor it would otherwise share the z = BAND_TOP top face
            # with the ground-floor band (coplanar, same facing -> Z-fighting strip seen from the board camera)
            mb.band("stone", pts, False, 0.0, 0.9, z0 - 0.2, z0 + 0.03)
            mb.strip("rail", pts, False, 0.84, z0, z0 + 1.0)
            mb.band("iron", pts, False, 0.8, 0.9, z0 + 0.99, z0 + 1.05)
        elif fi > 0:
            mb.band("stone", pts, False, 0.0, 0.07, z0 - 0.13, z0)
    H = lot.H
    mb.band("stone", pts, False, 0.0, 0.2, H, H + 0.12)
    mb.band("stone", pts, False, 0.0, 0.5, H + 0.52, H + 0.62)
    mb.band("stone", pts, False, 0.0, 0.72, H + 0.62, H + 0.8)


def build_lot(mb, lot):
    r = rng(lot.seed)
    mb.color = lot.color()
    mb.color_fn = None
    if lot.damage == "burnt":
        mb.color_fn = soot_fn(lot.roof1, r.uniform(0, 6.28), 0.25)
    elif lot.damage == "collapsed":
        mb.color_fn = soot_fn(lot.H, r.uniform(0, 6.28), 0.35)
    k = len(lot.poly)
    chains = street_chains(lot.types)
    ends = set()
    for c in chains:
        ends.add(("first", c[0]))
        ends.add(("last", c[-1]))
    for i in range(k):
        p, q = lot.poly[i], lot.poly[(i + 1) % k]
        fr = Frame(p, q)
        t = lot.types[i]
        if t == "street":
            street_facade(mb, fr, lot, r, ("first", i) in ends, ("last", i) in ends)
        elif t == "court":
            court_facade(mb, fr, lot, r)
        else:
            party_wall(mb, fr, lot)
    for c in chains:
        pts = [lot.poly[c[0]]] + [lot.poly[(j + 1) % k] for j in c]
        street_bands(mb, lot, pts)
    if lot.damage == "collapsed":
        rubble_heap(mb, lot, r)
    else:
        roof(mb, lot, r)
    mb.color_fn = None


def mirror_lot(poly, types):
    """Mirror across the block diagonal x = y (keeps CCW order)."""
    k = len(poly)
    pts = [(p[1], p[0]) for p in reversed(poly)]
    tys = [types[(k - 2 - j) % k] for j in range(k)]
    return pts, tys


def split_run(total, r, lo=11.0, hi=21.0):
    out = []
    rem = total
    while rem > hi:
        w = r.uniform(lo, min(hi, rem - lo))
        out.append(w)
        rem -= w
    out.append(rem)
    return out


def pick_floors(r, corner=False, low=False):
    x = r.random()
    if low:
        return 3 if (corner or x > 0.4) else 2
    if corner:
        return 6 if x < 0.55 else 5
    return 4 if x < 0.12 else (6 if x > 0.72 else 5)


def l_lots(seed, damage=None, low=False):
    """Lots of one SW L-piece. damage: None | "burnt" | "collapsed" (applied to a subset of lots); low: low-rise lots."""
    r = rng(seed)
    c1, c2 = r.uniform(6.0, 13.0), r.uniform(6.0, 13.0)
    xa, ya = -INNER + c1, -INNER + c2
    lots = []
    corner_poly = [(-F, ya), (-F, -F + CHAMFER), (-F + CHAMFER, -F), (xa, -F), (xa, -INNER), (-INNER, -INNER), (-INNER, ya)]
    corner_types = ["street", "street", "street", "party", "court", "court", "party"]
    lots.append(Lot(corner_poly, corner_types, r, pick_floors(r, True, low), corner=True, low=low))
    for arm in (0, 1):
        start = xa if arm == 0 else ya
        widths = split_run(-GAP - start, r, 9.0, 16.0) if low else split_run(-GAP - start, r)
        x = start
        for wi, wd in enumerate(widths):
            xb = x + wd
            poly = [(x, -F), (xb, -F), (xb, -INNER), (x, -INNER)]
            types = ["street", "end" if wi == len(widths) - 1 else "party", "court", "party"]
            if arm == 1:
                poly, types = mirror_lot(poly, types)
            lots.append(Lot(poly, types, r, pick_floors(r, low=low), low=low))
            x = xb
    if damage == "burnt":
        for i, lot in enumerate(lots):
            if i == 0 or r.random() < 0.5:
                lot.damage = "burnt"
    elif damage == "collapsed":
        arm_idx = list(range(1, len(lots)))
        r.shuffle(arm_idx)
        lots[arm_idx[0]].damage = "collapsed"
        if len(arm_idx) > 3:
            lots[arm_idx[1]].damage = "collapsed"
        lots[0].damage = "burnt"
        for i in arm_idx[2:]:
            if r.random() < 0.35:
                lots[i].damage = "burnt"
    return lots


def infill_lots(seed, damage=None, low=False):
    r = rng(seed)
    lots = []
    if r.random() < 0.5:
        lots.append(Lot([(-GAP, -F), (GAP, -F), (GAP, -INNER), (-GAP, -INNER)], ["street", "end", "court", "end"], r, pick_floors(r, low=low), low=low))
    else:
        m = r.uniform(-3.0, 3.0)
        lots.append(Lot([(-GAP, -F), (m, -F), (m, -INNER), (-GAP, -INNER)], ["street", "party", "court", "end"], r, pick_floors(r, low=low), low=low))
        lots.append(Lot([(m, -F), (GAP, -F), (GAP, -INNER), (m, -INNER)], ["street", "end", "court", "party"], r, pick_floors(r, low=low), low=low))
    if damage:
        for lot in lots:
            lot.damage = damage
    return lots


def fill_runs(r, total):
    """Alternating building / light-court spans covering [-total/2, total/2], starting and ending with a building."""
    nb = r.choice((2, 3, 3, 4))
    gaps = [r.uniform(6.0, 11.0) for _ in range(nb - 1)]
    rest = total - sum(gaps)
    ws = [r.uniform(0.7, 1.3) for _ in range(nb)]
    ws = [rest * w / sum(ws) for w in ws]
    spans, x = [], -total / 2.0
    for i, w in enumerate(ws):
        spans.append((x, x + w))
        x += w + (gaps[i] if i < nb - 1 else 0.0)
    return spans


def court_fill_lots(seed, low=False):
    """Inner-block wings filling the 130 m courtyard of a background block (dense Paris roofscape from above).
    Edges against the street ring are party walls, all others are court facades with windows."""
    r = rng(seed)
    lots = []
    xs, ys = fill_runs(r, 2 * INNER), fill_runs(r, 2 * INNER)
    eps = 0.01
    for i, (x0, x1) in enumerate(xs):
        for j, (y0, y1) in enumerate(ys):
            inner = 0 < i < len(xs) - 1 and 0 < j < len(ys) - 1
            if r.random() < (0.45 if inner else 0.12):
                continue  # small garden / light court
            poly = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
            types = ["party" if y0 < -INNER + eps else "court", "party" if x1 > INNER - eps else "court",
                     "party" if y1 > INNER - eps else "court", "party" if x0 < -INNER + eps else "court"]
            n_up = (2 if r.random() < 0.6 else 3) if low else (4 if r.random() < 0.55 else 5)
            lots.append(Lot(poly, types, r, n_up, low=low))
    return lots


def court_fill_piece(seed, low=False):
    return piece_mesh(court_fill_lots(seed, low))


def piece_mesh(lots):
    mb = MeshBuilder(SLOTS)
    for lot in lots:
        build_lot(mb, lot)
    return mb


def l_piece(seed, damage=None, low=False):
    return piece_mesh(l_lots(seed, damage, low))


def infill_piece(seed, damage=None, low=False):
    return piece_mesh(infill_lots(seed, damage, low))


# module seeds of the low-rise district (shared with 04_haussmann_modules.py)
LOW_SEEDS = {"lowl": [8100 + 7 * i for i in range(6)], "lowinfill": [9100 + 7 * i for i in range(4)],
             "lowcourt": [9500 + 7 * i for i in range(4)]}


def low_height_check():
    """Max z (m) over every low-rise module: must stay <= LOW_MAX_H."""
    worst = 0.0
    for seed in LOW_SEEDS["lowl"]:
        worst = max(worst, l_piece(seed, low=True).bounds()[1][2])
    for seed in LOW_SEEDS["lowinfill"]:
        worst = max(worst, infill_piece(seed, low=True).bounds()[1][2])
    for seed in LOW_SEEDS["lowcourt"]:
        worst = max(worst, court_fill_piece(seed, low=True).bounds()[1][2])
    return worst


if __name__ == "__main__":
    import time

    for name, fn, arg in (("L", l_piece, None), ("L burnt", l_piece, "burnt"), ("L collapsed", l_piece, "collapsed"),
                          ("infill", infill_piece, None), ("infill collapsed", infill_piece, "collapsed"),
                          ("court fill", lambda s, a: court_fill_piece(s), None),
                          ("low L", lambda s, a: l_piece(s, low=True), None), ("low infill", lambda s, a: infill_piece(s, low=True), None),
                          ("low court fill", lambda s, a: court_fill_piece(s, low=True), None)):
        t0 = time.time()
        mb = fn(7, arg)
        print("%-18s tris=%6d verts=%6d slots=%d bounds=%s %.2fs" % (name, mb.tri_count(), mb.vert_count(), len(mb.used_slots()),
                                                                     tuple(tuple(round(v, 1) for v in b) for b in mb.bounds()), time.time() - t0))
    worst = low_height_check()
    print("low-rise max height %.2f m (limit %.1f) -> %s" % (worst, LOW_MAX_H, "OK" if worst <= LOW_MAX_H else "FAIL"))
