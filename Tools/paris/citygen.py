"""City-level procedural meshes for the Paris board (pure Python on geom.MeshBuilder, no `unreal` import).

Cell-local frame (metres): one 200 m cell centred on the origin; roads run along the cell border (half of the
22 m carriageway belongs to each cell), 8 m sidewalks with 0.15 m granite kerbs and rounded corners, building
facades at +-81 m, courtyard +-65 m with the board "pad" (stone-bordered checker tile) in its centre.
Layers are stacked a few cm apart instead of cut out of each other (road 0, sidewalk 0.15, courtyard 0.18,
pad 0.2) - the steps are hidden by the buildings.

Meshes:
    ground_cell(kind)         board / background cell ground (kind: light | dark | garden | court | base | scorched)
    plaza(), champ_de_mars()  open cells (2x2 plaza with obelisk / park strip under the Eiffel Tower)
    cathedral_close(n)        paved 1 x n cell close under Notre-Dame (B2), same strip layout as champ_de_mars
    board_lines()             glowing inlaid grid on the street centre lines of the 8x8 board
    seine_segment(bridge)     200 m of river cell: quay road, promenade, parapet, quay walls, lower quays,
                              water, river bed; bridge=True adds a three-arch stone bridge on the centre line
    tree(seed), lamp(), obelisk(), car(seed, burnt), barge(seed)
"""
import math

import geom
from geom import Frame, MeshBuilder, Z, norm, rng

HALF = 100.0
ROAD_HALF = 11.0
KERB = HALF - ROAD_HALF  # 89
FACADE = 81.0
COURT = 65.0
KERB_H = 0.15
CORNER_R = 5.0
PAD0, PAD1 = 45.0, 48.5  # pad border ring (inner, outer half size)
LINE_W = 2.4  # board line width (reads at ~1.2 m/px from the gameplay camera)
BORDER_W = 4.0

SLOT_MATERIALS = {
    "road": "MI_Ground_Asphalt", "kerb": "MI_Stone_Grey", "walk": "MI_Ground_Sidewalk", "court": "MI_Ground_Cobble",
    "pad": "MI_Ground_Plaza", "light": "MI_Ground_PadLight", "dark": "MI_Ground_PadDark", "marking": "MI_Paint_Marking",
    "line": "MI_Board_Line", "grass": "MI_Ground_Grass", "gravel": "MI_Ground_Gravel", "water": "MI_Water_Seine",
    "quay": "MI_Ground_Quay", "stone": "MI_Stone_Limestone", "quaywall": "MI_Stone_Quay", "grey": "MI_Stone_Grey",
    "iron": "MI_Paint_Iron", "lamp": "MI_Paint_LampPost", "glow": "MI_Lamp_Glow", "bark": "MI_Paint_Bark",
    "leaf": "MI_Foliage", "gold": "MI_Paint_Gold", "rubble": "MI_Ground_Rubble", "scorch": "MI_Ground_Scorched",
    "damaged": "MI_Ground_Damaged", "char": "MI_Paint_Charred", "car": "MI_Paint_Car", "glass": "MI_Glass",
    "bed": "MI_Ground_Courtyard", "hull": "MI_Paint_Iron", "deck": "MI_Paint_Frame", "cabin": "MI_Paint_Door",
    "concrete": "MI_Paint_Concrete",
}
SLOTS = list(SLOT_MATERIALS)


def builder():
    return MeshBuilder(SLOTS)


# ---------------------------------------------------------------- 2D helpers
def rounded_rect(x0, x1, y0, y1, r, seg=5):
    """CCW rounded rectangle."""
    pts = []
    for cx, cy, a0 in ((x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180), (x1 - r, y0 + r, 270)):
        for i in range(seg + 1):
            a = math.radians(a0 + 90.0 * i / seg)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def rect(mb, slot, x0, x1, y0, y1, z):
    mb.poly(slot, [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], Z)


def ring(mb, slot, h0, h1, z, cx=0.0, cy=0.0):
    """Square ring between half sizes h0 < h1 (4 trapezoids)."""
    for k in range(4):
        c, s = [(1, 0), (0, 1), (-1, 0), (0, -1)][k]

        def P(a, b):
            # a along the side, b outward
            return (cx + c * b - s * a, cy + s * b + c * a, z)
        mb.poly(slot, [P(-h0, h0), P(h0, h0), P(h1, h1), P(-h1, h1)], Z)


def kerb_walls(mb, pts, z0, z1, slot="kerb", top_w=0.3):
    """Vertical kerb face around a CCW outline + granite kerb top strip."""
    mb.band(slot, pts + [pts[0]], False, -top_w, 0.0, z0, z1, bottom=False, ends=False)


