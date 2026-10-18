# -*- coding: utf-8 -*-
"""Procedural geometry toolkit for the Warsaw landmark set (Blender 5.2).

Everything is accumulated in plain python lists (no bpy.ops -> headless safe),
then emitted as one mesh object per material group.  Normals are recalculated
per closed shell with bmesh, and a box-projected UV map is written so the
meshes survive a round trip to Unreal with a usable texel density.

Usage:
    mb = MB("body")
    mb.box(0, 0, 0, 10, 10, 4)
    mb.lathe([(3, 0), (3, 4), (0, 5)], 5, 5, seg=24)   # spire
    emit(mb, coll, "stucco_ochre")
"""
import bpy
import bmesh
import math
from mathutils import Vector, Matrix

TAU = math.pi * 2.0


# ---------------------------------------------------------------- colour utils
def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_lin(h):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (srgb_to_linear(r), srgb_to_linear(g), srgb_to_linear(b), 1.0)


# ---------------------------------------------------------------- materials
_MATS = {}


def material(name, hexcol, rough=0.75, metal=0.0, pattern=None,
             hex2=None, scale=1.0, mortar=None):
    """Principled material with optional procedural pattern (render only).

    pattern: None | "plaster" | "tile" | "brick" | "stone" | "metal" | "concrete"
    """
    key = (name, hexcol, rough, metal, pattern, hex2, scale)
    if key in _MATS and _MATS[key].name in bpy.data.materials:
        return _MATS[key]
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (700, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (380, 0)
    col = hex_lin(hexcol)
    col2 = hex_lin(hex2) if hex2 else (col[0] * 0.72, col[1] * 0.72, col[2] * 0.72, 1.0)
    bsdf.inputs["Base Color"].default_value = col
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.35

    if pattern in ("tile", "brick", "stone", "plaster", "concrete"):
        tc = nt.nodes.new("ShaderNodeTexCoord")
        tc.location = (-700, 0)
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.location = (-520, 0)
        mp.inputs["Scale"].default_value = (scale, scale, scale)
        nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    if pattern == "tile":
        tex = nt.nodes.new("ShaderNodeTexWave")
        tex.location = (-300, 100)
        tex.wave_type = "BANDS"
        tex.bands_direction = "X"
        tex.inputs["Scale"].default_value = 7.0 * scale
        tex.inputs["Distortion"].default_value = 1.2
        tex.inputs["Detail"].default_value = 2.0
        nt.links.new(mp.outputs["Vector"], tex.inputs["Vector"])
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.location = (-60, 160)
        ramp.color_ramp.elements[0].color = col2
        ramp.color_ramp.elements[1].color = col
        nt.links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        bump = nt.nodes.new("ShaderNodeBump")
        bump.location = (120, -240)
        bump.inputs["Strength"].default_value = 0.45
        bump.inputs["Distance"].default_value = 0.08
        nt.links.new(tex.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    elif pattern == "brick":
        tex = nt.nodes.new("ShaderNodeTexBrick")
        tex.location = (-300, 100)
        tex.offset = 0.5
        tex.squash = 1.0
        tex.inputs["Scale"].default_value = 2.2 * scale
        tex.inputs["Mortar Size"].default_value = 0.012
        tex.inputs["Brick Width"].default_value = 0.22
        tex.inputs["Row Height"].default_value = 0.075
        tex.inputs["Color1"].default_value = col
        tex.inputs["Color2"].default_value = col2
        tex.inputs["Mortar"].default_value = hex_lin(mortar or "#b8b0a0")
        nt.links.new(mp.outputs["Vector"], tex.inputs["Vector"])
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        bump = nt.nodes.new("ShaderNodeBump")
        bump.location = (120, -240)
        bump.inputs["Strength"].default_value = 0.30
        bump.inputs["Distance"].default_value = 0.04
        nt.links.new(tex.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    elif pattern in ("stone", "concrete"):
        tex = nt.nodes.new("ShaderNodeTexVoronoi")
        tex.location = (-300, 100)
        tex.feature = "DISTANCE_TO_EDGE"
        tex.inputs["Scale"].default_value = 3.0 * scale
        nt.links.new(mp.outputs["Vector"], tex.inputs["Vector"])
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.location = (-60, 160)
        ramp.color_ramp.elements[0].position = 0.02
        ramp.color_ramp.elements[0].color = col2
        ramp.color_ramp.elements[1].position = 0.10
        ramp.color_ramp.elements[1].color = col
        nt.links.new(tex.outputs["Distance"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        bump = nt.nodes.new("ShaderNodeBump")
        bump.location = (120, -240)
        bump.inputs["Strength"].default_value = 0.35
        bump.inputs["Distance"].default_value = 0.04
        nt.links.new(tex.outputs["Distance"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    elif pattern == "plaster":
        tex = nt.nodes.new("ShaderNodeTexNoise")
        tex.location = (-300, -160)
        tex.inputs["Scale"].default_value = 5.0 * scale
        tex.inputs["Detail"].default_value = 8.0
        tex.inputs["Roughness"].default_value = 0.7
        nt.links.new(mp.outputs["Vector"], tex.inputs["Vector"])
        bump = nt.nodes.new("ShaderNodeBump")
        bump.location = (120, -240)
        bump.inputs["Strength"].default_value = 0.18
        bump.inputs["Distance"].default_value = 0.05
        nt.links.new(tex.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    else:
        # metal / plain: faint noise roughness break-up
        tex = nt.nodes.new("ShaderNodeTexNoise")
        tex.location = (-300, -160)
        tex.inputs["Scale"].default_value = 12.0 * scale
        tex.inputs["Detail"].default_value = 4.0
        bump = nt.nodes.new("ShaderNodeBump")
        bump.location = (120, -240)
        bump.inputs["Strength"].default_value = 0.08
        bump.inputs["Distance"].default_value = 0.03
        nt.links.new(tex.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    m.diffuse_color = col
    _MATS[key] = m
    return m


# ---------------------------------------------------------------- scene helpers
def scene_reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0
    return sc


def collection(name, parent=None):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
    holder = parent or bpy.context.scene.collection
    if c.name not in [x.name for x in holder.children]:
        holder.children.link(c)
    return c


def empty(name, coll, loc=(0, 0, 0)):
    o = bpy.data.objects.new(name, None)
    o.empty_display_type = "PLAIN_AXES"
    o.empty_display_size = 8.0
    o.location = loc
    coll.objects.link(o)
    return o


# ---------------------------------------------------------------- mesh builder
class MB(object):
    def __init__(self, name):
        self.name = name
        self.v = []
        self.f = []
        self.stack = [Matrix.Identity(4)]

    # -- transform stack --------------------------------------------------
    def push(self, m):
        self.stack.append(self.stack[-1] @ m)
        return self

    def pop(self):
        self.stack.pop()
        return self

    def at(self, x, y, z=0.0, rz=0.0):
        """Push a translation (and optional Z rotation) in degrees."""
        return self.push(Matrix.Translation((x, y, z)) @ Matrix.Rotation(math.radians(rz), 4, "Z"))

    def add(self, verts, faces):
        m = self.stack[-1]
        off = len(self.v)
        if m == Matrix.Identity(4):
            self.v.extend(tuple(p) for p in verts)
        else:
            self.v.extend(tuple(m @ Vector(p)) for p in verts)
        self.f.extend([[i + off for i in fc] for fc in faces])

    # -- primitives -------------------------------------------------------
    def box(self, x0, y0, z0, x1, y1, z1):
        x0, x1 = (x0, x1) if x0 <= x1 else (x1, x0)
        y0, y1 = (y0, y1) if y0 <= y1 else (y1, y0)
        z0, z1 = (z0, z1) if z0 <= z1 else (z1, z0)
        v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
        self.add(v, f)

    def boxc(self, cx, cy, cz, sx, sy, sz):
        self.box(cx - sx / 2, cy - sy / 2, cz - sz / 2,
                 cx + sx / 2, cy + sy / 2, cz + sz / 2)

    def prism_z(self, poly, z0, z1):
        n = len(poly)
        v = [(x, y, z0) for x, y in poly] + [(x, y, z1) for x, y in poly]
        f = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
        for i in range(n):
            j = (i + 1) % n
            f.append((i, j, n + j, n + i))
        self.add(v, f)

    def prism_y(self, poly_xz, y0, y1):
        n = len(poly_xz)
        v = [(x, y0, z) for x, z in poly_xz] + [(x, y1, z) for x, z in poly_xz]
        f = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
        for i in range(n):
            j = (i + 1) % n
            f.append((i, j, n + j, n + i))
        self.add(v, f)

    def prism_x(self, poly_yz, x0, x1):
        n = len(poly_yz)
        v = [(x0, y, z) for y, z in poly_yz] + [(x1, y, z) for y, z in poly_yz]
        f = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
        for i in range(n):
            j = (i + 1) % n
            f.append((i, j, n + j, n + i))
        self.add(v, f)

    def lathe(self, profile, cx=0.0, cy=0.0, seg=32, cap_bottom=True, cap_top=True):
        """profile: [(radius, z), ...] bottom -> top. radius 0 collapses to a pole."""
        rings = []
        for r, z in profile:
            if r <= 1e-6:
                rings.append([(cx, cy, z)])
            else:
                rings.append([(cx + math.cos(TAU * i / seg) * r,
                               cy + math.sin(TAU * i / seg) * r, z) for i in range(seg)])
        verts, faces = [], []
        idx = []
        for ring in rings:
            idx.append(list(range(len(verts), len(verts) + len(ring))))
            verts.extend(ring)
        for a, b in zip(idx[:-1], idx[1:]):
            if len(a) == 1 and len(b) == 1:
                continue
            if len(a) == 1:
                for i in range(len(b)):
                    faces.append((a[0], b[i], b[(i + 1) % len(b)]))
            elif len(b) == 1:
                for i in range(len(a)):
                    faces.append((b[0], a[(i + 1) % len(a)], a[i]))
            else:
                for i in range(len(a)):
                    j = (i + 1) % len(a)
                    faces.append((a[i], a[j], b[j], b[i]))
        if cap_bottom and len(idx[0]) > 1:
            faces.append(tuple(reversed(idx[0])))
        if cap_top and len(idx[-1]) > 1:
            faces.append(tuple(idx[-1]))
        self.add(verts, faces)

    def cyl(self, cx, cy, z0, z1, r, seg=24, r_top=None):
        r_top = r if r_top is None else r_top
        self.lathe([(r, z0), (r_top, z1)], cx, cy, seg)

    def dome(self, cx, cy, z0, R, H, seg=32, rings=8, squash=1.0):
        prof = []
        for i in range(rings + 1):
            t = (math.pi / 2) * i / rings
            prof.append((R * math.cos(t), z0 + H * math.sin(t) ** squash))
        self.lathe(prof, cx, cy, seg, cap_bottom=True, cap_top=False)

    def onion(self, cx, cy, z0, R, H, seg=32):
        """Baroque onion/helmet dome."""
        pts = [(R, z0), (R * 1.05, z0 + H * 0.18), (R * 0.92, z0 + H * 0.38),
               (R * 0.62, z0 + H * 0.58), (R * 0.30, z0 + H * 0.78),
               (R * 0.12, z0 + H * 0.90), (0.0, z0 + H)]
        self.lathe(pts, cx, cy, seg, cap_bottom=True, cap_top=False)

    def gable_y(self, x0, x1, y0, y1, z0, h):
        """Ridge along Y, gable faces at +/-Y."""
        xc = (x0 + x1) / 2.0
        self.prism_y([(x0, z0), (x1, z0), (xc, z0 + h)], y0, y1)

    def gable_x(self, x0, x1, y0, y1, z0, h):
        """Ridge along X, gable faces at +/-X."""
        yc = (y0 + y1) / 2.0
        self.prism_x([(y0, z0), (y1, z0), (yc, z0 + h)], x0, x1)

    def hip(self, x0, y0, x1, y1, z0, h, ridge_axis="y"):
        w = abs(x1 - x0)
        d = abs(y1 - y0)
        if ridge_axis == "y":
            inset = min(d / 2.0, w / 2.0)
            ry0, ry1 = y0 + inset, y1 - inset
            xc = (x0 + x1) / 2.0
            v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                 (xc, ry0, z0 + h), (xc, ry1, z0 + h)]
            if ry1 - ry0 < 1e-3:
                f = [(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4), (0, 3, 2, 1)]
                self.add(v[:5], f)
            else:
                f = [(0, 1, 4), (1, 2, 5, 4), (2, 3, 5), (3, 0, 4, 5), (0, 3, 2, 1)]
                self.add(v, f)
        else:
            inset = min(w / 2.0, d / 2.0)
            rx0, rx1 = x0 + inset, x1 - inset
            yc = (y0 + y1) / 2.0
            v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                 (rx0, yc, z0 + h), (rx1, yc, z0 + h)]
            if rx1 - rx0 < 1e-3:
                f = [(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4), (0, 3, 2, 1)]
                self.add(v[:5], f)
            else:
                f = [(0, 1, 5, 4), (1, 2, 5), (2, 3, 4, 5), (3, 0, 4), (0, 3, 2, 1)]
                self.add(v, f)

    def mansard(self, x0, y0, x1, y1, z0, h1, inset, h2, ridge_axis="x"):
        """Polish broken roof: steep lower hip to a rect, then a flat upper hip."""
        xm0, xm1 = x0 + inset, x1 - inset
        ym0, ym1 = y0 + inset, y1 - inset
        v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (xm0, ym0, z0 + h1), (xm1, ym0, z0 + h1),
             (xm1, ym1, z0 + h1), (xm0, ym1, z0 + h1)]
        f = [(0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7),
             (0, 3, 2, 1)]
        top = z0 + h1 + h2
        if ridge_axis == "x":
            d = (ym1 - ym0) / 2.0
            r0 = (xm0 + d, (ym0 + ym1) / 2.0, top)
            r1 = (xm1 - d, (ym0 + ym1) / 2.0, top)
            v += [r0, r1]
            R0, R1 = 8, 9
            f += [(4, 5, R1, R0), (5, 6, R1), (6, 7, R0, R1), (7, 4, R0)]
        else:
            d = (xm1 - xm0) / 2.0
            r0 = ((xm0 + xm1) / 2.0, ym0 + d, top)
            r1 = ((xm0 + xm1) / 2.0, ym1 - d, top)
            v += [r0, r1]
            R0, R1 = 8, 9
            f += [(4, 5, R0, R1), (5, 6, R1), (6, 7, R1, R0), (7, 4, R0)]
        self.add(v, f)

    def pyramid(self, x0, y0, x1, y1, z0, z1, cx=None, cy=None):
        cx = (x0 + x1) / 2.0 if cx is None else cx
        cy = (y0 + y1) / 2.0 if cy is None else cy
        v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (cx, cy, z1)]
        f = [(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4), (0, 3, 2, 1)]
        self.add(v, f)

    def wall_between(self, p0, p1, z0, z1, thick):
        """Axis-independent wall slab from p0 to p1 (centre line)."""
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        L = math.hypot(dx, dy)
        if L < 1e-6:
            return
        ang = math.degrees(math.atan2(dy, dx))
        self.push(Matrix.Translation((p0[0], p0[1], 0)) @ Matrix.Rotation(math.radians(ang), 4, "Z"))
        self.box(-thick / 2, -thick / 2, z0, L + thick / 2, thick / 2, z1)
        self.pop()

    def tube(self, pts, r, seg=6, r_end=None):
        """Polyline tube (cables, railings, spokes)."""
        r_end = r if r_end is None else r_end
        rings = []
        n = len(pts)
        for i, p in enumerate(pts):
            if i == 0:
                d = Vector(pts[1]) - Vector(pts[0])
            elif i == n - 1:
                d = Vector(pts[-1]) - Vector(pts[-2])
            else:
                d = Vector(pts[i + 1]) - Vector(pts[i - 1])
            d.normalize()
            up = Vector((0, 0, 1))
            if abs(d.dot(up)) > 0.99:
                up = Vector((1, 0, 0))
            a = d.cross(up).normalized()
            b = d.cross(a).normalized()
            rr = r + (r_end - r) * (i / max(1, n - 1))
            ring = [Vector(p) + a * (math.cos(TAU * k / seg) * rr) + b * (math.sin(TAU * k / seg) * rr)
                    for k in range(seg)]
            rings.append(ring)
        verts = [tuple(v) for ring in rings for v in ring]
        faces = []
        for i in range(n - 1):
            for k in range(seg):
                k2 = (k + 1) % seg
                faces.append((i * seg + k, i * seg + k2, (i + 1) * seg + k2, (i + 1) * seg + k))
        faces.append(tuple(range(seg - 1, -1, -1)))
        faces.append(tuple((n - 1) * seg + k for k in range(seg)))
        self.add(verts, faces)

    def ribbon(self, row_a, row_b):
        """Quad strip between two equal-length point rows."""
        n = len(row_a)
        v = list(row_a) + list(row_b)
        f = []
        for i in range(n - 1):
            f.append((i, i + 1, n + i + 1, n + i))
        self.add(v, f)

    def grid(self, fn, nu, nv, close_u=False):
        """Parametric surface: fn(u,v) -> (x,y,z), u,v in [0,1]."""
        verts = []
        for i in range(nu + (0 if close_u else 1)):
            for j in range(nv + 1):
                verts.append(fn(i / float(nu), j / float(nv)))
        W = nv + 1
        faces = []
        cols = nu if close_u else nu
        for i in range(cols):
            i2 = (i + 1) % nu if close_u else i + 1
            for j in range(nv):
                a = i * W + j
                b = i2 * W + j
                faces.append((a, b, b + 1, a + 1))
        self.add(verts, faces)

    # -- architectural details --------------------------------------------
    def window_glass(self, w, h, y0=-0.04, y1=0.07):
        """Dark glazing panel standing just in front of the wall plane."""
        self.box(-w / 2 + 0.02, y0, 0.02, w / 2 - 0.02, y1, h - 0.02)

    def window_frame(self, w, h, frame=0.085, sill=True, proud=0.13):
        """Stone surround + sill, standing proud of the wall plane."""
        fy0, fy1 = -proud, -0.01
        self.box(-w / 2 - frame, fy0, -frame, -w / 2, fy1, h + frame)
        self.box(w / 2, fy0, -frame, w / 2 + frame, fy1, h + frame)
        self.box(-w / 2 - frame, fy0, h, w / 2 + frame, fy1, h + frame)
        self.box(-w / 2, fy0, h * 0.66, w / 2, fy1, h * 0.66 + 0.055)
        if sill:
            self.box(-w / 2 - frame - 0.07, -proud - 0.09, -frame - 0.07,
                     w / 2 + frame + 0.07, fy1, -frame)
        else:
            self.box(-w / 2 - frame, fy0, -frame, w / 2 + frame, fy1, 0.0)

    def window(self, w, h, frame=0.085, sill=True, proud=0.13):
        self.window_glass(w, h)
        self.window_frame(w, h, frame, sill, proud)

    def arch_open(self, w, h, seg=9, y0=-0.06, y1=-0.004):
        """Dark opening (rectangle + semicircle) standing just in front of the wall."""
        r = w / 2.0
        poly = [(-r, 0.0)]
        for i in range(seg, -1, -1):
            a = math.pi * i / seg
            poly.append((math.cos(a) * r, h + math.sin(a) * r))
        poly.append((r, 0.0))
        self.prism_y(poly, y0, y1)

    def arch_ring(self, w, h, seg=9, band=0.13, proud=0.16):
        """Voussoir ring + flanking piers around an arch opening."""
        r = w / 2.0
        for i in range(seg):
            a0 = math.pi * i / seg
            a1 = math.pi * (i + 1) / seg
            am = (a0 + a1) / 2.0
            px = math.cos(am) * (r + band / 2)
            pz = h + math.sin(am) * (r + band / 2)
            L = (r + band) * math.pi / seg * 1.10
            self.push(Matrix.Translation((px, 0.0, pz)) @
                      Matrix.Rotation(am - math.pi / 2, 4, "Y"))
            self.box(-L / 2, -proud, -band / 2, L / 2, 0.0, band / 2)
            self.pop()
        for s in (-1, 1):
            self.box(s * r - 0.06, -proud, -0.02, s * (r + band), 0.0, h + 0.02)

    def coping_xz(self, profile, y0, y1, width=0.22, skip_last=True):
        """Stone coping band following a closed XZ profile (gable edges)."""
        n = len(profile)
        last = n - 1 if skip_last else n
        for i in range(last):
            x0, z0 = profile[i]
            x1, z1 = profile[(i + 1) % n]
            dx, dz = x1 - x0, z1 - z0
            L = math.hypot(dx, dz)
            if L < 1e-6:
                continue
            ang = math.atan2(-dz, dx)
            self.push(Matrix.Translation((x0, y0, z0)) @ Matrix.Rotation(ang, 4, "Y"))
            self.box(0, 0.0, -width / 2, L, y1 - y0, width / 2)
            self.pop()

    def balustrade(self, x0, y0, x1, y1, z, h=0.95, spacing=0.55):
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy)
        if L < 1e-6:
            return
        ang = math.degrees(math.atan2(dy, dx))
        self.push(Matrix.Translation((x0, y0, z)) @ Matrix.Rotation(math.radians(ang), 4, "Z"))
        self.box(0, -0.14, 0.0, L, 0.14, 0.14)          # plinth
        self.box(0, -0.20, h - 0.16, L, 0.20, h)         # handrail
        n = max(2, int(L / spacing))
        for i in range(n + 1):
            x = i * L / n
            self.lathe([(0.085, 0.10), (0.055, 0.22), (0.10, 0.42),
                        (0.045, 0.62), (0.075, h - 0.20)], x, 0.0, seg=8)
        self.pop()

    def crenels(self, x0, y0, x1, y1, z, h, merlon=1.2, gap=0.9, t=0.6):
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy)
        ang = math.degrees(math.atan2(dy, dx))
        self.push(Matrix.Translation((x0, y0, z)) @ Matrix.Rotation(math.radians(ang), 4, "Z"))
        n = max(1, int((L + gap) / (merlon + gap)))
        step = L / n
        for i in range(n):
            self.box(i * step, -t / 2, 0, i * step + merlon, t / 2, h)
        self.pop()

    def stairs(self, x0, y0, x1, y1, z0, steps, rise):
        for i in range(steps):
            z = z0 + i * rise
            self.box(x0, y0 + i * (y1 - y0) / steps, z, x1, y0 + (i + 1) * (y1 - y0) / steps, z + rise)

    # -- emit -------------------------------------------------------------
    def emit(self, coll, mat, name=None, smooth=False, uv_scale=0.5, parent=None):
        n = len(self.v)
        faces, dropped = [], 0
        for fc in self.f:
            if len(set(fc)) != len(fc) or any(i < 0 or i >= n for i in fc):
                dropped += 1
                continue
            faces.append(fc)
        self.dropped_faces = dropped
        me = bpy.data.meshes.new(name or self.name)
        me.from_pydata(self.v, [], faces)
        me.validate(verbose=False, clean_customdata=False)
        me.update()
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()
        me.update()
        # box projected UVs
        uv = me.uv_layers.new(name="UVMap")
        data = uv.data
        for poly in me.polygons:
            n = poly.normal
            ax = 0 if abs(n.x) >= abs(n.y) and abs(n.x) >= abs(n.z) else (1 if abs(n.y) >= abs(n.z) else 2)
            for li in poly.loop_indices:
                co = me.vertices[me.loops[li].vertex_index].co
                if ax == 0:
                    u, w = co.y, co.z
                elif ax == 1:
                    u, w = co.x, co.z
                else:
                    u, w = co.x, co.y
                data[li].uv = (u * uv_scale, w * uv_scale)
        if smooth:
            for p in me.polygons:
                p.use_smooth = True
        me.materials.append(mat)
        ob = bpy.data.objects.new(name or self.name, me)
        coll.objects.link(ob)
        if parent:
            ob.parent = parent
        return ob


# ---------------------------------------------------------------- render rig
def setup_world(strength=0.55, sky=(0.55, 0.66, 0.78)):
    w = bpy.data.worlds.new("WARSAW-WORLD")
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes["Background"]
    bg.inputs[0].default_value = (sky[0], sky[1], sky[2], 1.0)
    bg.inputs[1].default_value = strength
    bpy.context.scene.world = w
    return w


def sun(rot=(0.86, 0.12, 0.62), energy=3.4, angle=0.06):
    d = bpy.data.lights.new("SUN", type="SUN")
    d.energy = energy
    d.angle = angle
    o = bpy.data.objects.new("SUN", d)
    o.rotation_euler = rot
    bpy.context.scene.collection.objects.link(o)
    return o


def ground(name, size, mat, z=0.0):
    mb = MB(name)
    mb.box(-size / 2, -size / 2, z - 0.4, size / 2, size / 2, z)
    return mb.emit(bpy.context.scene.collection, mat, name)


def save(path):
    bpy.ops.wm.save_as_mainfile(filepath=path)
    return path
