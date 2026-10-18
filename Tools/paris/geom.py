"""Pure-Python mesh builder (no `unreal` import, testable with plain CPython).

Coordinates are METRES in a right-handed local frame (x, y, z-up). Geometry is collected per material
slot as flat-shaded polygons (each face owns its vertices, normals are exact face normals). Winding is
fixed automatically from the intended normal, so callers only state which way a face looks.

UV0 convention (shared with the Paris materials): metres, u along the surface (horizontal tangent),
v = -height on walls; horizontal faces use (x, -y). Vertex colour: R/G = per-building random values
(tint / palette), A = 1 - soot, B unused (1).
"""
import math
import random

Z = (0.0, 0.0, 1.0)


# ---------------------------------------------------------------- vector helpers
def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def length(a):
    return math.sqrt(dot(a, a))


def norm(a):
    ln = length(a)
    return (a[0] / ln, a[1] / ln, a[2] / ln) if ln > 1e-12 else (0.0, 0.0, 1.0)


def rotate_around_axis(v, axis, angle):
    """Rotate vector v around axis by angle (radians) using Rodrigues' rotation formula."""
    k = norm(axis)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    # v_rot = v*cos(a) + (k × v)*sin(a) + k*(k·v)*(1-cos(a))
    k_dot_v = dot(k, v)
    k_cross_v = cross(k, v)
    return (
        v[0] * cos_a + k_cross_v[0] * sin_a + k[0] * k_dot_v * (1 - cos_a),
        v[1] * cos_a + k_cross_v[1] * sin_a + k[1] * k_dot_v * (1 - cos_a),
        v[2] * cos_a + k_cross_v[2] * sin_a + k[2] * k_dot_v * (1 - cos_a)
    )


def newell(pts):
    nx = ny = nz = 0.0
    k = len(pts)
    for i in range(k):
        x0, y0, z0 = pts[i]
        x1, y1, z1 = pts[(i + 1) % k]
        nx += (y0 - y1) * (z0 + z1)
        ny += (z0 - z1) * (x0 + x1)
        nz += (x0 - x1) * (y0 + y1)
    return norm((nx, ny, nz))


def auto_uv(p, n):
    if abs(n[2]) > 0.95:
        return (p[0], -p[1])
    t = norm((-n[1], n[0], 0.0))
    b = cross(n, t)
    return (dot(p, t), -dot(p, b))


# ---------------------------------------------------------------- 2D helpers
def seg_normal(p, q):
    """Outward normal of edge p->q of a CCW polygon."""
    dx, dy = q[0] - p[0], q[1] - p[1]
    ln = math.hypot(dx, dy)
    return (dy / ln, -dx / ln)


def offset_polyline(pts, d, closed):
    """Mitred offset of a 2D polyline/polygon by d (positive = outward for CCW polygons)."""
    k = len(pts)
    out = []
    for i in range(k):
        prev_n = seg_normal(pts[i - 1], pts[i]) if (closed or i > 0) else None
        next_n = seg_normal(pts[i], pts[(i + 1) % k]) if (closed or i < k - 1) else None
        if prev_n is None:
            m = next_n
        elif next_n is None:
            m = prev_n
        else:
            s = 1.0 + prev_n[0] * next_n[0] + prev_n[1] * next_n[1]
            m = ((prev_n[0] + next_n[0]) / s, (prev_n[1] + next_n[1]) / s)
        out.append((pts[i][0] + m[0] * d, pts[i][1] + m[1] * d))
    return out


def inset_polygon(pts, dists):
    """Move every edge i (pts[i] -> pts[i+1]) of a CCW polygon inward by dists[i]; vertex i of the result
    is the intersection of the moved edges i-1 and i (per-edge mansard / setback insets)."""
    k = len(pts)
    lines = []
    for i in range(k):
        p, q = pts[i], pts[(i + 1) % k]
        n = seg_normal(p, q)
        d = dists[i]
        lines.append(((p[0] - n[0] * d, p[1] - n[1] * d), (q[0] - p[0], q[1] - p[1])))
    out = []
    for i in range(k):
        (p1, d1), (p2, d2) = lines[i - 1], lines[i]
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) < 1e-9:
            out.append(p2)
        else:
            t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / den
            out.append((p1[0] + d1[0] * t, p1[1] + d1[1] * t))
    return out


def poly_area(pts):
    a = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        a += x0 * y1 - x1 * y0
    return a * 0.5


