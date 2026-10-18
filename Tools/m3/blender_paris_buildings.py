"""Blender (5.2) procedural Paris buildings for the M3 board (new modelling, reference: GiantessAutoChess image
"ChatGPT Image 2026-09-28 19_59_37": dense Haussmann blocks, zinc mansards, corner domes, courtyard annexes).

    blender --background --factory-startup --python Tools/m3/blender_paris_buildings.py -- --out <dir> [--preview]
or from blender-mcp: sys.argv = ["x", "--", "--out", <dir>]; runpy.run_path(<this file>, run_name="__main__").

Every building is generated into a fresh mesh (no source file is read) and exported as one FBX. Conventions shared
with Tools/paris/haussmann.py so the existing UE material instances apply unchanged:
  * metres, +z up, pivot at the footprint centre, z = 0 at street level; the "front" faces -y;
  * material slots named after haussmann.SLOTS (stone, rustic, zinc, glass, frame, iron, rail, fascia, awning,
    door, chimney, pot, court, shop, char);
  * UV0 in metres: u along the surface, v = -height (walls) / along the slope (roofs);
  * vertex colour R = stone tint, G = shop palette, A = 1 - soot (per building, deterministic seed).
Writes <out>/m3_buildings.json (sizes, triangle counts, slots) and optional Workbench previews.
"""
import argparse
import json
import math
import os
import random
import sys

import bpy

SLOTS = ["stone", "rustic", "court", "zinc", "zincdark", "glass", "shop", "frame", "iron", "rail", "fascia",
         "awning", "awning2", "door", "chimney", "pot", "char", "skylight", "brick", "concrete", "soot"]
PREVIEW_RGB = {"stone": (0.78, 0.71, 0.58), "rustic": (0.70, 0.64, 0.52), "court": (0.74, 0.70, 0.62),
               "zinc": (0.36, 0.41, 0.47), "zincdark": (0.22, 0.25, 0.29), "glass": (0.10, 0.13, 0.16),
               "shop": (0.08, 0.10, 0.11), "frame": (0.85, 0.84, 0.80), "iron": (0.07, 0.08, 0.08),
               "rail": (0.06, 0.06, 0.06), "fascia": (0.20, 0.25, 0.20), "awning": (0.55, 0.12, 0.10),
               "awning2": (0.15, 0.32, 0.20), "door": (0.20, 0.13, 0.09), "chimney": (0.62, 0.52, 0.43),
               "pot": (0.62, 0.32, 0.20), "char": (0.05, 0.05, 0.05), "skylight": (0.30, 0.40, 0.45),
               "brick": (0.45, 0.22, 0.15), "concrete": (0.55, 0.55, 0.52), "soot": (0.08, 0.07, 0.07)}

GROUND_TOP, BAND_TOP, CORNICE, RISE, RUN = 4.6, 5.0, 0.8, 4.0, 2.3


