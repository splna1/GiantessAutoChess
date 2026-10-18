# -*- coding: utf-8 -*-
"""M6 military-base detail kit — hard-surface helpers on top of the Warsaw
mesh builder (Tools/warsaw/lib_geom.py, read-only).

Local detail frame convention (same as lib_geom.window):
    x = width, z = height, y = 0 at the wall plane, -Y = OUTWARD.
So a builder places a detail with `mb.at(cx, wall_y, z, rz)` and the helper
draws outward.  Everything accumulates in python lists -> headless safe.
"""
import bpy
import bmesh
import json
import math
import os
import random
import sys
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
WARSAW = os.path.join(ROOT, "Tools", "warsaw")
# NOTE: Tools/warsaw also contains a `spec.py`; this kit's spec is `m6spec.py`
# so the two never shadow each other.  Both dirs go to the END of sys.path.
for p in (HERE, WARSAW):
    if p in sys.path:
        sys.path.remove(p)
    sys.path.append(p)

import lib_geom as G          # noqa: E402
import m6spec as S            # noqa: E402

TAU = math.pi * 2.0
Vector = Vector


# ---------------------------------------------------------------- materials
_MC = {}

# pattern -> (noise frequency, bump strength, colour contrast, roughness wobble)
_PAT = {
    None:       (26.0, 0.030, 0.10, 0.02),
    "concrete": (11.0, 0.180, 0.26, 0.05),
    "plaster":  (18.0, 0.080, 0.13, 0.02),
    "stone":    (8.0, 0.240, 0.30, 0.06),
    "metal":    (40.0, 0.040, 0.09, 0.03),
    "brushed":  (90.0, 0.022, 0.10, 0.10),   # fine matte grain for heavy steel
    "plate":    (13.0, 0.085, 0.15, 0.05),
}


def reset_cache():
    """Drop cached datablocks after bpy.ops.wm.open_mainfile()."""
    _MC.clear()