# ---------------------------------------------------------------- ground cells
def crosswalks(mb, z=0.012, kerb=KERB, near=77.0, far=81.5):
    """Zebra crossings on the cell's half of each road, just before the four corners.
    Stripes run with the traffic (0.8 m wide, 1.7 m pitch) and are spread across the carriageway."""
    for sx in (-1, 1):
        for sy in (-1, 1):
            for i in range(6):
                a0 = kerb + 0.9 + i * 1.7
                ta, tb = sorted((sx * a0, sx * (a0 + 0.8)))
                la, lb = sorted((sy * near, sy * far))
                rect(mb, "marking", ta, tb, la, lb, z)  # road along y (x ~ sx*kerb..100)
                ta, tb = sorted((sy * a0, sy * (a0 + 0.8)))
                la, lb = sorted((sx * near, sx * far))
                rect(mb, "marking", la, lb, ta, tb, z)  # road along x (y ~ sy*kerb..100)


def pad(mb, kind, z=0.2, cx=0.0, cy=0.0):
    """Board pad: light/dark checker tile with a pale stone border (the cell where a piece stands)."""
    inner = {"light": "light", "dark": "dark", "garden": "grass", "scorched": "scorch"}.get(kind, "light")
    rect(mb, inner, cx - PAD0, cx + PAD0, cy - PAD0, cy + PAD0, z)
    ring(mb, "pad", PAD0, PAD1, z + 0.01, cx, cy)


def ground_cell(kind="light", board=True, scorched=False, seed=0):
    """kind: light | dark (board checker pad) or garden / court (background courtyard); scorched adds battle damage."""
    r = rng(seed)
    mb = builder()
    rect(mb, "damaged" if scorched else "road", -HALF, HALF, -HALF, HALF, 0.0)
    outline = rounded_rect(-KERB, KERB, -KERB, KERB, CORNER_R)
    mb.polygon2d("walk", outline, KERB_H)
    kerb_walls(mb, outline, 0.0, KERB_H + 0.01)
    court = "scorch" if scorched else ("gravel" if kind in ("garden", "base") else "court")
    rect(mb, court, -COURT - 1, COURT + 1, -COURT - 1, COURT + 1, 0.18)
    if board:
        pad(mb, kind)
    elif kind == "garden":
        # background courtyard: lawn quarters with gravel cross paths
        for sx in (-1, 1):
            for sy in (-1, 1):
                xa, xb = sorted((sx * 4.0, sx * 58.0))
                ya, yb = sorted((sy * 4.0, sy * 58.0))
                rect(mb, "grass", xa, xb, ya, yb, 0.2)
    crosswalks(mb)
    if scorched:
        n = 0
        while n < 10:
            x, y = r.uniform(-97, 97), r.uniform(-97, 97)
            if abs(x) < KERB and abs(y) < KERB and (abs(x) > COURT - 3 or abs(y) > COURT - 3):
                continue  # not under the buildings
            crater(mb, x, y, r.uniform(2.0, 4.5), r, 0.0 if max(abs(x), abs(y)) > KERB else 0.25)
            n += 1
    return mb


def crater(mb, x, y, rad, r, z=0.0):
    n = 9
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        rr = rad * r.uniform(0.8, 1.15)
        pts.append((x + rr * math.cos(a), y + rr * math.sin(a)))
    c = (x, y, z - rad * 0.25)
    for i in range(n):
        p, q = pts[i], pts[(i + 1) % n]
        tri = [c, (p[0], p[1], z + 0.02), (q[0], q[1], z + 0.02)]
        mb.poly("scorch", tri, geom.newell(tri) if geom.newell(tri)[2] > 0 else geom.mul(geom.newell(tri), -1))
    for i in range(n):
        p, q = pts[i], pts[(i + 1) % n]
        o1 = (x + (p[0] - x) * 1.35, y + (p[1] - y) * 1.35)
        o2 = (x + (q[0] - x) * 1.35, y + (q[1] - y) * 1.35)
        quad = [(p[0], p[1], z + 0.02), (q[0], q[1], z + 0.02), (o2[0], o2[1], z + 0.35), (o1[0], o1[1], z + 0.35)]
        nn = geom.newell(quad)
        mb.poly("rubble", quad, nn if nn[2] > 0 else geom.mul(nn, -1))


# ---------------------------------------------------------------- open cells
def plaza(kinds):
    """2x2 cell plaza centred on the origin (Place de la Concorde stand-in). kinds: dict (sx, sy) -> pad kind."""
    mb = builder()
    H = 2 * HALF
    rect(mb, "road", -H, H, -H, H, 0.0)
    outline = rounded_rect(-(H - ROAD_HALF), H - ROAD_HALF, -(H - ROAD_HALF), H - ROAD_HALF, 8.0, 7)
    mb.polygon2d("pad", outline, KERB_H)
    kerb_walls(mb, outline, 0.0, KERB_H + 0.01)
    # inlaid board lines through the plaza centre + a compass rose ring around the obelisk
    e = H - ROAD_HALF
    rect(mb, "line", -LINE_W / 2, LINE_W / 2, -e, e, KERB_H + 0.02)
    rect(mb, "line", -e, e, -LINE_W / 2, LINE_W / 2, KERB_H + 0.02)
    for (sx, sy), kind in kinds.items():
        pad(mb, kind, KERB_H + 0.03, sx * HALF, sy * HALF)
    # radial paving bands (darker granite) between the pads
    for k in range(8):
        a = math.radians(22.5 + 45 * k)
        c, s = math.cos(a), math.sin(a)
        p0, p1 = 22.0, 160.0
        w = 1.2
        pts = [(c * p0 - s * w, s * p0 + c * w), (c * p0 + s * w, s * p0 - c * w), (c * p1 + s * w, s * p1 - c * w), (c * p1 - s * w, s * p1 + c * w)]
        mb.poly("dark", [(p[0], p[1], KERB_H + 0.015) for p in pts], Z)
    circ = [(20.0 * math.cos(2 * math.pi * i / 32), 20.0 * math.sin(2 * math.pi * i / 32)) for i in range(32)]
    mb.polygon2d("dark", circ, KERB_H + 0.025)
    crosswalks_big(mb, H)
    return mb