class Kit:
    """Accumulates quads/tris with per-face slot and metre UVs, then builds one Blender mesh."""

    def __init__(self, name, seed):
        self.name = name
        self.rnd = random.Random(seed)
        self.v, self.f, self.uv, self.slot = [], [], [], []
        self.col = (self.rnd.random(), self.rnd.random(), 0.0, 1.0 - 0.25 * self.rnd.random())

    # ---------------------------------------------------------------- primitives
    def poly(self, pts, slot, uaxis=None):
        """Planar polygon (ccw seen from outside). UV: u along uaxis (default first edge), v = -(along up-ish axis)."""
        p0 = pts[0]
        e = _sub(pts[1], p0)
        nrm = _norm(_cross(e, _sub(pts[2], p0)))
        u = _norm(uaxis or e)
        vax = _norm(_cross(nrm, u))
        if vax[2] < 0 or (abs(vax[2]) < 1e-6 and vax[1] < 0):
            vax = (-vax[0], -vax[1], -vax[2])
        base = len(self.v)
        uvs = []
        for p in pts:
            d = _sub(p, p0)
            uvs.append((_dot(d, u) + p0[0] * 0.0, -_dot(d, vax) - p0[2]))
            self.v.append(p)
        self.f.append(tuple(range(base, base + len(pts))))
        self.uv.append(uvs)
        self.slot.append(SLOTS.index(slot))

    def box(self, x0, y0, z0, x1, y1, z1, slot, bottom=False, top_slot=None):
        a = (x0, y0, z0); b = (x1, y0, z0); c = (x1, y1, z0); d = (x0, y1, z0)
        A = (x0, y0, z1); B = (x1, y0, z1); C = (x1, y1, z1); D = (x0, y1, z1)
        self.poly([a, b, B, A], slot)
        self.poly([b, c, C, B], slot)
        self.poly([c, d, D, C], slot)
        self.poly([d, a, A, D], slot)
        self.poly([A, B, C, D], top_slot or slot, (1, 0, 0))
        if bottom:
            self.poly([a, d, c, b], slot, (1, 0, 0))

    def obox(self, o, u, n, s0, s1, d0, d1, z0, z1, slot, top_slot=None):
        """Box in a facade frame: origin o, along-facade unit u, outward unit n; spans s (along), d (outward), z."""
        def P(s, d, z):
            return (o[0] + u[0] * s + n[0] * d, o[1] + u[1] * s + n[1] * d, z)
        a, b, c, dd = P(s0, d0, z0), P(s1, d0, z0), P(s1, d1, z0), P(s0, d1, z0)
        A, B, C, D = P(s0, d0, z1), P(s1, d0, z1), P(s1, d1, z1), P(s0, d1, z1)
        self.poly([dd, c, C, D], slot)      # front (outward)
        self.poly([b, a, A, B], slot)       # back
        self.poly([a, dd, D, A], slot)
        self.poly([c, b, B, C], slot)
        self.poly([A, D, C, B], top_slot or slot, u)
        self.poly([a, b, c, dd], slot, u)

    def oquad(self, o, u, n, s0, s1, d, z0, z1, slot):
        def P(s, z):
            return (o[0] + u[0] * s + n[0] * d, o[1] + u[1] * s + n[1] * d, z)
        self.poly([P(s0, z0), P(s1, z0), P(s1, z1), P(s0, z1)], slot)

    def cylinder(self, cx, cy, z0, z1, r, seg, slot, cap=True, r1=None):
        r1 = r if r1 is None else r1
        ring0 = [(cx + r * math.cos(2 * math.pi * i / seg), cy + r * math.sin(2 * math.pi * i / seg), z0) for i in range(seg)]
        ring1 = [(cx + r1 * math.cos(2 * math.pi * i / seg), cy + r1 * math.sin(2 * math.pi * i / seg), z1) for i in range(seg)]
        for i in range(seg):
            j = (i + 1) % seg
            if r1 > 1e-4:
                self.poly([ring0[i], ring0[j], ring1[j], ring1[i]], slot)
            else:
                self.poly([ring0[i], ring0[j], (cx, cy, z1)], slot)
        if cap and r1 > 1e-4:
            self.poly(ring1, slot, (1, 0, 0))

    def dome(self, cx, cy, z0, r, h, seg, rings, slot):
        prev = [(cx + r * math.cos(2 * math.pi * i / seg), cy + r * math.sin(2 * math.pi * i / seg), z0) for i in range(seg)]
        for k in range(1, rings + 1):
            a = (math.pi / 2) * k / rings
            rr, zz = r * math.cos(a), z0 + h * math.sin(a)
            if k == rings:
                for i in range(seg):
                    self.poly([prev[i], prev[(i + 1) % seg], (cx, cy, zz)], slot)
                break
            cur = [(cx + rr * math.cos(2 * math.pi * i / seg), cy + rr * math.sin(2 * math.pi * i / seg), zz) for i in range(seg)]
            for i in range(seg):
                j = (i + 1) % seg
                self.poly([prev[i], prev[j], cur[j], cur[i]], slot)
            prev = cur

    def hip_roof(self, x0, y0, x1, y1, z0, rise, inset, slot, top_slot="zincdark", ridge=False):
        """Truncated pyramid (mansard break or pavilion roof). ridge=True closes to a ridge line instead of a flat top."""
        if ridge:
            # hipped roof closing to a ridge along the long axis; the hip ends run in by at most half the short side
            short = min(x1 - x0, y1 - y0)
            if (x1 - x0) >= (y1 - y0):
                ins_x, ins_y = min(inset, short / 2), (y1 - y0) / 2
            else:
                ins_x, ins_y = (x1 - x0) / 2, min(inset, short / 2)
        else:
            ins_x = ins_y = inset
        a, b, c, d = (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)
        z1 = z0 + rise
        A, B, C, D = (x0 + ins_x, y0 + ins_y, z1), (x1 - ins_x, y0 + ins_y, z1), (x1 - ins_x, y1 - ins_y, z1), (x0 + ins_x, y1 - ins_y, z1)
        for p, q, Q, P_ in ((a, b, B, A), (b, c, C, B), (c, d, D, C), (d, a, A, D)):
            if _dist(P_, Q) < 1e-3:
                self.poly([p, q, Q], slot)
            else:
                self.poly([p, q, Q, P_], slot)
        if not ridge and B[0] - A[0] > 0.01 and D[1] - A[1] > 0.01:
            self.poly([A, B, C, D], top_slot, (1, 0, 0))

    # ---------------------------------------------------------------- output
    def build(self):
        me = bpy.data.meshes.new(self.name)
        me.from_pydata(self.v, [], self.f)
        # only the slots that are present, in SLOTS order (materials.clear() would reset the face indices)
        used = sorted(set(self.slot))
        remap = {old: new for new, old in enumerate(used)}
        for i in used:
            s = SLOTS[i]
            mat = bpy.data.materials.get(s) or bpy.data.materials.new(s)
            mat.diffuse_color = PREVIEW_RGB[s] + (1.0,)
            me.materials.append(mat)
        uvl = me.uv_layers.new(name="UVMap")
        for poly, uvs, s in zip(me.polygons, self.uv, self.slot):
            poly.material_index = remap[s]
            for k, loop in enumerate(poly.loop_indices):
                uvl.data[loop].uv = uvs[k]
        ca = me.color_attributes.new("Col", "BYTE_COLOR", "CORNER")
        for d in ca.data:
            d.color = self.col
        # validate only after per-face attributes are written: it may drop degenerate faces and shift indices
        me.validate()
        me.update()
        obj = bpy.data.objects.new(self.name, me)
        bpy.context.scene.collection.objects.link(obj)
        return obj


# ---------------------------------------------------------------- vector helpers
def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    l = math.sqrt(_dot(a, a)) or 1.0
    return (a[0] / l, a[1] / l, a[2] / l)


def _dist(a, b):
    return math.sqrt(_dot(_sub(a, b), _sub(a, b)))


# ---------------------------------------------------------------- Haussmann grammar
def floors_z(heights):
    zs, z = [], BAND_TOP
    for h in heights:
        zs.append(z)
        z += h
    return zs, z