def earclip(pts):
    """Triangulate a simple 2D polygon (any winding). Returns index triples in CCW order."""
    idx = list(range(len(pts)))
    if poly_area(pts) < 0:
        idx.reverse()
    tris = []

    def is_convex(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) > 1e-12

    def inside(p, a, b, c):
        d1 = (p[0] - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (p[1] - b[1])
        d2 = (p[0] - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (p[1] - c[1])
        d3 = (p[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (p[1] - a[1])
        neg = d1 < -1e-12 or d2 < -1e-12 or d3 < -1e-12
        pos = d1 > 1e-12 or d2 > 1e-12 or d3 > 1e-12
        return not (neg and pos)

    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        k = len(idx)
        for i in range(k):
            ia, ib, ic = idx[i - 1], idx[i], idx[(i + 1) % k]
            a, b, c = pts[ia], pts[ib], pts[ic]
            if not is_convex(a, b, c):
                continue
            if any(inside(pts[j], a, b, c) for j in idx if j not in (ia, ib, ic)):
                continue
            tris.append((ia, ib, ic))
            idx.pop(i)
            break
        else:
            break  # degenerate, give up on the rest
    if len(idx) == 3:
        tris.append(tuple(idx))
    return tris


# ---------------------------------------------------------------- frames
class Frame:
    """Facade frame: a along the edge (t), b outward (n), z up. Built from a CCW polygon edge."""

    def __init__(self, p, q, z0=0.0):
        dx, dy = q[0] - p[0], q[1] - p[1]
        self.length = math.hypot(dx, dy)
        self.t = (dx / self.length, dy / self.length, 0.0)
        self.n = (self.t[1], -self.t[0], 0.0)
        self.o = (p[0], p[1], z0)

    def at(self, a, b, z):
        t, n, o = self.t, self.n, self.o
        return (o[0] + t[0] * a + n[0] * b, o[1] + t[1] * a + n[1] * b, o[2] + z)

    def vec(self, a, b, z):
        t, n = self.t, self.n
        return (t[0] * a + n[0] * b, t[1] * a + n[1] * b, z)


# ---------------------------------------------------------------- builder
class MeshBuilder:
    def __init__(self, slots):
        self.slots = list(slots)
        self.data = {s: {"p": [], "n": [], "uv": [], "c": [], "t": []} for s in self.slots}
        self.color = (1.0, 1.0, 1.0, 1.0)
        self.color_fn = None  # optional f(point, base_color) -> colour, e.g. height-dependent soot

    # -------------------------------------------------- primitives
    def poly(self, slot, pts, n=None, uvs=None):
        """Planar convex polygon; `n` = intended facing (winding fixed automatically)."""
        if len(pts) < 3:
            return
        nn = newell(pts)
        if n is None:
            n = nn
        else:
            n = norm(n)
            if dot(nn, n) < 0:
                pts = pts[::-1]
                if uvs is not None:
                    uvs = uvs[::-1]
        if uvs is None:
            uvs = [auto_uv(p, n) for p in pts]
        d = self.data[slot]
        base = len(d["p"])
        c = self.color
        cf = self.color_fn
        for p, uv in zip(pts, uvs):
            d["p"].append(p)
            d["n"].append(n)
            d["uv"].append(uv)
            d["c"].append(cf(p, c) if cf else c)
        for i in range(1, len(pts) - 1):
            d["t"].append((base, base + i, base + i + 1))

    def polygon2d(self, slot, pts2d, z, up=True):
        """Concave-safe horizontal polygon at height z (ear clipping)."""
        tris = earclip(pts2d)
        n = Z if up else (0.0, 0.0, -1.0)
        for ia, ib, ic in tris:
            self.poly(slot, [(pts2d[i][0], pts2d[i][1], z) for i in (ia, ib, ic)], n)

    def fquad(self, slot, fr, a0, a1, z0, z1, b, facing=1.0, uvs=None):
        """Quad in the facade plane b (facing +n if facing>0 else -n)."""
        pts = [fr.at(a0, b, z0), fr.at(a1, b, z0), fr.at(a1, b, z1), fr.at(a0, b, z1)]
        self.poly(slot, pts, mul(fr.n, facing), uvs)

    def fbox(self, slot, fr, a0, a1, b0, b1, z0, z1, skip=()):
        """Box aligned to a facade frame. skip: subset of front/back/left/right/top/bottom."""
        P = fr.at
        if "front" not in skip:
            self.poly(slot, [P(a0, b1, z0), P(a1, b1, z0), P(a1, b1, z1), P(a0, b1, z1)], fr.n)
        if "back" not in skip:
            self.poly(slot, [P(a0, b0, z0), P(a1, b0, z0), P(a1, b0, z1), P(a0, b0, z1)], mul(fr.n, -1))
        if "right" not in skip:
            self.poly(slot, [P(a1, b0, z0), P(a1, b1, z0), P(a1, b1, z1), P(a1, b0, z1)], fr.t)
        if "left" not in skip:
            self.poly(slot, [P(a0, b0, z0), P(a0, b1, z0), P(a0, b1, z1), P(a0, b0, z1)], mul(fr.t, -1))
        if "top" not in skip:
            self.poly(slot, [P(a0, b0, z1), P(a1, b0, z1), P(a1, b1, z1), P(a0, b1, z1)], Z)
        if "bottom" not in skip:
            self.poly(slot, [P(a0, b0, z0), P(a1, b0, z0), P(a1, b1, z0), P(a0, b1, z0)], (0, 0, -1))

    def obox(self, slot, c, ax, ay, az, hx, hy, hz, skip=()):
        """Oriented box: centre c, unit axes ax/ay/az, half sizes."""
        def P(sx, sy, sz):
            return add(add(add(c, mul(ax, sx * hx)), mul(ay, sy * hy)), mul(az, sz * hz))
        faces = {
            "px": ([P(1, -1, -1), P(1, 1, -1), P(1, 1, 1), P(1, -1, 1)], ax),
            "nx": ([P(-1, -1, -1), P(-1, 1, -1), P(-1, 1, 1), P(-1, -1, 1)], mul(ax, -1)),
            "py": ([P(-1, 1, -1), P(1, 1, -1), P(1, 1, 1), P(-1, 1, 1)], ay),
            "ny": ([P(-1, -1, -1), P(1, -1, -1), P(1, -1, 1), P(-1, -1, 1)], mul(ay, -1)),
            "pz": ([P(-1, -1, 1), P(1, -1, 1), P(1, 1, 1), P(-1, 1, 1)], az),
            "nz": ([P(-1, -1, -1), P(1, -1, -1), P(1, 1, -1), P(-1, 1, -1)], mul(az, -1)),
        }
        for k, (pts, n) in faces.items():
            if k not in skip:
                self.poly(slot, pts, n)

    def box(self, slot, x0, x1, y0, y1, z0, z1, skip=()):
        self.obox(slot, ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), (1, 0, 0), (0, 1, 0), (0, 0, 1),
                  (x1 - x0) / 2, (y1 - y0) / 2, (z1 - z0) / 2, skip)

    def band(self, slot, pts2d, closed, d0, d1, z0, z1, bottom=True, ends=True):
        """Horizontal moulding along a polyline: outer face at offset d1, top/bottom between d0..d1."""
        inner = offset_polyline(pts2d, d0, closed)
        outer = offset_polyline(pts2d, d1, closed)
        k = len(pts2d)
        segs = range(k) if closed else range(k - 1)
        for i in segs:
            j = (i + 1) % k
            ni = seg_normal(pts2d[i], pts2d[j])
            n3 = (ni[0], ni[1], 0.0)
            oi, oj, ii, ij = outer[i], outer[j], inner[i], inner[j]
            self.poly(slot, [(oi[0], oi[1], z0), (oj[0], oj[1], z0), (oj[0], oj[1], z1), (oi[0], oi[1], z1)], n3)
            self.poly(slot, [(ii[0], ii[1], z1), (ij[0], ij[1], z1), (oj[0], oj[1], z1), (oi[0], oi[1], z1)], Z)
            if bottom:
                self.poly(slot, [(ii[0], ii[1], z0), (ij[0], ij[1], z0), (oj[0], oj[1], z0), (oi[0], oi[1], z0)], (0, 0, -1))
        if not closed and ends:
            for i, nb in ((0, 1), (k - 1, k - 2)):
                d = norm((pts2d[i][0] - pts2d[nb][0], pts2d[i][1] - pts2d[nb][1], 0.0))
                a, b = inner[i], outer[i]
                self.poly(slot, [(a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z1), (a[0], a[1], z1)], d)

    def strip(self, slot, pts2d, closed, d, z0, z1, ends=True):
        """Vertical quads along a polyline offset by d (railings): u = metres along, v = 0 top .. 1 bottom."""
        o = offset_polyline(pts2d, d, closed)
        k = len(pts2d)
        segs = list(range(k)) if closed else list(range(k - 1))
        u = 0.0
        for i in segs:
            j = (i + 1) % k
            ni = seg_normal(pts2d[i], pts2d[j])
            a, b = o[i], o[j]
            ln = math.hypot(b[0] - a[0], b[1] - a[1])
            self.poly(slot, [(a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z1), (a[0], a[1], z1)], (ni[0], ni[1], 0.0),
                      uvs=[(u, 1.0), (u + ln, 1.0), (u + ln, 0.0), (u, 0.0)])
            u += ln
        if not closed and ends:
            for i, nb in ((0, 1), (k - 1, k - 2)):
                dn = norm((pts2d[i][0] - pts2d[nb][0], pts2d[i][1] - pts2d[nb][1], 0.0))
                a, b = pts2d[i], o[i]
                ln = math.hypot(b[0] - a[0], b[1] - a[1])
                self.poly(slot, [(a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z1), (a[0], a[1], z1)], dn,
                          uvs=[(0.0, 1.0), (ln, 1.0), (ln, 0.0), (0.0, 0.0)])

    def extrude_profile(self, slot, fr, prof, b0, b1, caps=True):
        """Extrude a 2D profile given in the frame's (a, z) plane from b0 to b1 (e.g. bridge elevations)."""
        k = len(prof)
        if poly_area(prof) < 0:
            prof = prof[::-1]
        for i in range(k):
            a0, z0 = prof[i]
            a1, z1 = prof[(i + 1) % k]
            # profile is CCW in (a, z): outward normal in (a, z) is (dz, -da)
            da, dz = a1 - a0, z1 - z0
            ln = math.hypot(da, dz)
            if ln < 1e-9:
                continue
            n = norm(add(mul(fr.t, dz / ln), (0.0, 0.0, -da / ln)))
            self.poly(slot, [fr.at(a0, b0, z0), fr.at(a1, b0, z1), fr.at(a1, b1, z1), fr.at(a0, b1, z0)], n)
        if caps:
            for bb, s in ((b1, 1.0), (b0, -1.0)):
                for ia, ib, ic in earclip(prof):
                    self.poly(slot, [fr.at(prof[i][0], bb, prof[i][1]) for i in (ia, ib, ic)], mul(fr.n, s))

    def heightfield(self, slot, x0, y0, sx, sy, nx, ny, hfun):
        """Grid patch with z = hfun(x, y); faces are split quads with face normals."""
        hs = [[hfun(x0 + sx * i / nx, y0 + sy * j / ny) for i in range(nx + 1)] for j in range(ny + 1)]
        for j in range(ny):
            for i in range(nx):
                xa, xb = x0 + sx * i / nx, x0 + sx * (i + 1) / nx
                ya, yb = y0 + sy * j / ny, y0 + sy * (j + 1) / ny
                p00 = (xa, ya, hs[j][i])
                p10 = (xb, ya, hs[j][i + 1])
                p11 = (xb, yb, hs[j + 1][i + 1])
                p01 = (xa, yb, hs[j + 1][i])
                self.poly(slot, [p00, p10, p11], Z)
                self.poly(slot, [p00, p11, p01], Z)

    # -------------------------------------------------- stats
    def tri_count(self):
        return sum(len(d["t"]) for d in self.data.values())

    def vert_count(self):
        return sum(len(d["p"]) for d in self.data.values())

    def used_slots(self):
        return [s for s in self.slots if self.data[s]["t"]]

    def bounds(self):
        xs, ys, zs = [], [], []
        for d in self.data.values():
            for p in d["p"]:
                xs.append(p[0])
                ys.append(p[1])
                zs.append(p[2])
        return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def rect_minus_rects(a0, a1, z0, z1, holes):
    """Decompose the wall rectangle [a0,a1]x[z0,z1] minus axis-aligned holes into rectangles."""
    zs = {z0, z1}
    for h in holes:
        zs.add(max(z0, min(z1, h[2])))
        zs.add(max(z0, min(z1, h[3])))
    zs = sorted(zs)
    out = []
    for zi in range(len(zs) - 1):
        za, zb = zs[zi], zs[zi + 1]
        if zb - za < 1e-6:
            continue
        zm = (za + zb) / 2
        cuts = sorted((h[0], h[1]) for h in holes if h[2] < zm < h[3])
        x = a0
        for c0, c1 in cuts:
            if c0 > x + 1e-6:
                out.append((x, min(c0, a1), za, zb))
            x = max(x, c1)
        if a1 > x + 1e-6:
            out.append((x, a1, za, zb))
    return out


def rng(seed):
    return random.Random(seed)