def crosswalks_big(mb, H):
    for sx in (-1, 1):
        for sy in (-1, 1):
            for i in range(6):
                x0 = H - ROAD_HALF + 0.9 + i * 1.7
                xa, xb = (x0, x0 + 0.8) if sx > 0 else (-x0 - 0.8, -x0)
                ya, yb = (H - 21.0, H - 17.0) if sy > 0 else (-H + 17.0, -H + 21.0)
                rect(mb, "marking", xa, xb, ya, yb, 0.012)
                rect(mb, "marking", ya, yb, xa, xb, 0.012)


def champ_de_mars(n_cells=4, tower_cell=2):
    """Park strip of n cells along +x (cell-local x from -100 to 200*n-100), lawns + gravel alleys."""
    mb = builder()
    x0, x1 = -HALF, -HALF + 2 * HALF * n_cells
    rect(mb, "road", x0, x1, -HALF, HALF, 0.0)
    outline = rounded_rect(x0 + ROAD_HALF, x1 - ROAD_HALF, -KERB, KERB, CORNER_R)
    mb.polygon2d("gravel", outline, KERB_H)
    kerb_walls(mb, outline, 0.0, KERB_H + 0.01)
    tx = tower_cell * 2 * HALF
    for i in range(n_cells):
        cx = i * 2 * HALF
        if i == tower_cell:
            continue
        for sy in (-1, 1):
            ya, yb = sorted((sy * 9.0, sy * 64.0))
            rect(mb, "grass", cx - 80.0, cx + 80.0, ya, yb, KERB_H + 0.03)
    # sanded square under the tower
    rect(mb, "court", tx - 78.0, tx + 78.0, -78.0, 78.0, KERB_H + 0.02)
    return mb


def cathedral_close(n_cells=2):
    """Paved close of n cells along +x (cell-local x from -100 to 200*n-100): quay-stone parvis with a plaza-stone
    border, kerbs and the surrounding half roads. Notre-Dame (06_landmarks.py) stands on it at z = KERB_H + 0.02."""
    mb = builder()
    x0, x1 = -HALF, -HALF + 2 * HALF * n_cells
    rect(mb, "road", x0, x1, -HALF, HALF, 0.0)
    outline = rounded_rect(x0 + ROAD_HALF, x1 - ROAD_HALF, -KERB, KERB, CORNER_R)
    mb.polygon2d("pad", outline, KERB_H)
    kerb_walls(mb, outline, 0.0, KERB_H + 0.01)
    rect(mb, "quay", x0 + KERB + 6.0, x1 - KERB - 6.0, -KERB + 6.0, KERB - 6.0, KERB_H + 0.02)
    # low stone bollard line along the long sides
    x = x0 + KERB + 10.0
    while x < x1 - KERB - 8.0:
        for sy in (-1.0, 1.0):
            prism(mb, "grey", (x, sy * (KERB - 3.0), KERB_H), (x, sy * (KERB - 3.0), KERB_H + 0.9), 0.3, 0.25, 8)
        x += 20.0
    return mb


# ---------------------------------------------------------------- board grid
def board_lines(n=8, cell=200.0, z=0.02):
    """Grid lines on the street centre lines of the n x n board (origin = board centre)."""
    mb = builder()
    h = n * cell / 2.0
    for i in range(n + 1):
        c = -h + i * cell
        w = BORDER_W if i in (0, n) else LINE_W
        ext = h + BORDER_W / 2
        rect(mb, "line", c - w / 2, c + w / 2, -ext, ext, z)
        rect(mb, "line", -ext, ext, c - w / 2, c + w / 2, z + 0.002)
    return mb