def facade(k, o, u, n, length, heights, shops=True, bay=3.3, balcony_floors=(1, -1), doors=(), courtyard=False):
    """Haussmann street facade on the wall plane through o (u along, n outward). Wall itself is built by the caller."""
    zs, top = floors_z(heights)
    nb = max(1, int(length // bay))
    pitch = length / nb
    wall = "court" if courtyard else "stone"
    # ground floor: rusticated base, shops or carriage door, stone band
    if not courtyard:
        k.obox(o, u, n, 0, length, 0, 0.12, 0, GROUND_TOP, "rustic")
        k.obox(o, u, n, -0.05, length + 0.05, 0, 0.22, GROUND_TOP, BAND_TOP, "stone")
    for i in range(nb):
        s0 = i * pitch
        c = s0 + pitch / 2
        if not courtyard:
            if i in doors:
                k.oquad(o, u, n, c - 1.5, c + 1.5, 0.125, 0, 3.9, "door")
                k.obox(o, u, n, c - 1.75, c + 1.75, 0.12, 0.3, 3.9, 4.25, "stone")
            elif shops:
                k.oquad(o, u, n, s0 + 0.35, s0 + pitch - 0.35, 0.125, 0.2, 3.4, "shop")
                k.obox(o, u, n, s0 + 0.25, s0 + pitch - 0.25, 0.12, 0.28, 3.4, 4.1, "fascia")
                if k.rnd.random() < 0.35:
                    aw = "awning" if k.rnd.random() < 0.6 else "awning2"
                    k.obox(o, u, n, s0 + 0.3, s0 + pitch - 0.3, 0.28, 1.6, 3.15, 3.35, aw)
            else:
                k.oquad(o, u, n, c - 0.7, c + 0.7, 0.125, 0.9, 3.8, "glass")
        for f, (z, h) in enumerate(zip(zs, heights)):
            wh = h * (0.66 if f < len(heights) - 1 else 0.6)
            w0, w1 = c - 0.62, c + 0.62
            zb = z + 0.35 + (0.0 if f > 0 else 0.15)
            k.oquad(o, u, n, w0, w1, 0.03, zb, zb + wh, "glass")
            # surround, sill and cap (pediments on the 1st floor, plain caps above)
            k.obox(o, u, n, w0 - 0.18, w0, 0, 0.12, zb, zb + wh, wall)
            k.obox(o, u, n, w1, w1 + 0.18, 0, 0.12, zb, zb + wh, wall)
            k.obox(o, u, n, w0 - 0.25, w1 + 0.25, 0, 0.2, zb - 0.16, zb, wall)
            cap = 0.32 if f == 0 else 0.18
            k.obox(o, u, n, w0 - 0.25, w1 + 0.25, 0, 0.22, zb + wh, zb + wh + cap, wall)
            k.obox(o, u, n, w0 + 0.05, w1 - 0.05, 0.03, 0.06, zb + wh * 0.62, zb + wh * 0.66, "frame")
            k.obox(o, u, n, c - 0.03, c + 0.03, 0.03, 0.06, zb, zb + wh, "frame")
            if not courtyard and f not in [b % len(heights) for b in balcony_floors]:
                k.obox(o, u, n, w0 - 0.05, w1 + 0.05, 0.12, 0.42, zb, zb + 0.9, "rail")  # balconette
    if not courtyard:
        for f in balcony_floors:
            z = zs[f % len(heights)] + 0.35
            k.obox(o, u, n, 0.2, length - 0.2, 0, 1.0, z - 0.18, z, "stone")
            k.obox(o, u, n, 0.2, length - 0.2, 0.92, 1.0, z, z + 1.0, "rail")
    # string courses and cornice
    for z in zs[1:]:
        k.obox(o, u, n, -0.05, length + 0.05, 0, 0.1, z - 0.12, z, wall)
    k.obox(o, u, n, -0.3, length + 0.3, 0, 0.35, top, top + 0.45, wall)
    k.obox(o, u, n, -0.45, length + 0.45, 0, 0.75, top + 0.45, top + CORNICE, wall)
    return top


def dormers(k, o, u, n, length, z0, bay=3.3, back=RUN * 0.55):
    nb = max(1, int(length // bay))
    pitch = length / nb
    for i in range(nb):
        if i % 2 and length > 12:
            continue
        c = i * pitch + pitch / 2
        d0 = -back - 0.8
        k.obox(o, u, n, c - 0.75, c + 0.75, d0, -back + 0.1, z0, z0 + 2.0, "zinc")
        k.oquad(o, u, n, c - 0.5, c + 0.5, -back + 0.11, z0 + 0.2, z0 + 1.6, "glass")
        k.obox(o, u, n, c - 0.9, c + 0.9, d0 - 0.1, -back + 0.25, z0 + 2.0, z0 + 2.25, "frame")


def chimneys(k, x0, y0, x1, y1, z, count, every_y=True):
    for i in range(count):
        t = (i + 0.5) / count
        if every_y:
            cx, cy = x0 + (x1 - x0) * k.rnd.choice((0.04, 0.96)), y0 + (y1 - y0) * t
        else:
            cx, cy = x0 + (x1 - x0) * t, y0 + (y1 - y0) * k.rnd.choice((0.3, 0.7))
        w = k.rnd.uniform(1.6, 3.2)
        h = k.rnd.uniform(1.6, 2.6)
        k.box(cx - 0.4, cy - w / 2, z - 0.5, cx + 0.4, cy + w / 2, z + h, "chimney")
        k.box(cx - 0.5, cy - w / 2 - 0.1, z + h, cx + 0.5, cy + w / 2 + 0.1, z + h + 0.18, "stone")
        npots = max(2, int(w / 0.45))
        for p in range(npots):
            py = cy - w / 2 + (p + 0.5) * w / npots
            k.cylinder(cx, py, z + h + 0.18, z + h + 0.18 + k.rnd.uniform(0.4, 0.75), 0.13, 6, "pot")


def rect_building(k, x0, y0, x1, y1, heights, street_sides=("s",), shops=True, mansard=True, n_chim=3,
                  doors_side=None, courtyard=False):
    """Freestanding Haussmann lot: walls, facades on the given sides (s=-y, e=+x, n=+y, w=-x), mansard, chimneys."""
    _, top = floors_z(heights)
    wall = "court" if courtyard else "stone"
    k.box(x0, y0, 0, x1, y1, top, wall)
    sides = {"s": ((x0, y0, 0), (1, 0, 0), (0, -1, 0), x1 - x0), "e": ((x1, y0, 0), (0, 1, 0), (1, 0, 0), y1 - y0),
             "n": ((x1, y1, 0), (-1, 0, 0), (0, 1, 0), x1 - x0), "w": ((x0, y1, 0), (0, -1, 0), (-1, 0, 0), y1 - y0)}
    for s in ("s", "e", "n", "w"):
        o, u, n, L = sides[s]
        street = s in street_sides
        facade(k, o, u, n, L, heights, shops=shops and street, doors=(1,) if s == doors_side else (),
               courtyard=courtyard or not street, balcony_floors=(1, -1) if street else ())
    zr = top + CORNICE
    if mansard:
        k.hip_roof(x0 + 0.2, y0 + 0.2, x1 - 0.2, y1 - 0.2, zr, RISE, RUN, "zinc")
        for s in street_sides:
            o, u, n, L = sides[s]
            dormers(k, (o[0] + n[0] * 0.2, o[1] + n[1] * 0.2, 0), u, n, L, zr + 0.4)
        chimneys(k, x0, y0, x1, y1, zr + RISE, n_chim)
        return zr + RISE
    k.box(x0 - 0.2, y0 - 0.2, zr - 0.05, x1 + 0.2, y1 + 0.2, zr + 0.25, "zincdark")
    return zr


# ---------------------------------------------------------------- buildings
def corner_rotunda(name, seed):
    """L-shaped corner Haussmann block (two 30 m wings, 14 m deep) with a round corner tower and zinc dome."""
    k = Kit(name, seed)
    H = [3.3, 3.1, 3.0, 2.9, 2.8]
    L, D, R = 32.0, 14.0, 7.0
    x0, y0 = -L / 2, -L / 2
    # south wing (facade -y) and west wing (facade -x) meet at the SW corner where the rotunda stands
    rect_building(k, x0 + R, y0, x0 + L, y0 + D, H, street_sides=("s",), n_chim=3, doors_side="s")
    rect_building(k, x0, y0 + R, x0 + D, y0 + L, H, street_sides=("w",), n_chim=3)
    zs, top = floors_z(H)
    cx, cy = x0 + R, y0 + R
    seg = 20
    k.cylinder(cx, cy, 0, top, R, seg, "stone", cap=False)
    k.cylinder(cx, cy, 0, GROUND_TOP, R + 0.12, seg, "rustic", cap=False)
    for z in zs:
        k.cylinder(cx, cy, z - 0.12, z, R + 0.1, seg, "stone", cap=False)
    for i in range(seg):
        a = 2 * math.pi * (i + 0.5) / seg
        if not (math.pi * 0.95 < a < math.pi * 1.55):
            continue  # windows only on the outer quarter of the drum
        n = (math.cos(a), math.sin(a), 0.0)
        u = (-math.sin(a), math.cos(a), 0.0)
        o = (cx + n[0] * R, cy + n[1] * R, 0)
        for z, h in zip(zs, H):
            k.oquad(o, u, n, -0.55, 0.55, 0.05, z + 0.4, z + 0.4 + h * 0.62, "glass")
            k.obox(o, u, n, -0.8, 0.8, 0, 0.16, z + 0.4 + h * 0.62, z + 0.6 + h * 0.62, "stone")
        k.oquad(o, u, n, -0.8, 0.8, 0.14, 0.3, 3.5, "shop")
        k.obox(o, u, n, -1.1, 1.1, 0.0, 0.95, zs[1] + 0.17, zs[1] + 0.35, "stone")
        k.obox(o, u, n, -1.1, 1.1, 0.85, 0.95, zs[1] + 0.35, zs[1] + 1.35, "rail")
    k.cylinder(cx, cy, top, top + CORNICE, R + 0.7, seg, "stone")
    # drum, dome, lantern, finial
    k.cylinder(cx, cy, top + CORNICE, top + CORNICE + 2.6, R - 0.4, seg, "zinc", cap=False)
    k.dome(cx, cy, top + CORNICE + 2.6, R - 0.2, 6.5, seg, 6, "zinc")
    zt = top + CORNICE + 2.6 + 6.5
    k.cylinder(cx, cy, zt - 0.4, zt + 2.2, 1.1, 8, "frame")
    k.cylinder(cx, cy, zt + 2.2, zt + 3.4, 1.25, 8, "zinc", r1=0.05)
    k.cylinder(cx, cy, zt + 3.4, zt + 5.2, 0.08, 6, "iron", r1=0.02)
    return k


def pavilion(name, seed):
    """Second-Empire public building (mairie / hotel): central pavilion with tall square roof, clock, two wings."""
    k = Kit(name, seed)
    H = [4.2, 3.8, 3.4]
    W, D = 52.0, 18.0
    # wings
    for sx in (-1, 1):
        xa, xb = (-W / 2, -7.0) if sx < 0 else (7.0, W / 2)
        rect_building(k, xa, -D / 2, xb, D / 2, H, street_sides=("s", "n"), shops=False, n_chim=2)
    # central pavilion: projecting, one floor taller, steep pavilion roof with crest
    Hc = H + [3.4]
    zs, top = floors_z(Hc)
    x0, x1, y0, y1 = -7.5, 7.5, -D / 2 - 2.0, D / 2 + 1.0
    k.box(x0, y0, 0, x1, y1, top, "stone")
    for s, (o, u, n, L) in {"s": ((x0, y0, 0), (1, 0, 0), (0, -1, 0), x1 - x0),
                             "n": ((x1, y1, 0), (-1, 0, 0), (0, 1, 0), x1 - x0)}.items():
        facade(k, o, u, n, L, Hc, shops=False, doors=(1, 2, 3) if s == "s" else (2,), bay=3.75)
    zr = top + CORNICE
    k.hip_roof(x0 + 0.2, y0 + 0.2, x1 - 0.2, y1 - 0.2, zr, 9.0, 3.6, "zinc")
    k.box(-3.8, -D / 2 - 2.3 - 0.4, zr, 3.8, -D / 2 + 1.0, zr + 3.4, "stone")  # clock dormer
    k.cylinder(0, -D / 2 - 2.75, zr + 1.7, zr + 1.71, 1.25, 16, "frame")
    k.box(x0 + 3.4, y0 + 3.4, zr + 9.0, x1 - 3.4, y1 - 3.4, zr + 9.25, "zincdark")
    for i in range(9):
        x = x0 + 3.6 + i * (x1 - x0 - 7.2) / 8
        k.box(x - 0.05, -0.05, zr + 9.25, x + 0.05, 0.05, zr + 10.6, "iron")
    k.box(x0 + 3.6, -0.06, zr + 10.5, x1 - 3.6, 0.06, zr + 10.6, "iron")
    # flag mast
    k.cylinder(0, 0, zr + 10.6, zr + 16.0, 0.08, 6, "iron")
    return k


def market_hall(name, seed):
    """Baltard-style iron and glass market hall: cast-iron columns, brick plinth, raised clerestory roof."""
    k = Kit(name, seed)
    W, D, Hc = 44.0, 26.0, 9.0
    k.box(-W / 2, -D / 2, 0, W / 2, D / 2, 1.2, "chimney")
    nx, ny = 11, 6
    for i in range(nx + 1):
        for j in range(ny + 1):
            if 0 < i < nx and 0 < j < ny and not (j == ny // 2):
                continue
            x = -W / 2 + i * W / nx
            y = -D / 2 + j * D / ny
            k.cylinder(x, y, 1.2, Hc, 0.22, 8, "iron")
    # glazed screen walls between columns
    for (o, u, n, L) in (((-W / 2, -D / 2, 0), (1, 0, 0), (0, -1, 0), W), ((W / 2, D / 2, 0), (-1, 0, 0), (0, 1, 0), W),
                         ((W / 2, -D / 2, 0), (0, 1, 0), (1, 0, 0), D), ((-W / 2, D / 2, 0), (0, -1, 0), (-1, 0, 0), D)):
        k.oquad(o, u, n, 0, L, -0.05, 1.2, Hc - 0.4, "skylight")
        nb = int(L / 4)
        for b in range(nb + 1):
            k.obox(o, u, n, b * L / nb - 0.1, b * L / nb + 0.1, -0.1, 0.05, 1.2, Hc, "iron")
        k.obox(o, u, n, 0, L, -0.1, 0.1, 4.6, 4.8, "iron")
    k.box(-W / 2 - 0.6, -D / 2 - 0.6, Hc, W / 2 + 0.6, D / 2 + 0.6, Hc + 0.35, "iron")
    # lower pitched zinc roof, clerestory glazing, upper glass+zinc ridge roof
    k.hip_roof(-W / 2 - 0.6, -D / 2 - 0.6, W / 2 + 0.6, D / 2 + 0.6, Hc + 0.35, 3.0, 6.0, "zinc", top_slot="skylight")
    k.box(-W / 2 + 6, -D / 2 + 6, Hc + 3.35, W / 2 - 6, D / 2 - 6, Hc + 5.2, "skylight")
    for i in range(12):
        x = -W / 2 + 6 + i * (W - 12) / 11
        k.box(x - 0.08, -D / 2 + 5.9, Hc + 3.35, x + 0.08, D / 2 - 5.9, Hc + 5.25, "iron")
    k.hip_roof(-W / 2 + 5.6, -D / 2 + 5.6, W / 2 - 5.6, D / 2 - 5.6, Hc + 5.2, 3.2, 99.0, "skylight", ridge=True)
    return k


def annex(name, seed, w=24.0, d=11.0, floors=2):
    """Courtyard workshop / annex: plastered, small windows, pitched zinc roof with a skylight band and chimney."""
    k = Kit(name, seed)
    H = [3.6, 3.2, 3.0][:floors]
    _, top = floors_z(H)
    top -= 0.4  # annexes have a lower ground floor
    k.box(-w / 2, -d / 2, 0, w / 2, d / 2, top, "court")
    for (o, u, n, L) in (((-w / 2, -d / 2, 0), (1, 0, 0), (0, -1, 0), w), ((w / 2, d / 2, 0), (-1, 0, 0), (0, 1, 0), w)):
        facade(k, o, u, n, L, H, courtyard=True, bay=3.6)
        k.oquad(o, u, n, 1.5, 4.5, 0.03, 0, 3.4, "door")
    k.hip_roof(-w / 2 - 0.3, -d / 2 - 0.3, w / 2 + 0.3, d / 2 + 0.3, top + 0.2, d * 0.32, 99.0, "zinc", ridge=True)
    k.box(-w / 2 + 2, -d / 4 - 0.6, top + 0.2 + d * 0.16 - 0.3, w / 2 - 2, -d / 4 + 0.6, top + 0.2 + d * 0.16 + 0.2, "skylight")
    chimneys(k, -w / 2, -0.5, w / 2, 0.5, top + d * 0.32, 2, every_y=False)
    return k


def chapel(name, seed):
    """Neighbourhood church: stone nave with steep slate roof, apse, buttresses, bell tower and spire."""
    k = Kit(name, seed)
    L, W, Hn = 30.0, 13.0, 13.0
    x0 = -L / 2 + 4.0
    k.box(x0, -W / 2, 0, x0 + L, W / 2, Hn, "stone")
    for i in range(7):
        x = x0 + 2.5 + i * (L - 5) / 6
        for sy in (-1, 1):
            y = sy * W / 2
            k.box(x - 0.6, min(y, y + sy * 1.4), 0, x + 0.6, max(y, y + sy * 1.4), Hn * 0.75, "stone")
            if i < 6:
                xm = x + (L - 5) / 12
                o = (xm, y, 0)
                n = (0, sy, 0)
                u = (sy * -1.0 * -1, 0, 0) if sy > 0 else (1, 0, 0)
                k.oquad(o, (1, 0, 0), n, -0.8, 0.8, 0.03, 4.0, 10.5, "glass")
                k.cylinder(xm, y + sy * 0.04, 10.5, 10.6, 0.8, 8, "stone")
    k.hip_roof(x0 - 0.3, -W / 2 - 0.4, x0 + L + 0.3, W / 2 + 0.4, Hn, W * 0.75, 99.0, "zincdark", ridge=True)
    # apse (half drum + half cone)
    ax = x0 + L
    for i in range(8):
        a0, a1 = -math.pi / 2 + math.pi * i / 8, -math.pi / 2 + math.pi * (i + 1) / 8
        r = W / 2
        p0 = (ax + r * math.cos(a0), r * math.sin(a0), 0)
        p1 = (ax + r * math.cos(a1), r * math.sin(a1), 0)
        k.poly([p0, p1, (p1[0], p1[1], Hn * 0.85), (p0[0], p0[1], Hn * 0.85)], "stone")
        k.poly([(p0[0], p0[1], Hn * 0.85), (p1[0], p1[1], Hn * 0.85), (ax, 0, Hn * 0.85 + W * 0.6)], "zincdark")
    # facade + bell tower with spire
    tx = x0 - 6.0
    k.box(tx, -3.5, 0, x0 + 0.5, 3.5, 30.0, "stone")
    k.box(tx - 0.3, -3.8, 0, x0 + 0.8, 3.8, 3.0, "rustic")
    k.oquad((tx, 0, 0), (0, -1, 0), (-1, 0, 0), -1.4, 1.4, 0.03, 0, 4.6, "door")
    k.cylinder(tx - 0.02, 0, 9.0, 9.01, 2.0, 16, "glass", cap=True)
    for z in (19.5, 25.0):
        for o, u, n in (((tx, 0, 0), (0, -1, 0), (-1, 0, 0)), ((x0 + 0.5, 0, 0), (0, 1, 0), (1, 0, 0)),
                        (((tx + x0 + 0.5) / 2, -3.5, 0), (1, 0, 0), (0, -1, 0)), (((tx + x0 + 0.5) / 2, 3.5, 0), (-1, 0, 0), (0, 1, 0))):
            k.oquad(o, u, n, -0.9, 0.9, 0.03, z, z + 3.2, "glass")
    cxs = (tx + x0 + 0.5) / 2
    k.box(cxs - 4.0, -4.0, 30.0, cxs + 4.0, 4.0, 30.8, "stone")
    k.cylinder(cxs, 0, 30.8, 46.0, 4.6, 8, "zincdark", r1=0.0)
    k.cylinder(cxs, 0, 46.0, 48.5, 0.08, 6, "iron")
    k.box(cxs - 0.9, -0.08, 47.4, cxs + 0.9, 0.08, 47.55, "iron")
    return k


def townhouse(name, seed, w, d, floors, sides):
    k = Kit(name, seed)
    H = {4: [3.4, 3.2, 3.0, 2.9], 5: [3.3, 3.1, 3.1, 2.9, 2.9], 6: [3.3, 3.1, 3.0, 2.9, 2.8, 2.8]}[floors]
    rect_building(k, -w / 2, -d / 2, w / 2, d / 2, H, street_sides=sides, n_chim=max(2, int(d / 5)), doors_side=sides[0])
    return k


def fountain(name, seed):
    """Square centre piece (Wallace / Medici style tiered fountain on a round basin)."""
    k = Kit(name, seed)
    k.cylinder(0, 0, 0, 0.7, 9.0, 32, "stone")
    k.cylinder(0, 0, 0.7, 0.72, 8.4, 32, "glass")
    k.cylinder(0, 0, 0.7, 3.2, 1.1, 12, "stone")
    k.cylinder(0, 0, 3.2, 3.7, 3.4, 16, "stone")
    k.cylinder(0, 0, 3.7, 5.6, 0.6, 10, "stone")
    k.cylinder(0, 0, 5.6, 6.0, 1.8, 12, "stone")
    k.cylinder(0, 0, 6.0, 8.2, 0.35, 8, "iron", r1=0.15)
    return k


def factory_stack(name, seed, top=67.0, damaged=False):
    """Multi-storey brick factory with its chimney rising through the roof at the east end (reference image, west
    industrial belt). Pivot = chimney axis at street level, so the module replaces a free-standing chimney in place
    and the chimney top keeps the old height (smoke FX sources stay valid)."""
    k = Kit(name, seed)
    x0, x1, y0, y1 = -46.0, 5.0, -13.0, 13.0
    floors = [5.2, 4.6, 4.6, 4.4]
    zs, H = [0.0], 0.0
    for h in floors:
        H += h
        zs.append(H)
    k.box(x0, y0, 0, x1, y1, H, "brick")
    k.box(x0 - 0.3, y0 - 0.3, 0, x1 + 0.3, y1 + 0.3, 1.0, "concrete")
    # long facades: brick piers, tall segmental windows, stone sills and floor bands
    for (o, u, n, L) in (((x0, y0, 0), (1, 0, 0), (0, -1, 0), x1 - x0), ((x1, y1, 0), (-1, 0, 0), (0, 1, 0), x1 - x0),
                         ((x1, y0, 0), (0, 1, 0), (1, 0, 0), y1 - y0), ((x0, y1, 0), (0, -1, 0), (-1, 0, 0), y1 - y0)):
        bays = max(2, int(L // 5.0))
        pitch = L / bays
        for b in range(bays + 1):
            k.obox(o, u, n, b * pitch - 0.45, b * pitch + 0.45, 0, 0.35, 0, H + 0.6, "brick")
        for b in range(bays):
            c = b * pitch + pitch / 2
            for f in range(len(floors)):
                z0 = zs[f] + (1.2 if f == 0 else 0.9)
                z1 = zs[f + 1] - 0.9
                if damaged and k.rnd.random() < 0.3:
                    k.oquad(o, u, n, c - 1.5, c + 1.5, 0.04, z0, z1, "soot")
                else:
                    k.oquad(o, u, n, c - 1.5, c + 1.5, 0.04, z0, z1, "glass")
                    k.obox(o, u, n, c - 1.55, c + 1.55, 0.04, 0.09, (z0 + z1) / 2 - 0.05, (z0 + z1) / 2 + 0.05, "frame")
                    k.obox(o, u, n, c - 0.05, c + 0.05, 0.04, 0.09, z0, z1, "frame")
                k.obox(o, u, n, c - 1.8, c + 1.8, 0, 0.25, z0 - 0.25, z0, "concrete")
                k.obox(o, u, n, c - 1.7, c + 1.7, 0, 0.22, z1, z1 + 0.45, "brick")  # segmental arch head
        for z in zs[1:-1]:
            k.obox(o, u, n, -0.2, L + 0.2, 0, 0.18, z - 0.25, z, "concrete")
        k.obox(o, u, n, -0.3, L + 0.3, 0, 0.45, H, H + 0.9, "concrete")  # parapet coping
    # gabled roof with a glazed monitor along the ridge
    k.hip_roof(x0 - 0.4, y0 - 0.4, x1 + 0.4, y1 + 0.4, H + 0.9, 7.0, 99.0, "zincdark", ridge=True)
    k.box(x0 + 4, -3.2, H + 0.9 + 5.5, x1 - 6, 3.2, H + 0.9 + 8.6, "skylight")
    k.hip_roof(x0 + 3.6, -3.6, x1 - 5.6, 3.6, H + 0.9 + 8.6, 2.2, 99.0, "zincdark", ridge=True)
    # lower annex (boiler house) on the north side
    k.box(x0 + 6, y1, 0, x0 + 26, y1 + 11, 9.5, "brick")
    k.box(x0 + 5.7, y1, 9.5, x0 + 26.3, y1 + 11.3, 10.1, "concrete")
    for b in range(4):
        c = x0 + 8.5 + b * 5
        k.oquad((c, y1 + 11, 0), (1, 0, 0), (0, 1, 0), -1.4, 1.4, 0.04, 1.5, 7.5, "glass")
    # chimney: square brick plinth through the roof, then a tapering round shaft with bands, sooty crown
    k.box(-4.0, -4.0, 0, 4.0, 4.0, H + 11.0, "brick")
    k.box(-4.4, -4.4, H + 11.0, 4.4, 4.4, H + 12.0, "concrete")
    shaft0 = H + 12.0
    if damaged:
        top = min(top, 52.0)
    seg = 18
    r0, r1 = 3.6, 2.6
    k.cylinder(0, 0, shaft0, top - 2.0, r0, seg, "brick", cap=False, r1=r1)
    for t in (0.3, 0.6, 0.85):
        z = shaft0 + (top - 2.0 - shaft0) * t
        rr = r0 + (r1 - r0) * t + 0.15
        k.cylinder(0, 0, z, z + 0.6, rr, seg, "concrete", cap=False)
    if damaged:
        # broken crown: jagged ring of uneven brick stubs
        for i in range(seg):
            a0, a1 = 2 * math.pi * i / seg, 2 * math.pi * (i + 1) / seg
            h = k.rnd.uniform(0.0, 3.5)
            p0 = (r1 * math.cos(a0), r1 * math.sin(a0), top - 2.0)
            p1 = (r1 * math.cos(a1), r1 * math.sin(a1), top - 2.0)
            k.poly([p0, p1, (p1[0], p1[1], top - 2.0 + h), (p0[0], p0[1], top - 2.0 + h)], "soot")
    else:
        k.cylinder(0, 0, top - 2.0, top - 0.6, r1 + 0.45, seg, "brick")
        k.cylinder(0, 0, top - 0.6, top, r1 + 0.6, seg, "soot")
    return k


def brick_facades(k, x0, y0, x1, y1, floors, bay=4.2, damaged=False, door_side=None, wall="brick"):
    """Brick piers, segmental windows and floor bands on the four walls of a box (x0..x1, y0..y1). Returns height."""
    zs, H = [0.0], 0.0
    for h in floors:
        H += h
        zs.append(H)
    walls = (((x0, y0, 0), (1, 0, 0), (0, -1, 0), x1 - x0), ((x1, y1, 0), (-1, 0, 0), (0, 1, 0), x1 - x0),
             ((x1, y0, 0), (0, 1, 0), (1, 0, 0), y1 - y0), ((x0, y1, 0), (0, -1, 0), (-1, 0, 0), y1 - y0))
    for side, (o, u, n, L) in enumerate(walls):
        bays = max(1, int(L // bay))
        pitch = L / bays
        for b in range(bays + 1):
            k.obox(o, u, n, b * pitch - 0.35, b * pitch + 0.35, 0, 0.3, 0, H, wall)
        for b in range(bays):
            c = b * pitch + pitch / 2
            for f in range(len(floors)):
                if f == 0 and side == door_side and b % 3 == 1:
                    k.oquad(o, u, n, c - 1.6, c + 1.6, 0.04, 0, min(3.8, zs[1] - 0.5), "door")
                    continue
                z0 = zs[f] + (1.1 if f == 0 else 0.8)
                z1 = zs[f + 1] - 0.8
                if z1 - z0 < 0.8:
                    continue
                slot = "soot" if damaged and k.rnd.random() < 0.35 else "glass"
                k.oquad(o, u, n, c - 1.1, c + 1.1, 0.04, z0, z1, slot)
                k.obox(o, u, n, c - 1.3, c + 1.3, 0, 0.2, z0 - 0.2, z0, "concrete")
                k.obox(o, u, n, c - 1.25, c + 1.25, 0, 0.18, z1, z1 + 0.35, wall)
        for z in zs[1:-1]:
            k.obox(o, u, n, -0.1, L + 0.1, 0, 0.15, z - 0.2, z, "concrete")
    return H


def warehouse(name, seed, w=36.0, d=18.0, floors=(4.8, 4.2, 4.2), damaged=False):
    """Brick warehouse / loft: gabled roof, loading doors with hoist beams, rooftop water tank (or burnt-out roof)."""
    k = Kit(name, seed)
    x0, x1, y0, y1 = -w / 2, w / 2, -d / 2, d / 2
    H = sum(floors)
    k.box(x0, y0, 0, x1, y1, H, "brick")
    brick_facades(k, x0, y0, x1, y1, floors, damaged=damaged, door_side=0)
    k.box(x0 - 0.2, y0 - 0.2, H, x1 + 0.2, y1 + 0.2, H + 0.6, "concrete")
    if damaged:
        k.poly([(x0 + 0.4, y0 + 0.4, H + 0.65), (x1 - 0.4, y0 + 0.4, H + 0.65), (x1 - 0.4, y1 - 0.4, H + 0.65),
                (x0 + 0.4, y1 - 0.4, H + 0.65)], "char", (1, 0, 0))
        for i in range(int(w // 2.5)):
            x = x0 + 1.5 + i * 2.5
            if k.rnd.random() < 0.6:
                k.box(x - 0.15, y0 + 0.5, H + 0.6, x + 0.15, y0 + d * k.rnd.uniform(0.3, 1.0) - 0.5, H + 0.9, "char")
    else:
        rise = d * 0.3
        k.hip_roof(x0 - 0.5, y0 - 0.5, x1 + 0.5, y1 + 0.5, H + 0.6, rise, 99.0, "zincdark", ridge=True)
        k.box(x1 - 7, -1.5, H + 0.6, x1 - 4, 1.5, H + 0.6 + rise + 2.5, "iron")
        k.cylinder(x1 - 5.5, 0, H + 0.6 + rise + 2.5, H + 0.6 + rise + 5.5, 1.9, 10, "iron")
    for i in range(3):
        x = x0 + w * (i + 1) / 4
        k.box(x - 0.15, y0 - 1.6, H - 1.2, x + 0.15, y0, H - 0.9, "iron")
    return k


def sawtooth_shed(name, seed, w=48.0, d=30.0, h=7.5, teeth=6, damaged=False):
    """Single-storey works hall with a north-light sawtooth roof (glazed vertical faces towards +y)."""
    k = Kit(name, seed)
    x0, x1, y0, y1 = -w / 2, w / 2, -d / 2, d / 2
    k.box(x0, y0, 0, x1, y1, h, "brick")
    brick_facades(k, x0, y0, x1, y1, (h,), bay=5.0, damaged=damaged, door_side=0)
    k.box(x0 - 0.2, y0 - 0.2, h, x1 + 0.2, y1 + 0.2, h + 0.4, "concrete")
    pitch = d / teeth
    rise = pitch * 0.55
    for t in range(teeth):
        ya, yb = y0 + t * pitch, y0 + (t + 1) * pitch
        if damaged and k.rnd.random() < 0.4:
            continue  # bays whose roof has fallen in
        z0, z1 = h + 0.4, h + 0.4 + rise
        k.poly([(x0, ya, z0), (x1, ya, z0), (x1, yb, z1), (x0, yb, z1)], "zinc", (1, 0, 0))
        k.poly([(x1, yb, z0), (x0, yb, z0), (x0, yb, z1), (x1, yb, z1)], "skylight")
        k.poly([(x0, ya, z0), (x0, yb, z1), (x0, yb, z0)], "brick")
        k.poly([(x1, ya, z0), (x1, yb, z0), (x1, yb, z1)], "brick")
    return k


def workers_row(name, seed, n=6, unit=7.0, d=10.0, damaged=False):
    """Terrace of narrow 2-3 storey workers' houses: brick or plaster, pitched roofs, chimney stacks."""
    k = Kit(name, seed)
    x = -n * unit / 2
    for _ in range(n):
        floors = [3.4, 3.0] + ([2.8] if k.rnd.random() < 0.5 else [])
        wall = "brick" if k.rnd.random() < 0.55 else "court"
        x0, x1 = x, x + unit
        H = sum(floors)
        k.box(x0, -d / 2, 0, x1, d / 2, H, wall)
        brick_facades(k, x0, -d / 2, x1, d / 2, floors, bay=3.4, damaged=damaged, door_side=0, wall=wall)
        if damaged and k.rnd.random() < 0.35:
            k.poly([(x0 + 0.2, -d / 2 + 0.2, H + 0.02), (x1 - 0.2, -d / 2 + 0.2, H + 0.02), (x1 - 0.2, d / 2 - 0.2, H + 0.02),
                    (x0 + 0.2, d / 2 - 0.2, H + 0.02)], "char", (1, 0, 0))
        else:
            rise = d * 0.32
            k.hip_roof(x0 - 0.05, -d / 2 - 0.4, x1 + 0.05, d / 2 + 0.4, H, rise, 0.01, "zincdark", ridge=True)
            k.box(x1 - 0.5, -0.9, H + d * 0.2, x1 + 0.5, 0.9, H + rise + 1.6, "chimney")
            for py in (-0.45, 0.45):
                k.cylinder(x1, py, H + rise + 1.6, H + rise + 2.2, 0.13, 6, "pot")
        x += unit
    return k


def gasholder(name, seed, r=16.0, h=24.0):
    """Gas holder: steel lattice guide frame around a dark tank (Paris industrial-suburb skyline mark)."""
    k = Kit(name, seed)
    k.cylinder(0, 0, 0, h * 0.8, r - 0.6, 24, "zincdark")
    k.dome(0, 0, h * 0.8, r - 0.6, 1.6, 24, 3, "zincdark")
    cols = 16
    for i in range(cols):
        a = 2 * math.pi * i / cols
        cx, cy = r * math.cos(a), r * math.sin(a)
        k.box(cx - 0.35, cy - 0.35, 0, cx + 0.35, cy + 0.35, h, "iron")
    for z in (h * 0.33, h * 0.66, h):
        for i in range(cols):
            a0, a1 = 2 * math.pi * i / cols, 2 * math.pi * (i + 1) / cols
            p0 = (r * math.cos(a0), r * math.sin(a0))
            p1 = (r * math.cos(a1), r * math.sin(a1))
            k.poly([(p0[0], p0[1], z - 0.5), (p1[0], p1[1], z - 0.5), (p1[0], p1[1], z), (p0[0], p0[1], z)], "iron")
    return k


BUILDINGS = {
    "SM_M3_CornerRotunda": (corner_rotunda, {}),
    "SM_M3_Pavilion": (pavilion, {}),
    "SM_M3_MarketHall": (market_hall, {}),
    "SM_M3_Annex_A": (annex, {"w": 24.0, "d": 11.0, "floors": 2}),
    "SM_M3_Annex_B": (annex, {"w": 18.0, "d": 10.0, "floors": 3}),
    "SM_M3_Chapel": (chapel, {}),
    "SM_M3_Townhouse_A": (townhouse, {"w": 14.0, "d": 15.0, "floors": 6, "sides": ("s",)}),
    "SM_M3_Townhouse_B": (townhouse, {"w": 18.0, "d": 15.0, "floors": 5, "sides": ("s", "e")}),
    "SM_M3_Townhouse_C": (townhouse, {"w": 22.0, "d": 16.0, "floors": 5, "sides": ("s", "n")}),
    "SM_M3_Townhouse_D": (townhouse, {"w": 12.0, "d": 14.0, "floors": 4, "sides": ("s",)}),
    "SM_M3_Fountain": (fountain, {}),
    "SM_M3_FactoryStack_A": (factory_stack, {"top": 67.0}),
    "SM_M3_FactoryStack_B": (factory_stack, {"top": 72.0}),
    "SM_M3_FactoryStack_C": (factory_stack, {"top": 77.0}),
    "SM_M3_FactoryStack_Damaged": (factory_stack, {"top": 50.0, "damaged": True}),
    "SM_M3_Warehouse_A": (warehouse, {"w": 36.0, "d": 18.0, "floors": (4.8, 4.2, 4.2)}),
    "SM_M3_Warehouse_B": (warehouse, {"w": 28.0, "d": 16.0, "floors": (4.8, 4.2, 4.2, 4.0)}),
    "SM_M3_Warehouse_Burnt": (warehouse, {"w": 36.0, "d": 18.0, "floors": (4.8, 4.2, 4.2), "damaged": True}),
    "SM_M3_Sawtooth_A": (sawtooth_shed, {"w": 48.0, "d": 30.0, "teeth": 6}),
    "SM_M3_Sawtooth_B": (sawtooth_shed, {"w": 32.0, "d": 24.0, "teeth": 5}),
    "SM_M3_Sawtooth_Burnt": (sawtooth_shed, {"w": 48.0, "d": 30.0, "teeth": 6, "damaged": True}),
    "SM_M3_WorkersRow_A": (workers_row, {"n": 6}),
    "SM_M3_WorkersRow_B": (workers_row, {"n": 4}),
    "SM_M3_WorkersRow_Burnt": (workers_row, {"n": 6, "damaged": True}),
    "SM_M3_Gasholder": (gasholder, {}),
}


def render_preview(obj, path):
    scene = bpy.context.scene
    for o in scene.objects:
        o.hide_render = o.type == "MESH" and o is not obj
    xs = [v.co.x for v in obj.data.vertices]; ys = [v.co.y for v in obj.data.vertices]; zs = [v.co.z for v in obj.data.vertices]
    size = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    cam_data = bpy.data.cameras.new("prev")
    cam = bpy.data.objects.new("prev", cam_data)
    scene.collection.objects.link(cam)
    from mathutils import Vector
    cam.location = (size * 0.95, -size * 1.25, size * 0.85)
    target = Vector((0, 0, (max(zs)) * 0.35))
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.render.resolution_x, scene.render.resolution_y = 800, 600
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam, do_unlink=True)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--only", default="")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    report = {}
    for seed, (name, (fn, kw)) in enumerate(BUILDINGS.items()):
        if a.only and a.only not in name:
            continue
        k = fn(name, 20261007 + seed * 101, **kw)
        obj = k.build()
        me = obj.data
        xs = [v.co.x for v in me.vertices]; ys = [v.co.y for v in me.vertices]; zs = [v.co.z for v in me.vertices]
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.export_scene.fbx(filepath=os.path.join(a.out, name + ".fbx"), use_selection=True, object_types={"MESH"},
                                 mesh_smooth_type="FACE", add_leaf_bones=False, bake_anim=False, path_mode="STRIP",
                                 colors_type="LINEAR")
        me.calc_loop_triangles()
        report[name] = {"fbx": name + ".fbx", "tris": len(me.loop_triangles),
                        "bounds_m": [[round(min(xs), 2), round(min(ys), 2), 0.0], [round(max(xs), 2), round(max(ys), 2), round(max(zs), 2)]],
                        "slots": [m.name for m in me.materials]}
        if a.preview:
            render_preview(obj, os.path.join(a.out, "preview_%s.png" % name))
    with open(os.path.join(a.out, "m3_buildings.json"), "w", encoding="utf-8") as f:
        json.dump({"generator": "Tools/m3/blender_paris_buildings.py", "buildings": report}, f, indent=1)
    print("M3_BUILDINGS_OK", len(report), json.dumps({k: v["tris"] for k, v in report.items()}))


if __name__ == "__main__":
    main()