def mat(key):
    """Principled material: one noise drives colour mottling, roughness and bump.

    Deliberately NOT the Warsaw Voronoi 'concrete' pattern — at building scale
    that reads as shattered ice.  Frequencies are in cycles per metre.
    """
    if key in _MC:
        return _MC[key]
    hexcol, rough, metal, pattern, scale = S.MAT[key]
    freq, bump_s, contrast, rough_var = _PAT.get(pattern, _PAT[None])
    freq *= max(0.25, scale)
    m = bpy.data.materials.new("M6_" + key)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (620, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (320, 0)
    col = G.hex_lin(hexcol)
    dark = tuple(c * (1.0 - contrast) for c in col[:3]) + (1.0,)
    light = tuple(min(1.0, c * (1.0 + contrast * 0.55)) for c in col[:3]) + (1.0,)

    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-820, 0)
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.location = (-640, 0)
    mp.inputs["Scale"].default_value = (freq, freq, freq)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.location = (-450, 40)
    nz.inputs["Scale"].default_value = 1.0
    nz.inputs["Detail"].default_value = 7.0
    nz.inputs["Roughness"].default_value = 0.62
    nt.links.new(mp.outputs["Vector"], nz.inputs["Vector"])

    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.location = (-220, 150)
    ramp.color_ramp.elements[0].position = 0.28
    ramp.color_ramp.elements[0].color = dark
    ramp.color_ramp.elements[1].position = 0.74
    ramp.color_ramp.elements[1].color = light
    nt.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])

    rr = nt.nodes.new("ShaderNodeMapRange")
    rr.location = (-220, -150)
    rr.inputs["From Min"].default_value = 0.0
    rr.inputs["From Max"].default_value = 1.0
    rr.inputs["To Min"].default_value = max(0.02, rough - rough_var)
    rr.inputs["To Max"].default_value = min(1.0, rough + rough_var)
    nt.links.new(nz.outputs["Fac"], rr.inputs["Value"])
    nt.links.new(rr.outputs["Result"], bsdf.inputs["Roughness"])
    bsdf.inputs["Metallic"].default_value = metal
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.42

    bump = nt.nodes.new("ShaderNodeBump")
    bump.location = (80, -320)
    bump.inputs["Strength"].default_value = bump_s
    bump.inputs["Distance"].default_value = 0.06
    nt.links.new(nz.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    m.diffuse_color = col
    _MC[key] = m
    return m


def emat(key):
    """Cached emissive material from spec.EMAT (Emission shader, no BSDF)."""
    if key in _MC:
        return _MC[key]
    hexcol, strength = S.EMAT[key]
    m = bpy.data.materials.new("M6_" + key)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (300, 0)
    em = nt.nodes.new("ShaderNodeEmission")
    em.location = (80, 0)
    em.inputs["Color"].default_value = G.hex_lin(hexcol)
    em.inputs["Strength"].default_value = strength
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    m.diffuse_color = G.hex_lin(hexcol)
    _MC[key] = m
    return m


# ---------------------------------------------------------------- 2D helpers
def _clip(pts, nx, nz, c, keep_le=True):
    """Sutherland-Hodgman against nx*x + nz*z <= c (or >=)."""
    out = []
    n = len(pts)
    for i in range(n):
        ax, az = pts[i]
        bx, bz = pts[(i + 1) % n]
        fa = nx * ax + nz * az - c
        fb = nx * bx + nz * bz - c
        if not keep_le:
            fa, fb = -fa, -fb
        ina, inb = fa <= 0.0, fb <= 0.0
        if ina:
            out.append((ax, az))
        if ina != inb:
            t = fa / (fa - fb)
            out.append((ax + (bx - ax) * t, az + (bz - az) * t))
    return out


def _rect(w, h, cx=0.0, cz=0.0):
    return [(cx - w / 2, cz - h / 2), (cx + w / 2, cz - h / 2),
            (cx + w / 2, cz + h / 2), (cx - w / 2, cz + h / 2)]


# ---------------------------------------------------------------- mesh builder
class MB(G.MB):
    """Detail builder: same vertex/face accumulator, more hard-surface verbs."""

    # ---- wall systems ---------------------------------------------------
    def panel_grid(self, w, h, nu, nv, z0=0.0, gap=0.05, thick=0.055, alt=0.014,
                   skip=()):
        """Gasketed panel field standing proud of the wall plane."""
        pw = (w - gap * (nu + 1)) / nu
        ph = (h - gap * (nv + 1)) / nv
        for i in range(nu):
            for j in range(nv):
                if (i, j) in skip:
                    continue
                x0 = -w / 2 + gap + i * (pw + gap)
                zz = z0 + gap + j * (ph + gap)
                t = thick + (alt if (i + j) % 2 else 0.0)
                self.box(x0, -t, zz, x0 + pw, 0.02, zz + ph)

    def rib_wall(self, w, h, n, z0=0.0, thick=0.10, depth=0.05, skip=()):
        """Vertical corrugation / stiffener ribs on a wall."""
        pitch = w / n
        for i in range(n + 1):
            if i in skip:
                continue
            x = -w / 2 + i * pitch
            self.box(x - thick / 2, -depth, z0, x + thick / 2, 0.0, z0 + h)

    def window_band(self, w, h, n, z0=0.0, mull=0.09, head=0.16, sill=0.14):
        """Ribbon glazing with mullions + head/sill trims (local wall frame)."""
        self.box(-w / 2, -0.075, z0, w / 2, -0.015, z0 + h)          # glass
        for i in range(n + 1):
            x = -w / 2 + i * (w / n)
            self.box(x - mull / 2, -0.10, z0, x + mull / 2, -0.005, z0 + h)
        self.box(-w / 2 - 0.05, -0.17, z0 + h, w / 2 + 0.05, 0.0, z0 + h + head)
        self.box(-w / 2 - 0.06, -0.20, z0 - sill, w / 2 + 0.06, 0.0, z0)

    def punch_window(self, w, h, z0=0.0, frame=0.10, proud=0.12):
        """Single punched opening: dark reveal + steel frame."""
        self.box(-w / 2, -0.06, z0, w / 2, -0.01, z0 + h)
        for sx in (-1, 1):
            x0 = sx * w / 2
            self.box(min(x0, x0 + sx * frame), -proud, z0 - frame * 0.4,
                     max(x0, x0 + sx * frame), 0.0, z0 + h + frame * 0.4)
        self.box(-w / 2 - frame, -proud, z0 + h, w / 2 + frame, 0.0, z0 + h + frame)
        self.box(-w / 2 - frame, -proud - 0.05, z0 - frame, w / 2 + frame, 0.0, z0)

    def louver(self, w, h, n, z0=0.0, slat=0.115, angle=-34.0, frame=True):
        """Weather louvre bank: tilted slats inside a frame."""
        if frame:
            self.box(-w / 2 - 0.06, -0.09, z0 - 0.06, w / 2 + 0.06, 0.0, z0 + h + 0.06)
        pitch = h / n
        for i in range(n):
            zz = z0 + (i + 0.5) * pitch
            self.push(Matrix.Translation((0, -0.02, zz)) @
                      Matrix.Rotation(math.radians(angle), 4, "X"))
            self.box(-w / 2, -slat / 2, -0.008, w / 2, slat / 2, 0.008)
            self.pop()

    def roller_door(self, w, h, n=14, z0=0.0):
        """Segmented roller shutter with guide rails."""
        pitch = h / n
        for i in range(n):
            zz = z0 + i * pitch
            self.box(-w / 2, -0.09, zz + 0.012, w / 2, -0.02, zz + pitch - 0.012)
        for sx in (-1, 1):
            x0 = sx * w / 2
            self.box(min(x0, x0 + sx * 0.16), -0.16, z0, max(x0, x0 + sx * 0.16), 0.0, z0 + h)
        self.box(-w / 2 - 0.2, -0.20, z0 + h, w / 2 + 0.2, 0.0, z0 + h + 0.22)

    def hazard(self, w, h, n=6, z0=0.0, y0=-0.014, y1=0.0):
        """Diagonal hazard stripes (45 deg) clipped exactly to the rectangle."""
        step = (w + h) / float(n)
        base = _rect(w, h, 0.0, z0 + h / 2)
        for i in range(n):
            if i % 2:
                continue
            c0 = i * step
            c1 = (i + 1) * step
            poly = _clip(base, 1.0, 1.0, c1, True)
            poly = _clip(poly, 1.0, 1.0, c0 + 0.001, False)
            if len(poly) >= 3:
                self.prism_y(poly, y0, y1)

    def paint_line(self, p0, p1, width=0.12, z=0.225):
        """Flat painted line on a deck (world-ish local x/y)."""
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        L = math.hypot(dx, dy)
        if L < 1e-6:
            return
        ang = math.degrees(math.atan2(dy, dx))
        self.push(Matrix.Translation((p0[0], p0[1], z)) @
                  Matrix.Rotation(math.radians(ang), 4, "Z"))
        self.box(0.0, -width / 2, 0.0, L, width / 2, 0.012)
        self.pop()

    def ring_hex(self, r, z=0.02, tube=0.16, seg=6):
        """Hexagonal marking / pad ring as a closed tube of small radius."""
        pts = [(math.cos(TAU * i / seg) * r, math.sin(TAU * i / seg) * r, z + tube)
               for i in range(seg + 1)]
        self.tube(pts, tube, seg=8)

    def ring_circle(self, r, z=0.02, tube=0.12, seg=32):
        pts = [(math.cos(TAU * i / seg) * r, math.sin(TAU * i / seg) * r, z + tube)
               for i in range(seg + 1)]
        self.tube(pts, tube, seg=8)

    # ---- structure / circulation ---------------------------------------
    def railing(self, L, h=1.10, spacing=1.35, z0=0.0, thick=0.045, kick=True):
        """Industrial guardrail running along +local X from 0..L."""
        self.box(0.0, -thick / 2, z0 + h - thick, L, thick / 2, z0 + h)
        self.box(0.0, -thick / 2.4, z0 + h * 0.52, L, thick / 2.4, z0 + h * 0.52 + thick * 0.8)
        n = max(2, int(L / spacing))
        for i in range(n + 1):
            x = i * L / n
            self.box(x - thick / 2, -thick / 2, z0, x + thick / 2, thick / 2, z0 + h)
        if kick:
            self.box(0.0, -0.012, z0 + 0.06, L, 0.012, z0 + 0.16)

    def ladder(self, H, w=0.46, z0=0.0, rungs=None, rails=0.045):
        """Vertical caged-ladder stand-in: rails + rungs on the local wall."""
        n = rungs or max(3, int(H / 0.32))
        for sx in (-1, 1):
            x = sx * w / 2
            self.box(x - rails / 2, -0.09, z0, x + rails / 2, -0.03, z0 + H)
        for i in range(n + 1):
            zz = z0 + i * H / n
            self.box(-w / 2, -0.075, zz, w / 2, -0.045, zz + 0.028)

    def stair_run(self, W, run, rise, steps, z0=0.0):
        """Straight stair ascending along +local Y, treads + stringers."""
        for i in range(steps):
            y0 = i * run / steps
            zz = z0 + i * rise / steps
            self.box(-W / 2, y0, zz, W / 2, y0 + run / steps, zz + rise / steps * 0.55)
        for sx in (-1, 1):
            x0 = sx * W / 2
            self.push(Matrix.Translation((x0, 0, z0)) @
                      Matrix.Rotation(-math.atan2(rise, run), 4, "X"))
            self.box(-0.03, -0.05, 0.0, 0.03, math.hypot(run, rise), 0.30)
            self.pop()

    def catwalk(self, w, d, z, rail_h=1.1, grate=True):
        """Rectangular platform with railing on three sides."""
        self.box(-w / 2, -d / 2, z - 0.10, w / 2, d / 2, z)
        if grate:
            n = max(4, int(w / 0.32))
            for i in range(n):
                x = -w / 2 + i * w / n
                self.box(x, -d / 2, z, x + 0.10, d / 2, z + 0.03)
        for (x, y, ang) in ((-w / 2, -d / 2, 0.0), (-w / 2, d / 2, 0.0),
                            (w / 2, -d / 2, 90.0), (w / 2, d / 2, 90.0)):
            self.push(Matrix.Translation((x, y, z)) @
                      Matrix.Rotation(math.radians(ang), 4, "Z"))
            self.railing(d if ang == 0.0 else w, h=rail_h)
            self.pop()

    # ---- mechanical / equipment ----------------------------------------
    def ac_unit(self, w=1.7, d=0.95, h=1.15):
        """Condenser: body, louvred face, fan grille, feet, pipes."""
        self.box(-w / 2, -d, 0.10, w / 2, 0.0, h)
        self.box(-w / 2 + 0.06, -d - 0.03, 0.16, w / 2 - 0.06, -d, h - 0.08)
        for i in range(6):
            zz = 0.22 + i * (h - 0.36) / 6
            self.box(-w / 2 + 0.08, -d - 0.05, zz, w / 2 - 0.08, -d - 0.02, zz + 0.035)
        self.lathe([(0.26, h), (0.26, h + 0.03), (0.0, h + 0.03)], 0.0, -d / 2, seg=16,
                   cap_bottom=True, cap_top=False)
        for sx in (-1, 1):
            x = sx * (w / 2 - 0.22)
            self.box(x - 0.05, -d + 0.12, 0.0, x + 0.05, -d + 0.25, 0.10)
            self.box(x - 0.05, -d + 0.12, h, x + 0.05, -d + 0.25, h + 0.35)

    def vent_cap(self, r=0.34, h=0.65, z0=1.0):
        self.lathe([(r, z0), (r, z0 + h * 0.55), (r * 1.35, z0 + h * 0.62),
                    (r * 1.35, z0 + h * 0.72), (0.0, z0 + h * 0.95)], 0.0, 0.0, seg=16)

    def extractor(self, r=0.85, h=1.5, z0=0.0):
        """Roof smoke/heat extractor: curb, barrel, cowl, bird mesh."""
        self.lathe([(r * 1.15, z0), (r * 1.15, z0 + 0.16)], 0, 0, seg=20)
        self.lathe([(r, z0 + 0.16), (r * 0.92, z0 + h)], 0, 0, seg=20)
        self.lathe([(r * 0.92, z0 + h), (r * 1.35, z0 + h + 0.18),
                    (r * 1.15, z0 + h + 0.50), (0.0, z0 + h + 0.55)], 0, 0, seg=20,
                   cap_bottom=False, cap_top=False)

    def pipe_run(self, pts, r=0.10, seg=8, r_end=None):
        self.tube([tuple(p) for p in pts], r, seg=seg, r_end=r_end)

    def cable_tray(self, pts, w=0.34, h=0.12):
        """U-channel along a polyline: bottom + two lips (square tubes)."""
        for i in range(len(pts) - 1):
            p0, p1 = Vector(pts[i]), Vector(pts[i + 1])
            d = p1 - p0
            L = d.length
            if L < 1e-6:
                continue
            ang = math.degrees(math.atan2(d.y, d.x))
            pitch = math.degrees(math.asin(max(-1.0, min(1.0, d.z / L))))
            self.push(Matrix.Translation(p0) @
                      Matrix.Rotation(math.radians(ang), 4, "Z") @
                      Matrix.Rotation(-math.radians(pitch), 4, "Y"))
            self.box(0, -w / 2, 0.0, L, w / 2, 0.04)
            self.box(0, -w / 2, 0.04, L, -w / 2 + 0.03, h)
            self.box(0, w / 2 - 0.03, 0.04, L, w / 2, h)
            self.pop()

    def container(self, L=6.06, W=2.44, H=2.60, ribs=20, z0=0.0):
        """ISO container with corrugation, corner castings and door end."""
        self.box(-W / 2, -L / 2, z0, W / 2, L / 2, z0 + H)
        for i in range(ribs):
            y = -L / 2 + 0.14 + i * (L - 0.28) / (ribs - 1)
            for sx in (-1, 1):
                x = sx * (W / 2)
                self.box(min(x, x + sx * 0.035), y - 0.045, z0 + 0.10,
                         max(x, x + sx * 0.035), y + 0.045, z0 + H - 0.10)
        for sx in (-1, 1):
            for sy in (-1, 1):
                x, y = sx * (W / 2 - 0.09), sy * (L / 2 - 0.09)
                self.box(x - 0.09, y - 0.09, z0 + H - 0.16, x + 0.09, y + 0.09, z0 + H)
                self.box(x - 0.09, y - 0.09, z0, x + 0.09, y + 0.09, z0 + 0.16)
        # door end (local +Y)
        self.box(-W / 2 + 0.08, L / 2, z0 + 0.10, -0.03, L / 2 + 0.035, z0 + H - 0.10)
        self.box(0.03, L / 2, z0 + 0.10, W / 2 - 0.08, L / 2 + 0.035, z0 + H - 0.10)
        for zz in (z0 + 0.35, z0 + H - 0.35):
            self.box(-0.55, L / 2 + 0.035, zz - 0.035, 0.55, L / 2 + 0.07, zz + 0.035)

    def solar_panel(self, w, h, nu=6, nv=3):
        """Frame + cell grid (tilted by the caller)."""
        self.box(-w / 2, -0.03, 0.0, w / 2, 0.03, h)
        for i in range(1, nu):
            x = -w / 2 + i * w / nu
            self.box(x - 0.012, -0.045, 0.01, x + 0.012, 0.045, h - 0.01)
        for j in range(1, nv):
            z = j * h / nv
            self.box(-w / 2 + 0.01, -0.042, z - 0.010, w / 2 - 0.01, 0.042, z + 0.010)
        self.box(-w / 2 - 0.04, -0.06, -0.02, w / 2 + 0.04, 0.06, 0.03)

    def dish(self, R, depth, seg=24, rings=6, z0=0.0):
        """Paraboloid opening toward local -Y, rim at y=0."""
        def fn(u, v):
            a = TAU * u
            r = R * (1.0 - v ** 1.7)
            return (math.cos(a) * r, -depth * (1.0 - (r / R) ** 2), z0 + math.sin(a) * r)
        self.grid(fn, seg, rings, close_u=True)

    def aesa_panel(self, w, h, nx=8, ny=6):
        """Phased-array face: dark radiating surface + element grid + frame."""
        self.box(-w / 2, -0.16, -h / 2, w / 2, 0.0, h / 2)
        for i in range(nx):
            for j in range(ny):
                x = -w / 2 + (i + 0.5) * w / nx
                z = -h / 2 + (j + 0.5) * h / ny
                self.box(x - w / nx * 0.36, -0.19, z - h / ny * 0.36,
                         x + w / nx * 0.36, -0.16, z + h / ny * 0.36)
        self.box(-w / 2 - 0.10, -0.22, -h / 2 - 0.10, w / 2 + 0.10, 0.0, h / 2 + 0.10)

    def whip(self, h, r=0.035, z0=0.0):
        self.lathe([(r * 2.2, z0), (r * 1.6, z0 + 0.25), (r, z0 + h), (0.0, z0 + h + 0.05)],
                   0, 0, seg=8)

    def beacon(self, r=0.10, z0=0.0):
        self.lathe([(r, z0), (r, z0 + r * 1.4), (r * 0.6, z0 + r * 2.0),
                    (0.0, z0 + r * 2.2)], 0, 0, seg=10)

    def sign_plate(self, w, h, z0=0.0, thick=0.05):
        self.box(-w / 2, -thick, z0, w / 2, 0.0, z0 + h)

    def bollard(self, r=0.11, h=1.0):
        self.lathe([(r, 0.0), (r, h - 0.10), (r * 0.72, h), (0.0, h)], 0, 0, seg=12)

    def jersey(self, L=3.0, h=1.05, w=0.62):
        """Concrete jersey barrier along local X."""
        poly = [(w / 2, 0.0), (w / 2, h * 0.28), (w * 0.22, h * 0.42),
                (w * 0.16, h), (-w * 0.16, h), (-w * 0.22, h * 0.42),
                (-w / 2, h * 0.28), (-w / 2, 0.0)]
        self.prism_y(poly, -L / 2, L / 2)

    def blast_wall(self, L, H, T, lean=0.22, z0=0.0):
        """Tapered protective wall along local X (thicker at the base)."""
        poly = [(-T / 2, z0), (T / 2, z0), (T / 2 - lean, z0 + H), (-T / 2 + lean, z0 + H)]
        self.prism_y(poly, -L / 2, L / 2)

    def truss(self, L, H, bays=6, chord=0.10):
        """Flat lattice beam along +X (two chords + zig-zag web)."""
        for sz in (-1, 1):
            z = H / 2 + sz * H / 2
            self.box(0.0, -chord / 2, z - chord / 2, L, chord / 2, z + chord / 2)
        for i in range(bays):
            x0 = i * L / bays
            x1 = (i + 1) * L / bays
            diag = math.hypot(L / bays, H)
            ang = math.degrees(math.atan2(H, L / bays)) * (1 if i % 2 else -1)
            self.push(Matrix.Translation((x0, 0, H / 2)) @
                      Matrix.Rotation(math.radians(-ang), 4, "Y"))
            self.box(0.0, -chord * 0.35, -diag / 2, chord * 0.7, chord * 0.35, diag / 2)
            self.pop()

    def arrow_marking(self, L=3.2, W=1.6, z=0.225):
        """Directional arrow painted on a deck (local X forward)."""
        self.box(0.0, -W * 0.18, z, L * 0.62, W * 0.18, z + 0.012)
        self.prism_z([(L * 0.58, -W / 2), (L, 0.0), (L * 0.58, W / 2)], z, z + 0.012)

    # ---- props ----------------------------------------------------------
    def vehicle(self, L=5.30, W=2.25, H=1.95, glass=None, rubber=None, z0=0.0):
        """Armoured 4x4 stand-in for scale.  Local +X forward, origin on ground."""
        glass = glass if glass is not None else self
        rubber = rubber if rubber is not None else self
        # hull with a chamfered nose
        self.prism_z([(-L / 2, -W / 2), (L / 2 - 0.55, -W / 2), (L / 2, -W / 2 + 0.45),
                      (L / 2, W / 2 - 0.45), (L / 2 - 0.55, W / 2), (-L / 2, W / 2)],
                     0.42 + z0, 1.22 + z0)
        self.box(-L / 2 + 0.15, -W / 2 + 0.05, 0.28 + z0, L / 2 - 0.4, W / 2 - 0.05, 0.46 + z0)
        # cab
        self.prism_z([(-L / 2 + 0.55, -W / 2 + 0.14), (L / 2 - 1.35, -W / 2 + 0.14),
                      (L / 2 - 1.15, -W / 2 + 0.30), (L / 2 - 1.15, W / 2 - 0.30),
                      (L / 2 - 1.35, W / 2 - 0.14), (-L / 2 + 0.55, W / 2 - 0.14)],
                     1.22 + z0, H + z0)
        glass.box(L / 2 - 1.48, -W / 2 + 0.20, 1.44 + z0, L / 2 - 1.20, W / 2 - 0.20, 1.82 + z0)
        for sy in (-1, 1):
            glass.box(-L / 2 + 0.75, sy * (W / 2 - 0.14) - 0.02, 1.46 + z0,
                      L / 2 - 1.55, sy * (W / 2 - 0.14) + 0.02, 1.78 + z0)
        # fenders + wheels
        for sx in (-1, 1):
            for sy in (-1, 1):
                x = sx * 1.62
                self.box(x - 0.62, sy * (W / 2 - 0.02) - 0.05, 0.86 + z0,
                         x + 0.62, sy * (W / 2 + 0.10), 1.10 + z0)
                rubber.push(Matrix.Translation((x, sy * (W / 2 - 0.06), 0.46 + z0)) @
                            Matrix.Rotation(math.pi / 2, 4, "X"))
                rubber.cyl(0.0, 0.0, -0.17, 0.17, 0.46, seg=18)
                rubber.pop()
                rubber.push(Matrix.Translation((x, sy * (W / 2 - 0.06), 0.46 + z0)) @
                            Matrix.Rotation(math.pi / 2, 4, "X"))
                rubber.cyl(0.0, 0.0, -0.19, 0.19, 0.22, seg=12)
                rubber.pop()
        # roof rack, bull bar, mirrors, whip
        self.box(-L / 2 + 0.65, -W / 2 + 0.25, H + z0, L / 2 - 1.45, W / 2 - 0.25, H + 0.09 + z0)
        for k in range(4):
            x = -L / 2 + 0.85 + k * 0.75
            self.box(x - 0.04, -W / 2 + 0.20, H + 0.09 + z0, x + 0.04, W / 2 - 0.20, H + 0.14 + z0)
        for sy in (-1, 1):
            self.box(L / 2 - 0.05, sy * 0.75 - 0.05, 0.70 + z0, L / 2 + 0.12, sy * 0.75 + 0.05, 1.05 + z0)
            self.box(-L / 2 + 0.1, sy * 1.02 - 0.04, 1.42 + z0, -L / 2 - 0.18, sy * 1.02 + 0.04, 1.52 + z0)
        self.tube([(-L / 2 + 0.3, W / 2 - 0.3, H + z0), (-L / 2 + 0.3, W / 2 - 0.3, H + 1.5 + z0)],
                  0.022, seg=6)

    def barrel(self, r=0.30, h=0.88, z0=0.0):
        self.lathe([(r, z0), (r, z0 + h), (r * 0.92, z0 + h + 0.04), (0.0, z0 + h + 0.04)], 0, 0, seg=14)
        for zz in (z0 + 0.22, z0 + 0.66):
            self.lathe([(r * 1.04, zz), (r * 1.04, zz + 0.05)], 0, 0, seg=14)

    def crate(self, w=1.2, d=0.8, h=0.9, z0=0.0):
        self.box(-w / 2, -d / 2, z0, w / 2, d / 2, z0 + h)
        for sx in (-1, 1):
            self.box(sx * (w / 2 - 0.06) - 0.03, -d / 2 - 0.02, z0 + 0.06,
                     sx * (w / 2 - 0.06) + 0.03, d / 2 + 0.02, z0 + h - 0.06)
        self.box(-w / 2 - 0.02, -d / 2 - 0.02, z0 + h - 0.10, w / 2 + 0.02, d / 2 + 0.02, z0 + h)

    def i_beam(self, L=20.0, d=1.10, b=0.42, tf=0.065, tw=0.038):
        """I-section member along +X, web centred, depth in Z."""
        h = d / 2.0
        poly = [(-b / 2, -h), (b / 2, -h), (b / 2, -h + tf), (tw / 2, -h + tf),
                (tw / 2, h - tf), (b / 2, h - tf), (b / 2, h), (-b / 2, h),
                (-b / 2, h - tf), (-tw / 2, h - tf), (-tw / 2, -h + tf),
                (-b / 2, -h + tf)]
        self.prism_x(poly, 0.0, L)

    def pipe_bundle(self, L=14.0, r=0.55, cols=3, rows=2, gap=0.06):
        """Stack of pipes along +X (rows in Z, cols in Y)."""
        for j in range(rows):
            for i in range(cols):
                y = (i - (cols - 1) / 2.0) * (2 * r + gap)
                z = r + j * (2 * r + gap) * 0.88
                self.push(Matrix.Translation((0.0, y, z)) @ Matrix.Rotation(math.pi / 2, 4, "Y"))
                self.cyl(0.0, 0.0, -L / 2, L / 2, r, seg=12)
                self.pop()

    def rebar_bundle(self, L=18.0, r=0.62, n=9):
        """Bundle of reinforcement bars along +X inside a strap."""
        for k in range(n):
            a = TAU * k / n
            y = math.cos(a) * r * 0.55
            z = r * 0.55 + math.sin(a) * r * 0.55
            self.push(Matrix.Translation((0.0, y, z)) @ Matrix.Rotation(math.pi / 2, 4, "Y"))
            self.cyl(0.0, 0.0, -L / 2, L / 2, 0.05, seg=5)
            self.pop()
        for sx in (-1, 1):
            self.box(sx * L * 0.28 - 0.05, -r * 0.85, 0.0, sx * L * 0.28 + 0.05, r * 0.85, r * 1.2)

    def pallet(self, w=2.4, d=1.2, h=1.2, z0=0.0, block=True):
        """Timber pallet + block/brick stack."""
        for k in range(3):
            self.box(-w / 2, -d / 2 + k * d / 3.0, z0, w / 2,
                     -d / 2 + k * d / 3.0 + 0.12, z0 + 0.16)
        self.box(-w / 2 + 0.2, -d / 2 + 0.1, z0, w / 2 - 0.2, d / 2 - 0.1, z0 + 0.30)
        if block:
            for i in range(4):
                for j in range(2):
                    for k in range(3):
                        self.box(-w / 2 + 0.25 + i * (w - 0.5) / 4,
                                 -d / 2 + 0.15 + j * (d - 0.3) / 2,
                                 z0 + 0.30 + k * 0.28,
                                 -w / 2 + 0.22 + i * (w - 0.5) / 4 + (w - 0.5) / 4 - 0.04,
                                 -d / 2 + 0.12 + j * (d - 0.3) / 2 + (d - 0.3) / 2 - 0.04,
                                 z0 + 0.56 + k * 0.28)

    def crawler(self, L=9.8, W=1.55, H=1.35, shoes=36, z0=0.0):
        """Crawler track unit: stadium belt with grouser shoes + frame + wheels.
        Runs along local X, width in Y."""
        R = H / 2.0
        straight = max(0.4, L - 2 * R)
        per = 2 * straight + TAU * R
        for i in range(shoes):
            s = i * per / shoes
            if s < straight:
                px, pz, ang = -straight / 2 + s, z0, 0.0
            elif s < straight + math.pi * R:
                a = -math.pi / 2 + (s - straight) / R
                px = straight / 2 + math.cos(a) * R
                pz = z0 + R + math.sin(a) * R
                ang = a + math.pi / 2
            elif s < 2 * straight + math.pi * R:
                px, pz, ang = straight / 2 - (s - straight - math.pi * R), z0 + 2 * R, 0.0
            else:
                a = math.pi / 2 + (s - 2 * straight - math.pi * R) / R
                px = -straight / 2 + math.cos(a) * R
                pz = z0 + R + math.sin(a) * R
                ang = a - math.pi / 2
            self.push(Matrix.Translation((px, 0.0, pz)) @ Matrix.Rotation(ang, 4, "Y"))
            self.box(-per / shoes * 0.46, -W / 2, -0.055, per / shoes * 0.46, W / 2, 0.055)
            self.box(-per / shoes * 0.30, -W / 2 + 0.06, 0.055,
                     per / shoes * 0.30, W / 2 - 0.06, 0.13)
            self.pop()
        self.box(-straight / 2 - 0.5, -W * 0.34, z0 + 0.20, straight / 2 + 0.5, W * 0.34,
                 z0 + H - 0.20)
        for sx in (-1, 1):
            x = sx * (straight / 2 + R * 0.55)
            self.push(Matrix.Translation((x, 0.0, z0 + R)) @ Matrix.Rotation(math.pi / 2, 4, "X"))
            self.cyl(0.0, 0.0, -W * 0.44, W * 0.44, R * 0.80, seg=14)
            self.pop()
            self.push(Matrix.Translation((x * 0.55, 0.0, z0 + R)) @ Matrix.Rotation(math.pi / 2, 4, "X"))
            self.cyl(0.0, 0.0, -W * 0.30, W * 0.30, R * 0.42, seg=10)
            self.pop()

    def lattice_boom(self, L, w0, w1, bays=18, chord=0.16, seg=5):
        """Square lattice boom along +X, chords + X bracing on four faces."""
        d0, d1 = w0 / 2.0, w1 / 2.0
        corners = ((-1, -1), (1, -1), (1, 1), (-1, 1))
        for i in range(bays):
            t0, t1 = i / float(bays), (i + 1) / float(bays)
            a0 = d0 + (d1 - d0) * t0
            a1 = d0 + (d1 - d0) * t1
            for (sy, sz) in corners:
                self.tube([(L * t0, sy * a0, sz * a0), (L * t1, sy * a1, sz * a1)],
                          chord, seg=seg)
            for k in range(4):
                (sy0, sz0) = corners[k]
                (sy1, sz1) = corners[(k + 1) % 4]
                p0 = (L * t0, sy0 * a0, sz0 * a0)
                p1 = (L * t0, sy1 * a0, sz1 * a0)
                q0 = (L * t1, sy1 * a1, sz1 * a1)
                q1 = (L * t1, sy0 * a1, sz0 * a1)
                self.tube([p0, q0], chord * 0.34, seg=4)
                self.tube([p1, q1], chord * 0.34, seg=4)

    def spreader(self, L=12.6, W=2.7, H=1.1, z0=0.0):
        """Telescopic container spreader with twistlocks and rams."""
        for sx in (-1, 1):
            self.box(sx * L / 2 - 0.35, -W / 2, z0, sx * L / 2 + 0.35, W / 2, z0 + H)
            for sy in (-1, 1):
                x = sx * (L / 2 - 0.28)
                y = sy * (W / 2 - 0.28)
                self.box(x - 0.16, y - 0.16, z0 - 0.22, x + 0.16, y + 0.16, z0 + 0.10)
                self.box(x - 0.10, y - 0.10, z0 - 0.34, x + 0.10, y + 0.10, z0 - 0.20)
        for sy in (-1, 1):
            y = sy * (W / 2 - 0.18)
            self.box(-L / 2 + 0.4, y - 0.16, z0 + H * 0.30, L / 2 - 0.4, y + 0.16, z0 + H * 0.85)
            self.box(-L / 4, y - 0.22, z0 + H * 0.05, L / 4, y + 0.22, z0 + H * 0.30)
        self.box(-1.4, -1.1, z0 + H, 1.4, 1.1, z0 + H + 0.55)
        for sx in (-1, 1):
            for sy in (-1, 1):
                self.tube([(sx * 0.9, sy * 0.7, z0 + H + 0.55),
                           (sx * 1.5, sy * 1.1, z0 + H + 1.5)], 0.05, seg=5)
        for sy in (-1, 1):
            self.tube([(-1.3, sy * 0.9, z0 + H + 0.20), (1.3, sy * 0.9, z0 + H + 0.20)],
                      0.07, seg=6)

    def silo(self, r=1.6, h=6.0, z0=0.0, legs=1.6):
        for sx in (-1, 1):
            for sy in (-1, 1):
                self.box(sx * r * 0.6 - 0.10, sy * r * 0.6 - 0.10, z0,
                         sx * r * 0.6 + 0.10, sy * r * 0.6 + 0.10, z0 + legs)
        self.lathe([(r * 0.35, z0 + legs), (r, z0 + legs + 0.9), (r, z0 + legs + h * 0.55),
                    (r * 0.85, z0 + legs + h * 0.62)], 0, 0, seg=20)
        self.lathe([(r, z0 + legs + h * 0.55), (r, z0 + legs + h), (0.0, z0 + legs + h + 0.2)],
                   0, 0, seg=20)
        self.box(-0.22, -0.22, z0 + legs + h, 0.22, 0.22, z0 + legs + h + 1.0)


# ---------------------------------------------------------------- scene
def reset():
    sc = G.scene_reset()
    sc.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in \
        [i.identifier for i in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else sc.render.engine
    return sc


def scene(tag):
    """Fresh scene + module collection + root empty."""
    reset()
    col = G.collection("COL_" + tag)
    root = G.empty("BASE_" + tag, col)
    return col, root


def emit(mb, col, key, name, parent=None, smooth=False, uv=0.5):
    m = emat(key) if key in S.EMAT else mat(key)
    return mb.emit(col, m, name=name, smooth=smooth, uv_scale=uv, parent=parent)


def emit_em(mb, col, key, name, parent=None, smooth=False, uv=0.5):
    return mb.emit(col, emat(key), name=name, smooth=smooth, uv_scale=uv, parent=parent)


def bbox(objs):
    mn = [1e9] * 3
    mx = [-1e9] * 3
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            for i in range(3):
                mn[i] = min(mn[i], w[i])
                mx[i] = max(mx[i], w[i])
    return [round(v, 3) for v in mn + mx]


def finish(objs, out_blend, tag, extra=None, save=True):
    """Write stats JSON + .blend, print the HEADLESS receipt line."""
    bb = bbox(objs)
    tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objs)
    st = {
        "kit": S.VERSION, "module": tag,
        "objects": len(objs),
        "verts": sum(len(o.data.vertices) for o in objs),
        "tris": tris,
        "bbox": bb,
        "size": [round(bb[i + 3] - bb[i], 3) for i in range(3)],
        "object_list": [{"name": o.name, "tris": sum(len(p.vertices) - 2 for p in o.data.polygons),
                         "mat": o.data.materials[0].name if o.data.materials else None}
                        for o in objs],
    }
    if extra:
        st.update(extra)
    os.makedirs(os.path.dirname(out_blend), exist_ok=True)
    if save:
        G.save(out_blend)
    st["blend"] = out_blend
    side = os.path.splitext(out_blend)[0] + ".json"
    with open(side, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    print("HEADLESS " + json.dumps(st, ensure_ascii=False))
    return st


# ---------------------------------------------------------------- light / sky
def sky(sun_el=30.0, sun_az=315.0, energy=5.0, sky_strength=0.60,
        sky_col=(0.34, 0.42, 0.52), bounce=(0.72, 0.63, 0.50)):
    """Flat ambient world (predictable, no Nishita blow-out) + a low warm sun.

    A vertical gradient is faked by mixing the sky colour with a dusty ground
    bounce colour along the view Z, so the horizon is warm and the zenith cool.
    """
    w = bpy.data.worlds.new("M6-SKY")
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    out.location = (400, 0)
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.location = (200, 0)
    bg.inputs[1].default_value = sky_strength
    # gradient: texture coordinate -> separate Z -> ramp between bounce and sky
    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-820, 0)
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    sep.location = (-640, 0)
    # screen-space gradient: 0 = bottom of frame (dust haze), 1 = top (sky)
    nt.links.new(tc.outputs["Window"], sep.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.location = (-420, 0)
    ramp.color_ramp.elements[0].position = 0.10
    ramp.color_ramp.elements[0].color = (bounce[0], bounce[1], bounce[2], 1.0)
    ramp.color_ramp.elements[1].position = 0.95
    ramp.color_ramp.elements[1].color = (sky_col[0], sky_col[1], sky_col[2], 1.0)
    try:
        ramp.color_ramp.interpolation = "EASE"
    except Exception:
        pass
    nt.links.new(sep.outputs["Y"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    bpy.context.scene.world = w

    d = bpy.data.lights.new("SUN", type="SUN")
    d.energy = energy
    d.angle = math.radians(1.6)
    d.color = (1.0, 0.93, 0.84)
    o = bpy.data.objects.new("SUN", d)
    o.rotation_euler = (math.radians(90.0 - sun_el), 0.0, math.radians(sun_az))
    bpy.context.scene.collection.objects.link(o)
    return o


def ground(size=900.0, key="dust", z=-0.05):
    mb = MB("GRD")
    mb.box(-size / 2, -size / 2, z - 1.0, size / 2, size / 2, z)
    return mb.emit(bpy.context.scene.collection, mat(key), "GEO-ground")


def ground_mat():
    """Site ground: two noise octaves (patches + grain) + strong mottling."""
    key = "GROUND"
    if key in _MC:
        return _MC[key]
    m = bpy.data.materials.new("M6_ground")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (700, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (420, 0)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-900, 0)
    mp1 = nt.nodes.new("ShaderNodeMapping")
    mp1.location = (-720, 120)
    mp1.inputs["Scale"].default_value = (0.018, 0.018, 0.018)
    nt.links.new(tc.outputs["Object"], mp1.inputs["Vector"])
    n1 = nt.nodes.new("ShaderNodeTexNoise")
    n1.location = (-540, 120)
    n1.inputs["Scale"].default_value = 1.0
    n1.inputs["Detail"].default_value = 4.0
    nt.links.new(mp1.outputs["Vector"], n1.inputs["Vector"])
    mp2 = nt.nodes.new("ShaderNodeMapping")
    mp2.location = (-720, -180)
    mp2.inputs["Scale"].default_value = (0.55, 0.55, 0.55)
    nt.links.new(tc.outputs["Object"], mp2.inputs["Vector"])
    n2 = nt.nodes.new("ShaderNodeTexNoise")
    n2.location = (-540, -180)
    n2.inputs["Scale"].default_value = 1.0
    n2.inputs["Detail"].default_value = 8.0
    nt.links.new(mp2.outputs["Vector"], n2.inputs["Vector"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "FLOAT"
    mix.location = (-320, -20)
    mix.inputs["Factor"].default_value = 0.35
    nt.links.new(n1.outputs["Fac"], mix.inputs[2])
    nt.links.new(n2.outputs["Fac"], mix.inputs[3])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.location = (-120, 120)
    ramp.color_ramp.elements[0].color = G.hex_lin("#5a5245")
    ramp.color_ramp.elements[1].color = G.hex_lin("#8d8371")
    nt.links.new(mix.outputs[0], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.95
    bump = nt.nodes.new("ShaderNodeBump")
    bump.location = (160, -260)
    bump.inputs["Strength"].default_value = 0.25
    bump.inputs["Distance"].default_value = 0.08
    nt.links.new(n2.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    _MC[key] = m
    return m


def scatter_rocks(center_xy, r0=22.0, r1=170.0, rocks=240, bushes=140, seed=11):
    """Loose rock + dry shrub scatter; returns (rock_obj, bush_obj)."""
    rnd = random.Random(seed)
    mr = MB("SCAT-rock")
    for _ in range(rocks):
        a = rnd.uniform(0.0, TAU)
        d = rnd.uniform(r0, r1)
        x = center_xy[0] + math.cos(a) * d
        y = center_xy[1] + math.sin(a) * d
        r = rnd.uniform(0.10, 0.48) * (1.0 + d / 300.0)
        h = r * rnd.uniform(0.35, 0.75)
        mr.lathe([(r, 0.0), (r * 0.86, h * 0.5), (r * 0.42, h), (0.0, h * 1.08)],
                 x, y, seg=rnd.choice((5, 6, 7)))
    mb = MB("SCAT-bush")
    for _ in range(bushes):
        a = rnd.uniform(0.0, TAU)
        d = rnd.uniform(r0, r1)
        x = center_xy[0] + math.cos(a) * d
        y = center_xy[1] + math.sin(a) * d
        r = rnd.uniform(0.25, 0.75)
        h = r * rnd.uniform(0.5, 1.0)
        mb.lathe([(0.0, 0.0), (r * 0.7, h * 0.25), (r, h * 0.55), (0.0, h)],
                 x, y, seg=rnd.choice((6, 7)))
    coll = bpy.context.scene.collection
    ro = mr.emit(coll, mat("stone_scatter"), "GEO-shot-rocks")
    bo = mb.emit(coll, mat("grass_dry"), "GEO-shot-bushes")
    return ro, bo