# ---------------------------------------------------------------- props
def icosphere(sub=1):
    t = (1.0 + 5 ** 0.5) / 2.0
    vs = [norm(v) for v in [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
                            (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]]
    fs = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8),
          (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    for _ in range(sub):
        cache = {}

        def mid(a, b):
            k = (min(a, b), max(a, b))
            if k not in cache:
                cache[k] = len(vs)
                vs.append(norm(geom.mul(geom.add(vs[a], vs[b]), 0.5)))
            return cache[k]
        nf = []
        for a, b, c in fs:
            ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
            nf += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        fs = nf
    return vs, fs


def blob(mb, slot, c, rx, ry, rz, r, jitter=0.18, sub=1):
    vs, fs = icosphere(sub)
    js = [1.0 + r.uniform(-jitter, jitter) for _ in vs]
    P = [(c[0] + v[0] * rx * j, c[1] + v[1] * ry * j, c[2] + v[2] * rz * j) for v, j in zip(vs, js)]
    for a, b, cc in fs:
        tri = [P[a], P[b], P[cc]]
        cen = geom.mul(geom.add(geom.add(tri[0], tri[1]), tri[2]), 1.0 / 3.0)
        mb.poly(slot, tri, geom.sub(cen, c))


def prism(mb, slot, p0, p1, r0, r1, sides=7, caps=True):
    """Tapered prism between points p0 and p1 (radii r0, r1)."""
    ax = norm(geom.sub(p1, p0))
    up = (1.0, 0.0, 0.0) if abs(ax[2]) > 0.9 else Z
    u = norm(geom.cross(ax, up))
    w = geom.cross(ax, u)
    ring0, ring1 = [], []
    for i in range(sides):
        a = 2 * math.pi * i / sides
        d = geom.add(geom.mul(u, math.cos(a)), geom.mul(w, math.sin(a)))
        ring0.append(geom.add(p0, geom.mul(d, r0)))
        ring1.append(geom.add(p1, geom.mul(d, r1)))
    for i in range(sides):
        j = (i + 1) % sides
        quad = [ring0[i], ring0[j], ring1[j], ring1[i]]
        mid = geom.mul(geom.add(ring0[i], ring0[j]), 0.5)
        mb.poly(slot, quad, geom.sub(mid, p0))
    if caps:
        mb.poly(slot, ring1, ax)
        mb.poly(slot, ring0, geom.mul(ax, -1))


def tree(seed=0, height=13.0):
    """Plane tree: tapered trunk, forked limbs, lumpy canopy of jittered icospheres."""
    r = rng(seed)
    mb = builder()
    h = height * r.uniform(0.85, 1.12)
    fork = h * 0.36
    prism(mb, "bark", (0, 0, -0.3), (0, 0, fork), 0.32, 0.24)
    limbs = []
    for i in range(r.randint(3, 4)):
        a = 2 * math.pi * i / 4 + r.uniform(-0.5, 0.5)
        lean = r.uniform(0.35, 0.6)
        end = (math.cos(a) * h * 0.22 * lean * 2, math.sin(a) * h * 0.22 * lean * 2, fork + h * r.uniform(0.28, 0.4))
        prism(mb, "bark", (0, 0, fork - 0.2), end, 0.17, 0.08, 5)
        limbs.append(end)
    cz = h * 0.66
    crx = h * 0.34
    blob(mb, "leaf", (0, 0, cz), crx * 0.8, crx * 0.8, h * 0.22, r, 0.2)
    for e in limbs:
        c = (e[0] * 1.1, e[1] * 1.1, e[2] + r.uniform(-0.3, 0.6))
        s = h * r.uniform(0.17, 0.22)
        blob(mb, "leaf", c, s, s, s * 0.8, r, 0.22)
    for _ in range(r.randint(3, 5)):
        a = r.uniform(0, 2 * math.pi)
        d = crx * r.uniform(0.45, 0.8)
        c = (math.cos(a) * d, math.sin(a) * d, cz + r.uniform(-1.2, 1.8))
        s = h * r.uniform(0.12, 0.17)
        blob(mb, "leaf", c, s, s, s * 0.85, r, 0.22)
    return mb


def lamp():
    """Paris candelabra lamp post (4.6 m): stepped base, fluted shaft, lantern with glowing panes."""
    mb = builder()
    prism(mb, "lamp", (0, 0, 0), (0, 0, 0.55), 0.24, 0.18, 8)
    prism(mb, "lamp", (0, 0, 0.55), (0, 0, 3.9), 0.085, 0.06, 8)
    prism(mb, "lamp", (0, 0, 0.9), (0, 0, 1.05), 0.14, 0.14, 8)
    prism(mb, "lamp", (0, 0, 3.9), (0, 0, 4.02), 0.18, 0.12, 8)
    prism(mb, "glow", (0, 0, 4.02), (0, 0, 4.55), 0.16, 0.22, 6, caps=False)
    prism(mb, "lamp", (0, 0, 4.55), (0, 0, 4.8), 0.26, 0.04, 6)
    return mb


def obelisk():
    """Luxor obelisk on its pedestal (total ~33 m), gilded pyramidion, octagonal fountain-style base."""
    mb = builder()
    oct_ = [(9.0 * math.cos(math.radians(22.5 + 45 * i)), 9.0 * math.sin(math.radians(22.5 + 45 * i))) for i in range(8)]
    mb.band("grey", oct_, True, -9.0 + 0.01, 0.0, 0.0, 0.6)
    mb.polygon2d("grey", oct_, 0.6)
    mb.box("stone", -3.2, 3.2, -3.2, 3.2, 0.6, 1.4)
    mb.box("grey", -2.4, 2.4, -2.4, 2.4, 1.4, 7.4)
    mb.box("stone", -2.8, 2.8, -2.8, 2.8, 7.4, 8.2)
    z0, z1, w0, w1 = 8.2, 30.6, 1.25, 0.9
    for k in range(4):
        c, s = [(1, 0), (0, 1), (-1, 0), (0, -1)][k]

        def P(a, b, z):
            return (c * b - s * a, s * b + c * a, z)
        mb.poly("quaywall", [P(-w0, w0, z0), P(w0, w0, z0), P(w1, w1, z1), P(-w1, w1, z1)], (c, s, (w0 - w1) / (z1 - z0)))
        mb.poly("gold", [P(-w1, w1, z1), P(w1, w1, z1), P(0, 0, z1 + 2.4)], (c, s, w1 / 2.4))
    return mb


def car(seed=0, burnt=False):
    r = rng(seed)
    mb = builder()
    mb.color = (r.random(), r.random(), 1.0, 1.0)
    L, W = r.uniform(3.9, 4.5), 1.75
    body = "char" if burnt else "car"
    fr = Frame((-L / 2, 0.0), (L / 2, 0.0))
    mb.extrude_profile(body, fr, [(0, 0.3), (L, 0.3), (L, 0.75), (L - 0.15, 0.95), (0, 0.95)], -W / 2, W / 2)
    cab = [(L * 0.25, 0.95), (L * 0.78, 0.95), (L * 0.62, 1.42), (L * 0.33, 1.42)]
    mb.extrude_profile("char" if burnt else "glass", fr, cab, -W / 2 + 0.12, W / 2 - 0.12)
    for a in (0.7, L - 0.75):
        for b in (-W / 2 + 0.05, W / 2 - 0.25):
            mb.fbox("iron", fr, a - 0.33, a + 0.33, b, b + 0.2, 0.0, 0.62, skip=())
    return mb


def barge(seed=0):
    """Seine peniche: 38 m hull with pointed bow, deck house, wheelhouse."""
    r = rng(seed)
    mb = builder()
    L, W = r.uniform(32, 40), 5.1
    hull = [(-L / 2, -W / 2), (L / 2 - 4.0, -W / 2), (L / 2, 0.0), (L / 2 - 4.0, W / 2), (-L / 2, W / 2)]
    mb.band("hull", hull, True, -W, 0.0, -0.8, 1.2, bottom=False)
    mb.polygon2d("deck", geom.offset_polyline(hull, -0.05, True), 1.2)
    fr = Frame((-L / 2, 0.0), (L / 2, 0.0))
    a0 = -L / 2 + 3.0
    a1 = a0 + L * r.uniform(0.45, 0.6)
    mb.fbox("cabin", fr, a0 - (-L / 2), a1 - (-L / 2), -1.9, 1.9, 1.2, 3.0, skip=("bottom",))
    for a in range(int(a0 - (-L / 2)) + 1, int(a1 - (-L / 2)) - 1, 2):
        mb.fquad("glass", fr, a, a + 1.1, 1.9, 2.6, 1.905)
    mb.fbox("deck", fr, 1.0, 4.0, -1.6, 1.6, 1.2, 4.2, skip=("bottom",))
    return mb



# ---------------------------------------------------------------- Seine
Y_ROAD1 = 1011.0  # kerb of the west quay road
Y_WALL0 = 1019.0  # west quay wall (top of the embankment)
Y_WATER0 = 1030.0  # edge of the west lower quay
Y_WATER1 = 1170.0
Y_WALL1 = 1181.0
Y_ROAD2 = 1189.0
Z_LOWQ = -4.5
Z_WATER = -6.4
Z_BED = -10.0
# B4 quay upgrade
FLOOD_H = 1.35  # flood wall on the upper quay: concrete body to FLOOD_H - 0.15, stone coping on top
STAIR_W = 2.6  # quay stair width (landing in a gap of the flood wall, flight hugging the quay wall)
STAIR_N, STAIR_TREAD = 28, 0.32
STAIRS_X = (-62.0, 38.0)  # segment-local x of the stair landing on the west (+1) / east (-1) quay, plain segments only
GOLD_PYLON_H = 14.0  # Alexandre III style pylons at the four bridge ends (gilded group on top)


def stair_span(side):
    """(x0, x1) segment-local extent of the quay stair on `side` (landing + flight), for layout keep-outs."""
    sx = STAIRS_X[0] if side > 0 else STAIRS_X[1]
    return sx, sx + STAIR_W + (STAIR_N - 1) * STAIR_TREAD


def bar(mb, slot, p, q, t=0.05):
    """Square-section bar of half thickness t between points p and q."""
    d = geom.sub(q, p)
    ln = geom.length(d)
    ax = norm(d)
    up = (1.0, 0.0, 0.0) if abs(ax[2]) > 0.95 else Z
    ay = norm(geom.cross(up, ax))
    az = geom.cross(ax, ay)
    mb.obox(slot, geom.mul(geom.add(p, q), 0.5), ax, ay, az, ln / 2.0, t, t)


def baluster(mb, slot, x, y, z0, h=0.65):
    """Vase-shaped stone baluster (4 hexagonal frusta, no inner caps)."""
    zs = [z0, z0 + 0.1 * h, z0 + 0.55 * h, z0 + 0.85 * h, z0 + h]
    rs = [0.10, 0.07, 0.12, 0.06, 0.09]
    for i in range(4):
        prism(mb, slot, (x, y, zs[i]), (x, y, zs[i + 1]), rs[i], rs[i + 1], 6, caps=False)


def quay_stair(mb, sx, wall_y, side):
    """Stair from the upper promenade (KERB_H) to the lower quay (Z_LOWQ): landing in the flood-wall gap at
    x in [sx, sx + STAIR_W], flight running towards +x along the river face of the quay wall, iron handrail."""
    y0, y1 = sorted((wall_y, wall_y + side * STAIR_W))
    outer = wall_y + side * STAIR_W
    wall_face = "ny" if side > 0 else "py"  # face against the quay wall: never visible
    mb.box("stone", sx, sx + STAIR_W, y0, y1, Z_LOWQ, KERB_H, skip=("nz", wall_face))
    rise = (KERB_H - Z_LOWQ) / STAIR_N
    xa = sx + STAIR_W
    for k in range(1, STAIR_N):
        top = KERB_H - k * rise
        mb.box("stone", xa, xa + STAIR_TREAD, y0, y1, Z_LOWQ, top, skip=("nz", "nx", wall_face))
        xa += STAIR_TREAD
    # handrail on the open side: posts + sloped rail
    xr = sx + STAIR_W
    p_top = (xr, outer, KERB_H + 1.0)
    p_bot = (xa, outer, Z_LOWQ + 1.0)
    bar(mb, "iron", p_top, p_bot, 0.03)
    for k in range(0, STAIR_N, 5):
        x = sx + STAIR_W + k * STAIR_TREAD
        zb = KERB_H - (k + 1) * rise
        bar(mb, "iron", (x, outer, zb), (x, outer, zb + 1.0 + 0.02), 0.025)
    bar(mb, "iron", (sx, outer, KERB_H), (sx, outer, KERB_H + 1.0), 0.025)
    bar(mb, "iron", (sx, outer, KERB_H + 1.0), p_top, 0.03)


def seine_segment(bridge=False, x0=-100.0, x1=100.0, style="classic"):
    """River cell y 1000..1200 (absolute), x0..x1 local; the bridge (if any) sits on x = 0.

    B4: the upper-quay parapet is now a concrete flood wall with stone coping; plain segments get one stair per quay
    down to the lower quay (STAIRS_X); bridges get a balustrade (style "classic") or the gilded Alexandre III treatment
    (style "gold": pylons with gilded groups, gilded keystones)."""
    mb = builder()
    gap = 16.0 if bridge else 0.0
    spans = [(x0, -gap), (gap, x1)] if bridge else [(x0, x1)]
    # quay roads (other half of the carriageway next to the col 8 / col 10 cells)
    rect(mb, "road", x0, x1, 1000.0, Y_ROAD1, 0.0)
    rect(mb, "road", x0, x1, Y_ROAD2, 1200.0, 0.0)
    for y0, y1, wall_y, side in ((Y_ROAD1, Y_WALL0, Y_WALL0, 1.0), (Y_WALL1, Y_ROAD2, Y_WALL1, -1.0)):
        sx = None if bridge else (STAIRS_X[0] if side > 0 else STAIRS_X[1])
        for (a, b) in spans:
            rect(mb, "walk", a, b, y0, y1, KERB_H)
            ky = y0 if side > 0 else y1
            mb.poly("kerb", [(a, ky, 0.0), (b, ky, 0.0), (b, ky, KERB_H + 0.01), (a, ky, KERB_H + 0.01)], (0, -side, 0))
            # flood wall: concrete body + stone coping, open at the stair landing
            p0, p1 = (wall_y - side * 0.55, wall_y) if side > 0 else (wall_y, wall_y + 0.55)
            pa, pb = min(p0, p1), max(p0, p1)
            pieces = [(a, b)]
            if sx is not None and a < sx < b:
                pieces = [(a, sx), (sx + STAIR_W, b)]
            for fa, fb in pieces:
                mb.box("concrete", fa, fb, pa, pb, KERB_H, FLOOD_H - 0.15, skip=("nz",))
                mb.box("stone", fa, fb, pa - 0.08, pb + 0.08, FLOOD_H - 0.15, FLOOD_H, skip=())
        if sx is not None:
            quay_stair(mb, sx, wall_y, side)
    # embankment walls, lower quays, water, bed
    for wall_y, edge_y, side in ((Y_WALL0, Y_WATER0, 1.0), (Y_WALL1, Y_WATER1, -1.0)):
        mb.poly("quaywall", [(x0, wall_y, Z_LOWQ), (x1, wall_y, Z_LOWQ), (x1, wall_y, KERB_H), (x0, wall_y, KERB_H)], (0, side, 0))
        ya, yb = sorted((wall_y, edge_y))
        rect(mb, "quay", x0, x1, ya, yb, Z_LOWQ)
        mb.poly("quaywall", [(x0, edge_y, Z_BED), (x1, edge_y, Z_BED), (x1, edge_y, Z_LOWQ), (x0, edge_y, Z_LOWQ)], (0, side, 0))
        # mooring bollards
        x = x0 + 12.0
        while x < x1 - 5.0:
            by = edge_y - side * 0.8
            prism(mb, "iron", (x, by, Z_LOWQ), (x, by, Z_LOWQ + 0.6), 0.22, 0.18, 8)
            x += 25.0
    rect(mb, "water", x0, x1, Y_WATER0, Y_WATER1, Z_WATER)
    rect(mb, "bed", x0, x1, Y_WATER0, Y_WATER1, Z_BED)
    if bridge:
        stone_bridge(mb, style=style)
    return mb


def arch_points(a0, a1, zs, zc, n=12):
    """Segmental arch from (a0, zs) to (a1, zs) with crown zc."""
    span = a1 - a0
    rise = zc - zs
    R = (span * span / 4.0 + rise * rise) / (2.0 * rise)
    cx, cz = (a0 + a1) / 2.0, zc - R
    th = math.asin(span / 2.0 / R)
    return [(cx + R * math.sin(-th + 2 * th * i / n), cz + R * math.cos(-th + 2 * th * i / n)) for i in range(n + 1)]


def stone_bridge(mb, half_w=15.0, style="classic"):
    """Three-arch masonry bridge on x = 0 spanning the Seine (Pont de la Concorde stand-in).

    B4: balustrade (plinth, vase balusters, handrail, lamp pedestals) instead of the solid parapet. style "gold"
    (Pont Alexandre III stand-in) adds four tall pylons with gilded groups at the bridge ends and gilded keystone
    cartouches on every arch face."""
    piers = [(1071.0, 1077.0), (1123.0, 1129.0)]
    zs, zc, ztop = -4.2, -1.4, -0.03
    springs = [(Y_WATER0, piers[0][0]), (piers[0][1], piers[1][0]), (piers[1][1], Y_WATER1)]
    prof = [(Y_WALL0, Z_BED), (Y_WATER0, Z_BED)]
    for i, (a0, a1) in enumerate(springs):
        prof.append((a0, zs))
        prof += arch_points(a0, a1, zs, zc)[1:-1]
        prof.append((a1, zs))
        if i < 2:
            prof += [(a1, Z_BED), (piers[i][1], Z_BED)]
    prof += [(Y_WATER1, Z_BED), (Y_WALL1, Z_BED), (Y_WALL1, ztop), (Y_WALL0, ztop)]
    fr = Frame((0.0, 0.0), (0.0, 1.0))  # a = world y, b = world x
    mb.extrude_profile("stone", fr, prof, -half_w, half_w)
    # voussoir rings and cornice on both faces
    for s in (-1.0, 1.0):
        b0, b1 = (half_w, half_w + 0.18) if s > 0 else (-half_w - 0.18, -half_w)
        for a0, a1 in springs:
            inner = arch_points(a0, a1, zs, zc)
            outer = arch_points(a0 - 1.1, a1 + 1.1, zs, zc + 1.0)
            ringp = inner + outer[::-1]
            mb.extrude_profile("grey", fr, ringp, b0, b1)
        mb.extrude_profile("stone", fr, [(Y_WALL0 - 8.0, -1.0), (Y_WALL1 + 8.0, -1.0), (Y_WALL1 + 8.0, -0.35), (Y_WALL0 - 8.0, -0.35)],
                           b0, b1 + (0.3 if s > 0 else 0.0) if s > 0 else b1)
    # piers: cutwaters on both sides
    for pa, pb in piers:
        pm = (pa + pb) / 2.0
        for s in (-1.0, 1.0):
            base = s * half_w
            tip = s * (half_w + 5.0)
            pts = [(base, pa), (s * (half_w + 2.0), pa), (tip, pm), (s * (half_w + 2.0), pb), (base, pb)]
            pts = [(p[0], p[1]) for p in pts]
            if geom.poly_area(pts) < 0:
                pts = pts[::-1]
            mb.band("grey", pts, True, -0.01, 0.0, Z_BED, -2.6, bottom=False)
            mb.polygon2d("stone", pts, -2.6)
    # deck: carriageway, sidewalks with kerbs, balustrades
    rect(mb, "road", -ROAD_HALF, ROAD_HALF, Y_ROAD1, Y_ROAD2, 0.0)
    pedestals = (Y_ROAD1 + 4.0, 1051.0, 1100.0, 1149.0, Y_ROAD2 - 4.0)
    for s in (-1.0, 1.0):
        xa, xb = sorted((s * ROAD_HALF, s * (half_w - 0.6)))
        rect(mb, "walk", xa, xb, Y_ROAD1, Y_ROAD2, KERB_H)
        kx = s * ROAD_HALF
        mb.poly("kerb", [(kx, Y_ROAD1, 0.0), (kx, Y_ROAD2, 0.0), (kx, Y_ROAD2, KERB_H + 0.01), (kx, Y_ROAD1, KERB_H + 0.01)], (-s, 0, 0))
        pa, pb = sorted((s * (half_w - 0.6), s * half_w))
        pm = (pa + pb) / 2.0
        mb.box("stone", pa, pb, Y_ROAD1, Y_ROAD2, KERB_H, KERB_H + 0.25, skip=("nz",))  # plinth
        mb.box("stone", pa - 0.08, pb + 0.08, Y_ROAD1, Y_ROAD2, 1.05, 1.2, skip=())  # handrail
        for y in pedestals:
            mb.box("stone", pa - 0.25, pb + 0.25, y - 0.8, y + 0.8, KERB_H, 1.6, skip=("nz",))
        y = Y_ROAD1 + 0.35
        while y < Y_ROAD2 - 0.3:
            if all(abs(y - py) > 0.95 for py in pedestals):
                baluster(mb, "stone", pm, y, KERB_H + 0.25, 1.05 - (KERB_H + 0.25))
            y += 0.36
    if style == "gold":
        gold_bridge_ornaments(mb, half_w, springs, zs, zc)


def gold_bridge_ornaments(mb, half_w, springs, zs, zc):
    """Pont Alexandre III stand-in: pylons with gilded groups at the four ends, gilded keystone cartouches."""
    r = rng(1900)
    for s in (-1.0, 1.0):
        px = s * (half_w + 2.6)
        for py in (Y_ROAD1 + 1.8, Y_ROAD2 - 1.8):
            mb.box("stone", px - 2.0, px + 2.0, py - 2.0, py + 2.0, 0.0, 2.2)  # base
            mb.box("stone", px - 1.5, px + 1.5, py - 1.5, py + 1.5, 2.2, GOLD_PYLON_H - 1.0)  # shaft
            for zr in (5.0, 9.0):  # banding
                mb.box("grey", px - 1.6, px + 1.6, py - 1.6, py + 1.6, zr, zr + 0.35)
            mb.box("stone", px - 1.9, px + 1.9, py - 1.9, py + 1.9, GOLD_PYLON_H - 1.0, GOLD_PYLON_H)  # capital
            # gilded group: rearing horse + winged figure, abstracted as jittered blobs
            zt = GOLD_PYLON_H
            blob(mb, "gold", (px, py, zt + 1.2), 1.4, 0.7, 1.1, r, 0.2)
            blob(mb, "gold", (px + s * 0.4, py, zt + 2.6), 0.5, 0.45, 1.0, r, 0.15)
            for w in (-1.0, 1.0):
                blob(mb, "gold", (px - s * 0.3, py + w * 0.9, zt + 3.1), 0.25, 0.9, 0.55, r, 0.2)
    for s in (-1.0, 1.0):
        b = s * (half_w + 0.2)
        for a0, a1 in springs:
            ym = (a0 + a1) / 2.0
            blob(mb, "gold", (b, ym, zc + 0.5), 0.35, 1.6, 0.9, r, 0.12)  # keystone cartouche
            for t in (0.25, 0.75):  # garland ends
                yy = a0 + (a1 - a0) * t
                blob(mb, "gold", (b, yy, zc - 0.1), 0.25, 0.9, 0.35, r, 0.15)


def bridge_lamp_positions(half_w=15.0):
    return [(s * (half_w - 0.3), y) for s in (-1.0, 1.0) for y in (Y_ROAD1 + 4.0, 1051.0, 1100.0, 1149.0, Y_ROAD2 - 4.0)]


if __name__ == "__main__":
    import time

    for name, fn in (("cell light", lambda: ground_cell("light")), ("cell garden", lambda: ground_cell("garden", False)),
                     ("cell scorched", lambda: ground_cell("dark", True, True, 3)),
                     ("plaza", lambda: plaza({(-1, -1): "dark", (1, -1): "light", (-1, 1): "light", (1, 1): "dark"})),
                     ("champ", champ_de_mars), ("lines", board_lines), ("seine", seine_segment),
                     ("seine+bridge", lambda: seine_segment(True)), ("tree", tree), ("lamp", lamp), ("obelisk", obelisk),
                     ("car", car), ("barge", barge), ("seine+gold", lambda: seine_segment(True, style="gold"))):
        t0 = time.time()
        mb = fn()
        print("%-14s tris=%6d slots=%-40s bounds=%s %.2fs" % (name, mb.tri_count(), ",".join(mb.used_slots())[:40],
                                                         tuple(tuple(round(v, 1) for v in b) for b in mb.bounds()), time.time() - t0))
